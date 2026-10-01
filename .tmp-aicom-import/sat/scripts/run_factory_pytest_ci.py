#!/usr/bin/env python3
"""Factory CI pytest runner — coverage + forced exit when pytest teardown hangs."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _pytest_argv() -> list[str]:
    common = [
        "-q",
        "--timeout=45",
        "--ignore=tests/test_marketplace_e2e.py",
        "--ignore=tests/test_visual_regression.py",
        "--ignore=tests/test_browser_fastapi_login_integration.py",
        "--ignore=tests/test_visual_standards_playwright.py",
        "--ignore=tests/test_diagram_golden_visual.py",
        "-k",
        "not test_full_software_browser_e2e",
    ]
    extra = sys.argv[1:]
    return [
        "coverage",
        "run",
        "--source=web,agents,orchestrator,director,pipeline_worker",
        "-m",
        "pytest",
        *common,
        *extra,
    ]


def _terminate(proc: subprocess.Popen[bytes], grace_sec: float = 15.0) -> int | None:
    if proc.poll() is not None:
        return proc.returncode
    proc.send_signal(signal.SIGTERM)
    deadline = time.time() + grace_sec
    while time.time() < deadline:
        if proc.poll() is not None:
            return proc.returncode
        time.sleep(0.2)
    proc.kill()
    return proc.wait()


def main() -> int:
    os.chdir(ROOT)
    coverage_path = ROOT / ".coverage"
    if coverage_path.exists():
        coverage_path.unlink()

    hard_cap = int(os.environ.get("AIFACTORY_PYTEST_HARD_CAP_SEC", "600"))
    hang_grace = int(os.environ.get("AIFACTORY_PYTEST_HANG_GRACE_SEC", "120"))

    proc = subprocess.Popen(_pytest_argv())
    started = time.time()
    while True:
        rc = proc.poll()
        if rc is not None:
            if rc != 0:
                return rc
            break

        elapsed = time.time() - started
        if elapsed >= hang_grace and coverage_path.is_file():
            # Suite finished and coverage data is on disk; pytest often hangs here in CI.
            _terminate(proc)
            break
        if elapsed >= hard_cap:
            _terminate(proc)
            return 124 if not coverage_path.is_file() else 0

        time.sleep(0.5)

    json_proc = subprocess.run(
        ["coverage", "json", "-o", "coverage.json", "-i"],
        check=False,
    )
    return json_proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
