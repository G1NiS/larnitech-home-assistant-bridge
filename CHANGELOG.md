# Changelog

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
