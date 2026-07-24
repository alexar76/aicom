"""
Runtime throughput presets for pipeline workers.

``general.local_high_throughput_enabled`` in layered platform config (Admin → Settings) selects
aggressive defaults suited to a powerful local machine (many cores / RAM, local Ollama).

Explicit ``AIFACTORY_*`` environment variables always win when set (non-empty).
Values are re-read when the primary config file mtime changes so toggling Settings applies without restart.
"""

from __future__ import annotations

import os
from typing import Any

from core.config_merge import load_merged_config
from core.paths import config_path

_CONFIG_PATH = config_path()
_cache_mtime: float | None = None
_cache_turbo: bool | None = None


def _turbo_enabled_uncached() -> bool:
    try:
        if not _CONFIG_PATH.is_file():
            return False
        raw = load_merged_config(_CONFIG_PATH)
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


def _env_bool(name: str) -> bool | None:
    raw = os.environ.get(name)
    if raw is None or str(raw).strip() == "":
        return None
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


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


def _llm_limits_from_config() -> dict[str, Any]:
    try:
        raw = load_merged_config(_CONFIG_PATH)
        if not isinstance(raw, dict):
            return {}
        llm = raw.get("llm")
        if not isinstance(llm, dict):
            return {}
        limits = llm.get("limits")
        return limits if isinstance(limits, dict) else {}
    except Exception:
        return {}


def _limit_float_from_config(key: str) -> float | None:
    lim = _llm_limits_from_config()
    val = lim.get(key)
    if isinstance(val, (int, float)):
        return float(val)
    return None


def _llm_section_from_config() -> dict[str, Any]:
    try:
        raw = load_merged_config(_CONFIG_PATH)
        if not isinstance(raw, dict):
            return {}
        llm = raw.get("llm")
        return llm if isinstance(llm, dict) else {}
    except Exception:
        return {}


def effective_llm_critical_escalation_enabled() -> bool:
    """Whether critical tasks may escalate ACROSS providers when the default fails.

    When False (default), a failing default provider only fails over to a rule's
    explicit ``fallback_provider`` — routing stays within the configured default
    unless an operator wired an alternative per task. When True, a critical task
    (see ``llm.cost_guard._CRITICAL_TASK_TYPES``) whose default provider is
    unhealthy / erroring will additionally fail over to the highest-priority
    *other* provider that has credentials configured. This intentionally widens
    routing from "strong vs light model within the default provider" to
    "across providers", so it is opt-in.

    Env ``AIFACTORY_LLM_CRITICAL_ESCALATION_ENABLED`` overrides the
    ``llm.critical_escalation_enabled`` platform-config value.
    """
    v = _env_bool("AIFACTORY_LLM_CRITICAL_ESCALATION_ENABLED")
    if v is not None:
        return v
    return bool(_llm_section_from_config().get("critical_escalation_enabled", False))


def effective_llm_max_requests_per_minute() -> int:
    v = _env_int("AIFACTORY_LLM_MAX_REQUESTS_PER_MINUTE")
    if v is not None:
        return max(0, v)
    cfg = _limit_float_from_config("max_requests_per_minute")
    if cfg is not None:
        return max(0, int(cfg))
    return 0


def effective_llm_daily_cost_cap_usd() -> float:
    v = _env_float("AIFACTORY_LLM_DAILY_COST_CAP_USD")
    if v is not None:
        return max(0.0, v)
    cfg = _limit_float_from_config("daily_cost_cap_usd")
    if cfg is not None:
        return max(0.0, cfg)
    return 0.0


def effective_llm_monthly_cost_cap_usd() -> float:
    v = _env_float("AIFACTORY_LLM_MONTHLY_COST_CAP_USD")
    if v is not None:
        return max(0.0, v)
    cfg = _limit_float_from_config("monthly_cost_cap_usd")
    if cfg is not None:
        return max(0.0, cfg)
    return 0.0


def effective_llm_pre_call_reserve_usd() -> float:
    v = _env_float("AIFACTORY_LLM_PRE_CALL_RESERVE_USD")
    if v is not None:
        return max(0.0, v)
    cfg = _limit_float_from_config("pre_call_reserve_usd")
    if cfg is not None:
        return max(0.0, cfg)
    if effective_llm_daily_cost_cap_usd() > 0 or effective_llm_monthly_cost_cap_usd() > 0:
        return 0.05
    return 0.0


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
        "effective_llm_max_requests_per_minute": effective_llm_max_requests_per_minute(),
        "effective_llm_daily_cost_cap_usd": effective_llm_daily_cost_cap_usd(),
        "effective_llm_monthly_cost_cap_usd": effective_llm_monthly_cost_cap_usd(),
        "effective_llm_pre_call_reserve_usd": effective_llm_pre_call_reserve_usd(),
        "effective_llm_critical_escalation_enabled": effective_llm_critical_escalation_enabled(),
    }
