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
FANCOIL_POWER_LOW = 0x53
FANCOIL_POWER_MEDIUM = 0xA6
FANCOIL_POWER_HIGH = 0xFA


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


def fancoil_power_for_percent(percent: float) -> int:
    """Return the closest documented Larnitech fancoil power byte, 0-250."""
    native_level = fancoil_native_level(percent)
    if native_level <= 0:
        return 0
    if native_level == FANCOIL_LEVEL_LOW:
        return FANCOIL_POWER_LOW
    if native_level == FANCOIL_LEVEL_MEDIUM:
        return FANCOIL_POWER_MEDIUM
    return FANCOIL_POWER_HIGH


def fancoil_raw_hex(power: int, *, turn_on: bool = True) -> str:
    """Return a documented raw fancoil status-set payload.

    The Larnitech fancoil setting format supports two bytes:
    - byte 0: 1 = on, 0 = off, 0xFE = do not change on/off
    - byte 1: fan power, 0-250
    """
    if power <= 0:
        return "0x00"
    first_byte = 0x01 if turn_on else 0xFE
    return f"0x{first_byte:02X}{max(0, min(0xFA, power)):02X}"


def larnitech_status_for_command(
    device: LarnitechDevice | None,
    payload: str,
    command_kind: CommandKind,
) -> Any:
    """Convert a Home Assistant MQTT command payload to Larnitech API2 status-set.

    API2 accepts object status payloads such as {"state": "off"} for simple on/off
    items. Fancoil structured fan fields are accepted by API2 but can be ignored by
    Larnitech runtime, so fancoil speed writes use the documented raw 2-byte payload.
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


def _fancoil_state_status(payload: str) -> str:
    # Use raw payloads for fancoil state too. The structured {"state":"on"} path
    # turns the device on but this installation keeps/restores fan=100 and mode=heat.
    return fancoil_raw_hex(FANCOIL_POWER_HIGH) if parse_bool_payload(payload) else "0x00"


def _fancoil_mode_status(payload: str) -> str:
    # Backward compatibility for stale climate cards/topics. New discovery publishes
    # fancoils as fan entities, not climate entities. Larnitech mode appears to be a
    # runtime/status bit and is not reliably changed by structured API2 mode fields.
    mode = payload.strip().lower()
    if mode == "off":
        return "0x00"
    if mode in {"cool", "heat", "on"}:
        return fancoil_raw_hex(FANCOIL_POWER_HIGH)
    raise ValueError(f"Unsupported fancoil HVAC mode: {payload!r}")


def _fancoil_fan_status(payload: str) -> str:
    value = payload.strip().lower()

    speed_power = {
        "off": 0,
        "0": 0,
        "low": FANCOIL_POWER_LOW,
        "1": FANCOIL_POWER_LOW,
        "medium": FANCOIL_POWER_MEDIUM,
        "med": FANCOIL_POWER_MEDIUM,
        "2": FANCOIL_POWER_MEDIUM,
        "high": FANCOIL_POWER_HIGH,
        "max": FANCOIL_POWER_HIGH,
        "3": FANCOIL_POWER_HIGH,
    }

    if value in speed_power:
        power = speed_power[value]
    else:
        try:
            power = fancoil_power_for_percent(float(value))
        except ValueError as exc:
            raise ValueError(f"Unsupported fancoil fan mode: {payload!r}") from exc

    return fancoil_raw_hex(power)


def _fancoil_preset_status(payload: str) -> str | dict[str, str]:
    preset = payload.strip()
    if not preset:
        raise ValueError("Empty fancoil preset payload")

    # New fan entity preset modes are the speed names. Keep this here so stale
    # subscriptions or older retained discovery payloads still control fan speed.
    if preset.lower() in {"off", "0", "low", "1", "medium", "med", "2", "high", "max", "3"}:
        return _fancoil_fan_status(preset)

    if preset.lower() == "none":
        return fancoil_raw_hex(FANCOIL_POWER_HIGH)

    # API2 returns automation names for some fancoils. Avoid using them from the fan
    # entity by default; direct preset commands are left for legacy/manual testing.
    return {"state": "on", "automation": preset}
