from __future__ import annotations

from typing import Any

from homeassistant.components.light import ColorMode, LightEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, TYPE_DIMMER, TYPE_LAMP
from .entity import LarnitechEntity, numeric_value, state_is_on
from .hub import LarnitechHub
from .models import LarnitechDevice


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    hub: LarnitechHub = hass.data[DOMAIN][entry.entry_id]
    devices = [device for device in hub.devices if device.type in {TYPE_LAMP, TYPE_DIMMER}]
    async_add_entities([LarnitechLight(hub, device) for device in devices])


class LarnitechLight(LarnitechEntity, LightEntity):
    def __init__(self, hub: LarnitechHub, device: LarnitechDevice) -> None:
        super().__init__(hub, device)
        if device.type == TYPE_DIMMER:
            self._attr_supported_color_modes = {ColorMode.BRIGHTNESS}
            self._attr_color_mode = ColorMode.BRIGHTNESS
        else:
            self._attr_supported_color_modes = {ColorMode.ONOFF}
            self._attr_color_mode = ColorMode.ONOFF

    @property
    def is_on(self) -> bool | None:
        return state_is_on(self.status)

    @property
    def brightness(self) -> int | None:
        level = numeric_value(self.status, "level", "brightness")
        if level is None:
            return None
        return max(0, min(255, round(level * 255 / 100)))

    async def async_turn_on(self, **kwargs: Any) -> None:
        payload: dict[str, Any] = {"state": "on"}
        if self.device.type == TYPE_DIMMER and "brightness" in kwargs:
            payload["level"] = round(int(kwargs["brightness"]) * 100 / 255)
        await self.hub.async_set_status(self.device.addr, payload)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.hub.async_set_status(self.device.addr, {"state": "off"})
