#!/usr/bin/env python3
"""Migrate data from SQLite to PostgreSQL.

Reads all rows from SQLite databases (hub, channels, provenance) and
bulk-inserts into PostgreSQL. Handles type conversions and verifies
row counts after migration.

Usage:
    python scripts/migrate_to_postgres.py \
        --pg-url postgresql://aicom:aicom@localhost:5432/aicom

    python scripts/migrate_to_postgres.py --dry-run
    python scripts/migrate_to_postgres.py --verify-only --pg-url ...
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path


def _connect_pg(url: str):
    """Connect to PostgreSQL with psycopg."""
    import psycopg
    from psycopg.rows import dict_row
    return psycopg.connect(url, row_factory=dict_row)


def _migrate_table(
    pg_conn,
    table: str,
    rows: list[dict],
    columns: list[str],
    conflict_cols: list[str],
    json_cols: list[str] | None = None,
) -> int:
    """Bulk-insert rows into PostgreSQL with ON CONFLICT handling.

    Args:
        pg_conn: psycopg connection
        table: table name
        rows: list of row dicts
        columns: column names
        conflict_cols: columns for ON CONFLICT clause
        json_cols: columns to serialize as JSON (for SQLite TEXT → PG JSONB)

    Returns:
        Number of rows inserted
    """
    json_cols = json_cols or []
    col_str = ", ".join(columns)
    placeholders = ", ".join(["%s"] * len(columns))
    conflict = ", ".join(conflict_cols)
    set_clause = ", ".join(
        f"{c} = EXCLUDED.{c}" for c in columns if c not in conflict_cols
    )

    sql = (
        f"INSERT INTO {table} ({col_str}) VALUES ({placeholders}) "
        f"ON CONFLICT ({conflict}) DO UPDATE SET {set_clause}"
    )

    values = []
    for row in rows:
        vals = []
        for col in columns:
            val = row.get(col)
            if col in json_cols and isinstance(val, str) and val.strip():
                try:
                    val = json.dumps(json.loads(val))  # validate + normalize JSON
                except (json.JSONDecodeError, TypeError):
                    pass
            vals.append(val)
        values.append(tuple(vals))

    with pg_conn:
        with pg_conn.cursor() as cur:
            cur.executemany(sql, values)

    return len(rows)


def migrate(args: argparse.Namespace) -> int:
    """Run the full migration."""
    pg_conn = _connect_pg(args.pg_url)
    print(f"Connected to PostgreSQL: {args.pg_url.split('@')[-1]}")

    # ── Hub DB ──────────────────────────────────────────────────────
    hub_db = args.sqlite_db
    if os.path.isfile(hub_db):
        sq = sqlite3.connect(hub_db)
        sq.row_factory = sqlite3.Row
        print(f"\n--- Hub database: {hub_db} ---")

        # capabilities
        rows = [dict(r) for r in sq.execute("SELECT * FROM capabilities").fetchall()]
        cols = [
            "capability_id", "product_id", "name", "version", "description",
            "input_schema", "output_schema", "price_per_call_usd",
            "p50_latency_ms", "success_rate_30d", "source_hub",
            "source_hub_name", "routed_price_usd", "routing_fee_bps",
            "trust_score", "agent", "prompt_template",
        ]
        if not args.dry_run:
            n = _migrate_table(pg_conn, "capabilities", rows, cols,
                              ["capability_id", "product_id", "source_hub"],
                              json_cols=["input_schema", "output_schema"])
        else:
            n = len(rows)
        print(f"  capabilities: {n} rows [{'DRY RUN' if args.dry_run else 'OK'}]")

        # peers
        rows = [dict(r) for r in sq.execute("SELECT * FROM peers").fetchall()]
        cols = [
            "url", "name", "capabilities_count", "last_crawl", "trust_score",
            "well_known_url", "manifest_url", "public_key", "depth",
            "discoverer", "status",
        ]
        if not args.dry_run:
            n = _migrate_table(pg_conn, "peers", rows, cols, ["url"])
        else:
            n = len(rows)
        print(f"  peers: {n} rows [{'DRY RUN' if args.dry_run else 'OK'}]")

        # invocation_stats
        rows = [dict(r) for r in sq.execute("SELECT * FROM invocation_stats").fetchall()]
        cols = [
            "capability_id", "product_id", "source_hub", "price_usd",
            "latency_ms", "success", "timestamp", "consumer_hub",
        ]
        if not args.dry_run:
            n = _migrate_table(pg_conn, "invocation_stats", rows, cols, [])
        else:
            n = len(rows)
        print(f"  invocation_stats: {n} rows [{'DRY RUN' if args.dry_run else 'OK'}]")

        # reputation_events
        rows = [dict(r) for r in sq.execute("SELECT * FROM reputation_events").fetchall()]
        cols = [
            "event_type", "provider_hub", "capability_id", "timestamp",
            "price_usd", "latency_ms", "consumer_hub", "signature",
        ]
        if not args.dry_run:
            n = _migrate_table(pg_conn, "reputation_events", rows, cols, [])
        else:
            n = len(rows)
        print(f"  reputation_events: {n} rows [{'DRY RUN' if args.dry_run else 'OK'}]")

        sq.close()

    # ── Channels DB ─────────────────────────────────────────────────
    channels_db = args.sqlite_channels
    if os.path.isfile(channels_db):
        sq = sqlite3.connect(channels_db)
        sq.row_factory = sqlite3.Row
        print(f"\n--- Channels database: {channels_db} ---")

        rows = [dict(r) for r in sq.execute("SELECT * FROM channels").fetchall()]
        cols = [
            "channel_id", "balance_cents", "original_deposit_cents",
            "used_cents", "token", "chain", "wallet", "tx_hash",
            "recipient", "status", "opened_at", "expires_at",
            "settle_tx_hash", "closed_at",
        ]
        if not args.dry_run:
            n = _migrate_table(pg_conn, "channels", rows, cols, ["channel_id"])
        else:
            n = len(rows)
        print(f"  channels: {n} rows [{'DRY RUN' if args.dry_run else 'OK'}]")

        rows = [dict(r) for r in sq.execute("SELECT * FROM debited_receipts").fetchall()]
        cols = ["receipt_id", "channel_id", "amount_cents", "timestamp"]
        if not args.dry_run:
            n = _migrate_table(pg_conn, "debited_receipts", rows, cols, ["receipt_id"])
        else:
            n = len(rows)
        print(f"  debited_receipts: {n} rows [{'DRY RUN' if args.dry_run else 'OK'}]")

        sq.close()

    # ── Provenance DB ───────────────────────────────────────────────
    prov_db = args.sqlite_provenance
    if os.path.isfile(prov_db):
        sq = sqlite3.connect(prov_db)
        sq.row_factory = sqlite3.Row
        print(f"\n--- Provenance database: {prov_db} ---")

        rows = [dict(r) for r in sq.execute("SELECT * FROM provenance_receipts").fetchall()]
        cols = [
            "receipt_id", "model_id", "provider_hub", "input_hash",
            "output_hash", "parent_receipts", "timestamp",
            "issuer_pubkey_b64", "proof_value", "tee_attestation",
            "latency_ms", "price_usd", "invocation_nonce",
            "reputation_score", "raw_json",
        ]
        if not args.dry_run:
            n = _migrate_table(pg_conn, "provenance_receipts", rows, cols,
                              ["receipt_id"],
                              json_cols=["parent_receipts", "tee_attestation", "raw_json"])
        else:
            n = len(rows)
        print(f"  provenance_receipts: {n} rows [{'DRY RUN' if args.dry_run else 'OK'}]")

        sq.close()

    pg_conn.close()
    print("\nMigration complete.")
    return 0


def verify(args: argparse.Namespace) -> int:
    """Verify row counts match between SQLite and PG."""
    pg_conn = _connect_pg(args.pg_url)
    print(f"Connected to PostgreSQL: {args.pg_url.split('@')[-1]}")
    print("\nRow count verification:\n")
    print(f"{'Table':<25} {'SQLite':>8} {'PG':>8} {'Status':>10}")
    print("-" * 55)

    tables = {
        "capabilities": args.sqlite_db,
        "peers": args.sqlite_db,
        "invocation_stats": args.sqlite_db,
        "reputation_events": args.sqlite_db,
        "channels": args.sqlite_channels,
        "debited_receipts": args.sqlite_channels,
        "provenance_receipts": args.sqlite_provenance,
    }

    for table, db_path in tables.items():
        sqlite_count = 0
        if os.path.isfile(db_path):
            sq = sqlite3.connect(db_path)
            sq.row_factory = sqlite3.Row
            try:
                sqlite_count = sq.execute(f"SELECT COUNT(*) as c FROM {table}").fetchone()["c"]
            except sqlite3.OperationalError:
                pass
            sq.close()

        pg_count = 0
        try:
            with pg_conn:
                with pg_conn.cursor() as cur:
                    cur.execute(f"SELECT COUNT(*) as c FROM {table}")
                    pg_count = cur.fetchone()["c"]
        except Exception:
            pass

        match = "✓" if sqlite_count == pg_count else "✗ MISMATCH"
        print(f"{table:<25} {sqlite_count:>8} {pg_count:>8} {match:>10}")

    pg_conn.close()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Migrate SQLite data to PostgreSQL"
    )
    parser.add_argument(
        "--pg-url",
        default=os.environ.get("DATABASE_URL", ""),
        help="PostgreSQL connection string (or set DATABASE_URL)",
    )
    parser.add_argument(
        "--sqlite-db",
        default="data/hub.db",
        help="Path to SQLite hub database",
    )
    parser.add_argument(
        "--sqlite-channels",
        default="data/channels.db",
        help="Path to SQLite channels database",
    )
    parser.add_argument(
        "--sqlite-provenance",
        default="data/provenance.db",
        help="Path to SQLite provenance database",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would be migrated without writing",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Only verify row counts between SQLite and PG",
    )

    args = parser.parse_args()

    if args.verify_only:
        if not args.pg_url:
            print("Error: --pg-url required for --verify-only")
            return 1
        return verify(args)

    if not args.dry_run and not args.pg_url:
        print("Error: --pg-url required (or set DATABASE_URL)")
        return 1

    return migrate(args)


if __name__ == "__main__":
    raise SystemExit(main())
