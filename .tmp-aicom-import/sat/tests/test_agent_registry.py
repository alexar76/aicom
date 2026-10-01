"""Factory-born agents register themselves as economy participants."""

import time

import pytest

from web.backend.services import agent_registry


@pytest.fixture(autouse=True)
def _isolated_registry(tmp_path, monkeypatch):
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path))
    monkeypatch.delenv("AIFACTORY_AGENT_REGISTRY_KEY", raising=False)
    monkeypatch.delenv("AIFACTORY_PROD", raising=False)
    monkeypatch.delenv("AIFACTORY_PRODUCTION", raising=False)
    monkeypatch.delenv("AIFACTORY_ENV", raising=False)
    yield


def _beat(**over):
    payload = {
        "agent_id": "sentinel-1",
        "name": "Sentinel",
        "product_id": "prod-bdb1634806de",
        "sdk": "aimarket-agent@2.2.0",
        "version": "0.1.0",
        "public_url": "https://sentinel.vercel.app",
        "capabilities_used": ["atlas.situation.brief@v1", "atlas.fire.weather@v1"],
        "stats": {"invokes_total": 12, "spend_usd_total": 0.72, "errors_24h": 0},
    }
    payload.update(over)
    return payload


def test_heartbeat_creates_then_updates_one_record():
    first = agent_registry.record_heartbeat(_beat())
    assert first["heartbeats"] == 1
    assert first["capabilities_used"] == [
        "atlas.situation.brief@v1",
        "atlas.fire.weather@v1",
    ]

    second = agent_registry.record_heartbeat(_beat(stats={"invokes_total": 20}))
    assert second["heartbeats"] == 2
    assert second["first_seen"] == first["first_seen"]
    assert second["stats"]["invokes_total"] == 20

    roster = agent_registry.list_agents()
    assert len(roster) == 1
    assert roster[0]["status"] == "live"


def test_unknown_stat_fields_are_dropped():
    rec = agent_registry.record_heartbeat(
        _beat(stats={"invokes_total": 3, "evil_blob": "x" * 10_000})
    )
    assert rec["stats"] == {"invokes_total": 3.0}


def test_bad_agent_id_is_rejected():
    for bad in ("", "../etc/passwd", "has spaces", "x" * 80):
        with pytest.raises(ValueError):
            agent_registry.record_heartbeat(_beat(agent_id=bad))


def test_status_ages_from_live_to_stale_to_offline():
    now = time.time()
    assert agent_registry.status_for(now, now=now) == "live"
    assert agent_registry.status_for(now - 600, now=now) == "stale"
    assert agent_registry.status_for(now - 7200, now=now) == "offline"


def test_summary_aggregates_the_economy():
    agent_registry.record_heartbeat(_beat())
    agent_registry.record_heartbeat(
        _beat(
            agent_id="argus-1",
            name="Argus",
            sdk="@aimarket/agent@0.1.4",
            capabilities_used=["atlas.situation.brief@v1"],
            stats={"invokes_total": 8, "spend_usd_total": 0.28},
        )
    )
    s = agent_registry.registry_summary()
    assert s["agents_total"] == 2
    assert s["agents_live"] == 2
    assert s["invokes_total"] == 20
    assert s["spend_usd_total"] == pytest.approx(1.0)
    assert s["capabilities"]["atlas.situation.brief@v1"] == 2
    assert set(s["sdks"]) == {"aimarket-agent@2.2.0", "@aimarket/agent@0.1.4"}


def test_key_is_optional_in_dev_but_marks_unverified():
    ok, reason = agent_registry.check_agent_key(None)
    assert ok is True
    assert reason == "unverified_dev"


def test_production_without_a_key_fails_closed(monkeypatch):
    monkeypatch.setenv("AIFACTORY_PROD", "1")
    ok, reason = agent_registry.check_agent_key(None)
    assert ok is False
    assert reason == "registry_key_not_configured"


def test_configured_key_must_match(monkeypatch):
    monkeypatch.setenv("AIFACTORY_AGENT_REGISTRY_KEY", "s3cret")
    assert agent_registry.check_agent_key("s3cret") == (True, "verified")
    assert agent_registry.check_agent_key("wrong")[0] is False
    assert agent_registry.check_agent_key(None)[0] is False


def test_product_is_agent_reads_the_order_not_a_guess():
    assert agent_registry.product_is_agent({"tags": ["owner-order", "agent"]}) is True
    assert agent_registry.product_is_agent({"category": "agent"}) is True
    assert agent_registry.product_is_agent({"spec": {"product_kind": "agent"}}) is True
    assert agent_registry.product_is_agent({"tags": ["saas"], "category": "saas"}) is False
    assert agent_registry.product_is_agent(None) is False


def test_publish_seeds_a_participant_awaiting_first_contact():
    """A serverless agent runs only when called — publishing is the event to record."""
    rec = agent_registry.bootstrap_from_publish(
        product_id="prod-abc",
        name="Sentinel",
        public_url="https://sentinel.vercel.app",
        capabilities=["atlas.situation.brief@v1"],
    )
    assert rec["agent_id"] == "prod-abc"
    assert rec["verified"] is True

    roster = agent_registry.list_agents()
    assert len(roster) == 1
    # Published, but it has not reported in — the roster must not claim it is live.
    assert roster[0]["status"] == "stale"
    assert roster[0]["public_url"] == "https://sentinel.vercel.app"


def test_agents_own_heartbeat_promotes_it_to_live():
    agent_registry.bootstrap_from_publish(
        product_id="prod-abc", name="Sentinel", public_url="https://x.vercel.app"
    )
    agent_registry.record_heartbeat(
        _beat(agent_id="prod-abc", name="Sentinel", stats={"invokes_total": 4})
    )
    roster = agent_registry.list_agents()
    assert roster[0]["status"] == "live"
    assert roster[0]["stats"]["invokes_total"] == 4


def test_corrupt_registry_file_does_not_break_reads(tmp_path):
    agent_registry.registry_path().parent.mkdir(parents=True, exist_ok=True)
    agent_registry.registry_path().write_text("{not json", encoding="utf-8")
    assert agent_registry.list_agents() == []
    agent_registry.record_heartbeat(_beat())
    assert len(agent_registry.list_agents()) == 1
