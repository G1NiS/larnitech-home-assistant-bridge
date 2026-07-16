from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, TYPE_SWITCH, TYPE_VALVE, TYPE_VALVE_HEATING
from .entity import LarnitechEntity, state_is_on
from .hub import LarnitechHub
from .models import LarnitechDevice

SWITCH_TYPES = {TYPE_SWITCH, TYPE_VALVE, TYPE_VALVE_HEATING}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    hub: LarnitechHub = hass.data[DOMAIN][entry.entry_id]
    devices = [device for device in hub.devices if device.type in SWITCH_TYPES]
    async_add_entities([LarnitechSwitch(hub, device) for device in devices])


class LarnitechSwitch(LarnitechEntity, SwitchEntity):
    @property
    def is_on(self) -> bool | None:
        return state_is_on(self.status)

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.hub.async_set_status(self.device.addr, {"state": "on"})

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.hub.async_set_status(self.device.addr, {"state": "off"})
