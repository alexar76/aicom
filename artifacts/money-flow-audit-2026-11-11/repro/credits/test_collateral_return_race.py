"""Scratch repro: two concurrent operator collateral returns both pass the route's
read-then-check guard; CreditsLedger.return_collateral floors collateral at 0 but credits the
full amount each time, so balance grows by 2x the posted stake."""
from __future__ import annotations

import sys
import threading

sys.path.insert(0, "/Users/alex/Desktop/ai_tests/aicompany/aicom/.claude/worktrees/bold-volhard-8c154f/aimarket-hub")

from aimarket_hub import credits  # noqa: E402
from aimarket_hub.database import HubDatabase  # noqa: E402


def test_double_return(tmp_path):
    db = HubDatabase(str(tmp_path / "hub.db"))
    ledger = credits.CreditsLedger(db._conn)
    acct = ledger.create_account(label="pub", grant_usd=25.0, grant_note=credits.OPERATOR_GRANT_NOTE)
    aid = acct["account_id"]
    assert ledger.debit(aid, 25.0, note="supply stake", as_collateral=True)["debited_usd"] == 25.0
    assert ledger.account(aid)["balance_usd"] == 0.0 and ledger.account(aid)["collateral_usd"] == 25.0

    # What accounts.py:691-702 does per request: read collateral, compare, then return.
    barrier = threading.Barrier(2)
    results = []

    def route():
        posted = float(ledger.account(aid)["collateral_usd"])
        barrier.wait()  # both requests have passed the `amount > posted` check
        if 25.0 > posted + 1e-9:
            results.append("refused")
            return
        results.append(ledger.return_collateral(aid, 25.0, note="operator return"))

    threads = [threading.Thread(target=route) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    acc = ledger.account(aid)
    print(results, acc)
    assert acc["collateral_usd"] == 0.0
    assert acc["balance_usd"] == 50.0  # 25 posted, 50 returned
