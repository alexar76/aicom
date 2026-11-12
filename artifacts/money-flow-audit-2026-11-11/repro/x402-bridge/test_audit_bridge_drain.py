"""Audit repro (scratch only): bridge losses on undelivered paid calls are unbounded per buyer, and the
per-seller daily cap is keyed by payee address, which the seller itself publishes."""

from __future__ import annotations

import os

import pytest

from aimarket_hub import credits, x402_bridge
from tests.test_x402_bridge import (  # noqa: F401
    SETTLED, _Resp, _Seller, _buyer, _hub, _invoke, _offer, _payments, _v2_402, bridge_env,
)

PAYEES = ["0x" + f"{i:040x}" for i in range(1, 6)]  # five payees the seller publishes


def test_one_small_top_up_drains_bridge_via_settle_then_refuse(tmp_path, monkeypatch, bridge_env):
    bridge_env["usd"] = 100.0           # the wallet
    monkeypatch.setenv("AIMARKET_INVOKE_RATE_LIMIT", "100000")
    # Seller publishes 5 payees in its own well-known; each paid call: settles, answers 200 {"success": false}.
    calls_per_payee = 10                # 10 x $0.05 = $0.50 = per-"seller" daily cap, per payee
    script = []
    for p in PAYEES:
        for _ in range(calls_per_payee):
            script.append(_Resp(402, {}, _v2_402(_offer(amount="50000", pay_to=p))))
            script.append(_Resp(200, {"success": False, "refuse_reason": "nope", "data": "the work"}, SETTLED))
    seller = _Seller(*script, well_known={"payment": {"enforced": True, "protocol": "x402", "accepts": [
        {"network": "base", "pay_to": p} for p in PAYEES]}})
    client, db = _hub(tmp_path, monkeypatch, seller, price=0.05)
    key, account = _buyer(topped_up=0.05)   # one $0.05 top-up

    statuses = []
    for _ in range(len(PAYEES) * calls_per_payee):
        r = _invoke(client, key)
        statuses.append(r.status_code)
    rows = _payments(db)
    paid_out = sum(r["amount_usd"] for r in rows if r["status"] == "undelivered")
    print("http:", sorted(set(statuses)), "rows:", len(rows), "undelivered paid out $", round(paid_out, 6))
    print("buyer balance", credits.ledger().balance(account), "spent", credits.ledger().account(account)["spent_usd"])
    # Buyer paid in $0.05 and was charged nothing; the bridge settled $2.50 to one seller in one day,
    # five times the documented $0.50 per-seller daily cap.
    assert credits.ledger().balance(account) == pytest.approx(0.05)
    assert credits.ledger().account(account)["spent_usd"] == 0
    assert paid_out == pytest.approx(2.50)
    assert len({r["pay_to"].lower() for r in rows}) == 5


def test_granted_credit_reaches_a_stranger_after_paid_credit_was_spent_locally(tmp_path, monkeypatch, bridge_env):
    seller = _Seller(_Resp(402, {}, _v2_402(_offer(amount="50000"))),
                     _Resp(200, {"ok": True, "result": 1}, SETTLED))
    client, db = _hub(tmp_path, monkeypatch, seller, price=0.05)
    key, account = _buyer(topped_up=0.05)
    ledger = credits.ledger()
    # The paid-in $0.05 is spent on something else (a plain debit stands in for a local capability).
    assert not ledger.debit(account, 0.05, receipt_id="local_1", note="local capability").get("error")
    # Then the operator grants $0.05 (signup bonus, promo...).
    ledger.grant(account, 0.05, note="promo")
    assert ledger.balance(account) == pytest.approx(0.05)
    r = _invoke(client, key)
    print("status", r.status_code, "rows", _payments(db))
    assert r.status_code == 200
    # Granted credit just became $0.05 USDC in the seller's wallet.
    assert [p["status"] for p in _payments(db)] == ["delivered"]


def test_a_json_array_answer_after_payment_is_paid_but_never_delivered(tmp_path, monkeypatch, bridge_env):
    seller = _Seller(_Resp(402, {}, _v2_402(_offer(amount="1000"))), _Resp(200, [{"row": 1}], SETTLED),
                     _Resp(402, {}, _v2_402(_offer(amount="1000"))), _Resp(200, [{"row": 1}], SETTLED))
    client, db = _hub(tmp_path, monkeypatch, seller, price=0.002)
    key, account = _buyer(topped_up=1.0)
    a, b = _invoke(client, key), _invoke(client, key)
    print(a.status_code, a.text[:120], b.status_code, [p["status"] for p in _payments(db)])
    assert a.status_code == b.status_code == 502
    assert [p["status"] for p in _payments(db)] == ["undelivered", "undelivered"]
    assert credits.ledger().account(account)["spent_usd"] == 0
