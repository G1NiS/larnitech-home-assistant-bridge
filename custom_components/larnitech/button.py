from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, TYPE_LIGHT_SCHEME
from .entity import LarnitechEntity
from .hub import LarnitechHub

BUTTON_TYPES = {TYPE_LIGHT_SCHEME}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    hub: LarnitechHub = hass.data[DOMAIN][entry.entry_id]
    devices = [device for device in hub.devices if device.type in BUTTON_TYPES]
    async_add_entities([LarnitechButton(hub, device) for device in devices])


class LarnitechButton(LarnitechEntity, ButtonEntity):
    async def async_press(self) -> None:
        # 0xFF is the generic Larnitech toggle / execute command used by light
        # schemes and script-like items.
        await self.hub.async_set_status(self.device.addr, "0xFF")
