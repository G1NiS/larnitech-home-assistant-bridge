# Changelog

## 0.1.24 - 2026-07-09

### Added

- Added HACS custom integration baseline under `custom_components/larnitech`.
- Added Home Assistant config flow for host, API2 port and API2 key.
- Added native Home Assistant platforms:
  - `light`
  - `fan`
  - `sensor`
  - `binary_sensor`
  - `switch`
- Added HACS metadata with `hacs.json` and `info.md`.
- Added HACS and Hassfest validation workflows.
- Added translation files for the config flow.
- Added funding metadata for service-based monetization.
- Added custom SVG brand icon draft under `brand/icon.svg`.

### Notes

- Public HACS baseline is free and does not require a license key.
- Fancoils are exposed as ON/OFF fan entities only.
- Add binary `brand/icon.png` before submitting as a HACS default repository.

## 0.1.23 - 2026-07-09

### Changed

- Cleaned up experimental fancoil speed, climate, raw hex, full API dump and fancoil debug paths in the add-on/MQTT bridge.
- Fancoils are exposed as ON/OFF fan entities only.

## Earlier add-on changelog

The Home Assistant add-on changelog is maintained in [`addon/CHANGELOG.md`](addon/CHANGELOG.md).

## 0.1.13 - 2026-07-07

- Added configurable `fancoil_entity_mode` option: `fan` or `climate`.
- Kept `fan` as default for installations where heating/cooling is controlled outside Larnitech.
- Retained `climate` mode for pure-Larnitech installations.
- Added stale MQTT Discovery cleanup when switching fancoil mode.

## 0.1.12 - 2026-07-07

- Changed fancoils to 3-speed Home Assistant fan entities by default.
- Added speed command mapping: `off`, `low`, `medium`, `high`.

## 0.1.11 - 2026-07-07

- Fixed fancoil command payloads to use Larnitech-style hex status values.

## 0.1.10 - 2026-07-07

- Fixed Larnitech WebSocket keepalive timeout loops.

## 0.1.9 - 2026-07-07

- Added initial fancoil climate support.

## 0.1.8 - 2026-07-07

- Fixed MQTT discovery state persistence and stale topic cleanup.

## 0.1.7 - 2026-07-07

- Improved reconnect behavior and command retry handling.

## 0.1.6 - 2026-07-07

- Added reconnect logic for Larnitech WebSocket connections.

## 0.1.5 - 2026-07-06

- Split status and command WebSocket flows.

## 0.1.3 - 2026-07-06

- Switched MQTT object IDs to stable address-based IDs.

## 0.1.0 - 2026-07-06

- Initial MVP.
