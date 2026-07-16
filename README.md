# Larnitech HA Bridge

Unofficial Home Assistant add-on bridge for Larnitech-compatible smart home systems.

It connects to **Larnitech API2 WebSocket**, reads devices/status updates, and publishes them to **Home Assistant through MQTT Discovery**.

> This project is not affiliated with, endorsed by, or sponsored by Larnitech or Home Assistant.  
> Larnitech and Home Assistant are trademarks of their respective owners.

## Current status

Current add-on version: **0.1.23**

This is an early community release. It is intended for users who are comfortable with Home Assistant add-ons, MQTT Discovery, and Larnitech API2 configuration.

### Current scope

- Connects to Larnitech API2 WebSocket.
- Requests the full device list.
- Subscribes to live status updates.
- Publishes Home Assistant MQTT Discovery entities.
- Groups all entities under one Home Assistant device by default.
- Filters internal `Setup` items and physical input switches by default.
- Forwards Home Assistant MQTT commands back to Larnitech.
- Supports lights and dimmers.
- Supports common sensors and binary sensors.
- Exposes Larnitech `fancoil` items as simple Home Assistant `fan` entities with **ON/OFF only**.
- Publishes optional module diagnostics.

Full release notes are maintained in [`addon/CHANGELOG.md`](addon/CHANGELOG.md).

## Supported items

| Larnitech type | Home Assistant entity | Control |
|---|---|---|
| `lamp` | `light` | ON/OFF |
| `dimmer-lamp` | `light` | ON/OFF + brightness |
| `switch` | `switch` | ON/OFF, hidden by default when used as input switches |
| `valve` | `switch` | ON/OFF |
| `valve-heating` | `switch` | ON/OFF |
| `temperature-sensor` | `sensor` | read-only |
| `humidity-sensor` | `sensor` | read-only |
| `illumination-sensor` | `sensor` | read-only |
| `motion-sensor` | `binary_sensor` | read-only |
| `door-sensor` | `binary_sensor` | read-only |
| `leak-sensor` | `binary_sensor` | read-only |
| `fancoil` | `fan` | ON/OFF only |
| `light-scheme` | `button` | optional, disabled by default |
| `script` | `button` | optional, disabled by default |

## Known limitations

- Fancoil Low / Medium / High speed control is **not advertised** in Home Assistant.
- Fancoils are intentionally exposed as simple ON/OFF fan entities.
- On the tested installation, Larnitech API2 accepted fancoil speed payloads but restored runtime speed back to `fan=100.0`; therefore speed control was removed from public discovery.
- Heat/cool mode for fancoils is not exposed as a Home Assistant `climate` entity in this public baseline.
- This add-on does not replace a full HVAC controller. Use Home Assistant automations or the native heating/cooling system for higher-level HVAC logic.

## Architecture

```text
Larnitech API2 WebSocket
        ↓
Larnitech HA Bridge add-on
        ↓
MQTT Discovery + MQTT state/command topics
        ↓
Home Assistant
```

The bridge uses two API2 WebSocket connections:

```text
status WebSocket  -> get-devices, status-subscribe, live status events
command WebSocket -> status-set commands from Home Assistant/MQTT
```

This avoids concurrent WebSocket receive calls and keeps command handling separated from the live status stream.

## Home Assistant add-on installation

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

## Example configuration

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

## Configuration options

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

## Device grouping modes

Default mode:

```yaml
device_grouping: "bridge"
prefix_entity_names_with_area: true
```

This creates one Home Assistant MQTT device named **Larnitech Smart House**. Entities are named with the room prefix, for example:

```text
Virtuvė · Salos šviestuvai
Tėvų WC · WC spot
Beno kambarys · LED
```

Alternative modes:

```yaml
device_grouping: "area"
```

Creates one Home Assistant device per Larnitech area/room.

```yaml
device_grouping: "entity"
```

Creates one Home Assistant device per Larnitech item.

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

The raw Larnitech status is still published as JSON attributes, so users can inspect the values returned by their installation.

## Diagnostics

When enabled:

```yaml
publish_module_diagnostics: true
```

The bridge publishes diagnostic sensors with discovered module information based on Larnitech address prefixes and cfgid values.

Useful diagnostic entities include:

```text
Larnitech Modules
Larnitech Published entities
```

## Updating from earlier test versions

After updating from versions that exposed fancoil speeds or climate entities:

1. Update the add-on to the latest version.
2. Restart the add-on.
3. Reload the Home Assistant MQTT integration.
4. If stale fancoil speed/climate entities remain, restart Home Assistant.
5. If needed, delete stale MQTT entities and let Discovery recreate them.

The add-on clears retained legacy MQTT discovery topics when `cleanup_legacy_mqtt: true` is enabled.

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

## License

Licensed under the Apache License, Version 2.0. See [`LICENSE`](LICENSE).

## Legal

This project is not affiliated with, endorsed by, or sponsored by Larnitech or Home Assistant. Product names and trademarks belong to their respective owners.
