"""Scratch repro: a browser-driven Studio paid run whose process dies (or whose request task
is cancelled) while the buyer's payment is being verified stays busy=1 for ever: nothing was
dispatched, the payment is valid, yet no later advance can dispatch and no refund can be prepared."""
from __future__ import annotations

import asyncio
import json

import pytest

from aimarket_hub import settle
from aimarket_hub.config import HubConfig
from aimarket_hub.database import HubDatabase
from aimarket_hub.models import Capability
from aimarket_hub.signing import Signer
from aimarket_hub.studio_paid import AdvanceRequest, PaidStudio, PreflightRequest

SELLER = "0x" + "12" * 20
WALLET = "0x" + "34" * 20
TX = "0x" + "56" * 32


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setenv("AIMARKET_AUTO_CRAWL", "0")
    monkeypatch.setenv("AIMARKET_X402_ENABLED", "1")
    monkeypatch.setenv("AIMARKET_X402_ACCEPT", "1")
    monkeypatch.setenv("AIMARKET_X402_CHAIN", "base")
    monkeypatch.delenv("AIMARKET_X402_ASSET", raising=False)
    monkeypatch.setenv("AIMARKET_MARKET_FEE_BPS", "0")
    monkeypatch.setenv("AIMARKET_SETTLE_RPC_URL", "http://127.0.0.1:1")
    config = HubConfig()
    config.db_path = str(tmp_path / "hub.db")
    config.signing_key_path = str(tmp_path / "key")
    db = HubDatabase(config.db_path)
    signer = Signer(config.signing_key_path)
    seen = []

    async def invoke(payload, headers, caller):
        seen.append(payload)
        return 200, {"success": True, "result": {"reading": 7}}

    db.upsert_capability(Capability(product_id="demo-product", capability_id="demo.read@v1",
                                    name="r", source_hub="local", payout_address=SELLER,
                                    price_per_call_usd=0.004, prompt_template="{}"))
    return config, db, signer, invoke, seen


def _studio(config, db, signer, invoke):
    return PaidStudio(db=db, config=config, signer=signer, invoke=invoke, route_ok=lambda c: True)


def _adv(svc, q, tx=None):
    return asyncio.run(svc.advance(q["run_id"], q["access_token"],
                                   AdvanceRequest(step_id="n0", wallet=WALLET, tx_hash=tx), "buyer"))


def _good_verify(**kw):
    t = kw["terms"]
    return dict(tx_hash=kw["tx_hash"], paid_units=t.seller_units, fee_units=t.fee_units,
                nonce=kw["require_nonce"], authorizer=WALLET, pay_to=t.pay_to, confirmations=2)


def test_crash_during_payment_verification_leaves_run_busy_forever(setup, monkeypatch):
    config, db, signer, invoke, seen = setup
    svc = _studio(config, db, signer, invoke)
    q = svc.preflight(PreflightRequest(nodes=[dict(product_id="demo-product",
                                                   capability_id="demo.read@v1", source_hub="local")]))
    assert q["ready"]
    _adv(svc, q)  # mints the invoice, step awaiting_payment

    snapshot = {}

    class Killed(BaseException):
        pass

    def dying_verify(**kw):
        # The DB as a SIGKILL (deploy, OOM) would leave it: the payment_pending save has run.
        row = db._conn.execute("SELECT state_json, busy FROM studio_paid_runs WHERE run_id = ?",
                               (q["run_id"],)).fetchone()
        snapshot.update(state_json=row["state_json"], busy=row["busy"])
        raise Killed()

    monkeypatch.setattr(settle, "verify_transfer", dying_verify)
    with pytest.raises(Killed):
        _adv(svc, q, tx=TX)
    # simulate SIGKILL: the except-BaseException handler never ran
    db._conn.execute("UPDATE studio_paid_runs SET state_json = ?, busy = ? WHERE run_id = ?",
                     (snapshot["state_json"], snapshot["busy"], q["run_id"]))
    db._conn.commit()
    assert snapshot["busy"] == 1
    assert json.loads(snapshot["state_json"])["steps"][0]["status"] == "payment_pending"

    # restart: a fresh process, the payment is now valid on chain
    monkeypatch.setattr(settle, "verify_transfer", _good_verify)
    svc2 = _studio(config, db, signer, invoke)
    for _ in range(3):
        out = _adv(svc2, q, tx=TX)
        assert out["busy"] is True and out["status"] == "active"
    assert seen == []  # never dispatched, buyer paid
    # The seller-refund route requires a terminal run, so it is closed too.
    # (pipeline_refunds.prepare: run['status'] not in ('completed','failed') -> 409)


def test_cancelled_request_before_dispatch_marks_reconciliation_and_locks(setup, monkeypatch):
    config, db, signer, invoke, seen = setup
    svc = _studio(config, db, signer, invoke)
    q = svc.preflight(PreflightRequest(nodes=[dict(product_id="demo-product",
                                                   capability_id="demo.read@v1", source_hub="local")]))
    _adv(svc, q)

    def cancelled(**kw):
        raise asyncio.CancelledError()

    monkeypatch.setattr(settle, "verify_transfer", cancelled)
    with pytest.raises(asyncio.CancelledError):
        _adv(svc, q, tx=TX)
    monkeypatch.setattr(settle, "verify_transfer", _good_verify)
    out = _adv(svc, q, tx=TX)
    assert out["busy"] is True and out["status"] == "reconciliation_required"
    assert seen == []  # nothing was ever dispatched, yet the run is locked as "uncertain"


def test_transient_inner_refusal_after_payment_ends_run_failed(setup, monkeypatch):
    """The inner /invoke answers 429 rate_limited (or 503 'payment verifier unavailable')
    BEFORE executing and releases the buyer's payment claim for a retry; the Studio marks the
    paid step and the run failed (terminal) and never shows the payment secret, so the buyer
    can neither retry through the Studio nor redeem the released claim elsewhere."""
    config, db, signer, invoke, seen = setup
    calls = []

    async def refusing(payload, headers, caller):
        calls.append(headers)
        return 429, {"success": False, "error": "rate_limited",
                     "detail": "invoke rate limit exceeded — slow down"}

    svc = _studio(config, db, signer, refusing)
    q = svc.preflight(PreflightRequest(nodes=[dict(product_id="demo-product",
                                                   capability_id="demo.read@v1", source_hub="local")]))
    _adv(svc, q)
    monkeypatch.setattr(settle, "verify_transfer", _good_verify)
    out = _adv(svc, q, tx=TX)
    assert out["status"] == "failed"
    assert out["bill_of_materials"]["total_usd"] == 0.004       # buyer's payment recorded
    assert len(calls) == 1 and "X-Payment-Secret" in calls[0]
    # a retry once the limiter has cooled down changes nothing: the run is terminal
    svc.invoke = invoke
    again = _adv(svc, q, tx=TX)
    assert again["status"] == "failed" and seen == []
    assert "secret" not in json.dumps(again).lower()
