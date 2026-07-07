from larnitech_ha_bridge.discovery import discovery_payload, entity_component, normalize_state
from larnitech_ha_bridge.models import LarnitechDevice


def test_lamp_maps_to_light():
    device = LarnitechDevice(addr="1:2", name="Kitchen", type="lamp", area="Kitchen", raw={})
    assert entity_component(device) == "light"


def test_discovery_payload_has_topics():
    device = LarnitechDevice(addr="1:2", name="Kitchen", type="lamp", area="Kitchen", raw={})
    payload = discovery_payload("larnitech", device)
    assert payload is not None
    assert payload["command_topic"].endswith("/set")
    assert payload["state_topic"].endswith("/state")


def test_area_grouping_uses_area_device_identifier():
    device = LarnitechDevice(
        addr="493:166",
        name="Virtuvės šviestuvai",
        type="dimmer-lamp",
        area="Virtuvė",
        raw={},
    )
    payload = discovery_payload("larnitech", device, grouping="area")
    assert payload is not None
    assert payload["device"]["identifiers"] == ["larnitech_area_virtuv"]
    assert payload["device"]["name"] == "Larnitech - Virtuvė"


def test_door_sensor_maps_to_binary_sensor():
    device = LarnitechDevice(addr="415:25", name="Door", type="door-sensor", area="Setup", raw={})
    assert entity_component(device) == "binary_sensor"
    payload = discovery_payload("larnitech", device)
    assert payload is not None
    assert payload["device_class"] == "door"


def test_illumination_sensor_maps_to_sensor():
    device = LarnitechDevice(
        addr="999:1",
        name="Illumination",
        type="illumination-sensor",
        area="Setup",
        raw={},
    )
    payload = discovery_payload("larnitech", device)
    assert payload is not None
    assert payload["device_class"] == "illuminance"
    assert payload["unit_of_measurement"] == "lx"


def test_fancoil_maps_to_fan_by_default():
    device = LarnitechDevice(
        addr="415:52",
        name="Miegamasis",
        type="fancoil",
        area="Setup",
        raw={"status": {"state": "on", "fan": 33.2}},
    )

    assert entity_component(device) == "fan"
    payload = discovery_payload("larnitech", device)

    assert payload is not None
    assert payload["command_topic"] == "larnitech/415_52/set"
    assert payload["state_topic"] == "larnitech/415_52/state"
    assert payload["preset_mode_command_topic"] == "larnitech/415_52/preset_mode/set"
    assert payload["preset_mode_state_topic"] == "larnitech/415_52/preset_mode/state"
    assert payload["percentage_command_topic"] == "larnitech/415_52/percentage/set"
    assert payload["percentage_state_topic"] == "larnitech/415_52/percentage/state"
    assert payload["speed_range_min"] == 1
    assert payload["speed_range_max"] == 3
    assert payload["preset_modes"] == ["off", "low", "medium", "high"]
    assert "current_temperature_topic" not in payload
    assert "mode_command_topic" not in payload


def test_fancoil_can_map_to_climate_when_configured():
    device = LarnitechDevice(
        addr="415:52",
        name="Miegamasis",
        type="fancoil",
        area="Setup",
        raw={
            "automations": ["Mode", "Comfort", "Off", "Eco", "Fast"],
            "status": {"state": "on", "current": 23.1, "fan": 33.2, "mode": "heat"},
        },
    )

    assert entity_component(device, fancoil_entity_mode="climate") == "climate"
    payload = discovery_payload("larnitech", device, fancoil_entity_mode="climate")

    assert payload is not None
    assert payload["mode_command_topic"] == "larnitech/415_52/mode/set"
    assert payload["mode_state_topic"] == "larnitech/415_52/mode/state"
    assert payload["current_temperature_topic"] == "larnitech/415_52/current_temperature/state"
    assert payload["fan_mode_command_topic"] == "larnitech/415_52/fan_mode/set"
    assert payload["fan_modes"] == ["off", "low", "medium", "high"]
    assert payload["preset_modes"] == ["Mode", "Comfort", "Off", "Eco", "Fast"]


def test_normalize_dict_state():
    assert normalize_state({"state": "opened"}) == "ON"
    assert normalize_state({"state": "off"}) == "OFF"
    assert normalize_state({"state": 22.345}) == "22.34"


def test_object_id_is_address_stable():
    from larnitech_ha_bridge.discovery import legacy_object_id, object_id

    device = LarnitechDevice(
        addr="493:166",
        name="Virtuvės šviestuvai",
        type="dimmer-lamp",
        area="Virtuvė",
        raw={},
    )
    assert object_id("larnitech", device) == "larnitech_493_166"
    assert legacy_object_id("larnitech", device) == "larnitech_493_166_virtuv_s_viestuvai"


def test_bridge_grouping_uses_single_device():
    device = LarnitechDevice(
        addr="493:166",
        name="Salos šviestuvai",
        type="dimmer-lamp",
        area="Virtuvė",
        raw={},
    )
    payload = discovery_payload("larnitech", device, grouping="bridge", prefix_area=True)
    assert payload is not None
    assert payload["device"]["identifiers"] == ["larnitech_bridge"]
    assert payload["device"]["name"] == "Larnitech Smart House"
    assert payload["name"] == "Virtuvė · Salos šviestuvai"


def test_dimmer_discovery_has_brightness_topics():
    device = LarnitechDevice(
        addr="493:118",
        name="Lempa",
        type="dimmer-lamp",
        area="Darbo kambarys",
        raw={},
    )
    payload = discovery_payload("larnitech", device, grouping="bridge", prefix_area=True)
    assert payload is not None
    assert payload["brightness_command_topic"] == "larnitech/493_118/brightness/set"
    assert payload["brightness_state_topic"] == "larnitech/493_118/brightness/state"
    assert payload["brightness_scale"] == 100


def test_command_payload_for_lamp_on_off():
    from larnitech_ha_bridge.commands import larnitech_status_for_command

    device = LarnitechDevice(addr="406:7", name="Kiemas", type="lamp", area="Namas", raw={})
    assert larnitech_status_for_command(device, "ON", "state") == {"state": "on"}
    assert larnitech_status_for_command(device, "OFF", "state") == {"state": "off"}


def test_command_payload_for_dimmer_brightness():
    from larnitech_ha_bridge.commands import larnitech_status_for_command

    device = LarnitechDevice(
        addr="493:118",
        name="Lempa",
        type="dimmer-lamp",
        area="Darbo kambarys",
        raw={},
    )
    assert larnitech_status_for_command(device, "42", "brightness") == {"level": 42}


def test_command_payload_for_fancoil_three_speeds():
    from larnitech_ha_bridge.commands import larnitech_status_for_command

    device = LarnitechDevice(
        addr="415:52",
        name="Miegamasis",
        type="fancoil",
        area="Setup",
        raw={},
    )
    assert larnitech_status_for_command(device, "OFF", "state") == {"state": "off"}
    assert larnitech_status_for_command(device, "ON", "state") == {"state": "on"}
    assert larnitech_status_for_command(device, "low", "fan_mode") == {"state": "on", "fan": 33.0}
    assert larnitech_status_for_command(device, "medium", "fan_mode") == {"state": "on", "fan": 66.0}
    assert larnitech_status_for_command(device, "high", "fan_mode") == {"state": "on", "fan": 100.0}
    assert larnitech_status_for_command(device, "1", "preset") == {"state": "on", "fan": 33.0}
    assert larnitech_status_for_command(device, "2", "preset") == {"state": "on", "fan": 66.0}
    assert larnitech_status_for_command(device, "3", "preset") == {"state": "on", "fan": 100.0}
    assert larnitech_status_for_command(device, "0", "fan_mode") == {"state": "off", "fan": 0.0}
