from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN, PLATFORMS
from .hub import LarnitechHub

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

    await hub.async_setup()

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
