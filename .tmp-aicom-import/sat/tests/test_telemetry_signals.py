"""Parsing evolution_signal rows from telemetry JSONL."""

from __future__ import annotations

import json
from pathlib import Path

from core.telemetry_signals import EVOLUTION_SIGNAL_EVENT_TYPE, extract_evolution_signals_from_jsonl_dir


def test_extract_evolution_signals_orders_and_filters(tmp_path: Path):
    d = tmp_path / "prod-x"
    d.mkdir()

    line_other = json.dumps({"event_type": "page_view", "data": {}})
    line_sig = json.dumps(
        {
            "product_id": "prod-x",
            "event_type": EVOLUTION_SIGNAL_EVENT_TYPE,
            "data": {"signal": "nps", "weight": 0.9},
            "timestamp": 100.0,
        }
    )
    (d / "telemetry_2026-01-01.jsonl").write_text(line_other + "\n" + line_sig + "\n", encoding="utf-8")

    out = extract_evolution_signals_from_jsonl_dir(d, limit=10)
    assert len(out) == 1
    assert out[0].get("data", {}).get("signal") == "nps"


def test_extract_respects_limit(tmp_path: Path):
    d = tmp_path / "prod-y"
    d.mkdir()
    lines = []
    for i in range(5):
        lines.append(
            json.dumps(
                {
                    "event_type": EVOLUTION_SIGNAL_EVENT_TYPE,
                    "data": {"i": i},
                    "timestamp": float(i),
                }
            )
        )
    (d / "telemetry_2026-02-01.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    out = extract_evolution_signals_from_jsonl_dir(d, limit=2)
    assert len(out) == 2
    assert [x.get("data", {}).get("i") for x in out] == [3, 4]
