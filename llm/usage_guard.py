"""
LLM usage guard — cost caps (daily / monthly USD) and requests-per-minute limiting.

Enforced in :class:`llm.router.LLMRouter` before each generate/stream call.
Spend is recorded from provider logs after each billed API response.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from core.paths import state_dir
from core.throughput_limits import (
    effective_llm_daily_cost_cap_usd,
    effective_llm_max_requests_per_minute,
    effective_llm_monthly_cost_cap_usd,
    effective_llm_pre_call_reserve_usd,
)

logger = logging.getLogger(__name__)

_GUARD: Optional["LLMUsageGuard"] = None
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


class LLMUsageGuard:
    """Tracks estimated USD spend and request rate for the process."""

    def __init__(self, state_path: Path | None = None):
        self._state_path = state_path or (state_dir() / "llm_usage_guard.json")
        self._lock = threading.Lock()
        self._request_times: deque[float] = deque()
        self._day_key = ""
        self._month_key = ""
        self._day_spend_usd = 0.0
        self._month_spend_usd = 0.0
        self._load_state()

    def _utc_day_key(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def _utc_month_key(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m")

    def _rollover_if_needed(self) -> None:
        day = self._utc_day_key()
        month = self._utc_month_key()
        if day != self._day_key:
            self._day_key = day
            self._day_spend_usd = 0.0
        if month != self._month_key:
            self._month_key = month
            self._month_spend_usd = 0.0

    def _load_state(self) -> None:
        self._day_key = self._utc_day_key()
        self._month_key = self._utc_month_key()
        try:
            if not self._state_path.is_file():
                return
            raw = json.loads(self._state_path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                return
            if str(raw.get("day") or "") == self._day_key:
                self._day_spend_usd = float(raw.get("day_spend_usd") or 0.0)
            if str(raw.get("month") or "") == self._month_key:
                self._month_spend_usd = float(raw.get("month_spend_usd") or 0.0)
        except Exception as e:
            logger.warning("Could not load LLM usage guard state: %s", e)

    def _persist_state(self) -> None:
        try:
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "day": self._day_key,
                "day_spend_usd": round(self._day_spend_usd, 6),
                "month": self._month_key,
                "month_spend_usd": round(self._month_spend_usd, 6),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            self._state_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except Exception as e:
            logger.debug("Could not persist LLM usage guard state: %s", e)

    def _prune_request_times(self, now_mono: float) -> None:
        while self._request_times and now_mono - self._request_times[0] >= 60.0:
            self._request_times.popleft()

    def _check_cost_caps_locked(self) -> None:
        reserve = effective_llm_pre_call_reserve_usd()
        daily_cap = effective_llm_daily_cost_cap_usd()
        if daily_cap > 0 and self._day_spend_usd + reserve > daily_cap:
            raise LLMUsageLimitError(
                f"LLM daily cost cap exceeded (${self._day_spend_usd:.4f} spent + "
                f"${reserve:.4f} reserve > ${daily_cap:.2f} cap)",
                limit_type="daily_cost_cap",
                spent_usd=self._day_spend_usd,
                cap_usd=daily_cap,
            )
        monthly_cap = effective_llm_monthly_cost_cap_usd()
        if monthly_cap > 0 and self._month_spend_usd + reserve > monthly_cap:
            raise LLMUsageLimitError(
                f"LLM monthly cost cap exceeded (${self._month_spend_usd:.4f} spent + "
                f"${reserve:.4f} reserve > ${monthly_cap:.2f} cap)",
                limit_type="monthly_cost_cap",
                spent_usd=self._month_spend_usd,
                cap_usd=monthly_cap,
            )

    async def _wait_rpm_slot(self) -> None:
        max_rpm = effective_llm_max_requests_per_minute()
        if max_rpm <= 0:
            return
        while True:
            with self._lock:
                now = time.monotonic()
                self._prune_request_times(now)
                if len(self._request_times) < max_rpm:
                    return
                wait_sec = 60.0 - (now - self._request_times[0])
            await asyncio.sleep(max(0.01, min(wait_sec, 1.0)))

    async def acquire(self) -> None:
        """Wait for RPM slot, then verify cost caps before issuing a request."""
        await self._wait_rpm_slot()
        with self._lock:
            self._rollover_if_needed()
            self._check_cost_caps_locked()
            self._request_times.append(time.monotonic())

    def record_spend(self, usd: float) -> None:
        """Record estimated USD after a provider logs token usage."""
        try:
            amount = float(usd)
        except (TypeError, ValueError):
            return
        if amount <= 0:
            return
        with self._lock:
            self._rollover_if_needed()
            self._day_spend_usd += amount
            self._month_spend_usd += amount
            self._persist_state()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            self._rollover_if_needed()
            return {
                "day": self._day_key,
                "day_spend_usd": round(self._day_spend_usd, 6),
                "month": self._month_key,
                "month_spend_usd": round(self._month_spend_usd, 6),
                "requests_last_minute": len(self._request_times),
                "daily_cost_cap_usd": effective_llm_daily_cost_cap_usd(),
                "monthly_cost_cap_usd": effective_llm_monthly_cost_cap_usd(),
                "max_requests_per_minute": effective_llm_max_requests_per_minute(),
                "pre_call_reserve_usd": effective_llm_pre_call_reserve_usd(),
            }


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
