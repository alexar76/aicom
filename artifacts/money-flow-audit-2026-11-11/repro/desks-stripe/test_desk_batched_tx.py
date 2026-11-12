"""Two desk invoices paid by two Transfer logs of ONE transaction (exchange/processor batch, Safe
multisend): the scan settles the first and never the second; confirm refuses it too."""
from __future__ import annotations

import os

os.environ["APP_ENV"] = "test"
os.environ["SCHEDULER_ENABLED"] = "false"
os.environ["HUB_MODE"] = "fixture"
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["SEED_DEMO"] = "true"
os.environ["JWT_SECRET"] = "test-secret-must-be-at-least-32b"
os.environ["PAY_MODE"] = "fixture"
os.environ["DESK_MODE"] = "live"
os.environ["DESK_ID"] = "tideline"

from desk_kernel.service import pay
from desk_kernel.service.config import current_claim, get_settings
from desk_kernel.service.db import Base, SessionLocal, engine
from desk_kernel.service.models import BaseInvoice
from desk_kernel.service.payfixture import get_fixture_rpc, reset_fixture_rpc


def test_second_invoice_in_same_tx_never_settles():
    get_settings.cache_clear(); current_claim.cache_clear(); reset_fixture_rpc()
    Base.metadata.drop_all(bind=engine); Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    a = pay.create_invoice(db, plan="solo")
    b = pay.create_invoice(db, plan="team")
    rpc = get_fixture_rpc()
    token = get_settings().pay_usdc_address
    t1 = rpc.inject_usdc_transfer(token=token, pay_to=a.pay_to, amount_raw=a.amount_raw)
    t2 = rpc.inject_usdc_transfer(token=token, pay_to=b.pay_to, amount_raw=b.amount_raw)
    # Make the second log part of the first transaction (one batched tx, two Transfer logs).
    second = rpc._logs[-1]
    second["transactionHash"] = t1.tx_hash
    second["blockNumber"] = rpc._logs[-2]["blockNumber"]
    second["logIndex"] = "0x1"
    rpc._receipts[t1.tx_hash]["logs"].append(second)
    rpc._receipts.pop(t2.tx_hash, None)
    settled = pay.scan_payments(db, rpc=rpc)
    db.refresh(a); db.refresh(b)
    print("settled:", settled, "a:", a.status, "b:", b.status)
    assert a.status == "paid"
    assert b.status != "paid"           # 149 USDC received, no key
    try:
        pay.confirm_invoice(db, b, t1.tx_hash, rpc=rpc)
        raise AssertionError("confirm settled it")
    except ValueError as exc:
        print("confirm(b):", exc)
        assert "already settled" in str(exc)
    pay.scan_payments(db, rpc=rpc)
    db.refresh(b)
    assert b.status != "paid"
    db.close()
