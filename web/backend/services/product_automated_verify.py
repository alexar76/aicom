"""Automated product verification (no LLM) for pipeline auto-recovery."""

from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path
from typing import Any

from core.child_env import scrub_child_env
from core.paths import code_dir, resolve_data_root
from core.quality_settings import demo_quality_min_score
from web.backend.services.backend_runtime_e2e import run_backend_runtime_e2e
from web.backend.services.demo_quality import assess_product_demo, quality_gates_pass
from web.backend.services.domain_methodology import get_domain_pack, select_domain_pack
from web.backend.services.methodology_review import review_implementation

logger = logging.getLogger(__name__)


def _load_spec(product_id: str, data_root: Path) -> dict[str, Any]:
    spec_path = data_root / "specs" / product_id / "specification.json"
    if not spec_path.is_file():
        return {"delivery_profile": "full_software"}
    try:
        import json

        payload = json.loads(spec_path.read_text(encoding="utf-8"))
    except Exception:
        return {"delivery_profile": "full_software"}
    inner = payload.get("specification")
    return inner if isinstance(inner, dict) else payload


def _run_pytest_if_present(product_root: Path) -> dict[str, Any]:
    has_tests = (product_root / "tests").is_dir() or bool(list(product_root.glob("test_*.py")))
    if not has_tests:
        return {"passed": True, "skipped": True, "exit_code": 0, "total": 0, "failed": 0}

    # The tests belong to a generated product. Pytest imports them and every
    # conftest.py it finds, so package isolation alone is not a privilege boundary.
    env = scrub_child_env(os.environ)
    env["PYTHONPATH"] = str(product_root)
    env.setdefault("DATABASE_URL", "sqlite:///:memory:")
    env.setdefault("ENVIRONMENT", "test")
    env.setdefault("PYTHONDONTWRITEBYTECODE", "1")
    try:
        timeout = int(os.environ.get("AIFACTORY_AUTOMATED_PYTEST_TIMEOUT_SEC", "120"))
    except ValueError:
        timeout = 120
    timeout = max(5, min(timeout, 600))
    try:
        proc = subprocess.run(
            [os.environ.get("AIFACTORY_PYTHON", "python3"), "-m", "pytest", "-q"],
            cwd=str(product_root),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        output = exc.stdout or ""
        if isinstance(output, bytes):
            output = output.decode("utf-8", errors="replace")
        return {
            "passed": False,
            "skipped": False,
            "exit_code": 124,
            "total": 1,
            "failed": 1,
            "reason": "pytest_timeout",
            "timeout_seconds": timeout,
            "stdout_tail": output[-1500:],
        }
    passed = proc.returncode == 0
    return {
        "passed": passed,
        "skipped": False,
        "exit_code": proc.returncode,
        "total": max(1, proc.stdout.count(" passed")) if passed else 1,
        "failed": 0 if passed else 1,
        "stdout_tail": (proc.stdout or "")[-1500:],
    }


def verify_product_automated(
    product_id: str,
    *,
    data_root: str | Path | None = None,
    require_tests: bool = True,
) -> dict[str, Any]:
    """
    Run pytest (when present), methodology, backend runtime E2E, and demo quality gates.
    Returns dict with ``passed`` bool and component reports.
    """
    pid = str(product_id or "").strip()
    root = resolve_data_root(data_root)
    product_root = code_dir(pid, data_root=root)
    spec = _load_spec(pid, root)

    if not product_root.is_dir():
        return {"passed": False, "reason": "no_code_dir", "product_id": pid}

    tests = _run_pytest_if_present(product_root)
    if require_tests and not tests.get("skipped") and not tests.get("passed"):
        return {
            "passed": False,
            "reason": "pytest_failed",
            "product_id": pid,
            "tests": tests,
        }

    domain = str(spec.get("domain") or "").strip()
    pack = get_domain_pack(domain) if domain else None
    if pack is None:
        pack = select_domain_pack(
            " ".join(str(spec.get(k) or "") for k in ("product_name", "description")),
            category=str(spec.get("category") or ""),
            spec=spec,
        )
    methodology = review_implementation(
        product_root,
        pack=pack,
        spec=spec,
        min_score=55,
    )
    backend = run_backend_runtime_e2e(pid, data_root=str(root))
    demo = assess_product_demo(pid, spec=spec, data_root=str(root))
    demo_ok = quality_gates_pass(demo, delivery_profile=str(spec.get("delivery_profile") or "full_software"))
    min_demo = demo_quality_min_score()

    strict_visual = [
        i
        for i in (demo.get("issues") or [])
        if isinstance(i, dict)
        and str(i.get("code", "")).startswith(("visual_app_", "visual_missing"))
    ]

    passed = (
        bool(methodology.get("passed"))
        and bool(backend.get("passed"))
        and demo_ok
        and not strict_visual
        and int(demo.get("score") or 0) >= min_demo
    )

    return {
        "passed": passed,
        "product_id": pid,
        "tests": tests,
        "methodology": methodology,
        "backend_runtime": backend,
        "demo": demo,
        "demo_ok": demo_ok,
        "strict_visual_count": len(strict_visual),
    }
