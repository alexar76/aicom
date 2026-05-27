"""UNI wallet security regressions (audit C/H items)."""

from __future__ import annotations

import json
import re
import uuid

import pytest

from core.uni.wallet import InsufficientFundsError, UniWalletService


@pytest.fixture
def uni_svc(tmp_path, monkeypatch):
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path / "data"))
    monkeypatch.setenv("AIFACTORY_UNI_ENABLED", "1")
    monkeypatch.setenv("AIFACTORY_UNI_TOPUP_SPREAD_BPS", "0")
    import core.uni.store as uni_store

    uni_store._sqlite_conn = None
    return UniWalletService()


def test_topup_idempotent_no_double_balance(uni_svc):
    owner = f"cust-{uuid.uuid4().hex[:8]}"
    tx = f"0x{uuid.uuid4().hex}"
    a = uni_svc.topup_from_chain(owner, usd_amount=10.0, tx_hash=tx, chain="base", token="USDT")
    b = uni_svc.topup_from_chain(owner, usd_amount=10.0, tx_hash=tx, chain="base", token="USDT")
    assert a["wallet"]["balance_uni"] == 1000
    assert b.get("duplicate") is True
    assert b["wallet"]["balance_uni"] == 1000


def test_hold_conditional_rejects_overdraft(uni_svc):
    owner = f"cust-{uuid.uuid4().hex[:8]}"
    uni_svc.topup_from_chain(owner, usd_amount=1.0, tx_hash=f"0x{uuid.uuid4().hex}", chain="base", token="USDT")
    with pytest.raises(InsufficientFundsError):
        uni_svc.hold(owner, amount_uni=200, channel_id=f"ch_{uuid.uuid4().hex[:8]}")


def test_available_uni_is_balance_minus_hold(uni_svc):
    owner = f"cust-{uuid.uuid4().hex[:8]}"
    uni_svc.topup_from_chain(owner, usd_amount=5.0, tx_hash=f"0x{uuid.uuid4().hex}", chain="base", token="USDT")
    ch = f"ch_{uuid.uuid4().hex[:8]}"
    uni_svc.hold(owner, amount_uni=300, channel_id=ch)
    w = uni_svc.get_wallet_by_owner(owner)
    assert w["balance_uni"] == 200
    assert w["hold_uni"] == 300
    assert w["available_uni"] == 0


def test_spend_hold_duplicate_not_free(uni_svc):
    owner = f"cust-{uuid.uuid4().hex[:8]}"
    uni_svc.topup_from_chain(owner, usd_amount=10.0, tx_hash=f"0x{uuid.uuid4().hex}", chain="base", token="USDT")
    ch = f"ch_{uuid.uuid4().hex[:8]}"
    uni_svc.hold(owner, amount_uni=500, channel_id=ch)
    ref = "prod/cap/nonce1"
    first = uni_svc.spend_hold(channel_id=ch, amount_uni=100, ref=ref)
    second = uni_svc.spend_hold(channel_id=ch, amount_uni=100, ref=ref)
    assert first.get("ok") is True
    assert second.get("duplicate") is True
    assert second.get("ok") is False


def test_receipt_signature_roundtrip():
    from core.uni.receipts import issue_receipt, verify_receipt

    r = issue_receipt(
        wallet_id="uni_wal_test",
        kind="grant",
        amount_uni=42,
        meta={"note": "test"},
        idempotency_key=f"test-{uuid.uuid4().hex}",
    )
    assert verify_receipt(r) is True
    r["amount_uni"] = "999"
    assert verify_receipt(r) is False


def test_receipt_captures_and_signs_trace_id(monkeypatch):
    """When an OTel trace is active, issue_receipt MUST stamp the trace_id into
    the signed payload, and tampering with it MUST invalidate the signature."""
    from core.uni import receipts as receipts_mod
    from core.uni.receipts import issue_receipt, verify_receipt

    fake_trace = "a" * 32
    monkeypatch.setattr(
        "core.tracing.current_trace_id_hex",
        lambda: fake_trace,
    )

    r = issue_receipt(
        wallet_id="uni_wal_trace_test",
        kind="invoke",
        amount_uni=10,
        meta={},
        idempotency_key=f"trace-{uuid.uuid4().hex}",
    )

    # 1) trace_id captured into the payload
    assert r.get("trace_id") == fake_trace
    # 2) signature verifies over the trace-id-bearing payload
    assert verify_receipt(r) is True
    # 3) tampering with trace_id breaks the signature (signed, not decorative)
    r_tampered = dict(r)
    r_tampered["trace_id"] = "b" * 32
    assert verify_receipt(r_tampered) is False


def test_receipt_duplicate_returns_prior_receipt(uni_svc):
    """M-10: idempotent retry must return the ORIGINAL receipt, not an empty dict."""
    owner = f"cust-{uuid.uuid4().hex[:8]}"
    tx = f"0x{uuid.uuid4().hex}"
    a = uni_svc.topup_from_chain(owner, usd_amount=5.0, tx_hash=tx, chain="base", token="USDT")
    b = uni_svc.topup_from_chain(owner, usd_amount=5.0, tx_hash=tx, chain="base", token="USDT")
    assert b.get("duplicate") is True
    # The duplicate path must surface the existing receipt so the caller can
    # quote it downstream without re-issuing.
    assert b.get("receipt") is not None
    assert b["receipt"].get("id") == a["receipt"]["id"]


def test_list_receipts_includes_seller_side(uni_svc):
    """L-1: list_receipts_for_wallet must use the v2 columns to also surface
    receipts where the wallet is the seller (default role='any')."""
    from core.uni.receipts import list_receipts_for_wallet

    buyer = f"buyer-{uuid.uuid4().hex[:8]}"
    seller = f"seller-{uuid.uuid4().hex[:8]}"
    uni_svc.topup_from_chain(buyer, usd_amount=10.0, tx_hash=f"0x{uuid.uuid4().hex}", chain="base", token="USDT")
    out = uni_svc.charge(
        buyer,
        seller_owner_id=seller,
        amount_uni=200,
        meta={"product_id": "p1"},
        idempotency_key=f"charge-{uuid.uuid4().hex}",
    )
    seller_wallet_id = out["seller"]["wallet_id"]
    # seller-side: SELECT from uni_receipts WHERE seller_wallet_id = ?
    sales = list_receipts_for_wallet(seller_wallet_id, role="seller")
    assert len(sales) >= 1
    assert any(rec.get("kind") == "invoke" for rec in sales)
