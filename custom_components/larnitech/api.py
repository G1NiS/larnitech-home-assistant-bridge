from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from contextlib import suppress
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
    def __init__(self, host: str, port: int, api_key: str, name: str = "api") -> None:
        self.host = host
        self.port = port
        self.api_key = api_key
        self.name = name
        self.ws_url = f"ws://{host}:{port}/api"
        self._ws: Any | None = None
        self._request_id = 0
        self._authorized = False
        self._request_lock = asyncio.Lock()
        self._pending_response: asyncio.Future[dict[str, Any]] | None = None
        self._pending_request_type: str | None = None
        self._message_queue: asyncio.Queue[dict[str, Any] | BaseException] = asyncio.Queue()
        self._receiver_task: asyncio.Task[None] | None = None

    @property
    def connected(self) -> bool:
        return (
            self._ws is not None
            and self._authorized
            and self._receiver_task is not None
            and not self._receiver_task.done()
        )

    async def connect(self) -> None:
        _LOGGER.debug("[%s] Connecting to Larnitech API2 at %s", self.name, self.ws_url)
        ws = await websockets.connect(
            self.ws_url,
            ping_interval=None,
            open_timeout=WEBSOCKET_OPEN_TIMEOUT,
            close_timeout=WEBSOCKET_CLOSE_TIMEOUT,
        )
        self._ws = ws
        self._authorized = False
        self._message_queue = asyncio.Queue()
        self._receiver_task = asyncio.create_task(self._receive_loop(ws, self._message_queue))
        try:
            await self.authorize()
        except BaseException:
            await self.close()
            raise

    async def authorize(self) -> None:
        await self._request("authorize", require_authorized=False, key=self.api_key)
        self._authorized = True

    async def close(self) -> None:
        ws = self._ws
        receiver_task = self._receiver_task
        self._ws = None
        self._receiver_task = None
        self._authorized = False

        pending = self._pending_response
        self._pending_response = None
        self._pending_request_type = None
        if pending is not None and not pending.done():
            pending.set_exception(RuntimeError("Larnitech WebSocket is closed"))

        if receiver_task is not None and receiver_task is not asyncio.current_task():
            receiver_task.cancel()
            with suppress(asyncio.CancelledError):
                await receiver_task

        if ws is None:
            return
        try:
            await asyncio.wait_for(ws.close(), timeout=WEBSOCKET_CLOSE_TIMEOUT + 1)
        except Exception as exc:
            _LOGGER.debug("[%s] Ignoring WebSocket close error: %s", self.name, exc)

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    async def request(self, request_type: str, **payload: Any) -> dict[str, Any]:
        return await self._request(request_type, require_authorized=True, **payload)

    async def _request(
        self,
        request_type: str,
        *,
        require_authorized: bool,
        **payload: Any,
    ) -> dict[str, Any]:
        if self._ws is None:
            raise RuntimeError("Larnitech WebSocket is not connected")
        if require_authorized and not self._authorized:
            raise RuntimeError("Larnitech API2 is not authorized")

        async with self._request_lock:
            ws = self._ws
            if ws is None:
                raise RuntimeError("Larnitech WebSocket is not connected")

            response_future = asyncio.get_running_loop().create_future()
            self._pending_response = response_future
            self._pending_request_type = request_type
            message = {"request": request_type, "id": self._next_id(), **payload}
            try:
                await ws.send(json.dumps(message))
                response = await asyncio.wait_for(
                    asyncio.shield(response_future),
                    timeout=REQUEST_TIMEOUT,
                )
            finally:
                if self._pending_response is response_future:
                    self._pending_response = None
                    self._pending_request_type = None

        self._raise_if_error(response, request_type)
        return response

    async def _receive_loop(
        self,
        ws: Any,
        message_queue: asyncio.Queue[dict[str, Any] | BaseException],
    ) -> None:
        try:
            while True:
                raw_message = await ws.recv()
                try:
                    data = json.loads(raw_message)
                except json.JSONDecodeError:
                    _LOGGER.warning("[%s] Invalid JSON from Larnitech: %s", self.name, raw_message)
                    continue

                pending = self._pending_response
                request_type = self._pending_request_type
                response_type = data.get("response")
                is_event = data.get("event") is not None
                is_expected_response = (
                    pending is not None
                    and not pending.done()
                    and not is_event
                    and (response_type is None or response_type == request_type)
                )
                if is_expected_response:
                    pending.set_result(data)
                elif response_type is None:
                    message_queue.put_nowait(data)
                else:
                    _LOGGER.debug(
                        "[%s] Ignoring unsolicited %s response",
                        self.name,
                        response_type,
                    )
        except asyncio.CancelledError:
            raise
        except BaseException as exc:
            if self._ws is ws:
                self._ws = None
                self._authorized = False
            pending = self._pending_response
            if pending is not None and not pending.done():
                pending.set_exception(exc)
            message_queue.put_nowait(exc)

    async def get_devices(self) -> list[LarnitechDevice]:
        response = await self.request("get-devices", status="detailed")
        return self.devices_from_response(response)

    @staticmethod
    def devices_from_response(response: dict[str, Any]) -> list[LarnitechDevice]:
        raw_devices = (
            response.get("devices") or response.get("data") or response.get("result") or []
        )
        if isinstance(raw_devices, dict):
            raw_devices = list(raw_devices.values())
        return [LarnitechDevice.from_raw(item) for item in raw_devices if isinstance(item, dict)]

    async def set_status(self, addr: str, status: Any) -> dict[str, Any]:
        return await self.request("status-set", addr=addr, status=status)

    async def subscribe_status(self) -> None:
        try:
            await self.request("status-subscribe")
        except LarnitechApiError as exc:
            _LOGGER.warning("[%s] Status subscription failed: %s", self.name, exc)

    async def receive_message(self) -> dict[str, Any]:
        if self._receiver_task is None:
            raise RuntimeError("Larnitech WebSocket is not connected")

        message = await self._message_queue.get()
        if isinstance(message, BaseException):
            raise message
        return message

    async def raw_messages(self) -> AsyncIterator[dict[str, Any]]:
        while True:
            yield await self.receive_message()

    @classmethod
    def extract_status_events(cls, data: dict[str, Any]) -> list[DeviceStatus]:
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
        raise LarnitechApiError(f"{request_type} failed: code={code}, description={description}")
