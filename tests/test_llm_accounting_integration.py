"""Real router/provider/pricing/ledger/circuit components; only external HTTP is simulated."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import httpx
import pytest
import pytest_asyncio
import yaml

import core.events as events
import llm.circuit_breaker as circuits
import llm.cost_guard as costs
import llm.pricing_estimate as pricing
import llm.usage_guard as usage
from llm.provider import GenerationConfig
from llm.router import LLMRouter

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [pytest.mark.asyncio, pytest.mark.component_integration]


@dataclass
class LLMSandbox:
    router: LLMRouter
    root: Path
    guard: usage.LLMUsageGuard
    requests: list[dict] = field(default_factory=list)
    primary_failures: int = 0

    def respond(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.requests.append({"host": request.url.host, **body})
        assert request.url.path == "/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer integration-test-only"
        if request.url.host == "primary.test" and self.primary_failures:
            self.primary_failures -= 1
            return httpx.Response(503, json={"error": "simulated provider unavailable"})
        if body["stream"]:
            chunks = [
                {"choices": [{"delta": {"content": "hello "}}]},
                {"choices": [{"delta": {"content": "world"}, "finish_reason": "stop"}]},
            ]
            text = "".join(f"data: {json.dumps(chunk)}\n\n" for chunk in chunks) + "data: [DONE]\n\n"
            return httpx.Response(200, text=text, headers={"content-type": "text/event-stream"})
        return httpx.Response(200, json={
            "choices": [{"message": {"content": "hello world"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 100, "total_tokens": 200},
        })

    def logs(self) -> list[dict]:
        return [json.loads(line) for line in (self.root / "logs" / "llm_calls.jsonl").read_text().splitlines()]

    def persisted_spend(self) -> float:
        # A new instance must read what the actual provider logged and the guard persisted.
        return usage.LLMUsageGuard(self.root / "state" / "usage.json").snapshot()["day_spend_usd"]


@pytest_asyncio.fixture
async def llm_stack(tmp_path, monkeypatch):
    for key, value in {
        "AIFACTORY_DATA_ROOT": str(tmp_path),
        "AIFACTORY_STATE_DIR": str(tmp_path / "state"),
        "AIFACTORY_LOGS_DIR": str(tmp_path / "logs"),
        "AIFACTORY_LLM_DAILY_COST_CAP_USD": "10",
        "AIFACTORY_LLM_MONTHLY_COST_CAP_USD": "0",
        "AIFACTORY_LLM_PRE_CALL_RESERVE_USD": "0.05",
        "AIFACTORY_LLM_MAX_REQUESTS_PER_MINUTE": "0",
        "AIFACTORY_LLM_MIN_INTERVAL_SEC": "0",
        "AIFACTORY_LLM_CACHE_ENABLED": "0",
        "AIFACTORY_LLM_CRITICAL_ESCALATION_ENABLED": "0",
        "AIFACTORY_COST_GUARD_TIGHT_THRESHOLD": "0.8",
        "AIFACTORY_COST_GUARD_CRITICAL_THRESHOLD": "0.95",
    }.items():
        monkeypatch.setenv(key, value)
    guard = usage.LLMUsageGuard(tmp_path / "state" / "usage.json")
    circuit = circuits.CircuitBreakerStore(
        state_path=tmp_path / "state" / "circuits.json",
        config=circuits.CircuitBreakerConfig(failure_threshold=1, open_duration_sec=0),
    )
    bus = events.EventBus()
    monkeypatch.setattr(usage, "_GUARD", guard)
    monkeypatch.setattr(circuits, "_STORE", circuit)
    monkeypatch.setattr(costs, "_cost_guard", None)
    monkeypatch.setattr(events, "_event_bus", bus)
    monkeypatch.setattr(pricing, "_yaml_cache", (0.0, {}))
    monkeypatch.setattr(pricing, "_unpriced_models", {})
    # Synthetic rates keep assertions independent of vendor prices.
    rates = {"input_per_mtok": 1000, "output_per_mtok": 3000, "blended_per_mtok": 2000}
    price_file = tmp_path / "pricing.yaml"
    price_file.write_text(yaml.safe_dump({"models": dict.fromkeys(("primary-heavy", "primary-light", "backup-heavy"), rates)}))
    monkeypatch.setenv("AIFACTORY_LLM_PRICING_YAML", str(price_file))
    config_file = tmp_path / "providers.yaml"
    config_file.write_text(yaml.safe_dump({
        "default_provider": "primary",
        "providers": {
            name: {
                "enabled": True, "provider_type": "openai_compatible",
                "base_url": f"https://{name}.test/v1", "api_key": "integration-test-only",
                "models": {"heavy": f"{name}-heavy"},
            } for name in ("primary", "backup")
        },
        "routing_rules": [{"task_type": task, "preferred_provider": "primary", "fallback_provider": "backup"}
                          for task in ("code_generation", "market_research")],
    }))
    router = LLMRouter(config_path=config_file)
    sandbox = LLMSandbox(router, tmp_path, guard)
    try:
        for provider in router.providers.values():
            # Keep the real provider; replace its network transport rather than generate().
            await provider._client.aclose()
            provider._client = httpx.AsyncClient(
                base_url=provider.base_url,
                headers={"authorization": "Bearer integration-test-only"},
                transport=httpx.MockTransport(sandbox.respond),
            )
        yield sandbox
    finally:
        for provider in router.providers.values():
            await provider.close()
        await bus.shutdown()


async def test_provider_tokens_reach_pricing_and_persisted_budget(llm_stack, monkeypatch):
    monkeypatch.setenv("AIFACTORY_LLM_DAILY_COST_CAP_USD", "0.5")
    monkeypatch.setenv("AIFACTORY_LLM_PRE_CALL_RESERVE_USD", "0.2")
    assert await llm_stack.router.generate("first") == "hello world"
    assert llm_stack.persisted_spend() == pytest.approx(0.4)
    log = llm_stack.logs()[0]
    assert (log["prompt_tokens"], log["completion_tokens"], log["estimated_cost_usd"]) == (100, 100, 0.4)
    with pytest.raises(usage.LLMUsageLimitError):
        await llm_stack.router.generate("second")
    assert len(llm_stack.requests) == 1, "an exhausted budget must not reach either upstream"
    assert llm_stack.persisted_spend() == pytest.approx(0.4)


@pytest.mark.parametrize("limit", ["daily", "monthly"])
@pytest.mark.parametrize("task_type,spend,expected_model,tier", [
    ("market_research", 8.5, "primary-light", "tight"),
    ("code_generation", 8.5, "primary-heavy", "tight"),
    ("code_generation", 9.5, "primary-light", "critical"),
])
async def test_real_usage_selects_budget_tier_and_outgoing_model(
    llm_stack, monkeypatch, limit, task_type, spend, expected_model, tier,
):
    if limit == "monthly":
        monkeypatch.setenv("AIFACTORY_LLM_DAILY_COST_CAP_USD", "0")
        monkeypatch.setenv("AIFACTORY_LLM_MONTHLY_COST_CAP_USD", "10")
    llm_stack.guard.record_spend(spend)
    llm_stack.router._provider_configs["primary"]["models"]["light"] = "primary-light"
    assert costs.get_cost_guard().budget_tier() == tier
    assert costs.get_cost_guard().snapshot()[f"{limit}_cost_cap_usd"] == 10
    assert await llm_stack.router.generate("model selection", task_type) == "hello world"
    assert llm_stack.requests[0]["model"] == expected_model
    assert llm_stack.persisted_spend() == pytest.approx(spend + 0.4)


async def test_http_failover_recovers_through_persisted_half_open_probe(llm_stack):
    llm_stack.primary_failures = 1
    assert await llm_stack.router.generate("first attempt") == "hello world"
    assert [(r["host"], r["model"]) for r in llm_stack.requests] == [
        ("primary.test", "primary-heavy"), ("backup.test", "backup-heavy"),
    ]
    disk = json.loads((llm_stack.root / "state" / "circuits.json").read_text())
    assert disk["providers"]["primary"]["state"] == "open"
    assert disk["providers"]["primary"]["total_failures"] == 1

    assert await llm_stack.router.generate("recovery probe") == "hello world"
    assert len(llm_stack.requests) == 3
    assert llm_stack.requests[-1]["host"] == "primary.test"
    reopened = circuits.CircuitBreakerStore(state_path=llm_stack.root / "state" / "circuits.json")
    row = reopened.snapshot(["primary"])["providers"]["primary"]
    assert row["state"] == "closed"
    assert row["total_recoveries"] == 1
    assert llm_stack.persisted_spend() == pytest.approx(0.8)
    assert [entry["success"] for entry in llm_stack.logs()] == [False, True, True]


async def test_streaming_books_spend_and_blocks_the_next_request(llm_stack, monkeypatch):
    cfg = GenerationConfig()
    text = "".join([token async for token in llm_stack.router.stream("stream me", config=cfg)])
    assert text == "hello world"
    assert cfg.finish_reason == "stop"
    spend = llm_stack.persisted_spend()
    assert spend > 0
    assert llm_stack.logs()[0]["estimated_cost_usd"] == spend
    monkeypatch.setenv("AIFACTORY_LLM_DAILY_COST_CAP_USD", str(spend))
    with pytest.raises(usage.LLMUsageLimitError):
        _ = [token async for token in llm_stack.router.stream("must be blocked")]
    assert len(llm_stack.requests) == 1


@pytest.mark.parametrize("stream", [False, True])
async def test_corrupt_ledger_prevents_all_upstream_traffic(llm_stack, stream):
    path = llm_stack.root / "state" / "usage.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b'{"day_spend_usd": broken and private')
    original = path.read_bytes()
    with pytest.raises(usage.LLMUsageStateError):
        if stream:
            _ = [token async for token in llm_stack.router.stream("blocked")]
        else:
            await llm_stack.router.generate("blocked")
    assert llm_stack.requests == []
    assert path.read_bytes() == original
