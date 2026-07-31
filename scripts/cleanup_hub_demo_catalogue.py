#!/usr/bin/env python3
"""Find capabilities a hub is offering that it cannot execute, and fix them.

    python3 scripts/cleanup_hub_demo_catalogue.py /app/data/hub.db            # dry-run
    python3 scripts/cleanup_hub_demo_catalogue.py /app/data/hub.db --apply    # flag demos
    python3 scripts/cleanup_hub_demo_catalogue.py /app/data/hub.db --apply --delete

Selects by **defect, not by name**. The previous version matched `(\\d+)`, `template`,
`one-pager` and `waitlist`, which caught the eleven obviously-ugly factory artifacts and
missed twelve seeded rows priced $0.15-$1.50 whose invoke path answered 404 —
`code.review@v1`, `legal.review@v1`, `translate.doc@v1` and friends. Respectable names
were the only thing separating them from the rows that were deleted.

A capability is unfulfillable when it is local and has neither an `invoke_url` nor a
static JSON pack in `prompt_template`; see `aimarket_hub.fulfillment`. Federated rows are
never touched — the peer that published them owns execution.

Default action is `is_demo=1`, not deletion. Most offenders are the hub's own seeded
showcase, which exists so a fresh hub is not empty; flagging keeps it visible to anyone
who asks with `include_demo=true` while removing it from the storefront. `--delete` is
for rows that should not exist at all, like duplicated factory runs.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys

UNFULFILLABLE_LOCAL = (
    "source_hub='local' AND COALESCE(invoke_url,'')='' "
    "AND COALESCE(prompt_template,'') NOT LIKE '{%'"
)

# Kept only to label the output. Selection no longer depends on it — a row is a problem
# because it cannot run, whatever it happens to be called.
JUNK_HINTS = ("(", "template:", "one-pager", "waitlist", "caldera", "lensline")


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("db_path")
    ap.add_argument("--apply", action="store_true", help="write changes (default: dry-run)")
    ap.add_argument(
        "--delete", action="store_true", help="DELETE the rows instead of setting is_demo=1"
    )
    args = ap.parse_args()

    conn = sqlite3.connect(args.db_path)
    conn.row_factory = sqlite3.Row

    total = conn.execute(
        "SELECT COUNT(*) FROM capabilities WHERE source_hub='local'"
    ).fetchone()[0]
    rows = conn.execute(
        "SELECT capability_id, product_id, name, price_per_call_usd, "
        "COALESCE(is_demo,0) AS is_demo "
        f"FROM capabilities WHERE {UNFULFILLABLE_LOCAL} ORDER BY capability_id"
    ).fetchall()

    print(f"{len(rows)} of {total} local capabilities have no execution path")
    for r in rows:
        blob = f"{r['capability_id']} {r['name']}".lower()
        kind = "factory-junk" if any(h in blob for h in JUNK_HINTS) else "seeded-showcase"
        state = "already flagged" if r["is_demo"] else "SOLD AS REAL"
        print(f"  {r['capability_id'][:40]:<40} ${r['price_per_call_usd']:<6} {kind:<16} {state}")

    if not rows:
        print("\nnothing to do — every local capability can be executed")
        return 0

    if not args.apply:
        print("\ndry-run only — pass --apply to write (add --delete to remove instead of flag)")
        return 0

    ids = [(r["capability_id"],) for r in rows]
    if args.delete:
        conn.executemany(
            "DELETE FROM capabilities WHERE capability_id=? AND source_hub='local'", ids
        )
        conn.commit()
        print(f"\ndeleted {len(ids)} rows")
    else:
        conn.executemany(
            "UPDATE capabilities SET is_demo=1 WHERE capability_id=? AND source_hub='local'", ids
        )
        conn.commit()
        print(
            f"\nflagged is_demo=1 on {len(ids)} rows — they stay visible with "
            "include_demo=true and leave the storefront"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
