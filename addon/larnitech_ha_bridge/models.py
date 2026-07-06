from __future__ import annotations

from dataclasses import dataclass
from typing import Any


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
            area=str(raw.get("area")) if raw.get("area") is not None else None,
            raw=raw,
        )


@dataclass(frozen=True)
class DeviceStatus:
    addr: str
    value: Any
    raw: dict[str, Any]
