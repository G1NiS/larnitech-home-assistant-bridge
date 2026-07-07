from __future__ import annotations

import re
from typing import Any, Literal

from .models import LarnitechDevice

FancoilEntityMode = Literal["fan", "climate"]


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


def entity_component(
    device: LarnitechDevice,
    fancoil_entity_mode: FancoilEntityMode = "fan",
) -> str | None:
    if device.type == "fancoil":
        return fancoil_entity_mode
    return SUPPORTED_TYPES.get(device.type)


def object_id(bridge_id: str, device: LarnitechDevice) -> str:
    # v0.1.3 uses address-only object IDs so renaming items in Larnitech does not
    # create duplicate entities in Home Assistant.
    return slugify(f"{bridge_id}_{device.addr}")


def legacy_object_id(bridge_id: str, device: LarnitechDevice) -> str:
    # v0.1.0-v0.1.2 used name-based object IDs.
    # Those retained MQTT discovery topics must be cleared during migration.
    return slugify(f"{bridge_id}_{device.addr}_{device.name}")


def base_topic(bridge_id: str, device: LarnitechDevice) -> str:
    return f"{bridge_id}/{slugify(device.addr)}"


def discovery_topic(
    prefix: str,
    bridge_id: str,
    device: LarnitechDevice,
    fancoil_entity_mode: FancoilEntityMode = "fan",
) -> str | None:
    component = entity_component(device, fancoil_entity_mode=fancoil_entity_mode)
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


def legacy_discovery_topic(
    prefix: str,
    bridge_id: str,
    device: LarnitechDevice,
    fancoil_entity_mode: FancoilEntityMode = "fan",
) -> str | None:
    component = entity_component(device, fancoil_entity_mode=fancoil_entity_mode)
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
    fancoil_entity_mode: FancoilEntityMode = "fan",
) -> dict[str, Any] | None:
    component = entity_component(device, fancoil_entity_mode=fancoil_entity_mode)
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

    if component == "climate":
        payload.update(_climate_discovery_payload(topic, device))
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
        "preset_modes": ["off", "low", "medium", "high"],
        "preset_mode_state_topic": f"{topic}/preset_mode/state",
        "preset_mode_command_topic": f"{topic}/preset_mode/set",
        "json_attributes_topic": f"{topic}/attributes",
    }


def _climate_discovery_payload(topic: str, device: LarnitechDevice) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "mode_state_topic": f"{topic}/mode/state",
        "mode_command_topic": f"{topic}/mode/set",
        "modes": ["off", "heat", "cool"],
        "current_temperature_topic": f"{topic}/current_temperature/state",
        "temperature_state_topic": f"{topic}/target_temperature/state",
        "temperature_unit": "C",
        "precision": 0.1,
        "temp_step": 0.5,
        "fan_mode_state_topic": f"{topic}/fan_mode/state",
        "fan_mode_command_topic": f"{topic}/fan_mode/set",
        "fan_modes": ["off", "low", "medium", "high"],
        "json_attributes_topic": f"{topic}/attributes",
    }

    min_temp = _float_attr(device.raw, "t-min", "t_min")
    max_temp = _float_attr(device.raw, "t-max", "t_max")
    if min_temp is not None:
        payload["min_temp"] = min_temp
    if max_temp is not None:
        payload["max_temp"] = max_temp

    preset_modes = _preset_modes(device)
    if preset_modes:
        payload.update(
            {
                "preset_modes": preset_modes,
                "preset_mode_state_topic": f"{topic}/preset/state",
                "preset_mode_command_topic": f"{topic}/preset/set",
            }
        )

    return payload


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
    automations = device.raw.get("automations")
    if not isinstance(automations, list):
        return []

    modes: list[str] = []
    for automation in automations:
        if not isinstance(automation, str):
            continue
        automation = automation.strip()
        if automation and automation not in modes:
            modes.append(automation)
    return modes


def diagnostics_sensor_payload(
    bridge_id: str, object_suffix: str, name: str
) -> tuple[str, dict[str, Any]]:
    topic_base = f"{bridge_id}/diagnostics/{slugify(object_suffix)}"
    unique_id = slugify(f"{bridge_id}_{object_suffix}")
    discovery = {
        "name": f"Diagnostics · {name}",
        "unique_id": unique_id,
        "state_topic": f"{topic_base}/state",
        "json_attributes_topic": f"{topic_base}/attributes",
        "entity_category": "diagnostic",
        "device": bridge_device_info(bridge_id),
    }
    discovery_topic_value = f"sensor/{unique_id}/config"
    return discovery_topic_value, discovery


def normalize_state(value: Any) -> str:
    if isinstance(value, dict):
        if "state" in value:
            return normalize_state(value["state"])
        if "value" in value:
            return normalize_state(value["value"])
        if "level" in value:
            try:
                return "ON" if float(value["level"]) > 0 else "OFF"
            except (TypeError, ValueError):
                return str(value["level"])
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
