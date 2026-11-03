"""The credits ledger moves money in one transaction, or not at all.

An outside review (2026-10-22) asked what happens when the hub dies "after a child hold is
created and right before the final capture". Two things could split a money move in two:

* **A crash between two commits.** Resolving a hold committed its new status first and
  moved the money in a second transaction; carving a child out of an allowance committed
  the allowance's decrement before the child row existed. A process killed in between left a
  hold marked released whose money never came back, or an allowance shrunk for a child that
  was never written — money gone from the buyer's balance for good, with nothing left that
  any sweep would release.
* **Another thread's failed statement.** Every request thread shares one SQLite connection,
  and a failing statement rolls back whatever is pending on it. Between the money statement
  and its commit, any other request's error could undo the money move while the bookkeeping
  around it committed.

These tests kill a real process at the last statement before the commit, and run a failing
statement on the shared connection at the same point, then check the ledger's two
invariants: an account's ``held_mc`` is exactly the sum of its held holds, and no
millicent was created or destroyed.
"""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import textwrap
import threading
from pathlib import Path

import pytest

from aimarket_hub import credits
from aimarket_hub.database import HubDatabase

HUB_ROOT = Path(__file__).resolve().parents[1]


def _invariants(db_path: Path) -> list[str]:
    """Every way the ledger can be wrong, as text (empty when it is right)."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    problems: list[str] = []
    try:
        for a in conn.execute("SELECT * FROM credit_accounts").fetchall():
            held = conn.execute(
                "SELECT COALESCE(SUM(amount_mc), 0) FROM credit_holds WHERE account_id = ? AND status = 'held'",
                (a["account_id"],),
            ).fetchone()[0]
            if int(a["held_mc"]) != int(held):
                problems.append(f"{a['account_id']}: held_mc {a['held_mc']} but held holds sum to {held}")
            money_in = int(a["granted_mc"]) + int(a["topped_up_mc"] or 0)
            accounted = int(a["balance_mc"]) + int(a["held_mc"]) + int(a["spent_mc"]) + int(a["collateral_mc"])
            if money_in != accounted:
                problems.append(f"{a['account_id']}: {money_in} mc came in, {accounted} mc accounted for")
    finally:
        conn.close()
    return problems


def _snapshot(db_path: Path) -> dict:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        return {
            "accounts": [dict(r) for r in conn.execute(
                "SELECT account_id, balance_mc, held_mc, spent_mc FROM credit_accounts ORDER BY account_id")],
            "holds": [dict(r) for r in conn.execute(
                "SELECT receipt_id, amount_mc, status FROM credit_holds ORDER BY receipt_id")],
        }
    finally:
        conn.close()


def _setup(tmp_path: Path) -> tuple[Path, str]:
    """An account with $1, a $0.10 allowance and a $0.02 child carved out of it."""
    db_path = tmp_path / "hub.db"
    db = HubDatabase(db_path)
    ledger = credits.CreditsLedger(db._conn)
    account = ledger.create_account("crash", grant_usd=1.0)["account_id"]
    assert not ledger.hold(account, 0.10, "alw_root").get("error")
    assert not ledger.transfer_hold("alw_root", "child_a", 0.02).get("error")
    db._conn.close()
    assert _invariants(db_path) == []
    return db_path, account


# The operation runs in a separate interpreter that dies (os._exit, no cleanup, no rollback
# by Python) at the ledger line, which every money move writes last before its commit.
_CRASH = textwrap.dedent("""
    import os, sys
    sys.path.insert(0, {root!r})
    from aimarket_hub import credits
    from aimarket_hub.database import HubDatabase
    db = HubDatabase({db!r})
    ledger = credits.CreditsLedger(db._conn)
    def die(*a, **k):
        os._exit(9)
    ledger._log = die
    {op}
    os._exit(0)
""")

OPERATIONS = {
    "carve a child out of the allowance": "ledger.transfer_hold('alw_root', 'child_b', 0.03)",
    "capture a child": "ledger.capture_hold('child_a')",
    "release a child back into the allowance": "ledger.release_hold('child_a')",
    "release the allowance": "ledger.release_hold('alw_root')",
    "reserve for a new call": "ledger.hold({account!r}, 0.05, 'rcpt_new')",
    "charge a routing fee": "ledger.debit({account!r}, 0.01, 'fee_1')",
}


@pytest.mark.parametrize("name", list(OPERATIONS))
def test_a_process_killed_before_the_commit_moves_no_money(tmp_path, name):
    db_path, account = _setup(tmp_path)
    before = _snapshot(db_path)
    op = OPERATIONS[name].format(account=account)
    script = _CRASH.format(root=str(HUB_ROOT), db=str(db_path), op=op)
    proc = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=120,
                          env={**os.environ, "AIMARKET_CREDITS_ENABLED": "1"})
    assert proc.returncode == 9, proc.stderr[-2000:]
    assert _invariants(db_path) == []
    # All or nothing: the killed operation left no trace, so the hold it was resolving is
    # still held and a sweep (or a retry) can finish the job.
    assert _snapshot(db_path) == before


@pytest.mark.parametrize("name", ["release a child back into the allowance", "capture a child",
                                  "carve a child out of the allowance", "release the allowance"])
def test_another_threads_failed_statement_cannot_undo_half_a_money_move(tmp_path, name):
    db_path, account = _setup(tmp_path)
    db = HubDatabase(db_path)
    ledger = credits.CreditsLedger(db._conn)
    original_log = ledger._log
    errors: list[BaseException] = []

    def foreign_failure() -> None:
        # Another request's statement fails on the shared connection; the backend rolls back
        # whatever is pending on it.
        try:
            db._conn.execute("INSERT INTO no_such_table VALUES (1)")
        except Exception as exc:  # noqa: BLE001 - the failure is the point
            errors.append(exc)

    def interleaved(*args, **kwargs):
        t = threading.Thread(target=foreign_failure)
        t.start()
        # Wait for it unless it is held back (it should be: the money move owns the connection).
        t.join(timeout=0.3)
        interleaved.threads.append(t)
        return original_log(*args, **kwargs)

    interleaved.threads = []
    ledger._log = interleaved
    eval(OPERATIONS[name].format(account=account), {"ledger": ledger})
    for t in interleaved.threads:
        t.join(timeout=10)
    assert errors, "the foreign statement should have failed"
    db._conn.close()
    assert _invariants(db_path) == []


def test_concurrent_children_never_spend_more_than_the_allowance(tmp_path):
    """Thirty children race for a $0.10 allowance at $0.007 each: at most fourteen get in."""
    db_path = tmp_path / "hub.db"
    db = HubDatabase(db_path)
    ledger = credits.CreditsLedger(db._conn)
    account = ledger.create_account("race", grant_usd=1.0)["account_id"]
    assert not ledger.hold(account, 0.10, "alw_race").get("error")
    results: list[dict] = []
    lock = threading.Lock()
    barrier = threading.Barrier(30)

    def child(i: int) -> None:
        barrier.wait()
        r = ledger.transfer_hold("alw_race", f"child_{i}", 0.007)
        if not r.get("error") and i % 3 == 0:
            ledger.release_hold(f"child_{i}")        # a failed child: its money goes back
        with lock:
            results.append(r)

    threads = [threading.Thread(target=child, args=(i,)) for i in range(30)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    won = [r for r in results if not r.get("error")]
    assert 14 <= len(won) <= 30
    held = db._conn.execute(
        "SELECT COALESCE(SUM(amount_mc), 0) AS s FROM credit_holds WHERE status = 'held'",
    ).fetchone()["s"]
    assert held == credits.usd_to_mc(0.10)          # allowance + live children = what was set aside
    db._conn.close()
    assert _invariants(db_path) == []
    json.dumps(results)  # every answer is plain data
