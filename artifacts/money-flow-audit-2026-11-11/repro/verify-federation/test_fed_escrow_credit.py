"""Scratch repro: federated escrow authorization stored for a call paid by CREDITS."""
from __future__ import annotations

import sqlite3

import pytest
from fastapi.testclient import TestClient

import aimarket_hub.api as api_mod
import aimarket_hub.hub_routes.invoke as invoke_routes
import aimarket_hub.channels as channels_mod
import aimarket_hub.outbound_http as ohttp
from aimarket_hub.api import create_app
from aimarket_hub.channels import ChannelLedger
from aimarket_hub.config import HubConfig
from aimarket_hub.database import HubDatabase
from aimarket_hub.models import Capability, Peer
from aimarket_hub.signing import Signer

ADMIN_TOKEN = "fed-admin-token"
PEER = "https://oracle-peer.example.com"
MCP = "https://oracle-peer.example.com/ai-market/mcp"


class _Resp:
    def __init__(self, status_code=200, payload=None):
        self.status_code, self._p, self.text, self.headers = status_code, payload, "", {}

    def json(self):
        return self._p


class _Out:
    def __init__(self):
        self.posts = []
        self.headers = []

    async def safe_get(self, url, *, timeout=10.0):
        return _Resp(200, {"mcp_endpoint": MCP})

    async def safe_post(self, url, *, json=None, headers=None, timeout=30.0, invoke=False, oracle_paid=False):
        self.posts.append((url, json))
        self.headers.append(dict(headers or {}))
        return _Resp(200, {"ok": True, "result": {"v": 1},
                           "receipt": {"nonce": "orc_1", "latency_ms": 5, "price_usd": 0.05}})


def _build(tmp_path, monkeypatch):
    monkeypatch.setenv("AIFACTORY_CRYPTO_ENABLED", "1")
    monkeypatch.setenv("AIMARKET_CREDITS_ENABLED", "1")
    monkeypatch.setenv("AIMARKET_CREDITS_FREE_GRANT_USD", "0")
    monkeypatch.setenv("AIMARKET_ALLOW_DEMO_CREDIT", "1")
    monkeypatch.setenv("AIMARKET_ADMIN_TOKEN", ADMIN_TOKEN)
    monkeypatch.setenv("AIFACTORY_PUBLIC_URL", "http://factory.test")
    monkeypatch.setenv("AIMARKET_ROUTING_FEE_BPS", "1000")
    monkeypatch.setattr(channels_mod, "_ledger", ChannelLedger(db_path=str(tmp_path / "channels.db")))
    config = HubConfig()
    config.db_path = str(tmp_path / "hub.db")
    config.signing_key_path = str(tmp_path / "key")
    db = HubDatabase(config.db_path)
    app = create_app(config=config, db=db, signer=Signer(config.signing_key_path))
    db.upsert_peer(Peer(url=PEER, name=PEER, capabilities_count=1,
                        well_known_url=f"{PEER}/.well-known/ai-market.json", trusted=True))
    db.upsert_capability(Capability(capability_id="cap.x@v1", product_id="prod-x", name="x",
                                    price_per_call_usd=0.05, source_hub=PEER, source_hub_name=PEER,
                                    trust_score=0.5))
    return app, db, config


@pytest.mark.parametrize("shape", ["sells", "resells"])
def test_authorization_stored_but_credits_pay(tmp_path, monkeypatch, shape):
    app, db, config = _build(tmp_path, monkeypatch)
    if shape == "sells":
        monkeypatch.setattr(config, "sells_on_behalf_of", lambda _u: True)
    else:
        monkeypatch.setattr(config, "peer_api_key", lambda _u: "aimk_router_key_at_peer")
    out = _Out()
    monkeypatch.setattr(ohttp, "safe_get", out.safe_get)
    monkeypatch.setattr(ohttp, "safe_post", out.safe_post)
    monkeypatch.setattr(invoke_routes, "channel_escrow_binding", lambda _cid: "0x" + "cd" * 32)

    import aimarket_hub.escrow_bridge.authorization as bridge_auth
    stored, withdrawn = [], []

    def _verify_and_store(**kw):
        stored.append(kw)
        row = type("Row", (), {"receipt_id": kw["expected_receipt_id"]})()
        return type("Accepted", (), {"row": row})()

    monkeypatch.setattr(bridge_auth, "verify_and_store", _verify_and_store)
    monkeypatch.setattr(bridge_auth, "withdraw", lambda rid, *_a, **_k: withdrawn.append(rid))

    receipt = "0x" + "77" * 32
    with TestClient(app) as client:
        signup = client.post("/ai-market/v2/accounts", json={"label": "buyer"}).json()
        client.post(f"/ai-market/v2/accounts/{signup['account_id']}/credit",
                    json={"amount_usd": 1.0}, headers={"Authorization": f"Bearer {ADMIN_TOKEN}"})
        opened = channels_mod._ledger.open(5.0, with_secret=True)["channel"]
        r = client.post("/ai-market/v2/invoke", json={
            "product_id": "prod-x", "capability_id": "cap.x@v1", "source_hub": PEER, "input": {},
            "payment_authorization": {"receiptId": receipt, "amount": "55000", "nonce": 0},
        }, headers={"X-API-Key": signup["api_key"], "X-Payment-Channel": opened["channel_id"],
                    "X-Payment-Channel-Secret": opened["channel_secret"]})
        acct = client.get("/ai-market/v2/account", headers={"X-API-Key": signup["api_key"]}).json()
        chan = channels_mod._ledger.get_channel(opened["channel_id"]) if hasattr(channels_mod._ledger, "get_channel") else None

    conn = sqlite3.connect(str(tmp_path / "channels.db"))
    holds = [x[0] for x in conn.execute("SELECT receipt_id FROM channel_holds")]
    debits = [x[0] for x in conn.execute("SELECT receipt_id FROM debited_receipts")]
    conn.close()
    print(shape, r.status_code, "stored:", [(s["expected_receipt_id"][:10], s["expected_amount_usd"]) for s in stored],
          "withdrawn:", withdrawn, "credits spent:", acct.get("spent_usd"),
          "channel holds:", holds, "channel debits:", debits)
    assert r.status_code == 200, r.text
    assert stored and stored[0]["expected_receipt_id"] == receipt   # authorization persisted
    assert withdrawn == []                                          # ...and never withdrawn
    assert receipt not in debits                                    # no channel debit backs it
    # credits paid the price only; the routing fee (resells) was never charged
    assert acct["spent_usd"] == pytest.approx(0.05)
