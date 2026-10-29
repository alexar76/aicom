"""Agent-discovery surfaces for the whole row: x402 manifest, skill.md,
llms.txt, and one Bazaar discovery extension per route.

Standing rules (inherited from the sibling services, all test-pinned):
every route's extension carries a FULL typed output schema (never the
hollow {"type", "example"} shape), every description is under the
500-char CDP limit and carries a "use when" sentence, and the manifest
accepts mirror the live 402 challenges exactly.
"""

from __future__ import annotations

from .config import PRICE_UNITS, SOLANA_ACCEPT_PATHS, Settings, units_to_price
from .services.nudge import nudge_extension

USDC_ASSET = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"

# x402scan ownership proof: an EIP-191 personal_sign of this service's bare
# origin URL ("https://stall-row-production.up.railway.app") by the payTo
# wallet, signed by the owner on 2026-10-25. Published in the manifest below
# and in the OpenAPI x-discovery / x-agentcash-provenance root keys (see
# main.py) so x402scan can verify control of the payment address. This is
# publish-and-verify: the proofs must stay published permanently — removing
# them un-verifies the x402scan listing. DO NOT REMOVE.
OWNERSHIP_PROOFS = [
    "0x89b5fb8c99407c2e2537aa130e54c3dd17f21775b4699f54bded387a09412641126cad8aed0b6367ca8972055827221dc77b4ccfb9d82fcb96cecdc8812732be1b"
]

_S = {"type": "string"}
_N = {"type": ["string", "null"]}
_I = {"type": "integer"}
_IS = {"type": ["integer", "string"]}
_IN = {"type": ["integer", "null"]}
_B = {"type": "boolean"}


def _obj(props: dict, required: list[str]) -> dict:
    return {"type": "object", "properties": props, "required": required}


# ---------------------------------------------------------------------------
# Route table: path -> (description, input schema, output schema, examples,
# tags). Descriptions MUST stay < 500 chars (asserted at import time and
# in tests) and contain a "Use ... when" sentence.
# ---------------------------------------------------------------------------

ROUTES: dict[str, dict] = {
    "/v1/wallet-snapshot": {
        "description": (
            "Snapshot one Base wallet in a single call: ETH balance, top token "
            "holdings, first and last activity, and outgoing transaction count. "
            "Use this when an agent needs a wallet's shape before deciding to "
            "pay, trust, or transact with it. Explorer fields that cannot be "
            "supplied come back marked unknown, never invented."
        ),
        "tags": ["base", "wallet", "balances", "data", "agents"],
        "input_schema": _obj({"address": _S}, ["address"]),
        "input_example": {"address": "0x097f9685D1e0752bF8B02d61E5Ce9be7eA0FBA7F"},
        "output_schema": _obj(
            {
                "address": _S,
                "eth_balance": _S,
                "eth_balance_wei": _N,
                "eth_balance_source": _S,
                "outgoing_tx_count_nonce": _IN,
                "is_contract": {"type": ["boolean", "string", "null"]},
                "token_balances": {
                    "type": ["array", "string"],
                    "items": _obj(
                        {
                            "address": _N,
                            "name": _N,
                            "symbol": _N,
                            "decimals": _IN,
                            "balance": _N,
                            "balance_raw": _N,
                        },
                        ["address", "name", "symbol", "decimals", "balance", "balance_raw"],
                    ),
                },
                "first_activity": _S,
                "last_activity": _S,
                "sources": {"type": "object"},
                "note": _S,
            },
            ["address", "eth_balance", "sources"],
        ),
        "output_example": {
            "address": "0x097f9685D1e0752bF8B02d61E5Ce9be7eA0FBA7F",
            "eth_balance": "0.0042",
            "eth_balance_wei": "4200000000000000",
            "eth_balance_source": "blockscout",
            "outgoing_tx_count_nonce": 137,
            "is_contract": False,
            "token_balances": [
                {
                    "address": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
                    "name": "USD Coin",
                    "symbol": "USDC",
                    "decimals": 6,
                    "balance": "12.5",
                    "balance_raw": "12500000",
                }
            ],
            "first_activity": "2025-11-02T14:03:11.000000Z",
            "last_activity": "2026-10-20T09:41:52.000000Z",
            "sources": {"eth_balance": "blockscout", "token_balances": "blockscout", "activity_window": "blockscout"},
            "note": "Fields marked unknown could not be supplied by their source.",
        },
    },
    "/v1/allowance-audit": {
        "description": (
            "Audit one Base wallet's ERC-20 approvals against a curated list of "
            "major spenders (Permit2, Uniswap, Aerodrome, aggregators): active "
            "approvals are listed and unlimited ones flagged high risk. Use this "
            "when an agent or its owner wants to know what a wallet has already "
            "authorized before it holds or moves funds. When the explorer "
            "cannot supply the held-token list, the token-dependent fields "
            "come back marked unknown rather than the call failing."
        ),
        "tags": ["base", "security", "approvals", "allowance", "agents"],
        "input_schema": _obj({"address": _S}, ["address"]),
        "input_example": {"address": "0x097f9685D1e0752bF8B02d61E5Ce9be7eA0FBA7F"},
        "output_schema": _obj(
            {
                "address": _S,
                "tokens_held_checked": _IS,
                "spenders_checked": _I,
                "spender_coverage": {"type": "array", "items": _S},
                "allowance_checks_performed": _I,
                "active_approvals": {
                    "type": ["array", "string"],
                    "items": _obj(
                        {
                            "token_address": _N,
                            "token_symbol": _N,
                            "spender": _S,
                            "spender_name": _S,
                            "allowance": _N,
                            "allowance_raw": _S,
                            "unlimited": _B,
                            "risk": _S,
                        },
                        ["spender", "spender_name", "allowance_raw", "unlimited", "risk"],
                    ),
                },
                "unlimited_approvals": _IS,
                "summary": _S,
                "coverage_note": _S,
                "note": _S,
            },
            ["address", "tokens_held_checked", "spenders_checked", "active_approvals", "unlimited_approvals", "summary"],
        ),
        "output_example": {
            "address": "0x097f9685D1e0752bF8B02d61E5Ce9be7eA0FBA7F",
            "tokens_held_checked": 2,
            "spenders_checked": 10,
            "spender_coverage": ["Permit2 (Uniswap)", "Uniswap V3 SwapRouter02"],
            "allowance_checks_performed": 20,
            "active_approvals": [],
            "unlimited_approvals": 0,
            "summary": "No active approvals found across 2 held token(s) and 10 known spenders.",
            "coverage_note": "Only the listed spenders are checked.",
        },
    },
    "/v1/tx-decoder": {
        "description": (
            "Decode one Base transaction into plain English: sender, receiver, "
            "ETH value, status, the known method behind the selector, every "
            "ERC-20 transfer it made, and a one-sentence summary. Use this "
            "when an agent needs to explain or verify what a transaction "
            "actually did before acting on it."
        ),
        "tags": ["base", "transactions", "decode", "data", "agents"],
        "input_schema": _obj({"tx_hash": _S}, ["tx_hash"]),
        "input_example": {"tx_hash": "0x" + "ab" * 32},
        "output_schema": _obj(
            {
                "tx_hash": _S,
                "block_number": _IN,
                "from": _N,
                "to": _N,
                "value_eth": _S,
                "status": _S,
                "method_id": _N,
                "method": _N,
                "method_description": _N,
                "gas_used": _IN,
                "erc20_transfers": {
                    "type": "array",
                    "items": _obj(
                        {"token": _N, "from": _S, "to": _S, "amount_raw": _N},
                        ["from", "to"],
                    ),
                },
                "summary": _S,
            },
            ["tx_hash", "value_eth", "status", "erc20_transfers", "summary"],
        ),
        "output_example": {
            "tx_hash": "0x" + "ab" * 32,
            "block_number": 22104511,
            "from": "0x1111111111111111111111111111111111111111",
            "to": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
            "value_eth": "0",
            "status": "success",
            "method_id": "0xa9059cbb",
            "method": "transfer",
            "method_description": "ERC-20 transfer(to, amount)",
            "gas_used": 51604,
            "erc20_transfers": [
                {
                    "token": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
                    "from": "0x1111111111111111111111111111111111111111",
                    "to": "0x2222222222222222222222222222222222222222",
                    "amount_raw": "12500000",
                }
            ],
            "summary": "ERC-20 transfer(to, amount) from 0x1111111111111111111111111111111111111111 to 0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913 with 1 ERC-20 transfer(s) — status: success.",
        },
    },
    "/v1/gas-oracle": {
        "description": (
            "Current Base gas in one call: the live gas price, the current "
            "base fee, the base-fee range across the last 20 blocks, whether "
            "fees are rising, falling, or flat, and a cheap-window hint drawn "
            "from that data. Use this when an agent wants to time a "
            "transaction instead of paying whatever the moment charges."
        ),
        "tags": ["base", "gas", "fees", "data", "agents"],
        "input_schema": _obj({}, []),
        "input_example": {},
        "output_schema": _obj(
            {
                "chain": _S,
                "latest_block": _I,
                "gas_price_gwei": _S,
                "base_fee_gwei": _S,
                "base_fee_min_gwei_20_blocks": _S,
                "base_fee_max_gwei_20_blocks": _S,
                "blocks_sampled": _I,
                "trend": {"type": "string", "enum": ["rising", "falling", "flat"]},
                "cheapest_window_hint": _S,
                "as_of_epoch": _I,
                "note": _S,
            },
            ["chain", "latest_block", "gas_price_gwei", "base_fee_gwei", "trend", "cheapest_window_hint"],
        ),
        "output_example": {
            "chain": "base",
            "latest_block": 22104511,
            "gas_price_gwei": "0.0062",
            "base_fee_gwei": "0.0058",
            "base_fee_min_gwei_20_blocks": "0.0051",
            "base_fee_max_gwei_20_blocks": "0.0079",
            "blocks_sampled": 20,
            "trend": "flat",
            "cheapest_window_hint": "Base fee is flat across the last 20 blocks.",
            "as_of_epoch": 1761000000,
            "note": "Trend and hint describe the last ~20 blocks only.",
        },
    },
    "/v1/wallet-verdict": {
        "description": (
            "A trust verdict for one Base wallet: OFAC SDN exact-match against "
            "a dated snapshot, wallet age, activity level, and an "
            "address-poisoning scan of its recent token transfers, combined "
            "into SAFE, CAUTION, or AVOID with a 0-100 score and itemized "
            "reasons. Use this when an agent must decide whether a wallet is "
            "safe to pay or take instructions from."
        ),
        "tags": ["base", "security", "sanctions", "verdict", "agents"],
        "input_schema": _obj({"address": _S}, ["address"]),
        "input_example": {"address": "0x097f9685D1e0752bF8B02d61E5Ce9be7eA0FBA7F"},
        "output_schema": _obj(
            {
                "address": _S,
                "verdict": {"type": "string", "enum": ["SAFE", "CAUTION", "AVOID"]},
                "score": _I,
                "sanctions": {"type": "object"},
                "wallet_age_days": _IN,
                "first_activity": _S,
                "outgoing_tx_count_nonce": _IN,
                "poisoning": {"type": "object"},
                "reasons": {
                    "type": "array",
                    "items": _obj({"name": _S, "points": _I, "detail": _S}, ["name", "points", "detail"]),
                },
                "limits": _S,
            },
            ["address", "verdict", "score", "sanctions", "poisoning", "reasons"],
        ),
        "output_example": {
            "address": "0x097f9685D1e0752bF8B02d61E5Ce9be7eA0FBA7F",
            "verdict": "SAFE",
            "score": 100,
            "sanctions": {"status": "no_match", "matched": False, "snapshot_date": "2026-10-21"},
            "wallet_age_days": 352,
            "first_activity": "2025-11-02T14:03:11+00:00",
            "outgoing_tx_count_nonce": 137,
            "poisoning": {"status": "none_found", "signals": []},
            "reasons": [],
            "limits": "Sanctions matching is exact-address only against the bundled snapshot.",
        },
    },
    "/v1/pre-trade-guard": {
        "description": (
            "Pre-Trade Guard — before you pay an x402 listing, screen the "
            "payTo you are about to pay: its Verdict Index catalog history "
            "(first seen, payTo rotations, listings added or removed across "
            "the snapshots held), an OFAC SDN exact-match check, and the "
            "wallet's Base age and activity, combined into PROCEED, CAUTION, "
            "or ABORT with itemized reasons. Use this when an agent is about "
            "to pay a payTo it has never paid before."
        ),
        "tags": ["x402", "security", "sanctions", "verdict", "payments", "agents"],
        "input_schema": _obj(
            {"pay_to": _S, "amount": {"type": ["integer", "string", "null"]}, "network": _N, "resource": _N},
            ["pay_to"],
        ),
        "input_example": {
            "pay_to": "0x097f9685D1e0752bF8B02d61E5Ce9be7eA0FBA7F",
            "resource": "https://stall-row-production.up.railway.app/v1/wallet-verdict",
            "amount": 20000,
        },
        "output_schema": _obj(
            {
                "pay_to": _S,
                "resource": _N,
                "amount": {"type": ["integer", "string", "null"]},
                "network": _S,
                "verdict": {"type": "string", "enum": ["PROCEED", "CAUTION", "ABORT"]},
                "risk_score": _I,
                "unknown_legs": {"type": "array", "items": _S},
                "sanctions": {"type": "object"},
                "index": {"type": "object"},
                "wallet": {"type": "object"},
                "reasons": {
                    "type": "array",
                    "items": _obj({"name": _S, "points": _I, "detail": _S}, ["name", "points", "detail"]),
                },
                "not_checked": _S,
                "limits": _S,
            },
            ["pay_to", "verdict", "risk_score", "sanctions", "index", "wallet", "reasons"],
        ),
        "output_example": {
            "pay_to": "0x097f9685D1e0752bF8B02d61E5Ce9be7eA0FBA7F",
            "resource": "https://stall-row-production.up.railway.app/v1/wallet-verdict",
            "amount": 20000,
            "network": "eip155:8453",
            "verdict": "PROCEED",
            "risk_score": 0,
            "unknown_legs": [],
            "sanctions": {"status": "no_match", "matched": False, "snapshot_date": "2026-10-21"},
            "index": {
                "status": "ok",
                "snapshots_held": 3,
                "listed_now": 16,
                "first_seen_at": "2026-10-26T18:00:00Z",
                "rotations_in": [],
                "rotations_out": [],
            },
            "wallet": {"status": "ok", "age_days": 352, "outgoing_tx_count_nonce": 137},
            "reasons": [
                {"name": "catalog track record", "points": 0, "detail": "PayTo appears in the snapshots held with no payTo rotations."}
            ],
            "not_checked": "Operator identity and delivery quality are not checked.",
            "limits": "Listing history covers only the snapshots held.",
        },
    },
    "/v1/counterparty-report": {
        "description": (
            "Counterparty Report — one bundled report on one seller: the "
            "payTo's wallet snapshot, an OFAC SDN exact-match screen, and "
            "its Verdict Index listing history, plus a Token Verdict when "
            "you name a token, a LockSmith audit when you name a service "
            "URL, and a ListSmith grade when you name a listing URL. Legs "
            "that are not requested or cannot run are marked, never "
            "padded. Use this when an agent is about to rely on a seller "
            "it has never dealt with."
        ),
        "tags": ["x402", "security", "verdict", "sellers", "agents"],
        "input_schema": _obj(
            {
                "pay_to": _S,
                "token_address": _N,
                "chain": _S,
                "service_url": _N,
                "listing_url": _N,
                "resource": _N,
            },
            ["pay_to"],
        ),
        "input_example": {
            "pay_to": "0x097f9685D1e0752bF8B02d61E5Ce9be7eA0FBA7F",
            "service_url": "https://stall-row-production.up.railway.app/v1/wallet-verdict",
            "listing_url": "https://stall-row-production.up.railway.app/.well-known/x402",
        },
        "output_schema": _obj(
            {
                "pay_to": _S,
                "token_address": _N,
                "service_url": _N,
                "listing_url": _N,
                "generated_at": _S,
                "legs_ok": {"type": "array", "items": _S},
                "legs_failed": {"type": "array", "items": _S},
                "legs_unavailable": {"type": "array", "items": _S},
                "legs_not_requested": {"type": "array", "items": _S},
                "legs": {"type": "object"},
                "limits": _S,
            },
            ["pay_to", "generated_at", "legs_ok", "legs"],
        ),
        "output_example": {
            "pay_to": "0x097f9685D1e0752bF8B02d61E5Ce9be7eA0FBA7F",
            "token_address": None,
            "service_url": "https://stall-row-production.up.railway.app/v1/wallet-verdict",
            "listing_url": "https://stall-row-production.up.railway.app/.well-known/x402",
            "generated_at": "2026-10-27T12:00:00Z",
            "legs_ok": ["wallet", "index", "locksmith", "listsmith"],
            "legs_failed": [],
            "legs_unavailable": [],
            "legs_not_requested": ["token_verdict"],
            "legs": {"wallet": {"status": "ok"}, "locksmith": {"status": "ok", "headline": "SECURE"}},
            "limits": "Legs marked not_requested were not asked for and were not run.",
        },
    },
    "/v1/grade-my-stall": {
        "description": (
            "Grade My Stall — a seller-side report card for one x402 "
            "resource: a live unpaid probe (does it answer 402 with a "
            "parseable challenge?), the description measured against "
            "the 500-character limit, CDP listing presence in the "
            "newest catalog snapshot, Settled's record, the origin's "
            "x402scan ownership declaration, and payTo consistency "
            "across sources. Checks that cannot be performed report "
            "unverified, never a guess. Use this when you run a stall "
            "and want to know how buyers' tools see it."
        ),
        "tags": ["x402", "sellers", "listings", "verification"],
        "input_schema": _obj(
            {"resource_url": _S, "pay_to": _N},
            ["resource_url"],
        ),
        "input_example": {
            "resource_url": "https://stall-row-production.up.railway.app/v1/wallet-verdict",
            "pay_to": "0x097f9685D1e0752bF8B02d61E5Ce9be7eA0FBA7F",
        },
        "output_schema": _obj(
            {
                "resource": _S,
                "pay_to_supplied": _N,
                "checks": {"type": "object"},
                "summary": {"type": "object"},
                "overall": _S,
                "limits": _S,
            },
            ["resource", "checks", "summary", "overall"],
        ),
        "output_example": {
            "resource": "https://stall-row-production.up.railway.app/v1/wallet-verdict",
            "pay_to_supplied": "0x097f9685D1e0752bF8B02d61E5Ce9be7eA0FBA7F",
            "checks": {
                "answers_402": {"status": "ok", "detail": "answers 402 with a parseable x402 challenge"},
                "payai": {"status": "unverified", "detail": "no public catalogue read"},
            },
            "summary": {"ok": 5, "issue": 0, "not_found": 0, "unverified": 2},
            "overall": "no_issues_found",
            "limits": "Live reads at report time, plus the newest Index snapshot.",
        },
    },
    "/v1/receipt-verify": {
        "description": (
            "Receipt Verifier — a Base transaction hash in, a "
            "normalized verified receipt out: payer, payTo and "
            "amount from the USDC Transfer log, asset and network, "
            "settled status and confirmations. When the payTo is "
            "this fleet's own and the amount matches a priced route, "
            "routes at that price are listed as candidates — an "
            "amount alone never proves which route was called. "
            "Unknown transactions error honestly, unsettled. Use "
            "this when someone claims they paid and you want the "
            "chain's version. Base only."
        ),
        "tags": ["x402", "payments", "verification", "receipts"],
        "input_schema": _obj({"tx_hash": _S}, ["tx_hash"]),
        "input_example": {
            "tx_hash": "0xeabaf4f583441a52af8ba936783aa96a13d5e71e8a0bf69d9d622076bd346c75",
        },
        "output_schema": _obj(
            {
                "tx_hash": _S,
                "network": _S,
                "chain": _S,
                "payer": _N,
                "tx_sender": _N,
                "pay_to": _N,
                "amount_units": {"type": "integer"},
                "amount_usd": _S,
                "asset": _N,
                "asset_symbol": _S,
                "settled": {"type": "boolean"},
                "receipt_status": _N,
                "block_number": _IN,
                "confirmations": _IN,
                "usdc_transfers": {"type": "array", "items": {"type": "object"}},
                "fleet_route_candidates": {"type": "array", "items": {"type": "object"}},
                "limits": _S,
            },
            ["tx_hash", "network", "payer", "pay_to", "amount_units", "settled"],
        ),
        "output_example": {
            "tx_hash": "0xeabaf4f583441a52af8ba936783aa96a13d5e71e8a0bf69d9d622076bd346c75",
            "network": "eip155:8453",
            "chain": "base",
            "payer": "0xa4f183a6799F0310FcCC545B07F2DcC960223de2",
            "tx_sender": "0xe74817f4cdc15844314812b2271276e64e890fae",
            "pay_to": "0x097f9685D1e0752bF8B02d61E5Ce9be7eA0FBA7F",
            "amount_units": 1000000,
            "amount_usd": "1",
            "asset": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
            "asset_symbol": "USDC",
            "settled": True,
            "receipt_status": "0x1",
            "block_number": 28000000,
            "confirmations": 120,
            "usdc_transfers": [
                {
                    "from": "0xa4f183a6799F0310FcCC545B07F2DcC960223de2",
                    "to": "0x097f9685D1e0752bF8B02d61E5Ce9be7eA0FBA7F",
                    "amount_units": 1000000,
                }
            ],
            "fleet_route_candidates": [
                {"service": "stall-row", "route": "/v1/counterparty-report"}
            ],
            "limits": "Base only (eip155:8453).",
        },
    },
    "/v1/flagged-paytos": {
        "description": (
            "Bad-payTo Registry Feed — the currently flagged payTos, "
            "each with its evidence: every address in the bundled "
            "OFAC SDN snapshot, payTos the newest catalog snapshot "
            "pair shows rotated away from live listings, and payTos "
            "of listings that vanished between snapshots. Built "
            "from the same two sources the Pre-Trade Guard screens "
            "against. No entry without evidence; entry and evidence "
            "caps are stated, never silent. Use this when a router "
            "or guard wants the fleet's current avoid-list in one "
            "cheap call."
        ),
        "tags": ["x402", "security", "sanctions", "registry", "agents"],
        "input_schema": _obj({}, []),
        "input_example": {},
        "output_schema": _obj(
            {
                "generated_at": _S,
                "baseline_at": _N,
                "current_at": _N,
                "counts": {"type": "object"},
                "truncation": {"type": "object"},
                "index_note": _N,
                "entries": {"type": "array", "items": {"type": "object"}},
                "limits": _S,
            },
            ["generated_at", "counts", "entries"],
        ),
        "output_example": {
            "generated_at": "2026-10-27T12:00:00Z",
            "baseline_at": "2026-10-27T05:38:08Z",
            "current_at": "2026-10-27T11:39:12Z",
            "counts": {
                "ofac_sdn": 91,
                "rotated_away_events": 3,
                "vanished_events": 12,
                "flagged_paytos": 101,
                "entries_returned": 101,
            },
            "truncation": {
                "entries_capped_at": 500,
                "entries_truncated": 0,
                "evidence_examples_per_reason": 5,
            },
            "index_note": None,
            "entries": [
                {
                    "pay_to": "0x0330070fd38ec3bb94f58fa55d40368271e9e54a",
                    "reasons": ["ofac_sdn"],
                    "evidence": {
                        "ofac_sdn": {
                            "snapshot_date": "2026-10-21",
                            "snapshot_source": "https://www.treasury.gov/ofac/downloads/sdn.csv",
                            "detail": "Address appears verbatim in the bundled OFAC SDN digital-currency snapshot.",
                        }
                    },
                }
            ],
            "limits": "Flags are evidence, not verdicts.",
        },
    },
    "/v1/agent-card-verify": {
        "description": (
            "Agent-Card Verifier — an ERC-8004 agent id (resolved on "
            "Base via the registry) or an agent.json URL in; "
            "the card is fetched and checked against live reality: "
            "declared endpoints probed unpaid (402 is correct for a "
            "paid service), challenge payTos compared with the "
            "card's declared wallets, declared prices with live "
            "challenge amounts. Undeclared fields report not_checked, "
            "never a guess; an unreachable card errors honestly, "
            "unsettled. Use this when an agent's card claims more "
            "than its endpoints do."
        ),
        "tags": ["x402", "agents", "erc-8004", "verification", "identity"],
        "input_schema": _obj(
            {"agent_id": _IN, "agent_url": _N},
            [],
        ),
        "input_example": {"agent_id": 97809},
        "output_schema": _obj(
            {
                "agent_id": _IN,
                "card_url": _S,
                "source": _S,
                "card_name": _N,
                "checks": {"type": "object"},
                "summary": {"type": "object"},
                "overall": _S,
                "limits": _S,
            },
            ["card_url", "checks", "summary", "overall"],
        ),
        "output_example": {
            "agent_id": 97809,
            "card_url": "https://raw.githubusercontent.com/QuincyGB/ren-executor-metadata/main/agent.json",
            "source": "erc8004_registry",
            "card_name": "Ren",
            "checks": {
                "card_parses": {"status": "ok", "detail": "card fetched and parsed"},
                "payto_matches": {"status": "not_checked", "detail": "no probed endpoint issued a payment challenge — not checked"},
            },
            "summary": {"ok": 2, "issue": 0, "not_checked": 2},
            "overall": "no_issues_found",
            "limits": "Live reads at report time.",
        },
    },
    "/v1/tube-search": {
        "description": (
            "YouTube search results as clean JSON: title, video id, URL, "
            "channel, duration, and views for each result, scraped from the "
            "public results page with no API key. Use this when an agent "
            "needs to find a video mid-task and cannot drive a browser or "
            "hold a Google API key."
        ),
        "tags": ["search", "youtube", "video", "data", "agents"],
        "input_schema": _obj(
            {"query": _S, "max_results": {"type": "integer", "minimum": 1, "maximum": 20}},
            ["query"],
        ),
        "input_example": {"query": "base blockchain x402 tutorial", "max_results": 5},
        "output_schema": _obj(
            {
                "query": _S,
                "count": _I,
                "results": {
                    "type": "array",
                    "items": _obj(
                        {
                            "title": _S,
                            "video_id": _S,
                            "url": _S,
                            "channel": _N,
                            "duration": _N,
                            "views": _N,
                        },
                        ["title", "video_id", "url"],
                    ),
                },
            },
            ["query", "count", "results"],
        ),
        "output_example": {
            "query": "base blockchain x402 tutorial",
            "count": 1,
            "results": [
                {
                    "title": "x402 explained in 10 minutes",
                    "video_id": "dQw4w9WgXcQ",
                    "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                    "channel": "Example Channel",
                    "duration": "10:24",
                    "views": "12K views",
                }
            ],
        },
    },
    "/v1/page-to-markdown": {
        "description": (
            "Fetch one web page and return its main content as clean "
            "Markdown with title and word count, extracted server-side. "
            "Private and loopback targets are refused. Use this when an "
            "agent needs to read a page inside a workflow without a browser "
            "and without wading through navigation and boilerplate."
        ),
        "tags": ["fetch", "markdown", "web", "reading", "agents"],
        "input_schema": _obj({"url": _S}, ["url"]),
        "input_example": {"url": "https://www.x402.org/"},
        "output_schema": _obj(
            {
                "url": _S,
                "final_url": _S,
                "title": _N,
                "markdown": _S,
                "word_count": _I,
            },
            ["url", "final_url", "markdown", "word_count"],
        ),
        "output_example": {
            "url": "https://www.x402.org/",
            "final_url": "https://www.x402.org/",
            "title": "x402 — internet-native payments",
            "markdown": "# x402\n\nAn open standard for internet-native payments.",
            "word_count": 8,
        },
    },
    "/v1/repo-vitals": {
        "description": (
            "Vital signs for one GitHub repository in a single call: stars, "
            "forks, open issues, license, last push, archived flag, and a "
            "0-100 health score with a verdict line. Use this when an agent "
            "is choosing a dependency, a repo to contribute to, or a project "
            "to trust, and needs the quick read before the deep one."
        ),
        "tags": ["github", "repos", "data", "agents"],
        "input_schema": _obj({"repo": _S}, ["repo"]),
        "input_example": {"repo": "QuincyGB/token-verdict"},
        "output_schema": _obj(
            {
                "repo": _S,
                "url": _N,
                "description": _N,
                "stars": _I,
                "forks": _I,
                "open_issues": _I,
                "license": _N,
                "pushed_at": _N,
                "created_at": _N,
                "archived": _B,
                "health_score": _I,
                "health_notes": {"type": "array", "items": _S},
                "verdict": _S,
            },
            ["repo", "stars", "forks", "open_issues", "archived", "health_score", "verdict"],
        ),
        "output_example": {
            "repo": "QuincyGB/token-verdict",
            "url": "https://github.com/QuincyGB/token-verdict",
            "description": "x402 token-risk verdict service",
            "stars": 3,
            "forks": 0,
            "open_issues": 1,
            "license": "MIT",
            "pushed_at": "2026-10-21T19:11:00Z",
            "created_at": "2026-10-07T00:00:00Z",
            "archived": False,
            "health_score": 45,
            "health_notes": ["Very few stars (<10)."],
            "verdict": "Active-looking repository with a modest footprint.",
        },
    },
    "/v1/price-check": {
        "description": (
            "Pricing comps for an x402 listing, read live from the CDP Bazaar "
            "public catalog: how many resources match your keywords, their "
            "price distribution, the closest comparables, and a recommended "
            "listing price with its rationale. Use this when you operate an "
            "x402 route and are setting or changing its price."
        ),
        "tags": ["x402", "bazaar", "pricing", "sellers", "agents"],
        "input_schema": _obj({"keywords": _S, "description": _S}, ["keywords"]),
        "input_example": {"keywords": "token risk verdict"},
        "output_schema": _obj(
            {
                "keywords": _S,
                "catalog_status": _S,
                "matches_found": _I,
                "price_distribution": {
                    "type": ["object", "null"],
                    "properties": {
                        "min_usd": {"type": "number"},
                        "median_usd": {"type": "number"},
                        "p90_usd": {"type": "number"},
                        "max_usd": {"type": "number"},
                    },
                },
                "comparables": {
                    "type": "array",
                    "items": _obj(
                        {"resource": _N, "description": _S, "price_units": _I, "price_usd": {"type": "number"}},
                        ["description", "price_units", "price_usd"],
                    ),
                },
                "recommended_price_usd": {"type": ["number", "null"]},
                "rationale": _S,
            },
            ["keywords", "catalog_status", "matches_found", "comparables", "rationale"],
        ),
        "output_example": {
            "keywords": "token risk verdict",
            "catalog_status": "ok",
            "matches_found": 3,
            "price_distribution": {"min_usd": 0.01, "median_usd": 0.02, "p90_usd": 0.05, "max_usd": 0.05},
            "comparables": [
                {"resource": "https://example.com/v1/verdict", "description": "Token verdict", "price_units": 20000, "price_usd": 0.02}
            ],
            "recommended_price_usd": 0.02,
            "rationale": "Median of 3 cataloged match(es).",
        },
    },
    "/v1/card-smith": {
        "description": (
            "Generate or grade an agent card (the /.well-known/agent-card.json "
            "an agent publishes for A2A and AgentWorld-style registries). "
            "Generate builds a structurally valid card from your fields; grade "
            "scores a supplied card and itemizes its defects. Use this when "
            "you are registering an agent and want the card right the first "
            "time."
        ),
        "tags": ["agents", "a2a", "agent-card", "identity", "sellers"],
        "input_schema": _obj(
            {
                "mode": {"type": "string", "enum": ["generate", "grade"]},
                "name": _S,
                "description": _S,
                "skills": {"type": "array"},
                "card": {"type": "object"},
            },
            ["mode"],
        ),
        "input_example": {"mode": "generate", "name": "Ren", "description": "Research agent", "skills": ["research"]},
        "output_schema": _obj(
            {
                "mode": _S,
                "card": {"type": ["object", "null"]},
                "validation": _obj(
                    {
                        "valid_structure": _B,
                        "score": _I,
                        "defects": {
                            "type": "array",
                            "items": _obj(
                                {"name": _S, "severity": _S, "detail": _S},
                                ["name", "severity", "detail"],
                            ),
                        },
                    },
                    ["valid_structure", "score", "defects"],
                ),
            },
            ["mode", "validation"],
        ),
        "output_example": {
            "mode": "generate",
            "card": {"name": "Ren", "description": "Research agent", "url": "", "version": "1.0.0", "skills": []},
            "validation": {"valid_structure": False, "score": 55, "defects": [{"name": "missing url", "severity": "major", "detail": "Top-level 'url' is absent or empty."}]},
        },
    },
    "/v1/job-scout": {
        "description": (
            "A digest of currently open agent jobs from the marketplaces we "
            "sweep daily, filtered by the capabilities you name and sorted by "
            "budget: platform, budget, capability tags, deadline, and source "
            "snapshot time on every row, with a stale flag when the snapshot "
            "ages past 24 hours. Use this when your agent is looking for "
            "paid work."
        ),
        "tags": ["jobs", "bounties", "agents", "work", "digest"],
        "input_schema": _obj(
            {"capabilities": {"type": "array", "items": _S}, "limit": _I},
            [],
        ),
        "input_example": {"capabilities": ["research"], "limit": 5},
        "output_schema": _obj(
            {
                "snapshot_fetched_at": _N,
                "snapshot_source": _N,
                "data_stale": _B,
                "snapshot_age_hours": {"type": ["number", "null"]},
                "count": _I,
                "jobs": {
                    "type": "array",
                    "items": _obj(
                        {
                            "title": _S,
                            "platform": _S,
                            "budget_usd": {"type": ["number", "null"]},
                            "capabilities": {"type": "array", "items": _S},
                            "url": _S,
                        },
                        ["title", "platform", "url"],
                    ),
                },
                "note": _S,
            },
            ["data_stale", "count", "jobs", "note"],
        ),
        "output_example": {
            "snapshot_fetched_at": "2026-10-21T19:49:00Z",
            "snapshot_source": "Ren's Synmerco sweep",
            "data_stale": False,
            "snapshot_age_hours": 2.0,
            "count": 1,
            "jobs": [
                {
                    "title": "FDIC bank health snapshot, 10 Florida banks",
                    "platform": "Synmerco",
                    "budget_usd": 12.0,
                    "capabilities": ["research", "data-analysis"],
                    "url": "https://synmerco.com",
                    "fetched_at": "2026-10-21T19:49:00Z",
                    "expires_at": "2026-10-23T16:15:00Z",
                    "status": "open",
                }
            ],
            "note": "Snapshot data from our own platform sweeps.",
        },
    },
    "/v1/recheck": {
        "description": (
            "Probe one x402 resource or page WITHOUT paying it: BASELINE / "
            "UNCHANGED / CHANGED with a diff (price, asset, payTo, schema, "
            "body) vs the last check. Use this when a scheduled agent must "
            "know what changed first. Watch and pack state persist across "
            "redeploys on the service volume. Checking the same endpoint "
            "on a schedule? Buy the pack instead — POST /v1/recheck/pack "
            "is $1 for 250 checks (90 days) and this route spends pack "
            "credits when you send pack_id, so a loop makes one payment, "
            "not hundreds."
        ),
        "tags": ["monitoring", "x402", "change-detection", "diff", "agents"],
        "input_schema": _obj({"url": _S, "watch_id": _S, "pack_id": _S}, ["url"]),
        "input_example": {
            "url": "https://token-verdict-production.up.railway.app/v1/verdict",
            "watch_id": "token-verdict-main",
        },
        "output_schema": _obj(
            {
                "watch_id": _S,
                "url": _S,
                "kind": {"type": "string", "enum": ["x402", "web"]},
                "status": {
                    "type": "string",
                    "enum": ["BASELINE", "UNCHANGED", "CHANGED"],
                },
                "changes": {
                    "type": "array",
                    "items": _obj(
                        {
                            "field": _S,
                            "before": {"type": ["string", "integer", "null"]},
                            "after": {"type": ["string", "integer", "null"]},
                        },
                        ["field", "before", "after"],
                    ),
                },
                "current": {"type": "object"},
                "checked_at": _S,
                "summary": _S,
            },
            ["watch_id", "url", "kind", "status", "changes", "current", "checked_at", "summary"],
        ),
        "output_example": {
            "watch_id": "token-verdict-main",
            "url": "https://token-verdict-production.up.railway.app/v1/verdict",
            "kind": "x402",
            "status": "CHANGED",
            "changes": [{"field": "amount", "before": "20000", "after": "25000"}],
            "current": {
                "status_code": 402,
                "amount": "25000",
                "asset": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
                "network": "eip155:8453",
                "payTo": "0x097f9685D1e0752bF8B02d61E5Ce9be7eA0FBA7F",
                "description_hash": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                "schema_hash": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            },
            "checked_at": "2026-10-24T16:00:00Z",
            "summary": "Changed since the previous check: amount.",
        },
    },
    "/v1/index/changes": {
        "description": (
            "Verdict Index — the CDP Bazaar catalog changelog: the diff "
            "between our two newest full-catalog snapshots (price, asset, "
            "network, payTo, description, service name), with added and "
            "removed resources counted. Snapshots refresh about every 6 "
            "hours; until two exist this returns 502 and charges nothing. "
            "Filter by resource, payTo, service name, or network — every "
            "chain covered, Solana included; the summary breaks counts "
            "down by network. Use this when a router needs what changed "
            "since its last sync."
        ),
        "tags": ["index", "x402", "changelog", "catalog", "monitoring", "agents"],
        "input_schema": _obj(
            {"resource_contains": _S, "pay_to": _S, "service_name": _S, "network": _S, "limit": _I},
            [],
        ),
        "input_example": {"resource_contains": "token-verdict", "limit": 50},
        "output_schema": _obj(
            {
                "baseline_at": _S,
                "current_at": _S,
                "generated_at": _S,
                "summary": _obj(
                    {
                        "resources_before": _I,
                        "resources_after": _I,
                        "field_changes": _I,
                        "added": _I,
                        "removed": _I,
                    },
                    ["resources_before", "resources_after", "field_changes", "added", "removed"],
                ),
                "events_returned": _I,
                "events": {
                    "type": "array",
                    "items": _obj(
                        {
                            "resource": _S,
                            "kind": {"type": "string", "enum": ["field_changed", "added", "removed"]},
                            "field": _N,
                            "before": {"type": ["string", "null"]},
                            "after": {"type": ["string", "null"]},
                        },
                        ["resource", "kind"],
                    ),
                },
            },
            ["baseline_at", "current_at", "summary", "events"],
        ),
        "output_example": {
            "baseline_at": "2026-10-26T18:00:00Z",
            "current_at": "2026-10-27T00:00:00Z",
            "generated_at": "2026-10-27T00:05:00Z",
            "summary": {
                "resources_before": 78127,
                "resources_after": 78142,
                "field_changes": 3,
                "added": 412,
                "removed": 397,
            },
            "events_returned": 1,
            "events": [
                {
                    "resource": "https://token-verdict-production.up.railway.app/v1/verdict",
                    "kind": "field_changed",
                    "field": "description",
                    "before": "old copy",
                    "after": "new copy",
                }
            ],
        },
    },
    "/v1/orchestrate": {
        "description": (
            "One combined fleet report for $0.75: Token Verdict's "
            "verdict on a token, RouteVerdict's delivery check and "
            "LockSmith's security audit summary on a service URL, and "
            "ListSmith's grade on a listing URL — four fleet services "
            "in one call. A failed leg is marked in the report, not "
            "hidden; only a total failure returns 502 and charges "
            "nothing. Use this when an agent is about to trust a "
            "token and a stall in the same workflow and wants one "
            "receipt instead of four payments."
        ),
        "tags": ["bundle", "x402", "verdict", "audit", "agents", "fleet"],
        "input_schema": _obj(
            {"address": _S, "chain": _S, "service_url": _S, "listing_url": _S},
            ["address", "service_url", "listing_url"],
        ),
        "input_example": {
            "address": "0x940181a94A35A4569E4529A3CDfB74e38FD98631",
            "chain": "base",
            "service_url": "https://token-verdict-production.up.railway.app/v1/verdict",
            "listing_url": "https://token-verdict-production.up.railway.app/.well-known/x402",
        },
        "output_schema": _obj(
            {
                "token": _obj({"address": _S, "chain": _S}, ["address", "chain"]),
                "service_url": _S,
                "listing_url": _S,
                "legs_ok": {"type": "array", "items": _S},
                "legs_failed": {"type": "array", "items": _S},
                "legs": {
                    "type": "object",
                    "additionalProperties": _obj(
                        {"status": _S, "headline": _N, "error": _N},
                        ["status"],
                    ),
                },
            },
            ["token", "service_url", "listing_url", "legs_ok", "legs_failed", "legs"],
        ),
        "output_example": {
            "token": {"address": "0x9401\u2026", "chain": "base"},
            "service_url": "https://example-stall.app/v1/call",
            "listing_url": "https://example-stall.app/.well-known/x402",
            "legs_ok": ["token_verdict", "route_verdict", "locksmith", "listsmith"],
            "legs_failed": [],
            "legs": {
                "token_verdict": {"status": "ok", "headline": "SOLID (risk 12.0)"},
                "locksmith": {"status": "ok", "headline": "SECURE"},
            },
        },
    },
    "/v1/recheck/pack": {
        "description": (
            "Recheck watch pack — the default for monitoring loops: one "
            "$1.00 payment buys 250 change-checks for ONE endpoint "
            "($0.004 per check instead of $0.005), good for 90 days. "
            "Returns an unguessable pack id — spend credits via POST "
            "/v1/recheck (body pack_id or X-Recheck-Pack header); read "
            "the balance free at POST /v1/recheck/pack-balance, and an "
            "exhausted pack returns 402 rather than charging per call. "
            "Use this when anything checks the same endpoint more than "
            "~3 times a week."
        ),
        "tags": ["monitoring", "x402", "change-detection", "prepaid", "agents"],
        "input_schema": _obj({"url": _S}, ["url"]),
        "input_example": {
            "url": "https://token-verdict-production.up.railway.app/v1/verdict",
        },
        # Generated from a real local run of the buy handler (payment
        # identity stubbed with a fixed authorization nonce, the way
        # tests/test_recheck_pack.py drives it) — pinned ≤1,450 bytes
        # serialized by test_discovery.py (Settled sample-size cap).
        "output_schema": _obj(
            {
                "pack_id": _S,
                "url": _S,
                "credits_total": _I,
                "credits_remaining": _I,
                "created_at": _S,
                "expires_at": _S,
                "expired": _B,
                "expiry_days": _I,
                "price_units": _I,
                "note": _S,
            },
            ["pack_id", "url", "credits_total", "credits_remaining", "expires_at"],
        ),
        "output_example": {
            "pack_id": "pack_9c73fa7ea40a6411b6517bd8cb3465a6",
            "url": "https://token-verdict-production.up.railway.app/v1/verdict",
            "credits_total": 250,
            "credits_remaining": 250,
            "created_at": "2026-10-25T05:36:48Z",
            "expires_at": "2027-01-23T05:36:48Z",
            "expired": False,
            "expiry_days": 90,
            "price_units": 1000000,
            "note": "Spend credits with POST /v1/recheck: send this pack_id in the body or the X-Recheck-Pack header. Read the balance free at POST /v1/recheck/pack-balance.",
        },
    },
    "/v1/fleet-check": {
        "description": (
            "Fleet Check — one health sweep of your whole x402 fleet: "
            "name resource URLs and/or origins (expanded from their "
            "own /.well-known/x402) and get a per-route table — alive, "
            "status, whether the 402 challenge decodes, each accept's "
            "network/asset/payTo/amount, an OK / DEGRADED / DOWN "
            "verdict naming the defect, and a grade per origin. "
            "Probes are unpaid only — this route never pays any route "
            "it checks. Use this when you run more than one x402 "
            "stall and want one honest answer about all of them."
        ),
        "tags": ["x402", "monitoring", "health-check", "sellers", "agents"],
        "input_schema": _obj(
            {
                "resources": {"type": "array", "items": _S},
                "origins": {"type": "array", "items": _S},
            },
            [],
        ),
        "input_example": {
            "origins": ["https://stall-row-production.up.railway.app"],
        },
        "output_schema": _obj(
            {
                "checked_at": _S,
                "resources": {
                    "type": "array",
                    "items": _obj(
                        {
                            "url": _S,
                            "origin": _S,
                            "alive": _B,
                            "http_status": {"type": ["integer", "null"]},
                            "challenge_ok": _B,
                            "accepts": {
                                "type": "array",
                                "items": _obj(
                                    {
                                        "scheme": _N,
                                        "network": _N,
                                        "asset": _N,
                                        "payTo": _N,
                                        "amount": _N,
                                    },
                                    [],
                                ),
                            },
                            "verdict": _S,
                            "defects": {
                                "type": "array",
                                "items": _obj(
                                    {"code": _S, "detail": _S},
                                    ["code", "detail"],
                                ),
                            },
                        },
                        ["url", "origin", "alive", "verdict"],
                    ),
                },
                "origins": {
                    "type": "array",
                    "items": _obj(
                        {
                            "origin": _S,
                            "resources": _I,
                            "ok": _I,
                            "degraded": _I,
                            "down": _I,
                            "score": {"type": ["integer", "null"]},
                            "verdict": _S,
                        },
                        ["origin", "resources", "verdict"],
                    ),
                },
                "summary": _obj(
                    {
                        "resources": _I,
                        "ok": _I,
                        "degraded": _I,
                        "down": _I,
                        "origins": _I,
                        "truncated": _I,
                    },
                    ["resources", "ok", "degraded", "down"],
                ),
                "limits": _S,
            },
            ["checked_at", "resources", "origins", "summary"],
        ),
        # Generated from a real local run of the sweep (MockTransport
        # playing a one-route fixture fleet) — pinned ≤1,450 bytes
        # serialized by test_discovery.py (Settled sample-size cap).
        "output_example": {
            "checked_at": "2026-10-28T01:37:53Z",
            "resources": [
                {
                    "url": "https://93.184.216.34/v1/verdict",
                    "origin": "https://93.184.216.34",
                    "alive": True,
                    "http_status": 402,
                    "challenge_ok": True,
                    "accepts": [
                        {
                            "scheme": "exact",
                            "network": "eip155:8453",
                            "asset": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
                            "payTo": "0x097f9685D1e0752bF8B02d61E5Ce9be7eA0FBA7F",
                            "amount": "20000",
                        }
                    ],
                    "verdict": "OK",
                    "defects": [],
                }
            ],
            "origins": [
                {
                    "origin": "https://93.184.216.34",
                    "resources": 1,
                    "ok": 1,
                    "degraded": 0,
                    "down": 0,
                    "score": 100,
                    "verdict": "TRUSTED",
                }
            ],
            "summary": {
                "resources": 1,
                "ok": 1,
                "degraded": 0,
                "down": 0,
                "origins": 1,
                "truncated": 0,
            },
            "limits": "Unpaid probes at sweep time: liveness, HTTP status, and the 402 challenge a buyer would meet. Declared-vs-live comparisons use the origin's own /.well-known/x402 when it publishes one; an origin that publishes none is checked live-only, never guessed about. This checker never pays, signs, or settles any route it probes.",
        },
    },
    "/v1/fleet-check/pack": {
        "description": (
            "Fleet Check pack — the standing form of Fleet Check: one "
            "$5.00 payment buys 100 sweep credits for ONE fixed fleet "
            "definition (resources and/or origins), good for 90 days. "
            "Sweeps run on your interval or on demand via POST "
            "/v1/fleet-check/run — one credit per sweep, never per "
            "route — diff against the last sweep, and POST failures "
            "and recoveries to your webhook (heartbeats optional); "
            "the latest table is free at POST /v1/fleet-check/status. "
            "Use this when your stalls should be watched continuously."
        ),
        "tags": ["x402", "monitoring", "prepaid", "health-check", "agents"],
        "input_schema": _obj(
            {
                "resources": {"type": "array", "items": _S},
                "origins": {"type": "array", "items": _S},
                "webhook_url": _N,
                "email": _N,
                "heartbeat": _B,
                "interval_s": _I,
            },
            [],
        ),
        "input_example": {
            "origins": ["https://stall-row-production.up.railway.app"],
            "interval_s": 3600,
        },
        # Generated from a real local run of the buy handler (payment
        # identity stubbed with a fixed authorization nonce, the way
        # tests/test_fleetcheck.py drives it) — pinned ≤1,450 bytes
        # serialized by test_discovery.py (Settled sample-size cap).
        "output_schema": _obj(
            {
                "pack_id": _S,
                "definition": _obj(
                    {
                        "resources": {"type": "array", "items": _S},
                        "origins": {"type": "array", "items": _S},
                    },
                    ["resources", "origins"],
                ),
                "webhook_url": _N,
                "email": _N,
                "heartbeat": _B,
                "interval_s": _I,
                "credits_total": _I,
                "credits_remaining": _I,
                "created_at": _S,
                "expires_at": _S,
                "expired": _B,
                "last_run_at": _N,
                "expiry_days": _I,
                "price_units": _I,
                "note": _S,
            },
            ["pack_id", "definition", "credits_total", "credits_remaining", "expires_at"],
        ),
        "output_example": {
            "pack_id": "fcpack_6029769f56d21efaf8dab279c312d625",
            "definition": {
                "resources": [],
                "origins": ["https://stall-row-production.up.railway.app"],
            },
            "webhook_url": None,
            "email": None,
            "heartbeat": False,
            "interval_s": 3600,
            "credits_total": 100,
            "credits_remaining": 100,
            "created_at": "2026-10-28T01:38:32Z",
            "expires_at": "2027-01-26T01:38:32Z",
            "expired": False,
            "last_run_at": None,
            "expiry_days": 90,
            "price_units": 5000000,
            "note": "Sweeps of this fixed fleet definition run automatically on the pack interval and on demand via POST /v1/fleet-check/run — one credit per sweep, never per route. Read the latest table free at POST /v1/fleet-check/status.",
        },
    },
    "/v1/fleet-pass": {
        "description": (
            "Fleet Pass — one prepaid balance for the whole fleet: one "
            "$5.00 payment buys a $5.00 balance that spends on any paid "
            "route across Token Verdict, RouteVerdict, ListSmith, "
            "StallRow and LockSmith, each call debited at that route's "
            "listed price (90 days). Send the pass id as the "
            "X-Fleet-Pass header; read the balance free at POST "
            "/v1/fleet-pass/balance. Use this when a loop calls more "
            "than one fleet service and wants one budget, not a "
            "payment per call."
        ),
        "tags": ["prepaid", "x402", "budget", "agents", "fleet"],
        "input_schema": _obj({}, []),
        "input_example": {},
        "output_schema": _obj(
            {
                "pass_id": _S,
                "balance_units": _I,
                "balance_usd": {"type": "number"},
                "total_units": _I,
                "total_usd": {"type": "number"},
                "created_at": _S,
                "expires_at": _S,
                "expired": _B,
                "expiry_days": _I,
                "price_units": _I,
                "note": _S,
            },
            ["pass_id", "balance_units", "expires_at"],
        ),
        "output_example": {
            "pass_id": "fpass_9c73fa7ea40a6411b6517bd8cb3465a6b3",
            "balance_units": 5000000,
            "balance_usd": 5.0,
            "total_units": 5000000,
            "total_usd": 5.0,
            "created_at": "2026-10-26T20:00:00Z",
            "expires_at": "2027-01-24T20:00:00Z",
            "expired": False,
            "expiry_days": 90,
            "price_units": 5000000,
            "note": "Spend with the X-Fleet-Pass header on any fleet route. Read the balance free at POST /v1/fleet-pass/balance.",
        },
    },
    "/v1/fleet-pass-20": {
        "description": (
            "Fleet Pass v2 — the $20 working pass for agent "
            "frameworks: one $20.00 payment buys a $20.00 prepaid "
            "balance that spends on any paid route across Token "
            "Verdict, RouteVerdict, ListSmith, StallRow and "
            "LockSmith, each call debited at that route's listed "
            "price — no holder discounts (90 days). Send the pass id "
            "as the X-Fleet-Pass header; read the balance free at "
            "POST /v1/fleet-pass/balance. Use this when a framework "
            "loop calls the fleet often enough that a $5 pass would "
            "run dry mid-run."
        ),
        "tags": ["prepaid", "x402", "budget", "agents", "fleet", "frameworks"],
        "input_schema": _obj({}, []),
        "input_example": {},
        "output_schema": _obj(
            {
                "pass_id": _S,
                "balance_units": _I,
                "balance_usd": {"type": "number"},
                "total_units": _I,
                "total_usd": {"type": "number"},
                "created_at": _S,
                "expires_at": _S,
                "expired": _B,
                "expiry_days": _I,
                "price_units": _I,
                "note": _S,
            },
            ["pass_id", "balance_units", "expires_at"],
        ),
        "output_example": {
            "pass_id": "fpass_9c73fa7ea40a6411b6517bd8cb3465a6b3",
            "balance_units": 20000000,
            "balance_usd": 20.0,
            "total_units": 20000000,
            "total_usd": 20.0,
            "created_at": "2026-10-27T16:00:00Z",
            "expires_at": "2027-01-25T16:00:00Z",
            "expired": False,
            "expiry_days": 90,
            "price_units": 20000000,
            "note": "Spend with the X-Fleet-Pass header on any fleet route; each call debits that route's listed price. Read the balance free at POST /v1/fleet-pass/balance.",
        },
    },
}

for _path, _r in ROUTES.items():
    assert len(_r["description"]) < 500, f"{_path} description too long: {len(_r['description'])}"
    assert "Use this when" in _r["description"] or "Use this when" in _r["description"], _path


def route_extension(path: str) -> dict:
    """Canonical v2 Bazaar discovery extension for one route (same shape
    the sibling services ship — `info` carries values, `schema` is the
    JSON Schema OF the info object)."""
    r = ROUTES[path]
    input_schema = r["input_schema"]
    output_schema = r["output_schema"]
    return {
        "info": {
            "input": {
                "type": "http",
                "method": "POST",
                "bodyType": "json",
                "body": r["input_example"],
            },
            "output": {
                "type": "json",
                "example": r["output_example"],
                "schema": output_schema,
            },
        },
        "schema": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": {
                "input": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string", "const": "http"},
                        "method": {"type": "string", "enum": ["POST", "PUT", "PATCH"]},
                        "bodyType": {"type": "string", "enum": ["json", "form-data", "text"]},
                        "body": input_schema,
                    },
                    "required": ["type", "method", "bodyType", "body"],
                    "additionalProperties": False,
                },
                "output": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string"},
                        "example": output_schema,
                        "schema": {"type": "object"},
                    },
                    "required": ["type"],
                },
            },
            "required": ["input"],
        },
    }


def _price_str(path: str, settings: Settings) -> str:
    return settings.prices.get(path) or units_to_price(PRICE_UNITS[path])


def x402_manifest(settings: Settings, base_url: str) -> dict:
    def accepts(path: str) -> list[dict]:
        out = [
            {
                "scheme": "exact",
                "network": settings.network,
                "amount": str(PRICE_UNITS[path]),
                "asset": USDC_ASSET,
                "payTo": settings.pay_to,
                "maxTimeoutSeconds": 300,
            }
        ]
        # The Fleet Check routes also accept Solana USDC (same USD
        # price, 6-decimal smallest units) — the manifest mirrors the
        # live 402 challenges exactly, so the second accept is here
        # too. An accept, not a resource: the count does not move.
        if path in SOLANA_ACCEPT_PATHS:
            out.append(
                {
                    "scheme": "exact",
                    "network": settings.solana_network,
                    "amount": str(PRICE_UNITS[path]),
                    "asset": settings.solana_usdc_mint,
                    "payTo": settings.solana_pay_to,
                    "maxTimeoutSeconds": 300,
                }
            )
        return out

    resources = []
    for path, r in ROUTES.items():
        resources.append(
            {
                "resource": f"{base_url}{path}",
                "method": "POST",
                "price": _price_str(path, settings),
                "scheme": "exact",
                "mimeType": "application/json",
                "description": r["description"],
                "tags": r["tags"],
                "accepts": accepts(path),
                "inputSchema": r["input_schema"],
                "outputSchema": r["output_schema"],
            }
        )
    resources.append(
        {
            "resource": f"{base_url}/quote",
            "method": "GET",
            "price": "$0.00",
            "description": "Free price quote for every route on the row",
        }
    )
    return {
        "x402Version": 2,
        "service": settings.service_name,
        "description": (
            "A row of small x402 stalls in one service: Base chain "
            "reads (wallet snapshot, allowance audit, transaction decoder, "
            "gas oracle), a wallet trust verdict, fetch tools (YouTube "
            "search, page-to-Markdown, GitHub repo vitals), seller tools "
            "(Bazaar price-check, agent-card smith), a digest of open "
            "agent jobs, and scheduled change detection for x402 "
            "resources and web pages, with prepaid check packs. Use this when an agent needs one cheap, honest "
            "fact mid-task and cannot run the source itself."
        ),
        "network": settings.network,
        "payTo": settings.pay_to,
        "ownershipProofs": OWNERSHIP_PROOFS,
        # The nudge inbox: this stall accepts signed fleet-health
        # nudges (app/services/nudge.py; spec in x402-loop-kits).
        # A top-level extension, NOT a resource — inbound mail is
        # free and the priced route count does not move.
        "extensions": {"nudge": nudge_extension(base_url)},
        "resources": resources,
    }


def skill_md(settings: Settings, base_url: str) -> str:
    lines = [
        f"# {settings.service_name} — a row of x402 micro-services",
        "",
        f"{len(ROUTES)} paid endpoints in one deployment. No API key; payment is "
        "the authentication (x402 v2, exact scheme, USDC on Base). Every "
        "route states its data sources and marks fields it cannot supply "
        "as unknown — nothing is fabricated, and an upstream failure "
        "returns 502 so the payment does not settle.",
        "",
        "Recheck packs: buy POST /v1/recheck/pack once ($1.00 = 250 "
        "checks on one endpoint URL, 90-day expiry), then call POST "
        "/v1/recheck with the pack id in the body (pack_id) or the "
        "X-Recheck-Pack header to spend credits instead of paying per "
        "call. Check a pack's balance free at POST "
        "/v1/recheck/pack-balance.",
        "",
        "Fleet Pass: buy POST /v1/fleet-pass once ($5.00 = a $5.00 "
        "USD balance, 90-day expiry) and spend it on ANY paid route "
        "across all five fleet services (Token Verdict, RouteVerdict, "
        "ListSmith, StallRow, LockSmith) by sending the pass id as "
        "the X-Fleet-Pass header — each call debits that route's "
        "listed price. Check the balance free at POST "
        "/v1/fleet-pass/balance.",
        "",
        "Webhook Watch: register POST /v1/watch/register (free) with "
        "a funded recheck pack or Fleet Pass and a webhook URL — the "
        "service rechecks on your interval and POSTs the change to "
        "your webhook on BASELINE/CHANGED. Run one check now via POST "
        "/v1/watch/run; read state via POST /v1/watch/status.",
        "",
        "Rotation Alerts: register POST /v1/rotation-alerts/register "
        "(free) with a payTo and/or a resource URL, a webhook, and a "
        "Fleet Pass — each new Verdict Index catalog snapshot (about "
        "every 6 hours) is compared against the previous one, and "
        "events touching your target (payTo rotation, price change, "
        "vanishing, new listing) are POSTed to your webhook. The "
        "first evaluation is a free silent baseline; each later "
        "evaluation debits $0.005 from the pass. Read state via POST "
        "/v1/rotation-alerts/status.",
        "",
        "Router Watchlist: register POST /v1/watchlist/register "
        "(free) with a webhook and a Fleet Pass — each new catalog "
        "snapshot is diffed restricted to the top-100 resources by "
        "30d calls (top_n configurable to 500), and entries, exits, "
        "payTo rotations, and price changes among members are POSTed "
        "to your webhook. Same funding shape as Rotation Alerts: "
        "free silent baseline first, then $0.005 per evaluation from "
        "the pass. Read state via POST /v1/watchlist/status.",
        "",
        "Index Subscription: register POST /v1/index/subscribe "
        "(free) with the same filters POST /v1/index/changes accepts "
        "(resource_contains, pay_to, service_name, network), a "
        "webhook, and a Fleet Pass — each new catalog snapshot's "
        "filtered diff (empty diffs included, as the feed's "
        "heartbeat) is POSTed to your webhook. The first evaluation "
        "is a free silent baseline; each later evaluation debits "
        "$0.10 from the pass — the listed price of one "
        "/v1/index/changes call. Run one now via POST "
        "/v1/index/subscription/run; read state via POST "
        "/v1/index/subscription/status. A $20 Fleet Pass v2 (POST "
        "/v1/fleet-pass-20, same ledger and 90-day expiry, debits at "
        "listed prices) funds longer subscriptions.",
        "",
        "Fleet Check: POST /v1/fleet-check ($0.10) sweeps YOUR whole "
        "fleet in one call — name resource URLs and/or origins "
        "(expanded from their /.well-known/x402) and get a per-route "
        "health table (alive, challenge decodes, accept summary, "
        "OK / DEGRADED / DOWN with the defect named) plus a grade "
        "per origin. Probes are unpaid only; the checker never pays "
        "a route it checks. The standing form is the pack: POST "
        "/v1/fleet-check/pack ($5.00 = 100 sweeps of one fixed fleet "
        "definition, 90 days) — sweeps run on your interval or via "
        "POST /v1/fleet-check/run, diff against the last sweep, and "
        "push failures/recoveries to your webhook; read the latest "
        "table via POST /v1/fleet-check/status.",
        "",
        "## Paid endpoints",
        "",
    ]
    for path, r in ROUTES.items():
        lines.append(f"### `POST {base_url}{path}` — {_price_str(path, settings)} USDC")
        lines.append("")
        lines.append(r["description"])
        lines.append("")
        lines.append(f"Input example: `{r['input_example']}`")
        lines.append("")
    lines += [
        "## Free endpoints",
        "",
        f"- `GET {base_url}/quote` — every route's price, network, payTo",
        f"- `GET {base_url}/health` — liveness",
        f"- `GET {base_url}/.well-known/x402` — machine-readable manifest",
        f"- `POST {base_url}/v1/recheck/pack-balance` — a pack's credits + expiry (pack id required)",
    ]
    return "\n".join(lines) + "\n"


def llms_txt(settings: Settings, base_url: str) -> str:
    lines = [
        f"# {settings.service_name}",
        "",
        f"A row of {len(ROUTES)} paid x402 micro-services. Network {settings.network}, x402 v2.",
        "",
        "## Endpoints",
        "",
    ]
    for path in ROUTES:
        lines.append(f"- POST {base_url}{path} — {_price_str(path, settings)} USDC")
        if path == "/v1/recheck/pack":
            lines += [
                "Monitoring loop? The pack is the default: $1.00 = 250 checks on one",
                "endpoint for 90 days ($0.004/check). Spend with pack_id on",
                "POST /v1/recheck; check the balance free at",
                "POST /v1/recheck/pack-balance. Exhausted packs return 402 — they",
                "never fall back to per-call billing. Renewal is a new pack purchase.",
            ]
    lines += [
        f"- GET {base_url}/quote — free price quote",
        f"- GET {base_url}/health — free liveness check",
        f"- GET {base_url}/.well-known/x402 — manifest",
        f"- POST {base_url}/v1/recheck/pack-balance — free pack balance (pack id required)",
    ]
    return "\n".join(lines) + "\n"
