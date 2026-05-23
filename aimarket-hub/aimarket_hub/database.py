"""Database index for capabilities, peers, receipts, and reputation events.

Supports SQLite (default) and PostgreSQL via DATABASE_URL env var.
Uses the DBBackend abstraction for dialect-agnostic queries.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from aimarket_hub.models import Capability, InvocationStat, Peer, ReputationEvent
from aimarket_hub.db_backend import DBBackend, create_backend
from aimarket_hub.migrations import Migrations


class HubDatabase:
    """Hub index database — SQLite or PostgreSQL via DATABASE_URL.

    Args:
        db_path: SQLite path (used when database_url is not set)
        database_url: PostgreSQL connection string (optional)
    """

    def __init__(
        self,
        db_path: str | Path = "data/hub.db",
        database_url: str = "",
    ):
        self.db_path = Path(db_path)
        self._backend: DBBackend = create_backend(
            database_url=database_url, db_path=db_path,
        )
        migrations = Migrations(self._backend)
        migrations.apply()
        self._conn = self._backend  # backward compat for tests

    def _migrate(self) -> None:
        # Keep for backward compat — actual migration runs via Migrations in __init__
        pass

    def _legacy_migrate(self) -> None:
        cur = self._conn.cursor()
        cur.executescript("""
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

            CREATE INDEX IF NOT EXISTS idx_caps_source ON capabilities(source_hub);
            CREATE INDEX IF NOT EXISTS idx_caps_cid ON capabilities(capability_id);
            CREATE INDEX IF NOT EXISTS idx_peers_status ON peers(status);
            CREATE INDEX IF NOT EXISTS idx_stats_ts ON invocation_stats(timestamp);
            CREATE INDEX IF NOT EXISTS idx_reputation_provider ON reputation_events(provider_hub);
        """)
        self._conn.commit()

    # ── Capabilities ──────────────────────────────────────────

    def upsert_capability(self, cap: Capability) -> None:
        self._conn.execute("""
            INSERT OR REPLACE INTO capabilities
                (capability_id, product_id, name, version, description,
                 input_schema, output_schema, price_per_call_usd, p50_latency_ms,
                 success_rate_30d, source_hub, source_hub_name,
                 routed_price_usd, routing_fee_bps, trust_score, agent, prompt_template,
                 updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """, (
            cap.capability_id, cap.product_id, cap.name, cap.version, cap.description,
            json.dumps(cap.input_schema), json.dumps(cap.output_schema),
            cap.price_per_call_usd, cap.p50_latency_ms, cap.success_rate_30d,
            cap.source_hub, cap.source_hub_name,
            cap.routed_price_usd, cap.routing_fee_bps, cap.trust_score,
            cap.agent, cap.prompt_template,
        ))
        self._conn.commit()

    def get_capability(self, product_id: str, capability_id: str, source_hub: str = "local") -> Capability | None:
        row = self._conn.execute(
            "SELECT * FROM capabilities WHERE product_id=? AND capability_id=? AND source_hub=?",
            (product_id, capability_id, source_hub),
        ).fetchone()
        return _row_to_capability(row) if row else None

    def list_capabilities(self, source_hub: str | None = None, limit: int = 200) -> list[Capability]:
        if source_hub:
            rows = self._conn.execute(
                "SELECT * FROM capabilities WHERE source_hub=? ORDER BY trust_score DESC LIMIT ?",
                (source_hub, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM capabilities ORDER BY trust_score DESC LIMIT ?", (limit,)
            ).fetchall()
        return [_row_to_capability(r) for r in rows]

    def search_capabilities(self, query: str, limit: int = 20) -> list[Capability]:
        """Simple keyword search across name and description."""
        terms = [f"%{t}%" for t in query.split() if len(t) > 1]
        if not terms:
            return self.list_capabilities(limit=limit)
        placeholders = " OR ".join(["(name LIKE ? OR description LIKE ?)"] * len(terms))
        params = []
        for t in terms:
            params.extend([t, t])
        rows = self._conn.execute(
            f"SELECT * FROM capabilities WHERE {placeholders} ORDER BY trust_score DESC LIMIT ?",
            [*params, limit],
        ).fetchall()
        return [_row_to_capability(r) for r in rows]

    def count_capabilities(self, source_hub: str | None = None) -> int:
        if source_hub:
            return self._conn.execute(
                "SELECT COUNT(*) FROM capabilities WHERE source_hub=?", (source_hub,)
            ).fetchone()[0]
        return self._conn.execute("SELECT COUNT(*) FROM capabilities").fetchone()[0]

    def count_federated(self) -> int:
        return self._conn.execute(
            "SELECT COUNT(*) FROM capabilities WHERE source_hub != 'local'"
        ).fetchone()[0]

    def clear_federated(self) -> None:
        """Remove all non-local capabilities (before re-crawl)."""
        self._conn.execute("DELETE FROM capabilities WHERE source_hub != 'local'")
        self._conn.commit()

    # ── Peers ─────────────────────────────────────────────────

    def upsert_peer(self, peer: Peer) -> None:
        self._conn.execute("""
            INSERT OR REPLACE INTO peers
                (url, name, capabilities_count, last_crawl, trust_score,
                 well_known_url, manifest_url, public_key, depth, discoverer, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')
        """, (
            peer.url, peer.name, peer.capabilities_count, peer.last_crawl,
            peer.trust_score, peer.well_known_url, peer.manifest_url,
            peer.public_key, peer.depth, peer.discoverer,
        ))
        self._conn.commit()

    def list_peers(self) -> list[Peer]:
        rows = self._conn.execute(
            "SELECT * FROM peers WHERE status='active' ORDER BY trust_score DESC"
        ).fetchall()
        return [_row_to_peer(r) for r in rows]

    def get_peer(self, url: str) -> Peer | None:
        row = self._conn.execute("SELECT * FROM peers WHERE url=?", (url,)).fetchone()
        return _row_to_peer(row) if row else None

    def peer_count(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM peers WHERE status='active'").fetchone()[0]

    # ── Stats ─────────────────────────────────────────────────

    def record_invocation(self, stat: InvocationStat) -> None:
        self._conn.execute("""
            INSERT INTO invocation_stats
                (capability_id, product_id, source_hub, price_usd, latency_ms, success, timestamp, consumer_hub)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            stat.capability_id, stat.product_id, stat.source_hub,
            stat.price_usd, stat.latency_ms, int(stat.success),
            stat.timestamp, stat.consumer_hub,
        ))
        self._conn.commit()

    def recent_stats(self, limit: int = 50) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM invocation_stats ORDER BY timestamp DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def stats_summary(self) -> dict[str, Any]:
        """Aggregate stats for the live ticker."""
        total = self._conn.execute("SELECT COUNT(*) FROM invocation_stats").fetchone()[0]
        success = self._conn.execute(
            "SELECT COUNT(*) FROM invocation_stats WHERE success=1"
        ).fetchone()[0]
        avg_price = self._conn.execute(
            "SELECT AVG(price_usd) FROM invocation_stats"
        ).fetchone()[0] or 0
        avg_latency = self._conn.execute(
            "SELECT AVG(latency_ms) FROM invocation_stats"
        ).fetchone()[0] or 0
        # Revenue per hour (last hour)
        hour_ago = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 3600))
        revenue_hour = self._conn.execute(
            "SELECT COALESCE(SUM(price_usd), 0) FROM invocation_stats WHERE timestamp >= ?",
            (hour_ago,),
        ).fetchone()[0]
        return {
            "total_invocations": total,
            "successful_invocations": success,
            "success_rate": success / total if total > 0 else 0,
            "avg_price_usd": round(avg_price, 4),
            "avg_latency_ms": round(avg_latency, 1),
            "revenue_per_hour_usd": round(revenue_hour, 4),
            "peers_count": self.peer_count(),
            "capabilities_count": self.count_capabilities(),
            "federated_capabilities_count": self.count_federated(),
        }

    # ── Reputation ────────────────────────────────────────────

    def record_reputation_event(self, event: ReputationEvent) -> None:
        self._conn.execute("""
            INSERT INTO reputation_events
                (event_type, provider_hub, capability_id, timestamp, price_usd, latency_ms, consumer_hub, signature)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            event.event_type, event.provider_hub, event.capability_id,
            event.timestamp, event.price_usd, event.latency_ms,
            event.consumer_hub, event.signature,
        ))
        self._conn.commit()

    def reputation_events_for(self, provider_hub: str, limit: int = 100) -> list[ReputationEvent]:
        rows = self._conn.execute(
            "SELECT * FROM reputation_events WHERE provider_hub=? ORDER BY timestamp DESC LIMIT ?",
            (provider_hub, limit),
        ).fetchall()
        return [_row_to_reputation(r) for r in rows]

    # ── Maintenance ───────────────────────────────────────────

    def close(self) -> None:
        self._backend.close()


def _row_to_capability(row: sqlite3.Row) -> Capability:
    d = dict(row)
    return Capability(
        capability_id=d.get("capability_id", ""),
        product_id=d.get("product_id", ""),
        name=d.get("name", ""),
        version=d.get("version", "v1"),
        description=d.get("description", ""),
        input_schema=_json_parse(d.get("input_schema", "{}")),
        output_schema=_json_parse(d.get("output_schema", "{}")),
        price_per_call_usd=d.get("price_per_call_usd", 0.35),
        p50_latency_ms=d.get("p50_latency_ms", 3000),
        success_rate_30d=d.get("success_rate_30d", 0.97),
        source_hub=d.get("source_hub", "local"),
        source_hub_name=d.get("source_hub_name", ""),
        routed_price_usd=d.get("routed_price_usd"),
        routing_fee_bps=d.get("routing_fee_bps", 0),
        trust_score=d.get("trust_score", 0.0),
        agent=d.get("agent", ""),
        prompt_template=d.get("prompt_template", ""),
    )


def _row_to_peer(row: sqlite3.Row) -> Peer:
    d = dict(row)
    return Peer(
        url=d.get("url", ""),
        name=d.get("name", ""),
        capabilities_count=d.get("capabilities_count", 0),
        last_crawl=d.get("last_crawl", ""),
        trust_score=d.get("trust_score", 0.0),
        well_known_url=d.get("well_known_url", ""),
        manifest_url=d.get("manifest_url", ""),
        public_key=d.get("public_key", ""),
        depth=d.get("depth", 0),
        discoverer=d.get("discoverer", ""),
    )


def _row_to_reputation(row: sqlite3.Row) -> ReputationEvent:
    d = dict(row)
    return ReputationEvent(
        event_type=d.get("event_type", ""),
        provider_hub=d.get("provider_hub", ""),
        capability_id=d.get("capability_id"),
        timestamp=d.get("timestamp", ""),
        price_usd=d.get("price_usd", 0),
        latency_ms=d.get("latency_ms", 0),
        consumer_hub=d.get("consumer_hub", ""),
        signature=d.get("signature", ""),
    )


def _json_parse(val: Any) -> dict[str, Any]:
    if isinstance(val, dict):
        return val
    if isinstance(val, str):
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            return {}
    return {}
