"""Financial rejection, retry and competing-worker paths on both UNI databases."""
from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

from tests.test_payment_chain_recovery import isolated
from tests.test_uni_settlement_atomicity import setup_wallet, snapshot

pytestmark = pytest.mark.component_integration


def execute(sql, args=()):
    from core.uni.store import uni_connection

    with uni_connection() as conn:
        return conn.execute(sql.replace("?", "%s") if os.environ["UNI_DB_BACKEND"] == "postgres" else sql, args)


@pytest.mark.parametrize("operation,error", [
    ("charge", "charge amount must be positive"), ("hold", "hold amount must be positive"),
    ("spend", "spend amount must be positive"), ("minimum", "minimum_withdraw_uni"),
    ("fee", "withdraw amount too small after fee"),
])
def test_invalid_settlement_never_changes_financial_state(isolated, monkeypatch, operation, error):
    from core.uni.wallet import UniWalletError

    svc = setup_wallet()
    monkeypatch.setenv("AIFACTORY_UNI_MIN_WITHDRAW_UNI", "100")
    if operation == "fee":
        monkeypatch.setattr("core.uni.wallet.platform_fee_uni", lambda *a, **k: 100)
    calls = {
        "charge": lambda: svc.charge("buyer", seller_owner_id="seller", amount_uni=0, idempotency_key="invalid"),
        "hold": lambda: svc.hold("buyer", amount_uni=0, channel_id="invalid"),
        "spend": lambda: svc.spend_hold(channel_id="invalid", amount_uni=0),
        "minimum": lambda: svc.withdraw_to_chain("buyer", amount_uni=1, payout_address="test", chain="base"),
        "fee": lambda: svc.withdraw_to_chain("buyer", amount_uni=100, payout_address="test", chain="base"),
    }
    before = snapshot()
    with pytest.raises(UniWalletError, match=error):
        calls[operation]()
    assert snapshot() == before


@pytest.mark.parametrize("operation", ["charge", "hold", "withdraw"])
def test_insufficient_funds_roll_back_the_claim(isolated, monkeypatch, operation):
    from core.uni.wallet import InsufficientFundsError

    svc = setup_wallet()
    monkeypatch.setenv("AIFACTORY_UNI_MIN_WITHDRAW_UNI", "1")
    before = snapshot()
    with pytest.raises(InsufficientFundsError):
        if operation == "charge":
            svc.charge("buyer", seller_owner_id="seller", amount_uni=2000, idempotency_key="large")
        elif operation == "hold":
            svc.hold("buyer", amount_uni=2000, channel_id="large")
        else:
            svc.withdraw_to_chain("buyer", amount_uni=2000, payout_address="test", chain="base")
    assert snapshot() == before


def test_hold_retry_and_zero_fee_charge(isolated, monkeypatch):
    svc = setup_wallet()
    held = svc.hold("buyer", amount_uni=500, channel_id="same")
    before = snapshot()
    retry = svc.hold("buyer", amount_uni=500, channel_id="same")
    assert retry["duplicate"] and retry["hold_id"] == held["hold_id"]
    assert snapshot() == before
    monkeypatch.setenv("AIFACTORY_UNI_PLATFORM_FEE_BPS", "0")
    out = svc.charge("buyer", seller_owner_id="seller", amount_uni=10, idempotency_key="no-fee")
    assert out["platform_fee_uni"] == 0
    assert svc.get_wallet_by_owner("buyer")["balance_uni"] == 490
    assert svc.get_wallet_by_owner("seller")["balance_uni"] == 10


def test_legacy_hold_claim_without_reserve_record_fails_closed(isolated):
    from core.uni.wallet import UniWalletError

    svc = setup_wallet()
    svc.hold("buyer", amount_uni=100, channel_id="missing-record")
    execute("DELETE FROM uni_holds WHERE channel_id=?", ("missing-record",))
    before = snapshot()
    with pytest.raises(UniWalletError, match="hold_state_unavailable"):
        svc.hold("buyer", amount_uni=100, channel_id="missing-record")
    assert snapshot() == before


def test_duplicate_withdrawal_id_cannot_debit_twice(isolated, monkeypatch):
    from core.uni.wallet import UniWalletError

    svc = setup_wallet()
    monkeypatch.setenv("AIFACTORY_UNI_MIN_WITHDRAW_UNI", "1")
    monkeypatch.setattr("core.uni.wallet.uuid.uuid4", lambda: SimpleNamespace(hex="a" * 32))
    svc.withdraw_to_chain("buyer", amount_uni=500, payout_address="test", chain="base")
    before = snapshot()
    with pytest.raises(UniWalletError, match="duplicate_withdraw"):
        svc.withdraw_to_chain("buyer", amount_uni=500, payout_address="test", chain="base")
    assert snapshot() == before


@pytest.mark.parametrize("operation", ["charge", "grant", "spend"])
def test_legacy_committed_claim_without_receipt_fails_closed(isolated, operation):
    from core.uni.wallet import UniWalletError

    svc = setup_wallet()
    svc.hold("buyer", amount_uni=500, channel_id="legacy", seller_ref="seller")
    calls = {
        "charge": lambda: svc.charge("buyer", seller_owner_id="seller", amount_uni=100, idempotency_key="legacy"),
        "grant": lambda: svc.grant("buyer", amount_uni=100, ref="legacy", meta={}),
        "spend": lambda: svc.spend_hold(channel_id="legacy", amount_uni=100, ref="legacy"),
    }
    first = calls[operation]()
    execute("DELETE FROM uni_receipts WHERE receipt_id=?", (first["receipt"]["id"],))
    before = snapshot()
    with pytest.raises(UniWalletError, match="settlement_receipt_unavailable"):
        calls[operation]()
    assert snapshot() == before


@pytest.mark.parametrize("state", ["missing", "closed", "insufficient", "closed-during-lookup"])
def test_spend_rechecks_reserve_before_crediting_anyone(isolated, monkeypatch, state):
    from core.uni.wallet import UniWalletError

    svc = setup_wallet()
    if state != "missing":
        svc.hold("buyer", amount_uni=500, channel_id="boundary", seller_ref="seller")
    if state == "closed":
        svc.release_hold("boundary")
    if state == "closed-during-lookup":
        original = svc.get_or_create_wallet
        closed = False

        def close_before_settlement(owner, **kwargs):
            nonlocal closed
            if owner == "seller" and not closed:
                closed = True
                svc.release_hold("boundary")
            return original(owner, **kwargs)
        monkeypatch.setattr(svc, "get_or_create_wallet", close_before_settlement)
    with pytest.raises(UniWalletError, match="insufficient_hold" if state == "insufficient" else "hold_not_open"):
        svc.spend_hold(channel_id="boundary", amount_uni=600 if state == "insufficient" else 100)
    assert svc.get_wallet_by_owner("seller")["balance_uni"] == 0
    assert svc.get_or_create_platform_wallet()["balance_uni"] == 0


@pytest.mark.parametrize("missing_receipt", [False, True])
def test_worker_winning_between_spend_checks_is_not_paid_twice(isolated, monkeypatch, missing_receipt):
    from core.uni.wallet import UniWalletError

    svc = setup_wallet()
    svc.hold("buyer", amount_uni=500, channel_id="race", seller_ref="seller")
    original = svc.get_or_create_wallet
    won = False
    winner = None

    def competing_settlement(owner, **kwargs):
        nonlocal won, winner
        if owner == "seller" and not won:
            won = True
            winner = svc.spend_hold(channel_id="race", amount_uni=100, ref="same")
            if missing_receipt:
                execute("DELETE FROM uni_receipts WHERE receipt_id=?", (winner["receipt"]["id"],))
        return original(owner, **kwargs)
    monkeypatch.setattr(svc, "get_or_create_wallet", competing_settlement)
    if missing_receipt:
        with pytest.raises(UniWalletError, match="settlement_receipt_unavailable"):
            svc.spend_hold(channel_id="race", amount_uni=100, ref="same")
    else:
        retry = svc.spend_hold(channel_id="race", amount_uni=100, ref="same")
        assert retry["duplicate"] and retry["receipt"] == winner["receipt"]
    assert svc.get_wallet_by_owner("buyer")["hold_uni"] == 400
    assert svc.get_wallet_by_owner("seller")["balance_uni"] == 95
    assert svc.get_or_create_platform_wallet()["balance_uni"] == 5


def test_release_missing_closed_empty_and_legacy_claim(isolated, monkeypatch):
    from core.uni.wallet import UniWalletError

    svc = setup_wallet()
    with pytest.raises(UniWalletError, match="hold_not_found"):
        svc.release_hold("missing")
    svc.hold("buyer", amount_uni=200, channel_id="empty", seller_ref="seller")
    monkeypatch.setenv("AIFACTORY_UNI_PLATFORM_FEE_BPS", "0")
    spent = svc.spend_hold(channel_id="empty", amount_uni=200)
    assert spent["platform_fee_uni"] == 0
    assert svc.release_hold("empty")["refund_uni"] == 0
    assert svc.release_hold("empty")["refund_uni"] == 0
    svc.hold("buyer", amount_uni=100, channel_id="legacy-release")
    svc.release_hold("legacy-release")
    execute("UPDATE uni_holds SET status='open', remaining_uni=100 WHERE channel_id=?", ("legacy-release",))
    before = snapshot()
    assert svc.release_hold("legacy-release")["duplicate"] is True
    assert snapshot() == before


def test_receipt_trace_fallback_reserved_metadata_and_failed_readback(isolated, monkeypatch):
    from core.uni import receipts

    svc = setup_wallet()
    wallet_id = svc.get_wallet_by_owner("buyer")["wallet_id"]

    def no_trace():
        raise RuntimeError("tracer unavailable")
    monkeypatch.setattr("core.tracing.current_trace_id_hex", no_trace)
    receipt = receipts.issue_receipt(wallet_id=wallet_id, kind="test", amount_uni=1,
        meta={"wallet_id": "cannot-replace", "nested": {"ignored": True}}, idempotency_key="trace-fallback")
    assert receipt["wallet_id"] == wallet_id and "nested" not in receipt and "trace_id" not in receipt
    assert receipts.verify_receipt(receipt)
    before = snapshot()
    monkeypatch.setattr(receipts, "get_receipt_by_idempotency_key", lambda *a, **k: None)
    with pytest.raises(RuntimeError, match="settlement_receipt_unavailable"):
        receipts.issue_receipt(wallet_id=wallet_id, kind="test", amount_uni=1, meta={}, trace_id="explicit")
    assert snapshot() == before


@pytest.mark.parametrize("damaged", ['[]', 'null', '"text"', '12', 'invalid-json'])
def test_non_object_receipt_history_cannot_be_a_success_or_unused_transfer(isolated, damaged):
    from core.uni.receipts import find_topup_receipt, get_receipt, get_receipt_by_idempotency_key
    from core.uni.wallet import UniWalletError

    svc = setup_wallet()
    topup = svc.topup_from_chain("buyer", usd_amount=1, tx_hash="0x" + "ab" * 32)
    receipt_id = topup["receipt"]["id"]
    execute("UPDATE uni_receipts SET payload_json=? WHERE receipt_id=?", (damaged, receipt_id))
    before = snapshot()
    assert get_receipt(receipt_id) is None
    assert get_receipt_by_idempotency_key("topup:0x" + "ab" * 32) is None
    assert find_topup_receipt("0x" + "ab" * 32) == {}, "damaged history still pins a claimed transfer"
    with pytest.raises(UniWalletError, match="settlement_receipt_unavailable"):
        svc.topup_from_chain("buyer", usd_amount=1, tx_hash="0x" + "ab" * 32)
    assert snapshot() == before


def test_unknown_wallet_amount_is_not_assumed_zero(isolated):
    from core.uni.wallet import UniWalletError, UniWalletService

    with pytest.raises(UniWalletError, match="wallet_amount_unavailable"):
        UniWalletService._wallet_view({"balance_uni": None, "hold_uni": 0})
