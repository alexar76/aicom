#!/usr/bin/env python3
"""Discharge payout obligations that AIMarketEscrow has already paid.

    python3 scripts/reconcile_escrow_obligations.py            # dry-run
    python3 scripts/reconcile_escrow_obligations.py --apply

Run inside the hub container: it uses the hub's own escrow bridge, so it inherits the
configured contract, network and RPC pool rather than introducing a second source of
truth.

`outstanding_obligations_usd` is published on `/ai-market/v2/stats/live` as the hub's
solvency number — money the operator owes depositors and has not paid. For channels
funded through escrow it was always wrong: `close()` books the unspent remainder as a
debt because on the transfer path the operator is holding the deposit, but an escrow
deposit never leaves the contract and `settleChannel` returns it to the depositor
directly. The live hub was advertising $3.84 owed while the chain showed every one of
those four remainders already returned.

`channels._record_payout_obligation` no longer creates these. This script clears the
ones booked before that fix, and stays useful afterwards for the transfer path, where a
manual payout still needs recording.

An obligation is discharged only when the contract says the channel is Settled or
Refunded. Anything still Open is left alone — that is a real, unpaid debt.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys

DISCHARGED_ON_CHAIN = ("Settled", "Refunded")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default="/app/data/channels.db")
    ap.add_argument("--apply", action="store_true", help="write changes (default: dry-run)")
    args = ap.parse_args()

    from aimarket_hub.escrow_bridge import chain

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT o.channel_id, o.amount_cents, o.wallet, c.escrow_channel "
        "FROM channel_payout_obligations o JOIN channels c USING(channel_id) "
        "WHERE o.status = 'owed' ORDER BY o.created_at"
    ).fetchall()

    if not rows:
        print("no outstanding obligations")
        return 0

    clear, keep_cents = [], 0
    for r in rows:
        escrow = str(r["escrow_channel"] or "").strip()
        if not escrow:
            keep_cents += r["amount_cents"]
            print(f"  {r['channel_id']}  ${r['amount_cents']/100:>5.2f}  transfer-funded "
                  f"— operator must pay this, left alone")
            continue
        try:
            state = chain.read_channel(escrow).status_name
        except Exception as exc:
            keep_cents += r["amount_cents"]
            print(f"  {r['channel_id']}  ${r['amount_cents']/100:>5.2f}  chain read failed "
                  f"({str(exc)[:40]}) — left alone")
            continue
        if state in DISCHARGED_ON_CHAIN:
            clear.append(r["channel_id"])
            print(f"  {r['channel_id']}  ${r['amount_cents']/100:>5.2f}  on-chain {state} "
                  f"— already paid by the contract, discharge")
        else:
            keep_cents += r["amount_cents"]
            print(f"  {r['channel_id']}  ${r['amount_cents']/100:>5.2f}  on-chain {state} "
                  f"— still owed")

    print(f"\n{len(clear)} to discharge, ${keep_cents/100:.2f} genuinely outstanding")
    if not args.apply:
        print("dry-run only — pass --apply to write")
        return 0

    conn.executemany(
        "UPDATE channel_payout_obligations "
        "SET status = 'settled', settled_at = datetime('now'), "
        "    payout_tx_hash = COALESCE(NULLIF(payout_tx_hash,''), 'escrow:settleChannel') "
        "WHERE channel_id = ? AND status = 'owed'",
        [(cid,) for cid in clear],
    )
    conn.commit()
    print(f"discharged {len(clear)} obligation(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
