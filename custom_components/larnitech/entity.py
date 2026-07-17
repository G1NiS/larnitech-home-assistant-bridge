from __future__ import annotations

import re
from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN, TYPE_DIMMER, TYPE_LAMP, TYPE_LIGHT, TYPE_LIGHT_SCHEME
from .hub import LarnitechHub
from .models import DeviceStatus, LarnitechDevice


def _slugify(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9_]+", "_", value)
    value = re.sub(r"_+", "_", value).strip("_")
    return value or "unknown"


def larnitech_area(device: LarnitechDevice) -> str:
    area = (device.area or "Setup").strip()
    return area or "Setup"


def is_grouped_light(device: LarnitechDevice) -> bool:
    if device.type == TYPE_LIGHT_SCHEME:
        return True
    if device.type not in {TYPE_LAMP, TYPE_LIGHT, TYPE_DIMMER}:
        return False
    contains = device.raw.get("contains")
    if isinstance(contains, list) and contains:
        return True
    return str(device.raw.get("virtual", "")).strip().lower() in {"yes", "true", "1"}


def larnitech_device_info(device: LarnitechDevice) -> DeviceInfo:
    """Return the Home Assistant device grouping for a Larnitech item.

    Larnitech installations are normally organised by areas/rooms. Exposing one
    Home Assistant device per area keeps the integration usable: room entities are
    grouped together and Setup/unassigned items are still visible instead of being
    hidden inside a single large bridge device.
    """
    if is_grouped_light(device):
        return DeviceInfo(
            identifiers={(DOMAIN, "light_groups")},
            name="Larnitech · Light groups",
            manufacturer="Larnitech-compatible",
            model="Light schemes / grouped lights",
        )

    area = larnitech_area(device)
    return DeviceInfo(
        identifiers={(DOMAIN, f"area_{_slugify(area)}")},
        name=f"Larnitech · {area}",
        manufacturer="Larnitech-compatible",
        model="Area / room",
        suggested_area=area,
    )


class LarnitechEntity(Entity):
    _attr_has_entity_name = True

    def __init__(self, hub: LarnitechHub, device: LarnitechDevice) -> None:
        self.hub = hub
        self.device = device
        self._attr_unique_id = f"{DOMAIN}_{device.addr.replace(':', '_')}"
        self._attr_name = device.name
        self._attr_device_info = larnitech_device_info(device)
        self._unsubscribe = None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "addr": self.device.addr,
            "larnitech_type": self.device.type,
            "larnitech_area": larnitech_area(self.device),
            "larnitech_grouped_light": is_grouped_light(self.device),
        }

    async def async_added_to_hass(self) -> None:
        self._unsubscribe = self.hub.async_add_listener(self.device.addr, self._handle_status)

    async def async_will_remove_from_hass(self) -> None:
        if self._unsubscribe:
            self._unsubscribe()
            self._unsubscribe = None

    def _handle_status(self, status: DeviceStatus) -> None:
        self.schedule_update_ha_state()

    @property
    def status(self) -> Any:
        return self.hub.status_by_addr.get(self.device.addr, self.device.raw.get("status"))


def status_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {"state": value}


def state_is_on(value: Any) -> bool:
    data = status_dict(value)
    state = str(data.get("state", data.get("value", value))).strip().lower()
    return state in {"on", "open", "opened", "true", "1", "yes"}


def numeric_value(value: Any, *keys: str) -> float | None:
    data = status_dict(value)
    for key in keys:
        raw = data.get(key)
        if raw is None:
            continue
        try:
            return float(raw)
        except (TypeError, ValueError):
            continue
    if not keys:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    return None
