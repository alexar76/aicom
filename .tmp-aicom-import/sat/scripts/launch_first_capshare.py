#!/usr/bin/env python3
"""First CapShare listing — AI auditor is the ALP gate, not a human score.

Default is dry-run: fetch live Hub evidence + MOMUS findings, print the pack.

``--float`` writes a local IPO ledger (set ACEX_IPO_DB_PATH). Dev/SQLite only.

``--hub-float`` POSTs to the live Hub admin IPO endpoint. The Hub runs
``ai-auditor:acex-v1`` itself — do **not** send ``audit_score_bps``.
Requires ``AIMARKET_ADMIN_TOKEN``.

On-chain PulseAMM still needs ≥ 1_000 USDC seed + owner ``setMarketMaker`` /
``createPool`` from the deployer key. See ``acex/docs/first-market-launch.md``.

Usage:
  python scripts/launch_first_capshare.py
  python scripts/launch_first_capshare.py --product atlas.products --float
  python scripts/launch_first_capshare.py --product atlas.products --hub-float
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
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
HUB_IPO = os.environ.get(
    "ACEX_HUB_IPO_URL",
    "https://modelmarket.dev/ai-market/v2/capital/ipo",
)
MOMUS_URL = os.environ.get(
    "ACEX_MOMUS_FINDINGS_URL",
    "https://momus.modelmarket.dev/findings",
)


def _get_json(url: str, timeout: float = 12.0) -> dict:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _post_json(url: str, body: dict, *, token: str, timeout: float = 60.0) -> tuple[int, dict]:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8") if exc.fp else ""
        try:
            payload = json.loads(raw) if raw else {"error": exc.reason}
        except json.JSONDecodeError:
            payload = {"error": raw or str(exc.reason)}
        return int(exc.code), payload


def fetch_hub_caps(product_id: str) -> list[dict]:
    q = urllib.parse.urlencode({"intent": product_id, "budget": "5"})
    payload = _get_json(f"{HUB_SEARCH}?{q}")
    matches = payload.get("matches") or []
    return [m for m in matches if str(m.get("product_id") or "") == product_id]


def _admin_token() -> str:
    token = (os.environ.get("AIMARKET_ADMIN_TOKEN") or "").strip()
    if token:
        return token
    secret = ROOT / "data" / "secrets" / "aimarket_admin_token.txt"
    if secret.is_file():
        return secret.read_text(encoding="utf-8").strip()
    return ""


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--product", default=DEFAULT_PRODUCT)
    p.add_argument(
        "--float",
        action="store_true",
        help="Write local ACEX IPO + audit ledgers if the AI pack approves (dev SQLite)",
    )
    p.add_argument(
        "--hub-float",
        action="store_true",
        help="POST /capital/ipo on the live Hub (AI auditor runs on the Hub; no human score)",
    )
    args = p.parse_args()
    if args.float and args.hub_float:
        print("pass only one of --float or --hub-float", file=sys.stderr)
        return 2
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

    if args.hub_float:
        token = _admin_token()
        if not token:
            print(
                "AIMARKET_ADMIN_TOKEN missing (env or data/secrets/aimarket_admin_token.txt)",
                file=sys.stderr,
            )
            return 1
        # Hub re-runs AI audit; omit audit_score_bps or it returns human_audit_override_forbidden.
        body = {"product_id": pid, "name": pid}
        status, payload = _post_json(HUB_IPO, body, token=token)
        print(f"── Hub IPO POST {HUB_IPO} → HTTP {status} ──")
        print(json.dumps(payload, indent=2, default=str))
        if status >= 400 or payload.get("error"):
            return 1
        print(
            "Off-chain CapShares floated on Hub. "
            "PulseAMM createPool is still a separate operator step "
            "(see acex/docs/first-market-launch.md)."
        )
        return 0

    if not args.float:
        print("dry-run: pass --float (local) or --hub-float (prod Hub admin IPO).")
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
    print(
        json.dumps(
            {**floated, "coverage": covered, "ai_audit": pack},
            indent=2,
            default=str,
        )
    )
    print(
        "On-chain PulseAMM is NOT seeded by this script. "
        "MIN_INITIAL_USDC=1000; deployer must createPool after approveListing."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
