# Larnitech HA Bridge

Unofficial Home Assistant integration and add-on bridge for Larnitech-compatible smart home systems.

The project provides two installation paths:

1. **HACS custom integration** — recommended public/community path.
2. **Home Assistant add-on** — legacy/MQTT bridge path for users who prefer MQTT Discovery.

> This project is not affiliated with, endorsed by, or sponsored by Larnitech or Home Assistant.  
> Larnitech and Home Assistant are trademarks of their respective owners.

## Current status

Current HACS integration version: **0.1.27**  
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
Settings → Devices & services → Add integration → Larnitech HA Bridge
```

8. Enter the Larnitech host, API2 port and API2 key.

Example:

```text
Host: 192.168.xxx.xxx
API2 port: 2041
API2 key: your Larnitech API2 key
```

Do not include `http://`, `ws://`, or `/api` in the host field.
