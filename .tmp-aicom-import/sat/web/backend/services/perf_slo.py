"""
Performance / SLO evaluation
============================
Evaluates lightweight release SLOs based on QA runtime signals.
"""

from __future__ import annotations

import os
from typing import Any


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except ValueError:
        return default


def evaluate_perf_slo(browser_e2e: dict[str, Any], backend_e2e: dict[str, Any]) -> dict[str, Any]:
    """
    Return perf gate status from runtime probes.
    Defaults are intentionally conservative for generated apps.
    """
    ttfb_budget = _env_int("AIFACTORY_SLO_TTFB_MS_MAX", 1500)
    dcl_budget = _env_int("AIFACTORY_SLO_DCL_MS_MAX", 3500)
    load_budget = _env_int("AIFACTORY_SLO_LOAD_MS_MAX", 6000)

    issues: list[str] = []
    perf = browser_e2e.get("performance") if isinstance(browser_e2e, dict) else {}
    if not isinstance(perf, dict):
        perf = {}
    ttfb = int(perf.get("ttfb_ms") or 0)
    dcl = int(perf.get("dom_content_loaded_ms") or 0)
    load = int(perf.get("load_event_ms") or 0)

    if ttfb and ttfb > ttfb_budget:
        issues.append(f"ttfb_too_high:{ttfb}>{ttfb_budget}")
    if dcl and dcl > dcl_budget:
        issues.append(f"dcl_too_high:{dcl}>{dcl_budget}")
    if load and load > load_budget:
        issues.append(f"load_too_high:{load}>{load_budget}")

    backend_passed = bool((backend_e2e or {}).get("passed") or (backend_e2e or {}).get("skipped"))
    if not backend_passed:
        issues.append("backend_runtime_unstable")

    passed = len(issues) == 0
    return {
        "passed": passed,
        "issues": issues,
        "thresholds": {
            "ttfb_ms_max": ttfb_budget,
            "dom_content_loaded_ms_max": dcl_budget,
            "load_event_ms_max": load_budget,
        },
        "observed": {"ttfb_ms": ttfb, "dom_content_loaded_ms": dcl, "load_event_ms": load},
    }

