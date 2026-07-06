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

Early MVP / debug version. Current add-on version: 0.1.1.

Current scope:

- Connect to Larnitech API2 WebSocket.
- Request device list.
- Subscribe to status updates.
- Publish basic Home Assistant MQTT Discovery entities.
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
