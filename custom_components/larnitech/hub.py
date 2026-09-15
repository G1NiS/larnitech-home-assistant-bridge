from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from contextlib import suppress
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant, callback

from .api import LarnitechApiClient
from .mapping import MappingRecorder
from .models import DeviceStatus, LarnitechDevice

_LOGGER = logging.getLogger(__name__)

Listener = Callable[[DeviceStatus], None]
AvailabilityListener = Callable[[bool], None]
SETUP_AREA = "Setup"
MAPPING_MAX_DURATION_SECONDS = 60 * 60
STATUS_REFRESH_INTERVAL_SECONDS = 120
RECONNECT_DELAY_SECONDS = 5
RECONNECT_MAX_DELAY_SECONDS = 60


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
    def __init__(
        self,
        hass: HomeAssistant,
        host: str,
        port: int,
        api_key: str,
        area_overrides: dict[str, str] | None = None,
    ) -> None:
        self.hass = hass
        self.host = host
        self.port = port
        self.api_key = api_key
        self.area_overrides = {
            str(addr).strip(): str(area).strip()
            for addr, area in (area_overrides or {}).items()
            if str(addr).strip() and str(area).strip()
        }
        self.devices: list[LarnitechDevice] = []
        self.devices_by_addr: dict[str, LarnitechDevice] = {}
        self.status_by_addr: dict[str, Any] = {}
        self._listeners: dict[str, set[Listener]] = {}
        self._availability_listeners: set[AvailabilityListener] = set()
        self._status_api = LarnitechApiClient(host, port, api_key, name="status")
        self._status_task: asyncio.Task | None = None
        self._mapping_recorder: MappingRecorder | None = None
        self._mapping_timeout_task: asyncio.Task[None] | None = None
        self._closed = False
        self._available = False
        self._ever_connected = False
        self.reconnect_count = 0
        self.last_disconnect: datetime | None = None

    @property
    def mapping_active(self) -> bool:
        return self._mapping_recorder is not None and self._mapping_recorder.active

    @property
    def available(self) -> bool:
        return self._available

    async def async_setup(self) -> None:
        # API2 commands and status events share this one persistent WebSocket.
        # Larnitech controllers may reject or drop simultaneous API2 connections.
        await self._status_api.connect()
        devices = await self._status_api.get_devices()
        devices = self._with_area_overrides(devices)
        self.devices = self._with_inferred_areas(devices)
        self.devices_by_addr = {device.addr: device for device in self.devices}
        for device in self.devices:
            if "status" in device.raw:
                self.status_by_addr[device.addr] = device.raw["status"]
        await self._status_api.subscribe_status()
        self._set_available(True)
        self._status_task = asyncio.create_task(self._status_loop())
        _LOGGER.info("Discovered %s Larnitech devices", len(self.devices))

    async def async_close(self) -> None:
        self._closed = True
        self._set_available(False)
        await self.async_stop_mapping()
        if self._status_task:
            self._status_task.cancel()
            try:
                await self._status_task
            except asyncio.CancelledError:
                pass
        await self._status_api.close()

    async def async_set_status(self, addr: str, status: Any) -> None:
        if not self.available:
            raise RuntimeError("Larnitech API2 is reconnecting")
        await self._status_api.set_status(addr, status)

    async def async_start_mapping(self, group_window_seconds: float = 3.0) -> Path:
        if self.mapping_active:
            assert self._mapping_recorder is not None
            assert self._mapping_recorder.latest_summary_path is not None
            return self._mapping_recorder.latest_summary_path

        output_dir = Path(self.hass.config.path("larnitech_mapping"))
        recorder = MappingRecorder(
            self.hass,
            output_dir,
            group_window_seconds=group_window_seconds,
        )
        self._mapping_recorder = recorder
        try:
            path = await recorder.async_start(
                self.devices,
                initial_values=self.status_by_addr,
            )
        except Exception:
            self._mapping_recorder = None
            raise

        self._mapping_timeout_task = asyncio.create_task(self._async_mapping_timeout())
        _LOGGER.warning(
            "Larnitech mapping session %s started; summary: %s; auto-stop: %s minutes",
            recorder.session_id,
            path,
            MAPPING_MAX_DURATION_SECONDS // 60,
        )
        return path

    async def async_stop_mapping(self) -> Path | None:
        recorder = self._mapping_recorder
        if recorder is None:
            return None

        # Stop accepting new status events before draining the recorder queue.
        self._mapping_recorder = None
        timeout_task = self._mapping_timeout_task
        self._mapping_timeout_task = None
        if timeout_task is not None and timeout_task is not asyncio.current_task():
            timeout_task.cancel()
            with suppress(asyncio.CancelledError):
                await timeout_task

        path = await recorder.async_stop()
        _LOGGER.warning("Larnitech mapping session stopped; summary: %s", path)
        return path

    async def _async_mapping_timeout(self) -> None:
        try:
            await asyncio.sleep(MAPPING_MAX_DURATION_SECONDS)
            if self.mapping_active:
                path = await self.async_stop_mapping()
                _LOGGER.warning(
                    "Larnitech mapping session stopped automatically after %s minutes; summary: %s",
                    MAPPING_MAX_DURATION_SECONDS // 60,
                    path,
                )
        except asyncio.CancelledError:
            raise

    @callback
    def async_add_listener(self, addr: str, listener: Listener) -> Callable[[], None]:
        listeners = self._listeners.setdefault(addr, set())
        listeners.add(listener)

        @callback
        def remove() -> None:
            listeners.discard(listener)

        return remove

    @callback
    def async_add_availability_listener(
        self,
        listener: AvailabilityListener,
    ) -> Callable[[], None]:
        self._availability_listeners.add(listener)

        @callback
        def remove() -> None:
            self._availability_listeners.discard(listener)

        return remove

    def _with_area_overrides(self, devices: list[LarnitechDevice]) -> list[LarnitechDevice]:
        if not self.area_overrides:
            return devices

        enriched: list[LarnitechDevice] = []
        for device in devices:
            area = self.area_overrides.get(device.addr)
            enriched.append(replace(device, area=area) if area else device)
        return enriched

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
        reconnect_delay = RECONNECT_DELAY_SECONDS
        while not self._closed:
            next_refresh = asyncio.get_running_loop().time() + STATUS_REFRESH_INTERVAL_SECONDS
            try:
                while not self._closed:
                    timeout = max(0, next_refresh - asyncio.get_running_loop().time())
                    try:
                        message = await asyncio.wait_for(
                            self._status_api.receive_message(),
                            timeout=timeout,
                        )
                    except TimeoutError:
                        self._refresh_statuses(await self._status_api.get_devices())
                        next_refresh = (
                            asyncio.get_running_loop().time() + STATUS_REFRESH_INTERVAL_SECONDS
                        )
                        continue

                    for status in self._status_api.extract_status_events(message):
                        self._handle_status(status)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if self._closed:
                    return
                self._set_available(False)
                _LOGGER.warning(
                    "Larnitech status stream disconnected: %s; reconnecting",
                    exc,
                )

            await self._status_api.close()

            while not self._closed:
                try:
                    await asyncio.sleep(reconnect_delay)
                    await self._status_api.connect()
                    self._refresh_statuses(await self._status_api.get_devices())
                    await self._status_api.subscribe_status()
                    reconnect_delay = RECONNECT_DELAY_SECONDS
                    self._set_available(True)
                    _LOGGER.info("Larnitech status stream reconnected and state refreshed")
                    break
                except asyncio.CancelledError:
                    raise
                except Exception:
                    if self._closed:
                        return
                    _LOGGER.exception(
                        "Failed to reconnect Larnitech status stream; retrying in %s seconds",
                        reconnect_delay,
                    )
                    await self._status_api.close()
                    reconnect_delay = min(
                        reconnect_delay * 2,
                        RECONNECT_MAX_DELAY_SECONDS,
                    )

    def _refresh_statuses(self, devices: list[LarnitechDevice]) -> None:
        for device in devices:
            if "status" in device.raw:
                self._handle_status(
                    DeviceStatus(
                        addr=device.addr,
                        value=device.raw["status"],
                        raw=device.raw,
                    )
                )

    @callback
    def _set_available(self, available: bool) -> None:
        if self._available == available:
            return
        if available:
            if self._ever_connected:
                self.reconnect_count += 1
            self._ever_connected = True
        elif self._ever_connected and not self._closed:
            self.last_disconnect = datetime.now(UTC)
        self._available = available
        for listener in list(self._availability_listeners):
            listener(available)
        for addr, listeners in self._listeners.items():
            status = DeviceStatus(
                addr=addr,
                value=self.status_by_addr.get(addr),
                raw={},
            )
            for listener in list(listeners):
                listener(status)

    @callback
    def _handle_status(self, status: DeviceStatus) -> None:
        self.status_by_addr[status.addr] = status.value
        if self._mapping_recorder is not None:
            self._mapping_recorder.enqueue(status)
        for listener in list(self._listeners.get(status.addr, set())):
            listener(status)
