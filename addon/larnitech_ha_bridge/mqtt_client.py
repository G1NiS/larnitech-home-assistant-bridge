from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import paho.mqtt.client as mqtt

from .commands import CommandKind
from .config import BridgeConfig
from .discovery import (
    component_discovery_topic,
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

    def _component_for_device(self, device: LarnitechDevice) -> str | None:
        return entity_component(device, fancoil_entity_mode=self.config.fancoil_entity_mode)

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
            component = self._component_for_device(device)
            topic = discovery_topic(
                self.config.mqtt_discovery_prefix,
                self.config.bridge_id,
                device,
                fancoil_entity_mode=self.config.fancoil_entity_mode,
            )
            old_topic = legacy_discovery_topic(
                self.config.mqtt_discovery_prefix,
                self.config.bridge_id,
                device,
                fancoil_entity_mode=self.config.fancoil_entity_mode,
            )

            if topic and component:
                all_supported_topics.add(topic)
            if old_topic and component:
                legacy_topics.add(old_topic)

            # Fancoils can be exposed as either fan or climate. Clear the opposite retained
            # MQTT discovery topic so Home Assistant does not keep stale duplicate entities.
            if device.type == "fancoil" and component:
                for stale_component in {"fan", "climate"} - {component}:
                    legacy_topics.add(
                        component_discovery_topic(
                            self.config.mqtt_discovery_prefix,
                            self.config.bridge_id,
                            device,
                            stale_component,
                        )
                    )

            if self.should_publish(device) and topic:
                current_topics.add(topic)

        self._cleanup_stale_discovery_topics(current_topics, all_supported_topics, legacy_topics)

        # Second pass: publish new grouped discovery payloads.
        for device in devices:
            topic = discovery_topic(
                self.config.mqtt_discovery_prefix,
                self.config.bridge_id,
                device,
                fancoil_entity_mode=self.config.fancoil_entity_mode,
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
                fancoil_entity_mode=self.config.fancoil_entity_mode,
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
            self._subscribe_entity_commands(device, payload)

        _LOGGER.info(
            "Published MQTT discovery for %s entities using "
            "device_grouping=%s, fancoil_entity_mode=%s",
            supported,
            self.config.device_grouping,
            self.config.fancoil_entity_mode,
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
            diagnostic_topics = self.publish_module_diagnostics(
                devices, published_devices=publishable, skipped=skipped, unsupported=unsupported
            )
            current_topics |= diagnostic_topics

        self._save_discovery_topics(current_topics)
        return publishable

    def _subscribe_entity_commands(
        self, device: LarnitechDevice, payload: dict[str, object]
    ) -> None:
        command_topic = payload.get("command_topic")
        if isinstance(command_topic, str):
            self._command_by_topic[command_topic] = (device.addr, "state")
            self.client.subscribe(command_topic)

        brightness_command_topic = payload.get("brightness_command_topic")
        if isinstance(brightness_command_topic, str):
            self._command_by_topic[brightness_command_topic] = (device.addr, "brightness")
            self.client.subscribe(brightness_command_topic)

        component = self._component_for_device(device)

        if component == "button":
            button_command_topic = payload.get("command_topic")
            if isinstance(button_command_topic, str):
                self._command_by_topic[button_command_topic] = (device.addr, "press")
                self.client.subscribe(button_command_topic)

        if component == "fan":
            fan_command_topics = (
                payload.get("preset_mode_command_topic"),
                payload.get("percentage_command_topic"),
            )
            for fan_command_topic in fan_command_topics:
                if isinstance(fan_command_topic, str):
                    self._command_by_topic[fan_command_topic] = (device.addr, "fan_mode")
                    self.client.subscribe(fan_command_topic)
            return

        if component == "climate":
            climate_command_topics: dict[str, CommandKind] = {
                "mode_command_topic": "mode",
                "fan_mode_command_topic": "fan_mode",
                "preset_mode_command_topic": "preset",
            }
            for payload_key, command_kind in climate_command_topics.items():
                climate_command_topic = payload.get(payload_key)
                if isinstance(climate_command_topic, str):
                    self._command_by_topic[climate_command_topic] = (device.addr, command_kind)
                    self.client.subscribe(climate_command_topic)

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
        for module_addr in sorted(
            modules, key=lambda value: int(value) if value.isdigit() else value
        ):
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
        self.client.publish(
            f"{self.config.bridge_id}/diagnostics/modules/state",
            str(len(normalized_modules)),
            retain=True,
        )
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
        self.client.publish(
            f"{self.config.bridge_id}/diagnostics/published_entities/state",
            str(len(published_devices)),
            retain=True,
        )
        self.client.publish(
            f"{self.config.bridge_id}/diagnostics/published_entities/attributes",
            json.dumps(
                {
                    "published": len(published_devices),
                    "skipped": len(skipped),
                    "unsupported": len(unsupported),
                    "device_grouping": self.config.device_grouping,
                    "fancoil_entity_mode": self.config.fancoil_entity_mode,
                }
            ),
            retain=True,
        )
        topics.add(topic)

        _LOGGER.info("Published module diagnostics for %s modules", len(normalized_modules))
        return topics

    def should_publish(self, device: LarnitechDevice) -> bool:
        area = device.area or ""
        component = self._component_for_device(device)

        if area in self.config.ignored_areas:
            return False

        if device.type in self.config.ignored_types:
            return False

        # Keep fancoils visible even when Larnitech reports them under the internal Setup area.
        if self.config.hide_setup_area and area.lower() == "setup" and device.type != "fancoil":
            return False

        if self.config.hide_input_switches and device.type == "switch":
            return False

        if device.type == "light-scheme" and not self.config.publish_light_schemes:
            return False

        if device.type == "script" and not self.config.publish_scripts:
            return False

        return component is not None

    def publish_initial_status(self, devices: list[LarnitechDevice]) -> None:
        published = 0
        for device in devices:
            component = self._component_for_device(device)
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

        if device and device.type == "fancoil":
            if self.config.fancoil_entity_mode == "climate":
                self._publish_fancoil_climate_status(topic_base, status)
            else:
                self._publish_fancoil_fan_status(topic_base, status)

    def _publish_fancoil_fan_status(self, topic_base: str, status: DeviceStatus) -> None:
        status_data = self._status_dict(status)
        fan_level = self._extract_numeric(status_data, "fan", "fan_level", "level")

        self.client.publish(
            f"{topic_base}/state",
            self._fancoil_state_from_status(status_data, fan_level),
            retain=True,
        )

        if fan_level is not None:
            fan_speed = self._fan_speed_from_level(fan_level)
            self.client.publish(
                f"{topic_base}/percentage/state",
                str(fan_speed),
                retain=True,
            )
            self.client.publish(
                f"{topic_base}/preset_mode/state",
                self._fan_preset_from_speed(fan_speed),
                retain=True,
            )

        self.client.publish(f"{topic_base}/attributes", json.dumps(status.raw), retain=True)

    def _publish_fancoil_climate_status(self, topic_base: str, status: DeviceStatus) -> None:
        status_data = self._status_dict(status)

        mode = self._extract_fancoil_mode(status_data)
        if mode:
            self.client.publish(f"{topic_base}/mode/state", mode, retain=True)

        current_temperature = self._extract_numeric(
            status_data,
            "current",
            "current_temperature",
            "temperature",
            "t_cur",
            "t-current",
        )
        if current_temperature is not None:
            self.client.publish(
                f"{topic_base}/current_temperature/state",
                str(current_temperature),
                retain=True,
            )

        target_temperature = self._extract_numeric(
            status_data,
            "target",
            "target_temperature",
            "setpoint",
            "t_set",
            "t-set",
            "temperature-level",
        )
        if target_temperature is not None:
            self.client.publish(
                f"{topic_base}/target_temperature/state",
                str(target_temperature),
                retain=True,
            )

        fan_level = self._extract_numeric(status_data, "fan", "fan_level", "level")
        if fan_level is not None:
            self.client.publish(
                f"{topic_base}/fan_mode/state",
                self._fan_preset_from_level(fan_level),
                retain=True,
            )

        preset = status_data.get("automation") or status_data.get("preset")
        if isinstance(preset, str) and preset.strip():
            self.client.publish(f"{topic_base}/preset/state", preset.strip(), retain=True)

        self.client.publish(f"{topic_base}/attributes", json.dumps(status.raw), retain=True)

    @staticmethod
    def _status_dict(status: DeviceStatus) -> dict[str, Any]:
        if isinstance(status.value, dict):
            return status.value

        raw_status = status.raw.get("status")
        if isinstance(raw_status, dict):
            return raw_status

        return status.raw

    @staticmethod
    def _fancoil_state_from_status(status_data: dict[str, Any], fan_level: float | None) -> str:
        state = str(status_data.get("state", "")).lower().strip()
        if state in {"off", "0", "false"}:
            return "OFF"
        if fan_level is not None:
            return "ON" if fan_level > 0 else "OFF"
        if state in {"on", "1", "true"}:
            return "ON"
        return "OFF"

    @staticmethod
    def _extract_fancoil_mode(status_data: dict[str, Any]) -> str | None:
        state = str(status_data.get("state", "")).lower().strip()
        if state in {"off", "0", "false"}:
            return "off"

        mode = str(status_data.get("mode", "")).lower().strip()
        if mode in {"heat", "cool"}:
            return mode

        if state in {"on", "1", "true"}:
            return "heat"

        return None

    @staticmethod
    def _extract_numeric(status_data: dict[str, Any], *keys: str) -> float | None:
        for key in keys:
            value = status_data.get(key)
            if value is None:
                continue
            try:
                return round(float(value), 2)
            except (TypeError, ValueError):
                continue
        return None

    @staticmethod
    def _fan_speed_from_level(level: float) -> int:
        if level <= 0:
            return 0
        if level > 100:
            if level <= 125:
                return 1
            if level <= 210:
                return 2
            return 3
        if level <= 40:
            return 1
        if level <= 75:
            return 2
        return 3

    @classmethod
    def _fan_preset_from_level(cls, level: float) -> str:
        return cls._fan_preset_from_speed(cls._fan_speed_from_level(level))

    @staticmethod
    def _fan_preset_from_speed(speed: int) -> str:
        if speed <= 0:
            return "off"
        if speed == 1:
            return "low"
        if speed == 2:
            return "medium"
        return "high"

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
        _LOGGER.info(
            "MQTT command: topic=%s addr=%s kind=%s payload=%s",
            message.topic,
            addr,
            kind,
            payload,
        )
        self.command_callback(addr, payload, kind)
