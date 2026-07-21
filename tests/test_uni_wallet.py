"""UNI wallet service tests — fixed peg and fee economics."""

from __future__ import annotations

import uuid

import pytest

from core.uni.config import uni_enabled, uni_platform_fee_bps
from core.uni.pricing import usd_to_uni
from core.uni.wallet import InsufficientFundsError, UniWalletService


@pytest.fixture
def uni_svc(tmp_path, monkeypatch):
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path / "data"))
    monkeypatch.setenv("AIFACTORY_UNI_ENABLED", "1")
    monkeypatch.setenv("AIFACTORY_UNI_TOPUP_SPREAD_BPS", "0")
    monkeypatch.setenv("AIFACTORY_UNI_PLATFORM_FEE_BPS", "500")
    import core.uni.store as uni_store

    uni_store._sqlite_conn = None
    return UniWalletService()


def test_uni_enabled_by_default(monkeypatch):
    monkeypatch.delenv("AIFACTORY_UNI_ENABLED", raising=False)
    assert uni_enabled() is True


def test_fixed_peg_usd_to_uni():
    assert usd_to_uni(1.0) == 100
    assert usd_to_uni(10.0) == 1000


def test_wallet_topup_hold_spend(uni_svc):
    owner = f"cust-{uuid.uuid4().hex[:8]}"
    top = uni_svc.topup_from_chain(owner, usd_amount=10.0, tx_hash=f"0x{uuid.uuid4().hex}", chain="base", token="USDT")
    assert top["wallet"]["balance_uni"] == 1000

    ch_id = f"ch_{uuid.uuid4().hex[:8]}"
    hold = uni_svc.hold(owner, amount_uni=500, channel_id=ch_id)
    assert hold["amount_uni"] == 500
    w = uni_svc.get_wallet_by_owner(owner)
    assert w["balance_uni"] == 500
    assert w["hold_uni"] == 500

    spend = uni_svc.spend_hold(channel_id=ch_id, amount_uni=100, ref="cap/test")
    assert spend["ok"] is True
    assert spend["platform_fee_uni"] == 5
    assert spend["net_to_seller_uni"] == 95
    assert spend["remaining_uni"] == 400

    platform = uni_svc.get_or_create_platform_wallet()
    assert platform["balance_uni"] >= 5

    released = uni_svc.release_hold(ch_id)
    assert released["refund_uni"] == 400


def test_charge_splits_fee(uni_svc):
    buyer = f"buyer-{uuid.uuid4().hex[:6]}"
    seller = f"seller-{uuid.uuid4().hex[:6]}"
    uni_svc.topup_from_chain(buyer, usd_amount=5.0, tx_hash=f"0x{uuid.uuid4().hex}", chain="base", token="USDT")
    out = uni_svc.charge(buyer, seller_owner_id=seller, amount_uni=200, meta={"product_id": "p1"}, idempotency_key="c1")
    assert out["platform_fee_uni"] == 200 * uni_platform_fee_bps() // 10_000
    assert out["net_to_seller_uni"] == 200 - out["platform_fee_uni"]
    assert uni_svc.get_wallet_by_owner(buyer)["balance_uni"] == 500 - 200
    assert uni_svc.get_wallet_by_owner(seller)["balance_uni"] == out["net_to_seller_uni"]


def test_charge_insufficient(uni_svc):
    buyer = f"buyer-{uuid.uuid4().hex[:6]}"
    uni_svc.grant(buyer, amount_uni=10, ref="tiny", meta={})
    with pytest.raises(InsufficientFundsError):
        uni_svc.charge(buyer, seller_owner_id="seller-x", amount_uni=100, meta={}, idempotency_key="x1")


def test_topup_idempotent_on_tx_hash(uni_svc):
    owner = f"cust-{uuid.uuid4().hex[:8]}"
    tx = f"0x{uuid.uuid4().hex}"
    a = uni_svc.topup_from_chain(owner, usd_amount=4.0, tx_hash=tx, chain="base", token="USDT")
    b = uni_svc.topup_from_chain(owner, usd_amount=4.0, tx_hash=tx, chain="base", token="USDT")
    assert a["wallet"]["balance_uni"] == b["wallet"]["balance_uni"] == 400
    assert b.get("duplicate") is True


def test_economy_summary(uni_svc):
    owner = f"cust-{uuid.uuid4().hex[:8]}"
    uni_svc.grant(owner, amount_uni=250, ref="test-grant", meta={"reason": "test"})
    summary = uni_svc.economy_summary()
    assert summary["wallets"] >= 1
    assert summary["balance_uni_total"] >= 250


def test_treasury_audit_snapshot(uni_svc):
    from core.uni.treasury import snapshot_treasury_audit

    owner = f"cust-{uuid.uuid4().hex[:8]}"
    uni_svc.topup_from_chain(owner, usd_amount=2.0, tx_hash=f"0x{uuid.uuid4().hex}", chain="base", token="USDT")
    snap = snapshot_treasury_audit(usdt_observed=100.0)
    assert snap["total_uni_outstanding"] == 200
    assert snap["usdt_required"] == pytest.approx(2.0)
    assert snap["healthy"] is True
