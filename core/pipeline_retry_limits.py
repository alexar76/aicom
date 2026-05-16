"""Central retry / recovery limits for pipeline tasks (env-overridable)."""

from __future__ import annotations

import os


def _env_int(name: str, default: int, *, lo: int = 1, hi: int = 100) -> int:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        return max(lo, min(hi, int(raw)))
    except (TypeError, ValueError):
        return default


def task_max_retries() -> int:
    """Per-task retries before the task is marked failed (default raised from 3 → 7)."""
    return _env_int("AIFACTORY_TASK_MAX_RETRIES", 7, lo=1, hi=25)


def pm_spec_auto_requeue_max() -> int:
    """How many times PM spec-gate failures auto-reopen the product instead of terminal FAILED."""
    return _env_int("AIFACTORY_PM_SPEC_AUTO_REQUEUE_MAX", 5, lo=0, hi=50)
