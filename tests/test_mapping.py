from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from larnitech_ha_bridge.mapping import MappingRecorder
from larnitech_ha_bridge.models import DeviceStatus, LarnitechDevice


class Clock:
    def __init__(self) -> None:
        self.mono = 0.0
        self.now = datetime(2026, 7, 27, 12, 0, tzinfo=timezone.utc)

    def advance(self, seconds: float) -> None:
        self.mono += seconds
        self.now += timedelta(seconds=seconds)

    def monotonic(self) -> float:
        return self.mono

    def utcnow(self) -> datetime:
        return self.now


def device(addr: str, name: str, type_: str, area: str) -> LarnitechDevice:
    return LarnitechDevice(addr=addr, name=name, type=type_, area=area, raw={})


def status(addr: str, value: object) -> DeviceStatus:
    return DeviceStatus(addr=addr, value=value, raw={"addr": addr, "status": value})


def test_correlates_input_and_multiple_outputs(tmp_path) -> None:
    clock = Clock()
    recorder = MappingRecorder(
        tmp_path,
        group_window_seconds=3,
        clock=clock.monotonic,
        utcnow=clock.utcnow,
    )
    recorder.start(
        [
            device("329:14", "Switch", "switch", "Setup"),
            device("347:4", "Lempa", "lamp", "Svečių WC"),
            device("493:178", "LED", "dimmer-lamp", "Svečių WC"),
        ]
    )

    recorder.record(status("329:14", 1))
    clock.advance(0.2)
    recorder.record(status("347:4", "on"))
    clock.advance(0.2)
    recorder.record(status("493:178", 100))

    assert len(recorder.steps) == 1
    step = recorder.steps[0]
    assert step.input is not None
    assert step.input.addr == "329:14"
    assert [output.addr for output in step.outputs] == ["347:4", "493:178"]

    summary = json.loads(recorder.summary_path.read_text(encoding="utf-8"))
    assert summary["steps"][0]["input"]["addr"] == "329:14"
    assert len(summary["steps"][0]["outputs"]) == 2


def test_groups_output_only_burst_and_starts_new_step_after_quiet_window(tmp_path) -> None:
    clock = Clock()
    recorder = MappingRecorder(
        tmp_path,
        group_window_seconds=2,
        clock=clock.monotonic,
        utcnow=clock.utcnow,
    )
    recorder.start(
        [
            device("493:111", "Spot 1", "dimmer-lamp", "Tėvų WC"),
            device("493:114", "Spot 2", "dimmer-lamp", "Tėvų WC"),
        ]
    )

    recorder.record(status("493:111", 100))
    clock.advance(0.3)
    recorder.record(status("493:114", 100))
    clock.advance(2.1)
    recorder.record(status("493:111", 0))

    assert len(recorder.steps) == 2
    assert recorder.steps[0].source == "output-only"
    assert [output.addr for output in recorder.steps[0].outputs] == ["493:111", "493:114"]
    assert recorder.steps[1].outputs[0].value == 0


def test_ignores_sensor_changes_for_summary_but_keeps_raw_event(tmp_path) -> None:
    clock = Clock()
    recorder = MappingRecorder(tmp_path, clock=clock.monotonic, utcnow=clock.utcnow)
    recorder.start([device("443:30", "Motion", "motion-sensor", "Tambūras")])

    recorder.record(status("443:30", 100))

    assert recorder.steps == ()
    lines = recorder.events_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["addr"] == "443:30"


def test_does_not_start_step_on_switch_release(tmp_path) -> None:
    clock = Clock()
    recorder = MappingRecorder(tmp_path, clock=clock.monotonic, utcnow=clock.utcnow)
    recorder.start([device("329:11", "Switch", "switch", "Setup")])

    recorder.record(status("329:11", 0))

    assert recorder.steps == ()
