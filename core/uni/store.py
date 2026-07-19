"""SQLite / PostgreSQL persistence for UNI wallets."""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from contextlib import contextmanager, suppress
from typing import TYPE_CHECKING, Any

from core.paths import uni_db_path as resolve_uni_db_path
from core.uni.config import uni_database_url, uni_db_backend

if TYPE_CHECKING:
    from collections.abc import Iterator

logger = logging.getLogger(__name__)

_SCHEMA_SQLITE = """
CREATE TABLE IF NOT EXISTS uni_wallets (
    wallet_id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL UNIQUE,
    balance_uni REAL NOT NULL DEFAULT 0,
    hold_uni REAL NOT NULL DEFAULT 0,
    lifetime_in REAL NOT NULL DEFAULT 0,
    lifetime_out REAL NOT NULL DEFAULT 0,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_uni_wallets_owner ON uni_wallets(owner_id);

CREATE TABLE IF NOT EXISTS uni_ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    wallet_id TEXT NOT NULL,
    entry_type TEXT NOT NULL,
    amount_uni REAL NOT NULL,
    balance_after REAL NOT NULL,
    hold_after REAL NOT NULL,
    ref TEXT,
    meta_json TEXT,
    ts REAL NOT NULL,
    idempotency_key TEXT UNIQUE
);
CREATE INDEX IF NOT EXISTS idx_uni_ledger_wallet_ts ON uni_ledger(wallet_id, ts);

CREATE TABLE IF NOT EXISTS uni_holds (
    hold_id TEXT PRIMARY KEY,
    wallet_id TEXT NOT NULL,
    channel_id TEXT,
    amount_uni REAL NOT NULL,
    remaining_uni REAL NOT NULL,
    seller_ref TEXT,
    status TEXT NOT NULL,
    expires_at REAL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_uni_holds_channel ON uni_holds(channel_id);

CREATE TABLE IF NOT EXISTS uni_receipts (
    receipt_id TEXT PRIMARY KEY,
    wallet_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    amount_uni REAL NOT NULL,
    payload_json TEXT NOT NULL,
    signature TEXT NOT NULL,
    ts REAL NOT NULL,
    idempotency_key TEXT UNIQUE
);
CREATE INDEX IF NOT EXISTS idx_uni_receipts_wallet_ts ON uni_receipts(wallet_id, ts);
"""

_SCHEMA_POSTGRES = """
CREATE TABLE IF NOT EXISTS uni_wallets (
    wallet_id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL UNIQUE,
    balance_uni DOUBLE PRECISION NOT NULL DEFAULT 0,
    hold_uni DOUBLE PRECISION NOT NULL DEFAULT 0,
    lifetime_in DOUBLE PRECISION NOT NULL DEFAULT 0,
    lifetime_out DOUBLE PRECISION NOT NULL DEFAULT 0,
    created_at DOUBLE PRECISION NOT NULL,
    updated_at DOUBLE PRECISION NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_uni_wallets_owner ON uni_wallets(owner_id);

CREATE TABLE IF NOT EXISTS uni_ledger (
    id BIGSERIAL PRIMARY KEY,
    wallet_id TEXT NOT NULL,
    entry_type TEXT NOT NULL,
    amount_uni DOUBLE PRECISION NOT NULL,
    balance_after DOUBLE PRECISION NOT NULL,
    hold_after DOUBLE PRECISION NOT NULL,
    ref TEXT,
    meta_json TEXT,
    ts DOUBLE PRECISION NOT NULL,
    idempotency_key TEXT UNIQUE
);
CREATE INDEX IF NOT EXISTS idx_uni_ledger_wallet_ts ON uni_ledger(wallet_id, ts);

CREATE TABLE IF NOT EXISTS uni_holds (
    hold_id TEXT PRIMARY KEY,
    wallet_id TEXT NOT NULL,
    channel_id TEXT,
    amount_uni DOUBLE PRECISION NOT NULL,
    remaining_uni DOUBLE PRECISION NOT NULL,
    seller_ref TEXT,
    status TEXT NOT NULL,
    expires_at DOUBLE PRECISION,
    created_at DOUBLE PRECISION NOT NULL,
    updated_at DOUBLE PRECISION NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_uni_holds_channel ON uni_holds(channel_id);

CREATE TABLE IF NOT EXISTS uni_receipts (
    receipt_id TEXT PRIMARY KEY,
    wallet_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    amount_uni DOUBLE PRECISION NOT NULL,
    payload_json TEXT NOT NULL,
    signature TEXT NOT NULL,
    ts DOUBLE PRECISION NOT NULL,
    idempotency_key TEXT UNIQUE
);
CREATE INDEX IF NOT EXISTS idx_uni_receipts_wallet_ts ON uni_receipts(wallet_id, ts);
"""

_SCHEMA_V2_SQLITE = """
CREATE TABLE IF NOT EXISTS uni_withdrawals (
    withdrawal_id TEXT PRIMARY KEY,
    wallet_id TEXT NOT NULL,
    amount_uni REAL NOT NULL,
    fee_uni REAL NOT NULL,
    net_usdt REAL NOT NULL,
    payout_chain TEXT NOT NULL,
    payout_token TEXT NOT NULL,
    payout_address TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    tx_hash TEXT,
    error TEXT,
    requested_at REAL NOT NULL,
    completed_at REAL
);
CREATE INDEX IF NOT EXISTS idx_uni_withdrawals_wallet ON uni_withdrawals(wallet_id, status);

CREATE TABLE IF NOT EXISTS uni_treasury_audit (
    snapshot_id TEXT PRIMARY KEY,
    ts REAL NOT NULL,
    total_uni_outstanding REAL NOT NULL,
    total_uni_platform REAL NOT NULL,
    usdt_required REAL NOT NULL,
    usdt_observed_on_chain REAL NOT NULL,
    reserve_ratio REAL NOT NULL,
    healthy INTEGER NOT NULL,
    note TEXT
);
CREATE INDEX IF NOT EXISTS idx_uni_treasury_audit_ts ON uni_treasury_audit(ts DESC);
"""

_RECEIPT_V2_COLUMNS = (
    ("buyer_wallet_id", "TEXT"),
    ("seller_wallet_id", "TEXT"),
    ("platform_fee_uni", "REAL NOT NULL DEFAULT 0"),
    ("net_to_seller_uni", "REAL NOT NULL DEFAULT 0"),
    ("product_id", "TEXT"),
    ("capability_id", "TEXT"),
    ("tx_hash", "TEXT"),
    ("chain", "TEXT"),
    ("hub_id", "TEXT"),
    ("status", "TEXT NOT NULL DEFAULT 'committed'"),
    # OTEL provenance: 32-char lowercase hex W3C trace id captured when the
    # receipt was issued. Lets the receipt holder follow a paid invoke back to
    # the LLM trace in LangSmith / Phoenix / Jaeger.
    ("trace_id", "TEXT"),
)

_WALLET_V2_COLUMNS = (
    ("owner_type", "TEXT NOT NULL DEFAULT 'customer'"),
    ("status", "TEXT NOT NULL DEFAULT 'active'"),
)


def _sqlite_column_names(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {str(r[1]) for r in rows}


def _apply_sqlite_migrations(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA_V2_SQLITE)
    for col, typ in _RECEIPT_V2_COLUMNS:
        if col not in _sqlite_column_names(conn, "uni_receipts"):
            conn.execute(f"ALTER TABLE uni_receipts ADD COLUMN {col} {typ}")
    for col, typ in _WALLET_V2_COLUMNS:
        if col not in _sqlite_column_names(conn, "uni_wallets"):
            conn.execute(f"ALTER TABLE uni_wallets ADD COLUMN {col} {typ}")
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_uni_receipts_tx_kind
        ON uni_receipts(tx_hash, kind) WHERE tx_hash IS NOT NULL AND tx_hash != ''
        """
    )
    conn.executescript(
        """
        CREATE TRIGGER IF NOT EXISTS uni_ledger_no_update
        BEFORE UPDATE ON uni_ledger
        BEGIN
          SELECT RAISE(ABORT, 'uni_ledger is append-only');
        END;
        CREATE TRIGGER IF NOT EXISTS uni_ledger_no_delete
        BEFORE DELETE ON uni_ledger
        BEGIN
          SELECT RAISE(ABORT, 'uni_ledger is append-only');
        END;
        """
    )
    conn.commit()


def _pg_execute_script(conn: Any, script: str) -> None:
    """Run a SQL script statement-by-statement (psycopg executes one statement per call)."""
    buf: list[str] = []
    for line in script.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            continue
        buf.append(line)
        if stripped.endswith(";"):
            stmt = "\n".join(buf).strip()
            buf = []
            if stmt:
                conn.execute(stmt)
    if buf:
        stmt = "\n".join(buf).strip()
        if stmt:
            conn.execute(stmt.rstrip(";"))


def _apply_postgres_migrations(conn: Any) -> None:
    _pg_execute_script(conn, _SCHEMA_V2_SQLITE.replace("REAL", "DOUBLE PRECISION"))
    for col, typ in _RECEIPT_V2_COLUMNS:
        with suppress(Exception):
            conn.execute(
                f"ALTER TABLE uni_receipts ADD COLUMN IF NOT EXISTS {col} {typ.replace('REAL', 'DOUBLE PRECISION')}"
            )
    for col, typ in _WALLET_V2_COLUMNS:
        with suppress(Exception):
            conn.execute(f"ALTER TABLE uni_wallets ADD COLUMN IF NOT EXISTS {col} {typ}")
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_uni_receipts_tx_kind
        ON uni_receipts(tx_hash, kind) WHERE tx_hash IS NOT NULL AND tx_hash != ''
        """
    )
    conn.execute(
        """
        CREATE OR REPLACE FUNCTION uni_ledger_reject_mutation()
        RETURNS trigger AS $$
        BEGIN
          RAISE EXCEPTION 'uni_ledger is append-only';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    conn.execute("DROP TRIGGER IF EXISTS uni_ledger_no_update ON uni_ledger")
    conn.execute(
        """
        CREATE TRIGGER uni_ledger_no_update
        BEFORE UPDATE ON uni_ledger
        FOR EACH ROW EXECUTE PROCEDURE uni_ledger_reject_mutation()
        """
    )
    conn.execute("DROP TRIGGER IF EXISTS uni_ledger_no_delete ON uni_ledger")
    conn.execute(
        """
        CREATE TRIGGER uni_ledger_no_delete
        BEFORE DELETE ON uni_ledger
        FOR EACH ROW EXECUTE PROCEDURE uni_ledger_reject_mutation()
        """
    )
    conn.commit()


_lock = threading.Lock()
_sqlite_conn: sqlite3.Connection | None = None
_pg_pool: Any = None


def _init_sqlite(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA_SQLITE)
    _apply_sqlite_migrations(conn)


def _init_postgres(pool: Any) -> None:
    with pool.connection() as conn:
        _pg_execute_script(conn, _SCHEMA_POSTGRES)
        _apply_postgres_migrations(conn)


def _get_sqlite() -> sqlite3.Connection:
    global _sqlite_conn
    if _sqlite_conn is None:
        path = resolve_uni_db_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        _sqlite_conn = sqlite3.connect(str(path), check_same_thread=False)
        _sqlite_conn.row_factory = sqlite3.Row
        _init_sqlite(_sqlite_conn)
    return _sqlite_conn


def _get_pg_pool() -> Any:
    global _pg_pool
    if _pg_pool is None:
        from psycopg_pool import ConnectionPool

        url = uni_database_url()
        if not url:
            raise RuntimeError("UNI postgres backend requires UNI_DATABASE_URL or DATABASE_URL")
        _pg_pool = ConnectionPool(url, min_size=1, max_size=8, kwargs={"autocommit": False})
        _init_postgres(_pg_pool)
    return _pg_pool


@contextmanager
def uni_connection() -> Iterator[Any]:
    """Yield a DB connection (sqlite3 or psycopg)."""
    backend = uni_db_backend()
    if backend == "postgres":
        pool = _get_pg_pool()
        with pool.connection() as conn:
            yield conn
            conn.commit()
        return
    with _lock:
        conn = _get_sqlite()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def row_to_dict(row: Any) -> dict[str, Any]:
    if row is None:
        return {}
    if isinstance(row, sqlite3.Row):
        return dict(row)
    if isinstance(row, dict):
        return row
    return dict(row)


def dumps_meta(meta: dict[str, Any] | None) -> str:
    return json.dumps(meta or {}, separators=(",", ":"), ensure_ascii=False)


def now_ts() -> float:
    return time.time()
