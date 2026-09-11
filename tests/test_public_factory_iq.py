"""Public Factory IQ API — whitelist boundary (R7).

``GET /api/public/factory-iq`` is unauthenticated when ``AIFACTORY_PUBLIC_IQ=1``.
Must emit only the scalar rollup from ``core.factory_iq`` — never prompts, paths,
keys, or per-product internals.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient


FORBIDDEN_SUBSTRINGS = (
    "sk-SECRET",
    "SYSTEM PROMPT LEAK",
    "/root/claudecode",
    "surrogate_repair_hint",
    "raw_text",
    "product_id",
    "p-poison",
    "api_key",
    "JWT_SECRET",
)


def _seed_poisoned_learning_data(data_root):
    state = data_root / "state"
    state.mkdir(parents=True, exist_ok=True)
    episode = {
        "product_id": "p-poison",
        "category": "saas",
        "learning_frozen": False,
        "objective": {
            "shipped": True,
            "ev": 1.2,
            "cost_usd": 0.4,
            "prompt": "SYSTEM PROMPT LEAK",
            "api_key": "sk-SECRET-LEAK",
        },
        "root_cause": {
            "signal": "missing pricing",
            "raw_text": "free form blob " * 20,
            "path": "/root/claudecode/aicom/data/secrets",
        },
    }
    (state / "episodes.jsonl").write_text(json.dumps(episode) + "\n", encoding="utf-8")
    rule = {
        "id": "rule-poison",
        "scope": {"category": "saas", "stage": "developer"},
        "claim": "Always add a 3-tier pricing block",
        "support": 3,
        "lift_ev": 0.5,
        "confidence": 0.7,
        "win_rate": 0.66,
        "status": "active",
        "prompt": "SYSTEM PROMPT LEAK",
        "api_key": "sk-SECRET-LEAK",
        "rationale": "internal judge rationale must not leak",
    }
    (state / "playbook.jsonl").write_text(json.dumps(rule) + "\n", encoding="utf-8")


@pytest.fixture
def iq_client(tmp_path, monkeypatch):
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path))
    _seed_poisoned_learning_data(tmp_path)

    from web.backend.main import app

    return TestClient(app)


def test_public_factory_iq_disabled_when_env_off(iq_client, monkeypatch):
    monkeypatch.delenv("AIFACTORY_PUBLIC_IQ", raising=False)
    resp = iq_client.get("/api/public/factory-iq")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"enabled": False}
    blob = json.dumps(body)
    for forbidden in FORBIDDEN_SUBSTRINGS:
        assert forbidden not in blob


def test_public_factory_iq_enabled_shape(iq_client, monkeypatch):
    monkeypatch.setenv("AIFACTORY_PUBLIC_IQ", "1")
    resp = iq_client.get("/api/public/factory-iq")
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("enabled") is True
    assert "factory_iq" in body
    assert "learning_curve" in body
    assert "playbook" in body
    assert "recent_rules" in body
    lc = body["learning_curve"]
    assert "live_ev_mean" in lc
    assert "frozen_ev_mean" in lc
    assert "gap" in lc
    assert "paying_off" in lc


def test_public_factory_iq_never_leaks_internals(iq_client, monkeypatch):
    monkeypatch.setenv("AIFACTORY_PUBLIC_IQ", "1")
    resp = iq_client.get("/api/public/factory-iq")
    assert resp.status_code == 200
    blob = json.dumps(resp.json())
    for forbidden in FORBIDDEN_SUBSTRINGS:
        assert forbidden not in blob, f"public factory-iq leaked: {forbidden}"

    # recent_rules must only expose whitelisted rule scalars
    for rule in resp.json().get("recent_rules") or []:
        assert set(rule.keys()) <= {
            "claim",
            "category",
            "lift_ev",
            "confidence",
            "win_rate",
            "support",
        }


def test_public_factory_iq_matches_admin_scalar_rollup(iq_client, monkeypatch):
    """Public mirror is the same snapshot + enabled flag — no extra fields."""
    monkeypatch.setenv("AIFACTORY_PUBLIC_IQ", "1")
    pub = iq_client.get("/api/public/factory-iq").json()
    admin = iq_client.get("/api/analytics/factory-iq").json()
    pub_rollup = {k: v for k, v in pub.items() if k != "enabled"}
    assert pub_rollup == admin
