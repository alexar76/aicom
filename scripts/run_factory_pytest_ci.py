#!/usr/bin/env python3
"""Run factory tests with coverage and a hard deadline; never infer success from coverage."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
from contextlib import suppress
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
        sys.executable,
        "-m",
        "coverage",
        "run",
        "-m",
        "pytest",
        *common,
        *extra,
    ]


def _terminate(proc: subprocess.Popen[bytes], grace_sec: float = 15.0) -> int | None:
    """Reap the runner and stop its process group, including browser/server children."""
    with suppress(ProcessLookupError):
        os.killpg(proc.pid, signal.SIGTERM)
    try:
        proc.wait(timeout=grace_sec)
    except subprocess.TimeoutExpired:
        pass
    finally:
        # The parent can exit before a child that ignores SIGTERM does.
        with suppress(ProcessLookupError):
            os.killpg(proc.pid, signal.SIGKILL)
    return proc.wait()


def main() -> int:
    try:
        hard_cap = int(os.environ.get("AIFACTORY_PYTEST_HARD_CAP_SEC", "600"))
        if hard_cap <= 0:
            raise ValueError("must be positive")
    except ValueError:
        print("AIFACTORY_PYTEST_HARD_CAP_SEC must be a positive integer", file=sys.stderr)
        return 2

    os.chdir(ROOT)
    try:
        # A failed run must not leave a previous run's report looking current.
        for name in (".coverage", "coverage.json"):
            (ROOT / name).unlink(missing_ok=True)
        proc = subprocess.Popen(_pytest_argv(), start_new_session=True)
    except OSError as exc:
        print(f"Could not start factory tests: {exc}", file=sys.stderr)
        return 2

    try:
        rc = proc.wait(timeout=hard_cap)
    except subprocess.TimeoutExpired:
        print(f"Factory tests exceeded {hard_cap}s; run is incomplete", file=sys.stderr)
        _terminate(proc)
        return 124
    except KeyboardInterrupt:
        _terminate(proc)
        return 130

    if rc != 0:
        return rc if rc > 0 else 128 - rc
    try:
        exported = subprocess.run(
            [sys.executable, "-m", "coverage", "json", "-o", "coverage.json"],
            check=False,
            timeout=60,
        ).returncode
        if exported:
            return exported
        return subprocess.run(
            [sys.executable, str(ROOT / "scripts/check_payment_coverage.py"), str(ROOT / "coverage.json")],
            check=False,
            timeout=60,
        ).returncode
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"Could not complete coverage checks: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
