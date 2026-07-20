from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.typing import ConfigType

from .const import (
    DOMAIN,
    PLATFORMS,
    TYPE_DIMMER,
    TYPE_DOOR,
    TYPE_FANCOIL,
    TYPE_HUMIDITY,
    TYPE_ILLUMINATION,
    TYPE_LAMP,
    TYPE_LEAK,
    TYPE_LIGHT,
    TYPE_LIGHT_SCHEME,
    TYPE_MOTION,
    TYPE_SWITCH,
    TYPE_TEMPERATURE,
    TYPE_VALVE,
    TYPE_VALVE_HEATING,
)
from .entity import entity_enabled_default
from .hub import LarnitechHub
from .models import LarnitechDevice

_LOGGER = logging.getLogger(__name__)

TYPE_TO_ENTITY_DOMAIN = {
    TYPE_LAMP: "light",
    TYPE_LIGHT: "light",
    TYPE_DIMMER: "light",
    TYPE_FANCOIL: "fan",
    TYPE_TEMPERATURE: "sensor",
    TYPE_HUMIDITY: "sensor",
    TYPE_ILLUMINATION: "sensor",
    TYPE_MOTION: "binary_sensor",
    TYPE_DOOR: "binary_sensor",
    TYPE_LEAK: "binary_sensor",
    TYPE_SWITCH: "switch",
    TYPE_VALVE: "switch",
    TYPE_VALVE_HEATING: "switch",
    TYPE_LIGHT_SCHEME: "button",
}


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    host = entry.data["host"]
    if not entry.title.startswith("Larnitech HA Bridge"):
        hass.config_entries.async_update_entry(entry, title=f"Larnitech HA Bridge ({host})")

    area_overrides = entry.options.get("area_overrides", entry.data.get("area_overrides", {}))

    hub = LarnitechHub(
        hass=hass,
        host=host,
        port=entry.data["port"],
        api_key=entry.data["api_key"],
        area_overrides=area_overrides,
    )

    try:
        await hub.async_setup()
    except Exception as exc:
        await hub.async_close()
        raise ConfigEntryNotReady(f"Unable to connect to Larnitech API2 at {host}") from exc

    _cleanup_stale_hidden_entities(hass, hub.devices)

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = hub
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    hub: LarnitechHub | None = hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    if hub is not None:
        await hub.async_close()
    return unload_ok


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


def _cleanup_stale_hidden_entities(
    hass: HomeAssistant,
    devices: list[LarnitechDevice],
) -> None:
    """Remove old entity-registry entries for low-level hidden Larnitech items."""
    registry = er.async_get(hass)
    for device in devices:
        if entity_enabled_default(device):
            continue
        entity_domain = TYPE_TO_ENTITY_DOMAIN.get(device.type)
        if entity_domain is None:
            continue
        unique_id = f"{DOMAIN}_{device.addr.replace(':', '_')}"
        entity_id = registry.async_get_entity_id(entity_domain, DOMAIN, unique_id)
        if entity_id is None:
            continue
        registry.async_remove(entity_id)
        _LOGGER.debug("Removed stale hidden Larnitech entity %s", entity_id)
