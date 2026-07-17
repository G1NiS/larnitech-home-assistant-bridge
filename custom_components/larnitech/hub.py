from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import replace
from typing import Any

from homeassistant.core import HomeAssistant, callback

from .api import LarnitechApiClient
from .models import DeviceStatus, LarnitechDevice

_LOGGER = logging.getLogger(__name__)

Listener = Callable[[DeviceStatus], None]
SETUP_AREA = "Setup"


def _is_setup_area(area: str | None) -> bool:
    return area is None or not area.strip() or area.strip().lower() == SETUP_AREA.lower()


def _relation_addrs(raw: dict[str, Any]) -> list[str]:
    addrs: list[str] = []
    for key in ("linked", "contains", "items", "refs", "item_refs"):
        value = raw.get(key)
        if not isinstance(value, list):
            continue
        for item in value:
            if isinstance(item, dict) and item.get("addr"):
                addrs.append(str(item["addr"]))
            elif isinstance(item, str):
                addrs.append(item)
    return addrs


class LarnitechHub:
    def __init__(self, hass: HomeAssistant, host: str, port: int, api_key: str) -> None:
        self.hass = hass
        self.host = host
        self.port = port
        self.api_key = api_key
        self.devices: list[LarnitechDevice] = []
        self.devices_by_addr: dict[str, LarnitechDevice] = {}
        self.status_by_addr: dict[str, Any] = {}
        self._listeners: dict[str, set[Listener]] = {}
        self._status_api = LarnitechApiClient(host, port, api_key, name="status")
        self._command_api = LarnitechApiClient(host, port, api_key, name="command")
        self._status_task: asyncio.Task | None = None
        self._closed = False

    async def async_setup(self) -> None:
        await self._command_api.connect()
        await self._status_api.connect()
        self.devices = self._with_inferred_areas(await self._status_api.get_devices())
        self.devices_by_addr = {device.addr: device for device in self.devices}
        for device in self.devices:
            if "status" in device.raw:
                self.status_by_addr[device.addr] = device.raw["status"]
        await self._status_api.subscribe_status()
        self._status_task = asyncio.create_task(self._status_loop())
        _LOGGER.info("Discovered %s Larnitech devices", len(self.devices))

    async def async_close(self) -> None:
        self._closed = True
        if self._status_task:
            self._status_task.cancel()
            try:
                await self._status_task
            except asyncio.CancelledError:
                pass
        await self._status_api.close()
        await self._command_api.close()

    async def async_set_status(self, addr: str, status: Any) -> None:
        await self._command_api.set_status(addr, status)

    @callback
    def async_add_listener(self, addr: str, listener: Listener) -> Callable[[], None]:
        listeners = self._listeners.setdefault(addr, set())
        listeners.add(listener)

        @callback
        def remove() -> None:
            listeners.discard(listener)

        return remove

    @staticmethod
    def _with_inferred_areas(devices: list[LarnitechDevice]) -> list[LarnitechDevice]:
        """Infer useful areas for linked physical items.

        API2 already exposes an `area` field for most logical items. Some physical
        inputs remain in `Setup` but have `linked` targets. In those cases the
        switch is grouped with the first linked target that has a non-Setup area.
        """
        area_by_addr = {
            device.addr: device.area
            for device in devices
            if device.area is not None and not _is_setup_area(device.area)
        }
        enriched: list[LarnitechDevice] = []
        for device in devices:
            if not _is_setup_area(device.area):
                enriched.append(device)
                continue

            inferred_area = None
            for addr in _relation_addrs(device.raw):
                related_area = area_by_addr.get(addr)
                if related_area:
                    inferred_area = related_area
                    break

            if inferred_area:
                enriched.append(replace(device, area=inferred_area))
            else:
                enriched.append(device)
        return enriched

    async def _status_loop(self) -> None:
        while not self._closed:
            try:
                async for message in self._status_api.raw_messages():
                    for status in self._status_api.extract_status_events(message):
                        self._handle_status(status)
            except asyncio.CancelledError:
                raise
            except Exception:
                if self._closed:
                    return
                _LOGGER.exception("Larnitech status stream failed, reconnecting")
                await self._status_api.close()
                await asyncio.sleep(5)
                try:
                    await self._status_api.connect()
                    await self._status_api.subscribe_status()
                except Exception:
                    _LOGGER.exception("Failed to reconnect Larnitech status stream")
                    await asyncio.sleep(10)

    @callback
    def _handle_status(self, status: DeviceStatus) -> None:
        self.status_by_addr[status.addr] = status.value
        for listener in list(self._listeners.get(status.addr, set())):
            listener(status)
