"""The realm seal on every door a peer can come through, not only the seed list.

`realm.check_seed` refused an outside seed at startup, and that was the only check. On
2026-09-23 HISTOR announced itself to the UNI bubble through the OPEN door, passed the assay,
was auto-admitted, and its three live-world capabilities sat in the bubble's catalogue for
ten days — every bubble invoke of them went out to histor.modelmarket.dev. Each test here
closes one of the other doors: open and admin announce, the inbound-crawl note, gossip, the
pending queue, and the rows that got in before the doors were shut.
"""
from __future__ import annotations

import asyncio
import time
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

from aimarket_hub import realm
from aimarket_hub.api import create_app
from aimarket_hub.config import HubConfig
from aimarket_hub.database import HubDatabase
from aimarket_hub.models import Capability, Peer
from aimarket_hub.signing import Signer

ADMIN_TOKEN = "test-admin-token-not-for-production"
ADMIN_HEADERS = {"Authorization": f"Bearer {ADMIN_TOKEN}"}
BUBBLE = "https://uni.example.dev"
SATELLITE = f"{BUBBLE}/sat/khronos"
OUTSIDE = "https://histor.example.org"


@pytest.fixture()
def uni(monkeypatch):
    monkeypatch.setenv("AIMARKET_CHAIN_REALM", "uni")
    monkeypatch.setenv("AIMARKET_UNI_CHAIN_ID", "31337")
    monkeypatch.setenv("AIMARKET_HUB_URL", BUBBLE)
    monkeypatch.delenv("AIMARKET_UNI_FEDERATION_HOSTS", raising=False)
    monkeypatch.setenv("AIMARKET_SEED_LIST", f"{SATELLITE}/.well-known/ai-market.json")
    monkeypatch.setenv("AIMARKET_ADMIN_TOKEN", ADMIN_TOKEN)
    monkeypatch.setenv("AIMARKET_FEDERATION_ASSAY", "0")
    monkeypatch.setenv("AIMARKET_FEDERATION_OPEN", "1")
    return monkeypatch


@pytest.fixture()
def resolvable(monkeypatch):
    """`.example*` never resolves and the SSRF guard resolves DNS; these tests are about the
    realm, so the guard is reduced to its syntax (as in test_open_federation)."""
    import aimarket_hub.crawler as crawler

    monkeypatch.setattr(
        crawler, "_url_is_safe", lambda url: url.startswith(("http://", "https://"))
    )


def _db(tmp_path, name="hub"):
    root = tmp_path / name
    root.mkdir(parents=True, exist_ok=True)
    return root, HubDatabase(root / "hub.db")


@contextmanager
def _hub(tmp_path, db=None, root=None):
    if db is None:
        root, db = _db(tmp_path)
    config = HubConfig()
    config.db_path = str(root / "hub.db")
    config.signing_key_path = str(root / "key")
    app = create_app(config=config, db=db, signer=Signer(root / "key"))
    with TestClient(app) as client:
        client.hub_db = db  # type: ignore[attr-defined]
        yield client


def test_peer_inside_is_the_seed_rule_as_a_predicate(uni):
    assert realm.peer_inside(SATELLITE)
    assert realm.peer_inside(f"{SATELLITE}/.well-known/ai-market.json")
    assert not realm.peer_inside(OUTSIDE)
    assert not realm.peer_inside("https://histor.modelmarket.dev")
    assert not realm.peer_inside("")


def test_a_live_hub_federates_with_anyone_public(monkeypatch):
    monkeypatch.delenv("AIMARKET_CHAIN_REALM", raising=False)
    assert realm.peer_inside(OUTSIDE)


def test_an_outside_hub_cannot_knock_on_the_open_door(uni, tmp_path, resolvable):
    """The exact path HISTOR took."""
    with _hub(tmp_path) as client:
        r = client.post("/ai-market/v2/federation/announce", json={"hub_url": OUTSIDE})
        assert r.status_code == 400, r.text
        assert "sealed" not in r.text.lower() and "uni" not in r.text.lower(), (
            "the refusal must not tell an outsider it reached a bubble"
        )
        assert client.hub_db.get_peer(OUTSIDE) is None


def test_an_outside_well_known_cannot_ride_in_on_an_inside_hub_url(uni, tmp_path, resolvable):
    with _hub(tmp_path) as client:
        r = client.post(
            "/ai-market/v2/federation/announce",
            json={"hub_url": SATELLITE, "well_known_url": f"{OUTSIDE}/.well-known/ai-market.json"},
        )
        assert r.status_code == 400, r.text


def test_not_even_the_operator_can_add_an_outside_peer(uni, tmp_path, resolvable):
    with _hub(tmp_path) as client:
        r = client.post(
            "/ai-market/v2/federation/announce", json={"hub_url": OUTSIDE}, headers=ADMIN_HEADERS
        )
        assert r.status_code == 400, r.text
        assert client.hub_db.get_peer(OUTSIDE) is None


def test_the_bubbles_own_satellite_may_still_knock(uni, tmp_path, resolvable):
    with _hub(tmp_path) as client:
        r = client.post("/ai-market/v2/federation/announce", json={"hub_url": SATELLITE})
        assert r.status_code == 200, r.text
        assert client.hub_db.get_peer(SATELLITE) is not None


def test_an_outside_crawler_is_noted_but_never_admitted(uni, tmp_path, resolvable):
    with _hub(tmp_path) as client:
        db = client.hub_db
        client.get("/.well-known/ai-market.json", headers={"X-AIMarket-Crawler": OUTSIDE})
        deadline = time.time() + 3
        while time.time() < deadline and not db.list_inbound_federation():
            time.sleep(0.02)
        assert db.list_inbound_federation(), "the operator should still learn who reads them"
        time.sleep(0.1)
        assert db.get_peer(OUTSIDE) is None


def test_peers_admitted_before_the_doors_were_shut_are_evicted_at_startup(uni, tmp_path):
    root, db = _db(tmp_path)
    for url in (OUTSIDE, SATELLITE):
        db.upsert_peer(Peer(url=url, name=url, well_known_url=f"{url}/.well-known/ai-market.json",
                            discoverer="announce:open"))
        db.upsert_capability(Capability(
            capability_id=f"{url.rsplit('/', 1)[-1]}.x@v1", product_id="p", name="x",
            source_hub=url, price_per_call_usd=0.0,
        ))
    with _hub(tmp_path, db=db, root=root):
        assert db.get_peer(OUTSIDE) is None
        assert db.list_capabilities(source_hub=OUTSIDE) == []
        assert db.get_peer(SATELLITE) is not None, "the bubble's own satellite must stay"
        assert len(db.list_capabilities(source_hub=SATELLITE)) == 1


def test_a_live_hub_evicts_nobody(monkeypatch, tmp_path):
    monkeypatch.delenv("AIMARKET_CHAIN_REALM", raising=False)
    _, db = _db(tmp_path)
    db.upsert_peer(Peer(url=OUTSIDE, name=OUTSIDE))
    assert realm.evict_outside_peers(db) == []
    assert db.get_peer(OUTSIDE) is not None


def test_the_crawler_never_dials_or_records_an_outside_host(uni, tmp_path, resolvable):
    """Pending rows and gossip are the two frontier paths that are not seeds."""
    from aimarket_hub.crawler import Crawler

    root, db = _db(tmp_path)
    db.announce_peer(
        Peer(url=OUTSIDE, name=OUTSIDE, well_known_url=f"{OUTSIDE}/.well-known/ai-market.json",
             discoverer="announce:open"),
        max_pending=10,
    )
    config = HubConfig()
    config.db_path = str(root / "hub.db")
    crawler = Crawler(config=config, db=db, signer=Signer(root / "key"))
    dialled: list[str] = []
    gossiped = "https://gossip.example.net"

    async def _fake_crawl_one(url, depth, discoverer):
        dialled.append(url)
        return {"capabilities_count": 0, "new_peer_urls": [gossiped]}

    crawler._crawl_one = _fake_crawl_one  # type: ignore[method-assign]
    asyncio.run(crawler.crawl())

    assert f"{SATELLITE}/.well-known/ai-market.json" in dialled
    assert not [u for u in dialled if not u.startswith(BUBBLE)], dialled
    assert db.get_peer(gossiped) is None, "gossip recorded an outside host"
