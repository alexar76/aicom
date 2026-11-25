from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .models import Grant, HubStats, MemoryCreate, MemorySummary, MemoryUnit, ProvenanceState, ScoreResult, TruthState
from .db import Database


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def content_hash(content: str) -> str:
    return "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest()



# Truth Layer statuses a catalog or search offers unless the caller asks otherwise: everything but a
# memory the evidence rejected. TruthStatus in models.py lists all four.
DEFAULT_TRUTH: tuple[str, ...] = ("unverified", "supported", "contested")

class MemoryStore:
    def __init__(self, db_path: str):
        import os
        if not (os.getenv("MEMORY_MARKET_DATABASE_URL") or os.getenv("DATABASE_URL")):
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.connection = Database(db_path, "MEMORY_MARKET_DATABASE_URL")
        self.lock = threading.RLock()
        self._migrate()

    def _migrate(self) -> None:
        with self.connection:
            self.connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS actor_proof_nonces_v2 (
                    audience TEXT NOT NULL, actor_id TEXT NOT NULL, nonce TEXT NOT NULL, expires_at BIGINT NOT NULL,
                    PRIMARY KEY (audience, actor_id, nonce)
                );
                CREATE INDEX IF NOT EXISTS idx_actor_proof_expiry ON actor_proof_nonces_v2(expires_at);
                CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    owner_id TEXT NOT NULL,
                    tags TEXT NOT NULL,
                    visibility TEXT NOT NULL CHECK (visibility IN ('private','shared','public','paid')),
                    price_usdc TEXT,
                    source_refs TEXT NOT NULL,
                    parent_memory_ids TEXT NOT NULL,
                    truth_status TEXT NOT NULL DEFAULT 'unverified',
                    truth_confidence REAL NOT NULL DEFAULT 0,
                    evidence_pack_id TEXT,
                    provenance_status TEXT NOT NULL DEFAULT 'unattested',
                    receipt_id TEXT,
                    lineage_root TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS grants (
                    id TEXT PRIMARY KEY,
                    memory_id TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
                    grantee_id TEXT NOT NULL,
                    granted_by TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    revoked_at TEXT,
                    UNIQUE(memory_id, grantee_id)
                );
                CREATE TABLE IF NOT EXISTS ratings (
                    memory_id TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
                    actor_id TEXT NOT NULL,
                    score INTEGER NOT NULL CHECK (score BETWEEN 1 AND 5),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(memory_id, actor_id)
                );
                CREATE INDEX IF NOT EXISTS idx_memories_visibility_created
                ON memories(visibility, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_memories_owner_created
                ON memories(owner_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_grants_grantee_active
                ON grants(grantee_id, memory_id) WHERE revoked_at IS NULL;
                CREATE TABLE IF NOT EXISTS payment_orders (
                    order_id TEXT PRIMARY KEY,
                    memory_id TEXT NOT NULL REFERENCES memories(id),
                    grantee_id TEXT NOT NULL,
                    price_usdc TEXT NOT NULL,
                    amount_usdc TEXT NOT NULL,
                    amount_raw TEXT NOT NULL,
                    recipient TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    created_unix INTEGER NOT NULL,
                    expires_unix INTEGER NOT NULL,
                    created_block INTEGER NOT NULL,
                    last_scanned_block INTEGER NOT NULL,
                    state TEXT NOT NULL DEFAULT 'pending' CHECK (state IN ('pending','expired','confirmed')),
                    tx_hash TEXT,
                    payer TEXT,
                    paid_block INTEGER,
                    paid_block_hash TEXT,
                    paid_at TEXT,
                    paid_unix INTEGER,
                    late INTEGER NOT NULL DEFAULT 0,
                    grant_id TEXT,
                    last_error TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_payment_orders_open
                ON payment_orders(state, expires_unix);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_payment_orders_tx
                ON payment_orders(tx_hash) WHERE tx_hash IS NOT NULL;
                CREATE TABLE IF NOT EXISTS payment_rate_limits (
                    ip TEXT PRIMARY KEY,
                    minute_start INTEGER NOT NULL,
                    minute_count INTEGER NOT NULL,
                    hour_start INTEGER NOT NULL,
                    hour_count INTEGER NOT NULL
                );
                """
            )
            if self.connection.is_postgres:
                columns = {
                    row["column_name"] for row in self.connection.execute(
                        "SELECT column_name FROM information_schema.columns WHERE table_name = 'payment_orders'"
                    )
                }
            else:
                columns = {row["name"] for row in self.connection.execute("PRAGMA table_info(payment_orders)")}
            if "paid_block_hash" not in columns:
                self.connection.execute("ALTER TABLE payment_orders ADD COLUMN paid_block_hash TEXT")

    def create(self, request: MemoryCreate, owner_id: str) -> MemoryUnit:
        memory_id = "mem_" + uuid4().hex[:24]
        created_at = now()
        with self.connection:
            self.connection.execute(
                """INSERT INTO memories (
                id, title, content, content_hash, owner_id, tags, visibility, price_usdc,
                source_refs, parent_memory_ids, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (memory_id, request.title, request.content, content_hash(request.content), owner_id,
                 json.dumps(request.tags), request.visibility, request.price_usdc,
                 json.dumps(request.source_refs), json.dumps(request.parent_memory_ids), created_at, created_at),
            )
        return self.get_unchecked(memory_id)

    def _rating(self, memory_id: str) -> tuple[float | None, int]:
        row = self.connection.execute(
            "SELECT AVG(score) average, COUNT(*) count FROM ratings WHERE memory_id = ?", (memory_id,)
        ).fetchone()
        return (round(row["average"], 2) if row["average"] is not None else None, row["count"])

    def _unit(self, row: sqlite3.Row) -> MemoryUnit:
        average, count = self._rating(row["id"])
        return MemoryUnit(
            id=row["id"], title=row["title"], content=row["content"], content_hash=row["content_hash"],
            owner_id=row["owner_id"], tags=json.loads(row["tags"]), visibility=row["visibility"],
            price_usdc=row["price_usdc"], source_refs=json.loads(row["source_refs"]),
            parent_memory_ids=json.loads(row["parent_memory_ids"]),
            truth=TruthState(status=row["truth_status"], confidence=row["truth_confidence"], evidence_pack_id=row["evidence_pack_id"]),
            provenance=ProvenanceState(status=row["provenance_status"], receipt_id=row["receipt_id"], lineage_root=row["lineage_root"]),
            average_score=average, score_count=count, created_at=row["created_at"], updated_at=row["updated_at"],
        )

    @staticmethod
    def summary(unit: MemoryUnit) -> MemorySummary:
        return MemorySummary(**unit.model_dump(exclude={"content", "source_refs", "parent_memory_ids"}))

    def get_unchecked(self, memory_id: str) -> MemoryUnit:
        row = self.connection.execute("SELECT * FROM memories WHERE id = ?", (memory_id,)).fetchone()
        if row is None:
            raise KeyError(memory_id)
        return self._unit(row)

    def has_grant(self, memory_id: str, actor_id: str) -> bool:
        return self.connection.execute(
            "SELECT 1 FROM grants WHERE memory_id = ? AND grantee_id = ? AND revoked_at IS NULL",
            (memory_id, actor_id),
        ).fetchone() is not None

    def payment_order(self, order_id: str) -> sqlite3.Row:
        row = self.connection.execute(
            "SELECT payment_orders.*, memories.title AS memory_title FROM payment_orders "
            "JOIN memories ON memories.id = payment_orders.memory_id WHERE order_id = ?",
            (order_id,),
        ).fetchone()
        if row is None:
            raise KeyError(order_id)
        return row

    def claimable_payment_orders(self, grace_floor: int, limit: int = 200) -> list[sqlite3.Row]:
        return self.connection.execute(
            "SELECT payment_orders.*, memories.title AS memory_title FROM payment_orders "
            "JOIN memories ON memories.id = payment_orders.memory_id "
            "WHERE state='pending' OR (state='expired' AND expires_unix > ?) "
            "ORDER BY created_unix LIMIT ?",
            (grace_floor, limit),
        ).fetchall()

    def open_payment_orders_for_grantee(self, grantee_id: str, grace_floor: int) -> int:
        row = self.connection.execute(
            "SELECT COUNT(*) AS count FROM payment_orders WHERE grantee_id = ? "
            "AND (state='pending' OR (state='expired' AND expires_unix > ?))",
            (grantee_id, grace_floor),
        ).fetchone()
        return int(row["count"])

    def confirmed_payment_orders(self, limit: int = 200):
        return self.connection.execute(
            "SELECT * FROM payment_orders WHERE state='confirmed' "
            "AND paid_block IS NOT NULL AND paid_block_hash IS NOT NULL "
            "ORDER BY paid_unix DESC LIMIT ?", (limit,)
        ).fetchall()

    def open_payment_amounts(self, grace_floor: int) -> set[int]:
        rows = self.connection.execute(
            "SELECT amount_raw FROM payment_orders WHERE state='pending' "
            "OR (state='expired' AND expires_unix > ?)", (grace_floor,),
        ).fetchall()
        return {int(row["amount_raw"]) for row in rows}

    def insert_payment_order(self, values: tuple[object, ...]) -> None:
        with self.lock, self.connection:
            self.connection.execute(
                """INSERT INTO payment_orders (
                order_id, memory_id, grantee_id, price_usdc, amount_usdc, amount_raw,
                recipient, created_at, created_unix, expires_unix, created_block,
                last_scanned_block, state
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')""",
                values,
            )

    def expire_payment_orders(self, timestamp: int) -> None:
        with self.lock, self.connection:
            self.connection.execute(
                "UPDATE payment_orders SET state='expired' WHERE state='pending' AND expires_unix < ?",
                (timestamp,),
            )

    def advance_payment_scan(self, end_block: int, grace_floor: int) -> None:
        with self.lock, self.connection:
            self.connection.execute(
                "UPDATE payment_orders SET last_scanned_block=MAX(last_scanned_block, ?) "
                "WHERE state='pending' OR (state='expired' AND expires_unix > ?)",
                (end_block, grace_floor),
            )

    def settle_payment(
        self, order_id: str, tx_hash: str, payer: str, paid_block: int,
        paid_block_hash: str | None, paid_at: str, paid_unix: int, late: bool,
    ) -> bool:
        """Claim one transaction and issue its access grant in one SQLite transaction."""
        with self.lock:
            try:
                with self.connection:
                    row = self.connection.execute(
                        "SELECT memory_id, grantee_id FROM payment_orders "
                        "WHERE order_id=? AND state IN ('pending','expired')", (order_id,),
                    ).fetchone()
                    if row is None:
                        return False
                    claimed = self.connection.execute(
                        "UPDATE payment_orders SET tx_hash=?, payer=?, paid_block=?, paid_block_hash=?, paid_at=?, "
                        "paid_unix=?, late=? WHERE order_id=? AND state IN ('pending','expired')",
                        (tx_hash.lower(), payer.lower(), paid_block, paid_block_hash, paid_at, paid_unix, int(late), order_id),
                    ).rowcount
                    if claimed != 1:
                        return False
                    owner = self.connection.execute(
                        "SELECT owner_id FROM memories WHERE id=?", (row["memory_id"],),
                    ).fetchone()
                    if owner is None:
                        raise RuntimeError("paid memory disappeared before settlement")
                    grant_id = "grant_" + uuid4().hex[:24]
                    granted_at = now()
                    self.connection.execute(
                        """INSERT INTO grants (id, memory_id, grantee_id, granted_by, created_at, revoked_at)
                        VALUES (?, ?, ?, ?, ?, NULL)
                        ON CONFLICT(memory_id, grantee_id) DO UPDATE SET
                        revoked_at=NULL, granted_by=excluded.granted_by, created_at=excluded.created_at""",
                        (grant_id, row["memory_id"], row["grantee_id"], owner["owner_id"], granted_at),
                    )
                    persisted = self.connection.execute(
                        "SELECT id FROM grants WHERE memory_id=? AND grantee_id=?",
                        (row["memory_id"], row["grantee_id"]),
                    ).fetchone()
                    self.connection.execute(
                        "UPDATE payment_orders SET state='confirmed', grant_id=?, last_error=NULL WHERE order_id=?",
                        (persisted["id"], order_id),
                    )
                return True
            except Exception as error:
                # sqlite3 and psycopg expose different exception classes; SQLSTATE
                # 23xxx is the portable integrity/unique-constraint family.
                if isinstance(error, sqlite3.IntegrityError) or getattr(error, "sqlstate", "").startswith("23"):
                    return False
                raise

    def reorg_payment(self, order_id: str) -> None:
        """Remove access granted by a payment whose block left the canonical chain."""
        with self.lock, self.connection:
            row = self.connection.execute(
                "SELECT grant_id, memory_id, grantee_id FROM payment_orders WHERE order_id = ?",
                (order_id,),
            ).fetchone()
            if row is not None:
                if row["grant_id"]:
                    self.connection.execute("DELETE FROM grants WHERE id = ?", (row["grant_id"],))
                self.connection.execute(
                    "UPDATE payment_orders SET state='expired', tx_hash=NULL, payer=NULL, "
                    "paid_block=NULL, paid_block_hash=NULL, paid_at=NULL, paid_unix=NULL, late=0, grant_id=NULL, "
                    "last_error='payment block reorged' WHERE order_id = ?",
                    (order_id,),
                )

    def can_read(self, unit: MemoryUnit, actor_id: str | None, team_id: str | None = None) -> bool:
        if team_id and f"team:{team_id}" in unit.tags and unit.visibility in {"shared", "public", "paid"}:
            return True
        if unit.visibility == "public":
            return True
        if actor_id is None:
            return False
        return actor_id == unit.owner_id or self.has_grant(unit.id, actor_id)

    def catalog(self, query: str, actor_id: str | None, limit: int, offset: int, team_id: str | None = None,
                truth: tuple[str, ...] | None = DEFAULT_TRUTH) -> tuple[list[MemorySummary], int]:
        """Discoverable memories, newest first. ``truth`` keeps only those whose Truth Layer status is
        listed; by default a memory the evidence rejected is not offered as an answer (it can still be
        read by id, with its status). ``None`` applies no truth filter."""
        params: list[object] = []
        access = "(visibility IN ('public','paid'))"
        team_tag = None
        if team_id:
            # LIKE metacharacters in team IDs are data, never other teams.
            escaped_team = team_id.casefold().replace("!", "!!").replace("%", "!%").replace("_", "!_")
            team_tag = f'%"team:{escaped_team}"%'
            access = "(lower(tags) LIKE ? ESCAPE '!' AND visibility IN ('shared','public','paid'))"
            params.append(team_tag)
        elif actor_id:
            access = "(visibility IN ('public','paid') OR owner_id = ? OR id IN (SELECT memory_id FROM grants WHERE grantee_id = ? AND revoked_at IS NULL))"
            params.extend([actor_id, actor_id])
        search = ""
        if query:
            needle = f"%{query.casefold()}%"
            # A catalog may advertise paid memories, but searching their hidden
            # content would let an unpaid caller test arbitrary secret substrings.
            readable = "visibility = 'public'"
            content_params: list[object] = []
            if actor_id:
                readable += " OR owner_id = ? OR id IN (SELECT memory_id FROM grants WHERE grantee_id = ? AND revoked_at IS NULL)"
                content_params.extend([actor_id, actor_id])
            if team_tag is not None:
                readable += " OR (lower(tags) LIKE ? ESCAPE '!' AND visibility IN ('shared','paid'))"
                content_params.append(team_tag)
            search = f" AND (lower(title) LIKE ? OR lower(tags) LIKE ? OR (lower(content) LIKE ? AND ({readable})))"
            params.extend([needle, needle, needle])
            params.extend(content_params)
        if truth is not None:
            search += (" AND truth_status IN (" + ",".join("?" * len(truth)) + ")") if truth else " AND 1=0"
            params.extend(truth)
        count = self.connection.execute(f"SELECT COUNT(*) count FROM memories WHERE {access}{search}", params).fetchone()["count"]
        rows = self.connection.execute(
            f"SELECT * FROM memories WHERE {access}{search} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            [*params, limit, offset],
        ).fetchall()
        return [self.summary(self._unit(row)) for row in rows], count

    def grant(self, memory_id: str, grantee_id: str, actor_id: str) -> Grant:
        unit = self.get_unchecked(memory_id)
        if unit.owner_id != actor_id:
            raise PermissionError("only the owner can grant access")
        grant_id = "grant_" + uuid4().hex[:24]
        created_at = now()
        with self.connection:
            self.connection.execute(
                """INSERT INTO grants (id, memory_id, grantee_id, granted_by, created_at, revoked_at)
                VALUES (?, ?, ?, ?, ?, NULL)
                ON CONFLICT(memory_id, grantee_id) DO UPDATE SET revoked_at = NULL, granted_by = excluded.granted_by, created_at = excluded.created_at""",
                (grant_id, memory_id, grantee_id, actor_id, created_at),
            )
        row = self.connection.execute(
            "SELECT id, memory_id, grantee_id, granted_by, created_at FROM grants WHERE memory_id = ? AND grantee_id = ?",
            (memory_id, grantee_id),
        ).fetchone()
        return Grant(**dict(row))

    def score(self, memory_id: str, actor_id: str, score: int) -> ScoreResult:
        self.get_unchecked(memory_id)
        timestamp = now()
        with self.connection:
            self.connection.execute(
                """INSERT INTO ratings (memory_id, actor_id, score, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(memory_id, actor_id) DO UPDATE SET score = excluded.score, updated_at = excluded.updated_at""",
                (memory_id, actor_id, score, timestamp, timestamp),
            )
        average, count = self._rating(memory_id)
        return ScoreResult(memory_id=memory_id, average_score=average or 0, score_count=count)

    def set_provenance(self, memory_id: str, receipt_id: str, lineage_root: str) -> None:
        with self.connection:
            self.connection.execute(
                "UPDATE memories SET provenance_status='attested', receipt_id=?, lineage_root=?, updated_at=? WHERE id=?",
                (receipt_id, lineage_root, now(), memory_id),
            )

    def unattested(self, limit: int = 200, after_id: str = "") -> list[MemoryUnit]:
        """Units the ledger never confirmed (``provenance_status='unattested'``), oldest id first."""
        rows = self.connection.execute(
            "SELECT * FROM memories WHERE provenance_status='unattested' AND id > ? ORDER BY id LIMIT ?",
            (after_id, limit),
        ).fetchall()
        return [self._unit(row) for row in rows]

    def set_truth(self, memory_id: str, status: str, confidence: float, pack_id: str) -> None:
        with self.connection:
            self.connection.execute(
                "UPDATE memories SET truth_status=?, truth_confidence=?, evidence_pack_id=?, updated_at=? WHERE id=?",
                (status, confidence, pack_id, now(), memory_id),
            )

    def stats(self, actor_id: str | None, payment_enabled: bool) -> HubStats:
        _, discoverable = self.catalog("", actor_id, 1, 0)
        row = self.connection.execute(
            """SELECT
            SUM(CASE WHEN provenance_status='attested' THEN 1 ELSE 0 END) attested,
            SUM(CASE WHEN truth_status!='unverified' THEN 1 ELSE 0 END) verified,
            SUM(CASE WHEN visibility='paid' THEN 1 ELSE 0 END) paid
            FROM memories"""
        ).fetchone()
        return HubStats(
            discoverable_memories=discoverable, attested_memories=row["attested"] or 0,
            verified_memories=row["verified"] or 0, paid_memories=row["paid"] or 0,
            payment_enabled=payment_enabled,
        )
