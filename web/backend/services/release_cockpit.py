"""
Release cockpit
===============
Single go/no-go evaluator for operational maturity.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from web.backend.services.benchmark_gate import evaluate_benchmark_gate
from web.backend.services.quality_constitution import evaluate_quality_constitution


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _read_jsonl(path: Path, limit: int = 200) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    except Exception:
        return []
    if len(rows) > limit:
        rows = rows[-limit:]
    return rows


def evaluate_release_cockpit(product_id: str, data_root: str = "/app/data") -> dict[str, Any]:
    root = Path(data_root)
    issues: list[str] = []
    checks: dict[str, bool] = {}

    constitution = evaluate_quality_constitution(product_id, data_root)
    checks["quality_constitution"] = bool(constitution.get("passed"))
    if not checks["quality_constitution"]:
        issues.extend([f"constitution:{x}" for x in (constitution.get("issues") or [])])

    lifecycle = _read_json(root / "state" / product_id / "lifecycle_release.json")
    lifecycle_obj = lifecycle.get("lifecycle_release") if isinstance(lifecycle, dict) else {}
    checks["lifecycle_artifact"] = isinstance(lifecycle_obj, dict) and bool(lifecycle_obj)
    if not checks["lifecycle_artifact"]:
        issues.append("lifecycle_release_missing")

    protocol_exec = _read_json(root / "state" / product_id / "release_protocol_execution.json")
    checks["release_protocol_executed"] = bool(protocol_exec.get("executed"))
    if not checks["release_protocol_executed"]:
        issues.append("release_protocol_not_executed")

    benchmark_gate = evaluate_benchmark_gate(str(root))
    latest_pass_rate = float((benchmark_gate.get("details") or {}).get("latest_pass_rate") or 0.0)
    min_pass_rate = float((benchmark_gate.get("details") or {}).get("min_pass_rate") or 0.0)
    checks["benchmark_passrate"] = bool(benchmark_gate.get("passed"))
    if not checks["benchmark_passrate"]:
        issues.append(str(benchmark_gate.get("reason") or "benchmark_gate: unknown"))

    # Perf regression check: compare recent p95 to prior baseline.
    perf_hist = _read_jsonl(root / "telemetry" / product_id / "load_perf_history.jsonl", limit=120)
    perf_regression_ok = True
    perf_regression_meta: dict[str, Any] = {"samples": len(perf_hist)}
    if len(perf_hist) >= 6:
        recent = perf_hist[-3:]
        baseline = perf_hist[-12:-3] or perf_hist[:-3]
        recent_p95 = sum(int(x.get("p95_ms") or 0) for x in recent) / max(1, len(recent))
        base_p95 = sum(int(x.get("p95_ms") or 0) for x in baseline) / max(1, len(baseline))
        ratio = (recent_p95 / base_p95) if base_p95 > 0 else 1.0
        max_ratio = float(os.environ.get("AIFACTORY_COCKPIT_PERF_REGRESSION_RATIO_MAX", "1.35"))
        perf_regression_ok = ratio <= max_ratio
        perf_regression_meta = {
            "samples": len(perf_hist),
            "recent_p95_ms_avg": round(recent_p95, 2),
            "baseline_p95_ms_avg": round(base_p95, 2),
            "ratio": round(ratio, 3),
            "max_ratio": max_ratio,
        }
        if not perf_regression_ok:
            issues.append(f"perf_regression_ratio_high:{ratio:.3f}>{max_ratio}")
    checks["perf_regression"] = perf_regression_ok

    go = all(bool(v) for v in checks.values())
    return {
        "product_id": product_id,
        "go_no_go": "go" if go else "no-go",
        "checks": checks,
        "issues": issues,
        "details": {
            "constitution": constitution,
            "lifecycle_release": lifecycle_obj,
            "release_protocol_execution": protocol_exec,
            "benchmark_latest_pass_rate": latest_pass_rate,
            "benchmark_min_pass_rate": min_pass_rate,
            "benchmark_gate": benchmark_gate,
            "perf_regression": perf_regression_meta,
        },
        "evaluated_at": time.time(),
    }


def execute_release_protocol(product_id: str, data_root: str = "/app/data") -> dict[str, Any]:
    """
    Executable release protocol:
    - verifies lifecycle release artifact has required sections
    - writes execution document for cockpit gating
    """
    root = Path(data_root)
    lifecycle = _read_json(root / "state" / product_id / "lifecycle_release.json")
    obj = lifecycle.get("lifecycle_release") if isinstance(lifecycle, dict) else {}
    required = ("versioning_strategy", "migration_plan", "canary_plan", "rollback_plan", "release_checks")
    missing = [k for k in required if not obj.get(k)]
    executed = len(missing) == 0
    payload = {
        "product_id": product_id,
        "executed": executed,
        "missing": missing,
        "checked_sections": list(required),
        "executed_at": time.time(),
    }
    out = root / "state" / product_id / "release_protocol_execution.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload

