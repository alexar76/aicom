"""Shared path / URL resolution for ACEX IPO and audit ledgers.

Production: PostgreSQL via dedicated ACEX URL env vars or shared DATABASE_URL.
Dev/test: SQLite files under a stable data root (never CWD-relative).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


def is_production() -> bool:
    return os.getenv("AIFACTORY_PROD", "").strip().lower() in ("1", "true", "yes")


def data_root() -> Path:
    env = os.environ.get("AIFACTORY_DATA_ROOT", "").strip()
    if env:
        return Path(env)
    try:
        from core.paths import data_root as core_data_root

        return core_data_root()
    except ImportError:
        return Path(__file__).resolve().parent.parent


def resolve_database_url(*env_keys: str) -> str:
    """First non-empty dedicated env, then DATABASE_URL."""
    for key in env_keys:
        value = os.getenv(key, "").strip()
        if value:
            return value
    return os.getenv("DATABASE_URL", "").strip()


def resolve_sqlite_path(raw: str, *, label: str) -> Path:
    """Absolute paths as-is; relative paths under AIFACTORY_DATA_ROOT / package.

    Resolution only. The ledgers call this even when PostgreSQL is configured, and on the
    hub AIFACTORY_DATA_ROOT is the read-only Factory catalog export, where creating
    <root>/data fails and took every paid invoke's ACEX accrual down with it. The
    directory is created by SQLiteBackend, only when SQLite is actually opened.
    """
    text = (raw or "").strip() or "data/acex.db"
    path = Path(text).expanduser()
    path = path.resolve() if path.is_absolute() else (data_root() / path).resolve()
    logger.info("ACEX %s ledger SQLite path %s", label, path)
    return path


class LedgerNotConfigured(RuntimeError):
    """A production hub with no PostgreSQL URL for an ACEX ledger: the ledger is off by
    configuration, which is a state, not a fault. Callers answer it (a 503 on a public read,
    no accrual on an invoke) without a traceback; the reason is logged once per process."""


_warned: set[str] = set()


def warn_not_configured_once(exc: LedgerNotConfigured, ledger: str) -> None:
    if ledger not in _warned:
        _warned.add(ledger)
        logger.warning("%s — ACEX %s reads answer 503 and invokes accrue nothing until it is set", exc, ledger)


def require_postgres_url(url: str, *, ledger: str) -> None:
    # Until 2026-10-23 this raised a bare RuntimeError that every caller logged with a full
    # traceback: 311 of them in one day on modelmarket.dev, which runs without ACEX ledgers.
    if is_production() and not url.startswith(("postgresql://", "postgres://")):
        raise LedgerNotConfigured(
            f"production ACEX {ledger} ledger requires "
            f"AIMARKET_ACEX_{ledger.upper()}_DATABASE_URL or DATABASE_URL=postgresql://...; "
            "SQLite fallback is disabled when AIFACTORY_PROD=1"
        )
