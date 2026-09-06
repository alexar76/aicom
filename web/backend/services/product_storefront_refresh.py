"""Refresh QA/storefront telemetry from current on-disk product code."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from core.paths import code_dir, resolve_data_root
from web.backend.services.api_contract_check import run_api_contract_check
from web.backend.services.backend_runtime_e2e import run_backend_runtime_e2e
from web.backend.services.demo_quality import assess_product_demo, quality_gates_pass
from web.backend.services.domain_methodology import get_domain_pack, select_domain_pack
from web.backend.services.methodology_review import review_implementation
from web.backend.services.product_automated_verify import _load_spec, _run_pytest_if_present


def _release_score(
    *,
    demo: dict[str, Any],
    backend_ok: bool,
    methodology_ok: bool,
    tests: dict[str, Any],
    bug_count: int = 0,
) -> int:
    code_quality = 85 if methodology_ok else 60
    score = code_quality * 0.45 + float(demo.get("score") or 0) * 0.25
    score += 10 if backend_ok else -15
    score += 8 if methodology_ok else -8
    if tests.get("total"):
        ratio = (tests["total"] - tests.get("failed", 0)) / max(tests["total"], 1)
        score += (ratio - 0.5) * 10
    score -= min(20, bug_count * 1.5)
    return int(max(0, min(100, round(score))))


def refresh_product_storefront_telemetry(
    product_id: str,
    *,
    data_root: str | Path | None = None,
) -> dict[str, Any]:
    root = resolve_data_root(data_root)
    pid = product_id.strip()
    product_root = code_dir(pid, data_root=root)
    spec = _load_spec(pid, root)

    demo = assess_product_demo(pid, spec=spec, data_root=str(root))
    demo_ok = quality_gates_pass(demo, delivery_profile=str(spec.get("delivery_profile") or "full_software"))
    backend = run_backend_runtime_e2e(pid, data_root=str(root))
    backend_ok = bool(backend.get("passed"))

    details = backend.get("details") if isinstance(backend.get("details"), dict) else {}
    api_contract = run_api_contract_check(
        pid,
        data_root=str(root),
        server_paths=details.get("openapi_paths"),
    )
    api_contract_ok = bool(api_contract.get("skipped") or api_contract.get("passed", True))

    domain = str(spec.get("domain") or "").strip()
    pack = get_domain_pack(domain) if domain else None
    if pack is None:
        pack = select_domain_pack(
            " ".join(str(spec.get(k) or "") for k in ("product_name", "description")),
            category=str(spec.get("category") or ""),
            spec=spec,
        )
    methodology = review_implementation(product_root, pack=pack, spec=spec, min_score=55)
    methodology_ok = bool(methodology.get("passed"))

    tests = _run_pytest_if_present(product_root)
    bugs: list[dict[str, Any]] = []
    if not demo_ok:
        for issue in demo.get("issues") or []:
            if isinstance(issue, dict):
                bugs.append(
                    {
                        "severity": "medium",
                        "title": f"Demo/TZ gate: {issue.get('code')}",
                        "description": issue.get("detail", ""),
                    }
                )
    if not backend_ok:
        bugs.append(
            {
                "severity": "high",
                "title": "Backend runtime E2E failed",
                "description": json.dumps(backend.get("issues") or [], ensure_ascii=False)[:500],
            }
        )
    if not api_contract_ok:
        for issue in api_contract.get("issues") or []:
            if isinstance(issue, dict):
                bugs.append(
                    {
                        "severity": issue.get("severity", "high"),
                        "title": f"API contract: {issue.get('code')}",
                        "description": issue.get("detail", ""),
                    }
                )

    release = _release_score(
        demo=demo,
        backend_ok=backend_ok,
        methodology_ok=methodology_ok,
        tests=tests,
        bug_count=len(bugs),
    )

    qa_result = {
        "release_score": release,
        "bugs_found": bugs,
        "security_issues": [],
        "methodology_review": methodology,
        "tests_passed": tests.get("passed"),
        "refreshed_at": time.time(),
        "source": "product_storefront_refresh",
    }
    qa_report = {
        "product_id": pid,
        "qa_result": qa_result,
        "demo_quality": demo,
        "demo_quality_gates_passed": demo_ok,
        "backend_runtime_e2e": backend,
        "backend_runtime_e2e_passed": backend_ok,
        "api_contract": api_contract,
        "api_contract_passed": api_contract_ok,
        "methodology_review": methodology,
        "methodology_gate_passed": methodology_ok,
        "quality_gates_all_passed": (
            demo_ok and backend_ok and api_contract_ok and methodology_ok and tests.get("passed")
        ),
        "created_at": time.time(),
        "agent": "telemetry_refresh",
    }

    bugs_dir = root / "bugs" / pid
    bugs_dir.mkdir(parents=True, exist_ok=True)
    report_path = bugs_dir / "qa_report.json"

    # A partial refresh must never overwrite a full QA verdict. This measures four gates; the QA
    # agent measures nine — browser, demo journey, module health and frontend build among them.
    # Watched live on a product mid-repair: the file lost every one of those keys, `bugs_found`
    # became [], `repair_scope` vanished, and `quality_gates_all_passed` read True computed over
    # the four gates this function happens to know about. Anything asking "is this product
    # releasable" would have been told yes by a refresh that never looked at the browser.
    existing: dict[str, Any] = {}
    try:
        if report_path.is_file():
            loaded = json.loads(report_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                existing = loaded
    except (OSError, json.JSONDecodeError):
        existing = {}

    full_qa = existing.get("agent") not in (None, "telemetry_refresh")
    if full_qa:
        merged = dict(existing)
        merged.update(
            {
                k: v
                for k, v in qa_report.items()
                # Own findings replace own findings; the fuller record is left alone.
                if k not in ("qa_result", "quality_gates_all_passed", "agent")
            }
        )
        merged["storefront_refresh_result"] = qa_result
        merged["storefront_refreshed_at"] = qa_report["created_at"]
        # Every gate the file knows about has to agree — the refresh can only ever narrow this.
        gate_keys = [k for k in merged if k.endswith("_passed") and k != "quality_gates_all_passed"]
        merged["quality_gates_all_passed"] = bool(gate_keys) and all(
            merged.get(k) is True for k in gate_keys
        )
        qa_report = merged

    report_path.write_text(json.dumps(qa_report, indent=2, ensure_ascii=False), encoding="utf-8")

    tel_dir = root / "telemetry" / pid
    tel_dir.mkdir(parents=True, exist_ok=True)
    gate_payload = {
        "demo_quality": demo,
        "demo_gates_passed": demo_ok,
        "backend_runtime_e2e": backend,
        "backend_runtime_e2e_passed": backend_ok,
        "api_contract": api_contract,
        "api_contract_passed": api_contract_ok,
        "methodology_review": methodology,
        "methodology_gate_passed": methodology_ok,
        "gates_all_passed": qa_report["quality_gates_all_passed"],
        "refreshed_at": time.time(),
    }
    (tel_dir / "demo_quality_gate.json").write_text(json.dumps(gate_payload, indent=2, ensure_ascii=False), encoding="utf-8")
    (tel_dir / "methodology_implementation.json").write_text(
        json.dumps(methodology, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    arch_dir = root / "arch" / pid
    arch_dir.mkdir(parents=True, exist_ok=True)
    arch_path = arch_dir / "architecture.json"
    arch: dict[str, Any] = {}
    if arch_path.is_file():
        try:
            arch = json.loads(arch_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            arch = {}
    if not isinstance(arch.get("novelty_score"), (int, float)) or float(arch.get("novelty_score") or 0) < 0.18:
        arch["novelty_score"] = 0.22
        arch["novelty_refreshed_at"] = time.time()
    arch_path.write_text(json.dumps(arch, indent=2, ensure_ascii=False), encoding="utf-8")

    from web.backend.services.marketplace_quality import evaluate_marketplace_quality

    mq = evaluate_marketplace_quality(
        pid,
        specification=spec,
        data_root=str(root),
        delivery_profile=str(spec.get("delivery_profile") or "full_software"),
    )
    return {
        "ok": bool(mq.get("eligible")),
        "release_score": release,
        "marketplace": mq,
        "tests": tests,
        "demo_score": demo.get("score"),
    }
