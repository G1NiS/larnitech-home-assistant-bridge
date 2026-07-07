# Changelog

## 0.1.17 - 2026-07-08

### Changed

- Changed fancoil speed writes to force Larnitech Manual mode before sending the fan percentage.
- `low` now sends a manual command with fan `33`.
- `medium` now sends a manual command with fan `66`.
- `high` now sends a manual command with fan `100`.
- `off` now sends the Off automation together with fan `0`.

### Notes

- 0.1.16 proved that API2 accepts `fan` values, but the physical unit stays on the speed stored in the active Larnitech mode.
- This release targets the tablet behaviour where speed is only editable when Auto is set to Manual.

## 0.1.16 - 2026-07-08

### Changed

- Changed fancoil speed writes from raw hex payloads to structured fan percentage objects.
- `off` sent state off and fan `0`.
- `low` sent state on and fan `33`.
- `medium` sent state on and fan `66`.
- `high` sent state on and fan `100`.

### Notes

- The previous raw hex payload path was accepted by API2 but did not change the physical fan speed on this installation.

## 0.1.15 - 2026-07-08

### Fixed

- Fixed fancoil speed control through Home Assistant MQTT fan percentage topics.
- Separated numeric fan speed percentage topics from named preset mode topics:
  - `percentage/set` now receives Home Assistant numeric speed commands `1`, `2`, `3`.
  - `preset_mode/set` still receives named commands `off`, `low`, `medium`, `high`.
- Subscribed the bridge to both fancoil speed command paths so both Home Assistant speed buttons and preset controls reach the Larnitech API2 command handler.
- Published numeric fancoil speed state to `percentage/state` and named speed state to `preset_mode/state`.
- Kept the existing Larnitech fancoil command mapping:
  - `off` -> `0x00`
  - `low` / speed 1 -> `0x0155`
  - `medium` / speed 2 -> `0x01AA`
  - `high` / speed 3 -> `0x01FA`

### Notes

- TLS connection, Server access connection and MQTT bridge research are intentionally not included in this release.
- This release keeps the documented API2 key connection as the only active Larnitech connection method.

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
