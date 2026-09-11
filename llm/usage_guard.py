"""
LLM usage guard — cost caps (daily / monthly USD) and requests-per-minute limiting.

Monetary amounts use ``Decimal`` for precision.
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
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Any

from core.decimal_json import dumps as _json_dumps
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


def _to_decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0")


class LLMUsageLimitError(RuntimeError):
    """Raised when an LLM call would exceed configured spend caps."""

    def __init__(self, message: str, *, limit_type: str, spent_usd: Decimal, cap_usd: Decimal):
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
        "day_spend_usd": Decimal("0"),
        "month": _utc_month_key(),
        "month_spend_usd": Decimal("0"),
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
    """Tracks estimated USD spend and request rate across all workers."""

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
                state["day_spend_usd"] = _to_decimal(raw.get("day_spend_usd") or 0)
            if str(raw.get("month") or "") == month:
                state["month"] = month
                state["month_spend_usd"] = _to_decimal(raw.get("month_spend_usd") or 0)
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
            "day_spend_usd": float(round(state["day_spend_usd"], 6)),
            "month": state["month"],
            "month_spend_usd": float(round(state["month_spend_usd"], 6)),
            "request_times": state.get("request_times") or [],
            "updated_at": datetime.now(UTC).isoformat(),
        }
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._state_path.with_suffix(".tmp")
        tmp.write_text(_json_dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(self._state_path)

    @staticmethod
    def _rollover(state: dict[str, Any]) -> None:
        day = _utc_day_key()
        month = _utc_month_key()
        if state.get("day") != day:
            state["day"] = day
            state["day_spend_usd"] = Decimal("0")
        if state.get("month") != month:
            state["month"] = month
            state["month_spend_usd"] = Decimal("0")

    @staticmethod
    def _prune_request_times(state: dict[str, Any], now_wall: float) -> None:
        times = state.get("request_times") or []
        state["request_times"] = [t for t in times if now_wall - t < 60.0]

    def _check_cost_caps(self, state: dict[str, Any]) -> None:
        reserve = _to_decimal(effective_llm_pre_call_reserve_usd())
        daily_cap = _to_decimal(effective_llm_daily_cost_cap_usd())
        day_spend = state.get("day_spend_usd", Decimal("0"))
        if daily_cap > 0 and day_spend + reserve > daily_cap:
            raise LLMUsageLimitError(
                f"LLM daily cost cap exceeded (${day_spend:.4f} spent + ${reserve:.4f} reserve > ${daily_cap:.2f} cap)",
                limit_type="daily_cost_cap", spent_usd=day_spend, cap_usd=daily_cap,
            )
        monthly_cap = _to_decimal(effective_llm_monthly_cost_cap_usd())
        month_spend = state.get("month_spend_usd", Decimal("0"))
        if monthly_cap > 0 and month_spend + reserve > monthly_cap:
            raise LLMUsageLimitError(
                f"LLM monthly cost cap exceeded (${month_spend:.4f} spent + ${reserve:.4f} reserve > ${monthly_cap:.2f} cap)",
                limit_type="monthly_cost_cap", spent_usd=month_spend, cap_usd=monthly_cap,
            )

    def _reserve_slot_locked(self, state: dict[str, Any]) -> None:
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
        while True:
            try:
                with _exclusive_file_lock(self._lock_path):
                    state = self._load_shared_state()
                    self._reserve_slot_locked(state)
                    self._persist_shared_state(state)
                    return
            except _RpmWaitRequired as e:
                await asyncio.sleep(e.wait_seconds)

    def record_spend(self, usd: float) -> None:
        amount = _to_decimal(usd)
        if amount <= 0:
            return
        with self._thread_lock:
            with _exclusive_file_lock(self._lock_path):
                state = self._load_shared_state()
                self._rollover(state)
                state["day_spend_usd"] = state.get("day_spend_usd", Decimal("0")) + amount
                state["month_spend_usd"] = state.get("month_spend_usd", Decimal("0")) + amount
                self._persist_shared_state(state)

    def snapshot(self) -> dict[str, Any]:
        with self._thread_lock:
            with _exclusive_file_lock(self._lock_path):
                state = self._load_shared_state()
                self._rollover(state)
                return {
                    "day_spend_usd": float(state["day_spend_usd"]),
                    "month_spend_usd": float(state["month_spend_usd"]),
                    "daily_cap_usd": effective_llm_daily_cost_cap_usd(),
                    "monthly_cap_usd": effective_llm_monthly_cost_cap_usd(),
                    "pre_call_reserve_usd": effective_llm_pre_call_reserve_usd(),
                    "requests_per_minute_limit": effective_llm_max_requests_per_minute(),
                    "requests_last_minute": len(state.get("request_times") or []),
                }


class _RpmWaitRequired(Exception):
    def __init__(self, wait_seconds: float):
        self.wait_seconds = max(1.0, wait_seconds)


def get_usage_guard() -> LLMUsageGuard:
    global _GUARD
    if _GUARD is None:
        with _GUARD_LOCK:
            if _GUARD is None:
                _GUARD = LLMUsageGuard()
    return _GUARD


def reset_usage_guard_for_tests(guard: LLMUsageGuard | None = None) -> None:
    global _GUARD
    with _GUARD_LOCK:
        _GUARD = guard


def record_llm_call_spend(entry: dict[str, Any]) -> None:
    est = entry.get("estimated_cost_usd")
    if est is None:
        return
    try:
        get_usage_guard().record_spend(float(est))
    except (TypeError, ValueError):
        return
    from core.pipeline_cost_guard import ingest_llm_log_entry
    ingest_llm_log_entry(entry)
