"""A verified address migration must not wash away a provider's old failures."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from types import SimpleNamespace

import pytest

from aimarket_hub.database import HubDatabase
from aimarket_hub.models import InvocationStat, Peer, ReputationEvent
from aimarket_hub.trust import IDENTITY_ALIASES_ENV, TrustScorer

OLD = "https://provider.example/old"
NEW = "https://provider.example/current"
OTHER = "https://stranger.example"


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.delenv(IDENTITY_ALIASES_ENV, raising=False)
    database = HubDatabase(tmp_path / "hub.db")
    yield database
    database.close()


def stamp():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def invocation(db, url, success, price=0.01):
    db.record_invocation(InvocationStat(capability_id="facts.read@v1", product_id="facts",
        source_hub=url, price_usd=price, latency_ms=100, success=success, timestamp=stamp()))


def configure(monkeypatch, mapping=None):
    monkeypatch.setenv(IDENTITY_ALIASES_ENV, json.dumps(mapping or {NEW: [OLD]}))


def history(db):
    return {table: [tuple(row) for row in db._conn.execute(f"SELECT * FROM {table} ORDER BY id").fetchall()]
            for table in ("invocation_stats", "reputation_events", "delivery_confirmations")}


def test_36_old_calls_and_one_new_call_are_one_identity_without_rewriting_history(db, monkeypatch):
    db.upsert_peer(Peer(url=NEW, name="Renamed provider", last_crawl=stamp()))
    db.upsert_peer(Peer(url=OTHER, name="EMPORION / SYMMARTYS", last_crawl=stamp()))
    for index in range(36):
        invocation(db, OLD, index < 18)
    invocation(db, NEW, True)
    invocation(db, OTHER, False, price=2)
    before = history(db)
    plain = TrustScorer(db)
    assert plain._compute_success_rate(NEW) == 1.0
    configure(monkeypatch)
    scorer = TrustScorer(db)
    assert scorer._compute_success_rate(NEW) == pytest.approx(19 / 37)
    assert scorer._compute_volume_30d(NEW) == pytest.approx(0.37)
    assert scorer.compute_score(NEW) == scorer.compute_score(OLD)
    assert scorer.compute_score(NEW) < plain.compute_score(NEW)
    assert scorer.compute_score(OTHER) == plain.compute_score(OTHER)
    assert len(before["invocation_stats"]) == 38
    assert history(db) == before


def test_reputation_and_delivery_aliases_keep_original_signatures_and_count_buyers_once(db, monkeypatch):
    db.upsert_peer(Peer(url=NEW, name="Provider", last_crawl=stamp()))
    db.record_reputation_event(ReputationEvent(event_type="invocation_success", provider_hub=OLD,
        capability_id="facts.read@v1", timestamp=stamp(), price_usd=5, latency_ms=100,
        consumer_hub="local", signature="unchanged-signed-old-event"))
    invocation(db, OLD, False)
    for number, url in enumerate((OLD, NEW)):
        db.record_delivery_confirmation(SimpleNamespace(id=f"delivery-{number}", source_hub=url,
            product_id="facts", kind="delivery", buyer_hash="same-verified-buyer"))
    before = history(db)
    configure(monkeypatch)
    scorer = TrustScorer(db)
    assert scorer._estimate_bond(NEW) == 50
    assert scorer._compute_success_rate(NEW) == 0.5  # one failed call, one distinct buyer
    assert history(db) == before


@pytest.mark.parametrize("raw", [
    "not-json", "[]", '{"https://provider.example/current":"not-a-list"}',
    json.dumps({NEW: [NEW]}),
    json.dumps({NEW: [OLD], OTHER: [OLD]}),
    json.dumps({NEW: [OLD], OLD: [OTHER]}),
    json.dumps({NEW: ["https://credential@example.org"]}),
    json.dumps({NEW: ["https://example.org/../old"]}),
    json.dumps({NEW: ["https://example.org/old?secret=value"]}),
    json.dumps({NEW: ["local"]}),
    '{"https://provider.example/current":[],"https://provider.example/current":[]}',
])
def test_invalid_or_ambiguous_operator_mappings_fail_closed(db, monkeypatch, raw):
    monkeypatch.setenv(IDENTITY_ALIASES_ENV, raw)
    with pytest.raises(ValueError, match=IDENTITY_ALIASES_ENV):
        TrustScorer(db)


def test_empty_configuration_keeps_existing_url_scoping(db, monkeypatch):
    invocation(db, OLD, False)
    invocation(db, NEW, True)
    monkeypatch.setenv(IDENTITY_ALIASES_ENV, "{}")
    scorer = TrustScorer(db)
    assert scorer._compute_success_rate(NEW) == 1.0
    assert scorer._compute_success_rate(OLD) == 0.0


def test_alias_ownership_normalizes_but_history_matches_exact_stored_urls(db, monkeypatch):
    raw_old = "https://PROVIDER.example:443/old/"
    invocation(db, raw_old, False)
    invocation(db, NEW, True)
    configure(monkeypatch, {NEW: [raw_old]})
    scorer = TrustScorer(db)
    assert scorer._compute_success_rate(NEW) == 0.5
    assert scorer._compute_success_rate(OLD) == 0.5
    assert scorer._compute_volume_30d(NEW) == pytest.approx(0.02)


def test_normalized_duplicate_aliases_and_unbounded_mapping_are_rejected(db, monkeypatch):
    for mapping in ({NEW: [OLD, "https://PROVIDER.example:443/old/"]},
                    {NEW: [f"https://provider.example/old-{n}" for n in range(64)]}):
        configure(monkeypatch, mapping)
        with pytest.raises(ValueError, match=IDENTITY_ALIASES_ENV):
            TrustScorer(db)
