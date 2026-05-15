"""Tests for LLM cost caps and requests-per-minute guard."""

from __future__ import annotations

import asyncio
import time

import pytest

from llm.router import LLMRouter
from llm.usage_guard import LLMUsageGuard, LLMUsageLimitError, reset_usage_guard_for_tests


@pytest.fixture
def guard(tmp_path, monkeypatch):
    state = tmp_path / "state" / "llm_usage_guard.json"
    monkeypatch.setenv("AIFACTORY_STATE_DIR", str(tmp_path / "state"))
    g = LLMUsageGuard(state_path=state)
    reset_usage_guard_for_tests(g)
    yield g
    reset_usage_guard_for_tests(None)


def test_daily_cost_cap_blocks(guard, monkeypatch):
    monkeypatch.setenv("AIFACTORY_LLM_DAILY_COST_CAP_USD", "1.0")
    monkeypatch.setenv("AIFACTORY_LLM_PRE_CALL_RESERVE_USD", "0.10")
    guard.record_spend(0.95)

    with pytest.raises(LLMUsageLimitError) as exc:
        asyncio.run(guard.acquire())
    assert exc.value.limit_type == "daily_cost_cap"


def test_monthly_cost_cap_blocks(guard, monkeypatch):
    monkeypatch.setenv("AIFACTORY_LLM_MONTHLY_COST_CAP_USD", "2.0")
    monkeypatch.setenv("AIFACTORY_LLM_PRE_CALL_RESERVE_USD", "0.10")
    guard.record_spend(1.95)

    with pytest.raises(LLMUsageLimitError) as exc:
        asyncio.run(guard.acquire())
    assert exc.value.limit_type == "monthly_cost_cap"


def test_record_spend_persists(guard, monkeypatch):
    monkeypatch.setenv("AIFACTORY_LLM_DAILY_COST_CAP_USD", "0")
    guard.record_spend(0.42)
    snap = guard.snapshot()
    assert snap["day_spend_usd"] == pytest.approx(0.42)
    assert guard._state_path.is_file()


@pytest.mark.asyncio
async def test_rpm_waits_when_window_full(guard, monkeypatch):
    monkeypatch.setenv("AIFACTORY_LLM_MAX_REQUESTS_PER_MINUTE", "2")
    monkeypatch.setenv("AIFACTORY_LLM_DAILY_COST_CAP_USD", "0")

    await guard.acquire()
    await guard.acquire()
    guard._request_times[0] = time.monotonic() - 59.0

    t0 = time.monotonic()
    await guard.acquire()
    assert time.monotonic() - t0 >= 0.5


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
async def test_router_blocks_when_daily_cap_exceeded(monkeypatch):
    monkeypatch.setenv("AIFACTORY_LLM_DAILY_COST_CAP_USD", "0.01")
    monkeypatch.setenv("AIFACTORY_LLM_PRE_CALL_RESERVE_USD", "0.01")

    guard = LLMUsageGuard()
    guard.record_spend(0.01)
    reset_usage_guard_for_tests(guard)

    router = LLMRouter()
    router.providers = {"fake": _FakeProvider()}
    router.default_provider = "fake"
    router.routing_rules = [{"task_type": "code_generation", "preferred_provider": "fake", "timeout_sec": 5}]

    with pytest.raises(LLMUsageLimitError):
        await router.generate("hello", "code_generation")

    reset_usage_guard_for_tests(None)
