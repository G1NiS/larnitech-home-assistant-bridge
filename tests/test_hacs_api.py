from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = ROOT / "custom_components" / "larnitech"
PACKAGE_NAME = "test_larnitech_hacs_api"

package = types.ModuleType(PACKAGE_NAME)
package.__path__ = [str(PACKAGE_ROOT)]
sys.modules.setdefault(PACKAGE_NAME, package)


def _load_module(name: str):
    qualified_name = f"{PACKAGE_NAME}.{name}"
    existing = sys.modules.get(qualified_name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(qualified_name, PACKAGE_ROOT / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[qualified_name] = module
    spec.loader.exec_module(module)
    return module


_load_module("models")
api = _load_module("api")
LarnitechApiClient = api.LarnitechApiClient


class FakeWebSocket:
    def __init__(self) -> None:
        self.incoming: asyncio.Queue[dict | BaseException] = asyncio.Queue()
        self.sent: list[dict] = []
        self.closed = False
        self.active_receivers = 0
        self.max_active_receivers = 0

    async def send(self, raw_message: str) -> None:
        message = json.loads(raw_message)
        self.sent.append(message)
        request_type = message["request"]

        if request_type == "authorize":
            self.incoming.put_nowait({"response": "authorize", "result": "success"})
        elif request_type == "get-devices":
            self.incoming.put_nowait(
                {
                    "response": "get-devices",
                    "devices": [
                        {
                            "addr": "1:2",
                            "name": "Test light",
                            "type": "lamp",
                            "area": "Test",
                            "status": {"state": "off"},
                        }
                    ],
                }
            )
        elif request_type == "status-subscribe":
            self.incoming.put_nowait({"response": "status-subscribe", "result": "success"})
        elif request_type == "status-set":
            self.incoming.put_nowait(
                {
                    "event": "statuses",
                    "devices": [
                        {
                            "addr": message["addr"],
                            "status": message["status"],
                        }
                    ],
                }
            )
            self.incoming.put_nowait(
                {
                    "response": "status-set",
                    "devices": [{"addr": message["addr"], "success": True}],
                }
            )

    async def recv(self) -> str:
        self.active_receivers += 1
        self.max_active_receivers = max(
            self.max_active_receivers,
            self.active_receivers,
        )
        try:
            item = await self.incoming.get()
        finally:
            self.active_receivers -= 1
        if isinstance(item, BaseException):
            raise item
        return json.dumps(item)

    async def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_one_websocket_handles_requests_and_status_events(monkeypatch) -> None:
    websocket = FakeWebSocket()
    connect_kwargs = None
    connect_calls = 0

    async def fake_connect(_url: str, **kwargs):
        nonlocal connect_calls, connect_kwargs
        connect_calls += 1
        connect_kwargs = kwargs
        return websocket

    monkeypatch.setattr(api.websockets, "connect", fake_connect)
    client = LarnitechApiClient("controller", 2041, "secret")

    await client.connect()
    devices = await client.get_devices()
    await client.subscribe_status()
    stream = client.raw_messages()
    response = await client.set_status("1:2", {"state": "on"})
    event = await asyncio.wait_for(stream.__anext__(), timeout=1)
    await client.close()

    assert connect_calls == 1
    assert connect_kwargs["ping_interval"] is None
    assert "ping_timeout" not in connect_kwargs
    assert websocket.max_active_receivers == 1
    assert devices[0].addr == "1:2"
    assert response["response"] == "status-set"
    assert event["event"] == "statuses"
    assert websocket.closed is True


@pytest.mark.asyncio
async def test_connection_error_reaches_status_stream(monkeypatch) -> None:
    websocket = FakeWebSocket()

    async def fake_connect(_url: str, **_kwargs):
        return websocket

    monkeypatch.setattr(api.websockets, "connect", fake_connect)
    client = LarnitechApiClient("controller", 2041, "secret")
    await client.connect()
    await client.subscribe_status()

    websocket.incoming.put_nowait(ConnectionError("socket lost"))
    with pytest.raises(ConnectionError, match="socket lost"):
        await asyncio.wait_for(client.raw_messages().__anext__(), timeout=1)

    assert client.connected is False
    await client.close()


@pytest.mark.asyncio
async def test_cancelled_status_wait_does_not_close_message_stream(monkeypatch) -> None:
    websocket = FakeWebSocket()

    async def fake_connect(_url: str, **_kwargs):
        return websocket

    monkeypatch.setattr(api.websockets, "connect", fake_connect)
    client = LarnitechApiClient("controller", 2041, "secret")
    await client.connect()
    await client.subscribe_status()

    with pytest.raises(TimeoutError):
        await asyncio.wait_for(client.receive_message(), timeout=0.01)

    websocket.incoming.put_nowait(
        {
            "event": "statuses",
            "devices": [{"addr": "1:2", "status": {"state": "on"}}],
        }
    )
    event = await asyncio.wait_for(client.receive_message(), timeout=1)

    assert event["event"] == "statuses"
    await client.close()
