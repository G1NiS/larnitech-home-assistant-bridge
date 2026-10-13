from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any


AREA_KEYS = ("area", "room", "zone", "section", "parent")


def motion_status_is_on(status: Any) -> bool:
    """Larnitech motion-sensor reports movement percentage, not just 'on'/'off'."""
    raw = status.get("state", status.get("value")) if isinstance(status, dict) else status
    if raw is None:
        return False
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)):
        return isfinite(raw) and raw > 0

    text = str(raw).strip().lower()
    if text in {"on", "open", "opened", "true", "yes"}:
        return True
    if text in {"off", "closed", "false", "no", "unknown", "undefined", ""}:
        return False
    try:
        intensity = int(text, 16) if text.startswith("0x") else float(text)
    except (TypeError, ValueError):
        return False
    return isfinite(intensity) and intensity > 0



def _extract_area(raw: dict[str, Any]) -> str | None:
    for key in AREA_KEYS:
        value = raw.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


@dataclass(frozen=True)
class LarnitechDevice:
    addr: str
    name: str
    type: str
    area: str | None
    raw: dict[str, Any]

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> "LarnitechDevice":
        return cls(
            addr=str(raw.get("addr", "")),
            name=str(raw.get("name") or raw.get("title") or raw.get("addr") or "Unknown"),
            type=str(raw.get("type") or raw.get("kind") or "unknown"),
            area=_extract_area(raw),
            raw=raw,
        )


@dataclass(frozen=True)
class DeviceStatus:
    addr: str
    value: Any
    raw: dict[str, Any]
