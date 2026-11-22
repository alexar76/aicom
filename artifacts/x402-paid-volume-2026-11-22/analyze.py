"""Read what measure.py collected and say who pays x402 sellers.

    python3 analyze.py RUN_DIR > summary.json

RUN_DIR holds meta.json, payees.json and transfers*.jsonl (or .jsonl.xz). run24/ is the census of 2026-11-22: 24 hours
of Base, blocks 60,489,171-60,921,170 (2026-11-21 19:10Z to 2026-11-22 19:10Z), read in two parts and deduplicated.

A payer's *reach* is how many of the listed payees it paid in the window. A payer that pays dozens of sellers a week
(indexers, auditors, scanners, test harnesses, our own survey once) is not a seller's customer in the usual sense; the
cut-off between the two is the open question in x402#2833 (scoreSeller), so the summary gives the whole distribution
and the counts at several cut-offs instead of one answer. Transfers of more than $100 are counted apart: x402 calls are
cents, so those are more likely payouts, refunds or exchange moves to an address that also sells.
"""

from __future__ import annotations

import collections
import json
import lzma
import statistics
import sys
from pathlib import Path

CUTOFFS = (5, 10, 20, 50)
BIG_UNITS = 100 * 10**6  # $100


def main(run: Path) -> dict:
    meta = json.loads((run / "meta.json").read_text())
    payees = json.loads((run / "payees.json").read_text())
    files = sorted(run.glob("transfers*.jsonl")) + sorted(run.glob("transfers*.jsonl.xz"))
    rows = [json.loads(line) for f in files
            for line in (lzma.open(f, "rt").read() if f.suffix == ".xz" else f.read_text()).splitlines() if line.strip()]
    seen, transfers = set(), []
    for r in rows:  # one log once, even if a range was read twice
        key = (r["tx"], r["log"])
        if key not in seen:
            seen.add(key)
            transfers.append(r)
    small = [t for t in transfers if t["units"] <= BIG_UNITS and t["payer"] != t["payee"]]
    big = [t for t in transfers if t["units"] > BIG_UNITS]

    reach = collections.Counter()
    pairs = {(t["payer"], t["payee"]) for t in small}
    for payer, _ in pairs:
        reach[payer] += 1
    payers = sorted(reach)
    reach_hist = collections.Counter()
    for p in payers:
        r = reach[p]
        reach_hist["1" if r == 1 else "2-4" if r < 5 else "5-9" if r < 10 else "10-19" if r < 20 else
                   "20-49" if r < 50 else "50+"] += 1

    by_payee = collections.defaultdict(list)
    for t in small:
        by_payee[t["payee"]].append(t)
    total_units = sum(t["units"] for t in small)

    def view(cutoff: int) -> dict:
        wide = {p for p in payers if reach[p] >= cutoff}
        units_wide = sum(t["units"] for t in small if t["payer"] in wide)
        buckets = collections.Counter()
        outside_units = []
        for payee in payees:
            ts = by_payee.get(payee, [])
            others = {t["payer"] for t in ts if t["payer"] not in wide}
            if not ts:
                buckets["no transfer"] += 1
            elif not others:
                buckets["only wide payers"] += 1
            elif len(others) == 1:
                buckets["1 other payer"] += 1
            elif len(others) < 5:
                buckets["2-4 other payers"] += 1
            elif len(others) < 20:
                buckets["5-19 other payers"] += 1
            else:
                buckets["20+ other payers"] += 1
            outside_units.append(sum(t["units"] for t in ts if t["payer"] not in wide))
        outside_units.sort(reverse=True)
        top10 = sum(outside_units[:10])
        rest = sum(outside_units)
        return {
            "cutoff_payees_reached": cutoff,
            "wide_payers": len(wide),
            "wide_payers_share_of_usd_pct": round(100 * units_wide / total_units, 1) if total_units else 0,
            "payee_buckets": dict(sorted(buckets.items())),
            "usd_from_other_payers": round(rest / 1e6, 2),
            "top10_payees_share_of_that_usd_pct": round(100 * top10 / rest, 1) if rest else 0,
        }

    amounts = [t["units"] / 1e6 for t in small]
    return {
        "window": {k: meta[k] for k in ("days", "from_block", "to_block", "from_time", "to_time", "chain", "token")},
        "catalog_listings": meta["catalog_listings"],
        "payees": len(payees),
        "payees_with_any_transfer": len({t["payee"] for t in small}),
        "transfers_up_to_100usd": len(small),
        "usd_up_to_100usd": round(total_units / 1e6, 2),
        "transfers_over_100usd": len(big),
        "usd_over_100usd": round(sum(t["units"] for t in big) / 1e6, 2),
        "payers": len(payers),
        "payer_reach_histogram": dict(reach_hist),
        "payer_reach_top": [reach[p] for p in sorted(payers, key=lambda p: -reach[p])[:10]],
        "transfer_usd_median": round(statistics.median(amounts), 6) if amounts else 0,
        "transfer_usd_quartiles": [round(q, 6) for q in statistics.quantiles(amounts, n=4)] if len(amounts) > 3 else [],
        "views": [view(c) for c in CUTOFFS],
        "bazaar_says_payers_but_chain_shows_none": sum(
            1 for k, v in payees.items() if v.get("bazaar_payers_30d_max", 0) > 0 and k not in by_payee),
    }


if __name__ == "__main__":
    print(json.dumps(main(Path(sys.argv[1])), indent=1))
