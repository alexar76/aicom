"""
Quality Constitution
====================
Single release contract that must pass before a product is considered done.
"""

from __future__ import annotations

import json
from pathlib import Path


def evaluate_quality_constitution(product_id: str, data_root: str = "/app/data") -> dict:
    root = Path(data_root)
    issues: list[str] = []
    checks: dict[str, bool] = {}

    qa_path = root / "bugs" / product_id / "qa_report.json"
    qa_report = {}
    if qa_path.is_file():
        try:
            qa_report = json.loads(qa_path.read_text(encoding="utf-8"))
        except Exception:
            issues.append("qa_report_invalid")
    else:
        issues.append("qa_report_missing")

    qa_result = qa_report.get("qa_result") if isinstance(qa_report, dict) else {}
    gates = qa_result.get("quality_gates") if isinstance(qa_result, dict) else {}
    acceptance = gates.get("acceptance_traceability") if isinstance(gates, dict) else {}
    domain_pack = gates.get("domain_acceptance_pack") if isinstance(gates, dict) else {}
    maintainability = gates.get("maintainability_review") if isinstance(gates, dict) else {}
    browser = gates.get("browser_preview_e2e") if isinstance(gates, dict) else {}
    backend = gates.get("backend_runtime_e2e") if isinstance(gates, dict) else {}
    demo = gates.get("demo_quality") if isinstance(gates, dict) else {}
    perf_slo = gates.get("perf_slo") if isinstance(gates, dict) else {}

    checks["domain_e2e"] = bool(isinstance(domain_pack, dict) and domain_pack.get("passed"))
    checks["acceptance_traceability"] = bool(isinstance(acceptance, dict) and acceptance.get("passed"))
    checks["maintainability"] = bool(isinstance(maintainability, dict) and maintainability.get("passed"))
    checks["ux"] = bool(isinstance(demo, dict) and not (demo.get("issues") or []))
    checks["security"] = len(qa_result.get("security_issues", []) or []) == 0 if isinstance(qa_result, dict) else False
    checks["observability"] = (root / "telemetry" / product_id).exists()
    checks["perf"] = bool((root / "telemetry" / product_id / "benchmark_summary.json").exists())
    checks["perf_slo"] = bool(isinstance(perf_slo, dict) and perf_slo.get("passed"))
    traceability = gates.get("traceability_matrix") if isinstance(gates, dict) else {}
    checks["traceability_matrix"] = bool(isinstance(traceability, dict) and traceability.get("passed"))
    impl_plan_path = root / "code" / product_id / "implementation_plan.json"
    checks["implementation_plan"] = impl_plan_path.is_file()
    lifecycle_release_path = root / "state" / product_id / "lifecycle_release.json"
    checks["lifecycle_release"] = lifecycle_release_path.is_file()

    browser_ok = bool(browser.get("passed")) if isinstance(browser, dict) else False
    backend_ok = bool(backend.get("passed") or backend.get("skipped")) if isinstance(backend, dict) else False
    checks["runtime_e2e"] = browser_ok and backend_ok

    for key, ok in checks.items():
        if not ok:
            issues.append(f"{key}_failed")

    passed = len(issues) == 0
    return {"passed": passed, "checks": checks, "issues": issues}
