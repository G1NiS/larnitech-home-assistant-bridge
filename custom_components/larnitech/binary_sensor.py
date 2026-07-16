from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, TYPE_DOOR, TYPE_LEAK, TYPE_MOTION
from .entity import LarnitechEntity, state_is_on
from .hub import LarnitechHub
from .models import LarnitechDevice

BINARY_TYPES = {TYPE_MOTION, TYPE_DOOR, TYPE_LEAK}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    hub: LarnitechHub = hass.data[DOMAIN][entry.entry_id]
    devices = [device for device in hub.devices if device.type in BINARY_TYPES]
    async_add_entities([LarnitechBinarySensor(hub, device) for device in devices])


class LarnitechBinarySensor(LarnitechEntity, BinarySensorEntity):
    def __init__(self, hub: LarnitechHub, device: LarnitechDevice) -> None:
        super().__init__(hub, device)
        if device.type == TYPE_MOTION:
            self._attr_device_class = BinarySensorDeviceClass.MOTION
        elif device.type == TYPE_DOOR:
            self._attr_device_class = BinarySensorDeviceClass.DOOR
        elif device.type == TYPE_LEAK:
            self._attr_device_class = BinarySensorDeviceClass.MOISTURE

    @property
    def is_on(self) -> bool | None:
        return state_is_on(self.status)
