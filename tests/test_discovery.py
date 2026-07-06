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


def test_normalize_bool():
    assert normalize_state(True) == "ON"
    assert normalize_state(False) == "OFF"
