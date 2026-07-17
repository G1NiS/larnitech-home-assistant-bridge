from __future__ import annotations

from typing import Any

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, TYPE_FANCOIL
from .entity import LarnitechEntity, numeric_value, state_is_on, status_dict
from .hub import LarnitechHub


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    hub: LarnitechHub = hass.data[DOMAIN][entry.entry_id]
    devices = [device for device in hub.devices if device.type == TYPE_FANCOIL]
    async_add_entities([LarnitechFancoil(hub, device) for device in devices])


class LarnitechFancoil(LarnitechEntity, FanEntity):
    _attr_supported_features = FanEntityFeature.TURN_ON | FanEntityFeature.TURN_OFF
    _enable_turn_on_off_backwards_compatibility = False

    @property
    def is_on(self) -> bool | None:
        status = self.status
        data = status_dict(status)

        # Larnitech fancoils can report fan=100 even while state=off. Trust the
        # explicit runtime state first, otherwise HA shows the fan as on when the
        # physical fan-coil is actually off.
        if "state" in data:
            return state_is_on(data)

        fan_level = numeric_value(data, "fan", "fan_level", "level")
        if fan_level is not None:
            return fan_level > 0
        return state_is_on(status)

    async def async_turn_on(
        self,
        percentage: int | None = None,
        preset_mode: str | None = None,
        **kwargs: Any,
    ) -> None:
        await self.hub.async_set_status(self.device.addr, {"state": "on"})

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.hub.async_set_status(self.device.addr, {"state": "off"})
