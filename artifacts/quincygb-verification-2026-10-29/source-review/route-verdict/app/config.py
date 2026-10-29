"""Settings for the route-verdict x402 service."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

log = logging.getLogger("route-verdict.config")

BASE_MAINNET = "eip155:8453"

# His payout wallet on Base (EVM) — the same payTo Token Verdict uses.
# Overridable via X402_PAY_TO.
OWNER_WALLET = "0x097f9685D1e0752bF8B02d61E5Ce9be7eA0FBA7F"
PLACEHOLDER_WALLETS = {"0x0000000000000000000000000000000000000000"}

# ultravioletadao public x402 facilitator (no keys). Verified via /supported:
# serves eip155:8453 (Base) with the exact scheme.
FACILITATOR_URL = "https://facilitator.ultravioletadao.xyz"

# PayAI public x402 facilitator (no keys for the exact scheme). Verified via
# /supported 2026-10-21: serves x402 v2 exact on eip155:8453 (Base). Settling
# through it catalogs this service in the PayAI index — each facilitator's
# catalog indexes only its own settlements.
PAYAI_FACILITATOR_URL = "https://facilitator.payai.network"


@dataclass(frozen=True)
class Settings:
    pay_to: str
    price_usdc: str  # e.g. "$0.05" — string format the x402 SDK expects
    network: str
    facilitator_url: str
    service_name: str
    fetch_timeout_s: float  # timeout for probing the target endpoint
    port: int
    db_path: str  # sqlite file holding prior checks (the diff memory)
    # Coinbase CDP facilitator credentials (optional). Only used when
    # X402_FACILITATOR_URL points at CDP — see use_cdp below.
    # Fleet-internal shared secret (optional). Gates the unpaid
    # /v1/internal/* route that StallRow's /v1/orchestrate fans out
    # to; unset = route disabled (404). Never in discovery.
    fleet_internal_secret: str | None = None
    cdp_api_key_id: str | None = None
    cdp_api_key_secret: str | None = None

    @property
    def use_cdp(self) -> bool:
        """True when settlements should run through the CDP facilitator
        with JWT auth — the path that feeds the CDP Bazaar catalog. Requires
        BOTH the CDP facilitator URL and API keys; otherwise the keyless
        public facilitator path runs unchanged."""
        return (
            "api.cdp.coinbase.com" in self.facilitator_url
            and bool(self.cdp_api_key_id)
            and bool(self.cdp_api_key_secret)
        )

    @property
    def use_payai(self) -> bool:
        """True when settlements run through the PayAI facilitator — the
        path that feeds the PayAI index catalog. No API key is needed for
        the exact scheme, so the URL alone selects it."""
        return "facilitator.payai.network" in self.facilitator_url


def load_settings() -> Settings:
    pay_to = os.environ.get("X402_PAY_TO", OWNER_WALLET).strip()
    if pay_to in PLACEHOLDER_WALLETS:
        raise RuntimeError("X402_PAY_TO is a placeholder address — set a real wallet.")
    if not (pay_to.startswith("0x") and len(pay_to) == 42):
        raise RuntimeError(f"X402_PAY_TO does not look like an EVM address: {pay_to!r}")

    network = os.environ.get("X402_NETWORK", BASE_MAINNET).strip()
    facilitator_url = os.environ.get("X402_FACILITATOR_URL", FACILITATOR_URL).strip()

    cdp_keys = {
        k: (os.environ.get(k, "").strip() or None)
        for k in ("CDP_API_KEY_ID", "CDP_API_KEY_SECRET")
    }

    return Settings(
        pay_to=pay_to,
        price_usdc=os.environ.get("X402_PRICE_USDC", "$0.05").strip(),
        network=network,
        facilitator_url=facilitator_url,
        service_name=os.environ.get("X402_SERVICE_NAME", "route-verdict").strip(),
        fetch_timeout_s=float(os.environ.get("ROUTE_VERDICT_FETCH_TIMEOUT_S", "10")),
        port=int(os.environ.get("PORT", "3000")),
        db_path=os.environ.get("ROUTE_VERDICT_DB", "route-verdict.db").strip(),
        fleet_internal_secret=os.environ.get("FLEET_INTERNAL_SECRET", "").strip() or None,
        **{k.lower(): v for k, v in cdp_keys.items() if v is not None},
    )
