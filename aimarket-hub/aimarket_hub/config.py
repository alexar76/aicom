"""Hub configuration — env vars, defaults, paths."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class HubConfig:
    """Configuration for an AIMarket Hub instance."""

    # Identity
    hub_name: str = field(default_factory=lambda: os.getenv("AIMARKET_HUB_NAME", "AIMarket Hub"))
    hub_url: str = field(default_factory=lambda: os.getenv("AIMARKET_HUB_URL", "http://localhost:9080"))
    hub_version: str = "2.0.0"

    # Database (SQLite path or PostgreSQL URL)
    db_path: str = field(default_factory=lambda: os.getenv("AIMARKET_DB_PATH", "data/hub.db"))
    database_url: str = field(default_factory=lambda: os.getenv("DATABASE_URL", ""))

    # Federation
    crawl_interval_s: int = field(default_factory=lambda: int(os.getenv("AIMARKET_CRAWL_INTERVAL_S", "3600")))
    routing_fee_bps: int = field(default_factory=lambda: int(os.getenv("AIMARKET_ROUTING_FEE_BPS", "100")))
    min_trust_score: float = field(default_factory=lambda: float(os.getenv("AIMARKET_MIN_TRUST_SCORE", "0.3")))
    max_crawl_depth: int = field(default_factory=lambda: int(os.getenv("AIMARKET_MAX_CRAWL_DEPTH", "3")))

    # Seed list
    seed_list: list[str] = field(default_factory=lambda: _parse_seed_list())

    # Keys
    signing_key_path: str = field(default_factory=lambda: os.getenv("AIMARKET_SIGNING_KEY_PATH", "data/hub_signing_key"))

    # HTTP
    request_timeout_s: float = field(default_factory=lambda: float(os.getenv("AIMARKET_REQUEST_TIMEOUT_S", "30")))

    # Payment — multi-chain
    payment_chains: list[str] = field(default_factory=lambda: _parse_chains())
    payment_tokens: list[str] = field(default_factory=lambda: _parse_tokens())
    payment_recipient: str = field(default_factory=lambda: os.getenv("AIMARKET_PAYMENT_RECIPIENT", ""))
    payment_testnet: bool = field(default_factory=lambda: os.getenv("AIFACTORY_PAYMENT_TESTNET", "1") == "1")
    payment_verify_stub: bool = field(default_factory=lambda: os.getenv("AIFACTORY_PAYMENT_VERIFY_STUB", "0") == "1")
    payment_min_confirmations: int = field(default_factory=lambda: int(os.getenv("AIFACTORY_PAYMENT_MIN_CONFIRMATIONS", "2")))

    # Escrow contracts (set after deployment)
    escrow_evm_address: str = field(default_factory=lambda: os.getenv("AIMARKET_ESCROW_EVM_ADDRESS", ""))
    escrow_solana_program_id: str = field(default_factory=lambda: os.getenv("AIMARKET_ESCROW_SOLANA_PROGRAM_ID", "9BcJEAQCeFrPunKQ16itbaAzpw9A4zMHYPQxNxEAZUXR"))

    # Hub bond
    hub_bond_usd: float = field(default_factory=lambda: float(os.getenv("AIMARKET_HUB_BOND_USD", "100")))
    hub_bond_token: str = field(default_factory=lambda: os.getenv("AIMARKET_HUB_BOND_TOKEN", "USDT"))
    hub_bond_chain: str = field(default_factory=lambda: os.getenv("AIMARKET_HUB_BOND_CHAIN", "base"))

    # Factory seed (demo mode)
    factory_seed_usd: float = field(default_factory=lambda: float(os.getenv("AIMARKET_FACTORY_SEED_USD", "0")))

    # Backward compat
    @property
    def payment_chain(self) -> str:
        return self.payment_chains[0] if self.payment_chains else "base"

    @property
    def payment_token(self) -> str:
        return self.payment_tokens[0] if self.payment_tokens else "USDT"

    def db_dir(self) -> Path:
        return Path(self.db_path).parent


def _parse_seed_list() -> list[str]:
    raw = os.getenv("AIMARKET_SEED_LIST", "")
    if not raw:
        return []
    return [u.strip() for u in raw.split(",") if u.strip()]


def _parse_chains() -> list[str]:
    raw = os.getenv("AIMARKET_PAYMENT_CHAINS", os.getenv("AIMARKET_PAYMENT_CHAIN", "base,ethereum,arbitrum,optimism,polygon"))
    return [c.strip() for c in raw.split(",") if c.strip()]


def _parse_tokens() -> list[str]:
    raw = os.getenv("AIMARKET_PAYMENT_TOKENS", os.getenv("AIMARKET_PAYMENT_TOKEN", "USDT,USDC,ETH"))
    return [t.strip() for t in raw.split(",") if t.strip()]
