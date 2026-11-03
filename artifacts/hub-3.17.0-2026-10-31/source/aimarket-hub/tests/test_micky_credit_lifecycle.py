"""Micky Arun follow-up: real prepaid ledger, synthetic money, isolated SQLite.

These exercise the current credits implementation, not a replacement billing model.
The separate HTTP-flow tests cover whether provider outcomes select capture or release.
Here the important boundaries are exact reservation, single-winner resolution, competing
connections, rollback, and the deliberately separate operator refund interface.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import sqlite3
import threading

import pytest

from aimarket_hub import credits
from aimarket_hub.db_backend import SQLiteBackend
from aimarket_hub.migrations import Migrations


@pytest.fixture()
def credit_db(tmp_path):
    backend = SQLiteBackend(tmp_path / "micky-credits.db")
    Migrations(backend).apply()
    ledger = credits.CreditsLedger(backend)
    account = ledger.create_account("synthetic buyer", grant_usd=0.01)["account_id"]
    try:
        yield backend, ledger, account
    finally:
        backend.close()


def raw_state(backend, account):
    row = backend.execute(
        "SELECT balance_mc, held_mc, spent_mc, collateral_mc, granted_mc, topped_up_mc "
        "FROM credit_accounts WHERE account_id = ?", (account,),
    ).fetchone()
    return {key: int(row[key]) for key in row.keys()}


def assert_conserved(backend, account, *, operator_credit_mc=0):
    state = raw_state(backend, account)
    assert all(value >= 0 for value in state.values()), state
    held = backend.execute(
        "SELECT COALESCE(SUM(amount_mc), 0) AS total FROM credit_holds "
        "WHERE account_id = ? AND status = 'held'", (account,),
    ).fetchone()["total"]
    assert state["held_mc"] == held
    assert state["balance_mc"] + state["held_mc"] + state["spent_mc"] + state["collateral_mc"] == (
        state["granted_mc"] + state["topped_up_mc"] + operator_credit_mc
    ), state
    return state


def test_hold_moves_exact_millicents_without_spending(credit_db):
    backend, ledger, account = credit_db
    result = ledger.hold(account, 0.0059, "exact-price")
    assert result == {"held_usd": 0.0059, "remaining_balance": 0.0041}
    state = assert_conserved(backend, account)
    assert (state["balance_mc"], state["held_mc"], state["spent_mc"]) == (410, 590, 0)
    assert ledger.hold_status("exact-price")["status"] == "held"


@pytest.mark.parametrize("first", ["capture", "release"])
def test_first_resolution_wins_and_all_replays_are_noops(credit_db, first):
    backend, ledger, account = credit_db
    assert "error" not in ledger.hold(account, 0.004, "resolve-once")
    operation = ledger.capture_hold if first == "capture" else ledger.release_hold
    assert operation("resolve-once")[f"{first}d_usd"] == 0.004
    settled = raw_state(backend, account)
    expected_status = "captured" if first == "capture" else "released"
    for _ in range(3):
        assert ledger.capture_hold("resolve-once") == {"captured_usd": 0.0, "already": expected_status}
        assert ledger.release_hold("resolve-once") == {"released_usd": 0.0, "already": expected_status}
        assert raw_state(backend, account) == settled
    assert_conserved(backend, account)
    entries = backend.execute(
        "SELECT kind, amount_mc FROM credit_ledger WHERE receipt_id = ? ORDER BY id", ("resolve-once",),
    ).fetchall()
    assert [(row["kind"], row["amount_mc"]) for row in entries] == [("hold", 400), (first, 400)]


def test_failed_hold_leaves_no_reservation_or_ledger_entry(credit_db):
    backend, ledger, account = credit_db
    before = raw_state(backend, account)
    assert "insufficient credit" in ledger.hold(account, 0.01001, "too-much")["error"]
    assert ledger.hold_status("too-much") is None
    assert raw_state(backend, account) == before
    assert backend.execute(
        "SELECT COUNT(*) AS n FROM credit_ledger WHERE receipt_id = ?", ("too-much",),
    ).fetchone()["n"] == 0
    assert_conserved(backend, account)


def test_existing_receipt_cannot_be_repriced_or_rebound(credit_db):
    backend, ledger, account = credit_db
    other = ledger.create_account("other buyer", grant_usd=0.01)["account_id"]
    ledger.hold(account, 0.004, "immutable-receipt")
    before = raw_state(backend, account), raw_state(backend, other)
    assert "already used" in ledger.hold(account, 0.006, "immutable-receipt")["error"]
    assert "already used" in ledger.hold(other, 0.004, "immutable-receipt")["error"]
    assert ledger.capture_hold("immutable-receipt")["captured_usd"] == 0.004
    assert raw_state(backend, other) == before[1]
    assert_conserved(backend, account)
    assert_conserved(backend, other)


def test_disabled_account_and_disabled_rail_do_not_strand_existing_hold(credit_db, monkeypatch):
    backend, ledger, account = credit_db
    ledger.hold(account, 0.004, "before-disable")
    assert ledger.set_status(account, "disabled")["status"] == "disabled"
    monkeypatch.setenv("AIMARKET_CREDITS_ENABLED", "0")
    assert "error" in ledger.hold(account, 0.001, "after-disable")
    assert ledger.release_hold("before-disable")["released_usd"] == 0.004
    state = assert_conserved(backend, account)
    assert (state["balance_mc"], state["held_mc"], state["spent_mc"]) == (1000, 0, 0)


@pytest.mark.parametrize("separate_connections", [False, True], ids=["shared-connection", "independent-connections"])
def test_real_concurrent_holds_cannot_overspend(credit_db, separate_connections):
    backend, ledger, account = credit_db
    workers = 12
    barrier = threading.Barrier(workers)
    peers = [SQLiteBackend(backend.db_path) for _ in range(workers)] if separate_connections else []

    def reserve(i):
        worker = credits.CreditsLedger(peers[i]) if peers else ledger
        barrier.wait(timeout=20)
        return worker.hold(account, 0.004, f"parallel-{i}")

    try:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            results = list(executor.map(reserve, range(workers)))
    finally:
        for peer in peers:
            peer.close()
    assert sum("error" not in result for result in results) == 2
    assert sum("insufficient credit" in result.get("error", "") for result in results) == 10
    state = assert_conserved(backend, account)
    assert (state["balance_mc"], state["held_mc"], state["spent_mc"]) == (200, 800, 0)


def test_capture_and_release_racing_on_independent_connections_have_one_winner(credit_db):
    backend, ledger, account = credit_db
    ledger.hold(account, 0.004, "racing-resolution")
    workers = 12
    barrier = threading.Barrier(workers)
    peers = [SQLiteBackend(backend.db_path) for _ in range(workers)]

    def settle(i):
        worker = credits.CreditsLedger(peers[i])
        barrier.wait(timeout=20)
        return (worker.capture_hold if i % 2 else worker.release_hold)("racing-resolution")

    try:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            results = list(executor.map(settle, range(workers)))
    finally:
        for peer in peers:
            peer.close()
    assert sum(result.get("captured_usd", 0.0) + result.get("released_usd", 0.0) for result in results) == 0.004
    assert sum("already" in result for result in results) == workers - 1
    final = ledger.hold_status("racing-resolution")["status"]
    state = assert_conserved(backend, account)
    assert (state["balance_mc"], state["held_mc"], state["spent_mc"]) == (
        (600, 0, 400) if final == "captured" else (1000, 0, 0)
    )
    assert backend.execute(
        "SELECT COUNT(*) AS n FROM credit_ledger WHERE receipt_id = ? AND kind IN ('capture', 'release')",
        ("racing-resolution",),
    ).fetchone()["n"] == 1


def test_routing_debits_and_call_holds_compete_for_the_same_balance(credit_db):
    backend, ledger, account = credit_db
    workers = 12
    barrier = threading.Barrier(workers)
    peers = [SQLiteBackend(backend.db_path) for _ in range(workers)]

    def spend(i):
        worker = credits.CreditsLedger(peers[i])
        barrier.wait(timeout=20)
        return (worker.debit if i % 2 else worker.hold)(account, 0.004, f"mixed-{i}")

    try:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            results = list(executor.map(spend, range(workers)))
    finally:
        for peer in peers:
            peer.close()
    accepted = [result for result in results if "error" not in result]
    assert len(accepted) == 2
    state = assert_conserved(backend, account)
    assert state["balance_mc"] == 200
    assert state["held_mc"] == 400 * sum("held_usd" in result for result in accepted)
    assert state["spent_mc"] == 400 * sum("debited_usd" in result for result in accepted)


@pytest.mark.parametrize("operation", ["hold", "capture", "release"])
def test_real_sqlite_ledger_failure_rolls_back_the_whole_move(credit_db, operation):
    backend, ledger, account = credit_db
    if operation != "hold":
        ledger.hold(account, 0.004, "rollback")
    before = raw_state(backend, account), ledger.hold_status("rollback")
    # SQLite itself rejects the append-only ledger write. No ledger method is mocked.
    backend.execute(
        "CREATE TRIGGER synthetic_ledger_failure BEFORE INSERT ON credit_ledger "
        "BEGIN SELECT RAISE(ABORT, 'synthetic ledger storage failure'); END"
    )
    backend.commit()
    with pytest.raises(sqlite3.IntegrityError, match="synthetic ledger storage failure"):
        if operation == "hold":
            ledger.hold(account, 0.004, "rollback")
        elif operation == "capture":
            ledger.capture_hold("rollback")
        else:
            ledger.release_hold("rollback")
    assert (raw_state(backend, account), ledger.hold_status("rollback")) == before
    assert_conserved(backend, account)


@pytest.mark.parametrize("parent_open", [True, False], ids=["allowance-open", "allowance-closed"])
def test_failed_child_returns_to_open_allowance_or_buyer_balance(credit_db, parent_open):
    backend, ledger, account = credit_db
    ledger.hold(account, 0.008, "allowance")
    ledger.transfer_hold("allowance", "child", 0.003)
    assert "error" in ledger.transfer_hold("allowance", "over-budget-child", 0.006)
    assert ledger.hold_status("over-budget-child") is None
    if not parent_open:
        ledger.release_hold("allowance")
    answer = ledger.release_hold("child")
    assert answer["released_usd"] == 0.003
    state = assert_conserved(backend, account)
    if parent_open:
        assert answer["returned_to"] == "allowance"
        assert (state["balance_mc"], state["held_mc"], state["spent_mc"]) == (200, 800, 0)
        assert ledger.hold_amount_usd("allowance") == 0.008
    else:
        assert "returned_to" not in answer
        assert (state["balance_mc"], state["held_mc"], state["spent_mc"]) == (1000, 0, 0)


def test_release_is_not_an_operator_refund(credit_db):
    backend, ledger, account = credit_db
    ledger.hold(account, 0.004, "provider-failed")
    ledger.release_hold("provider-failed")
    ledger.hold(account, 0.004, "provider-succeeded")
    ledger.capture_hold("provider-succeeded")
    assert ledger.refund(account, 0.004, note="operator revenue reversal")["refunded_usd"] == 0.004
    state = assert_conserved(backend, account)
    assert (state["balance_mc"], state["held_mc"], state["spent_mc"]) == (1000, 0, 0)
    refunds = backend.execute(
        "SELECT receipt_id, amount_mc, note FROM credit_ledger WHERE kind = 'refund'"
    ).fetchall()
    assert len(refunds) == 1
    assert dict(refunds[0]) == {"receipt_id": "", "amount_mc": 400, "note": "operator revenue reversal"}
    kinds = [row["kind"] for row in backend.execute(
        "SELECT kind FROM credit_ledger WHERE receipt_id = ?", ("provider-failed",),
    ).fetchall()]
    assert kinds == ["hold", "release"]


def test_operator_refund_has_no_receipt_replay_or_spend_cap(credit_db):
    """Characterize the trusted operator primitive; this is not a customer endpoint.

    Its contract allows goodwill credit, not just reversal of a particular receipt.
    Consequently a caller must not assume replay safety or a cap at captured funds.
    """
    backend, ledger, account = credit_db
    assert ledger.refund(account, 0.004, note="same operator instruction")["balance_usd"] == 0.014
    assert ledger.refund(account, 0.004, note="same operator instruction")["balance_usd"] == 0.018
    state = assert_conserved(backend, account, operator_credit_mc=800)
    assert (state["balance_mc"], state["held_mc"], state["spent_mc"]) == (1800, 0, 0)
    assert backend.execute("SELECT COUNT(*) AS n FROM credit_ledger WHERE kind = 'refund'").fetchone()["n"] == 2


def test_hold_age_alone_does_not_expire_or_increase_its_capture_amount(credit_db):
    """Expiry is a separate recovery sweep, not an automatic property of this ledger."""
    backend, ledger, account = credit_db
    ledger.hold(account, 0.004, "aged-hold")
    backend.execute(
        "UPDATE credit_holds SET created_at = '2000-01-01 00:00:00' WHERE receipt_id = ?", ("aged-hold",),
    )
    backend.commit()
    assert ledger.hold_status("aged-hold") == {"account_id": account, "amount_usd": 0.004, "status": "held"}
    assert ledger.capture_hold("aged-hold")["captured_usd"] == 0.004
    state = assert_conserved(backend, account)
    assert (state["balance_mc"], state["held_mc"], state["spent_mc"]) == (600, 0, 400)
