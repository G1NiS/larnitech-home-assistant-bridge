from __future__ import annotations

import json
import logging
from collections.abc import Callable
from pathlib import Path

import paho.mqtt.client as mqtt

from .config import BridgeConfig
from .discovery import discovery_payload, discovery_topic, entity_component, normalize_state, slugify
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
        self._discovery_state_path = Path("/data/discovery_topics.json")

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

    def publish_discovery(self, devices: list[LarnitechDevice]) -> list[LarnitechDevice]:
        publishable = [device for device in devices if self.should_publish(device)]

        current_topics: set[str] = set()
        all_supported_topics: set[str] = set()
        supported = 0
        skipped: list[dict[str, str | None]] = []
        unsupported: list[dict[str, str | None]] = []

        for device in devices:
            topic = discovery_topic(
                self.config.mqtt_discovery_prefix,
                self.config.bridge_id,
                device,
            )

            if topic and entity_component(device):
                all_supported_topics.add(topic)

            if not self.should_publish(device):
                skipped.append(
                    {
                        "addr": device.addr,
                        "name": device.name,
                        "type": device.type,
                        "area": device.area,
                    }
                )
                continue

            payload = discovery_payload(
                self.config.bridge_id,
                device,
                grouping=self.config.device_grouping,
            )

            if topic is None or payload is None:
                unsupported.append(
                    {
                        "addr": device.addr,
                        "name": device.name,
                        "type": device.type,
                        "area": device.area,
                    }
                )
                continue

            self.client.publish(topic, json.dumps(payload), retain=True)
            current_topics.add(topic)
            supported += 1

            command_topic = payload.get("command_topic")
            if command_topic:
                self._addr_by_command_topic[command_topic] = device.addr
                self.client.subscribe(command_topic)

        self._cleanup_stale_discovery_topics(current_topics, all_supported_topics)

        _LOGGER.info(
            "Published MQTT discovery for %s entities using device_grouping=%s",
            supported,
            self.config.device_grouping,
        )
        _LOGGER.info("Skipped %s filtered Larnitech items", len(skipped))

        if unsupported and self.config.publish_unsupported_devices:
            self.client.publish(
                f"{self.config.bridge_id}/diagnostics/unsupported_devices",
                json.dumps({"count": len(unsupported), "devices": unsupported}),
                retain=True,
            )
            _LOGGER.warning("Unsupported devices: %s", unsupported)

        if self.config.publish_unsupported_devices:
            self.client.publish(
                f"{self.config.bridge_id}/diagnostics/skipped_devices",
                json.dumps({"count": len(skipped), "devices": skipped}),
                retain=True,
            )

        self._save_discovery_topics(current_topics)
        return publishable

    def should_publish(self, device: LarnitechDevice) -> bool:
        area = device.area or ""

        if area in self.config.ignored_areas:
            return False

        if device.type in self.config.ignored_types:
            return False

        if self.config.hide_setup_area and area.lower() == "setup":
            return False

        if self.config.hide_input_switches and device.type == "switch":
            return False

        if device.type == "light-scheme" and not self.config.publish_light_schemes:
            return False

        if device.type == "script" and not self.config.publish_scripts:
            return False

        return entity_component(device) is not None

    def publish_initial_status(self, devices: list[LarnitechDevice]) -> None:
        published = 0
        for device in devices:
            component = entity_component(device)
            if component == "button":
                continue

            status = device.raw.get("status")
            if status is None:
                continue

            self.publish_status(DeviceStatus(addr=device.addr, value=status, raw=device.raw))
            published += 1

        _LOGGER.info("Published initial MQTT state for %s entities", published)

    def publish_status(self, status: DeviceStatus) -> None:
        topic = f"{self.config.bridge_id}/{slugify(status.addr)}/state"
        self.client.publish(topic, normalize_state(status.value), retain=True)
        self.client.publish(f"{topic}_raw", json.dumps(status.raw), retain=True)

    def _cleanup_stale_discovery_topics(
        self,
        current_topics: set[str],
        all_supported_topics: set[str],
    ) -> None:
        previous_topics = self._load_discovery_topics()

        # Clear topics that used to exist but are no longer published.
        # Also clear current-device topics that are now filtered out by v0.1.2 rules.
        stale_topics = (previous_topics | all_supported_topics) - current_topics

        for topic in stale_topics:
            self.client.publish(topic, "", retain=True)

        if stale_topics:
            _LOGGER.info("Cleared %s stale/filtered MQTT discovery topics", len(stale_topics))

    def _load_discovery_topics(self) -> set[str]:
        try:
            if not self._discovery_state_path.exists():
                return set()
            data = json.loads(self._discovery_state_path.read_text(encoding="utf-8"))
            return set(data.get("topics", []))
        except Exception:
            _LOGGER.exception("Failed to load MQTT discovery state")
            return set()

    def _save_discovery_topics(self, topics: set[str]) -> None:
        try:
            self._discovery_state_path.parent.mkdir(parents=True, exist_ok=True)
            self._discovery_state_path.write_text(
                json.dumps({"topics": sorted(topics)}, indent=2),
                encoding="utf-8",
            )
        except Exception:
            _LOGGER.exception("Failed to save MQTT discovery state")

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
