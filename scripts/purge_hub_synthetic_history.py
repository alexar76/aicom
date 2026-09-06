#!/usr/bin/env python3
"""Remove self-generated load-test history from a hub database.

    python3 scripts/purge_hub_synthetic_history.py /app/data/hub.db            # dry-run
    python3 scripts/purge_hub_synthetic_history.py /app/data/hub.db --apply

The live hub was publishing `total_invocations: 136199`, `success_rate: 1.0` and
`avg_price_usd: 0.7765` on a public endpoint. Every one of those events was the hub
calling itself: 89,703 from `http://127.0.0.1:9083` and 46,494 from its own public URL,
all against the twelve seeded demo capabilities that could not execute anyway. Real
traffic in the same table: two invocations, $0.16.

`hub.db` also carried a `channels` table with 125,989 rows and $16.4M of fictional
settled deposits. Nothing reads it — the ledger the hub actually uses is a separate
file, `channels.db` (`AIMARKET_CHANNELS_DB_PATH`), which correctly holds four channels.
That table is emptied here rather than dropped, so a migration expecting it still finds
its schema.

Selection is by consumer, not by date: an event whose consumer is this hub, localhost,
or the literal `local` is self-traffic whenever it happened. Anything from a real
external consumer survives regardless of age, so re-running this later cannot eat
genuine history.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys

# Consumers that mean "we called ourselves". `operator_self` is deliberately NOT here:
# the hub tags its own operator-driven invokes with it, and those are the two real paid
# calls — they belong in the record.
SELF_CONSUMERS = ("local", "127.0.0.1", "localhost", "0.0.0.0")


def is_self(consumer: str, hub_url: str) -> bool:
    c = (consumer or "").strip().rstrip("/").lower()
    if not c:
        return True
    if hub_url and c == hub_url.strip().rstrip("/").lower():
        return True
    return any(s in c for s in SELF_CONSUMERS)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("db_path")
    ap.add_argument("--hub-url", default="https://modelmarket.dev")
    ap.add_argument("--apply", action="store_true", help="write changes (default: dry-run)")
    args = ap.parse_args()

    conn = sqlite3.connect(args.db_path)
    conn.row_factory = sqlite3.Row

    rows = conn.execute(
        "SELECT id, COALESCE(consumer_hub,'') AS consumer FROM invocation_stats"
    ).fetchall()
    doomed = [r["id"] for r in rows if is_self(r["consumer"], args.hub_url)]
    keep = len(rows) - len(doomed)

    print(f"invocation_stats : {len(rows)} rows, {len(doomed)} self-generated, {keep} kept")
    for r in conn.execute(
        "SELECT COALESCE(consumer_hub,'(null)') c, COUNT(*) n, MIN(timestamp) a, MAX(timestamp) b "
        "FROM invocation_stats GROUP BY c ORDER BY n DESC LIMIT 10"
    ):
        verdict = "PURGE" if is_self(r["c"], args.hub_url) else "keep "
        print(f"  {verdict} {r['c'][:46]:<46} {r['n']:>7}  {r['a'][:10]}..{r['b'][:10]}")

    ch = conn.execute("SELECT COUNT(*) n FROM channels").fetchone()["n"]
    print(f"\nchannels (unused table in this db): {ch} rows -> emptied")

    if not args.apply:
        print("\ndry-run only — pass --apply to write")
        return 0

    conn.executemany("DELETE FROM invocation_stats WHERE id = ?", [(i,) for i in doomed])
    conn.execute("DELETE FROM channels")
    conn.commit()
    conn.execute("VACUUM")
    conn.commit()

    left = conn.execute("SELECT COUNT(*) n FROM invocation_stats").fetchone()["n"]
    print(f"\ndeleted {len(doomed)} events and {ch} channel rows; {left} events remain")
    return 0


if __name__ == "__main__":
    sys.exit(main())
