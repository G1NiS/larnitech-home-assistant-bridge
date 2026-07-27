from __future__ import annotations

import logging
from functools import partial

import voluptuous as vol

from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady, ServiceValidationError
from homeassistant.helpers import config_validation as cv
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

SERVICE_START_MAPPING = "start_mapping"
SERVICE_STOP_MAPPING = "stop_mapping"
CONF_CONFIG_ENTRY_ID = "config_entry_id"
CONF_GROUP_WINDOW_SECONDS = "group_window_seconds"

START_MAPPING_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_CONFIG_ENTRY_ID): cv.string,
        vol.Optional(CONF_GROUP_WINDOW_SECONDS, default=3.0): vol.All(
            vol.Coerce(float), vol.Range(min=0.5, max=10.0)
        ),
    }
)
STOP_MAPPING_SCHEMA = vol.Schema({vol.Optional(CONF_CONFIG_ENTRY_ID): cv.string})

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
    """Set up domain-level Larnitech actions."""
    hass.data.setdefault(DOMAIN, {})
    _register_mapping_services(hass)
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
    domain_data = hass.data.get(DOMAIN, {})
    hub: LarnitechHub | None = domain_data.pop(entry.entry_id, None)
    if hub is not None:
        await hub.async_close()
    return unload_ok


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


def _register_mapping_services(hass: HomeAssistant) -> None:
    if not hass.services.has_service(DOMAIN, SERVICE_START_MAPPING):
        hass.services.async_register(
            DOMAIN,
            SERVICE_START_MAPPING,
            partial(_async_handle_start_mapping, hass),
            schema=START_MAPPING_SCHEMA,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_STOP_MAPPING):
        hass.services.async_register(
            DOMAIN,
            SERVICE_STOP_MAPPING,
            partial(_async_handle_stop_mapping, hass),
            schema=STOP_MAPPING_SCHEMA,
        )


async def _async_handle_start_mapping(hass: HomeAssistant, call: ServiceCall) -> None:
    hub = _hub_for_service(hass, call)
    path = await hub.async_start_mapping(call.data[CONF_GROUP_WINDOW_SECONDS])
    persistent_notification.async_create(
        hass,
        (
            "Mapping started. Press one wall-switch key at a time and wait at least "
            f"{call.data[CONF_GROUP_WINDOW_SECONDS]:g} seconds between keys. "
            f"The latest summary will be written to `{path}`."
        ),
        title="Larnitech mapping started",
        notification_id="larnitech_mapping",
    )


async def _async_handle_stop_mapping(hass: HomeAssistant, call: ServiceCall) -> None:
    hub = _hub_for_service(hass, call)
    path = await hub.async_stop_mapping()
    if path is None:
        message = "No active Larnitech mapping session was found."
    else:
        message = f"Mapping stopped. Upload `{path}` for final switch and light labeling."
    persistent_notification.async_create(
        hass,
        message,
        title="Larnitech mapping stopped",
        notification_id="larnitech_mapping",
    )


def _hub_for_service(hass: HomeAssistant, call: ServiceCall) -> LarnitechHub:
    hubs: dict[str, LarnitechHub] = hass.data.get(DOMAIN, {})
    requested_entry_id = call.data.get(CONF_CONFIG_ENTRY_ID)
    if requested_entry_id:
        hub = hubs.get(requested_entry_id)
        if hub is None:
            raise ServiceValidationError(
                f"Larnitech config entry {requested_entry_id!r} is not loaded"
            )
        return hub
    if len(hubs) == 1:
        return next(iter(hubs.values()))
    if not hubs:
        raise ServiceValidationError("No loaded Larnitech integration was found")
    raise ServiceValidationError(
        "Multiple Larnitech integrations are loaded; provide config_entry_id"
    )


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
