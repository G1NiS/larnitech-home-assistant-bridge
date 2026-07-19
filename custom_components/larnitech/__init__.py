from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN, PLATFORMS, TYPE_SWITCH
from .hub import LarnitechHub
from .models import LarnitechDevice

_LOGGER = logging.getLogger(__name__)


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

    _cleanup_stale_generic_switch_entities(hass, hub.devices)

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


def _cleanup_stale_generic_switch_entities(
    hass: HomeAssistant,
    devices: list[LarnitechDevice],
) -> None:
    """Remove old entity-registry entries for hidden generic Larnitech switches."""
    registry = er.async_get(hass)
    for device in devices:
        if device.type != TYPE_SWITCH:
            continue
        unique_id = f"{DOMAIN}_{device.addr.replace(':', '_')}"
        entity_id = registry.async_get_entity_id("switch", DOMAIN, unique_id)
        if entity_id is None:
            continue
        registry.async_remove(entity_id)
        _LOGGER.debug("Removed stale Larnitech generic switch entity %s", entity_id)
