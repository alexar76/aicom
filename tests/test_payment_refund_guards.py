"""Refund eligibility and rollback against real SQLite/PostgreSQL ledgers."""
from __future__ import annotations

import os

import pytest

from tests.test_payment_chain_recovery import isolated, queued_withdrawal

pytestmark = pytest.mark.component_integration


@pytest.mark.parametrize("damage,error", [
    ("missing", "withdrawal_not_refundable"),
    ("queued", "withdrawal_not_refundable"),
    ("broadcast", "withdrawal_requires_chain_reconciliation"),
    ("zero-gross", "invalid_withdrawal_amount"),
    ("negative-fee", "invalid_withdrawal_amount"),
    ("oversized-fee", "invalid_withdrawal_amount"),
    ("ledger-unavailable", "refund_ledger_unavailable"),
])
def test_refund_guard_never_mints_or_changes_terminal_status(isolated, monkeypatch, damage, error):
    from core.uni.store import uni_connection
    from core.uni.wallet import UniWalletError

    svc, withdrawal = queued_withdrawal(monkeypatch)
    wid = withdrawal["withdrawal_id"]
    statement = "UPDATE uni_withdrawals SET status='refund_due' WHERE withdrawal_id=?"
    args = (wid,)
    if damage == "queued":
        statement = "UPDATE uni_withdrawals SET status='queued' WHERE withdrawal_id=?"
    elif damage == "broadcast":
        statement = "UPDATE uni_withdrawals SET status='refund_due', tx_hash=? WHERE withdrawal_id=?"
        args = ("0x" + "ab" * 32, wid)
    elif damage in ("zero-gross", "negative-fee", "oversized-fee"):
        statement = "UPDATE uni_withdrawals SET status='refund_due', amount_uni=?, fee_uni=? WHERE withdrawal_id=?"
        args = {"zero-gross": (0, 0, wid), "negative-fee": (10000, -1, wid),
                "oversized-fee": (10000, 10001, wid)}[damage]
    elif damage == "ledger-unavailable":
        monkeypatch.setattr(svc, "_claim_ledger_entry", lambda *a, **kw: False)
    with uni_connection() as conn:
        conn.execute(statement.replace("?", "%s") if os.environ["UNI_DB_BACKEND"] == "postgres" else statement, args)
    with pytest.raises(UniWalletError, match=error):
        svc.refund_withdrawal("missing-withdrawal" if damage == "missing" else wid)
    assert svc.get_wallet_by_owner("buyer")["balance_uni"] == 0
    with uni_connection() as conn:
        assert conn.execute("SELECT count(*) AS n FROM uni_ledger WHERE entry_type='refund'").fetchone()["n"] == 0
