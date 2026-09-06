"""Run product E2E probes in a child process.

Playwright/Chromium and generated uvicorn apps can abort the interpreter
(segfault, SIGKILL). Those must not take down the pipeline worker.
"""

from __future__ import annotations

import json
import logging
import os
import signal
import subprocess
import sys
from typing import Any

logger = logging.getLogger(__name__)

# Chromium + Playwright in the same 4GiB cgroup as uvicorn/worker will OOM-kill
# the fattest python3 (the pipeline worker). Skip the spawn when free memory is low.
_DEFAULT_MIN_FREE_MB = 3200.0

_RUNNER = (
    "import json,sys\n"
    "from importlib import import_module\n"
    "mod=import_module(sys.argv[1])\n"
    "fn=getattr(mod,sys.argv[2])\n"
    "pid=sys.argv[3]\n"
    "root=sys.argv[4] or None\n"
    "json.dump(fn(pid, root), sys.stdout, default=str)\n"
)


def cgroup_memory_bytes() -> tuple[int | None, int | None]:
    """Return ``(current, max)`` from cgroup v2, or ``(None, None)`` if unavailable."""
    current_p = "/sys/fs/cgroup/memory.current"
    max_p = "/sys/fs/cgroup/memory.max"
    try:
        current = int(open(current_p, encoding="utf-8").read().strip())
    except (OSError, ValueError):
        return None, None
    try:
        raw_max = open(max_p, encoding="utf-8").read().strip()
        if raw_max == "max":
            return current, None
        return current, int(raw_max)
    except (OSError, ValueError):
        return current, None


def browser_e2e_memory_ok(*, min_free_mb: float | None = None) -> tuple[bool, str]:
    """Whether this cgroup can absorb a Chromium probe without OOM-killing the worker."""
    if min_free_mb is None:
        raw = os.environ.get("AIFACTORY_BROWSER_E2E_MIN_FREE_MB", str(int(_DEFAULT_MIN_FREE_MB)))
        try:
            min_free_mb = float(raw)
        except ValueError:
            min_free_mb = _DEFAULT_MIN_FREE_MB
    current, maximum = cgroup_memory_bytes()
    if current is None or maximum is None or maximum <= 0:
        return True, "cgroup_memory_unknown"
    free_mb = (maximum - current) / (1024 * 1024)
    if free_mb < min_free_mb:
        return False, (
            f"cgroup_free_mb={free_mb:.0f} min_free_mb={min_free_mb:.0f} "
            f"current_mb={current / (1024 * 1024):.0f} max_mb={maximum / (1024 * 1024):.0f}"
        )
    return True, f"cgroup_free_mb={free_mb:.0f}"


def _kill_group(proc: subprocess.Popen) -> None:
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        try:
            proc.kill()
        except OSError:
            pass


def run_e2e_in_subprocess(
    *,
    module: str,
    func: str,
    product_id: str,
    data_root: str | None,
    timeout_sec: float,
) -> dict[str, Any]:
    """Invoke ``module.func(product_id, data_root)`` out of process; always return a dict."""
    if "browser_preview_e2e" in module:
        from core.quality_settings import browser_e2e_enabled

        if not browser_e2e_enabled():
            return {
                "passed": True,
                "skipped": True,
                "reason": "Browser E2E disabled (quality.browser_e2e_enabled / AIFACTORY_BROWSER_E2E)",
            }
        ok, detail = browser_e2e_memory_ok()
        if not ok:
            logger.warning("skipping browser E2E spawn: %s", detail)
            return {
                "passed": True,
                "skipped": True,
                "error": "e2e_skipped_low_memory",
                "detail": detail,
            }
    cmd = [
        sys.executable,
        "-c",
        _RUNNER,
        module,
        func,
        str(product_id),
        "" if data_root is None else str(data_root),
    ]
    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
            env=env,
        )
    except OSError as exc:
        logger.warning("e2e subprocess spawn failed: %s", exc)
        return {
            "passed": False,
            "skipped": False,
            "error": "e2e_subprocess_spawn_failed",
            "detail": str(exc)[:400],
        }
    try:
        stdout, stderr = proc.communicate(timeout=max(5.0, float(timeout_sec)))
    except subprocess.TimeoutExpired:
        _kill_group(proc)
        try:
            proc.communicate(timeout=5)
        except Exception:
            pass
        logger.warning("e2e subprocess timed out after %.0fs (%s.%s)", timeout_sec, module, func)
        return {
            "passed": False,
            "skipped": False,
            "error": "e2e_subprocess_timeout",
            "detail": f"{module}.{func} exceeded {timeout_sec:.0f}s",
        }
    if proc.returncode != 0:
        logger.warning(
            "e2e subprocess exited %s (%s.%s): %s",
            proc.returncode,
            module,
            func,
            (stderr or "")[:400],
        )
        return {
            "passed": False,
            "skipped": False,
            "error": "e2e_subprocess_exited",
            "detail": (stderr or stdout or f"exit {proc.returncode}")[:800],
            "returncode": proc.returncode,
        }
    try:
        parsed = json.loads(stdout or "{}")
    except json.JSONDecodeError:
        return {
            "passed": False,
            "skipped": False,
            "error": "e2e_subprocess_bad_json",
            "detail": (stdout or "")[:400],
        }
    if not isinstance(parsed, dict):
        return {
            "passed": False,
            "skipped": False,
            "error": "e2e_subprocess_non_dict",
            "detail": type(parsed).__name__,
        }
    return parsed
