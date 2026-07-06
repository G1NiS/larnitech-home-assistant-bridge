from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import websockets

from .models import DeviceStatus, LarnitechDevice

_LOGGER = logging.getLogger(__name__)


class LarnitechApiClient:
    def __init__(self, ws_url: str, api_key: str) -> None:
        self.ws_url = ws_url
        self.api_key = api_key
        self._ws: Any | None = None
        self._request_id = 0

    async def connect(self) -> None:
        _LOGGER.info("Connecting to Larnitech API2 at %s", self.ws_url)
        self._ws = await websockets.connect(self.ws_url, ping_interval=30, ping_timeout=10)
        _LOGGER.info("Connected to Larnitech API2")

    async def close(self) -> None:
        if self._ws is not None:
            await self._ws.close()
            self._ws = None

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    async def request(self, request_type: str, **payload: Any) -> dict[str, Any]:
        if self._ws is None:
            raise RuntimeError("Larnitech WebSocket is not connected")

        message = {
            "request": request_type,
            "key": self.api_key,
            "id": self._next_id(),
            **payload,
        }
        _LOGGER.debug("Larnitech request: %s", sanitize_secret(message))
        await self._ws.send(json.dumps(message))

        raw_response = await self._ws.recv()
        response = json.loads(raw_response)
        _LOGGER.debug("Larnitech response: %s", response)
        return response

    async def get_devices(self) -> list[LarnitechDevice]:
        response = await self.request("get-devices")
        raw_devices = (
            response.get("devices")
            or response.get("data")
            or response.get("result")
            or []
        )

        if isinstance(raw_devices, dict):
            raw_devices = list(raw_devices.values())

        devices = [LarnitechDevice.from_raw(item) for item in raw_devices if isinstance(item, dict)]
        _LOGGER.info("Discovered %s Larnitech devices", len(devices))
        for device in devices:
            _LOGGER.debug(
                "Device: addr=%s name=%s type=%s area=%s raw=%s",
                device.addr,
                device.name,
                device.type,
                device.area,
                device.raw,
            )
        return devices

    async def set_status(self, addr: str, status: Any) -> dict[str, Any]:
        return await self.request("status-set", addr=addr, status=status)

    async def subscribe_status(self) -> None:
        await self.request("status-subscribe")

    async def status_events(self) -> AsyncIterator[DeviceStatus]:
        if self._ws is None:
            raise RuntimeError("Larnitech WebSocket is not connected")

        while True:
            raw_message = await self._ws.recv()
            try:
                data = json.loads(raw_message)
            except json.JSONDecodeError:
                _LOGGER.warning("Invalid JSON from Larnitech: %s", raw_message)
                continue

            addr = data.get("addr") or data.get("device") or data.get("id")
            if not addr:
                _LOGGER.debug("Ignoring non-status Larnitech message: %s", data)
                continue

            value = data.get("status", data.get("value"))
            yield DeviceStatus(addr=str(addr), value=value, raw=data)


def sanitize_secret(data: dict[str, Any]) -> dict[str, Any]:
    clean = dict(data)
    if "key" in clean:
        clean["key"] = "***"
    return clean
