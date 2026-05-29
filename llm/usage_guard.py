"""
LLM usage guard — cost caps (daily / monthly USD) and requests-per-minute limiting.

Enforced in :class:`llm.router.LLMRouter` before each generate/stream call.
Spend is recorded from provider logs after each billed API response.

State is persisted under ``state_dir()/llm_usage_guard.json`` with an exclusive
file lock so multiple Uvicorn workers share one global RPM and spend budget.
"""

from __future__ import annotations

import asyncio
import fcntl
import json
import logging
import os
import threading
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from core.paths import state_dir
from core.throughput_limits import (
    effective_llm_daily_cost_cap_usd,
    effective_llm_max_requests_per_minute,
    effective_llm_monthly_cost_cap_usd,
    effective_llm_pre_call_reserve_usd,
)

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

logger = logging.getLogger(__name__)

_GUARD: LLMUsageGuard | None = None
_GUARD_LOCK = threading.Lock()


class LLMUsageLimitError(RuntimeError):
    """Raised when an LLM call would exceed configured spend caps."""

    def __init__(
        self,
        message: str,
        *,
        limit_type: str,
        spent_usd: float,
        cap_usd: float,
    ):
        super().__init__(message)
        self.limit_type = limit_type
        self.spent_usd = spent_usd
        self.cap_usd = cap_usd


def _utc_day_key() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")


def _utc_month_key() -> str:
    return datetime.now(UTC).strftime("%Y-%m")


def _empty_state() -> dict[str, Any]:
    return {
        "day": _utc_day_key(),
        "day_spend_usd": 0.0,
        "month": _utc_month_key(),
        "month_spend_usd": 0.0,
        "request_times": [],
    }


@contextmanager
def _exclusive_file_lock(lock_path: Path) -> Iterator[None]:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


class LLMUsageGuard:
    """Tracks estimated USD spend and request rate across all workers in the process group."""

    def __init__(self, state_path: Path | None = None):
        self._state_path = state_path or (state_dir() / "llm_usage_guard.json")
        self._lock_path = self._state_path.with_suffix(self._state_path.suffix + ".lock")
        self._thread_lock = threading.Lock()

    def _load_shared_state(self) -> dict[str, Any]:
        try:
            if not self._state_path.is_file():
                return _empty_state()
            raw = json.loads(self._state_path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                return _empty_state()
            state = _empty_state()
            day = _utc_day_key()
            month = _utc_month_key()
            if str(raw.get("day") or "") == day:
                state["day"] = day
                state["day_spend_usd"] = float(raw.get("day_spend_usd") or 0.0)
            if str(raw.get("month") or "") == month:
                state["month"] = month
                state["month_spend_usd"] = float(raw.get("month_spend_usd") or 0.0)
            times = raw.get("request_times")
            if isinstance(times, list):
                state["request_times"] = [float(t) for t in times if isinstance(t, (int, float))]
            return state
        except Exception as e:
            logger.warning("Could not load LLM usage guard state: %s", e)
            return _empty_state()

    def _persist_shared_state(self, state: dict[str, Any]) -> None:
        payload = {
            "day": state["day"],
            "day_spend_usd": round(float(state["day_spend_usd"]), 6),
            "month": state["month"],
            "month_spend_usd": round(float(state["month_spend_usd"]), 6),
            "request_times": state.get("request_times") or [],
            "updated_at": datetime.now(UTC).isoformat(),
        }
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(self._state_path)

    @staticmethod
    def _rollover(state: dict[str, Any]) -> None:
        day = _utc_day_key()
        month = _utc_month_key()
        if state.get("day") != day:
            state["day"] = day
            state["day_spend_usd"] = 0.0
        if state.get("month") != month:
            state["month"] = month
            state["month_spend_usd"] = 0.0

    @staticmethod
    def _prune_request_times(state: dict[str, Any], now_wall: float) -> None:
        times = state.get("request_times") or []
        state["request_times"] = [t for t in times if now_wall - t < 60.0]

    def _check_cost_caps(self, state: dict[str, Any]) -> None:
        reserve = effective_llm_pre_call_reserve_usd()
        daily_cap = effective_llm_daily_cost_cap_usd()
        day_spend = float(state.get("day_spend_usd") or 0.0)
        if daily_cap > 0 and day_spend + reserve > daily_cap:
            raise LLMUsageLimitError(
                f"LLM daily cost cap exceeded (${day_spend:.4f} spent + "
                f"${reserve:.4f} reserve > ${daily_cap:.2f} cap)",
                limit_type="daily_cost_cap",
                spent_usd=day_spend,
                cap_usd=daily_cap,
            )
        monthly_cap = effective_llm_monthly_cost_cap_usd()
        month_spend = float(state.get("month_spend_usd") or 0.0)
        if monthly_cap > 0 and month_spend + reserve > monthly_cap:
            raise LLMUsageLimitError(
                f"LLM monthly cost cap exceeded (${month_spend:.4f} spent + "
                f"${reserve:.4f} reserve > ${monthly_cap:.2f} cap)",
                limit_type="monthly_cost_cap",
                spent_usd=month_spend,
                cap_usd=monthly_cap,
            )

    def _reserve_slot_locked(self, state: dict[str, Any]) -> None:
        """Verify caps and consume an RPM slot when configured."""
        self._rollover(state)
        now_wall = time.time()
        max_rpm = effective_llm_max_requests_per_minute()
        if max_rpm > 0:
            self._prune_request_times(state, now_wall)
        self._check_cost_caps(state)
        if max_rpm > 0:
            if len(state.get("request_times") or []) >= max_rpm:
                oldest = min(state["request_times"])
                raise _RpmWaitRequired(60.0 - (now_wall - oldest))
            state.setdefault("request_times", []).append(now_wall)

    async def acquire(self) -> None:
        """Wait for a global RPM slot, then verify cost caps before issuing a request."""
        while True:
            try:
                with _exclusive_file_lock(self._lock_path):
                    state = self._load_shared_state()
                    self._reserve_slot_locked(state)
                    self._persist_shared_state(state)
                return
            except _RpmWaitRequired as wait:
                await asyncio.sleep(max(0.05, min(wait.seconds, 1.0)))

    def record_spend(self, usd: float) -> None:
        """Record estimated USD after a provider logs token usage."""
        try:
            amount = float(usd)
        except (TypeError, ValueError):
            return
        if amount <= 0:
            return
        with _exclusive_file_lock(self._lock_path):
            state = self._load_shared_state()
            self._rollover(state)
            state["day_spend_usd"] = float(state.get("day_spend_usd") or 0.0) + amount
            state["month_spend_usd"] = float(state.get("month_spend_usd") or 0.0) + amount
            self._persist_shared_state(state)

    def snapshot(self) -> dict[str, Any]:
        with _exclusive_file_lock(self._lock_path):
            state = self._load_shared_state()
            self._rollover(state)
            now_wall = time.time()
            self._prune_request_times(state, now_wall)
            return {
                "day": state["day"],
                "day_spend_usd": round(float(state.get("day_spend_usd") or 0.0), 6),
                "month": state["month"],
                "month_spend_usd": round(float(state.get("month_spend_usd") or 0.0), 6),
                "requests_last_minute": len(state.get("request_times") or []),
                "daily_cost_cap_usd": effective_llm_daily_cost_cap_usd(),
                "monthly_cost_cap_usd": effective_llm_monthly_cost_cap_usd(),
                "max_requests_per_minute": effective_llm_max_requests_per_minute(),
                "pre_call_reserve_usd": effective_llm_pre_call_reserve_usd(),
            }


class _RpmWaitRequired(Exception):
    def __init__(self, seconds: float):
        self.seconds = max(0.0, float(seconds))
        super().__init__(f"rpm wait {self.seconds:.3f}s")


def get_usage_guard() -> LLMUsageGuard:
    global _GUARD
    if _GUARD is not None:
        return _GUARD
    with _GUARD_LOCK:
        if _GUARD is None:
            _GUARD = LLMUsageGuard()
        return _GUARD


def reset_usage_guard_for_tests(guard: LLMUsageGuard | None = None) -> None:
    """Test helper — replace the process-wide guard instance."""
    global _GUARD
    with _GUARD_LOCK:
        _GUARD = guard


def record_llm_call_spend(entry: dict[str, Any]) -> None:
    """Hook for JSONL log rows — increments caps when ``estimated_cost_usd`` is set."""
    if not isinstance(entry, dict):
        return
    est = entry.get("estimated_cost_usd")
    if est is None:
        return
    try:
        get_usage_guard().record_spend(float(est))
    except (TypeError, ValueError):
        return
    try:
        from core.pipeline_cost_guard import ingest_llm_log_entry

        ingest_llm_log_entry(entry)
    except Exception:
        pass
