"""Jupiter swap route client for ACEX CapShares on Solana (Phase 2)."""

from __future__ import annotations

import os
from typing import Any

import httpx

JUPITER_QUOTE_URL = os.environ.get(
    "ACEX_JUPITER_QUOTE_URL", "https://quote-api.jup.ag/v6/quote"
).rstrip("/")
JUPITER_SWAP_URL = os.environ.get(
    "ACEX_JUPITER_SWAP_URL", "https://quote-api.jup.ag/v6/swap"
).rstrip("/")

# Devnet / mainnet USDC mints (override via env for staging).
DEFAULT_USDC_MINT = os.environ.get(
    "ACEX_SOLANA_USDC_MINT",
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
)


class JupiterRouteError(Exception):
    pass


async def fetch_jupiter_quote(
    *,
    input_mint: str,
    output_mint: str,
    amount: int,
    slippage_bps: int = 50,
    only_direct_routes: bool = False,
    timeout_s: float = 20.0,
) -> dict[str, Any]:
    """Fetch a Jupiter v6 quote for CapShare ↔ USDC routing."""
    if amount <= 0:
        raise JupiterRouteError("amount must be positive")
    params = {
        "inputMint": input_mint,
        "outputMint": output_mint,
        "amount": str(amount),
        "slippageBps": str(slippage_bps),
        "onlyDirectRoutes": "true" if only_direct_routes else "false",
    }
    async with httpx.AsyncClient(timeout=timeout_s) as client:
        resp = await client.get(JUPITER_QUOTE_URL, params=params)
    if resp.status_code != 200:
        raise JupiterRouteError(f"jupiter quote failed: HTTP {resp.status_code}")
    body = resp.json()
    if not body.get("outAmount"):
        raise JupiterRouteError("jupiter quote missing outAmount")
    return body


def build_swap_plan(quote: dict[str, Any], *, user_public_key: str) -> dict[str, Any]:
    """Return a swap plan payload for Pulse Terminal / wallet signing."""
    return {
        "provider": "jupiter",
        "quote": quote,
        "user_public_key": user_public_key,
        "swap_api": JUPITER_SWAP_URL,
        "input_mint": quote.get("inputMint"),
        "output_mint": quote.get("outputMint"),
        "in_amount": quote.get("inAmount"),
        "out_amount": quote.get("outAmount"),
        "price_impact_pct": quote.get("priceImpactPct"),
        "route_plan": quote.get("routePlan") or [],
    }


def synthetic_quote_for_tests(
    *,
    input_mint: str,
    output_mint: str,
    amount: int,
    out_amount: int | None = None,
) -> dict[str, Any]:
    """Deterministic quote for unit tests without hitting Jupiter."""
    out = out_amount if out_amount is not None else int(amount * 0.99)
    return {
        "inputMint": input_mint,
        "outputMint": output_mint,
        "inAmount": str(amount),
        "outAmount": str(out),
        "priceImpactPct": "0.01",
        "routePlan": [{"swapInfo": {"label": "test-pool"}}],
    }
