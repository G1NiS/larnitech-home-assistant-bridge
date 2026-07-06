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
    device = LarnitechDevice(addr="493:166", name="Virtuvės šviestuvai", type="dimmer-lamp", area="Virtuvė", raw={})
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
    device = LarnitechDevice(addr="999:1", name="Illumination", type="illumination-sensor", area="Setup", raw={})
    payload = discovery_payload("larnitech", device)
    assert payload is not None
    assert payload["device_class"] == "illuminance"
    assert payload["unit_of_measurement"] == "lx"


def test_normalize_dict_state():
    assert normalize_state({"state": "opened"}) == "ON"
    assert normalize_state({"state": "off"}) == "OFF"
    assert normalize_state({"state": 22.345}) == "22.34"


def test_object_id_is_address_stable():
    from larnitech_ha_bridge.discovery import object_id, legacy_object_id

    device = LarnitechDevice(addr="493:166", name="Virtuvės šviestuvai", type="dimmer-lamp", area="Virtuvė", raw={})
    assert object_id("larnitech", device) == "larnitech_493_166"
    assert legacy_object_id("larnitech", device) == "larnitech_493_166_virtuv_s_viestuvai"


def test_bridge_grouping_uses_single_device():
    device = LarnitechDevice(addr="493:166", name="Salos šviestuvai", type="dimmer-lamp", area="Virtuvė", raw={})
    payload = discovery_payload("larnitech", device, grouping="bridge", prefix_area=True)
    assert payload is not None
    assert payload["device"]["identifiers"] == ["larnitech_bridge"]
    assert payload["device"]["name"] == "Larnitech Smart House"
    assert payload["name"] == "Virtuvė · Salos šviestuvai"
