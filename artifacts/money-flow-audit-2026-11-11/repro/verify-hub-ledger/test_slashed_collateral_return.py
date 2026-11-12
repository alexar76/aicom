"""Scratch repro: a slash burns stake only in supply_stakes; credit_accounts.collateral_mc keeps
the full amount, and the operator's collateral-return route caps the return by collateral_mc,
so it hands the slashed money back to spendable balance."""
from __future__ import annotations

import sys

sys.path.insert(0, "/Users/alex/Desktop/ai_tests/aicompany/aicom/.claude/worktrees/bold-volhard-8c154f/aimarket-hub")

from aimarket_hub import credits  # noqa: E402
from tests._mandate_kit import ADMIN_TOKEN, funded_account, hub  # noqa: E402


def test_slashed_stake_is_still_returnable(monkeypatch, tmp_path):
    with hub(monkeypatch, tmp_path) as (client, db):
        account, _key = funded_account(client, db, 25.0)
        ledger = credits.CreditsLedger(db._conn)
        # What POST /supply/stake does on the credits rail: debit as collateral, then record the stake.
        assert ledger.debit(account, 25.0, note="supply stake", as_collateral=True)["debited_usd"] == 25.0
        db.supply_stake_add(account, 25.0, f"credits:{account}:x")
        slashed, remaining = db.supply_stake_slash(account, 25.0)
        assert (slashed, remaining) == (25.0, 0.0)
        acc = ledger.account(account)
        print("after slash: stake remaining", remaining, "credit collateral", acc["collateral_usd"],
              "outstanding", ledger.stats()["outstanding_credit_usd"])
        r = client.post(f"/ai-market/v2/accounts/{account}/collateral/return",
                        headers={"Authorization": f"Bearer {ADMIN_TOKEN}"}, json={"amount_usd": 25.0})
        print(r.status_code, r.json())
        assert r.status_code == 200 and ledger.account(account)["balance_usd"] == 25.0
