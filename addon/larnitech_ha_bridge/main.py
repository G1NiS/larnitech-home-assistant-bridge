from __future__ import annotations

import asyncio
import json
import logging
import signal
from datetime import datetime
from pathlib import Path
from typing import Any

from .commands import CommandKind, larnitech_status_for_command
from .config import load_config
from .larnitech_api import LarnitechApiClient, LarnitechApiError
from .models import LarnitechDevice
from .mqtt_client import MqttBridgeClient

RECONNECT_DELAY_INITIAL = 5
RECONNECT_DELAY_MAX = 60
FULL_API_DUMP_DIR = Path("/data/full_api_dump")


def setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )

    # Keep third-party WebSocket frame logs quiet even when bridge debug logging is enabled.
    # Otherwise raw API payloads can expose private API keys in Home Assistant logs.
    logging.getLogger("websockets").setLevel(logging.INFO)
    logging.getLogger("websockets.client").setLevel(logging.INFO)


def json_dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def make_dump_paths() -> tuple[Path, Path]:
    FULL_API_DUMP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return (
        FULL_API_DUMP_DIR / f"devices_full_{stamp}.json",
        FULL_API_DUMP_DIR / f"status_stream_{stamp}.jsonl",
    )


async def run_bridge() -> None:
    config = load_config()
    setup_logging(config.log_level)

    logger = logging.getLogger(__name__)
    pending_commands: asyncio.Queue[tuple[str, str, CommandKind]] = asyncio.Queue()
    devices_by_addr: dict[str, LarnitechDevice] = {}
    latest_status_by_addr: dict[str, object] = {}
    dump_devices_path: Path | None = None
    dump_stream_path: Path | None = None

    if config.full_api_dump:
        dump_devices_path, dump_stream_path = make_dump_paths()
        logger.warning(
            "[full-api-dump] enabled. Dumping full get-devices response and every raw "
            "status-subscribe message without filtering. Files: devices=%s stream=%s",
            dump_devices_path,
            dump_stream_path,
        )

    loop = asyncio.get_running_loop()

    def on_mqtt_command(addr: str, payload: str, kind: CommandKind) -> None:
        # Paho MQTT callbacks run in a separate thread. Use thread-safe queue handoff.
        loop.call_soon_threadsafe(pending_commands.put_nowait, (addr, payload, kind))

    def is_debug_fancoil(addr: str) -> bool:
        device = devices_by_addr.get(addr)
        return bool(config.fancoil_debug and device and device.type == "fancoil")

    def write_full_api_dump(kind: str, payload: Any) -> None:
        if not config.full_api_dump or dump_stream_path is None:
            return
        record = {
            "ts": datetime.now().isoformat(timespec="milliseconds"),
            "kind": kind,
            "payload": payload,
        }
        line = json_dumps(record)
        with dump_stream_path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
        logger.info("[full-api-dump] %s %s", kind, line)

    mqtt_client = MqttBridgeClient(config, on_mqtt_command)
    mqtt_client.connect()

    status_api = LarnitechApiClient(config.larnitech_ws_url, config.larnitech_api_key, name="status")
    command_api = LarnitechApiClient(config.larnitech_ws_url, config.larnitech_api_key, name="command")

    async def command_worker() -> None:
        delay = RECONNECT_DELAY_INITIAL
        while True:
            try:
                await command_api.connect()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception(
                    "Failed to connect Larnitech command WebSocket, retrying in %s s", delay
                )
                await command_api.close()
                await asyncio.sleep(delay)
                delay = min(delay * 2, RECONNECT_DELAY_MAX)
                continue

            delay = RECONNECT_DELAY_INITIAL
            try:
                while True:
                    addr, payload, kind = await pending_commands.get()
                    device = devices_by_addr.get(addr)
                    debug_fancoil = is_debug_fancoil(addr)
                    requeue = None
                    try:
                        if debug_fancoil:
                            logger.info(
                                "[fancoil-debug] before command: addr=%s kind=%s "
                                "payload=%s latest_status=%s device_raw=%s",
                                addr,
                                kind,
                                payload,
                                latest_status_by_addr.get(addr),
                                device.raw if device else None,
                            )

                        status_payload = larnitech_status_for_command(device, payload, kind)

                        if debug_fancoil:
                            logger.info(
                                "[fancoil-debug] mapped command: addr=%s kind=%s "
                                "payload=%s status_payload=%s",
                                addr,
                                kind,
                                payload,
                                status_payload,
                            )

                        if config.full_api_dump:
                            write_full_api_dump(
                                "ha_command",
                                {
                                    "addr": addr,
                                    "kind": kind,
                                    "mqtt_payload": payload,
                                    "status_payload": status_payload,
                                    "latest_status": latest_status_by_addr.get(addr),
                                    "device_raw": device.raw if device else None,
                                },
                            )

                        response = await command_api.set_status(addr, status_payload)
                        if config.full_api_dump:
                            write_full_api_dump("ha_command_response", response)
                        logger.info(
                            "Command completed: addr=%s kind=%s payload=%s response=%s",
                            addr,
                            kind,
                            payload,
                            response,
                        )

                        if debug_fancoil:
                            await asyncio.sleep(1.5)
                            logger.info(
                                "[fancoil-debug] after command: addr=%s latest_status=%s",
                                addr,
                                latest_status_by_addr.get(addr),
                            )
                    except (LarnitechApiError, ValueError):
                        logger.exception(
                            "Failed to set Larnitech status: addr=%s kind=%s payload=%s",
                            addr,
                            kind,
                            payload,
                        )
                    except Exception:
                        # Connection-level failure - the command never reached Larnitech, so put
                        # it back on the queue to retry once the connection is re-established.
                        requeue = (addr, payload, kind)
                        raise
                    finally:
                        pending_commands.task_done()
                        if requeue is not None:
                            pending_commands.put_nowait(requeue)
            except asyncio.CancelledError:
                raise
            except Exception:
                # Connection-level failure (dropped socket, timed-out response, etc.). Reconnect
                # immediately without backoff - the delay only grows if the reconnect itself fails.
                logger.exception("Larnitech command connection lost, reconnecting")
                await command_api.close()

    async def larnitech_worker() -> None:
        delay = RECONNECT_DELAY_INITIAL
        while True:
            try:
                await status_api.connect()
                devices_response = await status_api.get_devices_response()
                devices = status_api.devices_from_response(devices_response)
                logger.info("[status] Discovered %s Larnitech devices", len(devices))
                for device in devices:
                    logger.debug(
                        "[status] Device: addr=%s name=%s type=%s area=%s raw=%s",
                        device.addr,
                        device.name,
                        device.type,
                        device.area,
                        device.raw,
                    )
                if config.full_api_dump:
                    write_full_api_dump("get_devices_response", devices_response)
                    if dump_devices_path is not None:
                        dump_devices_path.write_text(
                            json.dumps(devices_response, ensure_ascii=False, indent=2, sort_keys=True),
                            encoding="utf-8",
                        )
                        logger.warning(
                            "[full-api-dump] wrote complete get-devices response to %s",
                            dump_devices_path,
                        )
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception(
                    "Failed to connect Larnitech status WebSocket, retrying in %s s", delay
                )
                await status_api.close()
                await asyncio.sleep(delay)
                delay = min(delay * 2, RECONNECT_DELAY_MAX)
                continue

            delay = RECONNECT_DELAY_INITIAL
            try:
                filtered_devices = [
                    device
                    for device in devices
                    if device.type not in config.ignored_types
                    and (device.area or "") not in config.ignored_areas
                ]

                devices_by_addr.clear()
                devices_by_addr.update({device.addr: device for device in filtered_devices})

                latest_status_by_addr.clear()
                latest_status_by_addr.update({device.addr: device.raw for device in filtered_devices})

                if config.fancoil_debug:
                    debug_fancoils = [
                        device.addr for device in filtered_devices if device.type == "fancoil"
                    ]
                    logger.info("[fancoil-debug] enabled for fancoils: %s", debug_fancoils)

                published_devices = mqtt_client.publish_discovery(filtered_devices)
                mqtt_client.publish_initial_status(published_devices)
                await status_api.subscribe_status()

                async for message in status_api.raw_messages():
                    if config.full_api_dump:
                        write_full_api_dump("status_message", message)
                    for status in status_api.extract_status_events(message):
                        latest_status_by_addr[status.addr] = status.raw
                        if is_debug_fancoil(status.addr):
                            logger.info(
                                "[fancoil-debug] native status update: addr=%s value=%s raw=%s",
                                status.addr,
                                status.value,
                                status.raw,
                            )
                        mqtt_client.publish_status(status)
            except asyncio.CancelledError:
                raise
            except Exception:
                # Connection-level failure. Reconnect immediately without backoff - the delay
                # only grows if the reconnect itself fails.
                logger.exception("Larnitech status connection lost, reconnecting")
                await status_api.close()

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
