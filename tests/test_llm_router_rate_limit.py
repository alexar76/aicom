from __future__ import annotations

import asyncio
import time

import pytest

from llm.router import LLMRouter


class _FakeProvider:
    def __init__(self):
        class _Health:
            status = type("S", (), {"value": "healthy"})()
            latency_ms = 1

        self.health = _Health()

    async def generate(self, prompt, config):
        await asyncio.sleep(0)
        return "ok"


@pytest.mark.asyncio
async def test_router_rate_limit_interval(monkeypatch):
    monkeypatch.setenv("AIFACTORY_LLM_MAX_PARALLEL_REQUESTS", "2")
    monkeypatch.setenv("AIFACTORY_LLM_MIN_INTERVAL_SEC", "0.05")
    router = LLMRouter()
    router.providers = {"fake": _FakeProvider()}
    router.default_provider = "fake"
    router.routing_rules = [{"task_type": "code_generation", "preferred_provider": "fake", "timeout_sec": 5}]

    t0 = time.monotonic()
    await asyncio.gather(
        router.generate("a", "code_generation"),
        router.generate("b", "code_generation"),
        router.generate("c", "code_generation"),
    )
    elapsed = time.monotonic() - t0
    assert elapsed >= 0.1


@pytest.mark.asyncio
async def test_router_recovers_provider_through_half_open(monkeypatch, tmp_path):
    """A tripped provider must recover through generate() via the HALF_OPEN probe.

    Regression: the router called the stateful allow_request() twice per attempt
    (once in the loop gate, once inside _generate_via_provider), so the second
    call always saw the probe already 'in flight' and returned busy — the
    provider could never leave OPEN.
    """
    from llm.circuit_breaker import (
        CircuitBreakerConfig,
        CircuitBreakerStore,
        CircuitState,
    )

    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path))
    router = LLMRouter()
    router.providers = {"fake": _FakeProvider()}
    router.default_provider = "fake"
    router.routing_rules = [{"task_type": "code_generation", "preferred_provider": "fake", "timeout_sec": 5}]

    store = CircuitBreakerStore(
        state_path=tmp_path / "cb.json",
        config=CircuitBreakerConfig(failure_threshold=3, failure_window_sec=60.0, open_duration_sec=0.1),
    )
    router._circuit = store

    for i in range(3):
        store.record_failure("fake", f"e{i}")
    assert store.snapshot(["fake"])["providers"]["fake"]["state"] == CircuitState.OPEN.value

    time.sleep(0.15)  # cooldown elapses → next allow_request advances to HALF_OPEN
    out = await router.generate("hi", "code_generation")
    assert out == "ok"
    assert store.snapshot(["fake"])["providers"]["fake"]["state"] == CircuitState.CLOSED.value
