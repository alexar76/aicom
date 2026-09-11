from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from director.discovery_pipeline import DiscoveryPipeline, SourceRuntime, compute_idea_score


def test_compute_idea_score_range() -> None:
    metrics = {
        "tam": 11,
        "pain_severity": 8,
        "differentiation": 7,
        "feasibility": 6,
        "strategic_fit": 6,
        "evidence_strength": 9,
        "implementation_effort_inverse": -2,
    }
    out = compute_idea_score(metrics)
    assert 0 <= out["total"] <= 10
    assert 0 <= out["confidence"] <= 10


@pytest.mark.asyncio
async def test_discovery_run_with_fallback(tmp_path: Path) -> None:
    class DummyRouter:
        async def generate(self, prompt: str, task_type: str, config):  # noqa: ANN001
            return '{"ideas": []}'

    pipeline = DiscoveryPipeline(router=DummyRouter(), data_dir=tmp_path / "discovery")
    result = await pipeline.run(existing_ideas=[], existing_categories=["saas", "saas"])
    assert result["ranked_ideas"]
    top = result["ranked_ideas"][0]
    assert top["category"] in {"ai_ml", "devtools", "fintech", "saas", "ecommerce", "iot", "security", "productivity"}
    assert (tmp_path / "discovery" / "ranked_ideas.json").exists()
    stored = json.loads((tmp_path / "discovery" / "ranked_ideas.json").read_text(encoding="utf-8"))
    assert stored["ranked_ideas"][0]["idea"]


def test_signal_pruning_ttl_and_size(tmp_path: Path) -> None:
    class DummyRouter:
        async def generate(self, prompt: str, task_type: str, config):  # noqa: ANN001
            return '{"ideas": []}'

    d = tmp_path / "discovery"
    d.mkdir(parents=True, exist_ok=True)
    signals_path = d / "signals.jsonl"
    now = int(time.time())
    rows = []
    for i in range(8):
        rows.append(
            {
                "source": "hn",
                "url": f"https://example.com/{i}",
                "timestamp": now - (40 * 86400 if i < 3 else 10),
            }
        )
    signals_path.write_text("\n".join(json.dumps(x) for x in rows) + "\n", encoding="utf-8")
    pipeline = DiscoveryPipeline(router=DummyRouter(), data_dir=d)
    pipeline.signal_ttl_days = 30
    pipeline.signal_max_rows = 4
    stat = pipeline.prune_signals()
    assert stat["before"] == 8
    assert stat["after"] == 4
    kept = [json.loads(x) for x in signals_path.read_text(encoding="utf-8").splitlines() if x.strip()]
    assert len(kept) == 4


def test_source_runtime_rate_and_backoff() -> None:
    rt = SourceRuntime("reddit", min_interval_sec=2.0, max_backoff_sec=10.0)
    now = time.time()
    ok, _ = rt.can_call(now)
    assert ok
    rt.mark_call(now, 50)
    ok2, reason2 = rt.can_call(now + 0.5)
    assert not ok2
    assert "rate_limited" in reason2

    rt.mark_failure(now + 1.0, "boom")
    ok3, reason3 = rt.can_call(now + 1.5)
    assert not ok3
    assert "backoff_active" in reason3
