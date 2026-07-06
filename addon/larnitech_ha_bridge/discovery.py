from __future__ import annotations

import re
from typing import Any, Literal

from .models import LarnitechDevice


SUPPORTED_TYPES = {
    "lamp": "light",
    "dimmer-lamp": "light",
    "light": "light",
    "temperature-sensor": "sensor",
    "humidity-sensor": "sensor",
    "illumination-sensor": "sensor",
    "motion-sensor": "binary_sensor",
    "door-sensor": "binary_sensor",
    "leak-sensor": "binary_sensor",
    "valve": "switch",
    "valve-heating": "switch",
    "light-scheme": "button",
    "script": "button",
    # Keep switch supported technically, but filter physical input switches by default in config.
    "switch": "switch",
}


def slugify(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9_]+", "_", value)
    value = re.sub(r"_+", "_", value).strip("_")
    return value or "unknown"


def entity_component(device: LarnitechDevice) -> str | None:
    return SUPPORTED_TYPES.get(device.type)


def object_id(bridge_id: str, device: LarnitechDevice) -> str:
    return slugify(f"{bridge_id}_{device.addr}_{device.name}")


def base_topic(bridge_id: str, device: LarnitechDevice) -> str:
    return f"{bridge_id}/{slugify(device.addr)}"


def discovery_topic(prefix: str, bridge_id: str, device: LarnitechDevice) -> str | None:
    component = entity_component(device)
    if component is None:
        return None
    return f"{prefix}/{component}/{object_id(bridge_id, device)}/config"


def device_info(
    bridge_id: str,
    device: LarnitechDevice,
    grouping: Literal["area", "bridge", "entity"],
) -> dict[str, Any]:
    if grouping == "bridge":
        return {
            "identifiers": [f"{bridge_id}_bridge"],
            "name": "Larnitech Smart Home",
            "manufacturer": "Larnitech-compatible",
            "model": "API2 Bridge",
        }

    if grouping == "area":
        area = device.area or "Unassigned"
        return {
            "identifiers": [f"{bridge_id}_area_{slugify(area)}"],
            "name": f"Larnitech - {area}",
            "manufacturer": "Larnitech-compatible",
            "model": "Area",
            "suggested_area": area,
        }

    return {
        "identifiers": [f"{bridge_id}_{slugify(device.addr)}"],
        "name": device.name,
        "manufacturer": "Larnitech-compatible",
        "model": device.type,
        "suggested_area": device.area,
    }


def discovery_payload(
    bridge_id: str,
    device: LarnitechDevice,
    grouping: Literal["area", "bridge", "entity"] = "area",
) -> dict[str, Any] | None:
    component = entity_component(device)
    if component is None:
        return None

    topic = base_topic(bridge_id, device)
    payload: dict[str, Any] = {
        "name": device.name or device.addr,
        "unique_id": object_id(bridge_id, device),
        "availability_topic": f"{bridge_id}/availability",
        "device": device_info(bridge_id, device, grouping),
    }

    if component in {"switch", "light"}:
        payload.update(
            {
                "state_topic": f"{topic}/state",
                "command_topic": f"{topic}/set",
                "payload_on": "ON",
                "payload_off": "OFF",
                "state_on": "ON",
                "state_off": "OFF",
            }
        )

    if component == "button":
        payload.update(
            {
                "command_topic": f"{topic}/set",
                "payload_press": "PRESS",
            }
        )

    if component == "sensor":
        payload["state_topic"] = f"{topic}/state"

        if device.type == "temperature-sensor":
            payload["device_class"] = "temperature"
            payload["unit_of_measurement"] = "°C"
            payload["state_class"] = "measurement"
        elif device.type == "humidity-sensor":
            payload["device_class"] = "humidity"
            payload["unit_of_measurement"] = "%"
            payload["state_class"] = "measurement"
        elif device.type == "illumination-sensor":
            payload["device_class"] = "illuminance"
            payload["unit_of_measurement"] = "lx"
            payload["state_class"] = "measurement"

    if component == "binary_sensor":
        payload["state_topic"] = f"{topic}/state"

        if device.type == "motion-sensor":
            payload["device_class"] = "motion"
        elif device.type == "door-sensor":
            payload["device_class"] = "door"
        elif device.type == "leak-sensor":
            payload["device_class"] = "moisture"

        payload["payload_on"] = "ON"
        payload["payload_off"] = "OFF"

    return payload


def normalize_state(value: Any) -> str:
    if isinstance(value, dict):
        if "state" in value:
            return normalize_state(value["state"])
        if "value" in value:
            return normalize_state(value["value"])
        return str(value)

    if isinstance(value, bool):
        return "ON" if value else "OFF"

    if isinstance(value, (int, float)):
        if value in (0, 1):
            return "ON" if value == 1 else "OFF"
        return str(round(value, 2))

    if isinstance(value, str):
        lowered = value.lower().strip()
        if lowered in {"1", "true", "on", "open", "opened", "active", "motion"}:
            return "ON"
        if lowered in {"0", "false", "off", "closed", "inactive", "clear"}:
            return "OFF"
        return value

    return str(value)
