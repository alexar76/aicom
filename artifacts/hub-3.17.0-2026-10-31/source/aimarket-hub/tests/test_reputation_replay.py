"""POST /reputation/events: a peer's signature proves WHO spoke, not that it may repeat itself.

Before 2026-09-11 one validly signed event could be posted again without limit (100 per
request, no rate limit), and trust.py derives a provider's success rate and estimated bond
from its last 10 events — so a peer could set a provider's trust score by volume. The
canonical binds the timestamp, so a stale event cannot be re-dated; it just had no window.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from aimarket_hub.api import create_app
from aimarket_hub.config import HubConfig
from aimarket_hub.database import HubDatabase
from aimarket_hub.models import Peer
from aimarket_hub.signing import Signer

CONSUMER = "https://consumer.example.com"
PROVIDER = "https://provider.example.com"


def _hub(tmp_path):
    root = tmp_path / "hub"
    root.mkdir()
    config = HubConfig()
    config.db_path = str(root / "hub.db")
    config.signing_key_path = str(root / "key")
    db = HubDatabase(root / "hub.db")
    consumer_signer = Signer(root / "consumer_key")
    db.upsert_peer(Peer(url=CONSUMER, name="consumer", public_key=consumer_signer.public_key_b64),
                   status="active")
    app = create_app(config=config, db=db, signer=Signer(root / "key"))
    return app, db, consumer_signer


def _signed_event(signer: Signer, *, timestamp: str, capability_id: str = "cap@v1") -> dict:
    event = {
        "type": "invocation_success",
        "provider_hub": PROVIDER,
        "consumer_hub": CONSUMER,
        "capability_id": capability_id,
        "timestamp": timestamp,
        "price_usd": 0.4,
        "latency_ms": 120,
    }
    canonical = (
        f"type:{event['type']}"
        f"|provider_hub:{event['provider_hub']}"
        f"|timestamp:{event['timestamp']}"
        f"|price_usd:{event['price_usd']}"
        f"|latency_ms:{event['latency_ms']}"
    )
    event["signature"] = {"algorithm": "ed25519", "value": signer.sign_canonical(canonical)}
    return event


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def test_the_same_signed_event_is_recorded_once(tmp_path):
    app, db, consumer = _hub(tmp_path)
    ev = _signed_event(consumer, timestamp=_now())
    with TestClient(app) as client:
        first = client.post("/ai-market/v2/reputation/events", json={"events": [ev]}).json()
        assert first == {"received": 1, "rejected": 0, "replayed": 0}, first
        # 100 copies in one request, then the same event again in another request.
        again = client.post("/ai-market/v2/reputation/events", json={"events": [ev] * 100}).json()
        assert again["received"] == 0 and again["replayed"] == 100, again
    assert len(db.reputation_events_for(PROVIDER, limit=500)) == 1


def test_replaying_under_a_different_capability_id_does_not_count_twice(tmp_path):
    """capability_id is not in the canonical, so the same signature verifies for any of them."""
    app, db, consumer = _hub(tmp_path)
    ts = _now()
    ev = _signed_event(consumer, timestamp=ts, capability_id="cap-a@v1")
    retargeted = dict(ev, capability_id="cap-b@v1")
    with TestClient(app) as client:
        assert client.post("/ai-market/v2/reputation/events", json={"events": [ev]}).json()["received"] == 1
        out = client.post("/ai-market/v2/reputation/events", json={"events": [retargeted]}).json()
        assert out["replayed"] == 1 and out["received"] == 0, out
    assert len(db.reputation_events_for(PROVIDER, limit=500)) == 1


def test_a_stale_signed_event_is_rejected(tmp_path):
    app, db, consumer = _hub(tmp_path)
    old = (datetime.now(timezone.utc) - timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
    future = (datetime.now(timezone.utc) + timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
    with TestClient(app) as client:
        for ts in (old, future, "not-a-time", ""):
            out = client.post(
                "/ai-market/v2/reputation/events",
                json={"events": [_signed_event(consumer, timestamp=ts)]},
            ).json()
            assert out["rejected"] == 1 and out["received"] == 0, (ts, out)
    assert db.reputation_events_for(PROVIDER, limit=500) == []


def test_submissions_are_rate_limited_per_client(tmp_path):
    app, _db, consumer = _hub(tmp_path)
    with TestClient(app) as client:
        codes = []
        for i in range(31):
            ev = _signed_event(consumer, timestamp=_now(), capability_id=f"cap-{i}@v1")
            codes.append(client.post("/ai-market/v2/reputation/events", json={"events": [ev]}).status_code)
    assert codes[:30] == [200] * 30
    assert codes[30] == 429
