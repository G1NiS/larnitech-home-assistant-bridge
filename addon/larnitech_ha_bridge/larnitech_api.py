from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import websockets

from .models import DeviceStatus, LarnitechDevice

_LOGGER = logging.getLogger(__name__)


class LarnitechApiError(RuntimeError):
    """Raised when Larnitech API2 returns an error response."""


class LarnitechApiClient:
    def __init__(self, ws_url: str, api_key: str) -> None:
        self.ws_url = ws_url
        self.api_key = api_key
        self._ws: Any | None = None
        self._request_id = 0
        self._authorized = False

    async def connect(self) -> None:
        _LOGGER.info("Connecting to Larnitech API2 at %s", self.ws_url)
        self._ws = await websockets.connect(self.ws_url, ping_interval=30, ping_timeout=10)
        _LOGGER.info("Connected to Larnitech API2 WebSocket")
        await self.authorize()

    async def authorize(self) -> None:
        if self._ws is None:
            raise RuntimeError("Larnitech WebSocket is not connected")

        # Larnitech API2 requires this separate authorization step first.
        # The API key is intentionally not included in later requests.
        message = {
            "request": "authorize",
            "key": self.api_key,
        }
        _LOGGER.debug("Larnitech request: {'request': 'authorize', 'key': '***'}")
        await self._ws.send(json.dumps(message))

        raw_response = await self._ws.recv()
        response = json.loads(raw_response)
        _LOGGER.debug("Larnitech authorize response: %s", response)

        self._raise_if_error(response, "authorize")
        self._authorized = True
        _LOGGER.info("Authorized with Larnitech API2")

    async def close(self) -> None:
        if self._ws is not None:
            await self._ws.close()
            self._ws = None
            self._authorized = False

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
        _LOGGER.debug("Larnitech request: %s", message)
        await self._ws.send(json.dumps(message))

        raw_response = await self._ws.recv()
        response = json.loads(raw_response)
        _LOGGER.debug("Larnitech response: %s", response)
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
        if isinstance(status, bool):
            status = {"state": "on" if status else "off"}
        return await self.request("status-set", addr=addr, status=status)

    async def subscribe_status(self, addr: str | None = None) -> None:
        payload = {"addr": addr} if addr else {}
        try:
            await self.request("status-subscribe", **payload)
            _LOGGER.info("Subscribed to Larnitech status updates")
        except LarnitechApiError as exc:
            # Some installations may require per-device subscriptions.
            # For MVP/debug mode, keep bridge running so discovery data remains visible.
            _LOGGER.warning("Status subscription failed: %s", exc)

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
