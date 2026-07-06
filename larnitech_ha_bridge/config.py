from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


class BridgeConfig(BaseModel):
    larnitech_host: str = Field(default="192.168.32.121")
    larnitech_port: int = Field(default=2041)
    larnitech_api_key: str

    mqtt_host: str = Field(default="core-mosquitto")
    mqtt_port: int = Field(default=1883)
    mqtt_username: str | None = None
    mqtt_password: str | None = None
    mqtt_discovery_prefix: str = Field(default="homeassistant")

    bridge_id: str = Field(default="larnitech")
    log_level: Literal["debug", "info", "warning", "error"] = "info"
    ignored_areas: list[str] = Field(default_factory=list)
    ignored_types: list[str] = Field(default_factory=list)
    publish_unsupported_devices: bool = True

    @property
    def larnitech_ws_url(self) -> str:
        return f"ws://{self.larnitech_host}:{self.larnitech_port}/api"


def load_config() -> BridgeConfig:
    addon_options = Path("/data/options.json")
    local_options = Path("options.json")

    if addon_options.exists():
        raw = json.loads(addon_options.read_text(encoding="utf-8"))
    elif local_options.exists():
        raw = json.loads(local_options.read_text(encoding="utf-8"))
    else:
        raw = {
            "larnitech_host": os.getenv("LARNITECH_HOST", "192.168.32.121"),
            "larnitech_port": int(os.getenv("LARNITECH_PORT", "2041")),
            "larnitech_api_key": os.getenv("LARNITECH_API_KEY", ""),
            "mqtt_host": os.getenv("MQTT_HOST", "core-mosquitto"),
            "mqtt_port": int(os.getenv("MQTT_PORT", "1883")),
            "mqtt_username": os.getenv("MQTT_USERNAME") or None,
            "mqtt_password": os.getenv("MQTT_PASSWORD") or None,
            "mqtt_discovery_prefix": os.getenv("MQTT_DISCOVERY_PREFIX", "homeassistant"),
            "bridge_id": os.getenv("BRIDGE_ID", "larnitech"),
            "log_level": os.getenv("LOG_LEVEL", "info"),
        }

    if not raw.get("larnitech_api_key"):
        raise ValueError("larnitech_api_key is required")

    return BridgeConfig(**raw)
