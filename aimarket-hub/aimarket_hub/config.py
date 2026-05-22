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

    # Database
    db_path: str = field(default_factory=lambda: os.getenv("AIMARKET_DB_PATH", "data/hub.db"))

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

    # Payment
    payment_chain: str = field(default_factory=lambda: os.getenv("AIMARKET_PAYMENT_CHAIN", "base"))
    payment_token: str = field(default_factory=lambda: os.getenv("AIMARKET_PAYMENT_TOKEN", "USDT"))
    payment_recipient: str = field(default_factory=lambda: os.getenv("AIMARKET_PAYMENT_RECIPIENT", "0x0000000000000000000000000000000000000000"))
    payment_testnet: bool = field(default_factory=lambda: os.getenv("AIFACTORY_PAYMENT_TESTNET", "1") == "1")
    payment_verify_stub: bool = field(default_factory=lambda: os.getenv("AIFACTORY_PAYMENT_VERIFY_STUB", "1") == "1")

    def db_dir(self) -> Path:
        return Path(self.db_path).parent


def _parse_seed_list() -> list[str]:
    raw = os.getenv("AIMARKET_SEED_LIST", "")
    if not raw:
        return []
    return [u.strip() for u in raw.split(",") if u.strip()]
