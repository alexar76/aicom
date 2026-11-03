"""`aimarket node`: a service someone already runs becomes a node the admission assay passes.

The decisive test runs the hub's own `run_assay` against the node, with the seller's API
faked behind it: one free route (a signed receipt is the evidence) and one x402 V2 route
whose 402 carries its offer only in PAYMENT-REQUIRED (the offer is the evidence).
"""
from __future__ import annotations

import asyncio
import base64
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from aimarket_hub import node
from aimarket_hub.config import HubConfig
from aimarket_hub.database import HubDatabase
from aimarket_hub.federation_assay import run_assay
from aimarket_hub.models import Peer
from aimarket_hub.signing import Signer
from aimarket_hub.validator import validate_manifest, validate_well_known

NODE_URL = "https://api.seller.example"
PAY_TO = "0xF7Eb4b12D673dF433d76B2DBD9CA41Db3fE1836E"

CONFIG = f'''
name = "Seller Example"
url = "{NODE_URL}"
upstream = "http://upstream.internal"

[[capability]]
id = "gas.price@v1"
product = "seller"
description = "Base gas price"
price_usd = 0.001
method = "GET"
path = "/gas-price"
input_schema = {{ type = "object", required = ["chain"], properties = {{ chain = {{ type = "string" }} }} }}

[[capability]]
id = "seller.ping@v1"
product = "seller"
description = "Free liveness check"
price_usd = 0
method = "POST"
path = "/ping"
'''


def _offer(amount: str = "1000") -> str:
    return base64.b64encode(json.dumps({"x402Version": 2, "accepts": [{
        "scheme": "exact", "network": "eip155:8453", "amount": amount,
        "asset": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913", "payTo": PAY_TO,
    }]}).encode()).decode()


def _seller(seen: list[httpx.Request]):
    """The seller's existing API: an x402 V2 GET route and a free POST route."""
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == "/gas-price":
            if not request.headers.get("payment-signature"):
                return httpx.Response(402, json={}, headers={"PAYMENT-REQUIRED": _offer()})
            return httpx.Response(200, json={"chain": request.url.params.get("chain"), "gwei": 0.005},
                                  headers={"PAYMENT-RESPONSE": "settled"})
        if request.url.path == "/ping":
            return httpx.Response(200, json={"pong": True})
        return httpx.Response(404)
    return httpx.MockTransport(handler)


@pytest.fixture
def served(tmp_path):
    path = tmp_path / "node.toml"
    path.write_text(CONFIG)
    cfg = node.load(path)
    cfg.key_path = str(tmp_path / "node_key")
    seen: list[httpx.Request] = []
    signer = Signer(cfg.key_path)
    app = node.create_app(cfg, signer=signer, transport=_seller(seen))
    with TestClient(app) as client:
        yield client, signer, seen


def test_the_documents_are_valid_and_signed(served):
    client, signer, _ = served
    wk = client.get("/.well-known/ai-market.json").json()
    assert validate_well_known(wk) == []
    assert Signer.verify_object_signature(wk, signer.public_key_b64)
    man = client.get("/ai-market/v2/manifest").json()
    assert validate_manifest(man) == []
    assert signer.verify_manifest_signature(man, signer.public_key_b64)
    assert [t["capability_id"] for t in man["tools"]] == ["gas.price@v1", "seller.ping@v1"]


def test_a_402_from_the_route_reaches_the_buyer_unchanged(served):
    client, _, seen = served
    r = client.post("/ai-market/v2/invoke", json={
        "capability_id": "gas.price@v1", "product_id": "seller", "input": {"chain": "base"}})
    assert r.status_code == 402
    assert r.headers["payment-required"] == _offer()
    assert seen[-1].method == "GET" and seen[-1].url.params["chain"] == "base"


def test_a_paid_retry_carries_the_payment_and_gets_a_signed_receipt(served):
    client, signer, seen = served
    r = client.post("/ai-market/v2/invoke", headers={"PAYMENT-SIGNATURE": "sig"}, json={
        "capability_id": "gas.price@v1", "product_id": "seller", "input": {"chain": "base"}})
    assert r.status_code == 200
    body = r.json()
    assert body["result"]["gwei"] == 0.005
    assert body["receipt"]["price_usd"] == 0.001
    assert signer.verify_receipt_signature(body["receipt"], signer.public_key_b64)
    assert r.headers["payment-response"] == "settled"
    assert seen[-1].headers["payment-signature"] == "sig"


def test_nested_input_to_a_get_route_is_refused(served):
    client, _, _ = served
    r = client.post("/ai-market/v2/invoke", json={
        "capability_id": "gas.price@v1", "input": {"chain": {"x": 1}}})
    assert r.status_code == 400


def _assay(client, tmp_path, free_first: bool):
    async def get_json(url):
        path = url.replace(NODE_URL, "")
        return client.get(path).json()

    async def post_json(url, body, headers):
        r = client.post(url.replace(NODE_URL, ""), json=body, headers=headers)
        try:
            data = r.json()
        except ValueError:
            data = {}
        return {"http_status": r.status_code, "json": data, "bytes": len(r.content),
                "headers": dict(r.headers)}

    async def judge_json(_body):
        return {"decision": "ok", "rationale": "live evidence"}

    db = HubDatabase(tmp_path / "assayer.db")
    db.upsert_peer(Peer(url=NODE_URL, name="Seller", trusted=False), status="pending")
    return asyncio.run(run_assay(
        NODE_URL, config=HubConfig(), db=db, signer=Signer(tmp_path / "assayer_key"),
        get_json=get_json, post_json=post_json, judge_json=judge_json, crawl_on_admit=False,
    ))


def test_the_hubs_own_assay_admits_the_node_on_its_free_route(served, tmp_path, monkeypatch):
    import aimarket_hub.crawler as crawler

    monkeypatch.setattr(crawler, "_url_is_safe", lambda u: u.startswith("https://"))
    client, _, _ = served
    dossier = _assay(client, tmp_path, free_first=True)
    assert dossier["verdict"] == "pass", dossier["checks"]
    assert dossier["sandbox"]["capability_id"] == "seller.ping@v1"
    assert dossier["sandbox"]["probe_kind"] == "free"


def test_a_paid_only_node_is_admitted_on_its_x402_v2_door(tmp_path, monkeypatch):
    import aimarket_hub.crawler as crawler

    monkeypatch.setattr(crawler, "_url_is_safe", lambda u: u.startswith("https://"))
    path = tmp_path / "node.toml"
    path.write_text(CONFIG.split("[[capability]]\nid = \"seller.ping@v1\"")[0])
    cfg = node.load(path)
    cfg.key_path = str(tmp_path / "node_key")
    app = node.create_app(cfg, signer=Signer(cfg.key_path), transport=_seller([]))
    with TestClient(app) as client:
        dossier = _assay(client, tmp_path, free_first=False)
    assert dossier["verdict"] == "pass", dossier["checks"]
    assert dossier["sandbox"]["probe_kind"] == "paid"
    assert dossier["sandbox"]["payment_challenge"]["recipient"] == PAY_TO


@pytest.mark.parametrize("bad,needle", [
    ('name = ""\nurl = "https://a"\nupstream = "http://b"\n', "name is required"),
    ('name = "x"\nurl = "ftp://a"\nupstream = "http://b"\n', "url must be"),
    ('name = "x"\nurl = "https://a"\nupstream = "http://b"\n', "at least one"),
    ('name = "x"\nurl = "https://a"\nupstream = "http://b"\n[[capability]]\nid = "noversion"\npath = "/a"\n',
     "name.verb@v1"),
    ('name = "x"\nurl = "https://a"\nupstream = "http://b"\n[[capability]]\nid = "a.b@v1"\npath = "a"\n',
     "path must start"),
])
def test_a_bad_config_names_what_is_wrong(tmp_path, bad, needle):
    path = tmp_path / "node.toml"
    path.write_text(bad)
    with pytest.raises(ValueError, match=needle):
        node.load(path)


def test_the_template_loads(tmp_path):
    path = tmp_path / "node.toml"
    path.write_text(node.TEMPLATE)
    cfg = node.load(path)
    assert cfg.capabilities[0].id == "weather.now@v1"


def test_a_provider_key_travels_in_the_signed_manifest_and_a_bad_one_is_named(tmp_path):
    """The key a seller signs answers and delivery receipts with: what lets a hub tie a buyer's
    receipt to this listing (deliveries.py). It rides in the manifest the node signs."""
    key = base64.b64encode(bytes(range(32))).decode()
    path = tmp_path / "node.toml"
    path.write_text(CONFIG.replace('path = "/ping"', f'path = "/ping"\nprovider_pubkey = "{key}"'))
    cfg = node.load(path)
    signer = Signer(tmp_path / "key")
    tools = {t["capability_id"]: t for t in node.manifest(cfg, signer)["tools"]}
    assert tools["seller.ping@v1"]["provider_pubkey"] == key
    assert "provider_pubkey" not in tools["gas.price@v1"], "only where the operator stated one"
    path.write_text(CONFIG.replace('path = "/ping"', 'path = "/ping"\nprovider_pubkey = "not-a-key"'))
    with pytest.raises(ValueError, match="provider_pubkey must be a base64 Ed25519"):
        node.load(path)

