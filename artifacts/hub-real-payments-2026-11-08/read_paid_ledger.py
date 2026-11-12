#!/usr/bin/env python3
"""Read only the one caller-selected paid operation/invoice/payment.

Input is a JSON object on stdin, containing public exact matching keys.
Use the normal runtime's DATABASE_URL or AIMARKET_DB_PATH; never display it.
No Hub imports, migrations, credential discovery, table inventories or writes.
"""
from decimal import Decimal
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
from urllib.parse import quote


def main():
    expected = json.load(sys.stdin)
    required = ("operation_id", "invoice_nonce", "tx_hash", "payer", "payee", "asset",
                "amount_atomic", "price_usd", "product_id", "capability_id", "input_digest",
                "receipt_nonce")
    if set(expected) != set(required):
        raise ValueError("Expected exact public selector fields")
    for name in ("invoice_nonce", "tx_hash"):
        if not re.fullmatch(r"0x[0-9a-fA-F]{64}", expected[name]):
            raise ValueError("Invalid payment selector")
    if not re.fullmatch(r"op_[0-9a-f]{32}", expected["operation_id"]):
        raise ValueError("Invalid operation selector")
    for name in ("payer", "payee", "asset"):
        if not re.fullmatch(r"0x[0-9a-fA-F]{40}", expected[name]):
            raise ValueError("Invalid public address")
    if int(expected["amount_atomic"]) <= 0:
        raise ValueError("Invalid positive payment amount")
    dsn = os.environ.get("DATABASE_URL", "")
    pg = dsn.startswith(("postgres://", "postgresql://"))
    if pg:
        import psycopg
        from psycopg.rows import dict_row
        connection = psycopg.connect(dsn, autocommit=False, row_factory=dict_row,
            options="-c default_transaction_read_only=on", connect_timeout=10)
        connection.execute("SET TRANSACTION READ ONLY")
    else:
        path = Path(os.environ.get("AIMARKET_DB_PATH", "data/hub.db")).resolve(strict=True)
        connection = sqlite3.connect("file:" + quote(str(path)) + "?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")

    def query(sql, params):
        if pg:
            sql = sql.replace("?", "%s")
        return [dict(row) for row in connection.execute(sql, params).fetchall()]

    def field(column, keys):
        if pg:
            expression = "CAST(" + column + " AS jsonb)"
            for index, key in enumerate(keys):
                expression += ("->>" if index == len(keys) - 1 else "->") + "'" + key + "'"
            return expression
        return "json_extract(" + column + ", '$." + ".".join(keys) + "')"

    try:
        # Every SELECT is scoped to this exact operation/nonce/transaction only.
        invoice = query("SELECT nonce, capability_id, pay_to, amount_units, consumed_at, tx_hash "
                        "FROM settle_invoices WHERE nonce = ?", (expected["invoice_nonce"],))
        payment = query("SELECT nonce, payer, amount_atomic, amount_usd, asset, capability_id, "
                        "status, settle_tx_hash, pay_to, receipt_id FROM x402_payments "
                        "WHERE nonce = ? AND settle_tx_hash = ?",
                        (expected["invoice_nonce"], expected["tx_hash"]))
        selected = {
            "status": ("state_json", ["status"]),
            "input_digest": ("state_json", ["input_digest"]),
            "wallet": ("state_json", ["request", "wallet"]),
            "tx_hash": ("state_json", ["request", "tx_hash"]),
            "invoice_nonce": ("state_json", ["offer", "invoice", "nonce"]),
            "product_id": ("state_json", ["offer", "product_id"]),
            "capability_id": ("state_json", ["offer", "capability_id"]),
            "amount_units": ("state_json", ["offer", "terms", "amount_units"]),
            "pay_to": ("state_json", ["offer", "terms", "pay_to"]),
            "response_status": ("response_json", ["status"]),
            "response_input_digest": ("response_json", ["input_digest"]),
            "response_receipt_nonce": ("response_json", ["receipt", "nonce"]),
            "response_price_usd": ("response_json", ["receipt", "price_usd"]),
        }
        projection = ", ".join(field(column, keys) + " AS " + alias
                               for alias, (column, keys) in selected.items())
        operations = query("SELECT operation_id, busy, " + projection +
                           " FROM seller_operations WHERE operation_id = ? AND response_json <> ''",
                           (expected["operation_id"],))
        checks = {"invoice_count_exactly_one": len(invoice) == 1,
                  "payment_count_exactly_one": len(payment) == 1,
                  "completed_cached_operation_count_exactly_one": len(operations) == 1}
        if len(invoice) == 1:
            row = invoice[0]
            checks["consumed_invoice_matches"] = (
                row["capability_id"] == expected["capability_id"] and
                row["pay_to"].lower() == expected["payee"].lower() and
                int(row["amount_units"]) == int(expected["amount_atomic"]) and
                float(row["consumed_at"]) > 0 and row["tx_hash"].lower() == expected["tx_hash"].lower())
        if len(payment) == 1:
            row = payment[0]
            checks["settled_payment_matches"] = (
                row["status"] == "settled" and row["payer"].lower() == expected["payer"].lower() and
                row["pay_to"].lower() == expected["payee"].lower() and
                row["asset"].lower() == expected["asset"].lower() and
                row["capability_id"] == expected["capability_id"] and
                int(row["amount_atomic"]) == int(expected["amount_atomic"]) and
                Decimal(str(row["amount_usd"])) == Decimal(str(expected["price_usd"])))
            link = row["receipt_id"] or ""
            checks["payment_receipt_link_valid_when_present"] = not link or link == expected["receipt_nonce"]
            receipt_link_present = bool(link)
        else:
            receipt_link_present = False
        if len(operations) == 1:
            row = operations[0]
            checks["operation_matches"] = (
                row["status"] == row["response_status"] == "completed" and not row["busy"] and
                row["input_digest"] == row["response_input_digest"] == expected["input_digest"] and
                row["wallet"].lower() == expected["payer"].lower() and
                row["tx_hash"].lower() == expected["tx_hash"].lower() and
                row["invoice_nonce"].lower() == expected["invoice_nonce"].lower() and
                row["product_id"] == expected["product_id"] and
                row["capability_id"] == expected["capability_id"] and
                int(row["amount_units"]) == int(expected["amount_atomic"]) and
                row["pay_to"].lower() == expected["payee"].lower() and
                row["response_receipt_nonce"] == expected["receipt_nonce"] and
                Decimal(str(row["response_price_usd"])) == Decimal(str(expected["price_usd"])))
        return {"ok": all(checks.values()), "operation_id": expected["operation_id"],
                "transaction_hash": expected["tx_hash"], "amount_atomic": int(expected["amount_atomic"]),
                "checks": checks, "x402_receipt_link_present": receipt_link_present,
                "legacy_empty_x402_receipt_link_qualified": not receipt_link_present,
                "operation_receipt_link_required": True, "read_only_connection": True,
                "scope": "one_exact_buyer_operation_invoice_payment", "raw_rows_emitted": False}
    finally:
        connection.rollback()
        connection.close()


if __name__ == "__main__":
    try:
        result = main()
    except Exception as exc:
        result = {"ok": False, "error_type": type(exc).__name__,
                  "error": "Read-only scoped ledger verification unavailable or mismatched",
                  "raw_rows_emitted": False}
    print(json.dumps(result, sort_keys=True))
    raise SystemExit(0 if result["ok"] else 1)
