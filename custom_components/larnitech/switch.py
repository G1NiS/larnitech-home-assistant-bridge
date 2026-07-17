from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, TYPE_SWITCH, TYPE_VALVE, TYPE_VALVE_HEATING
from .entity import LarnitechEntity, state_is_on, status_dict
from .hub import LarnitechHub
from .models import LarnitechDevice

SWITCH_TYPES = {TYPE_SWITCH, TYPE_VALVE, TYPE_VALVE_HEATING}


def is_controllable_switch(device: LarnitechDevice) -> bool:
    if device.type in {TYPE_VALVE, TYPE_VALVE_HEATING}:
        return True
    if device.type != TYPE_SWITCH:
        return False

    # Larnitech wall inputs are often reported as type=switch, area=Setup,
    # state=undefined and contain `linked` targets. They are physical inputs, not
    # useful Home Assistant switch controls, so keep them out of the entity list.
    if isinstance(device.raw.get("linked"), list) and device.raw["linked"]:
        state = str(status_dict(device.raw.get("status")).get("state", "")).lower()
        if state in {"undefined", "none", ""}:
            return False

    return True


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    hub: LarnitechHub = hass.data[DOMAIN][entry.entry_id]
    devices = [device for device in hub.devices if device.type in SWITCH_TYPES]
    async_add_entities([LarnitechSwitch(hub, device) for device in devices if is_controllable_switch(device)])


class LarnitechSwitch(LarnitechEntity, SwitchEntity):
    @property
    def is_on(self) -> bool | None:
        return state_is_on(self.status)

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.hub.async_set_status(self.device.addr, {"state": "on"})

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.hub.async_set_status(self.device.addr, {"state": "off"})
