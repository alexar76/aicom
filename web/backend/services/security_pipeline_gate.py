"""
Pipeline gate for Security agent output — failed scans send the product back to Developer.
"""

from __future__ import annotations

import os
from typing import Any


def _env_truthy(name: str, default: str = "1") -> bool:
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes")


def security_scan_passes_pipeline_gate(scan: dict[str, Any]) -> tuple[bool, list[str]]:
    """
    Returns (ok, reasons). If ok is False, the worker should treat this like a blocking gate:
    BUG_FOUND → Developer fix loop (until gate passes or repair budget is exhausted).

    Env:
      AIFACTORY_SECURITY_GATE_STRICT — default on; when off, gate always passes.
      AIFACTORY_SECURITY_MIN_SCORE — minimum security_score (0–100), default 55.
      AIFACTORY_SECURITY_BLOCK_SEVERITIES — comma list (default critical,high).
      AIFACTORY_SECURITY_BLOCK_SECRET_HINTS — default off (heuristics can be noisy).
      AIFACTORY_SECURITY_BLOCK_DEP_RISKS — default on for severities in BLOCK_SEVERITIES.
    """
    if not _env_truthy("AIFACTORY_SECURITY_GATE_STRICT", "1"):
        return True, []

    if not isinstance(scan, dict):
        return False, ["security_scan_invalid_payload"]

    reasons: list[str] = []

    try:
        min_score = int(os.environ.get("AIFACTORY_SECURITY_MIN_SCORE", "55"))
    except ValueError:
        min_score = 55
    try:
        score = int(scan.get("security_score") or 0)
    except (TypeError, ValueError):
        score = 0
    if score < min_score:
        reasons.append(f"security_score_below_gate:{score}<{min_score}")

    raw_levels = os.environ.get("AIFACTORY_SECURITY_BLOCK_SEVERITIES", "critical,high")
    block_levels = {x.strip().lower() for x in raw_levels.split(",") if x.strip()}

    vulns = scan.get("vulnerabilities") or []
    blocked_vuln_count = 0
    for v in vulns:
        if not isinstance(v, dict):
            continue
        sev = str(v.get("severity", "")).lower().strip()
        if sev in block_levels:
            blocked_vuln_count += 1
    if blocked_vuln_count:
        reasons.append(f"blocked_severity_findings:{blocked_vuln_count}")

    if _env_truthy("AIFACTORY_SECURITY_BLOCK_SECRET_HINTS", "0"):
        secrets = scan.get("secrets_found") or []
        if secrets:
            reasons.append(f"secret_hints:{len(secrets)}")

    if _env_truthy("AIFACTORY_SECURITY_BLOCK_DEP_RISKS", "1"):
        deps = scan.get("dependency_risks") or []
        bad_dep = 0
        for d in deps:
            if not isinstance(d, dict):
                continue
            sev = str(d.get("severity", "")).lower().strip()
            if sev in block_levels:
                bad_dep += 1
        if bad_dep:
            reasons.append(f"dependency_risks:{bad_dep}")

    return (len(reasons) == 0, reasons)


def build_security_gate_feedback(scan: dict[str, Any], reasons: list[str]) -> dict[str, Any]:
    """Compact payload for Developer prompts (bounded size)."""
    vulns = scan.get("vulnerabilities") or []
    sev_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}

    def _sort_key(v: dict[str, Any]) -> tuple[int, str]:
        return (
            sev_order.get(str(v.get("severity", "")).lower(), 9),
            str(v.get("file") or ""),
        )

    sorted_v = sorted([v for v in vulns if isinstance(v, dict)], key=_sort_key)
    return {
        "passed": False,
        "gate_reasons": list(reasons),
        "security_score": scan.get("security_score"),
        "grade": scan.get("grade"),
        "summary": scan.get("summary"),
        "vulnerabilities": sorted_v[:50],
        "secrets_found": (scan.get("secrets_found") or [])[:20],
        "dependency_risks": (scan.get("dependency_risks") or [])[:30],
    }
