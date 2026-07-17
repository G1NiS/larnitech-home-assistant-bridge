from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import voluptuous as vol
from homeassistant import config_entries

from .api import LarnitechApiClient
from .const import DEFAULT_PORT, DOMAIN


def _normalize_host_and_port(host: str, port: int) -> tuple[str, int]:
    """Normalize user-entered host values for local API2 connection.

    Users often paste values like http://192.168.1.10 or 192.168.1.10:2041.
    The WebSocket client expects only the host name/IP and the port separately.
    """
    value = host.strip()
    if not value:
        return "", port

    if "://" in value:
        parsed = urlparse(value)
        normalized_host = parsed.hostname or ""
        normalized_port = parsed.port or port
        return normalized_host.strip(), normalized_port

    value = value.split("/", 1)[0].strip()
    if value.count(":") == 1:
        host_part, port_part = value.rsplit(":", 1)
        if port_part.isdigit():
            return host_part.strip(), int(port_part)

    return value, port


class LarnitechConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}

        if user_input is not None:
            raw_host = user_input.get("host", "")
            raw_port = user_input.get("port", DEFAULT_PORT)
            raw_api_key = user_input.get("api_key", "")

            host, port = _normalize_host_and_port(str(raw_host), int(raw_port))
            api_key = str(raw_api_key).strip()

            if not host:
                errors["host"] = "host_required"
            if not api_key:
                errors["api_key"] = "api_key_required"

            if not errors:
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

            user_input = {**user_input, "host": host, "port": port, "api_key": api_key}

        schema = vol.Schema(
            {
                vol.Required("host"): str,
                vol.Required("port", default=DEFAULT_PORT): int,
                vol.Required("api_key"): str,
            }
        )
        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
            last_step=True,
        )
