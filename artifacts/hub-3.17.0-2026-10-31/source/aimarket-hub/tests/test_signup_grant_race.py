"""The signup-grant budget holds when signups arrive at once (outside review, 2026-10-22).

The daily budget is the one control a proxy pool cannot get around — but only if it is
enforced. Checked and minted as two steps, concurrent signups on more than one worker
process all read the same remaining budget and all minted. Here thirty threads, then four
processes sharing one database file, sign up against a budget with room for five grants.
"""
from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
import textwrap
import threading
import time
from pathlib import Path

import pytest

from aimarket_hub import credits
from aimarket_hub.database import HubDatabase

HUB_ROOT = Path(__file__).resolve().parents[1]


def _granted(db_path: Path) -> tuple[int, int]:
    conn = sqlite3.connect(str(db_path))
    try:
        total = conn.execute("SELECT COALESCE(SUM(amount_mc), 0) FROM credit_ledger WHERE kind = 'grant' AND note = ?",
                             (credits.SIGNUP_GRANT_NOTE,)).fetchone()[0]
        accounts = conn.execute("SELECT COUNT(*) FROM credit_accounts").fetchone()[0]
    finally:
        conn.close()
    return int(total), int(accounts)


@pytest.fixture
def budget(monkeypatch):
    monkeypatch.setenv("AIMARKET_SIGNUP_GRANT_USD", "0.05")
    monkeypatch.setenv("AIMARKET_SIGNUP_GRANT_DAILY_USD", "0.25")
    monkeypatch.delenv("AIMARKET_SIGNUP_GRANT_TOTAL_USD", raising=False)


def test_thirty_concurrent_signups_mint_exactly_the_budget(tmp_path, budget):
    db = HubDatabase(tmp_path / "hub.db")
    ledger = credits.CreditsLedger(db._conn)
    barrier = threading.Barrier(30)
    answers: list[dict] = []
    lock = threading.Lock()

    def signup(i: int) -> None:
        barrier.wait()
        a = ledger.open_signup_account(label=f"s{i}")
        with lock:
            answers.append(a)

    threads = [threading.Thread(target=signup, args=(i,)) for i in range(30)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    db._conn.close()
    granted, accounts = _granted(tmp_path / "hub.db")
    assert accounts == 30                       # everyone gets an account ...
    assert granted == credits.usd_to_mc(0.25)   # ... and the grants stop at the budget
    assert sum(1 for a in answers if a["balance_usd"] > 0) == 5
    assert all("daily" in a["grant_note"] for a in answers if a["balance_usd"] == 0)


_WORKER = textwrap.dedent("""
    import sys, time
    sys.path.insert(0, {root!r})
    from aimarket_hub import credits
    from aimarket_hub.database import HubDatabase
    ledger = credits.CreditsLedger(HubDatabase({db!r})._conn)
    while time.time() < {start}:
        time.sleep(0.001)
    for i in range(8):
        ledger.open_signup_account(label="p")
""")


def test_signups_from_several_worker_processes_stay_inside_the_budget(tmp_path, budget):
    db_path = tmp_path / "hub.db"
    HubDatabase(db_path)._conn.close()
    start = time.time() + 2.0
    script = _WORKER.format(root=str(HUB_ROOT), db=str(db_path), start=start)
    procs = [subprocess.Popen([sys.executable, "-c", script], env={**os.environ, "AIMARKET_CREDITS_ENABLED": "1"},
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(4)]
    for p in procs:
        _, err = p.communicate(timeout=120)
        assert p.returncode == 0, err[-2000:]
    granted, accounts = _granted(db_path)
    assert accounts == 32
    assert granted == credits.usd_to_mc(0.25)
