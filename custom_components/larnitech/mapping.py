from __future__ import annotations

import asyncio
import json
import math
import os
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable

from .models import DeviceStatus, LarnitechDevice

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

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
_SENSITIVE_KEY_PARTS = ("api_key", "apikey", "key", "password", "passwd", "secret", "token")
_MISSING = object()

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
    """Record and correlate Larnitech input/output changes without blocking HA."""

    def __init__(
        self,
        hass: HomeAssistant,
        output_dir: str | Path,
        *,
        group_window_seconds: float = 3.0,
    ) -> None:
        self.hass = hass
        self.output_dir = Path(output_dir)
        self.group_window_seconds = max(0.5, float(group_window_seconds))
        self._devices: dict[str, LarnitechDevice] = {}
        self._last_values: dict[str, Any] = {}
        self._steps: list[MappingStep] = []
        self._current_step: MappingStep | None = None
        self._current_step_last_event_mono: float | None = None
        self._queue: asyncio.Queue[DeviceStatus | None] = asyncio.Queue()
        self._worker_task: asyncio.Task[None] | None = None
        self._session_id = ""
        self._active = False

        self.events_path: Path | None = None
        self.summary_path: Path | None = None
        self.latest_summary_path: Path | None = None
        self.devices_path: Path | None = None

    @property
    def active(self) -> bool:
        return self._active

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def steps(self) -> tuple[MappingStep, ...]:
        return tuple(self._steps)

    async def async_start(
        self,
        devices: Iterable[LarnitechDevice],
        *,
        initial_values: dict[str, Any] | None = None,
    ) -> Path:
        if self._active:
            assert self.latest_summary_path is not None
            return self.latest_summary_path

        self._devices = {device.addr: device for device in devices}
        self._last_values = dict(initial_values or {})
        now = datetime.now(timezone.utc)
        self._session_id = now.strftime("%Y%m%dT%H%M%SZ")
        self.events_path = self.output_dir / f"mapping_events_{self._session_id}.jsonl"
        self.summary_path = self.output_dir / f"mapping_summary_{self._session_id}.json"
        self.latest_summary_path = self.output_dir / "mapping_summary_latest.json"
        self.devices_path = self.output_dir / f"mapping_devices_{self._session_id}.json"

        self._active = True
        try:
            await self.hass.async_add_executor_job(self._start_sync, now)
        except Exception:
            self._active = False
            raise
        self._worker_task = asyncio.create_task(self._worker())
        return self.latest_summary_path

    def enqueue(self, status: DeviceStatus) -> None:
        if self._active:
            self._queue.put_nowait(status)

    async def async_stop(self) -> Path | None:
        if not self._active:
            return self.latest_summary_path

        self._active = False
        await self._queue.join()
        self._queue.put_nowait(None)
        if self._worker_task is not None:
            await self._worker_task
            self._worker_task = None
        await self.hass.async_add_executor_job(self._write_summary)
        return self.latest_summary_path

    async def _worker(self) -> None:
        while True:
            status = await self._queue.get()
            try:
                if status is None:
                    return
                await self.hass.async_add_executor_job(self._record_sync, status)
            finally:
                self._queue.task_done()

    def _start_sync(self, now: datetime) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        assert self.events_path is not None
        assert self.devices_path is not None
        self.events_path.touch(exist_ok=True)
        self._write_json(
            self.devices_path,
            {
                "session_id": self._session_id,
                "created_at": self._iso(now),
                "devices": [self._device_dict(device) for device in self._devices.values()],
            },
        )
        self._write_summary()

    def _record_sync(self, status: DeviceStatus) -> None:
        now_mono = time.monotonic()
        now = datetime.now(timezone.utc)
        previous = self._last_values.get(status.addr, _MISSING)
        self._last_values[status.addr] = status.value

        # A first status without a known baseline is not evidence of a physical change.
        if previous is _MISSING or self._same_value(previous, status.value):
            return

        device = self._devices.get(status.addr)
        device_type = (device.type if device else "unknown").strip().lower()

        # Keep the export compact. Known sensors are not useful for switch mapping.
        if device is not None and device_type not in INPUT_TYPES and device_type not in OUTPUT_TYPES:
            return

        change = MappingChange(
            addr=status.addr,
            name=device.name if device else status.addr,
            type=device_type,
            area=device.area if device else None,
            previous=previous,
            value=status.value,
            observed_at=self._iso(now),
        )
        self._append_event(change, status.raw)

        if device_type in INPUT_TYPES and self._is_active(status.value):
            self._start_step(change, source="input", now_mono=now_mono)
            self._write_summary()
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

    def _start_step(
        self,
        input_change: MappingChange | None,
        *,
        source: str,
        now_mono: float,
    ) -> None:
        step = MappingStep(
            sequence=len(self._steps) + 1,
            started_at=(
                input_change.observed_at
                if input_change is not None
                else self._iso(datetime.now(timezone.utc))
            ),
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

    def _append_event(self, change: MappingChange, raw: dict[str, Any]) -> None:
        assert self.events_path is not None
        payload = {
            "session_id": self._session_id,
            **asdict(change),
            "raw": self._redact(raw),
        }
        with self.events_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")

    def _write_summary(self) -> None:
        assert self.summary_path is not None
        assert self.latest_summary_path is not None
        payload = {
            "session_id": self._session_id,
            "updated_at": self._iso(datetime.now(timezone.utc)),
            "active": self._active,
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

    @classmethod
    def _device_dict(cls, device: LarnitechDevice) -> dict[str, Any]:
        return {
            "addr": device.addr,
            "name": device.name,
            "type": device.type,
            "area": device.area,
            "raw": cls._redact(device.raw),
        }

    @classmethod
    def _redact(cls, value: Any) -> Any:
        if isinstance(value, dict):
            sanitized: dict[str, Any] = {}
            for key, item in value.items():
                key_text = str(key)
                normalized = key_text.lower().replace("-", "_")
                if any(part in normalized for part in _SENSITIVE_KEY_PARTS):
                    sanitized[key_text] = "***"
                else:
                    sanitized[key_text] = cls._redact(item)
            return sanitized
        if isinstance(value, list):
            return [cls._redact(item) for item in value]
        if isinstance(value, tuple):
            return [cls._redact(item) for item in value]
        return value

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
