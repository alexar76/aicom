#!/usr/bin/env python3
"""Export provenance receipts from SQLite to static JSON files.

Reads the provenance database and writes each receipt as a JSON file
under docs/verifier/data/receipts/<short_id>.json.

Usage:
    python scripts/export_receipts.py [--db data/provenance.db] [--out docs/verifier/data/receipts]
"""

import argparse
import json
import os
import sys


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export provenance receipts as static JSON files"
    )
    parser.add_argument(
        "--db",
        default="data/provenance.db",
        help="Path to provenance.db (default: data/provenance.db)",
    )
    parser.add_argument(
        "--out",
        default="docs/verifier/data/receipts",
        help="Output directory (default: docs/verifier/data/receipts)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=5000,
        help="Max receipts to export (default: 5000)",
    )
    args = parser.parse_args()

    if not os.path.isfile(args.db):
        print(f"Database not found: {args.db}", file=sys.stderr)
        return 1

    # Add project root to path for imports
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

    from aimarket_provenance.storage import ProvenanceStorage
    from aimarket_provenance.receipt import ProvenanceReceipt

    storage = ProvenanceStorage(args.db)
    os.makedirs(args.out, exist_ok=True)

    count = 0
    for receipt in storage.list_receipts(limit=args.limit):
        short_id = (
            receipt.receipt_id.split(":")[-1]
            if ":" in receipt.receipt_id
            else receipt.receipt_id
        )
        path = os.path.join(args.out, f"{short_id}.json")
        with open(path, "w") as f:
            json.dump(receipt.to_dict(), f, indent=2)
        count += 1
        print(f"  {short_id}.json")

    print(f"\nExported {count} receipt(s) to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
