from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from core.paths import benchmark_scorecard_path, resolve_data_root

# Built-in hard gate thresholds (not configurable via env).
BUILTIN_MIN_PASS_RATE = 0.80
BUILTIN_MAX_SCORECARD_AGE_SEC = 36 * 3600
BUILTIN_MIN_RUNS_7D = 3


def evaluate_benchmark_gate(data_root: str | Path | None = None) -> dict[str, Any]:
    root = resolve_data_root(data_root)
    scorecard_path = benchmark_scorecard_path() if data_root is None else root / "reports" / "benchmark_scorecard.json"
    if not scorecard_path.is_file():
        return {
            "passed": False,
            "reason": "benchmark_gate: scorecard_missing",
            "details": {},
        }
    try:
        scorecard = json.loads(scorecard_path.read_text(encoding="utf-8"))
    except Exception:
        return {
            "passed": False,
            "reason": "benchmark_gate: scorecard_invalid_json",
            "details": {},
        }

    generated_at = float(scorecard.get("generated_at") or 0.0)
    latest = scorecard.get("latest") if isinstance(scorecard.get("latest"), dict) else {}
    latest_pass_rate = float((latest or {}).get("pass_rate") or 0.0)
    runs_7d = int(scorecard.get("runs_last_7d") or 0)
    now = time.time()
    age_sec = (now - generated_at) if generated_at > 0 else float("inf")

    issues: list[str] = []
    if age_sec > BUILTIN_MAX_SCORECARD_AGE_SEC:
        issues.append("stale_scorecard")
    if runs_7d < BUILTIN_MIN_RUNS_7D:
        issues.append("insufficient_recent_runs")
    if latest_pass_rate < BUILTIN_MIN_PASS_RATE:
        issues.append("pass_rate_too_low")

    passed = len(issues) == 0
    reason = "benchmark_gate: ok" if passed else f"benchmark_gate: {','.join(issues)}"
    return {
        "passed": passed,
        "reason": reason,
        "details": {
            "latest_pass_rate": latest_pass_rate,
            "min_pass_rate": BUILTIN_MIN_PASS_RATE,
            "scorecard_age_sec": age_sec,
            "max_scorecard_age_sec": BUILTIN_MAX_SCORECARD_AGE_SEC,
            "runs_last_7d": runs_7d,
            "min_runs_last_7d": BUILTIN_MIN_RUNS_7D,
        },
    }
