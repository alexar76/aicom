"""UNI ledger configuration (SQLite default, optional PostgreSQL for production)."""

from __future__ import annotations

import os
from typing import Literal

from core.uni.constants import (
    DEFAULT_MIN_WITHDRAW_UNI,
    DEFAULT_PLATFORM_FEE_BPS,
    DEFAULT_TOPUP_FEE_BPS,
    DEFAULT_WITHDRAW_FEE_BPS,
    UNI_PER_USDT,
)

UniDbBackend = Literal["sqlite", "postgres"]


def _truthy(name: str, default: str = "false") -> bool:
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes", "on")


def uni_enabled() -> bool:
    return _truthy("AIFACTORY_UNI_ENABLED", "1")


def uni_db_backend() -> UniDbBackend:
    explicit = os.environ.get("UNI_DB_BACKEND", "").strip().lower()
    if explicit in ("sqlite", "postgres"):
        return explicit  # type: ignore[return-value]
    if uni_database_url() and _truthy("UNI_USE_POSTGRES", "false"):
        return "postgres"
    return "sqlite"


def uni_database_url() -> str:
    return (
        os.environ.get("UNI_DATABASE_URL", "").strip()
        or os.environ.get("DATABASE_URL", "").strip()
    )


def uni_use_commerce_db() -> bool:
    """When true, UNI tables live in ``store/commerce.db`` (same file as orders)."""
    return _truthy("AIFACTORY_UNI_USE_COMMERCE_DB", "0")


def uni_usd_cents_per_uni() -> int:
    """
    UNI per US cent at peg. Default 1 → 1 UNI = $0.01.

    Legacy ``AIFACTORY_UNI_USDT_RATE=100`` means 100 UNI per $1 (same peg).
    """
    raw = os.environ.get("AIFACTORY_UNI_USD_CENTS_PER_UNI", "").strip()
    if raw:
        try:
            return max(1, int(raw))
        except ValueError:
            pass
    legacy = os.environ.get("AIFACTORY_UNI_USDT_RATE", "").strip()
    if legacy:
        try:
            rate = float(legacy)
            if rate >= 1:
                return max(1, int(round(rate / 100.0)) or 1)
        except ValueError:
            pass
    return 1


def usdt_to_uni_rate() -> float:
    """UNI credited per 1 USDT at top-up (before spread). Default 100."""
    return float(uni_usd_cents_per_uni() * 100)


def uni_topup_spread_bps() -> int:
    try:
        return max(0, min(5000, int(os.environ.get("AIFACTORY_UNI_TOPUP_SPREAD_BPS", str(DEFAULT_TOPUP_FEE_BPS)))))
    except ValueError:
        return DEFAULT_TOPUP_FEE_BPS


def uni_platform_fee_bps() -> int:
    try:
        return max(0, min(10_000, int(os.environ.get("AIFACTORY_UNI_PLATFORM_FEE_BPS", str(DEFAULT_PLATFORM_FEE_BPS)))))
    except ValueError:
        return DEFAULT_PLATFORM_FEE_BPS


def uni_withdraw_fee_bps() -> int:
    try:
        return max(0, min(5000, int(os.environ.get("AIFACTORY_UNI_WITHDRAW_FEE_BPS", str(DEFAULT_WITHDRAW_FEE_BPS)))))
    except ValueError:
        return DEFAULT_WITHDRAW_FEE_BPS


def uni_min_withdraw_uni() -> int:
    try:
        return max(0, int(os.environ.get("AIFACTORY_UNI_MIN_WITHDRAW_UNI", str(DEFAULT_MIN_WITHDRAW_UNI))))
    except ValueError:
        return DEFAULT_MIN_WITHDRAW_UNI


def uni_grant_secret() -> str:
    return os.environ.get("AIFACTORY_UNI_GRANT_SECRET", "").strip()


def uni_treasury_usdt_observed() -> float | None:
    """Optional manual/ops override for audit job when chain indexer is not wired."""
    raw = os.environ.get("AIFACTORY_UNI_TREASURY_USDT_OBSERVED", "").strip()
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None
