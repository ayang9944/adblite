from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class Device:
    serial: str
    state: str = "unknown"
    model: str = ""
    transport_id: str = ""

    @property
    def label(self) -> str:
        if self.model:
            return f"{self.model} · {self.serial}"
        return self.serial


@dataclass
class ConnectionHistory:
    address: str
    name: str = ""
    kind: str = "wifi"
    last_used: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def label(self) -> str:
        return f"{self.name} ({self.address})" if self.name else self.address


@dataclass
class CustomCommand:
    name: str
    runner: str
    args: list[str] = field(default_factory=list)
    command: str = ""
    group: str = "常用"
    device_required: bool = True
    confirm: bool = False
