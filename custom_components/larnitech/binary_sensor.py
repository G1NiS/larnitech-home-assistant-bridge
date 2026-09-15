from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
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
    async_add_entities(
        [
            LarnitechConnectionBinarySensor(hub, entry.entry_id),
            *[LarnitechBinarySensor(hub, device) for device in devices],
        ]
    )


class LarnitechConnectionBinarySensor(BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_has_entity_name = True
    _attr_name = "API2 connection"

    def __init__(self, hub: LarnitechHub, entry_id: str) -> None:
        self.hub = hub
        self._attr_unique_id = f"{DOMAIN}_{entry_id}_api2_connection"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name="Larnitech HA Bridge",
            manufacturer="Larnitech-compatible",
            model="API2 bridge",
        )
        self._unsubscribe = None

    @property
    def is_on(self) -> bool:
        return self.hub.available

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "reconnect_count": self.hub.reconnect_count,
            "last_disconnect": (
                self.hub.last_disconnect.isoformat()
                if self.hub.last_disconnect is not None
                else None
            ),
        }

    async def async_added_to_hass(self) -> None:
        self._unsubscribe = self.hub.async_add_availability_listener(self._handle_availability)

    async def async_will_remove_from_hass(self) -> None:
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None

    @callback
    def _handle_availability(self, _available: bool) -> None:
        self.async_write_ha_state()


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
