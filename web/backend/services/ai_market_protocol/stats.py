"""Live feed of external AI market invocations."""

from __future__ import annotations

import json
import time
from typing import Any

from web.backend.services.ai_market_protocol.paths import stats_path


def append_stat(event: dict[str, Any]) -> None:
    row = {"time": time.time(), **event}
    p = stats_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def list_recent_stats(*, limit: int = 50) -> list[dict[str, Any]]:
    p = stats_path()
    if not p.exists():
        return []
    lines = p.read_text(encoding="utf-8").strip().splitlines()
    out: list[dict[str, Any]] = []
    for line in reversed(lines[-limit:]):
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out
