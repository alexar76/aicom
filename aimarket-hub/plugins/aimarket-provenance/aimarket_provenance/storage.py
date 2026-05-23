"""Provenance receipt storage — SQLite or PostgreSQL via DATABASE_URL.

Follows the DBBackend abstraction for dialect-agnostic queries.
Uses a separate database file/namespace (provenance) to avoid schema coupling.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from aimarket_hub.db_backend import create_backend
from aimarket_hub.migrations import Migrations

from .receipt import ProvenanceReceipt


class ProvenanceStorage:
    """Stores and retrieves ProvenanceReceipts — SQLite or PostgreSQL.

    Args:
        db_path: SQLite path (used when database_url is unset)
        database_url: PostgreSQL connection string (optional)
    """

    def __init__(
        self,
        db_path: str | Path = "data/provenance.db",
        database_url: str = "",
    ):
        self.db_path = Path(db_path)
        self._backend = create_backend(
            database_url=database_url, db_path=db_path,
        )
        Migrations(self._backend).apply(target_version=5)
        self._conn = self._backend  # backward compat alias

    def _migrate(self) -> None:
        pass  # Handled by Migrations in __init__

    def _legacy_migrate(self) -> None:
        self._conn.executescript("""
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

            CREATE INDEX IF NOT EXISTS idx_prov_receipt_id
                ON provenance_receipts(receipt_id);
            CREATE INDEX IF NOT EXISTS idx_prov_model
                ON provenance_receipts(model_id);
            CREATE INDEX IF NOT EXISTS idx_prov_provider
                ON provenance_receipts(provider_hub);
            CREATE INDEX IF NOT EXISTS idx_prov_timestamp
                ON provenance_receipts(timestamp);
        """)
        self._conn.commit()

    def store(self, receipt: ProvenanceReceipt) -> None:
        """Store a receipt. Raises sqlite3.IntegrityError on duplicate receipt_id."""
        raw = json.dumps(receipt.to_dict(), indent=2)
        self._conn.execute(
            """INSERT INTO provenance_receipts
               (receipt_id, model_id, provider_hub, input_hash, output_hash,
                parent_receipts, timestamp, issuer_pubkey_b64, proof_value,
                tee_attestation, latency_ms, price_usd, invocation_nonce,
                reputation_score, raw_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                receipt.receipt_id,
                receipt.model_id,
                receipt.provider_hub,
                receipt.input_hash,
                receipt.output_hash,
                json.dumps(receipt.parent_receipts),
                receipt.timestamp,
                receipt.issuer_public_key_b64,
                receipt.proof_value,
                json.dumps(receipt.tee_attestation) if receipt.tee_attestation else None,
                receipt.latency_ms,
                receipt.price_usd,
                receipt.invocation_nonce,
                receipt.reputation_score,
                raw,
            ),
        )
        self._conn.commit()

    def get_by_receipt_id(self, receipt_id: str) -> ProvenanceReceipt | None:
        row = self._conn.execute(
            "SELECT raw_json FROM provenance_receipts WHERE receipt_id = ?",
            (receipt_id,),
        ).fetchone()
        if not row:
            return None
        return ProvenanceReceipt.from_dict(json.loads(row["raw_json"]))

    def list_receipts(
        self,
        model_id: str | None = None,
        provider_hub: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ProvenanceReceipt]:
        conditions: list[str] = []
        params: list[Any] = []
        if model_id:
            conditions.append("model_id = ?")
            params.append(model_id)
        if provider_hub:
            conditions.append("provider_hub = ?")
            params.append(provider_hub)
        where = " AND ".join(conditions) if conditions else "1=1"
        rows = self._conn.execute(
            f"SELECT raw_json FROM provenance_receipts "
            f"WHERE {where} ORDER BY timestamp DESC LIMIT ? OFFSET ?",
            [*params, limit, offset],
        ).fetchall()
        return [
            ProvenanceReceipt.from_dict(json.loads(r["raw_json"])) for r in rows
        ]

    def count_receipts(self) -> int:
        return self._conn.execute(
            "SELECT COUNT(*) FROM provenance_receipts"
        ).fetchone()[0]

    def close(self) -> None:
        self._backend.close()
