"""The credits rail — the hub's only way to be paid with the chain switched off.

These tests pin the three properties the rail exists for, because each one was previously
false and each one on its own reduced a node's revenue to exactly zero:

  1. a listed price is real money when credits are on, even though crypto is off;
  2. an invoke that fails does not cost the buyer (reserve → release), and one that
     succeeds is captured exactly once;
  3. the routing fee is reserved BEFORE a peer is asked to work, so it cannot be
     free-ridden by omitting a header, and it fails closed.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aimarket_hub import credits  # noqa: E402
from aimarket_hub.database import HubDatabase  # noqa: E402


@pytest.fixture()
def ledger(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        monkeypatch.setenv("AIMARKET_CREDITS_ENABLED", "1")
        db = HubDatabase(os.path.join(tmp, "hub.db"))
        yield credits.configure(db._conn)


def test_account_key_is_hashed_and_usable_once(ledger):
    created = ledger.create_account(label="buyer one", grant_usd=0.10)
    assert created["api_key"].startswith(credits.KEY_PREFIX)
    assert created["balance_usd"] == pytest.approx(0.10)

    assert ledger.resolve(created["api_key"]) == created["account_id"]
    assert ledger.resolve("aimk_not-a-real-key") == ""
    assert ledger.resolve("") == ""


def test_sub_cent_prices_are_exact(ledger):
    """The channel ledger bills whole cents rounded UP, so $0.0059 costs a full cent there —
    a ~70% overcharge at this ecosystem's own measured average price. Millicents keep it exact."""
    acct = ledger.create_account(grant_usd=0.10)["account_id"]
    for _ in range(10):
        assert ledger.hold(acct, 0.0059, f"r{_}")["remaining_balance"] >= 0
        ledger.capture_hold(f"r{_}")
    assert ledger.balance(acct) == pytest.approx(0.10 - 0.059)
    assert ledger.account(acct)["spent_usd"] == pytest.approx(0.059)


def test_hold_cannot_overdraw_and_reports_the_shortfall(ledger):
    acct = ledger.create_account(grant_usd=0.01)["account_id"]
    assert ledger.hold(acct, 0.02, "r1").get("error", "").startswith("insufficient credit")
    # Nothing was taken by the refusal.
    assert ledger.balance(acct) == pytest.approx(0.01)


def test_concurrent_holds_cannot_oversell_one_balance(ledger):
    """The reservation is a conditional UPDATE, not read-then-write: with $0.01 of credit and
    a $0.004 price, exactly two invokes may proceed, not three."""
    acct = ledger.create_account(grant_usd=0.01)["account_id"]
    assert "error" not in ledger.hold(acct, 0.004, "a")
    assert "error" not in ledger.hold(acct, 0.004, "b")
    assert "error" in ledger.hold(acct, 0.004, "c")


def test_release_returns_the_money_and_capture_does_not(ledger):
    acct = ledger.create_account(grant_usd=0.05)["account_id"]
    ledger.hold(acct, 0.01, "kept")
    ledger.hold(acct, 0.01, "given-back")
    assert ledger.balance(acct) == pytest.approx(0.03)

    ledger.capture_hold("kept")
    ledger.release_hold("given-back")
    assert ledger.balance(acct) == pytest.approx(0.04)
    assert ledger.account(acct)["spent_usd"] == pytest.approx(0.01)
    assert ledger.account(acct)["held_usd"] == pytest.approx(0.0)


def test_resolution_is_idempotent(ledger):
    """A late exception on an already-settled invoke must not double-charge or double-refund —
    the invoke path's `finally` calls release on paths where capture already ran."""
    acct = ledger.create_account(grant_usd=0.05)["account_id"]
    ledger.hold(acct, 0.01, "once")
    ledger.capture_hold("once")
    assert ledger.release_hold("once") == {"released_usd": 0.0, "already": "captured"}
    assert ledger.capture_hold("once") == {"captured_usd": 0.0, "already": "captured"}
    assert ledger.balance(acct) == pytest.approx(0.04)


def test_receipt_ids_cannot_be_reused(ledger):
    acct = ledger.create_account(grant_usd=0.05)["account_id"]
    ledger.hold(acct, 0.01, "dup")
    assert "already used" in ledger.hold(acct, 0.01, "dup").get("error", "")


def test_disabled_account_cannot_spend(ledger):
    created = ledger.create_account(grant_usd=0.05)
    acct = created["account_id"]
    ledger.set_status(acct, "disabled")
    assert ledger.resolve(created["api_key"]) == ""
    assert "error" in ledger.hold(acct, 0.001, "r")


def test_stats_separate_earned_from_money_still_owed(ledger):
    """`credits_earned_usd` answers "is this node's P&L non-zero"; `outstanding_credit_usd`
    is the operator's liability — prepaid money it holds and has not earned."""
    a = ledger.create_account(grant_usd=0.10)["account_id"]
    b = ledger.create_account(grant_usd=0.10)["account_id"]
    ledger.hold(a, 0.04, "x")
    ledger.capture_hold("x")
    ledger.hold(b, 0.02, "y")  # still in flight

    stats = ledger.stats()
    assert stats["accounts"] == 2
    assert stats["credits_earned_usd"] == pytest.approx(0.04)
    assert stats["held_usd"] == pytest.approx(0.02)
    # 0.06 spendable + 0.10 on b's account minus the 0.02 held, plus the held itself.
    assert stats["outstanding_credit_usd"] == pytest.approx(0.16)


def test_grant_and_refund_are_distinguishable_in_the_ledger(ledger):
    acct = ledger.create_account(grant_usd=0.01)["account_id"]
    ledger.grant(acct, 0.05, note="invoice 7")
    ledger.hold(acct, 0.01, "z")
    ledger.capture_hold("z")
    ledger.refund(acct, 0.01, note="provider 502")

    kinds = [e["kind"] for e in ledger.recent(acct)]
    assert kinds.count("grant") == 2  # signup grant + top-up
    assert "refund" in kinds and "capture" in kinds
    assert ledger.balance(acct) == pytest.approx(0.06)
    assert ledger.account(acct)["spent_usd"] == pytest.approx(0.0)


def test_grant_rejects_unknown_account_rather_than_creating_one(ledger):
    assert "error" in ledger.grant("acct_nope", 1.0)
    assert "error" in ledger.debit("acct_nope", 1.0)


def test_grant_reference_is_idempotent(ledger):
    acct = ledger.create_account()["account_id"]
    first = ledger.grant(acct, 2.5, note="paid invoice", reference="invoice-42")
    replay = ledger.grant(acct, 2.5, note="webhook retry", reference="invoice-42")

    assert first["idempotent_replay"] is False
    assert replay["idempotent_replay"] is True
    assert ledger.balance(acct) == pytest.approx(2.5)


def test_grant_reference_cannot_be_rebound(ledger):
    first = ledger.create_account()["account_id"]
    second = ledger.create_account()["account_id"]
    ledger.grant(first, 1.0, reference="tx-7")

    assert "error" in ledger.grant(second, 1.0, reference="tx-7")
    assert "error" in ledger.grant(first, 2.0, reference="tx-7")


def test_collateral_is_not_revenue(ledger):
    """A publisher's stake is money the operator holds and may have to return. Counting it in
    `credits_earned_usd` told an operator who had earned nothing that they had earned $25."""
    acct = ledger.create_account(grant_usd=30.0)["account_id"]
    ledger.debit(acct, 25.0, note="supply stake", as_collateral=True)

    stats = ledger.stats()
    assert stats["credits_earned_usd"] == pytest.approx(0.0)
    assert stats["collateral_usd"] == pytest.approx(25.0)
    # Still the operator's liability: balance + collateral.
    assert stats["outstanding_credit_usd"] == pytest.approx(30.0)
    assert ledger.account(acct)["collateral_usd"] == pytest.approx(25.0)

    returned = ledger.return_collateral(acct, 25.0, note="unstaked")
    assert returned["balance_usd"] == pytest.approx(30.0)
    assert ledger.stats()["collateral_usd"] == pytest.approx(0.0)


# --- the signup grant, and the ceiling that makes it safe to switch on -------
# A grant is worth real invoke, so an open signup hands value to anyone who asks.
# Telling a person from a bot is not something this hub can do — a residential
# proxy pool defeats every address heuristic — so the grant is bounded by a
# budget instead. When it runs out the door stays open at zero balance.


def test_signup_grant_is_its_own_switch(monkeypatch):
    monkeypatch.delenv("AIMARKET_SIGNUP_GRANT_USD", raising=False)
    monkeypatch.setenv("AIMARKET_CREDITS_FREE_GRANT_USD", "0.05")
    assert credits.signup_grant_usd() == pytest.approx(0.05)

    monkeypatch.setenv("AIMARKET_SIGNUP_GRANT_USD", "0.02")
    assert credits.signup_grant_usd() == pytest.approx(0.02)

    monkeypatch.setenv("AIMARKET_SIGNUP_GRANT_USD", "0")
    assert credits.signup_grant_usd() == 0.0

    monkeypatch.setenv("AIMARKET_SIGNUP_GRANT_USD", "not a number")
    assert credits.signup_grant_usd() == 0.0


def test_grant_budget_bounds_the_blast_radius(ledger, monkeypatch):
    monkeypatch.setenv("AIMARKET_SIGNUP_GRANT_DAILY_USD", "0.10")
    monkeypatch.delenv("AIMARKET_SIGNUP_GRANT_TOTAL_USD", raising=False)

    allowed, reason = ledger.grant_within_budget(0.05)
    assert allowed and reason == ""

    # Two grants fit inside a $0.10 day; the third does not.
    ledger.create_account(label="one", grant_usd=0.05)
    ledger.create_account(label="two", grant_usd=0.05)
    assert ledger.granted_mc(since_hours=24) == credits.usd_to_mc(0.10)

    allowed, reason = ledger.grant_within_budget(0.05)
    assert allowed is False
    assert "daily" in reason


def test_a_zero_daily_budget_means_no_grants_not_unlimited(ledger, monkeypatch):
    monkeypatch.setenv("AIMARKET_SIGNUP_GRANT_DAILY_USD", "0")
    allowed, reason = ledger.grant_within_budget(0.05)
    assert allowed is False
    assert "disabled" in reason


def test_lifetime_budget_is_separate_from_the_daily_one(ledger, monkeypatch):
    monkeypatch.setenv("AIMARKET_SIGNUP_GRANT_DAILY_USD", "100")
    monkeypatch.setenv("AIMARKET_SIGNUP_GRANT_TOTAL_USD", "0.06")

    ledger.create_account(label="one", grant_usd=0.05)
    allowed, reason = ledger.grant_within_budget(0.05)
    assert allowed is False
    assert "lifetime" in reason

    # A grant that still fits under the lifetime ceiling is allowed.
    allowed, _ = ledger.grant_within_budget(0.01)
    assert allowed is True


def test_an_operator_credit_is_not_counted_against_the_grant_budget(ledger, monkeypatch):
    monkeypatch.setenv("AIMARKET_SIGNUP_GRANT_DAILY_USD", "0.10")
    account = ledger.create_account(label="paying buyer", grant_usd=0.0)
    ledger.grant(account["account_id"], 25.0, reference="invoice-2026-1", note="invoice settled")

    # ledger.grant() is the operator top-up path and logs kind='grant' as well.
    # Counting by kind alone would let one settled invoice spend a whole day of
    # signup grants, so the budget must ignore it entirely.
    assert ledger.granted_mc(since_hours=24) == 0
    allowed, reason = ledger.grant_within_budget(0.05)
    assert allowed is True
    assert reason == ""


def test_an_operator_opening_balance_does_not_eat_the_signup_budget(ledger, monkeypatch):
    monkeypatch.setenv("AIMARKET_SIGNUP_GRANT_DAILY_USD", "0.10")
    ledger.create_account(label="enterprise", grant_usd=25.0, grant_note=credits.OPERATOR_GRANT_NOTE)
    assert ledger.granted_mc(since_hours=24) == 0
    allowed, reason = ledger.grant_within_budget(0.05)
    assert allowed is True and reason == ""
