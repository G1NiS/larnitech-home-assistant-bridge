from __future__ import annotations

from typing import Any, Literal

from .models import LarnitechDevice

CommandKind = Literal["state", "brightness", "press", "mode", "fan_mode", "preset"]


def parse_bool_payload(payload: str) -> bool:
    value = payload.strip().lower()
    if value in {"on", "1", "true", "yes", "open"}:
        return True
    if value in {"off", "0", "false", "no", "closed"}:
        return False
    raise ValueError(f"Unsupported boolean payload: {payload!r}")


def clamp_level(value: float) -> int:
    if value < 0:
        return 0
    if value > 100:
        return 100
    return int(round(value))


def larnitech_status_for_command(
    device: LarnitechDevice | None,
    payload: str,
    command_kind: CommandKind,
) -> Any:
    """Convert a Home Assistant MQTT command payload to Larnitech API2 status-set."""

    device_type = device.type if device else None

    if command_kind == "brightness":
        try:
            return {"level": clamp_level(float(payload))}
        except ValueError as exc:
            raise ValueError(f"Invalid brightness payload: {payload!r}") from exc

    if command_kind == "press":
        # Larnitech lamp docs list 0xFF as "change status to opposite".
        # This is also the safest generic push-style command for scripts/light schemes.
        return "0xFF"

    if device_type == "fancoil":
        return _fancoil_on_off_status(payload, command_kind)

    is_on = parse_bool_payload(payload)

    controllable_types = {
        "lamp",
        "dimmer-lamp",
        "light",
        "switch",
        "valve",
        "valve-heating",
    }
    if device_type in controllable_types or device is None:
        return {"state": "on" if is_on else "off"}

    return {"state": "on" if is_on else "off"}


def _fancoil_on_off_status(payload: str, command_kind: CommandKind) -> dict[str, str]:
    """Fancoils are controlled as ON/OFF only.

    Speed and heat/cool writes were intentionally removed because this installation's
    Larnitech API2 accepts those commands but immediately restores the native runtime
    state. For stale retained MQTT topics, any non-zero/non-off command is treated as ON.
    """

    value = payload.strip().lower()

    if command_kind in {"fan_mode", "preset"}:
        is_on = value not in {"off", "0", "false", "no", "closed"}
        return {"state": "on" if is_on else "off"}

    if command_kind == "mode":
        return {"state": "off" if value == "off" else "on"}

    return {"state": "on" if parse_bool_payload(payload) else "off"}
