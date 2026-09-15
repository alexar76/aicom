#!/usr/bin/env python3
"""First CapShare listing — AI auditor is the ALP gate, not a human score.

Default is dry-run: fetch live Hub evidence + MOMUS findings, print the pack.
``--float`` writes a local IPO ledger (set ACEX_IPO_DB_PATH). It does not
broadcast Base txs and does not POST to the public Hub admin IPO endpoint.

On-chain PulseAMM still needs ≥ 1_000 USDC seed + owner ``setMarketMaker`` /
``createPool`` from the deployer key. That is a separate operator step.

Usage:
  python scripts/launch_first_capshare.py
  python scripts/launch_first_capshare.py --product atlas.products --float
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "aimarket-hub"))

from acex.integrations.ai_audit import (  # noqa: E402
    MIN_AUDIT_SCORE_BPS,
    build_pack,
    fetch_momus_findings,
)

DEFAULT_PRODUCT = "atlas.products"
HUB_SEARCH = os.environ.get(
    "ACEX_HUB_SEARCH_URL",
    "https://modelmarket.dev/ai-market/v2/search",
)
MOMUS_URL = os.environ.get(
    "ACEX_MOMUS_FINDINGS_URL",
    "https://momus.modelmarket.dev/findings",
)


def _get_json(url: str, timeout: float = 12.0) -> dict:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_hub_caps(product_id: str) -> list[dict]:
    q = urllib.parse.urlencode({"intent": product_id, "budget": "5"})
    payload = _get_json(f"{HUB_SEARCH}?{q}")
    matches = payload.get("matches") or []
    return [m for m in matches if str(m.get("product_id") or "") == product_id]


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--product", default=DEFAULT_PRODUCT)
    p.add_argument(
        "--float",
        action="store_true",
        help="Write local ACEX IPO + audit ledgers if the AI pack approves",
    )
    args = p.parse_args()
    pid = args.product.strip()

    print(f"── ACEX AI auditor ({pid}) ──")
    try:
        caps = fetch_hub_caps(pid)
        print(f"  hub matches for product: {len(caps)}")
    except Exception as exc:
        print(f"  hub search failed: {exc}", file=sys.stderr)
        caps = []
    try:
        findings = fetch_momus_findings(MOMUS_URL)
        print(f"  MOMUS findings fetched: {len(findings)}")
    except Exception as exc:
        print(f"  MOMUS fetch failed: {exc}", file=sys.stderr)
        findings = []

    pack = build_pack(pid, caps, momus_findings=findings)
    print(json.dumps({k: pack[k] for k in pack if k != "evidence"}, indent=2))
    if pack["verdict"] != "approve":
        print(
            f"REJECTED — score {pack['score_bps']} < {MIN_AUDIT_SCORE_BPS}. "
            "A human cannot override this pack.",
            file=sys.stderr,
        )
        return 2

    if not args.float:
        print("dry-run: pass --float to mint CapShares on the local IPO ledger.")
        return 0

    os.environ.setdefault("ACEX_REQUIRE_AI_AUDIT", "1")
    os.environ.setdefault("ACEX_IPO_DB_PATH", str(ROOT / "data" / "acex_ipo.db"))
    os.environ.setdefault("ACEX_AUDIT_DB_PATH", str(ROOT / "data" / "acex_audit.db"))
    from aimarket_hub import acex_audit, acex_ipo

    floated = acex_ipo.float_product(
        pid,
        name=pid,
        audit_score_bps=int(pack["score_bps"]),
        auditor_id=pack["auditor_id"],
        auditor_kind=pack["auditor_kind"],
        audit_pack_sha256=pack["pack_sha256"],
    )
    if floated.get("error"):
        print(f"float failed: {floated}", file=sys.stderr)
        return 1
    covered = acex_audit.sync_coverage(
        pid,
        pack["auditor_id"],
        cover_usd=10_000.0,
        score_bps=int(pack["score_bps"]),
        phase="insuring",
    )
    print("── local CapShares minted ──")
    print(f"  IPO ledger: {os.environ.get('ACEX_IPO_DB_PATH')}")
    print(f"  audit ledger: {os.environ.get('ACEX_AUDIT_DB_PATH')}")
    print(json.dumps({**floated, "coverage": covered, "ai_audit": pack}, indent=2, default=str))
    print(
        "On-chain PulseAMM is NOT seeded by this script. "
        "MIN_INITIAL_USDC=1000; deployer must createPool after approveListing."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
