from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_BASE_USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
DEFAULT_BASE_RPCS = (
    "https://mainnet.base.org",
    "https://base.drpc.org",
    "https://gateway.tenderly.co/public/base",
    "https://base-mainnet.public.blastapi.io",
)


@dataclass(frozen=True)
class Settings:
    db_path: str
    api_key: str
    provenance_url: str
    provenance_token: str
    truth_url: str
    payment_recipient: str
    payment_chain_id: int
    payment_asset: str
    payment_token_address: str
    payment_rpc_urls: tuple[str, ...]
    payment_min_confirmations: int
    payment_order_ttl_minutes: int
    payment_late_grace_hours: int
    payment_poll_seconds: int
    payment_log_scan_blocks: int
    payment_explorer_url: str
    hub_url: str
    publisher_token: str
    publisher_id: str
    provider_key_file: str
    team_auth_secret: str


def get_settings() -> Settings:
    rpc_urls = tuple(
        value.strip() for value in os.getenv("PAYMENT_BASE_RPC_URLS", ",".join(DEFAULT_BASE_RPCS)).split(",")
        if value.strip()
    ) or DEFAULT_BASE_RPCS
    settings = Settings(
        db_path=os.getenv("MEMORY_MARKET_DB", "./data/memory-market.sqlite3"),
        api_key=os.getenv("MEMORY_MARKET_API_KEY", "change-me"),
        provenance_url=os.getenv("PROVENANCE_LEDGER_URL", ""),
        provenance_token=os.getenv("PROVENANCE_ADMIN_TOKEN", "change-me"),
        truth_url=os.getenv("TRUTH_LAYER_URL", ""),
        payment_recipient=os.getenv("PAYMENT_RECIPIENT", ""),
        payment_chain_id=int(os.getenv("PAYMENT_CHAIN_ID", "8453")),
        payment_asset=os.getenv("PAYMENT_ASSET", "USDC"),
        payment_token_address=os.getenv("PAYMENT_USDC_ADDRESS", DEFAULT_BASE_USDC).strip() or DEFAULT_BASE_USDC,
        payment_rpc_urls=rpc_urls,
        payment_min_confirmations=max(1, min(int(os.getenv("PAYMENT_MIN_CONFIRMATIONS", "5")), 200)),
        payment_order_ttl_minutes=max(5, min(int(os.getenv("PAYMENT_ORDER_TTL_MINUTES", "60")), 1440)),
        payment_late_grace_hours=max(0, min(int(os.getenv("PAYMENT_LATE_GRACE_HOURS", "24")), 168)),
        payment_poll_seconds=max(5, min(int(os.getenv("PAYMENT_POLL_SECONDS", "20")), 300)),
        payment_log_scan_blocks=max(1, min(int(os.getenv("PAYMENT_LOG_SCAN_BLOCKS", "40")), 2000)),
        payment_explorer_url=os.getenv("PAYMENT_EXPLORER_URL", "https://basescan.org").strip().rstrip("/"),
        hub_url=os.getenv("AIMARKET_HUB_URL", ""),
        publisher_token=os.getenv("AIMARKET_PUBLISHER_TOKEN", ""),
        publisher_id=os.getenv("AIMARKET_PUBLISHER_ID", "memory-market"),
        provider_key_file=os.getenv("PROVIDER_SIGNING_KEY_FILE", "./data/provider-signing-key.pem"),
        team_auth_secret=os.getenv("AIMARKET_TEAM_AUTH_SECRET", ""),
    )
    if production_mode():
        if _is_weak_secret(settings.provenance_token):
            # Was the one secret this block did not check; its default is literally "change-me".
            raise RuntimeError("PROVENANCE_ADMIN_TOKEN must be a random 32+ character secret in production")
        if _is_weak_secret(settings.api_key):
            raise RuntimeError("MEMORY_MARKET_API_KEY must be a random 32+ character secret in production")
        if not (os.getenv("MEMORY_MARKET_DATABASE_URL") or os.getenv("DATABASE_URL")):
            raise RuntimeError("PostgreSQL DSN is required in production")
        if os.getenv("ATTESTED_PQC_ENABLED", "1").strip().lower() not in {"1", "true", "yes"}:
            raise RuntimeError("ATTESTED_PQC_ENABLED cannot be disabled in production")
        if os.getenv("ATTESTED_PQC_REQUIRE", "1").strip().lower() not in {"1", "true", "yes"}:
            raise RuntimeError("ATTESTED_PQC_REQUIRE cannot be disabled in production")
        if _is_weak_secret(settings.team_auth_secret):
            raise RuntimeError("AIMARKET_TEAM_AUTH_SECRET must be a random 32+ character secret in production")
    return settings


def production_mode() -> bool:
    """Fail CLOSED: production unless the operator says otherwise.

    Every gate here used to switch on ``AIFACTORY_PROD`` being SET, so a deployment that
    forgot the variable — or copied an ``.env.example`` carrying ``AIFACTORY_PROD=0`` —
    ran with no actor verification and no capability authentication, silently. Now an
    explicit ``AIFACTORY_PROD=1`` always wins, and only an explicit ``AIFACTORY_DEV=1``
    turns the checks off. Unset means production.
    """
    if os.getenv("AIFACTORY_PROD", "").strip().lower() in {"1", "true", "yes"}:
        return True
    return os.getenv("AIFACTORY_DEV", "").strip().lower() not in {"1", "true", "yes"}


def _is_weak_secret(value: str) -> bool:
    text = (value or "").strip()
    lowered = text.lower()
    if len(text) < 32:
        return True
    if lowered in {"change-me", "dev-secret", "dev-only-change-me"}:
        return True
    if lowered.startswith("replace-with") or lowered.startswith("dev-"):
        return True
    if lowered.endswith("-change-me") or "change-me" in lowered:
        return True
    return False
