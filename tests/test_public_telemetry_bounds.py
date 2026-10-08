"""Public analytics / telemetry writes are anonymous: each is bounded in size and rate.

Before: /api/marketing/analytics had no limiter and an unbounded `meta` (nginx allowed 128 MB),
and evolution-signal `context` went unbounded into an agent prompt.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def client(tmp_path):
    from fastapi.testclient import TestClient

    from web.backend.main import app

    with TestClient(app) as c:
        root = tmp_path / "telemetry_root"
        root.mkdir()
        c.app.state.telemetry.data_root = root
        yield c


def test_oversized_analytics_meta_is_refused(client):
    r = client.post("/api/marketing/analytics", json={"event": "page_view", "meta": {"x": "a" * 10000}})
    assert r.status_code == 422


def test_analytics_writes_are_rate_limited(client, monkeypatch):
    import web.backend.api.marketing as m

    monkeypatch.setattr(m, "_ANALYTICS_MAX_PER_HOUR", 2)
    codes = [client.post("/api/marketing/analytics", json={"event": f"cta_{i}"},
                         headers={"X-Forwarded-For": "198.51.100.77"}).status_code for i in range(3)]
    assert codes[-1] == 429


def test_oversized_evolution_context_is_refused(client):
    r = client.post("/api/telemetry/evolution-signal",
                    json={"product_id": "prod-abc123", "signal": "churn_risk", "context": {"note": "b" * 10000}})
    assert r.status_code == 422


def test_evolution_signals_reach_the_prompt_as_untrusted_data():
    import inspect

    import agents.evolution_analyst as ea

    src = inspect.getsource(ea)
    assert "wrap_untrusted_for_llm_embedding(prompt_json(evolution_signals" in src
