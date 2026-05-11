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
