from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry

from .api import LarnitechApiClient
from .const import DEFAULT_PORT, DOMAIN


INTEGRATION_TITLE = "Larnitech HA Bridge"
AREA_OVERRIDES_KEY = "area_overrides"
AREA_OVERRIDES_TEXT_KEY = "area_overrides_text"


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


def parse_area_overrides(value: str) -> dict[str, str]:
    overrides: dict[str, str] = {}
    for raw_line in value.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(f"Invalid area override line: {raw_line}")
        addr, area = line.split("=", 1)
        addr = addr.strip()
        area = area.strip()
        if not addr or not area:
            raise ValueError(f"Invalid area override line: {raw_line}")
        overrides[addr] = area
    return overrides


def format_area_overrides(overrides: dict[str, str] | None) -> str:
    if not overrides:
        return ""
    return "\n".join(f"{addr}={area}" for addr, area in sorted(overrides.items()))


class LarnitechConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @staticmethod
    def async_get_options_flow(config_entry: ConfigEntry) -> config_entries.OptionsFlow:
        return LarnitechOptionsFlow(config_entry)

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        host_default = ""
        port_default = DEFAULT_PORT
        api_key_default = ""
        area_overrides_default = ""

        if user_input is not None:
            raw_host = user_input.get("host", "")
            raw_port = user_input.get("port", DEFAULT_PORT)
            raw_api_key = user_input.get("api_key", "")
            raw_area_overrides = str(user_input.get(AREA_OVERRIDES_TEXT_KEY, "")).strip()

            host, port = _normalize_host_and_port(str(raw_host), int(raw_port))
            api_key = str(raw_api_key).strip()
            host_default = host
            port_default = port
            api_key_default = api_key
            area_overrides_default = raw_area_overrides
            area_overrides: dict[str, str] = {}

            if raw_area_overrides:
                try:
                    area_overrides = parse_area_overrides(raw_area_overrides)
                except ValueError:
                    errors[AREA_OVERRIDES_TEXT_KEY] = "area_overrides_invalid"

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
                    title=f"{INTEGRATION_TITLE} ({host})",
                    data={
                        "host": host,
                        "port": port,
                        "api_key": api_key,
                        AREA_OVERRIDES_KEY: area_overrides,
                    },
                )

        schema = vol.Schema(
            {
                vol.Required("host", default=host_default): str,
                vol.Required("port", default=port_default): int,
                vol.Required("api_key", default=api_key_default): str,
                vol.Optional(AREA_OVERRIDES_TEXT_KEY, default=area_overrides_default): str,
            }
        )
        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
            last_step=True,
        )


class LarnitechOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, config_entry: ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        current_overrides = self.config_entry.options.get(
            AREA_OVERRIDES_KEY,
            self.config_entry.data.get(AREA_OVERRIDES_KEY, {}),
        )
        area_overrides_default = format_area_overrides(current_overrides)

        if user_input is not None:
            raw_area_overrides = str(user_input.get(AREA_OVERRIDES_TEXT_KEY, "")).strip()
            try:
                area_overrides = parse_area_overrides(raw_area_overrides)
            except ValueError:
                errors[AREA_OVERRIDES_TEXT_KEY] = "area_overrides_invalid"
                area_overrides_default = raw_area_overrides
            else:
                return self.async_create_entry(
                    title="",
                    data={AREA_OVERRIDES_KEY: area_overrides},
                )

        schema = vol.Schema(
            {
                vol.Optional(AREA_OVERRIDES_TEXT_KEY, default=area_overrides_default): str,
            }
        )
        return self.async_show_form(
            step_id="init",
            data_schema=schema,
            errors=errors,
        )
