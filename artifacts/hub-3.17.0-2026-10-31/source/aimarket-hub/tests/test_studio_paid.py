"""Payment planning must precede work; response loss must never buy work twice."""
from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import time

import pytest
from fastapi.testclient import TestClient
from fastapi import HTTPException

from aimarket_hub import settle
from aimarket_hub.api import create_app
from aimarket_hub.config import HubConfig
from aimarket_hub.database import HubDatabase
from aimarket_hub.models import Capability, Peer
from aimarket_hub.signing import Signer
from aimarket_hub.studio_paid import AdvanceRequest, PaidStudio, PreflightRequest

SELLER = "0x" + "12" * 20
WALLET = "0x" + "34" * 20
TX = "0x" + "56" * 32


def listing(db, *, cid="demo.read@v1", price=0.004, source="local", payout=SELLER, **kwargs):
    cap = Capability(product_id="demo-product", capability_id=cid, name=cid,
                     source_hub=source, payout_address=payout, price_per_call_usd=price,
                     prompt_template='{"reading":7}', **kwargs)
    db.upsert_capability(cap)
    return cap


def node(nid="read", cid="demo.read@v1", **kwargs):
    return dict(id=nid, product_id="demo-product", capability_id=cid, source_hub="local", input={}, **kwargs)


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setenv("AIMARKET_AUTO_CRAWL", "0")
    monkeypatch.setenv("AIMARKET_X402_ENABLED", "1")
    monkeypatch.setenv("AIMARKET_X402_ACCEPT", "1")
    monkeypatch.setenv("AIMARKET_X402_CHAIN", "base")
    monkeypatch.delenv("AIMARKET_X402_ASSET", raising=False)
    monkeypatch.setenv("AIMARKET_MARKET_FEE_BPS", "0")
    monkeypatch.setenv("AIMARKET_SETTLE_RPC_URL", "http://127.0.0.1:1")
    monkeypatch.setenv("AIMARKET_INVOKE_RATE_PER_MIN", "100000")
    config = HubConfig()
    config.db_path = str(tmp_path / "hub.db")
    config.signing_key_path = str(tmp_path / "key")
    db = HubDatabase(config.db_path)
    signer = Signer(config.signing_key_path)
    seen = []

    async def invoke(payload, headers, caller):
        seen.append((payload, headers, caller))
        return 200, {"success": True, "result": {"reading": 7}, "receipt": {"nonce": "receipt-1"}}

    service = PaidStudio(db=db, config=config, signer=signer, invoke=invoke, route_ok=lambda c: True)
    listing(db)
    return service, db, seen


def quote(service, nodes=None, **kwargs):
    return service.preflight(PreflightRequest(nodes=nodes or [node()], **kwargs))


def advance(service, q, *, step="read", tx=None, wallet=WALLET):
    return asyncio.run(service.advance(q["run_id"], q["access_token"],
        AdvanceRequest(step_id=step, wallet=wallet, tx_hash=tx), "buyer.test"))


def verified(monkeypatch, *, wallet=WALLET):
    def verify(**kw):
        terms = kw["terms"]
        return dict(tx_hash=kw["tx_hash"], paid_units=terms.seller_units, fee_units=terms.fee_units,
                    nonce=kw["require_nonce"], authorizer=wallet, pay_to=terms.pay_to, confirmations=2)
    monkeypatch.setattr(settle, "verify_transfer", verify)


def test_preflight_quotes_external_local_seller_without_executing_or_crediting(setup):
    service, db, seen = setup
    q = quote(service)
    assert q["ready"] and q["total_units"] == "4000"
    assert q["steps"][0]["terms"]["pay_to"] == SELLER
    assert q["steps"][0]["payment_rail"] == "seller_direct"
    assert seen == []
    assert db._conn.execute("SELECT COUNT(*) AS n FROM settle_invoices").fetchone()["n"] == 0
    assert db._conn.execute("SELECT COUNT(*) AS n FROM credit_accounts").fetchone()["n"] == 0


@pytest.mark.parametrize("nodes", [
    [node(), node()],
    [node(depends_on=["absent"])],
    [node(depends_on=["read"])],
    [node(), node("other", input_from="read")],
    [{**node(), "input": {"reading": "${absent.reading}"}}],
])
def test_bad_graph_is_refused_before_any_purchase(setup, nodes):
    service, _, seen = setup
    assert not quote(service, nodes)["ready"]
    assert not seen


def test_budget_price_and_schema_are_checked_before_payment(setup):
    service, db, seen = setup
    assert not quote(service, max_budget_usd=0.003)["ready"]
    listing(db, input_schema={"type": "object", "required": ["city"], "properties": {"city": {"type": "string"}}})
    assert not quote(service)["ready"]
    q = quote(service, [{**node(), "input": {"city": "Berlin"}}])
    assert q["ready"]
    listing(db, price=0.005)
    out = advance(service, q)
    assert out["status"] == "failed" and "terms changed" in out["bill_of_materials"]["steps"][0]["error"]
    assert not seen


def test_peer_without_settlement_route_is_named_before_payment(setup):
    service, db, seen = setup
    listing(db, source="https://peer.test")
    q = quote(service, [{**node(), "source_hub": "https://peer.test"}])
    assert not q["ready"] and "bills independently" in q["blockers"][0]["detail"]
    assert not seen


def test_same_sku_at_different_origins_keeps_its_own_payee(setup):
    service, db, _ = setup
    listing(db, source="https://peer.test", payout="0x" + "ab" * 20)
    service.config.sells_on_behalf_of = lambda source: source == "https://peer.test"
    q = quote(service, [node(), {**node("peer"), "source_hub": "https://peer.test"}])
    assert q["ready"]
    assert [s["terms"]["pay_to"] for s in q["steps"]] == [SELLER, "0x" + "ab" * 20]


def test_payment_must_be_verified_and_retries_reuse_one_invoice(setup, monkeypatch):
    service, _, seen = setup
    q = quote(service)
    first = advance(service, q)
    nonce = first["next_step"]["invoice"]["nonce"]
    assert advance(service, q)["next_step"]["invoice"]["nonce"] == nonce
    monkeypatch.setattr(settle, "verify_transfer", lambda **kw: (_ for _ in ()).throw(settle.PaymentError("not mined")))
    pending = advance(service, q, tx=TX)
    assert pending["next_step"]["status"] == "payment_pending" and not seen
    assert pending["bill_of_materials"]["payment_unresolved"] == ["read"]
    verified(monkeypatch)
    done = advance(service, q, tx=TX)
    assert done["status"] == "completed" and len(seen) == 1
    assert done["bill_of_materials"]["total_usd"] == 0.004
    assert done["bill_of_materials"]["remaining_budget_usd"] == 0
    assert done["bill_of_materials"]["signature"]["algorithm"] == "ed25519"
    assert Signer.verify_object_signature(done["bill_of_materials"], service.signer.public_key_b64)
    assert not Signer.verify_object_signature(
        {**done["bill_of_materials"], "total_usd": 0}, service.signer.public_key_b64)
    assert set(seen[0][1]) == {"X-Payment", "X-Payment-Nonce", "X-Payment-Secret"}
    assert "secret" not in json.dumps(done).lower()
    assert advance(service, q, tx=TX) == done
    assert len(seen) == 1


def test_failure_keeps_paid_materials_and_does_not_purchase_later_steps(setup, monkeypatch):
    service, db, seen = setup
    listing(db, cid="demo.end@v1", price=0.002)
    q = quote(service, [node(), node("end", "demo.end@v1", depends_on=["read"])])
    async def fail(*args):
        seen.append(args)
        return 502, {"error": "provider failed"}
    service.invoke = fail
    advance(service, q)
    verified(monkeypatch)
    out = advance(service, q, tx=TX)
    assert out["status"] == "failed" and len(seen) == 1
    assert out["bill_of_materials"]["total_usd"] == 0.004
    assert out["bill_of_materials"]["remaining_budget_usd"] == 0.002
    assert out["bill_of_materials"]["steps"][1]["status"] == "queued"


def test_each_paid_run_result_and_receipt_is_returned_with_a_signed_private_result_digest(setup):
    service, db, _ = setup
    listing(db, price=0)
    listing(db, cid="demo.end@v1", price=0)
    outputs = {"demo.read@v1": {"name": "Private Counterparty Ω", "found": True},
               "demo.end@v1": {"registered": True}}
    receipts = {}

    async def invoke(payload, *_args):
        cid = payload["capability_id"]
        receipt = {"nonce": cid, "result_hash": hashlib.sha256(json.dumps(outputs[cid]).encode()).hexdigest()}
        receipt["signature"] = service.signer.sign_object(receipt)
        receipts[cid] = receipt
        return 200, {"success": True, "result": outputs[cid], "receipt": receipt}

    service.invoke = invoke
    q = quote(service, [node(), node("end", "demo.end@v1")])
    advance(service, q)
    out = advance(service, q, step="end")
    assert out["step_results"] == {"read": {"result": outputs["demo.read@v1"], "receipt": receipts["demo.read@v1"]},
                                    "end": {"result": outputs["demo.end@v1"], "receipt": receipts["demo.end@v1"]}}
    bill = out["bill_of_materials"]
    expected = hashlib.sha256(json.dumps(outputs["demo.read@v1"], sort_keys=True,
        separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()).hexdigest()
    assert bill["steps"][0]["result_sha256"] == expected
    assert "Private Counterparty" not in json.dumps(bill)
    assert "response_result" not in bill["steps"][0] and "result" not in bill["steps"][0]
    assert Signer.verify_object_signature(bill, service.signer.public_key_b64)
    tampered = copy.deepcopy(bill)
    tampered["steps"][0]["result_sha256"] = "0" * 64
    assert not Signer.verify_object_signature(tampered, service.signer.public_key_b64)
    state, _ = service.load(q["run_id"], q["access_token"])
    assert service.view(state)["step_results"] == out["step_results"]


def test_paid_error_retains_returned_evidence_without_inventing_evidence_for_queued_steps(setup):
    service, db, _ = setup
    listing(db, price=0)
    listing(db, cid="demo.end@v1", price=0)
    evidence = {"source_status": "unavailable"}
    receipt = {"nonce": "failed-check", "signature": {"value": "original-rejection"}}

    async def fail(*_args):
        return 503, {"success": False, "result": evidence, "receipt": receipt, "error": "registry unavailable"}

    service.invoke = fail
    q = quote(service, [node(), node("end", "demo.end@v1")])
    out = advance(service, q)
    assert out["status"] == "failed"
    assert out["step_results"] == {"read": {"result": evidence, "receipt": receipt}}
    assert out["bill_of_materials"]["steps"][1]["status"] == "queued"
    assert "result_sha256" not in out["bill_of_materials"]["steps"][1]


def test_references_are_resolved_and_validated_before_next_payment(setup, monkeypatch):
    service, db, seen = setup
    listing(db, cid="demo.end@v1", price=0, input_schema={"type": "object", "required": ["reading"],
        "properties": {"reading": {"type": "integer"}}})
    q = quote(service, [node(), {**node("end", "demo.end@v1", depends_on=["read"]), "input": {"reading": "${read.reading}"}}])
    assert q["ready"]
    advance(service, q)
    verified(monkeypatch)
    advance(service, q, tx=TX)
    out = advance(service, q, step="end")
    assert out["status"] == "completed"
    assert seen[-1][0]["input"] == {"reading": 7} and seen[-1][1] == {}


def test_wrong_wallet_does_not_dispatch_but_money_stays_in_bill(setup, monkeypatch):
    service, _, seen = setup
    q = quote(service)
    advance(service, q)
    verified(monkeypatch, wallet=SELLER)
    out = advance(service, q, tx=TX)
    assert out["status"] == "failed" and not seen
    assert out["bill_of_materials"]["total_usd"] == 0.004


@pytest.mark.asyncio
async def test_concurrent_requests_dispatch_only_once_and_reload_can_read_bill(setup, monkeypatch):
    service, db, seen = setup
    q = quote(service)
    body = AdvanceRequest(step_id="read", wallet=WALLET)
    await service.advance(q["run_id"], q["access_token"], body, "buyer")
    verified(monkeypatch)
    entered, release = asyncio.Event(), asyncio.Event()
    async def invoke(*args):
        seen.append(args)
        entered.set()
        await release.wait()
        return 200, {"success": True, "result": {"reading": 7}}
    service.invoke = invoke
    body.tx_hash = TX
    one = asyncio.create_task(service.advance(q["run_id"], q["access_token"], body, "buyer"))
    await entered.wait()
    two = await service.advance(q["run_id"], q["access_token"], body, "buyer")
    assert two["busy"] and len(seen) == 1
    release.set()
    await one
    recovered = PaidStudio(db=db, config=service.config, signer=service.signer, invoke=invoke, route_ok=lambda c: True)
    state, busy = recovered.load(q["run_id"], q["access_token"])
    assert not busy and recovered.view(state)["status"] == "completed"


def test_expired_quote_does_not_prepare_payment(setup):
    service, _, seen = setup
    q = quote(service)
    state, _ = service.load(q["run_id"], q["access_token"])
    state["expires_at"] = time.time() - 1
    service.save(state, unlock=True)
    assert advance(service, q)["status"] == "failed"
    assert not seen


def test_http_paid_run_uses_existing_settlement_without_spending_hub_credits(setup, monkeypatch):
    service, db, _ = setup
    verified(monkeypatch)
    app = create_app(config=service.config, db=db, signer=service.signer)
    with TestClient(app) as client:
        q = client.post("/studio/preflight", json={"nodes": [node()]}).json()
        assert q["ready"], q
        path = f"/studio/paid-runs/{q['run_id']}"
        assert client.get(path).status_code == 404
        headers = {"X-Studio-Run-Token": q["access_token"], "X-API-Key": "not-a-credit-source"}
        prepared = client.post(path + "/advance", json={"step_id": "read", "wallet": WALLET}, headers=headers)
        assert prepared.status_code == 200, prepared.text
        result = client.post(path + "/advance", json={"step_id": "read", "wallet": WALLET, "tx_hash": TX}, headers=headers)
        assert result.status_code == 200, result.text
        out = result.json()
        assert out["status"] == "completed", out
        assert out["final_result"] == {"reading": 7}
        assert out["bill_of_materials"]["total_usd"] == 0.004
        invoice = db._conn.execute("SELECT consumed_at FROM settle_invoices").fetchone()
        assert invoice["consumed_at"] > 0
        assert client.get(path, headers=headers).json() == out


def test_federated_seller_is_paid_through_the_existing_peer_route(setup, monkeypatch):
    import httpx
    import aimarket_hub.outbound_http as outbound
    service, db, _ = setup
    source = "https://studio-peer.test"
    monkeypatch.setenv("AIMARKET_SELLS_FOR", source)
    monkeypatch.setenv("AIMARKET_CREDITS_ENABLED", "1")
    db.upsert_peer(Peer(url=source, name="External seller", well_known_url=source + "/.well-known/ai-market.json", trusted=True))
    listing(db, source=source)
    verified(monkeypatch)
    calls = []

    async def get(url, **kw):
        return httpx.Response(200, json={"mcp_endpoint": source + "/invoke"})

    async def post(url, **kw):
        calls.append((url, kw))
        return httpx.Response(200, json={"success": True, "result": {"reading": 12}})

    monkeypatch.setattr(outbound, "safe_get", get)
    monkeypatch.setattr(outbound, "safe_post", post)
    app = create_app(config=service.config, db=db, signer=service.signer)
    with TestClient(app) as client:
        q = client.post("/studio/preflight", json={"nodes": [{**node(), "source_hub": source}]}).json()
        assert q["ready"] and not calls, q
        headers = {"X-Studio-Run-Token": q["access_token"]}
        path = f"/studio/paid-runs/{q['run_id']}/advance"
        client.post(path, json={"step_id": "read", "wallet": WALLET}, headers=headers)
        out = client.post(path, json={"step_id": "read", "wallet": WALLET, "tx_hash": TX}, headers=headers).json()
        assert out["status"] == "completed", out
        assert out["final_result"] == {"reading": 12}
        assert len(calls) == 1
        sent = calls[0][1]["headers"]
        assert sent["X-Payment"] == TX
        assert "X-AIMarket-Sandbox-Visitor" not in sent
        assert "X-Payment-Channel" not in sent


def test_lost_dispatch_result_requires_reconciliation_instead_of_reexecution(setup, monkeypatch):
    service, _, seen = setup
    q = quote(service)
    advance(service, q)
    verified(monkeypatch)
    async def lost(*args):
        seen.append(args)
        raise RuntimeError("lost provider response")
    service.invoke = lost
    with pytest.raises(RuntimeError):
        advance(service, q, tx=TX)
    out = advance(service, q, tx=TX)
    assert out["busy"] and out["status"] == "reconciliation_required"
    assert out["bill_of_materials"]["total_usd"] == 0.004
    assert len(seen) == 1


def test_schema_references_are_local_only(setup, monkeypatch):
    import urllib.request
    service, db, _ = setup
    def forbidden(*args, **kwargs):
        pytest.fail("schema validation must never fetch a remote reference")
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    listing(db, input_schema={"$ref": "http://127.0.0.1/private-schema"})
    q = quote(service)
    assert not q["ready"] and "unresolved reference" in q["blockers"][0]["detail"]
    listing(db, input_schema={"$defs": {"input": {"type": "object"}}, "$ref": "#/$defs/input"})
    assert quote(service)["ready"]


def test_wrong_resume_request_preserves_pending_payment(setup, monkeypatch):
    service, _, seen = setup
    q = quote(service)
    advance(service, q)
    monkeypatch.setattr(settle, "verify_transfer", lambda **kw: (_ for _ in ()).throw(settle.PaymentError("not mined")))
    pending = advance(service, q, tx=TX)
    for kwargs in ({"wallet": SELLER}, {"tx": "0x" + "ab" * 32}):
        with pytest.raises(HTTPException) as error:
            advance(service, q, **kwargs)
        assert error.value.status_code == 409
        state, busy = service.load(q["run_id"], q["access_token"])
        assert not busy and service.view(state) == pending
    verified(monkeypatch)
    assert advance(service, q, tx=TX)["status"] == "completed"
    assert len(seen) == 1


def test_invalid_token_is_rejected_at_preflight(setup, monkeypatch):
    service, _, seen = setup
    monkeypatch.setenv("AIMARKET_X402_ASSET", "not-an-evm-address")
    q = quote(service)
    assert not q["ready"] and "invalid payment token" in q["blockers"][0]["detail"]
    assert not seen


def test_a_reverted_payment_frees_the_step_instead_of_pending_forever(setup, monkeypatch):
    """verify_transfer's terminal answer (reverted, mined after expiry, the wrong transfer) used to be
    saved as 'Payment not yet verified', with no route to fail or re-pay the step."""
    service, _, seen = setup
    q = quote(service)
    advance(service, q)
    monkeypatch.setattr(settle, "verify_transfer", lambda **kw: (_ for _ in ()).throw(settle.PaymentFinal("transaction reverted")))
    out = advance(service, q, tx=TX)
    assert out["next_step"]["status"] == "awaiting_payment" and "nothing was dispatched" in out["detail"]
    assert out["bill_of_materials"]["payment_unresolved"] == [] and seen == []
    verified(monkeypatch)
    done = advance(service, q, tx="0x" + "77" * 32)
    assert done["status"] == "completed" and len(seen) == 1


def test_a_started_run_outlives_its_quote(setup, monkeypatch):
    """The 15-minute quote used to be re-checked before every unpaid step, free ones included,
    so a slow graph failed midway after earlier steps had been paid."""
    service, db, seen = setup
    listing(db, cid="demo.end@v1", price=0)
    q = quote(service, [node(), node("end", "demo.end@v1", depends_on=["read"])])
    advance(service, q)
    verified(monkeypatch)
    advance(service, q, tx=TX)
    state, _ = service.load(q["run_id"], q["access_token"])
    state["expires_at"] = 0
    service.save(state, unlock=True)
    done = advance(service, q, step="end")
    assert done["status"] == "completed" and len(seen) == 2


def test_quotes_nobody_started_are_purged_and_started_runs_are_kept(setup, monkeypatch):
    service, db, _ = setup
    idle, started = quote(service), quote(service)
    advance(service, started)
    db._conn.execute("UPDATE studio_paid_runs SET expires_at = 1")
    db._conn.commit()
    quote(service)  # any new preflight sweeps
    ids = {r["run_id"] for r in db._conn.execute("SELECT run_id FROM studio_paid_runs")}
    assert idle["run_id"] not in ids and started["run_id"] in ids
