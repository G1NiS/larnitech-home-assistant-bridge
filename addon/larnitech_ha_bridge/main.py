from __future__ import annotations

import asyncio
import logging
import signal

from .commands import CommandKind, larnitech_status_for_command
from .config import load_config
from .larnitech_api import LarnitechApiClient
from .models import LarnitechDevice
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
    pending_commands: asyncio.Queue[tuple[str, str, CommandKind]] = asyncio.Queue()
    devices_by_addr: dict[str, LarnitechDevice] = {}

    loop = asyncio.get_running_loop()

    def on_mqtt_command(addr: str, payload: str, kind: CommandKind) -> None:
        # Paho MQTT callbacks run in a separate thread. Use thread-safe queue handoff.
        loop.call_soon_threadsafe(pending_commands.put_nowait, (addr, payload, kind))

    mqtt_client = MqttBridgeClient(config, on_mqtt_command)
    mqtt_client.connect()

    status_api = LarnitechApiClient(config.larnitech_ws_url, config.larnitech_api_key, name="status")
    command_api = LarnitechApiClient(config.larnitech_ws_url, config.larnitech_api_key, name="command")

    async def command_worker() -> None:
        await command_api.connect()
        while True:
            addr, payload, kind = await pending_commands.get()
            device = devices_by_addr.get(addr)
            try:
                status_payload = larnitech_status_for_command(device, payload, kind)
                response = await command_api.set_status(addr, status_payload)
                logger.info("Command completed: addr=%s kind=%s payload=%s response=%s", addr, kind, payload, response)
            except Exception:
                logger.exception("Failed to set Larnitech status: addr=%s kind=%s payload=%s", addr, kind, payload)
            finally:
                pending_commands.task_done()

    async def larnitech_worker() -> None:
        await status_api.connect()
        devices = await status_api.get_devices()

        filtered_devices = [
            device
            for device in devices
            if device.type not in config.ignored_types
            and (device.area or "") not in config.ignored_areas
        ]

        devices_by_addr.clear()
        devices_by_addr.update({device.addr: device for device in filtered_devices})

        published_devices = mqtt_client.publish_discovery(filtered_devices)
        mqtt_client.publish_initial_status(published_devices)
        await status_api.subscribe_status()

        async for status in status_api.status_events():
            mqtt_client.publish_status(status)

    stop_event = asyncio.Event()

    def stop() -> None:
        stop_event.set()

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

    await status_api.close()
    await command_api.close()
    mqtt_client.close()


def main() -> None:
    asyncio.run(run_bridge())


if __name__ == "__main__":
    main()
