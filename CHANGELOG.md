# Changelog

## 0.1.31 - 2026-07-17

### Added

- Added optional area overrides for Larnitech items that are reported under `Setup` but should appear under specific Home Assistant rooms.
- Added integration options flow for editing area overrides after setup.

### Changed

- Generic Larnitech `switch` items are hidden by default because they are usually physical wall buttons or low-level controller inputs, not useful Home Assistant controls.
- Changed the HACS validation workflow to manual-only to prevent failed publish-gate checks from spamming notifications during active development.

### Fixed

- Added cleanup for stale generic `switch` entity-registry entries created by older versions, reducing inactive switch spam after upgrade.

## 0.1.30 - 2026-07-17

### Changed

- Removed the `Larnitech ·` prefix from area/room device names in Home Assistant.
- Room devices now use clean names such as `Svetainė`, `Darbo kambarys`, `Setup` and `Light groups`.

## 0.1.29 - 2026-07-17

### Fixed

- Fixed fan-coil ON/OFF service support by explicitly advertising `TURN_ON` and `TURN_OFF` fan features.
- Fixed fan-coil state reporting when Larnitech reports `fan=100` while the explicit runtime `state` is `off`.

## 0.1.28 - 2026-07-17

### Added

- Added Home Assistant button platform for Larnitech `light-scheme` items.
- Added a dedicated `Larnitech · Light groups` device for grouped lighting / light schemes.
- Added room/area-based Home Assistant device grouping for Larnitech items.
- Added `Larnitech · Setup` grouping for items without room metadata.
- Improved public README and HACS `info.md` descriptions.

### Changed

- Generic Larnitech `light` items are now mapped as Home Assistant `light` entities.
- Virtual grouped lights with `contains` metadata are grouped under `Larnitech · Light groups`.
- Physical wall/input switches with only `linked` targets and `undefined` state are filtered out of switch entities.
- Existing config entry titles are normalized to `Larnitech HA Bridge (...)` during setup.

## 0.1.27 - 2026-07-17

### Fixed

- Fixed Home Assistant setup failure caused by importing removed `UnitOfIlluminance` from `homeassistant.const`.
- Illumination sensors now use the supported `lx` unit string with `SensorDeviceClass.ILLUMINANCE`.

## 0.1.26 - 2026-07-17

### Changed

- Renamed the HACS integration display name to `Larnitech HA Bridge`.
- Updated config flow title and config entry title to use `Larnitech HA Bridge`.
- Added field descriptions for host, API2 port and API2 key.
- Preserved entered config flow values when validation fails.
- Updated README for the new integration name and local brand icon paths.

## 0.1.25 - 2026-07-17

### Changed

- Improved the HACS integration config flow host handling.
- Host input now accepts and normalizes values such as `http://host`, `ws://host`, and `host:2041`.
- Added field-level errors for missing host and missing API2 key.
- Updated config flow labels and README to explain that the host field should contain only a host name or IP address.
- Added local Home Assistant brand images under `custom_components/larnitech/brand/`.

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
- Added custom brand icon assets.

### Notes

- Public HACS baseline is free and does not require a license key.
- Fancoils are exposed as ON/OFF fan entities only.

## 0.1.23 - 2026-07-09

### Changed

- Cleaned up experimental fancoil speed, climate, raw hex, full API dump and fancoil debug paths in the add-on/MQTT bridge.
- Fancoils are exposed as ON/OFF fan entities only.

## Earlier add-on changelog

The Home Assistant add-on changelog is maintained in [`addon/CHANGELOG.md`](addon/CHANGELOG.md).
