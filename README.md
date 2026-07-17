# Larnitech HA Bridge

Unofficial Home Assistant integration and add-on bridge for Larnitech-compatible smart home systems.

The project provides two installation paths:

1. **HACS custom integration** — recommended public/community path.
2. **Home Assistant add-on** — legacy/MQTT bridge path for users who prefer MQTT Discovery.

> This project is not affiliated with, endorsed by, or sponsored by Larnitech or Home Assistant.  
> Larnitech and Home Assistant are trademarks of their respective owners.

## Current status

Current HACS integration version: **0.1.25**  
Current Home Assistant add-on version: **0.1.23**

The public HACS integration is free and does not require a license key.

Current public scope:

- Local Larnitech API2 WebSocket connection.
- Native Home Assistant entities.
- Lights and dimmers.
- Common sensors and binary sensors.
- Valves and switches.
- Larnitech `fancoil` items as simple Home Assistant `fan` entities with **ON/OFF only**.

Release notes are maintained in [`CHANGELOG.md`](CHANGELOG.md). Add-on-specific release notes are in [`addon/CHANGELOG.md`](addon/CHANGELOG.md).

## HACS custom integration installation

1. Open HACS in Home Assistant.
2. Go to:

```text
HACS → Integrations → ⋮ → Custom repositories
```

3. Add this repository URL:

```text
https://github.com/G1NiS/larnitech-home-assistant-bridge
```

4. Select repository type:

```text
Integration
```

5. Download the integration.
6. Restart Home Assistant.
7. Go to:

```text
Settings → Devices & services → Add integration → Larnitech
```

8. Enter the Larnitech host, API2 port and API2 key.

Use only the host name or IP address in the host field. Do not include `http://` or `/api`.

```text
Host: 192.168.xxx.xxx
Port: 2041
API2 key: your Larnitech API2 key
```

The config flow also accepts `http://host`, `ws://host` and `host:port` and normalizes them internally, but the recommended input is host/IP only.

## HACS publishing checklist

Repository structure:

```text
custom_components/larnitech/__init__.py
custom_components/larnitech/manifest.json
custom_components/larnitech/config_flow.py
README.md
hacs.json
```

Included metadata and validation:

- `hacs.json`
- `custom_components/larnitech/manifest.json`
- `custom_components/larnitech/strings.json`
- `custom_components/larnitech/translations/en.json`
- `.github/workflows/validate-hacs.yml`
- `.github/workflows/hassfest.yml`
- `info.md`
- `brand/icon.png`
- `custom_components/larnitech/brand/icon.png`
- `custom_components/larnitech/brand/logo.png`

## Supported items

| Larnitech type | Home Assistant entity | Control |
|---|---|---|
| `lamp` | `light` | ON/OFF |
| `dimmer-lamp` | `light` | ON/OFF + brightness |
| `switch` | `switch` | ON/OFF |
| `valve` | `switch` | ON/OFF |
| `valve-heating` | `switch` | ON/OFF |
| `temperature-sensor` | `sensor` | read-only |
| `humidity-sensor` | `sensor` | read-only |
| `illumination-sensor` | `sensor` | read-only |
| `motion-sensor` | `binary_sensor` | read-only |
| `door-sensor` | `binary_sensor` | read-only |
| `leak-sensor` | `binary_sensor` | read-only |
| `fancoil` | `fan` | ON/OFF only |

## Fancoils

Larnitech `type="fancoil"` items are exposed as Home Assistant `fan` entities with only:

```text
ON
OFF
```

The public baseline does not expose:

```text
Low / Medium / High
heat / cool mode
climate entity controls
```

Rationale: API2 speed writes were accepted by Larnitech but did not reliably change physical fan speed on the tested installation. The stable public behaviour is ON/OFF only.

## Add-on / MQTT bridge

The Home Assistant add-on remains available for users who prefer MQTT Discovery.

Add-on repository URL:

```text
https://github.com/G1NiS/larnitech-home-assistant-bridge
```

Example add-on configuration:

```yaml
larnitech_host: "192.168.xxx.xxx"
larnitech_port: 2041
larnitech_api_key: "YOUR_API_KEY"
mqtt_host: "core-mosquitto"
mqtt_port: 1883
mqtt_username: "YOUR_MQTT_USER"
mqtt_password: "YOUR_MQTT_PASSWORD"
mqtt_discovery_prefix: "homeassistant"
bridge_id: "larnitech"
log_level: "info"
device_grouping: "bridge"
ignored_areas: []
ignored_types: []
hide_setup_area: true
hide_input_switches: true
publish_light_schemes: false
publish_scripts: false
cleanup_legacy_mqtt: true
prefix_entity_names_with_area: true
publish_module_diagnostics: true
```

## Security notes

- Do not expose the Larnitech API2 port directly to the public internet.
- Do not commit or share `logic.xml` if it contains API keys, camera URLs, credentials, or private IP addresses.
- Keep your Larnitech API key and MQTT credentials private.
- Use VPN or properly secured Home Assistant remote access when remote access is required.

## Development

```bash
pip install -e '.[dev]'
pytest
ruff check .
```
