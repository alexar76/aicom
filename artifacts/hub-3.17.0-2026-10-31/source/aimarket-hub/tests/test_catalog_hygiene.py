"""Buyer-facing catalogue names and routes stay honest."""

from __future__ import annotations

import time

from fastapi.testclient import TestClient

from aimarket_hub.api import create_app
from aimarket_hub.catalog import catalogue_display_name, route_freshness
from aimarket_hub.config import HubConfig
from aimarket_hub.database import HubDatabase
from aimarket_hub.models import Capability, Peer
from aimarket_hub.signing import Signer


PEER = "https://peer.example.com"
CAPABILITY = "run@v1"
PRODUCT = "prod-eb9ce90c24f9"


def _stamp(offset_s: int = 0) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + offset_s))


def _cap(**overrides) -> Capability:
    values = dict(
        capability_id=CAPABILITY,
        product_id=PRODUCT,
        name=f"{PRODUCT}.run@v1",
        description="Execute primary workflow for **SignalForge Control Plane** — agent orchestration",
        source_hub=PEER,
        source_hub_name="Peer Hub",
        price_per_call_usd=0.35,
        trust_score=0.5,
    )
    values.update(overrides)
    return Capability(**values)


def _client(tmp_path, *, peer_status: str = "active", peer_age_s: int = 0, max_age_s: int = 60):
    db = HubDatabase(tmp_path / "hub.db")
    cap = _cap()
    db.upsert_capability(cap)
    db.upsert_peer(
        Peer(
            url=PEER,
            name="Peer Hub",
            capabilities_count=1,
            last_crawl=_stamp(-peer_age_s),
            trust_score=0.5,
            trusted=True,
        ),
        status=peer_status,
    )
    config = HubConfig()
    config.db_path = str(tmp_path / "hub.db")
    config.signing_key_path = str(tmp_path / "key")
    config.catalog_max_stale_s = max_age_s
    config.auto_crawl = False
    app = create_app(config=config, db=db, signer=Signer(config.signing_key_path))
    return TestClient(app)


def test_display_name_removes_duplicate_protocol_qualification():
    memory = _cap(
        capability_id="memory.verify@v1",
        product_id="memory-verify",
        name="memory-verify.Verify Memory@v1@v1",
        description="Verify a memory attestation",
    )
    assert catalogue_display_name(memory) == "Verify Memory"
    assert memory.tool_name() == "memory-verify.Verify Memory@v1"


def test_generic_factory_name_uses_the_product_subject():
    cap = _cap()
    assert catalogue_display_name(cap) == "SignalForge Control Plane · Run"
    assert cap.tool_name() == f"{PRODUCT}.run@v1"


def test_route_freshness_distinguishes_stale_and_unavailable():
    cap = _cap()
    active = Peer(url=PEER, name="Peer", last_crawl="2026-01-01T00:00:00Z", status="active")
    now = datetime_epoch = 1767225720.0  # 2026-01-01T00:02:00Z
    assert route_freshness(cap, active, max_age_s=60, now=now).status == "stale"
    active.last_crawl = ""
    assert route_freshness(cap, active, max_age_s=60, now=datetime_epoch).status == "unknown"
    active.status = "key_mismatch"
    assert route_freshness(cap, active, max_age_s=60, now=datetime_epoch).status == "unavailable"


def test_search_hides_stale_offer_but_can_return_it_as_not_offerable(tmp_path):
    with _client(tmp_path, peer_age_s=3600, max_age_s=60) as client:
        regular = client.get("/ai-market/v2/search", params={"intent": "run", "limit": 20}).json()
        assert not any(row["capability_id"] == CAPABILITY for row in regular["matches"])

        audit = client.get(
            "/ai-market/v2/search",
            params={"intent": "run", "limit": 20, "include_stale": True},
        ).json()
        row = next(row for row in audit["matches"] if row["capability_id"] == CAPABILITY)
        assert row["route_status"] == "stale"
        assert row["offerable"] is False
        assert row["display_name"] == "SignalForge Control Plane · Run"
        assert row["seller_kind"] == "hub"

        manifest = client.get("/ai-market/v2/manifest").json()
        assert not any(tool["capability_id"] == CAPABILITY for tool in manifest["tools"])


def test_key_mismatch_offer_is_never_returned_even_for_audit(tmp_path):
    with _client(tmp_path, peer_status="key_mismatch") as client:
        result = client.get(
            "/ai-market/v2/search",
            params={"intent": "run", "include_stale": True},
        ).json()
        assert not any(row["capability_id"] == CAPABILITY for row in result["matches"])
