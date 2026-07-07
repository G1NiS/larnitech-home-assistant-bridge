# Changelog

## 0.1.14 - 2026-07-07

### Fixed

- Added Home Assistant MQTT fan percentage speed discovery for fancoils.
- Reused the fancoil preset command topic for percentage speed control so Home Assistant speed buttons publish to an already subscribed command topic.
- Kept the 3-speed mapping:
  - `off` -> `0x00`
  - `low` / speed 1 -> `0x0155`
  - `medium` / speed 2 -> `0x01AA`
  - `high` / speed 3 -> `0x01FA`

## 0.1.13 - 2026-07-07

### Added

- Added `fancoil_entity_mode` add-on option:
  - `fan` - exposes Larnitech fancoils as Home Assistant fan entities.
  - `climate` - exposes Larnitech fancoils as Home Assistant climate entities for pure-Larnitech installations.
- Added automatic cleanup of stale fancoil MQTT Discovery topics when switching between `fan` and `climate` modes.
- Added tests for both fancoil discovery modes.

### Changed

- Kept `fan` as the default fancoil mode because this installation controls heating/cooling via Nibe and uses Larnitech fancoils as 3-speed air units.
- Published `fancoil_entity_mode` in diagnostics attributes.

## 0.1.12 - 2026-07-07

### Changed

- Changed Larnitech `type="fancoil"` from Home Assistant `climate` to Home Assistant `fan`.
- Removed fake fancoil temperature and heat/cool mode topics from default discovery.
- Published fancoil speed as fan preset mode: `off`, `low`, `medium`, `high`.
- Mapped real 3-speed fan commands:
  - `off` -> `0x00`
  - `low` / speed 1 -> `0x0155`
  - `medium` / speed 2 -> `0x01AA`
  - `high` / speed 3 -> `0x01FA`
- Cleared retained MQTT `climate` discovery topics from previous fancoil versions.

## 0.1.11 - 2026-07-07

### Fixed

- Changed fancoil HVAC mode and fan commands from JSON objects to Larnitech-style hex status values.
- `off` sends `0x00`.
- Fan speed sends two-byte commands where the first byte is on/off and the second byte is fan power in the Larnitech 0..250 range.

## 0.1.10 - 2026-07-07

### Fixed

- Disabled Python WebSocket protocol pings to avoid Larnitech `keepalive ping timeout` disconnect loops.
- Kept reconnect logic for real connection/request failures.
- Added shorter close timeout so broken sockets do not block reconnects.

## 0.1.9 - 2026-07-07

### Added

- Added initial `type="fancoil"` support as Home Assistant MQTT `climate` entities.
- Published fancoil HVAC mode, current temperature, target temperature when available, fan mode and raw attributes.
- Kept fancoils visible even when Larnitech reports them under internal `Setup` area.

## 0.1.8 - 2026-07-07

### Fixed

- Fixed a bug where MQTT discovery state was never saved to disk. Without this, stale/renamed Larnitech item discovery topics were not cleaned up across add-on restarts.

## 0.1.7 - 2026-07-07

### Fixed

- Reconnected immediately on connection loss instead of always waiting out the backoff delay.
- Retried commands that were in flight when the command WebSocket died.

## 0.1.6 - 2026-07-07

### Added

- Added reconnect logic with exponential backoff for status and command WebSocket connections.

## 0.1.5 - 2026-07-06

### Changed

- Split status and command WebSocket flows to avoid concurrent receive conflicts.
- Added command forwarding from Home Assistant MQTT entities to Larnitech API2.

## 0.1.3 - 2026-07-06

### Changed

- Used address-only MQTT object IDs so renaming items in Larnitech no longer creates duplicate Home Assistant entities.

## 0.1.0 - 2026-07-06

### Added

- Initial MVP add-on.
- Connected to Larnitech API2 WebSocket.
- Requested device list.
- Published Home Assistant MQTT Discovery entities.
