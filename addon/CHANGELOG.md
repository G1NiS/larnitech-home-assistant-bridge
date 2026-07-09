# Changelog

## 0.1.21 - 2026-07-09

### Changed

- Changed fancoil speed commands to use native Larnitech API2 fan levels observed from `full_api_dump`:
  - `low` / `1` -> `{"state":"on","fan":33.2}`
  - `medium` / `2` -> `{"state":"on","fan":66.4}`
  - `high` / `3` -> `{"state":"on","fan":100.0}`
- Numeric percentage commands are rounded to the closest native Larnitech fancoil level.
- Fancoil `state` commands remain minimal `{"state":"on"}` / `{"state":"off"}`.
- Home Assistant fan percentage `0` still sends only `{"state":"off"}`.

### Notes

- The native Larnitech UI reports manual fancoil fan levels as `0.0`, `33.2`, `66.4`, and `100.0`.
- This release keeps fancoils exposed as Home Assistant `fan` entities by default.

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
