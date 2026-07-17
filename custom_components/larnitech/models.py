from __future__ import annotations

from dataclasses import dataclass
from typing import Any


AREA_KEYS = ("area", "room", "zone", "section", "parent")


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
