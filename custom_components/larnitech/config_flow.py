from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries

from .api import LarnitechApiClient
from .const import DEFAULT_PORT, DOMAIN


class LarnitechConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input["host"]
            port = user_input["port"]
            api_key = user_input["api_key"]

            await self.async_set_unique_id(host)
            self._abort_if_unique_id_configured()

            client = LarnitechApiClient(host, port, api_key, name="config_flow")
            try:
                await client.connect()
                await client.get_devices()
            except Exception:
                errors["base"] = "cannot_connect"
            finally:
                await client.close()

            if not errors:
                return self.async_create_entry(
                    title=f"Larnitech {host}",
                    data={"host": host, "port": port, "api_key": api_key},
                )

        schema = vol.Schema(
            {
                vol.Required("host"): str,
                vol.Required("port", default=DEFAULT_PORT): int,
                vol.Required("api_key"): str,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)
