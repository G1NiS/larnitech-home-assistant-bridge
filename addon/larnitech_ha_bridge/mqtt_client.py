from __future__ import annotations

import json
import logging
from collections.abc import Callable

import paho.mqtt.client as mqtt

from .config import BridgeConfig
from .discovery import discovery_payload, discovery_topic, normalize_state, slugify
from .models import DeviceStatus, LarnitechDevice

_LOGGER = logging.getLogger(__name__)


class MqttBridgeClient:
    def __init__(self, config: BridgeConfig, command_callback: Callable[[str, str], None]) -> None:
        self.config = config
        self.command_callback = command_callback
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        if config.mqtt_username:
            self.client.username_pw_set(config.mqtt_username, config.mqtt_password)

        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self._addr_by_command_topic: dict[str, str] = {}

    def connect(self) -> None:
        _LOGGER.info("Connecting to MQTT at %s:%s", self.config.mqtt_host, self.config.mqtt_port)
        self.client.connect(self.config.mqtt_host, self.config.mqtt_port, keepalive=60)
        self.client.loop_start()

    def close(self) -> None:
        self.publish_availability(False)
        self.client.loop_stop()
        self.client.disconnect()

    def publish_availability(self, online: bool) -> None:
        self.client.publish(
            f"{self.config.bridge_id}/availability",
            "online" if online else "offline",
            retain=True,
        )

    def publish_discovery(self, devices: list[LarnitechDevice]) -> None:
        supported = 0
        unsupported = []

        for device in devices:
            topic = discovery_topic(
                self.config.mqtt_discovery_prefix,
                self.config.bridge_id,
                device,
            )
            payload = discovery_payload(self.config.bridge_id, device)

            if topic is None or payload is None:
                unsupported.append({"addr": device.addr, "name": device.name, "type": device.type})
                continue

            self.client.publish(topic, json.dumps(payload), retain=True)
            supported += 1

            command_topic = payload.get("command_topic")
            if command_topic:
                self._addr_by_command_topic[command_topic] = device.addr
                self.client.subscribe(command_topic)

        _LOGGER.info("Published MQTT discovery for %s supported devices", supported)

        if unsupported and self.config.publish_unsupported_devices:
            self.client.publish(
                f"{self.config.bridge_id}/diagnostics/unsupported_devices",
                json.dumps({"count": len(unsupported), "devices": unsupported}),
                retain=True,
            )
            _LOGGER.warning("Unsupported devices: %s", unsupported)

    def publish_status(self, status: DeviceStatus) -> None:
        topic = f"{self.config.bridge_id}/{slugify(status.addr)}/state"
        self.client.publish(topic, normalize_state(status.value), retain=True)
        self.client.publish(f"{topic}_raw", json.dumps(status.raw), retain=True)

    def _on_connect(self, client, userdata, flags, reason_code, properties) -> None:
        _LOGGER.info("Connected to MQTT: %s", reason_code)
        self.publish_availability(True)
        for command_topic in self._addr_by_command_topic:
            client.subscribe(command_topic)

    def _on_message(self, client, userdata, message) -> None:
        payload = message.payload.decode("utf-8")
        addr = self._addr_by_command_topic.get(message.topic)
        if addr is None:
            _LOGGER.debug("Ignoring MQTT message on unknown topic %s", message.topic)
            return

        _LOGGER.info("MQTT command: addr=%s payload=%s", addr, payload)
        self.command_callback(addr, payload)
