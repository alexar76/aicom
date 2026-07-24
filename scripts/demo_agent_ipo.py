#!/usr/bin/env python3
"""Agent IPO demo — factory → hub → ACEX, end to end, no human clicks.

Shows the full leg that was previously "Planned":
  1. AI-Factory ships a COMPLETED product
  2. Hub auto-lists its capabilities (auto_listing)
  3. ACEX floats it as CapShares (Agent IPO)               ← new leg
  4. A secondary investor buys a slice of the cap table
  5. Paid invokes route a revenue share into the pool      ← new leg
  6. Distribution pays holders pro-rata; they claim         ← new leg
  7. Pulse Terminal pricing reflects the live listing

Runs fully offline (no hub server, no chain) on Python 3.9+.

Usage:
  python scripts/demo_agent_ipo.py
Exit 0 when the holder payouts reconcile exactly to the distributed pool.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

# Configure ACEX BEFORE importing hub modules so module constants bind correctly.
_TMP = tempfile.mkdtemp(prefix="agent-ipo-demo-")
os.environ.setdefault("ACEX_AUTO_IPO", "1")
os.environ.setdefault("ACEX_REVENUE_SHARE_BPS", "5000")   # 50% to shareholders
os.environ.setdefault("ACEX_DEFAULT_MAX_SUPPLY", "1000000")
os.environ.setdefault("ACEX_TREASURY_HOLDER", "factory-treasury")
os.environ["ACEX_IPO_DB_PATH"] = str(Path(_TMP) / "acex_ipo.db")

_HUB = Path(__file__).resolve().parents[1] / "aimarket-hub"
if str(_HUB) not in sys.path:
    sys.path.insert(0, str(_HUB))

from aimarket_hub import acex_ipo  # noqa: E402
from aimarket_hub.auto_listing import auto_list_product  # noqa: E402
from aimarket_hub.capital_pricing import hub_capital_pricing  # noqa: E402
from aimarket_hub.database import HubDatabase  # noqa: E402

PRODUCT_ID = "prod-coldoutreach"
INVESTOR = "investor-alice"


def _write_pipeline(path: Path) -> None:
    path.write_text(json.dumps({
        "products": {
            PRODUCT_ID: {
                "name": "Cold Outreach Agent",
                "idea": "Autonomous AI agent that drafts and sends personalized cold outreach.",
                "state": "COMPLETED",
            }
        }
    }), encoding="utf-8")


def main() -> int:
    db = HubDatabase(str(Path(_TMP) / "hub.db"))
    pipeline = Path(_TMP) / "pipeline.json"
    _write_pipeline(pipeline)

    print("── 1+2+3. Factory ships → Hub auto-lists → ACEX floats ──")
    listed = auto_list_product(PRODUCT_ID, db=db, pipeline_path=pipeline)
    caps = [c["capability_id"] for c in listed["listed_capabilities"]]
    print(f"  listed capabilities: {caps}")
    ipo = listed.get("ipo") or {}
    if ipo.get("error") or not caps:
        print(f"  FAILED: IPO not floated: {ipo or listed.get('errors')}", file=sys.stderr)
        return 1
    print(f"  IPO: {ipo['symbol']} status={ipo['status']} "
          f"shares={ipo['shares_outstanding']} treasury={ipo['treasury']}")

    print("── 4. Secondary float: treasury sells 30% to an investor ──")
    t = acex_ipo.transfer_shares(PRODUCT_ID, "factory-treasury", INVESTOR, 300_000)
    if t.get("error"):
        print(f"  FAILED transfer: {t}", file=sys.stderr)
        return 1
    cap = acex_ipo.cap_table(PRODUCT_ID)
    for h in cap["holders"]:
        print(f"  {h['holder']:18} {h['shares']:>9,} shares  ({h['pct']}%)")

    print("── 5. 10 paid invokes ($1.00 each) route revenue to the pool ──")
    for _ in range(10):
        acex_ipo.accrue_revenue(PRODUCT_ID, 1.00)
    rev = acex_ipo.revenue_state(PRODUCT_ID)
    print(f"  gross=${rev['gross_revenue_usd']}  to pool (50%)=${rev['accrued_undistributed_usd']}")

    print("── 6. Distribute pro-rata ──")
    dist = acex_ipo.distribute(PRODUCT_ID)
    for p in dist["payouts"]:
        print(f"  {p['holder']:18} ← ${p['amount_usd']}  ({p['shares']:,} shares)")

    print("── 6.5. On-chain bridge: Merkle claimset for PulseDistributor ──")
    address_map = {
        "factory-treasury": "0x" + "a1" * 20,
        INVESTOR: "0x" + "b2" * 20,
    }
    cs = acex_ipo.build_onchain_claimset(PRODUCT_ID, address_map)
    print(f"  merkle_root={cs['merkle_root'][:18]}…  total={cs['total']} base-units  claims={cs['claim_count']}")
    # Verify one proof exactly as PulseDistributor.claim() would on-chain.
    from aimarket_hub import acex_merkle
    root_b = bytes.fromhex(cs["merkle_root"][2:])
    sample = cs["claims"][0]
    leaf = acex_merkle.make_leaf(sample["index"], sample["account"], sample["amount"])
    proof = [bytes.fromhex(p[2:]) for p in sample["proof"]]
    assert acex_merkle.verify(proof, root_b, leaf), "merkle proof failed"
    print(f"  proof verified for {sample['account'][:10]}… amount={sample['amount']} base-units ✓")

    print("── 7. Off-chain claim rail ──")
    claimed = acex_ipo.claim(PRODUCT_ID, INVESTOR)
    print(f"  {INVESTOR} claimed ${claimed['claimed_usd']}")

    print("── 8. Pulse Terminal pricing sees the live listing ──")
    snap = hub_capital_pricing(db, listing_id=PRODUCT_ID)
    print(f"  acex_listings_live={snap['acex_listings_live']}")
    for row in snap["listings"]:
        if row["listing_id"] == PRODUCT_ID:
            print(f"  share_price≈${row['share_price_usd']}  "
                  f"shares_outstanding={row.get('shares_outstanding')}  "
                  f"distributed=${row.get('distributed_usd')}")

    # ── Reconciliation: payouts must equal the distributed pool exactly ──
    total_paid = round(sum(p["amount_usd"] for p in dist["payouts"]), 6)
    expected = rev["accrued_undistributed_usd"]  # 50% of $10.00 = $5.00
    investor_share = next(p["amount_usd"] for p in dist["payouts"] if p["holder"] == INVESTOR)

    ok = (
        total_paid == dist["distributed_usd"] == expected == 5.00
        and investor_share == 1.50  # 30% of $5.00
        and claimed["claimed_usd"] == 1.50
    )
    print()
    if ok:
        print(f"✅ SUCCESS — distributed ${total_paid} reconciles exactly; "
              f"investor (30%) received ${investor_share}.")
        return 0
    print(f"❌ FAILED reconciliation: paid={total_paid} expected={expected} "
          f"investor={investor_share}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
