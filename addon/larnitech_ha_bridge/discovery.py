from __future__ import annotations

import re
from typing import Any

from .models import LarnitechDevice


SUPPORTED_TYPES = {
    "lamp": "light",
    "dimmer-lamp": "light",
    "light": "light",
    "switch": "switch",
    "relay": "switch",
    "temperature-sensor": "sensor",
    "humidity-sensor": "sensor",
    "motion-sensor": "binary_sensor",
    "leak-sensor": "binary_sensor",
    "valve": "switch",
    "valve-heating": "switch",
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


def discovery_payload(bridge_id: str, device: LarnitechDevice) -> dict[str, Any] | None:
    component = entity_component(device)
    if component is None:
        return None

    topic = base_topic(bridge_id, device)
    payload: dict[str, Any] = {
        "name": device.name,
        "unique_id": object_id(bridge_id, device),
        "state_topic": f"{topic}/state",
        "availability_topic": f"{bridge_id}/availability",
        "device": {
            "identifiers": [f"{bridge_id}_{slugify(device.addr)}"],
            "name": device.name,
            "manufacturer": "Larnitech-compatible",
            "model": device.type,
            "suggested_area": device.area,
        },
    }

    if component in {"switch", "light"}:
        payload["command_topic"] = f"{topic}/set"
        payload["payload_on"] = "ON"
        payload["payload_off"] = "OFF"
        payload["state_on"] = "ON"
        payload["state_off"] = "OFF"

    if component == "sensor":
        if "temperature" in device.type:
            payload["device_class"] = "temperature"
            payload["unit_of_measurement"] = "°C"
            payload["state_class"] = "measurement"
        elif "humidity" in device.type:
            payload["device_class"] = "humidity"
            payload["unit_of_measurement"] = "%"
            payload["state_class"] = "measurement"

    if component == "binary_sensor":
        if "motion" in device.type:
            payload["device_class"] = "motion"
        elif "leak" in device.type:
            payload["device_class"] = "moisture"
        payload["payload_on"] = "ON"
        payload["payload_off"] = "OFF"

    return payload


def normalize_state(value: Any) -> str:
    if isinstance(value, bool):
        return "ON" if value else "OFF"

    if isinstance(value, (int, float)):
        if value in (0, 1):
            return "ON" if value == 1 else "OFF"
        return str(value)

    if isinstance(value, str):
        lowered = value.lower().strip()
        if lowered in {"1", "true", "on", "open", "active"}:
            return "ON"
        if lowered in {"0", "false", "off", "closed", "inactive"}:
            return "OFF"
        return value

    return str(value)
