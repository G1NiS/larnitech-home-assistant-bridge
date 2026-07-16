from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfIlluminance, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, TYPE_HUMIDITY, TYPE_ILLUMINATION, TYPE_TEMPERATURE
from .entity import LarnitechEntity, numeric_value
from .hub import LarnitechHub
from .models import LarnitechDevice

SENSOR_TYPES = {TYPE_TEMPERATURE, TYPE_HUMIDITY, TYPE_ILLUMINATION}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    hub: LarnitechHub = hass.data[DOMAIN][entry.entry_id]
    devices = [device for device in hub.devices if device.type in SENSOR_TYPES]
    async_add_entities([LarnitechSensor(hub, device) for device in devices])


class LarnitechSensor(LarnitechEntity, SensorEntity):
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, hub: LarnitechHub, device: LarnitechDevice) -> None:
        super().__init__(hub, device)
        if device.type == TYPE_TEMPERATURE:
            self._attr_device_class = SensorDeviceClass.TEMPERATURE
            self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        elif device.type == TYPE_HUMIDITY:
            self._attr_device_class = SensorDeviceClass.HUMIDITY
            self._attr_native_unit_of_measurement = PERCENTAGE
        elif device.type == TYPE_ILLUMINATION:
            self._attr_device_class = SensorDeviceClass.ILLUMINANCE
            self._attr_native_unit_of_measurement = UnitOfIlluminance.LUX

    @property
    def native_value(self):
        value = numeric_value(self.status, "value", "state", "temperature", "humidity", "illumination")
        if value is not None:
            return value
        return numeric_value(self.status)
