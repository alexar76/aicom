"""
Runtime throughput presets for pipeline workers.

``general.local_high_throughput_enabled`` in ``config.yaml`` (Admin → Settings) selects
aggressive defaults suited to a powerful local machine (many cores / RAM, local Ollama).

Explicit ``AIFACTORY_*`` environment variables always win when set (non-empty).
Values are re-read when ``config.yaml`` mtime changes so toggling Settings applies without restart.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

_CONFIG_PATH = Path(os.environ.get("AIFACTORY_CONFIG_YAML", "/app/config.yaml"))
_cache_mtime: float | None = None
_cache_turbo: bool | None = None


def _turbo_enabled_uncached() -> bool:
    try:
        if not _CONFIG_PATH.is_file():
            return False
        raw = yaml.safe_load(_CONFIG_PATH.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return False
        g = raw.get("general")
        if not isinstance(g, dict):
            return False
        return bool(g.get("local_high_throughput_enabled", False))
    except Exception:
        return False


def local_high_throughput_enabled() -> bool:
    global _cache_mtime, _cache_turbo
    try:
        mtime = _CONFIG_PATH.stat().st_mtime
    except OSError:
        _cache_mtime, _cache_turbo = None, False
        return False
    if _cache_mtime == mtime and _cache_turbo is not None:
        return _cache_turbo
    _cache_mtime = mtime
    _cache_turbo = _turbo_enabled_uncached()
    return _cache_turbo


def _env_int(name: str) -> int | None:
    raw = os.environ.get(name)
    if raw is None or str(raw).strip() == "":
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _env_float(name: str) -> float | None:
    raw = os.environ.get(name)
    if raw is None or str(raw).strip() == "":
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def effective_max_running_tasks() -> int:
    v = _env_int("AIFACTORY_MAX_RUNNING_TASKS")
    if v is not None:
        return max(1, v)
    return 48 if local_high_throughput_enabled() else 16


def effective_task_executor_concurrency() -> int:
    v = _env_int("AIFACTORY_TASK_EXECUTOR_CONCURRENCY")
    if v is not None:
        return max(1, v)
    return 24 if local_high_throughput_enabled() else 6


def effective_batch_pipeline_max_start_per_cycle() -> int:
    v = _env_int("AIFACTORY_BATCH_PIPELINE_MAX_START_PER_CYCLE")
    if v is not None:
        return max(1, v)
    return 8 if local_high_throughput_enabled() else 2


def effective_batch_pipeline_active_limit() -> int:
    v = _env_int("AIFACTORY_BATCH_PIPELINE_ACTIVE_LIMIT")
    if v is not None:
        return max(1, v)
    return 96 if local_high_throughput_enabled() else 30


def effective_llm_max_parallel_requests() -> int:
    v = _env_int("AIFACTORY_LLM_MAX_PARALLEL_REQUESTS")
    if v is not None:
        return max(1, v)
    return 32 if local_high_throughput_enabled() else 8


def effective_llm_min_interval_sec() -> float:
    v = _env_float("AIFACTORY_LLM_MIN_INTERVAL_SEC")
    if v is not None:
        return max(0.0, v)
    return 0.0 if local_high_throughput_enabled() else 0.05


def throughput_snapshot() -> dict[str, Any]:
    """For debugging / admin diagnostics."""
    turbo = local_high_throughput_enabled()
    return {
        "local_high_throughput_enabled": turbo,
        "effective_max_running_tasks": effective_max_running_tasks(),
        "effective_task_executor_concurrency": effective_task_executor_concurrency(),
        "effective_batch_pipeline_max_start_per_cycle": effective_batch_pipeline_max_start_per_cycle(),
        "effective_batch_pipeline_active_limit": effective_batch_pipeline_active_limit(),
        "effective_llm_max_parallel_requests": effective_llm_max_parallel_requests(),
        "effective_llm_min_interval_sec": effective_llm_min_interval_sec(),
    }
