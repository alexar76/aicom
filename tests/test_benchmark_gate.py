from __future__ import annotations

import json
import time
from pathlib import Path

from web.backend.services.benchmark_gate import evaluate_benchmark_gate


def test_benchmark_gate_blocks_low_pass_rate(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    (reports / "benchmark_scorecard.json").write_text(
        json.dumps(
            {
                "generated_at": time.time(),
                "runs_last_7d": 5,
                "latest": {"pass_rate": 0.42},
            }
        ),
        encoding="utf-8",
    )
    out = evaluate_benchmark_gate(str(tmp_path))
    assert out["passed"] is False
    assert "pass_rate_too_low" in out["reason"]
