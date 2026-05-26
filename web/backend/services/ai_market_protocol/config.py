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


_PRODUCTION_ENV_TAGS = frozenset({"production", "prod", "live"})


def _is_production_env() -> bool:
    env = os.environ.get("AIFACTORY_ENV", "").strip().lower()
    if env in _PRODUCTION_ENV_TAGS:
        return True
    # Fallback marker used by some deploy scripts.
    return os.environ.get("AIFACTORY_PRODUCTION", "").strip().lower() in ("1", "true", "yes")


def demo_payment_bypass() -> bool:
    """Allow ``demo-*`` / ``0xdemo*`` tx hashes to bypass on-chain verification.

    Hard-disabled when the deployment self-identifies as production via
    ``AIFACTORY_ENV`` (production|prod|live) or ``AIFACTORY_PRODUCTION=1``. A
    misconfigured ``AIFACTORY_AI_MARKET_DEMO_PAYMENT=1`` in prod would otherwise
    let any caller mint UNI / open payment channels for free.
    """
    if _is_production_env():
        return False
    return os.environ.get("AIFACTORY_AI_MARKET_DEMO_PAYMENT", "0").strip().lower() in (
        "1",
        "true",
        "yes",
    )
