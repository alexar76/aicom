"""Deploy bodies, generated from the handler sources.

The handler source is embedded in the deploy request, so a hand-edited
deploy.json silently ships different code than the file under review. These are
generated, and tests assert the two still match.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
AGENTS_DIR = ROOT / "agents"

# Placeholder identity. Replace with the operator's real Ed25519 public key
# before deploying anywhere that owner matters; HESTIA records it but does not
# yet verify an owner signature at deploy time.
OWNER_PUBKEY = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="

# Where buyers pay these agents. The hearth verifies a transfer to this address
# on chain and serves the call; it never holds the funds and takes no cut, so
# this is the tenant owner's own wallet.
PAYOUT_ADDRESS = "0x1218ff36C5d2e3B6A565CdB1A8B1AcCFc606Ad0a"

PRODUCT_ID = "hestia-agents"
PUBLISHER_ID = "aicom"

AGENTS: dict[str, dict[str, Any]] = {
    "rules-decide": {
        "capability_id": "rules.decide@v1",
        "name": "Policy decision with a rule trace",
        "description": (
            "Evaluates a versioned rule set against a set of facts and returns the "
            "decision, the rule that fired, and why each earlier rule did not. "
            "Deterministic, so anyone holding the policy and the facts can re-run it "
            "and check the signed receipt."
        ),
        "price_per_call_usd": 0.004,
        "note": "verifiable decisions — pairs with pay-on-verified escrow",
    },
    "json-canonical": {
        "capability_id": "json.canonical@v1",
        "name": "Canonical JSON (RFC 8785) and digest",
        "description": (
            "Canonicalises a JSON value per RFC 8785 and returns the bytes plus "
            "SHA-256 and SHA-384. Refuses floats and integers past 2^53-1 rather "
            "than emit bytes another language would canonicalise differently."
        ),
        "price_per_call_usd": 0.001,
        "note": "signing helper for AWR receipts and W3C verifiable credentials",
    },
    "commit-referee": {
        "capability_id": "commit.referee@v1",
        "name": "Commit-reveal referee",
        "description": (
            "Checks a revealed value against its commitment and reports whether the "
            "commitment scheme itself binds. Flags salt||value layouts that let a "
            "committer open the same commitment two different ways."
        ),
        "price_per_call_usd": 0.002,
        "note": "settles reveals for lotteries and sealed-bid auctions",
    },
}


def handler_source(slug: str) -> str:
    return (AGENTS_DIR / slug / "handler.py").read_text(encoding="utf-8")


def deploy_body(
    slug: str,
    *,
    owner_pubkey: str = OWNER_PUBKEY,
    announce: bool = False,
    payout_address: str = PAYOUT_ADDRESS,
) -> dict[str, Any]:
    meta = AGENTS[slug]
    return {
        "slug": slug,
        "capability": {
            "product_id": PRODUCT_ID,
            "capability_id": meta["capability_id"],
            "name": meta["name"],
            "description": meta["description"],
            "price_per_call_usd": meta["price_per_call_usd"],
            "input_schema": {"type": "object"},
            "output_schema": {"type": "object"},
            "publisher_id": PUBLISHER_ID,
            "provider_pubkey": "",
        },
        "source": {"kind": "template", "handler": handler_source(slug)},
        "owner_pubkey": owner_pubkey,
        # Announcing puts a row in the Hub catalogue. That is an explicit,
        # outward-facing act, so it is never the default here.
        "announce": announce,
        "payout_address": payout_address,
        "note": meta["note"],
    }


def write_manifests() -> list[Path]:
    written = []
    for slug in AGENTS:
        target = AGENTS_DIR / slug / "deploy.json"
        body = json.dumps(deploy_body(slug), indent=2, ensure_ascii=False) + "\n"
        target.write_text(body, encoding="utf-8")
        written.append(target)
    return written
