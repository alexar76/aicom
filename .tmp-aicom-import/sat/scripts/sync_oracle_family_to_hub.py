#!/usr/bin/env python3
"""Index oracle-family manifest into AIMARKET_DB_PATH (Sortes, Platon, …).

Run after hub deploy or when federated caps are missing:

  PYTHONPATH=.:aimarket-hub python3 scripts/sync_oracle_family_to_hub.py

Exit 1 when sortes.draw@v1 is still absent after crawl (ops signal).
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "aimarket-hub") not in sys.path:
    sys.path.insert(0, str(ROOT / "aimarket-hub"))

DEFAULT_WK = "https://oracles.modelmarket.dev/.well-known/ai-market.json"


async def _crawl(well_known_url: str) -> dict:
    from aimarket_hub.config import HubConfig
    from aimarket_hub.crawler import Crawler
    from aimarket_hub.database import HubDatabase
    from aimarket_hub.signing import Signer
    from aimarket_hub.trust import TrustScorer

    config = HubConfig()
    db = HubDatabase(config.db_path, database_url=config.database_url)
    signer = Signer(config.signing_key_path)
    crawler = Crawler(
        config=config,
        db=db,
        signer=signer,
        trust_scorer=TrustScorer(db),
    )
    try:
        result = await crawler._crawl_one(well_known_url, 0, "sync_oracle_family")
        if result is None:
            return {"ok": False, "error": "crawl_failed", "indexed": 0}
        sortes = db.find_by_capability_id("sortes.draw@v1")
        return {
            "ok": True,
            "indexed": int(result.get("capabilities_count") or 0),
            "sortes_present": sortes is not None,
            "sortes_product_id": sortes.product_id if sortes else None,
            "sortes_source_hub": sortes.source_hub if sortes else None,
        }
    finally:
        await crawler.close()
        db.close()


def main() -> int:
    ap = argparse.ArgumentParser(description="Crawl oracle-family into hub DB")
    ap.add_argument(
        "--well-known",
        default=os.environ.get("ORACLE_FAMILY_WELL_KNOWN", DEFAULT_WK),
        help="Oracle family .well-known URL",
    )
    ap.add_argument(
        "--require-sortes",
        action="store_true",
        default=True,
        help="Exit 1 if sortes.draw@v1 missing after crawl (default: on)",
    )
    ap.add_argument(
        "--no-require-sortes",
        action="store_false",
        dest="require_sortes",
        help="Do not fail when Sortes cap is absent",
    )
    args = ap.parse_args()

    os.environ.setdefault("AIMARKET_DB_PATH", str(ROOT / "data" / "hub" / "hub.db"))

    stats = asyncio.run(_crawl(args.well_known))
    if not stats.get("ok"):
        print(f"FAIL: {stats.get('error', 'unknown')}", file=sys.stderr)
        return 1

    print(
        f"OK indexed {stats['indexed']} capability row(s) from {args.well_known}"
    )
    if stats.get("sortes_present"):
        print(
            f"  sortes.draw@v1 → product_id={stats['sortes_product_id']} "
            f"source_hub={stats['sortes_source_hub']}"
        )
    elif args.require_sortes:
        print("FAIL: sortes.draw@v1 not found in hub DB after crawl", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
