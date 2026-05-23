"""Versioned database migrations for AIMarket Hub.

Manages schema creation and upgrades across SQLite and PostgreSQL.
Each migration has up/down SQL written for SQLite. The PostgresBackend
automatically translates SQL via sqlite_to_pg().

A `_migrations` table tracks applied versions.

CLI usage:
    python -m aimarket_hub.migrations up       # Apply pending migrations
    python -m aimarket_hub.migrations down     # Roll back last migration
    python -m aimarket_hub.migrations status   # Show migration status
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any

from aimarket_hub.db_backend import DBBackend, create_backend

logger = logging.getLogger(__name__)

# ── Migration Registry ──────────────────────────────────────────────

MIGRATIONS: list[tuple[int, str, str, str]] = []


def _register(version: int, name: str, up: str, down: str) -> None:
    MIGRATIONS.append((version, name, up, down))


# All DDL is written for SQLite. PostgresBackend.executescript()
# translates to PostgreSQL dialect automatically (sqlite_to_pg):
#   INTEGER PRIMARY KEY AUTOINCREMENT → SERIAL PRIMARY KEY
#   REAL → DOUBLE PRECISION
#   datetime('now') → NOW()
#   INSERT OR REPLACE → INSERT ... ON CONFLICT DO UPDATE
#   PRAGMA → (removed for PG)

# 001: Core hub tables (capabilities, peers)
_register(1, "001_core_tables", """
CREATE TABLE IF NOT EXISTS capabilities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    capability_id TEXT NOT NULL,
    product_id TEXT NOT NULL,
    name TEXT NOT NULL,
    version TEXT NOT NULL DEFAULT 'v1',
    description TEXT DEFAULT '',
    input_schema TEXT DEFAULT '{}',
    output_schema TEXT DEFAULT '{}',
    price_per_call_usd REAL DEFAULT 0.35,
    p50_latency_ms INTEGER DEFAULT 3000,
    success_rate_30d REAL DEFAULT 0.97,
    source_hub TEXT NOT NULL,
    source_hub_name TEXT DEFAULT '',
    routed_price_usd REAL,
    routing_fee_bps INTEGER DEFAULT 0,
    trust_score REAL DEFAULT 0.0,
    agent TEXT DEFAULT '',
    prompt_template TEXT DEFAULT '',
    updated_at TEXT DEFAULT (datetime('now')),
    UNIQUE(capability_id, product_id, source_hub)
);

CREATE INDEX IF NOT EXISTS idx_caps_source ON capabilities(source_hub);
CREATE INDEX IF NOT EXISTS idx_caps_cid ON capabilities(capability_id);

CREATE TABLE IF NOT EXISTS peers (
    url TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    capabilities_count INTEGER DEFAULT 0,
    last_crawl TEXT DEFAULT '',
    trust_score REAL DEFAULT 0.0,
    well_known_url TEXT DEFAULT '',
    manifest_url TEXT DEFAULT '',
    public_key TEXT DEFAULT '',
    depth INTEGER DEFAULT 0,
    discoverer TEXT DEFAULT '',
    status TEXT DEFAULT 'active'
);

CREATE INDEX IF NOT EXISTS idx_peers_status ON peers(status);
""", """
DROP TABLE IF EXISTS capabilities;
DROP TABLE IF EXISTS peers;
""")

# 002: Invocation stats
_register(2, "002_invocation_stats", """
CREATE TABLE IF NOT EXISTS invocation_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    capability_id TEXT NOT NULL,
    product_id TEXT NOT NULL,
    source_hub TEXT NOT NULL,
    price_usd REAL DEFAULT 0,
    latency_ms INTEGER DEFAULT 0,
    success INTEGER DEFAULT 0,
    timestamp TEXT DEFAULT (datetime('now')),
    consumer_hub TEXT DEFAULT 'local'
);

CREATE INDEX IF NOT EXISTS idx_stats_ts ON invocation_stats(timestamp);
""", """
DROP TABLE IF EXISTS invocation_stats;
""")

# 003: Reputation events
_register(3, "003_reputation_events", """
CREATE TABLE IF NOT EXISTS reputation_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    provider_hub TEXT NOT NULL,
    capability_id TEXT,
    timestamp TEXT DEFAULT (datetime('now')),
    price_usd REAL DEFAULT 0,
    latency_ms INTEGER DEFAULT 0,
    consumer_hub TEXT NOT NULL,
    signature TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_reputation_provider ON reputation_events(provider_hub);
""", """
DROP TABLE IF EXISTS reputation_events;
""")

# 004: Payment channels
_register(4, "004_channels", """
CREATE TABLE IF NOT EXISTS channels (
    channel_id TEXT PRIMARY KEY,
    balance_cents INTEGER NOT NULL,
    original_deposit_cents INTEGER NOT NULL,
    used_cents INTEGER NOT NULL DEFAULT 0,
    token TEXT NOT NULL DEFAULT 'USDT',
    chain TEXT NOT NULL DEFAULT 'base',
    wallet TEXT NOT NULL DEFAULT '',
    tx_hash TEXT NOT NULL DEFAULT '',
    recipient TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'open',
    opened_at TEXT NOT NULL DEFAULT (datetime('now')),
    expires_at TEXT NOT NULL,
    settle_tx_hash TEXT NOT NULL DEFAULT '',
    closed_at TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_channels_status ON channels(status);
CREATE INDEX IF NOT EXISTS idx_channels_wallet ON channels(wallet);
CREATE INDEX IF NOT EXISTS idx_channels_expires ON channels(expires_at) WHERE status = 'open';

CREATE TABLE IF NOT EXISTS debited_receipts (
    receipt_id TEXT PRIMARY KEY,
    channel_id TEXT NOT NULL,
    amount_cents INTEGER NOT NULL,
    timestamp TEXT NOT NULL DEFAULT (datetime('now'))
);
""", """
DROP TABLE IF EXISTS debited_receipts;
DROP TABLE IF EXISTS channels;
""")

# 005: Provenance receipts
_register(5, "005_provenance_receipts", """
CREATE TABLE IF NOT EXISTS provenance_receipts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    receipt_id TEXT NOT NULL UNIQUE,
    model_id TEXT NOT NULL,
    provider_hub TEXT NOT NULL,
    input_hash TEXT NOT NULL,
    output_hash TEXT NOT NULL,
    parent_receipts TEXT DEFAULT '[]',
    timestamp TEXT NOT NULL,
    issuer_pubkey_b64 TEXT NOT NULL,
    proof_value TEXT NOT NULL,
    tee_attestation TEXT,
    latency_ms INTEGER DEFAULT 0,
    price_usd REAL DEFAULT 0.0,
    invocation_nonce TEXT DEFAULT '',
    reputation_score REAL,
    raw_json TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_prov_receipt_id ON provenance_receipts(receipt_id);
CREATE INDEX IF NOT EXISTS idx_prov_model ON provenance_receipts(model_id);
CREATE INDEX IF NOT EXISTS idx_prov_provider ON provenance_receipts(provider_hub);
CREATE INDEX IF NOT EXISTS idx_prov_timestamp ON provenance_receipts(timestamp);
""", """
DROP TABLE IF EXISTS provenance_receipts;
""")


# ── Migrations Manager ──────────────────────────────────────────────


class Migrations:
    """Apply and track database migrations."""

    def __init__(self, backend: DBBackend):
        self._backend = backend
        self._ensure_migrations_table()

    def _ensure_migrations_table(self) -> None:
        try:
            self._backend.execute(
                "CREATE TABLE IF NOT EXISTS _migrations ("
                "  version INTEGER PRIMARY KEY,"
                "  name TEXT NOT NULL,"
                "  applied_at TEXT DEFAULT (datetime('now'))"
                ")"
            )
            self._backend.commit()
        except Exception as exc:
            logger.warning("Could not create _migrations table: %s", exc)

    def applied_versions(self) -> set[int]:
        try:
            self._backend.execute("SELECT version FROM _migrations ORDER BY version")
            rows = self._backend.fetchall()
            return {r["version"] for r in rows}
        except Exception:
            return set()

    def pending(self) -> list[tuple[int, str, str, str]]:
        applied = self.applied_versions()
        return [m for m in MIGRATIONS if m[0] not in applied]

    def apply(self, target_version: int | None = None) -> int:
        pending = self.pending()
        if target_version is not None:
            pending = [m for m in pending if m[0] <= target_version]

        applied_count = 0
        for version, name, sql_up, _ in sorted(pending, key=lambda m: m[0]):
            logger.info("Applying migration %03d: %s", version, name)
            # Atomic: schema change + _migrations bookkeeping in ONE commit.
            # Previous two-commit pattern allowed crash between them, leaving
            # schema applied but not registered → next start would re-apply
            # and potentially double-INSERT seed data (EXP-77).
            try:
                self._backend.executescript(sql_up)
                self._backend.execute(
                    "INSERT INTO _migrations (version, name) VALUES (?, ?)",
                    (version, name),
                )
                self._backend.commit()
                applied_count += 1
                logger.info("  OK %03d", version)
            except Exception as exc:
                logger.error("  FAILED %03d: %s", version, exc)
                raise
        return applied_count

    def rollback(self, steps: int = 1) -> int:
        self._backend.execute(
            "SELECT version, name FROM _migrations ORDER BY version DESC LIMIT ?",
            (steps,),
        )
        rows = self._backend.fetchall()
        rolled = 0
        for row in reversed(rows):
            version = int(row["version"])
            name = row["name"]
            for v, n, _, sql_down in MIGRATIONS:
                if v == version:
                    logger.info("Rolling back %03d: %s", version, name)
                    self._backend.executescript(sql_down)
                    self._backend.execute(
                        "DELETE FROM _migrations WHERE version = ?",
                        (version,),
                    )
                    self._backend.commit()
                    rolled += 1
                    break
        return rolled

    def status(self) -> list[dict[str, Any]]:
        applied = self.applied_versions()
        return [
            {"version": v, "name": n, "applied": v in applied}
            for v, n, _, _ in sorted(MIGRATIONS, key=lambda m: m[0])
        ]


# ── CLI ─────────────────────────────────────────────────────────────


def _cli() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    database_url = os.environ.get("DATABASE_URL", "")
    db_path = os.environ.get("AIMARKET_DB_PATH", "data/hub.db")
    backend = create_backend(database_url=database_url, db_path=db_path)
    migrations = Migrations(backend)

    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"

    if cmd == "up":
        count = migrations.apply()
        print(f"\nApplied {count} migration(s)")
    elif cmd == "down":
        steps = int(sys.argv[2]) if len(sys.argv) > 2 else 1
        count = migrations.rollback(steps)
        print(f"\nRolled back {count} migration(s)")
    elif cmd == "status":
        rows = migrations.status()
        print(f"\nBackend: {backend.backend_type}")
        print(f"{'Version':>8}  {'Name':<30}  {'Status'}")
        print("-" * 55)
        for r in rows:
            s = "OK" if r["applied"] else "PENDING"
            print(f"{r['version']:>8}  {r['name']:<30}  {s}")
    else:
        print(f"Usage: python -m aimarket_hub.migrations [up|down|status]")
        sys.exit(1)

    backend.close()


if __name__ == "__main__":
    _cli()
