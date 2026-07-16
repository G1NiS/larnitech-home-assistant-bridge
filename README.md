# Larnitech HA Bridge

Unofficial Home Assistant integration and add-on bridge for Larnitech-compatible smart home systems.

The project provides two public installation paths:

1. **HACS custom integration** — recommended public/community installation path.
2. **Home Assistant add-on** — legacy/MQTT bridge path for users who prefer MQTT Discovery.

> This project is not affiliated with, endorsed by, or sponsored by Larnitech or Home Assistant.  
> Larnitech and Home Assistant are trademarks of their respective owners.

## Current status

Current version: **0.1.23**

This is an early community release. It is intended for users who are comfortable with Home Assistant, HACS, local network integrations and Larnitech API2 configuration.

### Public Community Edition

The public HACS integration is free and does not require a license key.

Current public scope:

- Connects locally to Larnitech API2 WebSocket.
- Requests the full device list.
- Subscribes to live status updates.
- Creates native Home Assistant entities.
- Supports lights and dimmers.
- Supports common sensors and binary sensors.
- Supports valves and switches.
- Exposes Larnitech `fancoil` items as simple Home Assistant `fan` entities with **ON/OFF only**.

### Commercial support / monetization

The recommended monetization model is services around the public integration, not locking the baseline integration:

- paid installer support;
- remote setup and troubleshooting;
- Larnitech-to-Home Assistant mapping work;
- custom dashboards;
- HVAC logic design;
- project-specific diagnostics;
- priority support;
- optional future Pro/Installer package.

GitHub Sponsors metadata is included in `.github/FUNDING.yml`. Replace or extend it with the final sponsor/support links before public launch.

Full release notes are maintained in [`addon/CHANGELOG.md`](addon/CHANGELOG.md).

## HACS custom integration installation

1. Make the repository public.
2. Open Home Assistant.
3. Go to:

```text
HACS → Integrations → ⋮ → Custom repositories
```

4. Add this repository URL:

```text
https://github.com/G1NiS/larnitech-home-assistant-bridge
```

5. Select repository type:

```text
Integration
```

6. Download the integration.
7. Restart Home Assistant.
8. Go to:

```text
Settings → Devices & services → Add integration → Larnitech
```

9. Enter:

```text
Host
API2 port
API2 key
```

## HACS publishing checklist

The repository is structured for HACS as an integration repository:

```text
custom_components/larnitech/__init__.py
custom_components/larnitech/manifest.json
custom_components/larnitech/config_flow.py
README.md
hacs.json
```

Required HACS/HA metadata included:

- `hacs.json`
- `custom_components/larnitech/manifest.json`
- `custom_components/larnitech/strings.json`
- `custom_components/larnitech/translations/en.json`
- HACS validation GitHub Action
- Hassfest GitHub Action
- `info.md`
- funding metadata
- custom SVG brand icon draft in `brand/icon.svg`

Before submitting as a HACS default repository, add a binary `brand/icon.png`. The current repository contains a text-based SVG draft because binary PNG upload is not available through the current automation channel.

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

## Known limitations

- Fancoil Low / Medium / High speed control is **not advertised** in Home Assistant.
- Fancoils are intentionally exposed as simple ON/OFF fan entities.
- On the tested installation, Larnitech API2 accepted fancoil speed payloads but restored runtime speed back to `fan=100.0`; therefore speed control was removed from the public baseline.
- Heat/cool mode for fancoils is not exposed as a Home Assistant `climate` entity.
- This integration does not replace a full HVAC controller. Use Home Assistant automations or the native heating/cooling system for higher-level HVAC logic.

## Architecture — HACS integration

```text
Home Assistant custom integration
        ↓
Larnitech API2 WebSocket
        ↓
Larnitech controller
```

The HACS integration uses two API2 WebSocket connections:

```text
status WebSocket  -> get-devices, status-subscribe, live status events
command WebSocket -> status-set commands from Home Assistant entities
```

## Home Assistant add-on installation

The add-on/MQTT bridge is still available for users who prefer MQTT Discovery.

1. Open Home Assistant.
2. Go to:

```text
Settings → Add-ons → Add-on Store → ⋮ → Repositories
```

3. Add this repository URL:

```text
https://github.com/G1NiS/larnitech-home-assistant-bridge
```

4. Install **Larnitech Bridge for Home Assistant**.
5. Configure the add-on.
6. Start the add-on.
7. Make sure the MQTT integration is enabled in Home Assistant.

### Add-on example configuration

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

## Add-on configuration options

| Option | Default | Description |
|---|---:|---|
| `larnitech_host` | `larnitech.local` | Larnitech controller host or IP address. |
| `larnitech_port` | `2041` | Larnitech API2 WebSocket port. |
| `larnitech_api_key` | empty | Required API2 key. |
| `mqtt_host` | `core-mosquitto` | MQTT broker host. |
| `mqtt_port` | `1883` | MQTT broker port. |
| `mqtt_username` | empty | Optional MQTT username. |
| `mqtt_password` | empty | Optional MQTT password. |
| `mqtt_discovery_prefix` | `homeassistant` | Home Assistant MQTT Discovery prefix. |
| `bridge_id` | `larnitech` | MQTT topic prefix and unique ID prefix. |
| `log_level` | `info` | `debug`, `info`, `warning`, or `error`. |
| `device_grouping` | `bridge` | `bridge`, `area`, or `entity`. |
| `ignored_areas` | `[]` | Larnitech areas to skip. |
| `ignored_types` | `[]` | Larnitech item types to skip. |
| `hide_setup_area` | `true` | Hide internal `Setup` area items, except fancoils. |
| `hide_input_switches` | `true` | Hide physical input switches by default. |
| `publish_light_schemes` | `false` | Publish Larnitech light schemes as Home Assistant buttons. |
| `publish_scripts` | `false` | Publish Larnitech scripts as Home Assistant buttons. |
| `cleanup_legacy_mqtt` | `true` | Clear retained stale MQTT Discovery topics. |
| `prefix_entity_names_with_area` | `true` | Prefix entity names with Larnitech area when using bridge grouping. |
| `publish_module_diagnostics` | `true` | Publish diagnostic module summary sensors. |

## Fancoils

Larnitech `type="fancoil"` items are exposed as Home Assistant `fan` entities with only:

```text
ON
OFF
```

The current public baseline does not expose:

```text
Low / Medium / High
heat / cool mode
climate entity controls
```

Rationale: API2 speed writes were accepted by Larnitech but did not reliably change physical fan speed on the tested installation. The stable public behaviour is therefore ON/OFF only.

## Security notes

- Do not expose the Larnitech API2 port directly to the public internet.
- Do not commit or share your `logic.xml` if it contains API keys, camera URLs, credentials, or private IP addresses.
- Keep your Larnitech API key and MQTT credentials private.
- Use a VPN, Home Assistant remote access, or a properly secured reverse proxy when remote access is required.

## Development

This is a clean-room implementation. Do not copy code from existing proprietary or third-party bridges into this repository.

Install development dependencies:

```bash
pip install -e '.[dev]'
```

Run tests:

```bash
pytest
```

Run linting:

```bash
ruff check .
```
