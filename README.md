# Larnitech HA Bridge

Unofficial Home Assistant integration and add-on bridge for Larnitech-compatible smart home systems.

Larnitech HA Bridge connects Home Assistant to a local Larnitech API2 WebSocket controller and exposes Larnitech items as native Home Assistant entities. The goal is to keep the public integration simple, local-first and usable for real installations without requiring cloud access or a license key.

> This project is not affiliated with, endorsed by, or sponsored by Larnitech or Home Assistant.  
> Larnitech and Home Assistant are trademarks of their respective owners.

## Installation paths

1. **HACS custom integration** — recommended public/community path.
2. **Home Assistant add-on** — legacy/MQTT Discovery bridge path for users who prefer MQTT.

## Current status

Current HACS integration version: **0.1.31**  
Current Home Assistant add-on version: **0.1.23**

The public HACS integration is free and does not require a license key.

## Features

- Local Larnitech API2 WebSocket connection.
- Native Home Assistant config flow.
- Lights and dimmers as Home Assistant `light` entities.
- Common sensors and binary sensors.
- Valves as Home Assistant `switch` entities.
- Larnitech `fancoil` items as simple Home Assistant `fan` entities with **ON/OFF only**.
- Room/area-based device grouping using the Larnitech structure when area information is available.
- Optional area overrides for items that Larnitech reports under `Setup` but should appear in a real room.
- Setup/unassigned items are exposed under a dedicated `Setup` area device.
- Larnitech light schemes are exposed as buttons under a dedicated `Light groups` device.
- Generic Larnitech `switch` inputs are hidden by default to avoid exposing wall buttons / inactive low-level inputs as HA controls.

## Entity mapping

| Larnitech item type | Home Assistant entity |
|---|---|
| `lamp`, `light` | `light` |
| `dimmer-lamp` | `light` with brightness |
| `temperature-sensor` | `sensor` |
| `humidity-sensor` | `sensor` |
| `illumination-sensor` | `sensor` |
| `motion-sensor` | `binary_sensor` |
| `door-sensor` | `binary_sensor` |
| `leak-sensor` | `binary_sensor` |
| `valve`, `valve-heating` | `switch` |
| `switch` | hidden by default |
| `fancoil` | `fan` with ON/OFF only |
| `light-scheme` | `button` |

## Device organisation

The HACS integration groups entities by the room or area reported by Larnitech. This keeps the Home Assistant device page usable in larger installations:

- each Larnitech room/area becomes a Home Assistant device named directly after the room, for example `Svetainė`, `Darbo kambarys`, `Beno kambarys`;
- items without room metadata are grouped under `Setup`;
- Larnitech light schemes / grouped lights are grouped under `Light groups`.

If Larnitech stores a real item in `Setup` and only exposes room references in the UI, use area overrides in the integration options:

```text
415:50=Svetainė
415:52=Miegamasis
415:53=Beno kambarys
415:51=Martyno kambarys
```

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
