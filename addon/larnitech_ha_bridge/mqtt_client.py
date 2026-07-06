from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from pathlib import Path
from typing import Literal

import paho.mqtt.client as mqtt

from .config import BridgeConfig
from .discovery import (
    diagnostics_sensor_payload,
    discovery_payload,
    discovery_topic,
    entity_component,
    legacy_discovery_topic,
    normalize_state,
    slugify,
)
from .models import DeviceStatus, LarnitechDevice

_LOGGER = logging.getLogger(__name__)

CommandKind = Literal["state", "brightness", "press"]


class MqttBridgeClient:
    def __init__(
        self,
        config: BridgeConfig,
        command_callback: Callable[[str, str, CommandKind], None],
    ) -> None:
        self.config = config
        self.command_callback = command_callback
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        if config.mqtt_username:
            self.client.username_pw_set(config.mqtt_username, config.mqtt_password)

        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self._command_by_topic: dict[str, tuple[str, CommandKind]] = {}
        self._devices_by_addr: dict[str, LarnitechDevice] = {}
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
        self._devices_by_addr = {device.addr: device for device in publishable}

        current_topics: set[str] = set()
        all_supported_topics: set[str] = set()
        legacy_topics: set[str] = set()
        supported = 0
        skipped: list[dict[str, str | None]] = []
        unsupported: list[dict[str, str | None]] = []

        # First pass: calculate current and legacy topics.
        for device in devices:
            topic = discovery_topic(
                self.config.mqtt_discovery_prefix,
                self.config.bridge_id,
                device,
            )
            old_topic = legacy_discovery_topic(
                self.config.mqtt_discovery_prefix,
                self.config.bridge_id,
                device,
            )

            if topic and entity_component(device):
                all_supported_topics.add(topic)
            if old_topic and entity_component(device):
                legacy_topics.add(old_topic)

            if self.should_publish(device) and topic:
                current_topics.add(topic)

        self._cleanup_stale_discovery_topics(current_topics, all_supported_topics, legacy_topics)

        # Second pass: publish new grouped discovery payloads.
        for device in devices:
            topic = discovery_topic(
                self.config.mqtt_discovery_prefix,
                self.config.bridge_id,
                device,
            )

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
                prefix_area=self.config.prefix_entity_names_with_area,
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
            supported += 1

            command_topic = payload.get("command_topic")
            if command_topic:
                self._command_by_topic[command_topic] = (device.addr, "state")
                self.client.subscribe(command_topic)

            brightness_command_topic = payload.get("brightness_command_topic")
            if brightness_command_topic:
                self._command_by_topic[brightness_command_topic] = (device.addr, "brightness")
                self.client.subscribe(brightness_command_topic)

            if entity_component(device) == "button":
                button_command_topic = payload.get("command_topic")
                if button_command_topic:
                    self._command_by_topic[button_command_topic] = (device.addr, "press")
                    self.client.subscribe(button_command_topic)

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

        if self.config.publish_module_diagnostics:
            diagnostic_topics = self.publish_module_diagnostics(devices, publishable, skipped, unsupported)
            current_topics |= diagnostic_topics

        self._save_discovery_topics(current_topics)
        return publishable

    def publish_module_diagnostics(
        self,
        devices: list[LarnitechDevice],
        published_devices: list[LarnitechDevice],
        skipped: list[dict[str, str | None]],
        unsupported: list[dict[str, str | None]],
    ) -> set[str]:
        modules: dict[str, dict[str, object]] = {}

        for device in devices:
            if ":" not in device.addr:
                continue

            module_addr = device.addr.split(":", 1)[0]
            raw = device.raw or {}
            module = modules.setdefault(
                module_addr,
                {
                    "module": module_addr,
                    "cfgids": set(),
                    "types": {},
                    "areas": set(),
                    "items": 0,
                },
            )

            module["items"] = int(module["items"]) + 1

            cfgid = raw.get("cfgid")
            if cfgid is not None:
                module["cfgids"].add(str(cfgid))

            if device.type:
                types = module["types"]
                types[device.type] = int(types.get(device.type, 0)) + 1

            if device.area:
                module["areas"].add(device.area)

        normalized_modules: list[dict[str, object]] = []
        for module_addr in sorted(modules, key=lambda value: int(value) if value.isdigit() else value):
            module = modules[module_addr]
            cfgids = sorted(module["cfgids"])
            areas = sorted(module["areas"])
            normalized_modules.append(
                {
                    "module": module_addr,
                    "model": f"cfgid {', '.join(cfgids)}" if cfgids else "unknown",
                    "cfgids": cfgids,
                    "areas": areas,
                    "items": module["items"],
                    "types": module["types"],
                }
            )

        topics: set[str] = set()

        discovery_suffix, payload = diagnostics_sensor_payload(
            self.config.bridge_id,
            "modules",
            "Modules",
        )
        topic = f"{self.config.mqtt_discovery_prefix}/{discovery_suffix}"
        self.client.publish(topic, json.dumps(payload), retain=True)
        self.client.publish(f"{self.config.bridge_id}/diagnostics/modules/state", str(len(normalized_modules)), retain=True)
        self.client.publish(
            f"{self.config.bridge_id}/diagnostics/modules/attributes",
            json.dumps({"modules": normalized_modules}),
            retain=True,
        )
        topics.add(topic)

        discovery_suffix, payload = diagnostics_sensor_payload(
            self.config.bridge_id,
            "published_entities",
            "Published entities",
        )
        topic = f"{self.config.mqtt_discovery_prefix}/{discovery_suffix}"
        self.client.publish(topic, json.dumps(payload), retain=True)
        self.client.publish(f"{self.config.bridge_id}/diagnostics/published_entities/state", str(len(published_devices)), retain=True)
        self.client.publish(
            f"{self.config.bridge_id}/diagnostics/published_entities/attributes",
            json.dumps(
                {
                    "published": len(published_devices),
                    "skipped": len(skipped),
                    "unsupported": len(unsupported),
                    "device_grouping": self.config.device_grouping,
                }
            ),
            retain=True,
        )
        topics.add(topic)

        _LOGGER.info("Published module diagnostics for %s modules", len(normalized_modules))
        return topics

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
        topic_base = f"{self.config.bridge_id}/{slugify(status.addr)}"
        state_topic = f"{topic_base}/state"
        self.client.publish(state_topic, normalize_state(status.value), retain=True)
        self.client.publish(f"{state_topic}_raw", json.dumps(status.raw), retain=True)

        device = self._devices_by_addr.get(status.addr)
        if device and device.type == "dimmer-lamp":
            level = self._extract_level(status.value)
            if level is not None:
                self.client.publish(f"{topic_base}/brightness/state", str(level), retain=True)

    @staticmethod
    def _extract_level(value) -> int | None:
        if not isinstance(value, dict):
            return None
        raw_level = value.get("level")
        if raw_level is None:
            return None
        try:
            level = float(raw_level)
        except (TypeError, ValueError):
            return None
        return max(0, min(100, int(round(level))))

    def _cleanup_stale_discovery_topics(
        self,
        current_topics: set[str],
        all_supported_topics: set[str],
        legacy_topics: set[str],
    ) -> None:
        previous_topics = self._load_discovery_topics()

        stale_topics = (previous_topics | all_supported_topics) - current_topics

        if self.config.cleanup_legacy_mqtt:
            stale_topics |= legacy_topics

        for topic in stale_topics:
            self.client.publish(topic, "", retain=True)

        if stale_topics:
            _LOGGER.info("Cleared %s stale/legacy MQTT discovery topics", len(stale_topics))
            time.sleep(2)

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
        for command_topic in self._command_by_topic:
            client.subscribe(command_topic)

    def _on_message(self, client, userdata, message) -> None:
        payload = message.payload.decode("utf-8")
        command = self._command_by_topic.get(message.topic)
        if command is None:
            _LOGGER.debug("Ignoring MQTT message on unknown topic %s", message.topic)
            return

        addr, kind = command
        _LOGGER.info("MQTT command: addr=%s kind=%s payload=%s", addr, kind, payload)
        self.command_callback(addr, payload, kind)
