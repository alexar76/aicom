"""Agent-discovery surfaces: x402 manifest, skill.md, llms.txt.

Indexers (x402scan, Bazaar, agentic.market) read these alongside the
live 402 responses, so they must stay consistent with main.py pricing.
RouteVerdict practices what it sells: the output schema below types
EVERY field of the check response — the hollow {"type", "example"}
outputs this service grades other endpoints down for are not shipped
here. A test validates the shipped example against the schema.
"""

from __future__ import annotations

from .config import Settings
from .nudge import nudge_extension


# x402 v2 "exact"-scheme asset for USDC on Base mainnet (6 decimals) — the
# real ERC-20 contract address, matching the asset the x402 SDK puts in
# the live 402 payment-required challenge. The manifest must mirror the
# challenge exactly or directory validators reject the mismatch.
USDC_ASSET = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"

# x402scan ownership proof: an EIP-191 personal_sign of this service's bare
# origin URL ("https://route-verdict-production.up.railway.app") by the payTo
# wallet, signed by the owner on 2026-10-24. Published in the manifest below
# and in the OpenAPI x-discovery / x-agentcash-provenance root keys (see
# main.py) so x402scan can verify control of the payment address. This is
# publish-and-verify: the proofs must stay published permanently — removing
# them un-verifies the x402scan listing. DO NOT REMOVE.
OWNERSHIP_PROOFS = [
    "0x8c2ed7029c8144956320b45dc4deb1ad0eccbd23cb7ee02ce0851b8ebea592386af46d9687b85f62424f96374763d3419b48a3107f0a54f4c70c36ba19ba518c1c"
]


def _price_to_units(price_usdc: str) -> str:
    """'$0.05' -> '50000' (USDC smallest units, 6 decimals)."""
    return str(int(round(float(price_usdc.replace("$", "").strip()) * 1_000_000)))


# --- Bazaar discovery schemas -------------------------------------------------

CHECK_INPUT_SCHEMA = {
    "type": "object",
    "required": ["resource_url"],
    "properties": {
        "resource_url": {
            "type": "string",
            "description": "Full URL of the x402 resource to audit, e.g. https://service.example.com/v1/endpoint",
        },
    },
}

_REASON_ITEM = {
    "type": "object",
    "required": ["name", "deduction", "detail"],
    "properties": {
        "name": {"type": "string"},
        "deduction": {"type": "integer", "minimum": 0},
        "detail": {"type": "string"},
    },
}

_DEDUCTION_ITEM = {
    "type": "object",
    "required": ["name", "points", "detail"],
    "properties": {
        "name": {"type": "string"},
        "points": {"type": "integer", "minimum": 0},
        "detail": {"type": "string"},
    },
}

_PRESENCE = {
    "type": "object",
    "required": ["status", "unique_payers_30d", "total_calls_30d", "last_called_at", "detail"],
    "properties": {
        "status": {"type": "string", "enum": ["listed", "not_listed", "unknown"]},
        "unique_payers_30d": {"type": ["integer", "null"]},
        "total_calls_30d": {"type": ["integer", "null"]},
        "last_called_at": {"type": ["string", "null"]},
        "detail": {"type": "string"},
    },
}

CHECK_OUTPUT_SCHEMA = {
    "type": "object",
    "required": [
        "resource_url", "checked_at", "verdict", "score", "reasons",
        "liveness", "terms", "schema_quality", "catalog", "diff",
    ],
    "properties": {
        "resource_url": {"type": "string"},
        "checked_at": {"type": "string", "description": "ISO-8601 timestamp of the probe"},
        "verdict": {"type": "string", "enum": ["TRUSTED", "CAUTION", "AVOID"]},
        "score": {
            "type": "number",
            "minimum": 0,
            "maximum": 100,
            "description": "Trust score: 100 (fully trusted) to 0, from the itemized deductions in reasons",
        },
        "reasons": {"type": "array", "items": _REASON_ITEM},
        "liveness": {
            "type": "object",
            "required": ["alive", "http_status", "latency_ms", "method", "x402_valid", "parse_error"],
            "properties": {
                "alive": {"type": "boolean", "description": "The endpoint returned an HTTP response at all"},
                "http_status": {"type": ["integer", "null"]},
                "latency_ms": {"type": ["integer", "null"]},
                "method": {"type": ["string", "null"], "enum": ["GET", "POST", None]},
                "x402_valid": {"type": "boolean", "description": "The response parses as a valid x402 challenge"},
                "parse_error": {"type": ["string", "null"]},
            },
        },
        "terms": {
            "type": "object",
            "required": ["found", "price_usdc", "amount_units", "network", "asset", "pay_to", "scheme", "x402_version"],
            "properties": {
                "found": {"type": "boolean"},
                "price_usdc": {"type": ["string", "null"], "description": "Formatted price like $0.02 for known assets; null when asset decimals are unknown"},
                "amount_units": {"type": ["string", "null"], "description": "Price in asset smallest units, exactly as published"},
                "network": {"type": ["string", "null"]},
                "asset": {"type": ["string", "null"]},
                "pay_to": {"type": ["string", "null"]},
                "scheme": {"type": ["string", "null"]},
                "x402_version": {"type": ["integer", "null"]},
            },
        },
        "schema_quality": {
            "type": "object",
            "required": ["extension_present", "hollow", "score", "deductions"],
            "properties": {
                "extension_present": {"type": "boolean"},
                "hollow": {"type": ["boolean", "null"], "description": "True when the output is example-only/untyped; null when no extension exists"},
                "score": {"type": ["integer", "null"], "description": "0-100; null when no extension exists"},
                "deductions": {"type": "array", "items": _DEDUCTION_ITEM},
            },
        },
        "catalog": {
            "type": "object",
            "required": ["cdp_bazaar", "payai"],
            "properties": {
                "cdp_bazaar": _PRESENCE,
                "payai": _PRESENCE,
            },
        },
        "diff": {
            "type": "object",
            "required": ["prior_check", "prior_checked_at", "changes", "summary"],
            "properties": {
                "prior_check": {"type": "boolean"},
                "prior_checked_at": {"type": ["string", "null"]},
                "changes": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["field", "before", "after", "detail"],
                        "properties": {
                            "field": {"type": "string"},
                            "before": {"type": ["string", "null"]},
                            "after": {"type": ["string", "null"]},
                            "detail": {"type": "string"},
                        },
                    },
                },
                "summary": {"type": "string"},
            },
        },
    },
}

CHECK_INPUT_EXAMPLE = {
    "resource_url": "https://token-verdict-production.up.railway.app/v1/verdict",
}

CHECK_OUTPUT_EXAMPLE = {
    "resource_url": "https://token-verdict-production.up.railway.app/v1/verdict",
    "checked_at": "2026-10-21T20:00:00+00:00",
    "verdict": "TRUSTED",
    "score": 85.0,
    "reasons": [
        {
            "name": "not listed in CDP Bazaar",
            "deduction": 10,
            "detail": "payTo wallet has 0 CDP Bazaar resources; this URL is not among them.",
        },
        {
            "name": "not listed in PayAI index",
            "deduction": 5,
            "detail": "PayAI reports no catalog row for this resource (it catalogs only its own facilitator's settlements).",
        },
    ],
    "liveness": {
        "alive": True,
        "http_status": 402,
        "latency_ms": 312,
        "method": "GET",
        "x402_valid": True,
        "parse_error": None,
    },
    "terms": {
        "found": True,
        "price_usdc": "$0.02",
        "amount_units": "20000",
        "network": "eip155:8453",
        "asset": USDC_ASSET,
        "pay_to": "0x097f9685D1e0752bF8B02d61E5Ce9be7eA0FBA7F",
        "scheme": "exact",
        "x402_version": 2,
    },
    "schema_quality": {
        "extension_present": True,
        "hollow": False,
        "score": 100,
        "deductions": [],
    },
    "catalog": {
        "cdp_bazaar": {
            "status": "not_listed",
            "unique_payers_30d": None,
            "total_calls_30d": None,
            "last_called_at": None,
            "detail": "payTo wallet has 0 CDP Bazaar resources; this URL is not among them.",
        },
        "payai": {
            "status": "not_listed",
            "unique_payers_30d": None,
            "total_calls_30d": None,
            "last_called_at": None,
            "detail": "PayAI reports no catalog row for this resource.",
        },
    },
    "diff": {
        "prior_check": False,
        "prior_checked_at": None,
        "changes": [],
        "summary": "no prior check on record",
    },
}


def bazaar_extension() -> dict:
    """The x402 Bazaar discovery extension for POST /v1/check, in the
    canonical v2 shape: `info` carries the values (example input AND a
    full example output with its typed schema); `schema` is the JSON
    Schema OF THE INFO OBJECT (properties input/output), which is what
    facilitator-side validators check the info against. Mirrors the
    output of the SDK's declare_discovery_extension for a body route,
    with info.input.method present at rest."""
    return {
        "info": {
            "input": {
                "type": "http",
                "method": "POST",
                "bodyType": "json",
                "body": CHECK_INPUT_EXAMPLE,
            },
            "output": {
                "type": "json",
                "example": CHECK_OUTPUT_EXAMPLE,
                "schema": CHECK_OUTPUT_SCHEMA,
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
                        "body": CHECK_INPUT_SCHEMA,
                    },
                    "required": ["type", "method", "bodyType", "body"],
                    "additionalProperties": False,
                },
                "output": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string"},
                        "example": CHECK_OUTPUT_SCHEMA,
                        "schema": {"type": "object"},
                    },
                    "required": ["type"],
                },
            },
            "required": ["input"],
        },
    }


def x402_manifest(settings: Settings, base_url: str) -> dict:
    # accepts[] mirrors the live 402 challenge so directory validators
    # (Agent Bazaar, x402scan) accept the manifest.
    accepts = [
        {
            "scheme": "exact",
            "network": settings.network,
            "amount": _price_to_units(settings.price_usdc),
            "asset": USDC_ASSET,
            "payTo": settings.pay_to,
            "maxTimeoutSeconds": 300,
        }
    ]
    return {
        "x402Version": 2,
        "service": settings.service_name,
        "description": (
            "Trust checks for x402 endpoints: send any paid resource URL, "
            "get a TRUSTED / CAUTION / AVOID verdict with a 0-100 score, "
            "an itemized deduction list, catalog presence in the CDP "
            "Bazaar and PayAI indexes, and a diff against the last check. "
            f"No API key, no signup, {settings.price_usdc} USDC per check. "
            "Use this when an agent, monitor, or inspector needs to "
            "verify an x402 route before paying it or relying on it."
        ),
        "network": settings.network,
        "payTo": settings.pay_to,
        "ownershipProofs": OWNERSHIP_PROOFS,
        # The nudge inbox: this stall accepts signed fleet-health
        # nudges (app/nudge.py; spec in x402-loop-kits).
        # A top-level extension, NOT a resource — inbound mail is
        # free and the priced route count does not move.
        "extensions": {"nudge": nudge_extension(base_url)},
        "resources": [
            {
                "resource": f"{base_url}/v1/check",
                "method": "POST",
                "price": settings.price_usdc,
                "scheme": "exact",
                "mimeType": "application/json",
                "description": (
                    "Trust & liveness check for one x402 resource URL: "
                    "live 402 probe (never pays the target), terms, "
                    "discovery-schema quality, catalog presence, diff. "
                    "Use this when auditing an unfamiliar x402 endpoint "
                    "before paying or relying on it."
                ),
                "tags": ["x402", "trust", "liveness", "monitoring", "verification", "agents"],
                "accepts": accepts,
                "inputSchema": CHECK_INPUT_SCHEMA,
                "outputSchema": CHECK_OUTPUT_SCHEMA,
            },
            {
                "resource": f"{base_url}/quote",
                "method": "GET",
                "price": "$0.00",
                "description": "Free price quote for the paid endpoint",
            },
        ],
    }


def skill_md(settings: Settings, base_url: str) -> str:
    return f"""# {settings.service_name} — trust & liveness checks for x402 endpoints (x402)

Send any x402 resource URL, get a trust verdict on the endpoint itself.
Pay {settings.price_usdc} USDC per call on Base (`{settings.network}`) via the
x402 protocol — no API key needed.

## Paid endpoint

`POST {base_url}/v1/check`

Body (JSON):
- `resource_url` (required): full URL of the x402 resource to audit,
  e.g. `https://token-verdict-production.up.railway.app/v1/verdict`

The check is observation-only: RouteVerdict requests the target WITHOUT
paying it, parses its 402 challenge, and never sends it money. Returns:

- `verdict` (TRUSTED / CAUTION / AVOID) and `score` (0-100 trust score)
- `reasons` — every deduction that produced the score, itemized
- `liveness` — alive?, HTTP status, latency, whether the 402 parses as x402
- `terms` — price, network, asset, payTo from the live challenge
- `schema_quality` — is the Bazaar discovery schema real and typed, or
  hollow ({{"type", "example"}} only)? Scored 0-100 with named deductions
- `catalog` — is the resource listed in the CDP Bazaar / PayAI index?
  (`unknown` means the lookup failed — never a fabricated "not listed")
- `diff` — what changed since the previous check of the same URL (price,
  payTo, schema score, listing presence, liveness); a first check says
  "no prior check on record"

## Free endpoints

- `GET {base_url}/quote` — price, network, payTo
- `GET {base_url}/health` — liveness
- `GET {base_url}/.well-known/x402` — machine-readable manifest

## Honest limits

RouteVerdict reads what an endpoint publishes and what the public
catalogs hold. It does not settle a test payment to the target, does not
measure response quality of the paid payload, and cannot see inside the
target's wallet — payTo *changes* are flagged by the diff, not explained.
"""


def llms_txt(settings: Settings, base_url: str) -> str:
    return f"""# {settings.service_name}

Paid API: trust & liveness checks for x402 endpoints. Price: {settings.price_usdc} USDC per call, x402 v2, network {settings.network}.

## Endpoints

- POST {base_url}/v1/check — paid. Body: {{"resource_url": str}}
- GET {base_url}/quote — free price quote
- GET {base_url}/health — free liveness check
- GET {base_url}/.well-known/x402 — manifest
"""
