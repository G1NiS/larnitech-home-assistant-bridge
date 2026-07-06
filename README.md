# Larnitech HA Bridge

Unofficial Home Assistant bridge for Larnitech-compatible smart home systems using API2 WebSocket and MQTT Discovery.

> This project is not affiliated with, endorsed by, or sponsored by Larnitech or Home Assistant.
> Larnitech and Home Assistant are trademarks of their respective owners.

## Editions

### Community Edition

Free and open-source bridge for Larnitech-compatible systems and Home Assistant.

### Pro / Installer Edition

Planned commercial extension with advanced diagnostics, mapping UI, installer tools and priority support.

## Status

Early MVP / debug version. Current add-on version: 0.1.7.

Current scope:

- Connect to Larnitech API2 WebSocket.
- Request device list.
- Subscribe to status updates.
- Publish Home Assistant MQTT Discovery entities.
- Group all Larnitech entities under one Home Assistant device by default.
- Filter internal Setup items and input switches by default.
- Forward MQTT commands back to Larnitech.

## Architecture

```text
Larnitech API2 WebSocket
        ↓
Larnitech HA Bridge
        ↓
MQTT Discovery + MQTT state/command topics
        ↓
Home Assistant
```

## Home Assistant add-on install

1. Push this repository to GitHub.
2. In Home Assistant, open:

```text
Settings → Add-ons → Add-on Store → ⋮ → Repositories
```

3. Add your GitHub repository URL.
4. Install **Larnitech Bridge for Home Assistant**.
5. Configure:

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
log_level: "debug"
ignored_areas: []
ignored_types: []
publish_unsupported_devices: true
```

## Legal

This project is written as a clean-room implementation. Do not copy code from existing bridges into this repository.


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

Legacy mode: one Home Assistant device per Larnitech item.

## Diagnostics

When enabled:

```yaml
publish_module_diagnostics: true
```

The bridge publishes diagnostic sensors with discovered module information based on Larnitech address prefixes and cfgid values.


## 0.1.5 command flow

The bridge uses two Larnitech API2 WebSocket connections:

```text
status WebSocket  -> get-devices, status-subscribe, live status events
command WebSocket -> status-set commands from Home Assistant/MQTT
```

This avoids concurrent `recv()` calls on the same WebSocket connection and makes command testing easier.

Supported control commands:

```text
lamp / dimmer-lamp / switch / valve / valve-heating:
  ON  -> {"state": "on"}
  OFF -> {"state": "off"}

dimmer-lamp brightness:
  0..100 -> {"level": value}

button/script/light-scheme:
  PRESS -> "0xFF"
```

## 0.1.6 connection resilience

Both the status and command WebSocket connections now reconnect automatically with
exponential backoff (5s up to 60s) if the connection to Larnitech drops. Previously a
dropped connection silently stopped status updates and/or commands until the add-on
was restarted manually.

## 0.1.7 faster, lossless reconnects

- A dropped connection now reconnects immediately instead of always waiting out the
  backoff delay - the delay only applies when the reconnect attempt itself fails, so a
  one-off blip recovers as fast as a fresh WebSocket handshake instead of stalling for
  5+ seconds.
- A command that was in flight when the command connection died is put back on the
  queue and retried once reconnected, instead of being silently dropped.
