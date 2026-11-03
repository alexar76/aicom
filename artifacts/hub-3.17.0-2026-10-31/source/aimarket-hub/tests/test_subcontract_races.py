"""SUB/1 under races and crashes — the scenarios an outside review (2026-10-22) asked for.

* A child that joins while its parent call is finishing: the check "is the parent still
  running?" and the insert of the child were two transactions, so a parent that finished in
  between got a child grafted onto a tree whose receipt was already out.
* An allowance closed and released while its children are being carved out of it.
* A child hold left 'held' by a process that died mid-call: the invoke sweep skips children
  (they belong to an allowance) and the allowance sweep released only the allowance, so the
  child's money stayed frozen in the buyer's account forever.
"""
from __future__ import annotations

import sqlite3
import threading
import time
from typing import Any

import pytest

from aimarket_hub import credits, invoke_funding, subcontract
from aimarket_hub.database import HubDatabase
from aimarket_hub.signing import Signer
from aimarket_hub.subcontract import SubcontractError

HUB = "https://hub.test"


class _Rows:
    def __init__(self, rows: list[Any]):
        self._rows = list(rows)

    def fetchone(self) -> Any:
        return self._rows.pop(0) if self._rows else None

    def fetchall(self) -> list[Any]:
        rows, self._rows = self._rows, []
        return rows


class _FinishesTheParentMidJoin:
    """The shared backend, except that the moment join() has read the parent's status, the
    parent call finishes — what a concurrent request would do in that gap."""

    def __init__(self, inner: Any, finish: Any):
        self._inner = inner
        self._finish = finish
        self.fired = False

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    def execute(self, sql: str, params: tuple = ()) -> Any:
        cursor = self._inner.execute(sql, params)
        if not self.fired and sql.lstrip().startswith("SELECT status FROM job_nodes"):
            self.fired = True
            rows = cursor.fetchall()
            self._finish()
            return _Rows(rows)
        return cursor


def _store(tmp_path) -> tuple[HubDatabase, subcontract.JobStore]:
    db = HubDatabase(tmp_path / "hub.db")
    return db, subcontract.JobStore(db._conn, Signer(tmp_path / "key"), HUB)


def test_a_child_cannot_join_a_call_that_finishes_while_it_is_checked(tmp_path):
    db, real = _store(tmp_path)
    root = real.open_root(product_id="p", capability_id="a.work@v1", max_depth=3)
    token = real.issue_token(root)
    racing = _FinishesTheParentMidJoin(
        db._conn, lambda: real.finish_root(root, product_id="p", capability_id="a.work@v1", status="captured"))
    store = subcontract.JobStore(racing, real._signer, HUB)
    with pytest.raises(SubcontractError) as refused:
        store.join(token=token, grant_secret="", product_id="q", capability_id="b.work@v1")
    assert racing.fired
    assert "finished" in refused.value.detail
    children = db._conn.execute(
        "SELECT COUNT(*) AS n FROM job_nodes WHERE parent_receipt = ?", (root.node,)).fetchone()["n"]
    assert children == 0
    # The slots the refused child took are given back.
    counters = {r["counter"]: r["n"] for r in db._conn.execute("SELECT counter, n FROM job_counters").fetchall()}
    assert counters.get(f"children:{root.node}", 0) == 0
    assert counters.get(f"nodes:{root.job_id}", 0) == 0


def test_joins_racing_a_finish_either_land_before_it_or_are_refused(tmp_path):
    """Sixteen joins and one finish at once: no child may exist that was written after the
    parent stopped running. Every child row that exists was admitted while it ran."""
    db, store = _store(tmp_path)
    root = store.open_root(product_id="p", capability_id="a.work@v1", max_depth=3)
    token = store.issue_token(root)
    # The parent row exists from the first join on; create it so the finish has a row to close.
    store._ensure_node(root.job_id, root.node, parent="", depth=0, product_id="p",
                       capability_id="a.work@v1", funded_by="own")
    barrier = threading.Barrier(17)
    outcomes: list[str] = []
    lock = threading.Lock()

    def join(i: int) -> None:
        barrier.wait()
        try:
            store.join(token=token, grant_secret="", product_id="q", capability_id=f"c{i}.work@v1")
            r = "joined"
        except SubcontractError as exc:
            r = exc.detail
        with lock:
            outcomes.append(r)

    def finish() -> None:
        barrier.wait()
        store.finish_node(root.node, status="captured")

    threads = [threading.Thread(target=join, args=(i,)) for i in range(16)] + [threading.Thread(target=finish)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    joined = outcomes.count("joined")
    rows = db._conn.execute("SELECT COUNT(*) AS n FROM job_nodes WHERE parent_receipt = ?", (root.node,)).fetchone()["n"]
    assert rows == joined
    assert all(o == "joined" or "finished" in o for o in outcomes)
    n = {r["counter"]: r["n"] for r in db._conn.execute("SELECT counter, n FROM job_counters").fetchall()}
    assert n.get(f"children:{root.node}", 0) == joined


def _ledger_ok(db_path) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        for a in conn.execute("SELECT * FROM credit_accounts").fetchall():
            held = conn.execute("SELECT COALESCE(SUM(amount_mc), 0) FROM credit_holds WHERE account_id = ? "
                                "AND status = 'held'", (a["account_id"],)).fetchone()[0]
            assert a["held_mc"] == held
            assert a["granted_mc"] == a["balance_mc"] + a["held_mc"] + a["spent_mc"] + a["collateral_mc"]
    finally:
        conn.close()


def test_closing_an_allowance_while_children_draw_on_it_loses_nothing(tmp_path):
    db = HubDatabase(tmp_path / "hub.db")
    ledger = credits.CreditsLedger(db._conn)
    account = ledger.create_account("buyer", grant_usd=1.0)["account_id"]
    assert not ledger.hold(account, 0.10, "alw_close").get("error")
    barrier = threading.Barrier(21)
    carved: list[str] = []
    lock = threading.Lock()

    def child(i: int) -> None:
        barrier.wait()
        if not ledger.transfer_hold("alw_close", f"kid_{i}", 0.004).get("error"):
            with lock:
                carved.append(f"kid_{i}")

    def close() -> None:
        barrier.wait()
        ledger.release_hold("alw_close")

    threads = [threading.Thread(target=child, args=(i,)) for i in range(20)] + [threading.Thread(target=close)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    # Children carved before the close keep their money; the close returned the rest. Then the
    # children resolve (half delivered, half failed) and everything adds up.
    for i, kid in enumerate(carved):
        (ledger.capture_hold if i % 2 else ledger.release_hold)(kid)
    db._conn.close()
    _ledger_ok(tmp_path / "hub.db")
    conn = sqlite3.connect(str(tmp_path / "hub.db"))
    try:
        spent = conn.execute("SELECT spent_mc FROM credit_accounts WHERE account_id = ?", (account,)).fetchone()[0]
    finally:
        conn.close()
    assert spent == credits.usd_to_mc(0.004) * (len(carved) // 2)


class _Counters:
    """The mandate store as the sweeps use it, recording what they settle and give back."""

    def __init__(self) -> None:
        self.settled: list[tuple[str, int]] = []
        self.given_back: list[tuple[str, int]] = []

    def settle(self, receipt_id: str, keep_micro: int) -> None:
        self.settled.append((receipt_id, keep_micro))

    def give_back(self, receipt_id: str, amount_micro: int) -> None:
        self.given_back.append((receipt_id, amount_micro))


def test_a_child_hold_orphaned_by_a_crash_is_released_and_its_mandate_budget_given_back(tmp_path):
    db = HubDatabase(tmp_path / "hub.db")
    ledger = credits.CreditsLedger(db._conn)
    store = _Counters()
    jobs = subcontract.JobStore(db._conn, Signer(tmp_path / "key"), HUB)
    account = ledger.create_account("buyer", grant_usd=1.0)["account_id"]
    assert not ledger.hold(account, 0.10, "alw_crash").get("error")
    jobs.open_root(product_id="p", capability_id="a.work@v1", allowance_micro=100_000,
                   allowance_receipt="alw_crash", account_id=account, mandate_digest="sha256-root-mandate")
    # Two children were running when the process died: one under the open allowance, and one
    # whose allowance the root then settled normally (a child request on a worker that died).
    assert not ledger.transfer_hold("alw_crash", "orphan_open", 0.02).get("error")
    assert not ledger.transfer_hold("alw_crash", "orphan_late", 0.01).get("error")
    fresh_before = ledger.balance(account)
    now = time.time()
    # Before an hour has passed nothing is touched: a child may still be running.
    assert invoke_funding.sweep_orphaned_child_holds(credits_ledger=ledger, store=store, now=now) == 0
    db._conn.execute("UPDATE credit_holds SET created_at = '2000-01-01 00:00:00' WHERE receipt_id LIKE 'orphan_%'")
    db._conn.execute("UPDATE job_grants SET expires_at = ?", (now - 7200,))
    db._conn.commit()
    # The allowance sweep settles the allowance first (what it always did) ...
    assert invoke_funding.sweep_stale_allowances(credits_ledger=ledger, store=store, jobs=jobs, now=now) == 1
    assert ledger.hold_status("orphan_open")["status"] == "held"
    # ... and the children it left behind come back to the buyer's balance.
    assert invoke_funding.sweep_orphaned_child_holds(credits_ledger=ledger, store=store, now=now) == 2
    assert invoke_funding.sweep_orphaned_child_holds(credits_ledger=ledger, store=store, now=now) == 0
    assert ledger.hold_status("orphan_open")["status"] == "released"
    assert ledger.hold_status("orphan_late")["status"] == "released"
    assert ledger.balance(account) == pytest.approx(1.0)
    assert ledger.balance(account) == pytest.approx(fresh_before + 0.10)
    # The allowance settled as $0.03 spent; both children failed, so the mandate gets it all back.
    assert store.settled == [("alw_crash", 30_000)]
    assert sorted(store.given_back) == [("alw_crash", 10_000), ("alw_crash", 20_000)]
    db._conn.close()
    _ledger_ok(tmp_path / "hub.db")


def test_the_grant_secret_is_never_written_to_the_database_or_a_refusal(tmp_path):
    db, jobs = _store(tmp_path)
    ledger = credits.CreditsLedger(db._conn)
    account = ledger.create_account("buyer", grant_usd=1.0)["account_id"]
    assert not ledger.hold(account, 0.05, "alw_secret").get("error")
    root = jobs.open_root(product_id="p", capability_id="a.work@v1", allowance_micro=50_000,
                          allowance_receipt="alw_secret", account_id=account, max_depth=2)
    secret = root.grant_secret
    assert len(secret) >= 40
    token = jobs.issue_token(root)
    assert secret not in token
    child = jobs.join(token=token, grant_secret=secret, product_id="q", capability_id="b.work@v1")
    assert child.funded_by == "allowance"
    jobs.close_grant(root.job_id)
    with pytest.raises(SubcontractError) as closed:
        jobs.join(token=token, grant_secret=secret, product_id="r", capability_id="c.work@v1")
    with pytest.raises(SubcontractError) as wrong:
        jobs.join(token=token, grant_secret=secret[:-1] + ("A" if secret[-1] != "A" else "B"),
                  product_id="r", capability_id="c.work@v1")
    for refusal in (closed.value, wrong.value):
        assert secret not in str(refusal.body())
    db._conn.commit()
    dump = "\n".join(db._conn._conn.iterdump()) if hasattr(db._conn, "_conn") else ""
    assert dump and secret not in dump
    tree = jobs.tree(root.job_id)
    assert secret not in str(tree)
