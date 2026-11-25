from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .crypto import Signer
from .models import AttestationCreate, Lineage, Receipt, VerifyResult
from .db import Database

GENESIS_ROOT = "sha256:" + "0" * 64


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


class Ledger:
    def __init__(self, db_path: str, signer: Signer):
        import os
        if not (os.getenv("PROVENANCE_LEDGER_DATABASE_URL") or os.getenv("DATABASE_URL")):
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.connection = Database(db_path, "PROVENANCE_LEDGER_DATABASE_URL")
        self.signer = signer
        self.lock = threading.RLock()
        self._migrate()

    def _migrate(self) -> None:
        with self.connection:
            self.connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS receipts (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    id TEXT NOT NULL UNIQUE,
                    memory_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    actor_id TEXT NOT NULL,
                    source_refs TEXT NOT NULL,
                    parent_memory_ids TEXT NOT NULL,
                    metadata TEXT NOT NULL,
                    previous_root TEXT NOT NULL,
                    event_hash TEXT NOT NULL,
                    chain_root TEXT NOT NULL UNIQUE,
                    signature TEXT NOT NULL,
                    public_key TEXT NOT NULL,
                    pq_algorithm TEXT,
                    pq_public_key TEXT,
                    pq_signature TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_receipts_memory_sequence
                ON receipts(memory_id, sequence);
                CREATE TABLE IF NOT EXISTS receipt_heads (
                    memory_id TEXT PRIMARY KEY,
                    chain_root TEXT NOT NULL
                );
                """
            )
            if self.connection.is_postgres:
                columns = {
                    row["column_name"] for row in self.connection.execute(
                        "SELECT column_name FROM information_schema.columns WHERE table_name = 'receipts'"
                    )
                }
            else:
                columns = {row["name"] for row in self.connection.execute("PRAGMA table_info(receipts)")}
            for name in ("pq_algorithm", "pq_public_key", "pq_signature"):
                if name not in columns:
                    self.connection.execute(f"ALTER TABLE receipts ADD COLUMN {name} TEXT")
            if self.connection.is_postgres:
                # Repair databases created by the early SQLite-to-PostgreSQL shim,
                # which translated AUTOINCREMENT away without installing a default.
                self.connection.execute("CREATE SEQUENCE IF NOT EXISTS receipts_sequence_seq")
                self.connection.execute(
                    "ALTER TABLE receipts ALTER COLUMN sequence "
                    "SET DEFAULT nextval('receipts_sequence_seq')"
                )
                self.connection.execute(
                    "SELECT setval('receipts_sequence_seq', COALESCE(MAX(sequence), 1), "
                    "COUNT(*) > 0) FROM receipts"
                )
            self.connection.execute(
                """INSERT INTO receipt_heads(memory_id, chain_root)
                SELECT receipt.memory_id, receipt.chain_root
                FROM receipts receipt
                WHERE receipt.sequence = (
                    SELECT MAX(latest.sequence) FROM receipts latest
                    WHERE latest.memory_id = receipt.memory_id
                )
                ON CONFLICT(memory_id) DO NOTHING"""
            )

    def append(self, request: AttestationCreate) -> Receipt:
        with self.lock, self.connection:
            self.connection.execute(
                "INSERT INTO receipt_heads(memory_id, chain_root) VALUES (?, ?) "
                "ON CONFLICT(memory_id) DO NOTHING",
                (request.memory_id, GENESIS_ROOT),
            )
            lock = " FOR UPDATE" if self.connection.is_postgres else ""
            previous = self.connection.execute(
                "SELECT chain_root FROM receipt_heads WHERE memory_id = ?" + lock,
                (request.memory_id,),
            ).fetchone()
            previous_root = previous["chain_root"]
            receipt_id = "rcpt_" + uuid4().hex[:24]
            created_at = datetime.now(timezone.utc).isoformat()
            event = {
                "id": receipt_id,
                "memory_id": request.memory_id,
                "event_type": request.event_type,
                "content_hash": request.content_hash,
                "actor_id": request.actor_id,
                "source_refs": request.source_refs,
                "parent_memory_ids": request.parent_memory_ids,
                "metadata": request.metadata,
                "created_at": created_at,
            }
            event_hash = sha256(canonical_json(event))
            chain_root = sha256(previous_root + ":" + event_hash)
            signature = self.signer.sign_block(chain_root)
            values = (
                receipt_id,
                request.memory_id,
                request.event_type,
                request.content_hash,
                request.actor_id,
                canonical_json(request.source_refs),
                canonical_json(request.parent_memory_ids),
                canonical_json(request.metadata),
                previous_root,
                event_hash,
                chain_root,
                signature["value"],
                self.signer.public_key,
                signature["pq_algorithm"],
                signature["pq_public_key"],
                signature["pq_value"],
                created_at,
            )
            self.connection.execute(
                """INSERT INTO receipts (
                id, memory_id, event_type, content_hash, actor_id, source_refs,
                parent_memory_ids, metadata, previous_root, event_hash, chain_root,
                signature, public_key, pq_algorithm, pq_public_key, pq_signature, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                values,
            )
            self.connection.execute(
                "UPDATE receipt_heads SET chain_root = ? WHERE memory_id = ?",
                (chain_root, request.memory_id),
            )
        return self.get(receipt_id)

    @staticmethod
    def _receipt(row: sqlite3.Row) -> Receipt:
        return Receipt(
            id=row["id"], memory_id=row["memory_id"], event_type=row["event_type"],
            content_hash=row["content_hash"], actor_id=row["actor_id"],
            source_refs=json.loads(row["source_refs"]),
            parent_memory_ids=json.loads(row["parent_memory_ids"]),
            metadata=json.loads(row["metadata"]), previous_root=row["previous_root"],
            event_hash=row["event_hash"], chain_root=row["chain_root"],
            signature=row["signature"], public_key=row["public_key"], created_at=row["created_at"],
            pq_algorithm=row["pq_algorithm"], pq_public_key=row["pq_public_key"],
            pq_signature=row["pq_signature"],
        )

    def get(self, receipt_id: str) -> Receipt:
        row = self.connection.execute("SELECT * FROM receipts WHERE id = ?", (receipt_id,)).fetchone()
        if row is None:
            raise KeyError(receipt_id)
        return self._receipt(row)

    def lineage(self, memory_id: str) -> Lineage:
        rows = self.connection.execute(
            "SELECT * FROM receipts WHERE memory_id = ? ORDER BY sequence", (memory_id,)
        ).fetchall()
        receipts = [self._receipt(row) for row in rows]
        return Lineage(memory_id=memory_id, chain_root=receipts[-1].chain_root if receipts else None, receipts=receipts)

    def trusted_public_keys(self) -> set[str]:
        """The ledger's Ed25519 key, plus earlier keys listed in PROVENANCE_TRUSTED_PUBLIC_KEYS
        (comma-separated, as receipts carry them) so receipts signed before a key rotation verify."""
        import os
        extra = {k.strip() for k in os.getenv("PROVENANCE_TRUSTED_PUBLIC_KEYS", "").split(",") if k.strip()}
        return {self.signer.public_key} | extra

    def trusted_pq_public_keys(self) -> set[str]:
        """The ledger's ML-DSA-65 key when PQC is on, plus PROVENANCE_TRUSTED_PQ_PUBLIC_KEYS."""
        import os
        extra = {k.strip() for k in os.getenv("PROVENANCE_TRUSTED_PQ_PUBLIC_KEYS", "").split(",") if k.strip()}
        own = {self.signer.pq_public_key} if self.signer.pq_public_key else set()
        return own | extra

    def verify(self, receipt_id: str) -> VerifyResult:
        row = self.connection.execute("SELECT * FROM receipts WHERE id = ?", (receipt_id,)).fetchone()
        if row is None:
            raise KeyError(receipt_id)
        receipt = self._receipt(row)
        event = {
            "id": receipt.id,
            "memory_id": receipt.memory_id,
            "event_type": receipt.event_type,
            "content_hash": receipt.content_hash,
            "actor_id": receipt.actor_id,
            "source_refs": receipt.source_refs,
            "parent_memory_ids": receipt.parent_memory_ids,
            "metadata": receipt.metadata,
            "created_at": receipt.created_at,
        }
        event_ok = sha256(canonical_json(event)) == receipt.event_hash
        root_ok = sha256(receipt.previous_root + ":" + receipt.event_hash) == receipt.chain_root
        signature_ok = Signer.verify(receipt.public_key, receipt.chain_root, receipt.signature)
        pq_signature_ok = Signer.verify_pq(receipt.pq_public_key, receipt.chain_root, receipt.pq_signature)
        previous_row = self.connection.execute(
            "SELECT chain_root FROM receipts WHERE memory_id = ? AND sequence < ? ORDER BY sequence DESC LIMIT 1",
            (receipt.memory_id, row["sequence"]),
        ).fetchone()
        expected_previous = previous_row["chain_root"] if previous_row else GENESIS_ROOT
        link_ok = expected_previous == receipt.previous_root
        # A signature is only evidence if it is the ledger's own: the row carries its public key, so
        # checking against that key alone let anyone who can rewrite a row re-hash and re-sign it.
        signer_ok = receipt.public_key in self.trusted_public_keys() and (
            receipt.pq_public_key is None or receipt.pq_public_key in self.trusted_pq_public_keys()
        )
        # The newest stored receipt of the memory must be the chain head the ledger recorded, so
        # deleting the latest receipts of a chain is not invisible. Both live in this database, so
        # this catches lost or deleted rows, not an attacker who also rewrites receipt_heads; for
        # that, compare with a chain_root kept outside the ledger (the one returned on append).
        head = self.connection.execute(
            "SELECT chain_root FROM receipt_heads WHERE memory_id = ?", (receipt.memory_id,)
        ).fetchone()
        last = self.connection.execute(
            "SELECT chain_root FROM receipts WHERE memory_id = ? ORDER BY sequence DESC LIMIT 1",
            (receipt.memory_id,),
        ).fetchone()
        head_ok = head is not None and last is not None and head["chain_root"] == last["chain_root"]
        checks = {
            "event_hash": event_ok, "chain_root": root_ok, "signature": signature_ok,
            "pq_signature": pq_signature_ok, "previous_link": link_ok,
            "signer_key": signer_ok, "chain_head": head_ok,
        }
        return VerifyResult(receipt_id=receipt.id, valid=all(checks.values()), checks=checks)
