#!/usr/bin/env python3
"""Unified smoke for full pipeline gates + browser validation."""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path


def _check_http(url: str, timeout: float = 10.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            ok = 200 <= int(resp.status) < 300
            print(f"[ok] {url} -> HTTP {resp.status}" if ok else f"[fail] {url} -> HTTP {resp.status}")
            return ok
    except (urllib.error.URLError, TimeoutError) as exc:
        print(f"[fail] {url} -> {exc}")
        return False


def _run_cmd(label: str, cmd: list[str], cwd: Path | None = None) -> int:
    print(f"\n=== {label} ===")
    print("$", " ".join(cmd))
    proc = subprocess.run(cmd, cwd=str(cwd) if cwd else None, check=False)
    if proc.returncode == 0:
        print(f"[ok] {label}")
    else:
        print(f"[fail] {label} (exit={proc.returncode})")
    return proc.returncode


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Full smoke: health checks + pytest demo gates + realistic browser E2E."
    )
    parser.add_argument(
        "product_id",
        help="Product id to verify with realistic static+browser combined bar.",
    )
    parser.add_argument(
        "--app-root",
        default=os.environ.get("AICOM_APP_ROOT", "/app"),
        help="Application root (default: AICOM_APP_ROOT or /app).",
    )
    parser.add_argument(
        "--frontend-url",
        default=os.environ.get("AICOM_FRONTEND_URL", "http://127.0.0.1:8080"),
        help="Frontend URL for smoke health check.",
    )
    parser.add_argument(
        "--api-url",
        default=os.environ.get("AICOM_API_URL", "http://127.0.0.1:8081"),
        help="API URL for smoke health check.",
    )
    args = parser.parse_args()

    app_root = Path(args.app_root)
    if not app_root.exists():
        print(f"[fail] app root does not exist: {app_root}")
        return 2

    api_health = f"{args.api_url.rstrip('/')}/api/health"
    frontend_home = f"{args.frontend_url.rstrip('/')}/"
    checks_ok = _check_http(api_health) and _check_http(frontend_home)

    pytest_rc = _run_cmd(
        "Pytest demo quality gates",
        [sys.executable, "-m", "pytest", "tests/test_demo_quality_gates.py", "-v", "--tb=short"],
        cwd=app_root,
    )

    smoke_rc = _run_cmd(
        "Realistic combined bar (static + browser E2E)",
        [sys.executable, str(app_root / "scripts" / "real_e2e_smoke.py"), args.product_id],
        cwd=app_root,
    )

    print("\n=== FINAL ===")
    if checks_ok and pytest_rc == 0 and smoke_rc == 0:
        print("FULL PIPELINE SMOKE: PASS")
        return 0
    print("FULL PIPELINE SMOKE: FAIL")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
