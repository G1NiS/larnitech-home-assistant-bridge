from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import websockets

from .models import DeviceStatus, LarnitechDevice

_LOGGER = logging.getLogger(__name__)

REQUEST_TIMEOUT = 10
WEBSOCKET_OPEN_TIMEOUT = 10
WEBSOCKET_CLOSE_TIMEOUT = 2


class LarnitechApiError(RuntimeError):
    """Raised when Larnitech API2 returns an error response."""


class LarnitechApiClient:
    def __init__(self, ws_url: str, api_key: str, name: str = "api") -> None:
        self.ws_url = ws_url
        self.api_key = api_key
        self.name = name
        self._ws: Any | None = None
        self._request_id = 0
        self._authorized = False

    async def connect(self) -> None:
        _LOGGER.info("[%s] Connecting to Larnitech API2 at %s", self.name, self.ws_url)
        self._ws = await websockets.connect(
            self.ws_url,
            # Larnitech API2 closes some clients because it does not consistently answer
            # Python websockets protocol pings. Disable client-side protocol keepalive and
            # let the bridge reconnect only on real socket/request failures.
            ping_interval=None,
            open_timeout=WEBSOCKET_OPEN_TIMEOUT,
            close_timeout=WEBSOCKET_CLOSE_TIMEOUT,
        )
        _LOGGER.info("[%s] Connected to Larnitech API2 WebSocket", self.name)
        await self.authorize()

    async def authorize(self) -> None:
        if self._ws is None:
            raise RuntimeError("Larnitech WebSocket is not connected")

        message = {
            "request": "authorize",
            "key": self.api_key,
        }
        _LOGGER.debug("[%s] Larnitech request: {'request': 'authorize', 'key': '***'}", self.name)
        await self._ws.send(json.dumps(message))

        raw_response = await asyncio.wait_for(self._ws.recv(), timeout=REQUEST_TIMEOUT)
        response = json.loads(raw_response)
        _LOGGER.debug("[%s] Larnitech authorize response: %s", self.name, response)

        self._raise_if_error(response, "authorize")
        self._authorized = True
        _LOGGER.info("[%s] Authorized with Larnitech API2", self.name)

    async def close(self) -> None:
        ws = self._ws
        self._ws = None
        self._authorized = False

        if ws is None:
            return

        try:
            await asyncio.wait_for(ws.close(), timeout=WEBSOCKET_CLOSE_TIMEOUT + 1)
        except Exception as exc:
            # Connection is already broken. Do not block reconnect loops on graceful close.
            _LOGGER.debug("[%s] Ignoring WebSocket close error: %s", self.name, exc)

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    async def request(self, request_type: str, **payload: Any) -> dict[str, Any]:
        if self._ws is None:
            raise RuntimeError("Larnitech WebSocket is not connected")
        if not self._authorized:
            raise RuntimeError("Larnitech API2 is not authorized")

        message = {
            "request": request_type,
            "id": self._next_id(),
            **payload,
        }
        _LOGGER.debug("[%s] Larnitech request: %s", self.name, message)
        await self._ws.send(json.dumps(message))

        raw_response = await asyncio.wait_for(self._ws.recv(), timeout=REQUEST_TIMEOUT)
        response = json.loads(raw_response)
        _LOGGER.debug("[%s] Larnitech response: %s", self.name, response)
        self._raise_if_error(response, request_type)
        return response

    async def get_devices(self) -> list[LarnitechDevice]:
        response = await self.request("get-devices", status="detailed")
        raw_devices = (
            response.get("devices")
            or response.get("data")
            or response.get("result")
            or []
        )

        if isinstance(raw_devices, dict):
            raw_devices = list(raw_devices.values())

        devices = [LarnitechDevice.from_raw(item) for item in raw_devices if isinstance(item, dict)]
        _LOGGER.info("[%s] Discovered %s Larnitech devices", self.name, len(devices))
        for device in devices:
            _LOGGER.debug(
                "[%s] Device: addr=%s name=%s type=%s area=%s raw=%s",
                self.name,
                device.addr,
                device.name,
                device.type,
                device.area,
                device.raw,
            )
        return devices

    async def set_status(self, addr: str, status: Any) -> dict[str, Any]:
        _LOGGER.info("[%s] Sending status-set: addr=%s status=%s", self.name, addr, status)
        return await self.request("status-set", addr=addr, status=status)

    async def subscribe_status(self, addr: str | None = None) -> None:
        payload = {"addr": addr} if addr else {}
        try:
            await self.request("status-subscribe", **payload)
            _LOGGER.info("[%s] Subscribed to Larnitech status updates", self.name)
        except LarnitechApiError as exc:
            _LOGGER.warning("[%s] Status subscription failed: %s", self.name, exc)

    async def status_events(self) -> AsyncIterator[DeviceStatus]:
        if self._ws is None:
            raise RuntimeError("Larnitech WebSocket is not connected")

        while True:
            raw_message = await self._ws.recv()
            try:
                data = json.loads(raw_message)
            except json.JSONDecodeError:
                _LOGGER.warning("[%s] Invalid JSON from Larnitech: %s", self.name, raw_message)
                continue

            for status in self._extract_status_events(data):
                yield status

    def _extract_status_events(self, data: dict[str, Any]) -> list[DeviceStatus]:
        events: list[DeviceStatus] = []

        if isinstance(data.get("devices"), list):
            for item in data["devices"]:
                if not isinstance(item, dict):
                    continue
                addr = item.get("addr")
                if not addr:
                    continue
                value = item.get("status", item.get("state", item.get("value")))
                events.append(DeviceStatus(addr=str(addr), value=value, raw=item))
            return events

        addr = data.get("addr") or data.get("device") or data.get("id")
        if addr:
            value = data.get("status", data.get("state", data.get("value")))
            events.append(DeviceStatus(addr=str(addr), value=value, raw=data))

        return events

    @staticmethod
    def _raise_if_error(response: dict[str, Any], request_type: str) -> None:
        error = response.get("error")
        if not error:
            return

        code = error.get("code") if isinstance(error, dict) else None
        description = error.get("description") if isinstance(error, dict) else str(error)
        raise LarnitechApiError(
            f"{request_type} failed: code={code}, description={description}"
        )
