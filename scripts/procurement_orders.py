#!/usr/bin/env python3
"""Inspect purchase accounting or explicitly reconcile an unknown bill from operator evidence."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.paths import data_root
from core.procurement_store import PurchaseStore, micros


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=data_root())
    sub = parser.add_subparsers(dest="command", required=True)
    listing = sub.add_parser("list")
    listing.add_argument("--product")
    resolve = sub.add_parser("reconcile", help="Records an operator-confirmed charge; never retries an invoke")
    resolve.add_argument("--order", required=True)
    resolve.add_argument("--charged-usd", required=True)
    resolve.add_argument("--evidence", required=True, help="Billing reference and reason, without credentials")
    args = parser.parse_args()
    store = PurchaseStore(args.data_root)
    if args.command == "list":
        fields = ("id", "product", "supplier", "status", "payment", "reserved", "charged", "reason", "outcome")
        print(json.dumps([{k: row[k] for k in fields} for row in store.orders(args.product)], indent=2))
        return
    row = next((r for r in store.orders() if r["id"] == args.order), None)
    if row is None or row["payment"] != "unknown":
        parser.error("order is missing or already reconciled")
    if not args.evidence.strip():
        parser.error("billing evidence is required")
    try:
        amount = micros(args.charged_usd)
    except (ValueError, ArithmeticError):
        parser.error("charged-usd must be a finite non-negative number")
    store.finish(args.order, status="rejected", charged=amount,
                 reason="operator_reconciled: " + args.evidence[:2000])
    print(json.dumps({"order": args.order, "charged_micro_usd": amount, "retried": False}))


if __name__ == "__main__":
    main()
