# Changelog

## 0.1.20 - 2026-07-09

### Added

- Added `full_api_dump` add-on option for complete Larnitech API2 diagnostics.
- When enabled, the bridge logs and stores the full `get-devices` API2 response without filtering by area, type, Setup/system area, supported entity type, or Home Assistant discovery eligibility.
- When enabled, the bridge logs and stores every raw `status-subscribe` message received from Larnitech API2.
- When enabled, the bridge also records Home Assistant command payloads and the matching Larnitech API2 command responses.

### Notes

- This release does not change fancoil control behaviour.
- Dump files are written inside the add-on data directory under `/data/full_api_dump/`:
  - `devices_full_<timestamp>.json`
  - `status_stream_<timestamp>.jsonl`
- The same dump records are also written to the add-on log with the `[full-api-dump]` prefix so they can be copied from Home Assistant logs.
- Use this only for short diagnostic windows because it logs the whole system.

## 0.1.19 - 2026-07-08

### Added

- Added `fancoil_debug` add-on option for controlled fancoil reverse-engineering.
- Added fancoil debug logging for native Larnitech status updates received through API2 `status-subscribe`.
- Added fancoil debug logging before Home Assistant commands, after command mapping, and after a short post-command wait.

### Notes

- This release does not change fancoil control behaviour. It only adds diagnostics so manual Larnitech tablet speed changes can be compared with Home Assistant commands.
- Use this release to test one fancoil at a time, starting with `415:50` / `Svetaine`.

## 0.1.18 - 2026-07-08

### Fixed

- Restored safe fancoil on/off behaviour by removing automation/profile fields from Home Assistant fan speed zero/off commands.
- Home Assistant fan percentage `0` now sends only `{"state":"off"}`.
- Home Assistant fancoil state `ON` continues to send only `{"state":"on"}`.
- Fancoil speed commands no longer force `automation: none` or `automation: Off`.

### Notes

- API2 accepts fancoil `fan` values, but this installation does not apply physical fan speed through API2 `status-set`.
- Manual speed control appears to be stored in Larnitech native item/profile configuration and likely requires the tablet/TCP XML item update path, not the documented API2 status path.

## 0.1.17 - 2026-07-08

### Changed

- Changed fancoil speed writes to force Larnitech Manual mode before sending the fan percentage.
- `low` sent a manual command with fan `33`.
- `medium` sent a manual command with fan `66`.
- `high` sent a manual command with fan `100`.
- `off` sent the Off automation together with fan `0`.

### Notes

- This approach changed the fancoil mode in Larnitech and could prevent a later state-only ON command from starting the unit again.
- Reverted in 0.1.18.

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
