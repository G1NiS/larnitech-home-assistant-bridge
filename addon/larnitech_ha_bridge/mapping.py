from __future__ import annotations

import json
import logging
import math
import os
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from .models import DeviceStatus, LarnitechDevice

_LOGGER = logging.getLogger(__name__)

INPUT_TYPES = {"switch", "button", "input", "binary-input"}
OUTPUT_TYPES = {
    "lamp",
    "light",
    "dimmer-lamp",
    "light-scheme",
    "script",
    "relay",
    "valve",
    "valve-heating",
}

_OFF_STRINGS = {
    "",
    "0",
    "0.0",
    "false",
    "off",
    "closed",
    "idle",
    "inactive",
    "none",
    "null",
    "released",
    "undefined",
}


@dataclass
class MappingChange:
    addr: str
    name: str
    type: str
    area: str | None
    previous: Any
    value: Any
    observed_at: str


@dataclass
class MappingStep:
    sequence: int
    started_at: str
    source: str
    input: MappingChange | None = None
    outputs: list[MappingChange] = field(default_factory=list)


class MappingRecorder:
    """Record and correlate Larnitech input/output status changes."""

    def __init__(
        self,
        output_dir: str | Path,
        *,
        group_window_seconds: float = 3.0,
        clock: Callable[[], float] = time.monotonic,
        utcnow: Callable[[], datetime] | None = None,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.group_window_seconds = max(0.5, float(group_window_seconds))
        self._clock = clock
        self._utcnow = utcnow or (lambda: datetime.now(timezone.utc))
        self._devices: dict[str, LarnitechDevice] = {}
        self._last_values: dict[str, Any] = {}
        self._steps: list[MappingStep] = []
        self._current_step: MappingStep | None = None
        self._current_step_last_event_mono: float | None = None
        self._started = False
        self._session_id = ""

        self.events_path: Path | None = None
        self.summary_path: Path | None = None
        self.latest_summary_path: Path | None = None
        self.devices_path: Path | None = None

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def steps(self) -> tuple[MappingStep, ...]:
        return tuple(self._steps)

    def start(self, devices: Iterable[LarnitechDevice]) -> None:
        if self._started:
            self.update_devices(devices)
            return

        self.output_dir.mkdir(parents=True, exist_ok=True)
        started_at = self._utcnow()
        self._session_id = started_at.strftime("%Y%m%dT%H%M%SZ")
        self.events_path = self.output_dir / f"mapping_events_{self._session_id}.jsonl"
        self.summary_path = self.output_dir / f"mapping_summary_{self._session_id}.json"
        self.latest_summary_path = self.output_dir / "mapping_summary_latest.json"
        self.devices_path = self.output_dir / f"mapping_devices_{self._session_id}.json"

        self.update_devices(devices)
        self._write_json(
            self.devices_path,
            {
                "session_id": self._session_id,
                "created_at": self._iso(started_at),
                "devices": [self._device_dict(device) for device in self._devices.values()],
            },
        )
        self._started = True
        self._write_summary()

        _LOGGER.warning(
            "[mapping] Session %s started. Files: %s, %s",
            self._session_id,
            self.events_path,
            self.summary_path,
        )

    def update_devices(self, devices: Iterable[LarnitechDevice]) -> None:
        self._devices = {device.addr: device for device in devices}

    def record(self, status: DeviceStatus) -> None:
        if not self._started:
            raise RuntimeError("MappingRecorder.start() must be called before record()")

        now_mono = self._clock()
        now = self._utcnow()
        previous = self._last_values.get(status.addr)
        self._last_values[status.addr] = status.value

        device = self._devices.get(status.addr)
        device_type = (device.type if device else "unknown").strip().lower()
        change = MappingChange(
            addr=status.addr,
            name=device.name if device else status.addr,
            type=device_type,
            area=device.area if device else None,
            previous=previous,
            value=status.value,
            observed_at=self._iso(now),
        )

        self._append_event(
            {
                "session_id": self._session_id,
                "observed_at": change.observed_at,
                "addr": status.addr,
                "name": change.name,
                "type": change.type,
                "area": change.area,
                "previous": previous,
                "value": status.value,
                "raw": status.raw,
            }
        )

        if self._same_value(previous, status.value):
            return

        if device_type in INPUT_TYPES and self._is_active(status.value):
            self._start_step(change, source="input", now_mono=now_mono)
            self._write_summary()
            _LOGGER.warning(
                "[mapping] Step %s input: %s (%s, %s)",
                self._current_step.sequence,
                change.name,
                change.addr,
                change.area or "no area",
            )
            return

        if device_type not in OUTPUT_TYPES:
            return

        if (
            self._current_step is None
            or self._current_step_last_event_mono is None
            or now_mono - self._current_step_last_event_mono > self.group_window_seconds
        ):
            self._start_step(None, source="output-only", now_mono=now_mono)

        assert self._current_step is not None
        self._upsert_output(self._current_step, change)
        self._current_step_last_event_mono = now_mono
        self._write_summary()
        _LOGGER.warning(
            "[mapping] Step %s output: %s (%s) %s -> %s",
            self._current_step.sequence,
            change.name,
            change.addr,
            self._safe_log_value(change.previous),
            self._safe_log_value(change.value),
        )

    def _start_step(
        self,
        input_change: MappingChange | None,
        *,
        source: str,
        now_mono: float,
    ) -> None:
        step = MappingStep(
            sequence=len(self._steps) + 1,
            started_at=input_change.observed_at if input_change else self._iso(self._utcnow()),
            source=source,
            input=input_change,
        )
        self._steps.append(step)
        self._current_step = step
        self._current_step_last_event_mono = now_mono

    @staticmethod
    def _upsert_output(step: MappingStep, change: MappingChange) -> None:
        for index, existing in enumerate(step.outputs):
            if existing.addr == change.addr:
                step.outputs[index] = change
                return
        step.outputs.append(change)

    def _append_event(self, payload: dict[str, Any]) -> None:
        assert self.events_path is not None
        with self.events_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")

    def _write_summary(self) -> None:
        assert self.summary_path is not None
        assert self.latest_summary_path is not None
        payload = {
            "session_id": self._session_id,
            "updated_at": self._iso(self._utcnow()),
            "group_window_seconds": self.group_window_seconds,
            "instructions": (
                "Each step represents one detected button press or one output-only change burst. "
                "Use input.addr when available; otherwise identify the physical button by step order."
            ),
            "steps": [asdict(step) for step in self._steps],
        }
        self._write_json(self.summary_path, payload)
        self._write_json(self.latest_summary_path, payload)

    @staticmethod
    def _write_json(path: Path, payload: dict[str, Any]) -> None:
        temp_path = path.with_suffix(path.suffix + ".tmp")
        temp_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
            encoding="utf-8",
        )
        os.replace(temp_path, path)

    @staticmethod
    def _device_dict(device: LarnitechDevice) -> dict[str, Any]:
        return {
            "addr": device.addr,
            "name": device.name,
            "type": device.type,
            "area": device.area,
            "raw": device.raw,
        }

    @staticmethod
    def _iso(value: datetime) -> str:
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

    @classmethod
    def _is_active(cls, value: Any) -> bool:
        if isinstance(value, dict):
            for key in ("pressed", "state", "status", "value", "level"):
                if key in value:
                    return cls._is_active(value[key])
            return bool(value)

        if isinstance(value, bool):
            return value

        if isinstance(value, (int, float)):
            return math.isfinite(float(value)) and float(value) > 0

        text = str(value).strip().lower()
        if text in _OFF_STRINGS:
            return False
        if text.startswith("0x"):
            try:
                return int(text, 16) > 0
            except ValueError:
                return True
        try:
            return float(text) > 0
        except ValueError:
            return True

    @staticmethod
    def _same_value(left: Any, right: Any) -> bool:
        try:
            return left == right
        except Exception:
            return False

    @staticmethod
    def _safe_log_value(value: Any) -> str:
        text = str(value)
        return text if len(text) <= 120 else text[:117] + "..."
