"""Two ledgers on one database never lose, mint or double-book channel money.

An outside review (2026-10-23) asked whether two concurrent closes of one channel could
settle it twice. Inside one hub process the ledger's lock serialized every money move, but
the moves were read-then-write: the balance was read, a new one computed in Python, and
written back as an absolute value. A second process on the same database (another hub
worker, a CLI beside the server, two hubs on one PostgreSQL) is not covered by that lock.
Measured with two ledgers on one SQLite file before the fix:

* 240 concurrent debits, all answered ok with 240 receipts, left used_cents at 120;
* a close racing a 30-cent debit booked the whole $1 deposit as owed in 59 of 60 trials
  (the 30 cents were spent and owed back);
* two closes both answered "settled" in 59 of 60 trials.

Each move is now one conditional statement (still open, enough balance, hold still held),
so the database picks the winner against the row as it is at write time.
"""
from __future__ import annotations

import itertools
import sqlite3
import threading

import pytest

from aimarket_hub.channels import ChannelLedger

_IDS = itertools.count()


@pytest.fixture(autouse=True)
def _crypto_enabled(monkeypatch):
    monkeypatch.setenv("AIFACTORY_CRYPTO_ENABLED", "1")
    monkeypatch.setenv("AIMARKET_ALLOW_DEMO_CREDIT", "1")


@pytest.fixture
def two_ledgers(tmp_path):
    db = tmp_path / "channels.db"
    ledgers = [ChannelLedger(db_path=str(db)), ChannelLedger(db_path=str(db))]
    for ledger in ledgers:
        ledger._MAX_CHANNELS = 10_000
    yield ledgers, str(db)
    for ledger in ledgers:
        ledger.stop_sweep()
        # The backend keeps a shared connection open (database, WAL, shm). Left open, the
        # descriptors pile up across the suite until select() in test_mcp_stdio fails.
        ledger._backend.close()


def _open(ledger, usd):
    r = ledger.open(usd, wallet=f"0xW{next(_IDS)}")
    ch = r["channel"]
    return ch["channel_id"], ch["channel_secret"], ch["wallet"]


def _row(db, channel_id):
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    try:
        row = con.execute("SELECT * FROM channels WHERE channel_id = ?", (channel_id,)).fetchone()
        owed = con.execute(
            "SELECT COALESCE(SUM(amount_cents), 0) FROM channel_payout_obligations WHERE channel_id = ?",
            (channel_id,),
        ).fetchone()[0]
        receipts = con.execute(
            "SELECT COUNT(*), COALESCE(SUM(amount_cents), 0) FROM debited_receipts WHERE channel_id = ?",
            (channel_id,),
        ).fetchone()
        held = con.execute(
            "SELECT COALESCE(SUM(amount_cents), 0) FROM channel_holds WHERE channel_id = ? AND status = 'held'",
            (channel_id,),
        ).fetchone()[0]
    finally:
        con.close()
    return dict(row), owed, tuple(receipts), held


def _run(*targets):
    threads = [threading.Thread(target=t) for t in targets]
    for t in threads:
        t.start()
    for t in threads:
        t.join()


def test_concurrent_debits_from_two_ledgers_are_all_recorded(two_ledgers):
    (a, b), db = two_ledgers
    cid, secret, _ = _open(a, 5.0)
    ok = []

    def spend(ledger):
        def go():
            for _ in range(30):
                if ledger.debit(cid, 0.01, receipt_id=f"r{next(_IDS)}", secret=secret).get("ok"):
                    ok.append(1)
        return go

    _run(spend(a), spend(b), spend(a), spend(b))
    row, _, (n_receipts, receipt_cents), _ = _row(db, cid)
    assert len(ok) == n_receipts == 120
    assert row["used_cents"] == receipt_cents == 120
    assert row["balance_cents"] + row["used_cents"] == row["original_deposit_cents"] == 500


def test_debits_past_the_balance_never_overdraw(two_ledgers):
    (a, b), db = two_ledgers
    cid, secret, _ = _open(a, 0.5)

    def spend(ledger):
        def go():
            for _ in range(20):
                ledger.debit(cid, 0.03, receipt_id=f"r{next(_IDS)}", secret=secret)
        return go

    _run(spend(a), spend(b), spend(a), spend(b))
    row, _, (n_receipts, receipt_cents), _ = _row(db, cid)
    assert row["balance_cents"] >= 0
    assert n_receipts == 16 and receipt_cents == row["used_cents"] == 48
    assert row["balance_cents"] + row["used_cents"] == 50


def test_a_close_racing_a_debit_owes_only_what_was_not_spent(two_ledgers):
    (a, b), db = two_ledgers
    for _ in range(25):
        cid, secret, wallet = _open(a, 1.0)
        out = {}
        _run(
            lambda: out.update(close=a.close(cid, wallet=wallet, secret=secret)),
            lambda: out.update(debit=b.debit(cid, 0.30, receipt_id=f"r{next(_IDS)}", secret=secret)),
        )
        row, owed, (_, receipt_cents), _ = _row(db, cid)
        assert row["status"] == "settled"
        assert owed + row["used_cents"] == 100, out
        assert receipt_cents == row["used_cents"]
        if out["debit"].get("ok"):
            assert out["close"]["settlement"]["refund_owed_usd"] == 0.70
        else:
            assert out["debit"]["error"] == "channel not open"
            assert out["close"]["settlement"]["refund_owed_usd"] == 1.0


def test_two_closes_settle_once(two_ledgers):
    (a, b), db = two_ledgers
    for _ in range(25):
        cid, secret, wallet = _open(a, 1.0)
        results = []
        _run(
            lambda: results.append(a.close(cid, wallet=wallet, secret=secret)),
            lambda: results.append(b.close(cid, wallet=wallet, secret=secret)),
        )
        settled = [r for r in results if "settlement" in r]
        assert len(settled) == 1, results
        assert [r["error"] for r in results if "error" in r] == ["channel is settled"]
        _, owed, _, _ = _row(db, cid)
        assert owed == 100


def test_a_capture_racing_a_release_moves_the_hold_once(two_ledgers):
    (a, b), db = two_ledgers
    for _ in range(25):
        cid, secret, _ = _open(a, 1.0)
        rid = f"h{next(_IDS)}"
        assert a.hold(cid, 0.40, rid, secret=secret)["ok"]
        out = {}
        _run(
            lambda: out.update(capture=a.capture_hold(rid)),
            lambda: out.update(release=b.release_hold(rid)),
        )
        assert sum(1 for r in out.values() if r.get("ok")) == 1, out
        row, _, (_, receipt_cents), held = _row(db, cid)
        assert held == 0
        assert row["balance_cents"] + row["used_cents"] == 100
        assert receipt_cents == row["used_cents"]
        assert row["used_cents"] in (0, 40)


def test_a_hold_cannot_land_on_a_channel_closed_under_it(two_ledgers):
    (a, b), db = two_ledgers
    for _ in range(25):
        cid, secret, wallet = _open(a, 1.0)
        out = {}
        _run(
            lambda: out.update(close=a.close(cid, wallet=wallet, secret=secret)),
            lambda: out.update(hold=b.hold(cid, 0.25, f"h{next(_IDS)}", secret=secret)),
        )
        row, owed, _, held = _row(db, cid)
        if "settlement" in out["close"]:
            # settled first: the hold found it closed, nothing is reserved, all is owed
            assert "error" in out["hold"] and held == 0 and owed == 100
            assert row["status"] == "settled"
        else:
            # the hold landed first: the close refused and the channel stays open
            assert out["hold"]["ok"] and held == 25 and owed == 0
            assert row["status"] == "open"
            assert row["balance_cents"] == 75


def test_a_duplicate_receipt_from_two_ledgers_is_charged_once(two_ledgers):
    (a, b), db = two_ledgers
    for _ in range(25):
        cid, secret, _ = _open(a, 1.0)
        rid = f"dup{next(_IDS)}"
        out = []
        _run(
            lambda: out.append(a.debit(cid, 0.10, receipt_id=rid, secret=secret)),
            lambda: out.append(b.debit(cid, 0.10, receipt_id=rid, secret=secret)),
        )
        # both calls answer (the loser used to raise IntegrityError out of the debit)
        assert len(out) == 2, out
        assert sum(1 for r in out if r.get("ok")) == 1, out
        assert [r["error"] for r in out if "error" in r] == ["receipt already processed (replay rejected)"]
        row, _, (n, cents), _ = _row(db, cid)
        assert n == 1 and cents == row["used_cents"] == 10
