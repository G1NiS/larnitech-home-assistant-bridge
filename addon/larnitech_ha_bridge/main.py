from __future__ import annotations

import asyncio
import logging
import signal

from .config import load_config
from .larnitech_api import LarnitechApiClient
from .mqtt_client import MqttBridgeClient


def setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )

    # Keep third-party WebSocket frame logs quiet even when bridge debug logging is enabled.
    # Otherwise raw API payloads can expose private API keys in Home Assistant logs.
    logging.getLogger("websockets").setLevel(logging.INFO)
    logging.getLogger("websockets.client").setLevel(logging.INFO)


async def run_bridge() -> None:
    config = load_config()
    setup_logging(config.log_level)

    logger = logging.getLogger(__name__)
    pending_commands: asyncio.Queue[tuple[str, str]] = asyncio.Queue()

    def on_mqtt_command(addr: str, payload: str) -> None:
        pending_commands.put_nowait((addr, payload))

    mqtt_client = MqttBridgeClient(config, on_mqtt_command)
    mqtt_client.connect()

    api = LarnitechApiClient(config.larnitech_ws_url, config.larnitech_api_key)

    async def command_worker() -> None:
        while True:
            addr, payload = await pending_commands.get()
            status = payload in {"ON", "1", "true", "True"}
            try:
                await api.set_status(addr, status)
            except Exception:
                logger.exception("Failed to set Larnitech status: addr=%s payload=%s", addr, payload)

    async def larnitech_worker() -> None:
        await api.connect()
        devices = await api.get_devices()

        filtered_devices = [
            device
            for device in devices
            if device.type not in config.ignored_types
            and (device.area or "") not in config.ignored_areas
        ]

        mqtt_client.publish_discovery(filtered_devices)
        await api.subscribe_status()

        async for status in api.status_events():
            mqtt_client.publish_status(status)

    stop_event = asyncio.Event()

    def stop() -> None:
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop)

    workers = [
        asyncio.create_task(command_worker()),
        asyncio.create_task(larnitech_worker()),
    ]

    await stop_event.wait()
    logger.info("Stopping Larnitech HA Bridge")
    for task in workers:
        task.cancel()
    await api.close()
    mqtt_client.close()


def main() -> None:
    asyncio.run(run_bridge())


if __name__ == "__main__":
    main()
