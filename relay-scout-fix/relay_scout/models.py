from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class EndpointTarget:
    name: str
    url: str
    kind: str = "json"
    webhook_urls: list[str] = field(default_factory=list)
    interval_seconds: int = 60


@dataclass
class Snapshot:
    endpoint_name: str
    timestamp: str
    status_code: int
    latency_ms: float
    response_json: dict[str, Any] | None = None
    error: str | None = None


@dataclass
class DiffResult:
    added_fields: list[str] = field(default_factory=list)
    removed_fields: list[str] = field(default_factory=list)
    changed_fields: list[str] = field(default_factory=list)
    summary: str = ""

    @property
    def has_changes(self) -> bool:
        return bool(self.added_fields or self.removed_fields or self.changed_fields)


@dataclass
class AlertRecord:
    endpoint_name: str
    alert_type: str
    message: str
    timestamp: str
    sent: bool = False
