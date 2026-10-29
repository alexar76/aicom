"""Parsing of x402 payment challenges (observation only — we never pay).

A target endpoint answers an unauthenticated request with HTTP 402 and a
challenge that lives either in the JSON body (x402 v1 and v2) or in the
base64 `payment-required` response header (v2). This module turns either
into a typed structure the checker can score. It is deliberately liberal:
real-world endpoints vary, and a parse failure is itself a finding the
caller reports — never an exception that escapes.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field
from decimal import Decimal

# Assets whose decimals we know, keyed by (network, asset). USDC on Base
# is the only asset we price-format; anything else is reported in raw
# smallest units with price_usdc = None (unknown decimals = no guessing).
KNOWN_ASSET_DECIMALS = {
    ("eip155:8453", "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"): 6,
}


@dataclass
class Accept:
    scheme: str | None
    network: str | None
    asset: str | None
    amount: str | None  # smallest units, as a string, exactly as published
    pay_to: str | None
    max_timeout_seconds: int | None


@dataclass
class ChallengeParse:
    valid: bool
    x402_version: int | None = None
    accepts: list[Accept] = field(default_factory=list)
    bazaar: dict | None = None  # extensions.bazaar, when present
    resource_description: str | None = None
    error: str | None = None
    source: str = "none"  # "body" | "header" | "none"

    def primary_accept(self, preferred_network: str = "eip155:8453") -> Accept | None:
        """The accept a Base buyer would use: prefer the preferred
        network, fall back to the first complete-looking entry."""
        for a in self.accepts:
            if a.network == preferred_network:
                return a
        return self.accepts[0] if self.accepts else None


def _parse_accept(raw: dict) -> Accept:
    amount = raw.get("amount")
    if amount is None:
        amount = raw.get("maxAmountRequired")  # x402 v1 field name
    timeout = raw.get("maxTimeoutSeconds")
    return Accept(
        scheme=raw.get("scheme"),
        network=raw.get("network"),
        asset=raw.get("asset"),
        amount=str(amount) if amount is not None else None,
        pay_to=raw.get("payTo"),
        max_timeout_seconds=int(timeout) if isinstance(timeout, (int, float)) else None,
    )


def _parse_payload(payload: object, source: str) -> ChallengeParse:
    if not isinstance(payload, dict):
        return ChallengeParse(valid=False, source=source, error="challenge is not a JSON object")
    raw_accepts = payload.get("accepts")
    if not isinstance(raw_accepts, list) or not raw_accepts:
        return ChallengeParse(
            valid=False,
            source=source,
            error="challenge has no accepts array",
            x402_version=payload.get("x402Version"),
        )
    accepts = [_parse_accept(a) for a in raw_accepts if isinstance(a, dict)]
    if not accepts:
        return ChallengeParse(valid=False, source=source, error="accepts entries are not objects")
    extensions = payload.get("extensions") or {}
    bazaar = extensions.get("bazaar") if isinstance(extensions, dict) else None
    resource = payload.get("resource") or {}
    description = resource.get("description") if isinstance(resource, dict) else None
    return ChallengeParse(
        valid=True,
        x402_version=payload.get("x402Version"),
        accepts=accepts,
        bazaar=bazaar if isinstance(bazaar, dict) else None,
        resource_description=description if isinstance(description, str) else None,
        source=source,
    )


def parse_challenge(status: int, headers: dict, body: bytes) -> ChallengeParse:
    """Parse a target's unauthenticated response into a ChallengeParse.

    Tries the JSON body first, then the base64 `payment-required` header.
    Header lookup is case-insensitive (pass any mapping of header names).
    """
    lowered = {str(k).lower(): v for k, v in headers.items()}

    if body:
        try:
            payload = json.loads(body)
        except (ValueError, UnicodeDecodeError):
            payload = None
        if isinstance(payload, dict) and ("accepts" in payload or "x402Version" in payload):
            return _parse_payload(payload, "body")

    header_value = lowered.get("payment-required")
    if header_value:
        try:
            decoded = base64.b64decode(header_value, validate=False)
            payload = json.loads(decoded)
        except (ValueError, UnicodeDecodeError):
            return ChallengeParse(valid=False, source="header", error="payment-required header is not base64 JSON")
        return _parse_payload(payload, "header")

    if status == 402:
        return ChallengeParse(valid=False, source="none", error="HTTP 402 with no parseable challenge")
    return ChallengeParse(valid=False, source="none", error=f"HTTP {status}, not a 402 challenge")


def format_price(amount_units: str | None, network: str | None, asset: str | None) -> str | None:
    """'$0.05' for a known asset; None when decimals are unknown.

    Sub-cent amounts keep their exact precision ('$0.001', '$0.005');
    see the Decimal rendering below.
    """
    if amount_units is None or network is None or asset is None:
        return None
    decimals = KNOWN_ASSET_DECIMALS.get((network, asset.lower()))
    if decimals is None:
        return None
    try:
        units = int(amount_units)
    except ValueError:
        return None
    # Exact Decimal arithmetic: sub-cent prices (fleet routes go down
    # to $0.001) keep their precision ('$0.001', '$0.005') and a nonzero
    # price never renders as "$0.00". Amounts of a cent or more keep
    # the familiar two-decimal rendering unless they carry sub-cent
    # residue, which is also shown exactly.
    value = Decimal(units) / (Decimal(10) ** decimals)
    rendered = format(value, "f")
    if "." in rendered:
        head, _, frac = rendered.partition(".")
        frac = frac.rstrip("0")
        if len(frac) < 2:
            frac = frac.ljust(2, "0")
        rendered = f"{head}.{frac}"
    else:
        rendered = f"{rendered}.00"
    return f"${rendered}"
