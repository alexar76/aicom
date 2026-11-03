"""Controlled observations for Micky Arun's expiry/recovery questions.

These exercise the current prepaid-credit implementation.  The last test records a
separate transfer-channel behaviour; it is not evidence that credits are escrowed
or that releasing a hold transfers USDC to the buyer.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from aimarket_hub import credits, invoke_funding, mandates
from aimarket_hub.channels import ChannelLedger
from aimarket_hub.database import HubDatabase


@pytest.fixture
def credit_state(tmp_path):
    db = HubDatabase(tmp_path / "micky-credits.db")
    try:
        yield db, credits.CreditsLedger(db._conn), mandates.MandateStore(db._conn, "https://hub.test")
    finally:
        db.close()


def test_old_credit_key_and_balance_do_not_expire_automatically(credit_state):
    db, ledger, _ = credit_state
    opened = ledger.create_account(label="old prepaid buyer", grant_usd=1.0)
    account = opened["account_id"]
    db._conn.execute("UPDATE credit_accounts SET created_at = '2000-01-01 00:00:00' WHERE account_id = ?",
                     (account,))
    db._conn.commit()
    assert ledger.resolve(opened["api_key"]) == account
    assert ledger.hold(account, 0.01, "old-key-call")["remaining_balance"] == pytest.approx(0.99)
    assert ledger.release_hold("old-key-call")["released_usd"] == pytest.approx(0.01)
    assert ledger.balance(account) == pytest.approx(1.0)
    assert not ledger.set_status(account, "disabled").get("error")
    assert ledger.resolve(opened["api_key"]) == ""
    assert ledger.hold(account, 0.01, "disabled-key-call").get("error")
    assert ledger.balance(account) == pytest.approx(1.0)


def test_abandoned_credit_hold_recovers_only_after_the_age_boundary(credit_state):
    db, ledger, store = credit_state
    account = ledger.create_account(grant_usd=1.0)["account_id"]
    assert not ledger.hold(account, 0.20, "abandoned").get("error")
    db._conn.execute("UPDATE credit_holds SET created_at = '2000-01-01 00:00:00' WHERE receipt_id = ?",
                     ("abandoned",))
    db._conn.commit()
    created = datetime(2000, 1, 1, tzinfo=timezone.utc).timestamp()
    at_boundary = invoke_funding.sweep_stale_credit_holds(
        credits_ledger=ledger, store=store, now=created + 3600.0)
    assert at_boundary == 0
    assert ledger.hold_status("abandoned")["status"] == "held"
    after_boundary = invoke_funding.sweep_stale_credit_holds(
        credits_ledger=ledger, store=store, now=created + 3600.001)
    assert after_boundary == 1
    assert ledger.hold_status("abandoned")["status"] == "released"
    assert ledger.balance(account) == pytest.approx(1.0)
    assert ledger.account(account)["spent_usd"] == pytest.approx(0)
    assert invoke_funding.sweep_stale_credit_holds(
        credits_ledger=ledger, store=store, now=created + 7200) == 0
    assert ledger.balance(account) == pytest.approx(1.0)


def test_release_restores_credit_and_preserves_the_operator_liability(credit_state):
    _, ledger, _ = credit_state
    account = ledger.create_account(grant_usd=1.0)["account_id"]
    before = ledger.stats()
    ledger.hold(account, 0.20, "failed")
    held = ledger.stats()
    assert held["held_usd"] == pytest.approx(0.20)
    assert held["outstanding_credit_usd"] == pytest.approx(before["outstanding_credit_usd"])
    ledger.release_hold("failed")
    released = ledger.stats()
    assert released["held_usd"] == pytest.approx(0)
    assert released["outstanding_credit_usd"] == pytest.approx(1.0)
    assert released["credits_earned_usd"] == pytest.approx(0)
    assert ledger.balance(account) == pytest.approx(1.0)


def test_signed_mandate_expiry_is_an_exclusive_boundary(monkeypatch, tmp_path):
    from tests._mandate_kit import HUB, hub, setup_mandate

    with hub(monkeypatch, tmp_path) as (client, db):
        signed = setup_mandate(client, db)
        store = mandates.MandateStore(db._conn, HUB)
        chain = store.chain(signed["digest"])
        deadline = chain[-1].valid_until.timestamp()
        assert store.chain(signed["digest"], now=deadline - 0.001)
        with pytest.raises(mandates.MandateError, match="not valid now"):
            store.chain(signed["digest"], now=deadline)
        assert credits.CreditsLedger(db._conn).balance(signed["account"]) == pytest.approx(1.0)


def test_transfer_channel_expiry_waits_for_a_sweep_and_pending_hold_resolution(tmp_path):
    """Observed limitation of the separate channel ledger, not a credit-account guarantee.

    Wall-clock expiry alone currently does not reject a debit/hold on an open row.
    A sweep also defers closure until held work is resolved; then it records a debt.
    """
    ledger = ChannelLedger(db_path=str(tmp_path / "channels.db"))
    ledger.stop_sweep()
    try:
        opened = ledger.open(1.0, wallet="0xMickyFixture")["channel"]
        cid, secret = opened["channel_id"], opened["channel_secret"]
        with ledger._get_conn() as conn:
            conn.execute("UPDATE channels SET expires_at = '2000-01-01T00:00:00Z' WHERE channel_id = ?", (cid,))
            conn.commit()
        assert ledger.debit(cid, 0.10, receipt_id="after-deadline", secret=secret)["ok"]
        assert ledger.hold(cid, 0.20, receipt_id="pending", secret=secret)["ok"]
        assert ledger._sweep_expired() == 0
        assert ledger.get(cid)["status"] == "open"
        assert ledger.release_hold("pending")["ok"]
        assert ledger._sweep_expired() == 1
        assert ledger.get(cid)["status"] == "expired"
        assert ledger.obligations()[0]["amount_usd"] == pytest.approx(0.90)
        assert ledger.debit(cid, 0.01, receipt_id="after-sweep", secret=secret).get("error")
    finally:
        ledger.stop_sweep()
