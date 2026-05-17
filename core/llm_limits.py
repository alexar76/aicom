"""
LLM router limits — YAML slice under ``llm.limits`` + effective values (env wins).

Admin → LLM Providers panel reads/writes these; enforcement lives in ``llm.usage_guard``.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from core.config_merge import load_merged_config
from core.paths import config_path
from core.logging_utils import log_suppressed
from core.throughput_limits import (
    effective_llm_daily_cost_cap_usd,
    effective_llm_max_requests_per_minute,
    effective_llm_monthly_cost_cap_usd,
    effective_llm_pre_call_reserve_usd,
)

logger = logging.getLogger(__name__)

_CONFIG_PATH = config_path()

DEFAULT_LLM_LIMITS: dict[str, float | int] = {
    "max_requests_per_minute": 0,
    "daily_cost_cap_usd": 0.0,
    "monthly_cost_cap_usd": 0.0,
    "pre_call_reserve_usd": 0.05,
}

_CACHE_MTIME: float | None = None
_CACHE_SLICE: dict[str, Any] | None = None


def _coerce_int(val: Any, default: int, *, lo: int = 0, hi: int = 10**9) -> int:
    try:
        n = int(val)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, n))


def _coerce_float(val: Any, default: float, *, lo: float = 0.0, hi: float = 1_000_000.0) -> float:
    try:
        n = float(val)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, n))


def llm_limits_yaml_slice() -> dict[str, Any]:
    """Saved limits from layered config (defaults applied; not env-overridden)."""
    global _CACHE_MTIME, _CACHE_SLICE
    try:
        mtime = _CONFIG_PATH.stat().st_mtime
    except OSError:
        mtime = 0.0
    if _CACHE_MTIME == mtime and _CACHE_SLICE is not None:
        return dict(_CACHE_SLICE)

    out = dict(DEFAULT_LLM_LIMITS)
    try:
        raw = load_merged_config(_CONFIG_PATH)
        llm = raw.get("llm") if isinstance(raw, dict) else None
        limits = llm.get("limits") if isinstance(llm, dict) else None
        if isinstance(limits, dict):
            if "max_requests_per_minute" in limits:
                out["max_requests_per_minute"] = _coerce_int(
                    limits["max_requests_per_minute"], int(out["max_requests_per_minute"])
                )
            if "daily_cost_cap_usd" in limits:
                out["daily_cost_cap_usd"] = _coerce_float(
                    limits["daily_cost_cap_usd"], float(out["daily_cost_cap_usd"])
                )
            if "monthly_cost_cap_usd" in limits:
                out["monthly_cost_cap_usd"] = _coerce_float(
                    limits["monthly_cost_cap_usd"], float(out["monthly_cost_cap_usd"])
                )
            if "pre_call_reserve_usd" in limits:
                out["pre_call_reserve_usd"] = _coerce_float(
                    limits["pre_call_reserve_usd"], float(out["pre_call_reserve_usd"])
                )
    except Exception as _suppressed_exc:
        log_suppressed(logger, "non-fatal (core/llm_limits.py)", exc_info=_suppressed_exc)

    _CACHE_MTIME = mtime
    _CACHE_SLICE = dict(out)
    return out


def bump_llm_limits_cache_after_config_write() -> None:
    global _CACHE_MTIME, _CACHE_SLICE
    _CACHE_MTIME = None
    _CACHE_SLICE = None


def normalize_llm_limits_payload(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    base = llm_limits_yaml_slice()
    return {
        "max_requests_per_minute": _coerce_int(
            raw.get("max_requests_per_minute", base["max_requests_per_minute"]),
            int(base["max_requests_per_minute"]),
        ),
        "daily_cost_cap_usd": _coerce_float(
            raw.get("daily_cost_cap_usd", base["daily_cost_cap_usd"]),
            float(base["daily_cost_cap_usd"]),
        ),
        "monthly_cost_cap_usd": _coerce_float(
            raw.get("monthly_cost_cap_usd", base["monthly_cost_cap_usd"]),
            float(base["monthly_cost_cap_usd"]),
        ),
        "pre_call_reserve_usd": _coerce_float(
            raw.get("pre_call_reserve_usd", base["pre_call_reserve_usd"]),
            float(base["pre_call_reserve_usd"]),
            hi=100.0,
        ),
    }


def _env_override_flags() -> dict[str, bool]:
    return {
        "max_requests_per_minute": bool(os.environ.get("AIFACTORY_LLM_MAX_REQUESTS_PER_MINUTE", "").strip()),
        "daily_cost_cap_usd": bool(os.environ.get("AIFACTORY_LLM_DAILY_COST_CAP_USD", "").strip()),
        "monthly_cost_cap_usd": bool(os.environ.get("AIFACTORY_LLM_MONTHLY_COST_CAP_USD", "").strip()),
        "pre_call_reserve_usd": bool(os.environ.get("AIFACTORY_LLM_PRE_CALL_RESERVE_USD", "").strip()),
    }


def admin_llm_limits_panel_dict() -> dict[str, Any]:
    """Payload for Admin → LLM Providers limits card."""
    from llm.usage_guard import get_usage_guard

    saved = llm_limits_yaml_slice()
    usage = get_usage_guard().snapshot()
    return {
        "limits_saved": saved,
        "limits_effective": {
            "max_requests_per_minute": effective_llm_max_requests_per_minute(),
            "daily_cost_cap_usd": effective_llm_daily_cost_cap_usd(),
            "monthly_cost_cap_usd": effective_llm_monthly_cost_cap_usd(),
            "pre_call_reserve_usd": effective_llm_pre_call_reserve_usd(),
        },
        "usage": usage,
        "env_overrides": _env_override_flags(),
    }
