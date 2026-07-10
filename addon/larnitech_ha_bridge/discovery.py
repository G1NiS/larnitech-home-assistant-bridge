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


def normalize_state(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("state", "value", "level", "temperature"):
            if key in value:
                return normalize_state(value[key])
        return str(value)

    if isinstance(value, bool):
        return "ON" if value else "OFF"

    if isinstance(value, int | float):
        return f"{float(value):.2f}".rstrip("0").rstrip(".")

    text = str(value).strip()
    normalized = text.lower()
    if normalized in {"on", "open", "opened", "true", "1", "yes"}:
        return "ON"
    if normalized in {"off", "closed", "close", "false", "0", "no"}:
        return "OFF"
    return text


def entity_component(device: LarnitechDevice) -> str | None:
    if device.type == "fancoil":
        # Water fan-coils are exposed as simple ON/OFF fan entities.
        # Speed and heat/cool control are intentionally not advertised.
        return "fan"
    return SUPPORTED_TYPES.get(device.type)


def object_id(bridge_id: str, device: LarnitechDevice) -> str:
    # Address-only object IDs avoid duplicate entities when items are renamed in Larnitech.
    return slugify(f"{bridge_id}_{device.addr}")


def legacy_object_id(bridge_id: str, device: LarnitechDevice) -> str:
    # v0.1.0-v0.1.2 used name-based object IDs.
    # Those retained MQTT discovery topics must be cleared during migration.
    return slugify(f"{bridge_id}_{device.addr}_{device.name}")


def base_topic(bridge_id: str, device: LarnitechDevice) -> str:
    return f"{bridge_id}/{slugify(device.addr)}"


def discovery_topic(prefix: str, bridge_id: str, device: LarnitechDevice) -> str | None:
    component = entity_component(device)
    if component is None:
        return None
    return component_discovery_topic(prefix, bridge_id, device, component)


def component_discovery_topic(
    prefix: str,
    bridge_id: str,
    device: LarnitechDevice,
    component: str,
) -> str:
    return f"{prefix}/{component}/{object_id(bridge_id, device)}/config"


def legacy_discovery_topic(prefix: str, bridge_id: str, device: LarnitechDevice) -> str | None:
    component = entity_component(device)
    if component is None:
        return None
    return f"{prefix}/{component}/{legacy_object_id(bridge_id, device)}/config"


def bridge_device_info(bridge_id: str) -> dict[str, Any]:
    return {
        "identifiers": [f"{bridge_id}_bridge"],
        "name": "Larnitech Smart House",
        "manufacturer": "Larnitech-compatible",
        "model": "Smart House / API2 Bridge",
    }


def device_info(
    bridge_id: str,
    device: LarnitechDevice,
    grouping: Literal["area", "bridge", "entity"],
) -> dict[str, Any]:
    if grouping == "bridge":
        return bridge_device_info(bridge_id)

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


def display_name(
    device: LarnitechDevice,
    grouping: Literal["area", "bridge", "entity"],
    prefix_area: bool = True,
) -> str:
    name = device.name or device.addr
    if grouping == "bridge" and prefix_area and device.area:
        return f"{device.area} · {name}"
    return name


def discovery_payload(
    bridge_id: str,
    device: LarnitechDevice,
    grouping: Literal["area", "bridge", "entity"] = "bridge",
    prefix_area: bool = True,
) -> dict[str, Any] | None:
    component = entity_component(device)
    if component is None:
        return None

    topic = base_topic(bridge_id, device)
    payload: dict[str, Any] = {
        "name": display_name(device, grouping, prefix_area),
        "unique_id": object_id(bridge_id, device),
        "availability_topic": f"{bridge_id}/availability",
        "device": device_info(bridge_id, device, grouping),
    }

    if component == "fan":
        payload.update(_fan_discovery_payload(topic))
        return payload

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

        if device.type == "dimmer-lamp":
            payload.update(
                {
                    "brightness_command_topic": f"{topic}/brightness/set",
                    "brightness_state_topic": f"{topic}/brightness/state",
                    "brightness_scale": 100,
                    "brightness_value_template": "{{ value | int }}",
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


def _fan_discovery_payload(topic: str) -> dict[str, Any]:
    return {
        "state_topic": f"{topic}/state",
        "command_topic": f"{topic}/set",
        "payload_on": "ON",
        "payload_off": "OFF",
        "state_on": "ON",
        "state_off": "OFF",
        "json_attributes_topic": f"{topic}/attributes",
    }


def _float_attr(raw: dict[str, Any], *names: str) -> float | None:
    for name in names:
        value = raw.get(name)
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _preset_modes(device: LarnitechDevice) -> list[str]:
    modes = device.raw.get("automations") or device.raw.get("automation") or []
    if isinstance(modes, str):
        return [mode.strip() for mode in modes.split(",") if mode.strip()]
    if isinstance(modes, list):
        return [str(mode).strip() for mode in modes if str(mode).strip()]
    return []


def diagnostics_sensor_payload(bridge_id: str, object_suffix: str, name: str) -> tuple[str, dict]:
    object_id_value = slugify(f"{bridge_id}_diagnostics_{object_suffix}")
    return (
        f"sensor/{object_id_value}/config",
        {
            "name": f"Larnitech · {name}",
            "unique_id": object_id_value,
            "state_topic": f"{bridge_id}/diagnostics/{object_suffix}/state",
            "json_attributes_topic": f"{bridge_id}/diagnostics/{object_suffix}/attributes",
            "availability_topic": f"{bridge_id}/availability",
            "device": bridge_device_info(bridge_id),
            "entity_category": "diagnostic",
        },
    )
