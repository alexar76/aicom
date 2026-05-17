from __future__ import annotations

import sys
import time
from unittest.mock import MagicMock

import pytest

# circuit_breaker tests must not require prometheus_client (pulled via llm.router in package init)
if "prometheus_client" not in sys.modules:
    sys.modules["prometheus_client"] = MagicMock()

from llm.circuit_breaker import CircuitBreakerConfig, CircuitBreakerStore, CircuitState


@pytest.fixture
def store(tmp_path):
    path = tmp_path / "circuits.json"
    return CircuitBreakerStore(
        state_path=path,
        config=CircuitBreakerConfig(
            failure_threshold=3,
            failure_window_sec=60.0,
            open_duration_sec=0.1,
        ),
    )


def test_closed_to_open_after_threshold(store: CircuitBreakerStore):
    for i in range(3):
        store.record_failure("deepseek", f"err{i}")
    snap = store.snapshot(["deepseek"])
    assert snap["providers"]["deepseek"]["state"] == CircuitState.OPEN.value


def test_open_blocks_requests(store: CircuitBreakerStore):
    store.force_open("groq")
    allowed, reason = store.allow_request("groq")
    assert allowed is False
    assert reason == "manual_force_open"


def _trip_open(store: CircuitBreakerStore, name: str) -> None:
    for i in range(3):
        store.record_failure(name, f"err{i}")


def test_half_open_recovery(store: CircuitBreakerStore):
    _trip_open(store, "anthropic")
    time.sleep(0.15)
    allowed, reason = store.allow_request("anthropic")
    assert allowed is True
    assert reason == "half_open_probe"
    store.record_success("anthropic")
    snap = store.snapshot(["anthropic"])
    assert snap["providers"]["anthropic"]["state"] == CircuitState.CLOSED.value
    assert snap["providers"]["anthropic"]["last_recovery_duration_sec"] is not None


def test_half_open_failure_reopens(store: CircuitBreakerStore):
    _trip_open(store, "together")
    time.sleep(0.15)
    store.allow_request("together")
    store.record_failure("together", "probe failed")
    snap = store.snapshot(["together"])
    assert snap["providers"]["together"]["state"] == CircuitState.OPEN.value


def test_manual_reset(store: CircuitBreakerStore):
    store.force_open("ollama")
    store.reset("ollama")
    snap = store.snapshot(["ollama"])
    row = snap["providers"]["ollama"]
    assert row["state"] == CircuitState.CLOSED.value
    assert row["manual_override"] is None
