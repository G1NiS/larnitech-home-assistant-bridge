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
    """Convert a Home Assistant MQTT command payload to Larnitech API2 status-set.

    API2 accepts object status payloads such as {"state": "off"} for on/off
    and {"level": 10} for dimmers. It also supports raw hex strings for some
    item types, so buttons/scripts use 0xFF as a toggle/press style command.
    """

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
        if command_kind == "mode":
            return _fancoil_mode_status(payload)
        if command_kind == "fan_mode":
            return _fancoil_fan_status(payload)
        if command_kind == "preset":
            return _fancoil_preset_status(payload)

    is_on = parse_bool_payload(payload)

    controllable_types = {
        "lamp",
        "dimmer-lamp",
        "light",
        "switch",
        "valve",
        "valve-heating",
        "fancoil",
    }
    if device_type in controllable_types or device is None:
        return {"state": "on" if is_on else "off"}

    return {"state": "on" if is_on else "off"}


def _fancoil_mode_status(payload: str) -> dict[str, str]:
    mode = payload.strip().lower()
    if mode == "off":
        return {"state": "off"}
    if mode in {"heat", "cool"}:
        return {"state": "on", "mode": mode}
    raise ValueError(f"Unsupported fancoil HVAC mode: {payload!r}")


def _fancoil_fan_status(payload: str) -> dict[str, str | int]:
    value = payload.strip().lower()
    fan_levels = {
        "off": 0,
        "low": 25,
        "medium": 50,
        "high": 75,
        "max": 100,
    }

    if value in fan_levels:
        level = fan_levels[value]
    else:
        try:
            level = clamp_level(float(value))
        except ValueError as exc:
            raise ValueError(f"Unsupported fancoil fan mode: {payload!r}") from exc

    status: dict[str, str | int] = {"fan": level}
    if level <= 0:
        status["state"] = "off"
    else:
        status["state"] = "on"
    return status


def _fancoil_preset_status(payload: str) -> dict[str, str]:
    preset = payload.strip()
    if not preset:
        raise ValueError("Empty fancoil preset payload")
    if preset.lower() == "off":
        return {"state": "off", "automation": preset}
    return {"state": "on", "automation": preset}
