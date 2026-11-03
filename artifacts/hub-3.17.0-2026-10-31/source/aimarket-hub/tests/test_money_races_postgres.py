"""The money races of tests/test_ledger_crash_consistency.py, test_subcontract_races.py and
test_signup_grant_race.py on PostgreSQL, where every thread has its own session and the
guarantees come from row locks instead of the shared SQLite connection's lock.

Runs when AIMARKET_TEST_DATABASE_URL names a database it may wipe (like the rest of the
PostgreSQL runs of this suite).
"""
from __future__ import annotations

import threading
from typing import Any, Callable

import pytest

from aimarket_hub import credits, subcontract
from aimarket_hub.database import HubDatabase
from aimarket_hub.signing import Signer
from aimarket_hub.subcontract import SubcontractError
from tests._mandate_kit import PG_URL, _reset_postgres

pytestmark = pytest.mark.skipif(not PG_URL, reason="needs AIMARKET_TEST_DATABASE_URL")

HUB = "https://hub.test"


@pytest.fixture
def db(tmp_path):
    _reset_postgres(PG_URL)
    database = HubDatabase(tmp_path / "unused.db", database_url=PG_URL)
    yield database
    database._conn.close()


def _race(n: int, work: Callable[[int], Any]) -> list[Any]:
    barrier = threading.Barrier(n)
    out: list[Any] = [None] * n

    def run(i: int) -> None:
        barrier.wait()
        try:
            out[i] = work(i)
        except Exception as exc:  # noqa: BLE001 - the outcome is the data
            out[i] = exc

    threads = [threading.Thread(target=run, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    return out


def _ledger_ok(conn: Any) -> None:
    for a in conn.execute("SELECT * FROM credit_accounts").fetchall():
        held = conn.execute("SELECT COALESCE(SUM(amount_mc), 0) AS s FROM credit_holds WHERE account_id = ? "
                            "AND status = 'held'", (a["account_id"],)).fetchone()["s"]
        assert int(a["held_mc"]) == int(held)
        assert int(a["granted_mc"]) == int(a["balance_mc"]) + int(a["held_mc"]) + int(a["spent_mc"]) + int(a["collateral_mc"])
    conn.commit()


def test_one_hold_resolved_by_many_at_once_moves_its_money_once(db):
    ledger = credits.CreditsLedger(db._conn)
    account = ledger.create_account("buyer", grant_usd=1.0)["account_id"]
    assert not ledger.hold(account, 0.10, "rcpt_contested").get("error")
    out = _race(12, lambda i: (ledger.capture_hold if i % 2 else ledger.release_hold)("rcpt_contested"))
    winners = [r for r in out if isinstance(r, dict) and not r.get("error") and not r.get("already")]
    assert len(winners) == 1, out
    _ledger_ok(db._conn)


def test_an_allowance_closed_while_children_draw_on_it_loses_nothing(db):
    ledger = credits.CreditsLedger(db._conn)
    account = ledger.create_account("buyer", grant_usd=1.0)["account_id"]
    assert not ledger.hold(account, 0.10, "alw_pg").get("error")
    out = _race(21, lambda i: ledger.release_hold("alw_pg") if i == 20 else ledger.transfer_hold("alw_pg", f"kid_{i}", 0.004))
    carved = [f"kid_{i}" for i, r in enumerate(out[:20]) if isinstance(r, dict) and not r.get("error")]
    for i, kid in enumerate(carved):
        (ledger.capture_hold if i % 2 else ledger.release_hold)(kid)
    _ledger_ok(db._conn)


def test_joins_racing_a_finish_never_graft_onto_a_finished_call(db, tmp_path):
    store = subcontract.JobStore(db._conn, Signer(tmp_path / "key"), HUB)
    root = store.open_root(product_id="p", capability_id="a.work@v1", max_depth=3)
    token = store.issue_token(root)
    store._ensure_node(root.job_id, root.node, parent="", depth=0, product_id="p",
                       capability_id="a.work@v1", funded_by="own")

    def work(i: int) -> Any:
        if i == 16:
            return store.finish_node(root.node, status="captured")
        return store.join(token=token, grant_secret="", product_id="q", capability_id=f"c{i}.work@v1")

    out = _race(17, work)
    joined = sum(1 for r in out[:16] if isinstance(r, subcontract.JobContext))
    assert all(isinstance(r, subcontract.JobContext) or (isinstance(r, SubcontractError) and "finished" in r.detail)
               for r in out[:16]), out
    rows = db._conn.execute("SELECT COUNT(*) AS n FROM job_nodes WHERE parent_receipt = ?", (root.node,)).fetchone()["n"]
    db._conn.commit()
    assert int(rows) == joined


def test_concurrent_signups_mint_exactly_the_budget(db, monkeypatch):
    monkeypatch.setenv("AIMARKET_SIGNUP_GRANT_USD", "0.05")
    monkeypatch.setenv("AIMARKET_SIGNUP_GRANT_DAILY_USD", "0.25")
    ledger = credits.CreditsLedger(db._conn)
    out = _race(20, lambda i: ledger.open_signup_account(label=f"s{i}"))
    assert all(isinstance(a, dict) for a in out), out
    assert sum(1 for a in out if a["balance_usd"] > 0) == 5
    assert ledger.granted_mc(since_hours=24) == credits.usd_to_mc(0.25)
    db._conn.commit()
