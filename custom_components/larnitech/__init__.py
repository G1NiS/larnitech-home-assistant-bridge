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

    hub = LarnitechHub(
        hass=hass,
        host=host,
        port=entry.data["port"],
        api_key=entry.data["api_key"],
    )

    await hub.async_setup()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = hub
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    hub: LarnitechHub | None = hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    if hub is not None:
        await hub.async_close()
    return unload_ok
