"""Protocol v1 configuration from environment."""

from __future__ import annotations

import os


def pilot_tuple() -> dict[str, str]:
    chain = os.environ.get("AIFACTORY_AI_MARKET_CHAIN", "base").strip().lower() or "base"
    token = os.environ.get("AIFACTORY_AI_MARKET_TOKEN", "USDT").strip().upper() or "USDT"
    contract = os.environ.get("AIFACTORY_AI_MARKET_CONTRACT", "").strip()
    return {"chain": chain, "token": token, "contract": contract}


def protocol_versions() -> list[str]:
    return ["v1", "mcp"]


def base_public_url() -> str:
    return (
        os.environ.get("AIFACTORY_PUBLIC_URL", "").strip()
        or os.environ.get("NEXT_PUBLIC_SITE_URL", "").strip()
        or "http://127.0.0.1:9080"
    ).rstrip("/")


def demo_payment_bypass() -> bool:
    return os.environ.get("AIFACTORY_AI_MARKET_DEMO_PAYMENT", "1").strip().lower() in (
        "1",
        "true",
        "yes",
    )
