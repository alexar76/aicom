"""
LLM provider circuit breaker — distributed self-healing layer.

State machine per provider:
  CLOSED → (≥ failure_threshold failures in failure_window_sec) → OPEN
  OPEN → (after open_duration_sec) → HALF_OPEN
  HALF_OPEN → success → CLOSED | failure → OPEN

State is persisted under ``state_dir()/llm_circuit_breakers.json`` with an
exclusive file lock so web backend and pipeline worker share one view.
"""

from __future__ import annotations

import enum
import json
import logging
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from core.paths import llm_circuit_state_path
from llm.usage_guard import _exclusive_file_lock

logger = logging.getLogger(__name__)

_STORE: Optional["CircuitBreakerStore"] = None
_STORE_LOCK = threading.Lock()


class CircuitState(str, enum.Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(RuntimeError):
    """Raised when a provider's circuit breaker blocks the request."""

    def __init__(self, provider: str, reason: str = "circuit_open"):
        self.provider = provider
        self.reason = reason
        super().__init__(f"Circuit breaker open for {provider}: {reason}")


@dataclass(frozen=True)
class CircuitBreakerConfig:
    failure_threshold: int = 5
    failure_window_sec: float = 60.0
    open_duration_sec: float = 30.0
    # If a HALF_OPEN probe never completes (worker crash, timeout), unblock after this many seconds.
    half_open_probe_timeout_sec: float = 120.0


def _default_provider_row() -> dict[str, Any]:
    now = time.time()
    return {
        "state": CircuitState.CLOSED.value,
        "failure_times": [],
        "opened_at": None,
        "half_open_since": None,
        "half_open_probe_in_flight": False,
        "half_open_probe_started_at": None,
        "last_failure_at": None,
        "last_success_at": None,
        "last_state_change_at": now,
        "last_error": "",
        "total_failures": 0,
        "total_opens": 0,
        "total_recoveries": 0,
        "last_recovery_duration_sec": None,
        "manual_override": None,
        "recent_events": [],
    }


def _prune_failures(failure_times: list[float], window_sec: float, now: float) -> list[float]:
    cutoff = now - window_sec
    return [t for t in failure_times if t >= cutoff]


def _append_event(row: dict[str, Any], event: str, detail: str = "") -> None:
    events = row.setdefault("recent_events", [])
    events.append({"ts": time.time(), "event": event, "detail": detail[:500]})
    if len(events) > 40:
        del events[:-40]


class CircuitBreakerStore:
    """File-backed multi-provider circuit breaker registry."""

    def __init__(
        self,
        state_path: Path | None = None,
        config: CircuitBreakerConfig | None = None,
    ):
        self._state_path = state_path or llm_circuit_state_path()
        self._lock_path = self._state_path.with_suffix(self._state_path.suffix + ".lock")
        self._config = config or CircuitBreakerConfig()

    def _load_all(self) -> dict[str, Any]:
        try:
            if not self._state_path.is_file():
                return {"providers": {}, "updated_at": time.time()}
            raw = json.loads(self._state_path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                return {"providers": {}, "updated_at": time.time()}
            providers = raw.get("providers")
            if not isinstance(providers, dict):
                providers = {}
            return {"providers": providers, "updated_at": float(raw.get("updated_at") or time.time())}
        except Exception as e:
            logger.warning("Could not load circuit breaker state: %s", e)
            return {"providers": {}, "updated_at": time.time()}

    def _persist_all(self, data: dict[str, Any]) -> None:
        data["updated_at"] = time.time()
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp.replace(self._state_path)

    def _ensure_row(self, providers: dict[str, Any], name: str) -> dict[str, Any]:
        row = providers.get(name)
        if not isinstance(row, dict):
            row = _default_provider_row()
            providers[name] = row
        return row

    def _transition(
        self,
        row: dict[str, Any],
        new_state: CircuitState,
        *,
        event: str,
        detail: str = "",
    ) -> None:
        old = row.get("state")
        if old == new_state.value:
            return
        row["state"] = new_state.value
        row["last_state_change_at"] = time.time()
        _append_event(row, event, detail)
        if new_state == CircuitState.OPEN:
            row["total_opens"] = int(row.get("total_opens") or 0) + 1
        if new_state == CircuitState.CLOSED and old in (CircuitState.OPEN.value, CircuitState.HALF_OPEN.value):
            row["total_recoveries"] = int(row.get("total_recoveries") or 0) + 1

    def _maybe_advance_from_open(self, row: dict[str, Any], now: float) -> None:
        if row.get("state") != CircuitState.OPEN.value:
            return
        opened_at = row.get("opened_at")
        if opened_at is None:
            return
        if now - float(opened_at) >= self._config.open_duration_sec:
            row["half_open_since"] = now
            row["half_open_probe_in_flight"] = False
            row["half_open_probe_started_at"] = None
            self._transition(row, CircuitState.HALF_OPEN, event="half_open_enter", detail="cooldown elapsed")

    def allow_request(self, provider: str) -> tuple[bool, str]:
        """Return (allowed, reason). Updates OPEN→HALF_OPEN when cooldown elapsed."""
        with _exclusive_file_lock(self._lock_path):
            data = self._load_all()
            providers = data["providers"]
            row = self._ensure_row(providers, provider)
            now = time.time()
            override = row.get("manual_override")
            if override == "force_open":
                self._persist_all(data)
                return False, "manual_force_open"
            if override == "force_closed":
                self._persist_all(data)
                return True, "manual_force_closed"

            state = row.get("state", CircuitState.CLOSED.value)
            if state == CircuitState.CLOSED.value:
                self._persist_all(data)
                return True, "closed"

            if state == CircuitState.OPEN.value:
                self._maybe_advance_from_open(row, now)
                state = row.get("state", CircuitState.OPEN.value)
                if state == CircuitState.OPEN.value:
                    self._persist_all(data)
                    return False, "circuit_open"
                # fell through to half_open

            if row.get("state") == CircuitState.HALF_OPEN.value:
                if row.get("half_open_probe_in_flight"):
                    started = row.get("half_open_probe_started_at")
                    stale = (
                        started is not None
                        and now - float(started) >= self._config.half_open_probe_timeout_sec
                    )
                    if stale:
                        logger.warning(
                            "Circuit HALF_OPEN probe for '%s' timed out after %.0fs — clearing stuck probe",
                            provider,
                            self._config.half_open_probe_timeout_sec,
                        )
                        row["half_open_probe_in_flight"] = False
                        row["half_open_probe_started_at"] = None
                        _append_event(row, "half_open_probe_timeout", detail="stale probe cleared")
                    else:
                        self._persist_all(data)
                        return False, "half_open_probe_busy"
                row["half_open_probe_in_flight"] = True
                row["half_open_probe_started_at"] = now
                self._persist_all(data)
                return True, "half_open_probe"

            self._persist_all(data)
            return True, "closed"

    def record_success(self, provider: str) -> dict[str, Any]:
        with _exclusive_file_lock(self._lock_path):
            data = self._load_all()
            providers = data["providers"]
            row = self._ensure_row(providers, provider)
            now = time.time()
            prev_state = row.get("state", CircuitState.CLOSED.value)
            row["last_success_at"] = now
            row["last_error"] = ""
            row["half_open_probe_in_flight"] = False
            row["half_open_probe_started_at"] = None
            row["failure_times"] = []

            if prev_state == CircuitState.HALF_OPEN.value:
                opened_at = row.get("opened_at")
                if opened_at is not None:
                    row["last_recovery_duration_sec"] = round(now - float(opened_at), 3)
                row["opened_at"] = None
                row["half_open_since"] = None
                self._transition(row, CircuitState.CLOSED, event="recovered", detail="probe succeeded")
            elif prev_state != CircuitState.CLOSED.value:
                row["opened_at"] = None
                row["half_open_since"] = None
                self._transition(row, CircuitState.CLOSED, event="closed", detail="success")

            self._persist_all(data)
            return self._public_row(provider, row, now)

    def record_failure(self, provider: str, error: str = "") -> dict[str, Any]:
        with _exclusive_file_lock(self._lock_path):
            data = self._load_all()
            providers = data["providers"]
            row = self._ensure_row(providers, provider)
            now = time.time()
            prev_state = row.get("state", CircuitState.CLOSED.value)
            row["last_failure_at"] = now
            row["last_error"] = (error or "")[:500]
            row["total_failures"] = int(row.get("total_failures") or 0) + 1
            row["half_open_probe_in_flight"] = False
            row["half_open_probe_started_at"] = None

            if prev_state == CircuitState.HALF_OPEN.value:
                row["opened_at"] = now
                self._transition(
                    row,
                    CircuitState.OPEN,
                    event="half_open_failed",
                    detail=row["last_error"],
                )
            else:
                failures = _prune_failures(
                    list(row.get("failure_times") or []),
                    self._config.failure_window_sec,
                    now,
                )
                failures.append(now)
                row["failure_times"] = failures
                if len(failures) >= self._config.failure_threshold:
                    row["opened_at"] = now
                    self._transition(
                        row,
                        CircuitState.OPEN,
                        event="threshold_tripped",
                        detail=f"{len(failures)} failures / {self._config.failure_window_sec}s",
                    )
                elif prev_state == CircuitState.CLOSED.value:
                    _append_event(row, "failure", detail=row["last_error"])

            self._persist_all(data)
            return self._public_row(provider, row, now)

    def force_open(self, provider: str, *, reason: str = "admin") -> dict[str, Any]:
        with _exclusive_file_lock(self._lock_path):
            data = self._load_all()
            row = self._ensure_row(data["providers"], provider)
            now = time.time()
            row["manual_override"] = "force_open"
            row["opened_at"] = now
            row["failure_times"] = []
            row["half_open_probe_in_flight"] = False
            row["half_open_probe_started_at"] = None
            self._transition(row, CircuitState.OPEN, event="manual_open", detail=reason)
            self._persist_all(data)
            return self._public_row(provider, row, now)

    def force_closed(self, provider: str, *, reason: str = "admin") -> dict[str, Any]:
        with _exclusive_file_lock(self._lock_path):
            data = self._load_all()
            row = self._ensure_row(data["providers"], provider)
            now = time.time()
            row["manual_override"] = "force_closed"
            row["opened_at"] = None
            row["half_open_since"] = None
            row["failure_times"] = []
            row["half_open_probe_in_flight"] = False
            row["half_open_probe_started_at"] = None
            self._transition(row, CircuitState.CLOSED, event="manual_close", detail=reason)
            self._persist_all(data)
            return self._public_row(provider, row, now)

    def reset(self, provider: str, *, reason: str = "admin") -> dict[str, Any]:
        with _exclusive_file_lock(self._lock_path):
            data = self._load_all()
            data["providers"][provider] = _default_provider_row()
            row = data["providers"][provider]
            _append_event(row, "reset", detail=reason)
            self._persist_all(data)
            return self._public_row(provider, row, time.time())

    def _public_row(self, provider: str, row: dict[str, Any], now: float) -> dict[str, Any]:
        failures = _prune_failures(
            list(row.get("failure_times") or []),
            self._config.failure_window_sec,
            now,
        )
        opened_at = row.get("opened_at")
        half_open_since = row.get("half_open_since")
        state = row.get("state", CircuitState.CLOSED.value)
        seconds_until_half_open: Optional[float] = None
        if state == CircuitState.OPEN.value and opened_at is not None:
            remaining = self._config.open_duration_sec - (now - float(opened_at))
            seconds_until_half_open = max(0.0, round(remaining, 2))

        return {
            "provider": provider,
            "state": state,
            "failure_count_window": len(failures),
            "failure_threshold": self._config.failure_threshold,
            "failure_window_sec": self._config.failure_window_sec,
            "open_duration_sec": self._config.open_duration_sec,
            "seconds_until_half_open": seconds_until_half_open,
            "opened_at": opened_at,
            "half_open_since": half_open_since,
            "last_failure_at": row.get("last_failure_at"),
            "last_success_at": row.get("last_success_at"),
            "last_state_change_at": row.get("last_state_change_at"),
            "last_error": row.get("last_error") or "",
            "last_recovery_duration_sec": row.get("last_recovery_duration_sec"),
            "total_failures": int(row.get("total_failures") or 0),
            "total_opens": int(row.get("total_opens") or 0),
            "total_recoveries": int(row.get("total_recoveries") or 0),
            "manual_override": row.get("manual_override"),
            "recent_events": list(row.get("recent_events") or [])[-8:],
        }

    def snapshot(self, provider_names: list[str] | None = None) -> dict[str, Any]:
        with _exclusive_file_lock(self._lock_path):
            data = self._load_all()
            providers = data["providers"]
            now = time.time()
            names = provider_names if provider_names is not None else sorted(providers.keys())
            out: dict[str, Any] = {}
            for name in names:
                row = self._ensure_row(providers, name)
                self._maybe_advance_from_open(row, now)
                out[name] = self._public_row(name, row, now)
            self._persist_all(data)
            return {
                "providers": out,
                "config": {
                    "failure_threshold": self._config.failure_threshold,
                    "failure_window_sec": self._config.failure_window_sec,
                    "open_duration_sec": self._config.open_duration_sec,
                },
                "updated_at": now,
            }


def get_circuit_store() -> CircuitBreakerStore:
    global _STORE
    with _STORE_LOCK:
        if _STORE is None:
            _STORE = CircuitBreakerStore()
        return _STORE


def sync_prometheus_from_snapshot(snapshot: dict[str, Any]) -> None:
    """Push circuit gauges/histograms from a store snapshot (best-effort)."""
    try:
        from web.backend.api.metrics import PrometheusMetrics

        for name, row in (snapshot.get("providers") or {}).items():
            PrometheusMetrics.set_circuit_state(name, str(row.get("state") or "closed"))
            recovery = row.get("last_recovery_duration_sec")
            if recovery is not None:
                PrometheusMetrics.observe_circuit_recovery(name, float(recovery))
    except Exception as e:
        logger.debug("circuit prometheus sync skipped: %s", e)
