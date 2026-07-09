from __future__ import annotations

from typing import Any, Literal

from .models import LarnitechDevice

CommandKind = Literal["state", "brightness", "press", "mode", "fan_mode", "preset"]


# Native Larnitech fancoil API2 status-subscribe reports manual fan levels as
# 0.0 / 33.2 / 66.4 / 100.0. The 33.2 and 66.4 values correspond to 83/250
# and 166/250 in the documented fancoil power scale.
FANCOIL_LEVEL_OFF = 0.0
FANCOIL_LEVEL_LOW = 33.2
FANCOIL_LEVEL_MEDIUM = 66.4
FANCOIL_LEVEL_HIGH = 100.0


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


def fancoil_native_level(percent: float) -> float:
    """Return the closest native Larnitech manual fancoil level."""
    if percent <= 0:
        return FANCOIL_LEVEL_OFF
    if percent <= 34:
        return FANCOIL_LEVEL_LOW
    if percent <= 67:
        return FANCOIL_LEVEL_MEDIUM
    return FANCOIL_LEVEL_HIGH


def larnitech_status_for_command(
    device: LarnitechDevice | None,
    payload: str,
    command_kind: CommandKind,
) -> Any:
    """Convert a Home Assistant MQTT command payload to Larnitech API2 status-set.

    API2 accepts object status payloads such as {"state": "off"} for simple on/off
    items. For fancoils, use the native manual fan levels observed from API2
    status-subscribe when speeds are changed in the Larnitech UI.
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


def _fancoil_state_status(payload: str) -> dict[str, str]:
    # Keep fancoil on/off as a minimal payload. Native Larnitech UI also keeps the
    # last selected fan level when the fancoil is switched off.
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

    native_speed_percent = {
        "off": FANCOIL_LEVEL_OFF,
        "0": FANCOIL_LEVEL_OFF,
        "low": FANCOIL_LEVEL_LOW,
        "1": FANCOIL_LEVEL_LOW,
        "medium": FANCOIL_LEVEL_MEDIUM,
        "med": FANCOIL_LEVEL_MEDIUM,
        "2": FANCOIL_LEVEL_MEDIUM,
        "high": FANCOIL_LEVEL_HIGH,
        "max": FANCOIL_LEVEL_HIGH,
        "3": FANCOIL_LEVEL_HIGH,
    }

    if value in native_speed_percent:
        fan = native_speed_percent[value]
    else:
        try:
            fan = fancoil_native_level(float(value))
        except ValueError as exc:
            raise ValueError(f"Unsupported fancoil fan mode: {payload!r}") from exc

    if fan <= 0:
        # Native Larnitech UI can report state=on, fan=0.0, but Home Assistant fan
        # percentage 0 semantically means OFF. Keep it as state-only OFF so it does
        # not alter profile/automation fields.
        return {"state": "off"}

    return {"state": "on", "fan": fan}


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

    # API2 returns automation names for some fancoils. Avoid using them from the fan
    # entity by default; direct preset commands are left for legacy/manual testing.
    return {"state": "on", "automation": preset}
