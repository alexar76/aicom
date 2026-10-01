"""
Extract structured evolution hints from TelemetryCollector JSONL files.

Events posted via ``POST /api/telemetry/evolution-signal`` use ``event_type == evolution_signal``.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

EVOLUTION_SIGNAL_EVENT_TYPE = "evolution_signal"


def extract_evolution_signals_from_jsonl_dir(
    telemetry_product_dir: Path,
    *,
    limit: int = 300,
) -> list[dict[str, Any]]:
    """
    Load recent evolution_signal rows from ``telemetry_*.jsonl`` under the product telemetry folder.

    Newest-first harvest (reverse file order + reverse line order within each file), returned
    chronologically (oldest → newest) for LLM context.
    """
    if limit <= 0 or not telemetry_product_dir.is_dir():
        return []

    files = sorted(telemetry_product_dir.glob("telemetry_*.jsonl"))
    collected: list[dict[str, Any]] = []

    for fp in reversed(files):
        try:
            raw = fp.read_text(encoding="utf-8")
        except OSError:
            continue
        for line in reversed(raw.splitlines()):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(row, dict):
                continue
            if row.get("event_type") != EVOLUTION_SIGNAL_EVENT_TYPE:
                continue
            collected.append(row)
            if len(collected) >= limit:
                return list(reversed(collected))

    return list(reversed(collected))
