"""Check payout ledger invariants without importing the application or opening a writable database."""

import json
import os
from pathlib import Path
import sqlite3


path = Path(os.environ.get("AIMARKET_DB_PATH") or "data/hub.db").resolve(strict=True)
db = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
withdrawal = "pwd_86535455c02e4e8c9b82ed2cd8553f60"
tx = "0x4f2fea9a34d1e50291d36f76540f39cb71270898ca6273818b896f8eced6eb8d"
row = db.execute("SELECT status, amount_mc, tx_hash, length(raw_tx) FROM publisher_withdrawals "
                 "WHERE withdrawal_id = ?", (withdrawal,)).fetchone()
postings = db.execute("SELECT kind, count(*), sum(amount_mc) FROM credit_ledger WHERE receipt_id = ? "
                      "GROUP BY kind ORDER BY kind", (withdrawal,)).fetchall()
pending = db.execute("SELECT count(*) FROM publisher_withdrawals WHERE status IN ('requested','signed','broadcast')"
                     ).fetchone()[0]
configured = bool(os.getenv("AIMARKET_OBSERVED_EXPLICIT_GET_ORIGINS", "").strip())
signer_in_hub = bool(os.getenv("AIMARKET_PUBLISHER_PAYOUT_KEY_FILE", "").strip())
assert row == ("paid", 1, tx, 0) and pending == 0
assert postings == [("publisher_withdraw_paid", 1, 1), ("publisher_withdraw_requested", 1, 1)]
assert not configured and not signer_in_hub
print(json.dumps({"withdrawal_id": withdrawal, "payout": row, "postings": postings,
                  "pending_withdrawals": pending, "explicit_get_origins_configured": configured,
                  "signer_key_file_in_hub": signer_in_hub}, indent=2))
