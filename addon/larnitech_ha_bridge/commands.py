from __future__ import annotations

from typing import Any, Literal

from .models import LarnitechDevice

CommandKind = Literal["state", "brightness", "press"]


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

    is_on = parse_bool_payload(payload)

    if device_type in {"lamp", "dimmer-lamp", "light", "switch", "valve", "valve-heating"} or device is None:
        return {"state": "on" if is_on else "off"}

    return {"state": "on" if is_on else "off"}
