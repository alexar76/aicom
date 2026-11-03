"""Two hubs, one sale: the buyer pays A, A pays B, everybody's books balance.

This is the gap that made federation a catalogue rather than a supply chain. A routed
invoke could not carry payment to the other side at all: the buyer's `X-Payment-Channel` is
meaningless on the peer's ledger, so the router called peers as a shared free-tier visitor,
and a peer that actually charged answered `402` — which was handed back to a buyer who has
no account there and no way to act on it. The one alternative,
`AIMARKET_PEER_PAYMENT_CHANNEL`, is a single global string, and channel ids are hub-local,
so it cannot be right for more than one peer.

The fix is a credit key per peer. The routing hub becomes a reseller with settlement: it
pays the peer out of its own account there, bills the buyer the catalogued price, and keeps
the routing fee as the spread. Consent is the key the peer issued — unlike
`AIMARKET_SELLS_FOR`, which declares this hub the seller of somebody else's work with no
consent anywhere.

Both hubs here are real apps in one process; the router's outbound HTTP is redirected into
the upstream's own TestClient, so the money really moves through two independent ledgers.
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from aimarket_hub import credits
from aimarket_hub.api import create_app
from aimarket_hub.config import HubConfig
from aimarket_hub.database import HubDatabase
from aimarket_hub.models import Capability, Peer
from aimarket_hub.signing import Signer

ADMIN = "test-admin-token-not-for-production"
UPSTREAM_URL = "https://upstream.example.com"


def _build(tmp_path, monkeypatch, name: str, hub_url: str, **env):
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    root = tmp_path / name
    root.mkdir(parents=True, exist_ok=True)
    config = HubConfig()
    config.db_path = str(root / "hub.db")
    config.signing_key_path = str(root / "key")
    config.hub_url = hub_url
    db = HubDatabase(root / "hub.db")
    app = create_app(config=config, db=db, signer=Signer(root / "key"))
    return app, db, config


def _priced_pack(db: HubDatabase, price: float) -> None:
    """A capability the upstream can really execute, with a real price."""
    db.upsert_capability(Capability(
        capability_id="up.answer@v1",
        product_id="up-answer",
        name="Upstream answer",
        description="Static pack served by the upstream hub",
        price_per_call_usd=price,
        source_hub="local",
        invoke_url="",
        prompt_template=json.dumps({"answer": "from upstream"}),
    ))


def _mirror_into_router(db: HubDatabase, price: float, fee_bps: int = 1000) -> None:
    """What the router's crawler would have stored for the upstream's catalogue.

    Including `routed_price_usd` — the crawler computes it as price x (1 + fee), and it is
    what the buyer is shown before they buy, so a test that omitted it would be checking a
    catalogue no real crawl produces.
    """
    db.upsert_peer(Peer(
        url=UPSTREAM_URL, name="Upstream", capabilities_count=1,
        trust_score=0.9, categories=["test"],
        well_known_url=f"{UPSTREAM_URL}/.well-known/ai-market.json",
    ))
    db.upsert_capability(Capability(
        capability_id="up.answer@v1",
        product_id="up-answer",
        name="Upstream answer",
        description="Static pack served by the upstream hub",
        price_per_call_usd=price,
        source_hub=UPSTREAM_URL,
        source_hub_name="Upstream",
        routed_price_usd=round(price * (1 + fee_bps / 10000), 6),
        routing_fee_bps=fee_bps,
        # The crawler stores the peer's trust on the row; without it the capability sits
        # below `min_trust_score` and never reaches search.
        trust_score=0.9,
    ))


@pytest.fixture()
def two_hubs(tmp_path, monkeypatch):
    """Upstream hub B (sells at $0.02) and router hub A (resells it, 10% fee)."""
    monkeypatch.setenv("AIMARKET_ADMIN_TOKEN", ADMIN)
    monkeypatch.setenv("AIMARKET_CREDITS_ENABLED", "1")
    monkeypatch.setenv("AIMARKET_ORACLE_FAMILY_URL", "off")
    monkeypatch.setenv("AIMARKET_CREDITS_FREE_GRANT_USD", "0")
    monkeypatch.setenv("AIMARKET_AUTO_CRAWL", "0")

    up_app, up_db, _ = _build(tmp_path, monkeypatch, "upstream", UPSTREAM_URL)
    _priced_pack(up_db, 0.02)
    up_client = TestClient(up_app)
    up_client.__enter__()

    # The router's own account AT the upstream, funded by the router's operator.
    signup = up_client.post("/ai-market/v2/accounts", json={"label": "router hub"}).json()
    up_client.post(
        f"/ai-market/v2/accounts/{signup['account_id']}/credit",
        json={"amount_usd": 1.0}, headers={"Authorization": f"Bearer {ADMIN}"},
    )
    router_key_at_upstream = signup["api_key"]

    router_app, router_db, _ = _build(
        tmp_path, monkeypatch, "router", "https://router.example.com",
        AIMARKET_ROUTING_FEE_BPS="1000",  # 10%, so the spread is legible in the numbers
        AIMARKET_PEER_API_KEYS=f"{UPSTREAM_URL}={router_key_at_upstream}",
    )
    _mirror_into_router(router_db, 0.02)
    router_client = TestClient(router_app)
    router_client.__enter__()

    # The router's outbound calls go to the upstream's app instead of the network.
    import aimarket_hub.api as api_mod
    import aimarket_hub.peer_routing as peer_routing
    import aimarket_hub.outbound_http as outbound

    async def _safe_post(url, **kwargs):
        path = str(url).replace(UPSTREAM_URL, "")
        return up_client.post(
            path, json=kwargs.get("json"), headers=kwargs.get("headers") or {},
        )

    async def _safe_get(url, **kwargs):
        return up_client.get(str(url).replace(UPSTREAM_URL, ""),
                             headers=kwargs.get("headers") or {})

    monkeypatch.setattr(outbound, "safe_post", _safe_post)
    monkeypatch.setattr(outbound, "safe_get", _safe_get, raising=False)
    monkeypatch.setattr(peer_routing, "_peer_endpoint_cache", {}, raising=False)

    try:
        yield router_client, up_client, router_key_at_upstream, signup["account_id"]
    finally:
        router_client.__exit__(None, None, None)
        up_client.__exit__(None, None, None)


def _buyer_at(client, funded_usd: float) -> str:
    signup = client.post("/ai-market/v2/accounts", json={"label": "buyer"}).json()
    client.post(
        f"/ai-market/v2/accounts/{signup['account_id']}/credit",
        json={"amount_usd": funded_usd}, headers={"Authorization": f"Bearer {ADMIN}"},
    )
    return signup["api_key"]


def _invoke(client, key: str | None = None):
    headers = {"X-API-Key": key} if key else {}
    return client.post("/ai-market/v2/invoke", headers=headers, json={
        "product_id": "up-answer", "capability_id": "up.answer@v1",
        "source_hub": UPSTREAM_URL, "input": {},
    })


def test_a_buyer_at_the_router_can_buy_the_upstreams_paid_capability(two_hubs):
    router, upstream, _key, router_acct = two_hubs
    buyer_key = _buyer_at(router, 1.0)

    r = _invoke(router, buyer_key)
    assert r.status_code == 200, r.text
    assert r.json()["result"]["answer"] == "from upstream"

    # The buyer paid the catalogued price plus the router's 10% spread.
    buyer = router.get("/ai-market/v2/account", headers={"X-API-Key": buyer_key}).json()
    assert buyer["spent_usd"] == pytest.approx(0.022)

    # The upstream really got paid, out of the router's account there.
    up_stats = upstream.get("/ai-market/v2/stats/live").json()["summary"]["credits"]
    assert up_stats["credits_earned_usd"] == pytest.approx(0.02)

    # And the router kept exactly its fee: it collected 0.022 and spent 0.02.
    router_stats = router.get("/ai-market/v2/stats/live").json()["summary"]["credits"]
    assert router_stats["credits_earned_usd"] == pytest.approx(0.022)


def test_without_a_key_the_upstream_402_does_not_reach_the_buyer_as_their_problem(
    tmp_path, monkeypatch,
):
    """The old behaviour, kept visible: no key at the peer → the sale cannot complete."""
    monkeypatch.setenv("AIMARKET_ADMIN_TOKEN", ADMIN)
    monkeypatch.setenv("AIMARKET_CREDITS_ENABLED", "1")
    monkeypatch.setenv("AIMARKET_ORACLE_FAMILY_URL", "off")
    monkeypatch.setenv("AIMARKET_AUTO_CRAWL", "0")
    up_app, up_db, _ = _build(tmp_path, monkeypatch, "upstream2", UPSTREAM_URL)
    _priced_pack(up_db, 0.02)
    with TestClient(up_app) as up_client:
        router_app, router_db, _ = _build(
            tmp_path, monkeypatch, "router2", "https://router2.example.com",
            AIMARKET_PEER_API_KEYS="",
        )
        _mirror_into_router(router_db, 0.02)

        import aimarket_hub.outbound_http as outbound

        async def _safe_post(url, **kwargs):
            return up_client.post(
                str(url).replace(UPSTREAM_URL, ""),
                json=kwargs.get("json"), headers=kwargs.get("headers") or {},
            )

        monkeypatch.setattr(outbound, "safe_post", _safe_post)
        with TestClient(router_app) as router:
            buyer_key = _buyer_at(router, 1.0)
            r = _invoke(router, buyer_key)
            # Either the router refuses up front (fee unpayable) or the upstream 402 is
            # passed through — what must NOT happen is a served call nobody paid for.
            assert r.status_code in (402, 502)
            buyer = router.get(
                "/ai-market/v2/account", headers={"X-API-Key": buyer_key},
            ).json()
            assert buyer["spent_usd"] == pytest.approx(0.0)


def test_an_empty_account_at_the_peer_costs_the_buyer_nothing(two_hubs):
    """The router's own credit runs out mid-sale: that is the router's problem, not the
    buyer's, and the buyer's reservation must come back."""
    router, upstream, _key, router_acct = two_hubs
    upstream.post(
        f"/ai-market/v2/accounts/{router_acct}/status",
        json={"status": "disabled"}, headers={"Authorization": f"Bearer {ADMIN}"},
    )
    buyer_key = _buyer_at(router, 1.0)

    r = _invoke(router, buyer_key)
    assert r.status_code in (401, 502)
    buyer = router.get("/ai-market/v2/account", headers={"X-API-Key": buyer_key}).json()
    assert buyer["spent_usd"] == pytest.approx(0.0)
    assert buyer["held_usd"] == pytest.approx(0.0)


def test_the_resold_capability_is_discoverable_at_the_routers_price(two_hubs):
    """A resold row is still a catalogue row — and it carries the router's own price."""
    router, _upstream, _key, _acct = two_hubs
    matches = router.get("/ai-market/v2/search?q=answer").json()["matches"]
    row = next((m for m in matches if m["capability_id"] == "up.answer@v1"), None)
    assert row is not None, "the routed capability should be discoverable"
    assert row["price_per_call_usd"] == pytest.approx(0.02)
    # The buyer is told the routed price and the fee before they buy anything.
    assert row["routed_price_usd"] == pytest.approx(0.022)
    assert row["routing_fee_bps"] == 1000
