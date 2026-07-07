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

Early MVP / debug version. Current add-on version: 0.1.13.

Current scope:

- Connect to Larnitech API2 WebSocket.
- Request device list.
- Subscribe to status updates.
- Publish Home Assistant MQTT Discovery entities.
- Group all Larnitech entities under one Home Assistant device by default.
- Filter internal Setup items and input switches by default.
- Forward MQTT commands back to Larnitech.
- Publish Larnitech fancoils as configurable Home Assistant `fan` or `climate` entities.

Full release notes are maintained in [`addon/CHANGELOG.md`](addon/CHANGELOG.md).

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
device_grouping: "bridge"
fancoil_entity_mode: "fan"
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

## Fancoil entity mode

Default mode for this installation:

```yaml
fancoil_entity_mode: "fan"
```

This exposes Larnitech fancoils as Home Assistant fan entities with 3 speeds:

```text
off     -> 0x00
low     -> 0x0155
medium  -> 0x01AA
high    -> 0x01FA
```

Alternative mode for pure-Larnitech installations:

```yaml
fancoil_entity_mode: "climate"
```

This exposes Larnitech fancoils as Home Assistant climate entities. It keeps HVAC mode, fan mode, preset mode and temperature topics when those values are available from Larnitech.

## Diagnostics

When enabled:

```yaml
publish_module_diagnostics: true
```

The bridge publishes diagnostic sensors with discovered module information based on Larnitech address prefixes and cfgid values.

## 0.1.13 configurable fancoil mode

- Adds `fancoil_entity_mode: fan|climate`.
- Keeps `fan` as default because the current installation controls heating/cooling through Nibe and uses Larnitech fancoils as 3-speed fan coils.
- Keeps `climate` mode available for users who use only Larnitech for fancoil climate control.
- Clears stale MQTT Discovery topics when switching fancoils between `fan` and `climate`.

## 0.1.12 fancoils as 3-speed fan entities

- Changes `type="fancoil"` from Home Assistant `climate` to Home Assistant `fan` by default.
- Removes fake fancoil temperature and heat/cool mode topics from default discovery.
- Publishes fancoil speed as fan preset mode: `off`, `low`, `medium`, `high`.
- Maps real 3-speed commands:
  - `off` -> `0x00`
  - `low` / speed 1 -> `0x0155`
  - `medium` / speed 2 -> `0x01AA`
  - `high` / speed 3 -> `0x01FA`

## 0.1.11 fancoil command payload fix

- Changes fancoil HVAC mode and fan commands from JSON objects to Larnitech-style hex status values.
- `off` sends `0x00`.
- Fan mode sends two-byte commands: first byte is on/off, second byte is fancoil fan power scaled to the Larnitech 0..250 range.

## 0.1.10 Larnitech WebSocket keepalive fix

- Disables Python WebSocket protocol pings to avoid Larnitech `keepalive ping timeout` disconnect loops.
- Keeps reconnect logic in place for real connection/request failures.
- Adds a short close timeout so a broken socket does not block reconnecting.

## 0.1.9 fancoil climate support

- Adds initial `type="fancoil"` support as Home Assistant MQTT `climate` entities.
- Replaced by configurable `fan|climate` mode in 0.1.13.

## 0.1.7 faster, lossless reconnects

- A dropped connection now reconnects immediately instead of always waiting out the backoff delay.
- A command that was in flight when the command connection died is put back on the queue and retried once reconnected.

## 0.1.6 connection resilience

Both the status and command WebSocket connections reconnect automatically with exponential backoff if the connection to Larnitech drops.

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
