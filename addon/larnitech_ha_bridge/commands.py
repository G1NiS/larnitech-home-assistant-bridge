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

    API2 accepts object status payloads such as {"state": "off"} for simple on/off
    items. Fancoil speed is sent as a structured manual fan value because the tablet
    exposes manual speed control as 0..100 percent fan status.
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
        if command_kind == "state":
            return _fancoil_state_status(payload)
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


def _hex_bytes(*values: int) -> str:
    return "0x" + "".join(f"{max(0, min(255, int(value))):02X}" for value in values)


def _percent_to_larnitech_power(percent: float) -> int:
    # Larnitech fancoil fan power byte is 0..250.
    return max(0, min(250, int(round(clamp_level(percent) * 2.5))))


def _fancoil_state_status(payload: str) -> dict[str, str]:
    return {"state": "on" if parse_bool_payload(payload) else "off"}


def _fancoil_mode_status(payload: str) -> dict[str, str]:
    # Backward compatibility for stale climate cards/topics. New discovery publishes
    # fancoils as fan entities, not climate entities.
    mode = payload.strip().lower()
    if mode == "off":
        return {"state": "off"}
    if mode in {"cool", "heat", "on"}:
        return {"state": "on", "mode": mode if mode in {"cool", "heat"} else "heat"}
    raise ValueError(f"Unsupported fancoil HVAC mode: {payload!r}")


def _fancoil_fan_status(payload: str) -> dict[str, float | str]:
    value = payload.strip().lower()

    # Tablet manual fancoil control exposes speeds as fan percentages, not raw power bytes.
    speed_percent = {
        "off": 0,
        "0": 0,
        "low": 33,
        "1": 33,
        "medium": 66,
        "med": 66,
        "2": 66,
        "high": 100,
        "max": 100,
        "3": 100,
    }

    if value in speed_percent:
        fan = speed_percent[value]
    else:
        try:
            fan = clamp_level(float(value))
        except ValueError as exc:
            raise ValueError(f"Unsupported fancoil fan mode: {payload!r}") from exc

    if fan <= 0:
        return {"state": "off", "fan": 0.0}

    return {"state": "on", "fan": float(fan)}


def _fancoil_preset_status(payload: str) -> dict[str, str] | dict[str, float | str] | str:
    preset = payload.strip()
    if not preset:
        raise ValueError("Empty fancoil preset payload")

    # New fan entity preset modes are the speed names. Keep this here so stale
    # subscriptions or older retained discovery payloads still control fan speed.
    if preset.lower() in {"off", "0", "low", "1", "medium", "med", "2", "high", "max", "3"}:
        return _fancoil_fan_status(preset)

    if preset.lower() == "none":
        return {"state": "on"}

    # API2 returns automation names for some fancoils, and accepts this payload shape.
    # Keep this for legacy profile commands, but new fan discovery does not expose them.
    return {"state": "on", "automation": preset}
