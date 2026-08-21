"""AIMarket Protocol configuration from environment (v1 + v2 + mcp)."""

from __future__ import annotations

import os
from typing import Any

# Wire version this hub advertises in the discovery manifest. The hub speaks the
# v1 payment/invoke surface, the v2 federation surface, and the MCP tool surface.
HUB_VERSION = "2.0.0"


def pilot_tuple() -> dict[str, str]:
    chain = os.environ.get("AIFACTORY_AI_MARKET_CHAIN", "base").strip().lower() or "base"
    token = os.environ.get("AIFACTORY_AI_MARKET_TOKEN", "USDT").strip().upper() or "USDT"
    contract = os.environ.get("AIFACTORY_AI_MARKET_CONTRACT", "").strip()
    return {"chain": chain, "token": token, "contract": contract}


def protocol_versions() -> list[str]:
    return ["v1", "v2", "mcp"]


def federation_descriptor() -> dict[str, Any]:
    """Honest v2 federation block for the discovery manifest.

    This hub federates search/invoke to a single optional upstream hub rather
    than maintaining its own crawled peer set, so the top-level ``peers`` list
    stays empty and the configured upstream (when federation is enabled) is
    advertised through ``seed_list``.
    """
    from core.aimarket_hub_url import resolve_federation_hub_url

    hub = resolve_federation_hub_url()  # default "" → unconfigured keeps seed_list empty
    federate = os.environ.get("AIMARKET_WIDGET_FEDERATE_SEARCH", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    seed_list = [f"{hub}/.well-known/ai-market.json"] if hub and federate else []
    try:
        routing_fee_bps = int(os.environ.get("AIMARKET_ROUTING_FEE_BPS", "0") or 0)
    except ValueError:
        routing_fee_bps = 0
    return {
        "crawl_interval_s": 3600,
        "routing_fee_bps": routing_fee_bps,
        "min_trust_score": 0.0,
        "seed_list": seed_list,
    }


# Hosts that name the machine doing the reading, whoever that turns out to be. A public
# manifest that advertises one of these has published an address nobody else can route to.
_LOOPBACK_HOSTS = ("localhost", "127.", "0.0.0.0", "[::1]", "::1",
                   "10.", "192.168.", "169.254.", "172.16.", "172.17.", "172.18.")


def _is_loopback_url(url: str) -> bool:
    if not url:
        return False
    host = url.split("//", 1)[-1].split("/", 1)[0].split("@")[-1].lower()
    return any(host.startswith(h) for h in _LOOPBACK_HOSTS)


def base_public_url() -> str:
    """The address this deployment tells the world to reach it at.

    A routable candidate wins over an unroutable one regardless of order. Taking the first
    non-empty value meant a stale ``AIFACTORY_PUBLIC_URL=http://localhost:9080`` outranked a
    perfectly correct ``NEXT_PUBLIC_SITE_URL=https://magic-ai-factory.com``, and the public
    manifest then advertised ``mcp_endpoint: http://localhost:9080/ai-market/mcp`` — every
    peer that honoured it dialled its own machine. Found live on 2026-08-16.

    Falls back to the first non-empty candidate so a purely local dev setup, where every
    candidate is loopback, still gets the address it configured.
    """
    candidates = [
        os.environ.get("AIFACTORY_PUBLIC_URL", "").strip(),
        os.environ.get("NEXT_PUBLIC_SITE_URL", "").strip(),
    ]
    present = [c for c in candidates if c]
    routable = [c for c in present if not _is_loopback_url(c)]
    return (routable[0] if routable else (present[0] if present else "http://127.0.0.1:9080")).rstrip("/")


_PRODUCTION_ENV_TAGS = frozenset({"production", "prod", "live"})


def _is_production_env() -> bool:
    env = os.environ.get("AIFACTORY_ENV", "").strip().lower()
    if env in _PRODUCTION_ENV_TAGS:
        return True
    # Two production-marker env vars exist in the repo: ``AIFACTORY_PROD=1`` is
    # consumed by ``security/prod_startup_guard.py``; ``AIFACTORY_PRODUCTION=1``
    # appears in some deploy scripts. Honour BOTH so a deployment that flips
    # only one of them still triggers the demo-bypass interlock.
    for key in ("AIFACTORY_PROD", "AIFACTORY_PRODUCTION"):
        if os.environ.get(key, "").strip().lower() in ("1", "true", "yes", "on"):
            return True
    return False


def demo_payment_bypass() -> bool:
    """Allow ``demo-*`` / ``0xdemo*`` tx hashes to bypass on-chain verification.

    Hard-disabled when the deployment self-identifies as production via
    ``AIFACTORY_ENV`` (production|prod|live), ``AIFACTORY_PROD=1``, or
    ``AIFACTORY_PRODUCTION=1``. A misconfigured ``AIFACTORY_AI_MARKET_DEMO_PAYMENT=1``
    in prod would otherwise let any caller mint UNI / open payment channels for free.
    """
    if _is_production_env():
        return False
    return os.environ.get("AIFACTORY_AI_MARKET_DEMO_PAYMENT", "0").strip().lower() in (
        "1",
        "true",
        "yes",
    )
