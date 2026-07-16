from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "larnitech"
DEFAULT_PORT = 2041
PLATFORMS: list[Platform] = [
    Platform.LIGHT,
    Platform.FAN,
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.SWITCH,
]

TYPE_LAMP = "lamp"
TYPE_DIMMER = "dimmer-lamp"
TYPE_FANCOIL = "fancoil"
TYPE_TEMPERATURE = "temperature-sensor"
TYPE_HUMIDITY = "humidity-sensor"
TYPE_ILLUMINATION = "illumination-sensor"
TYPE_MOTION = "motion-sensor"
TYPE_DOOR = "door-sensor"
TYPE_LEAK = "leak-sensor"
TYPE_SWITCH = "switch"
TYPE_VALVE = "valve"
TYPE_VALVE_HEATING = "valve-heating"
