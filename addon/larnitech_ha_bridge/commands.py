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
    items. Climate/fancoil devices are more strict in practice: the Larnitech XML
    documentation defines fancoil commands as raw one-byte or two-byte status values,
    where byte 0 is off/on/toggle/no-change and byte 1 is fan power from 0..250.
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
    # Larnitech fancoil fan power is 0..250. HA fan modes are user-facing percent bands.
    return max(0, min(250, int(round(clamp_level(percent) * 2.5))))


def _fancoil_state_status(payload: str) -> str:
    return _hex_bytes(1 if parse_bool_payload(payload) else 0)


def _fancoil_mode_status(payload: str) -> str:
    mode = payload.strip().lower()
    if mode == "off":
        return _hex_bytes(0)
    if mode in {"cool", "heat"}:
        # Larnitech's public fancoil status-setting documentation only guarantees
        # direct off/on byte commands. Heat/cool is normally encoded in the selected
        # Larnitech automation/profile, so selecting a non-off HVAC mode turns the
        # fancoil on without sending unsupported JSON fields.
        return _hex_bytes(1)
    raise ValueError(f"Unsupported fancoil HVAC mode: {payload!r}")


def _fancoil_fan_status(payload: str) -> str:
    value = payload.strip().lower()
    fan_percent = {
        "off": 0,
        "low": 25,
        "medium": 50,
        "high": 75,
        "max": 100,
    }

    if value in fan_percent:
        percent = fan_percent[value]
    else:
        try:
            percent = clamp_level(float(value))
        except ValueError as exc:
            raise ValueError(f"Unsupported fancoil fan mode: {payload!r}") from exc

    if percent <= 0:
        return _hex_bytes(0)

    # 2-byte fancoil command: byte0=1 (on), byte1=0..250 fan power.
    return _hex_bytes(1, _percent_to_larnitech_power(percent))


def _fancoil_preset_status(payload: str) -> dict[str, str] | str:
    preset = payload.strip()
    if not preset:
        raise ValueError("Empty fancoil preset payload")

    # Home Assistant may emit "none" to clear a preset even when it was not listed
    # in the discovery payload. Larnitech has no documented "clear automation" name;
    # keep the device on and avoid sending an invalid automation value.
    if preset.lower() == "none":
        return _hex_bytes(1)

    if preset.lower() == "off":
        return {"state": "off", "automation": preset}

    # API2 returns automation names for fancoils, and accepts this payload shape.
    # Keep this name-based path for Larnitech profiles such as Mode/Eco/Comfort/Fast.
    return {"state": "on", "automation": preset}
