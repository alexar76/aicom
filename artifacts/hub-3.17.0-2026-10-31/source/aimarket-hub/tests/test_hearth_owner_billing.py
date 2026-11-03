"""A hub sells a hearth tenant on its owner's behalf and pays the owner their share.

2026-10-04: with hearth payments on, this hub's resale of hestia.modelmarket.dev answered
`upstream_unpaid` for every tenant — a tenant took nothing but a per-call on-chain payment. The
hearth now serves a hub that holds its key when the tenant's owner chose that hub, and answers
with a `hub_billing` block signed by the hearth's provider key (hestia/hub_billing.py). This hub
verifies the block against the key it PINNED for the hearth, credits the owner's account here
its share of what this hub charged, and strips the block before the buyer sees the answer.
"""
from __future__ import annotations

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from aimarket_hub.api import create_app
from aimarket_hub.config import HubConfig
from aimarket_hub.database import HubDatabase
from aimarket_hub.models import Capability, Peer
from aimarket_hub.signing import Signer

ADMIN = "test-admin-token-not-for-production"
HUB_URL = "https://router.example.com"
HEARTH = "https://hearth.example.com"
PRICE = 0.01


@pytest.fixture()
def router(tmp_path, monkeypatch):
    for key, value in {
        "AIMARKET_ADMIN_TOKEN": ADMIN, "AIMARKET_CREDITS_ENABLED": "1",
        "AIMARKET_ORACLE_FAMILY_URL": "off", "AIMARKET_CREDITS_FREE_GRANT_USD": "0",
        "AIMARKET_AUTO_CRAWL": "0", "AIMARKET_ROUTING_FEE_BPS": "100",
        "AIMARKET_PUBLISHER_SHARE_BPS": "7000",
        "AIMARKET_PEER_API_KEYS": f"{HEARTH}=aimk_router_key_at_hearth",
    }.items():
        monkeypatch.setenv(key, value)
    config = HubConfig()
    config.db_path = str(tmp_path / "hub.db")
    config.signing_key_path = str(tmp_path / "key")
    config.hub_url = HUB_URL
    db = HubDatabase(tmp_path / "hub.db")
    hearth_key = Signer(tmp_path / "hearth.key")          # the hearth's provider key
    db.upsert_peer(Peer(url=HEARTH, name="hearth", capabilities_count=1, trust_score=0.9,
                        categories=["test"], public_key=hearth_key.public_key_b64, trusted=True,
                        well_known_url=f"{HEARTH}/.well-known/ai-market.json"))
    db.upsert_capability(Capability(
        capability_id="owner.check@v1", product_id="owner-checks", name="owner check",
        description="a tenant of the hearth, owned by someone else", price_per_call_usd=PRICE,
        source_hub=HEARTH, source_hub_name="hearth", routed_price_usd=PRICE * 1.01,
        routing_fee_bps=100, trust_score=0.9,
    ))
    app = create_app(config=config, db=db, signer=Signer(tmp_path / "key"))
    client = TestClient(app)
    client.__enter__()
    sent: list[dict] = []
    state = {"bill": None}

    import aimarket_hub.api as api_mod
    import aimarket_hub.peer_routing as peer_routing
    import aimarket_hub.outbound_http as outbound

    async def _safe_post(url, **kwargs):
        sent.append(dict(kwargs.get("headers") or {}))
        body = {"ok": True, "result": {"verdict": "fine"}}
        if state["bill"] is not None:
            body["hub_billing"] = state["bill"]
        return httpx.Response(200, json=body, request=httpx.Request("POST", str(url)))

    monkeypatch.setattr(outbound, "safe_post", _safe_post)
    monkeypatch.setattr(peer_routing, "_peer_endpoint_cache", {}, raising=False)
    try:
        yield client, hearth_key, state, sent, tmp_path
    finally:
        client.__exit__(None, None, None)


def _account(client, label: str, funded: float = 0.0) -> tuple[str, str]:
    signup = client.post("/ai-market/v2/accounts", json={"label": label}).json()
    if funded:
        client.post(f"/ai-market/v2/accounts/{signup['account_id']}/credit",
                    json={"amount_usd": funded}, headers={"Authorization": f"Bearer {ADMIN}"})
    return signup["account_id"], signup["api_key"]


def _bill(signer, owner_account: str, **over) -> dict:
    block = {"version": "hestia-hub-billing/1", "id": "hb_test", "hearth": HEARTH, "hub": HUB_URL,
             "slug": "owner-check", "capability_id": "owner.check@v1",
             "owner_pubkey": "TF1yoIZdB820AeHKmNTc5LY8GJVaOHMkzpryLgyfQwM=",
             "bill_to_account": owner_account, "price_usd": PRICE, "input_sha256": "0" * 64,
             "issued_at": 1}
    block.update(over)
    block["signature"] = signer.sign_object(block)
    return block


def _buy(client, buyer_key):
    return client.post("/ai-market/v2/invoke", headers={"X-API-Key": buyer_key}, json={
        "product_id": "owner-checks", "capability_id": "owner.check@v1",
        "source_hub": HEARTH, "input": {"claim": "x"}})


def _balance(client, key) -> float:
    return client.get("/ai-market/v2/account", headers={"X-API-Key": key}).json()["balance_usd"]


def test_the_owner_is_paid_its_share_and_the_buyer_never_sees_the_bill(router):
    client, hearth_key, state, sent, _ = router
    owner_acct, owner_key = _account(client, "tenant owner")
    _, buyer_key = _account(client, "buyer", funded=1.0)
    state["bill"] = _bill(hearth_key, owner_acct)
    res = _buy(client, buyer_key)
    assert res.status_code == 200, res.text
    assert "hub_billing" not in res.json()
    assert _balance(client, owner_key) == pytest.approx(PRICE * 0.7)   # 70% of what WE charged
    assert sent[-1]["X-API-Key"] == "aimk_router_key_at_hearth"
    assert sent[-1]["X-AIMarket-Hub-Charged"] == f"{PRICE:.6f}"


@pytest.mark.parametrize("forge", ["other_key", "other_hub", "other_capability", "inflated"])
def test_a_bill_that_does_not_hold_pays_nobody(router, forge):
    client, hearth_key, state, _, tmp_path = router
    owner_acct, owner_key = _account(client, "tenant owner")
    _, buyer_key = _account(client, "buyer", funded=1.0)
    if forge == "other_key":
        bill = _bill(Signer(tmp_path / "impostor.key"), owner_acct)
    elif forge == "other_hub":
        bill = _bill(hearth_key, owner_acct, hub="https://somebody-else.example.com")
    elif forge == "other_capability":
        bill = _bill(hearth_key, owner_acct, capability_id="pricier.thing@v1")
    else:
        bill = _bill(hearth_key, owner_acct)
        bill["price_usd"] = 999.0                              # edited after signing
    state["bill"] = bill
    assert _buy(client, buyer_key).status_code == 200          # the buyer still gets the work
    assert _balance(client, owner_key) == pytest.approx(0.0)


def test_the_share_is_of_what_this_hub_charged_not_the_hearths_number(router):
    client, hearth_key, state, _, _ = router
    owner_acct, owner_key = _account(client, "tenant owner")
    _, buyer_key = _account(client, "buyer", funded=1.0)
    state["bill"] = _bill(hearth_key, owner_acct, price_usd=50.0)     # signed, but not our price
    _buy(client, buyer_key)
    assert _balance(client, owner_key) == pytest.approx(PRICE * 0.7)


def test_an_operator_tenant_names_no_account_and_the_hub_keeps_the_sale(router):
    client, hearth_key, state, _, _ = router
    _, buyer_key = _account(client, "buyer", funded=1.0)
    state["bill"] = _bill(hearth_key, "")
    assert _buy(client, buyer_key).status_code == 200
    stats = client.get("/ai-market/v2/stats/live").json()["summary"]["credits"]
    assert stats.get("payouts_usd", 0.0) == pytest.approx(0.0)
