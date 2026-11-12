"""Selected-row read-only SQL regression, using a disposable synthetic SQLite DB."""
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

HELPER = Path(__file__).resolve().parents[1] / "read_paid_ledger.py"


def test_scoped_sqlite_ledger_preserves_bytes_and_accepts_legacy_receipt_link(tmp_path):
    db = tmp_path / "synthetic.db"
    expected = {"operation_id": "op_" + "01" * 16, "invoice_nonce": "0x" + "02" * 32,
                "tx_hash": "0x" + "03" * 32, "payer": "0x" + "04" * 20,
                "payee": "0x" + "05" * 20, "asset": "0x" + "06" * 20,
                "amount_atomic": 2000, "price_usd": "0.002", "product_id": "synthetic",
                "capability_id": "synthetic.read@v1", "input_digest": "07" * 32,
                "receipt_nonce": "synthetic_receipt"}
    connection = sqlite3.connect(db)
    connection.executescript("""
      CREATE TABLE settle_invoices(nonce TEXT PRIMARY KEY, capability_id TEXT, pay_to TEXT,
        amount_units TEXT, consumed_at REAL, tx_hash TEXT);
      CREATE TABLE x402_payments(nonce TEXT PRIMARY KEY,payer TEXT,amount_atomic TEXT,
        amount_usd REAL,asset TEXT,capability_id TEXT,status TEXT,settle_tx_hash TEXT,
        pay_to TEXT,receipt_id TEXT);
      CREATE TABLE seller_operations(operation_id TEXT PRIMARY KEY,busy INTEGER,
        state_json TEXT,response_json TEXT);
    """)
    connection.execute("INSERT INTO settle_invoices VALUES(?,?,?,?,?,?)", (
        expected["invoice_nonce"], expected["capability_id"], expected["payee"], "2000", 1, expected["tx_hash"]))
    connection.execute("INSERT INTO x402_payments VALUES(?,?,?,?,?,?,?,?,?,?)", (
        expected["invoice_nonce"], expected["payer"], "2000", .002, expected["asset"],
        expected["capability_id"], "settled", expected["tx_hash"], expected["payee"], ""))
    state = {"status": "completed", "input_digest": expected["input_digest"],
             "request": {"wallet": expected["payer"], "tx_hash": expected["tx_hash"]},
             "offer": {"invoice": {"nonce": expected["invoice_nonce"]},
                       "product_id": expected["product_id"], "capability_id": expected["capability_id"],
                       "terms": {"amount_units": 2000, "pay_to": expected["payee"]}}}
    response = {"status": "completed", "input_digest": expected["input_digest"],
                "receipt": {"nonce": expected["receipt_nonce"], "price_usd": .002}}
    connection.execute("INSERT INTO seller_operations VALUES(?,?,?,?)", (
        expected["operation_id"], 0, json.dumps(state), json.dumps(response)))
    # A different customer-like row is outside the helper's exact scope.
    connection.execute("INSERT INTO seller_operations VALUES(?,?,?,?)", (
        "op_" + "99" * 16, 0, "{}", "{}"))
    connection.commit()
    connection.close()
    before = db.read_bytes()
    env = {k: v for k, v in os.environ.items() if k in ("PATH", "SYSTEMROOT", "LANG")}
    env.update(AIMARKET_DB_PATH=str(db), HOME=str(tmp_path), TMPDIR=str(tmp_path))
    process = subprocess.run([sys.executable, str(HELPER)], input=json.dumps(expected),
                             capture_output=True, text=True, env=env, cwd=tmp_path)
    result = json.loads(process.stdout)
    assert process.returncode == 0 and result["ok"] is True
    assert result["legacy_empty_x402_receipt_link_qualified"] is True
    assert result["operation_receipt_link_required"] is True
    assert db.read_bytes() == before
    expected["input_digest"] = "bad_digest"
    process = subprocess.run([sys.executable, str(HELPER)], input=json.dumps(expected),
                             capture_output=True, text=True, env=env, cwd=tmp_path)
    assert process.returncode == 1 and json.loads(process.stdout)["ok"] is False
    assert db.read_bytes() == before
