from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = ROOT / "custom_components" / "larnitech"
PACKAGE_NAME = "test_larnitech_hacs"

package = types.ModuleType(PACKAGE_NAME)
package.__path__ = [str(PACKAGE_ROOT)]
sys.modules.setdefault(PACKAGE_NAME, package)


def _load_module(name: str):
    qualified_name = f"{PACKAGE_NAME}.{name}"
    existing = sys.modules.get(qualified_name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(qualified_name, PACKAGE_ROOT / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[qualified_name] = module
    spec.loader.exec_module(module)
    return module


models = _load_module("models")
mapping = _load_module("mapping")
DeviceStatus = models.DeviceStatus
LarnitechDevice = models.LarnitechDevice
MappingRecorder = mapping.MappingRecorder


class FakeHass:
    async def async_add_executor_job(self, target, *args):
        return target(*args)


def device(
    addr: str,
    name: str,
    type_: str,
    area: str,
    raw: dict | None = None,
) -> LarnitechDevice:
    return LarnitechDevice(addr=addr, name=name, type=type_, area=area, raw=raw or {})


def status(addr: str, value: object, raw: dict | None = None) -> DeviceStatus:
    return DeviceStatus(
        addr=addr,
        value=value,
        raw=raw or {"addr": addr, "status": value},
    )


@pytest.mark.asyncio
async def test_hacs_mapping_correlates_input_and_outputs(tmp_path) -> None:
    recorder = MappingRecorder(FakeHass(), tmp_path, group_window_seconds=3)
    await recorder.async_start(
        [
            device("329:14", "Switch", "switch", "Setup"),
            device("347:4", "Lempa", "lamp", "Svečių WC"),
            device("493:178", "LED", "dimmer-lamp", "Svečių WC"),
        ],
        initial_values={"329:14": 0, "347:4": "off", "493:178": 0},
    )

    recorder.enqueue(status("329:14", 1))
    recorder.enqueue(status("347:4", "on"))
    recorder.enqueue(status("493:178", 100))
    summary_path = await recorder.async_stop()

    assert summary_path is not None
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["active"] is False
    assert len(summary["steps"]) == 1
    assert summary["steps"][0]["input"]["addr"] == "329:14"
    assert [item["addr"] for item in summary["steps"][0]["outputs"]] == [
        "347:4",
        "493:178",
    ]


@pytest.mark.asyncio
async def test_hacs_mapping_ignores_first_status_without_baseline(tmp_path) -> None:
    recorder = MappingRecorder(FakeHass(), tmp_path)
    await recorder.async_start([device("347:4", "Lempa", "lamp", "Svečių WC")])

    recorder.enqueue(status("347:4", "on"))
    summary_path = await recorder.async_stop()

    assert summary_path is not None
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["steps"] == []
    assert recorder.events_path is not None
    assert recorder.events_path.read_text(encoding="utf-8") == ""


@pytest.mark.asyncio
async def test_hacs_mapping_excludes_sensor_changes_from_export(tmp_path) -> None:
    recorder = MappingRecorder(FakeHass(), tmp_path)
    await recorder.async_start(
        [device("443:30", "Motion", "motion-sensor", "Tambūras")],
        initial_values={"443:30": 0},
    )

    recorder.enqueue(status("443:30", 100))
    summary_path = await recorder.async_stop()

    assert summary_path is not None
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["steps"] == []
    assert recorder.events_path is not None
    assert recorder.events_path.read_text(encoding="utf-8") == ""


@pytest.mark.asyncio
async def test_hacs_mapping_redacts_sensitive_fields(tmp_path) -> None:
    recorder = MappingRecorder(FakeHass(), tmp_path)
    await recorder.async_start(
        [
            device(
                "329:14",
                "Switch",
                "switch",
                "Setup",
                raw={"addr": "329:14", "api_key": "device-secret"},
            )
        ],
        initial_values={"329:14": 0},
    )

    recorder.enqueue(
        status(
            "329:14",
            1,
            raw={"addr": "329:14", "status": 1, "token": "event-secret"},
        )
    )
    await recorder.async_stop()

    assert recorder.devices_path is not None
    devices = json.loads(recorder.devices_path.read_text(encoding="utf-8"))
    assert devices["devices"][0]["raw"]["api_key"] == "***"

    assert recorder.events_path is not None
    event = json.loads(recorder.events_path.read_text(encoding="utf-8").splitlines()[0])
    assert event["raw"]["token"] == "***"
