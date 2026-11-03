"""Database index for capabilities, peers, receipts, and reputation events.

Supports SQLite (default) and PostgreSQL via DATABASE_URL env var.
Uses the DBBackend abstraction for dialect-agnostic queries.
"""

from __future__ import annotations

import contextlib
import json
import math
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from aimarket_hub.db_backend import DBBackend, create_backend
from aimarket_hub.ecosystem import valid_caller_class
from aimarket_hub.invoke_outcome import normalize_outcome, scored_success_rate
from aimarket_hub.migrations import Migrations
from aimarket_hub.models import (
    Capability,
    InvocationStat,
    Peer,
    ReputationEvent,
    normalize_purpose,
)
from aimarket_hub.semantic_search import SearchMatch, rank_capabilities
from aimarket_hub.paging import page_limit


# Permission-violation reports read for one capability.
VIOLATION_REPORTS_MAX = 64

# Recent supply-chain audits one read may return.
SUPPLY_AUDITS_RECENT_MAX = 100

# Pending supply-chain audits one refresh may take.
SUPPLY_AUDITS_PENDING_MAX = 20


def _utc_cutoff(seconds_ago: float) -> str:
    """A UTC cutoff timestamp in SQLite's ``datetime()`` text format, computed in Python.

    Time-window queries compare ``created_at >= _utc_cutoff(...)`` instead of
    ``created_at >= datetime('now', ?)`` / ``julianday()`` so they are backend-portable:
    both SQLite and PostgreSQL compare the fixed ``YYYY-MM-DD HH:MM:SS`` prefix as TEXT
    (which sorts chronologically), and neither needs a dialect-specific date function the
    ``sqlite_to_pg`` translator cannot rewrite (the modifier is a bound param). The window
    is clamped non-negative so a misconfigured negative value can't invert the comparison."""
    secs = max(0.0, float(seconds_ago))
    return (datetime.now(timezone.utc) - timedelta(seconds=secs)).strftime("%Y-%m-%d %H:%M:%S")


def _parse_db_ts(value: Any) -> datetime | None:
    """Parse a stored ``created_at`` (SQLite ``YYYY-MM-DD HH:MM:SS`` or a PostgreSQL text
    variant with a sub-second / ``+00`` suffix) as UTC, reading the leading 19 chars."""
    s = str(value or "")
    if len(s) < 19:
        return None
    try:
        return datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


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
        self._backend: DBBackend = create_backend(
            database_url=database_url, db_path=db_path,
        )
        # The file the backend ACTUALLY opened, not the argument we asked for. For the
        # bare `HubDatabase()` shape the argument is the hub default, which means "no
        # subsystem chose a path" — create_backend then lets AIMARKET_DB_PATH name the
        # file, so storing the argument here reported `data/hub.db` while every read and
        # write went to the env-var file. Anything using this attribute is doing
        # diagnostics (health endpoints, backup/migration tooling, log lines), and a
        # diagnostic that names the wrong file is worse than no diagnostic.
        resolved = getattr(self._backend, "db_path", None)
        # PostgreSQL has no file at all: keep the requested path as an inert record rather
        # than inventing one, and let `backend_type` say which world we are in.
        self.db_path = Path(resolved) if resolved is not None else Path(db_path)
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
                invoke_url TEXT DEFAULT '',
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
                consumer_hub TEXT DEFAULT 'local',
                outcome TEXT NOT NULL DEFAULT 'fail'
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
            CREATE INDEX IF NOT EXISTS idx_reputation_sig ON reputation_events(consumer_hub, signature);
        """)
        self._conn.commit()
        self._legacy_add_columns()

    def _legacy_add_columns(self) -> None:
        """Add columns introduced after first release (idempotent).

        Only reachable from :meth:`_legacy_migrate`. It used to be a second
        ``_migrate`` further down the class body, which silently shadowed the
        no-op above — so ``_migrate()`` ran raw SQLite ``ALTER TABLE``s (and
        swallowed only ``sqlite3.OperationalError``, which a Postgres backend
        never raises) instead of the documented no-op.
        """
        try:
            self._conn.execute("ALTER TABLE capabilities ADD COLUMN invoke_url TEXT DEFAULT ''")
            self._conn.commit()
        except sqlite3.OperationalError:
            pass
        try:
            self._conn.execute("ALTER TABLE capabilities ADD COLUMN is_demo INTEGER DEFAULT 0")
            self._conn.commit()
        except sqlite3.OperationalError:
            pass

    # ── Capabilities ──────────────────────────────────────────

    def upsert_capability(self, cap: Capability) -> None:
        self._conn.execute("""
            INSERT OR REPLACE INTO capabilities
                (capability_id, product_id, name, version, description,
                 input_schema, output_schema, price_per_call_usd, p50_latency_ms,
                 success_rate_30d, source_hub, source_hub_name,
                 routed_price_usd, routing_fee_bps, trust_score, agent, prompt_template,
                 invoke_url, publisher_id, payout_address, provider_pubkey, stake_usd, is_demo,
                 peer_endpoint, catalogue_evidence, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """, (
            cap.capability_id, cap.product_id, cap.name, cap.version, cap.description,
            json.dumps(cap.input_schema), json.dumps(cap.output_schema),
            cap.price_per_call_usd, cap.p50_latency_ms, cap.success_rate_30d,
            cap.source_hub, cap.source_hub_name,
            cap.routed_price_usd, cap.routing_fee_bps, cap.trust_score,
            cap.agent, cap.prompt_template, cap.invoke_url or "",
            cap.publisher_id or "", cap.payout_address or "",
            cap.provider_pubkey or "", cap.stake_usd or 0.0,
            1 if cap.is_demo else 0,
            cap.peer_endpoint or "",
            json.dumps(cap.catalogue_evidence),
        ))
        self._conn.commit()

    def get_capability(self, product_id: str, capability_id: str, source_hub: str = "local") -> Capability | None:
        row = self._conn.execute(
            "SELECT * FROM capabilities WHERE product_id=? AND capability_id=? AND source_hub=?",
            (product_id, capability_id, source_hub),
        ).fetchone()
        return _row_to_capability(row) if row else None

    def find_by_capability_id(self, capability_id: str) -> Capability | None:
        """Best match when callers omit or mis-specify product_id (federated oracle caps)."""
        row = self._conn.execute(
            "SELECT * FROM capabilities WHERE capability_id=? ORDER BY trust_score DESC LIMIT 1",
            (capability_id,),
        ).fetchone()
        return _row_to_capability(row) if row else None

    def list_capabilities(self, source_hub: str | None = None, limit: int | None = 200) -> list[Capability]:
        if limit is not None and limit <= 0:
            return []
        if source_hub:
            sql = "SELECT * FROM capabilities WHERE source_hub=? ORDER BY trust_score DESC"
            params: list[Any] = [source_hub]
        else:
            sql = "SELECT * FROM capabilities ORDER BY trust_score DESC"
            params = []
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        return [_row_to_capability(r) for r in self._conn.execute(sql, params).fetchall()]

    def list_capabilities_diverse(self, limit: int | None = 20) -> list[Capability]:
        """Browse catalogue without letting one high-trust peer monopolise the page.

        Empty-intent search used to be pure ``ORDER BY trust_score DESC``, so Platon (0.5)
        filled every slot and GAIA live relays never appeared on first paint. Round-robin
        across ``source_hub`` keeps trust ordering *within* each hub.
        ``limit=None`` returns the whole index in that order — browse must not hide SKUs.
        """
        if limit is not None and limit <= 0:
            return []
        if limit is None:
            rows = self._conn.execute(
                "SELECT * FROM capabilities ORDER BY trust_score DESC"
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM capabilities ORDER BY trust_score DESC LIMIT ?",
                (max(limit * 20, 200),),
            ).fetchall()
        by_hub: dict[str, list[Any]] = {}
        for row in rows:
            hub = str(row["source_hub"] or "local")
            by_hub.setdefault(hub, []).append(row)
        # Prefer hubs that already have something to sell first (stable alpha as tiebreak).
        hubs = sorted(by_hub.keys(), key=lambda h: (-len(by_hub[h]), h))
        out: list[Capability] = []
        idx = 0
        while limit is None or len(out) < limit:
            progressed = False
            for hub in hubs:
                bucket = by_hub[hub]
                if idx < len(bucket):
                    out.append(_row_to_capability(bucket[idx]))
                    progressed = True
                    if limit is not None and len(out) >= limit:
                        break
            if not progressed:
                break
            idx += 1
        return out

    def search_capabilities_detailed(self, query: str, limit: int | None = 20) -> list[SearchMatch]:
        """Hybrid multilingual intent search with an explanation for every result.

        Exact IDs remain deterministic, while natural-language requests are matched over
        EN/RU/ES/FR/ZH descriptions and sparse intent concepts.  Empty intent is catalogue
        browsing, not a relevance claim, so it retains the cross-hub round-robin.
        """
        if limit is not None and limit <= 0:
            return []
        if not str(query or "").strip():
            return [
                SearchMatch(
                    capability=cap,
                    score=0.0,
                    lexical_score=0.0,
                    semantic_score=0.0,
                    quality_score=0.0,
                    match_type="browse",
                    matched_concepts=(),
                    matched_terms=(),
                )
                for cap in self.list_capabilities_diverse(limit=limit)
            ]

        # Rank the live index in memory. A fixed 5,000 ceiling hid later federated
        # SKUs the same way the /search ``limit=100`` clamp did.
        capabilities = self.list_capabilities(limit=None)
        _interpretation, matches = rank_capabilities(query, capabilities, limit=None)
        # A capability that answers every request with the same document ranks after every one whose
        # answer depends on the request, before the page is cut: demoted, never removed.
        from aimarket_hub import answer_dependence

        matches = answer_dependence.demote(matches, answer_dependence.independent_keys(self))
        return matches if limit is None else matches[:limit]

    def search_capabilities_ranked(
        self, query: str, limit: int = 20
    ) -> list[tuple[Capability, float]]:
        """Backward-compatible ``(Capability, score)`` view of semantic matches."""
        return [(match.capability, match.score) for match in self.search_capabilities_detailed(query, limit)]

    def search_capabilities(self, query: str, limit: int = 20) -> list[Capability]:
        """Return capabilities from the hybrid multilingual ranking."""
        return [c for c, _ in self.search_capabilities_ranked(query, limit=limit)]

    def count_capabilities(self, source_hub: str | None = None) -> int:
        if source_hub:
            return self._conn.execute(
                "SELECT COUNT(*) FROM capabilities WHERE source_hub=?", (source_hub,)
            ).fetchone()[0]
        return self._conn.execute("SELECT COUNT(*) FROM capabilities").fetchone()[0]

    # SQL mirror of aimarket_hub.fulfillment.capability_is_fulfillable. Kept as SQL so a
    # count never has to load every row; kept next to count_capabilities so the two are
    # read together. Federated rows are always offerable — the peer owns execution.
    _OFFERABLE_LOCAL = (
        "source_hub='local' AND ("
        "COALESCE(invoke_url,'') != '' OR COALESCE(prompt_template,'') LIKE '{%')"
    )

    def count_offerable(self, source_hub: str | None = None) -> int:
        """Capabilities this hub can actually execute — what it may honestly advertise.

        ``count_capabilities`` counts the table, including rows with no execution path.
        Publishing that number told peers the hub had seventeen capabilities while its
        manifest listed five.
        """
        if source_hub == "local":
            return self._conn.execute(
                f"SELECT COUNT(*) FROM capabilities WHERE {self._OFFERABLE_LOCAL}"
            ).fetchone()[0]
        if source_hub:
            return self._conn.execute(
                "SELECT COUNT(*) FROM capabilities WHERE source_hub=?", (source_hub,)
            ).fetchone()[0]
        return self._conn.execute(
            f"SELECT COUNT(*) FROM capabilities WHERE source_hub != 'local' "
            f"OR ({self._OFFERABLE_LOCAL})"
        ).fetchone()[0]

    def count_federated(self) -> int:
        return self._conn.execute(
            "SELECT COUNT(*) FROM capabilities WHERE source_hub != 'local'"
        ).fetchone()[0]

    def clear_federated(self) -> None:
        """Remove all non-local capabilities (before re-crawl)."""
        self._conn.execute("DELETE FROM capabilities WHERE source_hub != 'local'")
        self._conn.commit()

    def delete_capability(self, capability_id: str, source_hub: str = "local") -> int:
        """Delete a single capability by id. Returns the number of rows removed."""
        cur = self._conn.execute(
            "DELETE FROM capabilities WHERE capability_id=? AND source_hub=?",
            (capability_id, source_hub),
        )
        self._conn.commit()
        return cur.rowcount

    # ── Peers ─────────────────────────────────────────────────

    def upsert_peer(self, peer: Peer, status: str = "active") -> None:
        """Insert or replace a peer row.

        ``status`` defaults to ``active`` because a successful crawl is what
        normally calls this, and that must clear any pin-reject state. Open
        federation passes ``pending`` instead: the peer is recorded and visible,
        but ``trusted`` stays False so nothing it claims is ever indexed.

        ``first_seen`` is written once and preserved on every later upsert — it
        is how a hub that appeared this morning is told apart from one that has
        been in the table for months.

        The pin-reject diagnostics follow ``status``: cleared when this call moves
        a peer to ``active``/``pending``, carried forward when the caller is
        preserving ``key_mismatch``. The trust-score refresh loop passes the
        existing status back precisely so a caught takeover is not un-rejected,
        and blanking the reason there left the flag standing with nothing to
        explain it — a real ``key_mismatch`` peer sat in production for five days
        reading ``pin_reject_reason: ""``, so the cause had to be found by
        comparing keys by hand.
        """
        if status not in ("active", "pending", "key_mismatch", "pq_key_mismatch"):
            raise ValueError(f"unsupported peer status: {status!r}")
        existing = self._conn.execute(
            "SELECT first_seen, pin_reject_reason, advertised_public_key "
            "FROM peers WHERE url=?", (peer.url,)
        ).fetchone()
        first_seen = (
            (existing["first_seen"] if existing else "")
            or peer.first_seen
            or _utc_now_iso()
        )
        if status == "key_mismatch" and existing is not None:
            pin_reject_reason = existing["pin_reject_reason"] or ""
            advertised_public_key = existing["advertised_public_key"] or ""
        else:
            pin_reject_reason = ""
            advertised_public_key = ""
        self._conn.execute("""
            INSERT OR REPLACE INTO peers
                (url, name, capabilities_count, last_crawl, trust_score,
                 well_known_url, manifest_url, public_key, depth, discoverer,
                 categories, trusted, status, pin_reject_reason, advertised_public_key,
                 first_seen, description, hub_version, declared_id, mcp_endpoint,
                 pq_public_key, advertised_pq_public_key, declared_contracts)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            peer.url, peer.name, peer.capabilities_count, peer.last_crawl,
            peer.trust_score, peer.well_known_url, peer.manifest_url,
            peer.public_key, peer.depth, peer.discoverer,
            json.dumps(peer.categories or []), int(bool(peer.trusted)), status,
            pin_reject_reason, advertised_public_key,
            first_seen,
            # A column named in one of these three lists and missing from another blanks
            # itself on every crawl and reads back as "" with no error anywhere — INSERT OR
            # REPLACE rewrites the whole row, and _row_to_peer reads with .get(). Add to all
            # three or to none.
            peer.description, peer.hub_version, peer.declared_id, peer.mcp_endpoint,
            peer.pq_public_key, peer.advertised_pq_public_key,
            json.dumps(peer.declared_contracts or {}),
        ))
        self._conn.commit()

    def announce_peer(self, peer: Peer, max_pending: int) -> str:
        """Record an unauthenticated peer announcement. Returns what happened.

        Never upgrades: an already-known peer is left exactly as it is, so an
        announcement can neither downgrade a trusted peer to pending nor rewrite
        a pinned key. Returns ``"known"``, ``"added"`` or ``"rejected_cap"``.
        """
        if self.get_peer(peer.url) is not None:
            return "known"
        if self.count_pending_hosts() >= max_pending:
            return "rejected_cap"
        self.upsert_peer(peer, status="pending")
        return "added"

    def active_peer_with_public_key(self, public_key: str, *, exclude_url: str = "") -> str | None:
        """URL of an ACTIVE peer already holding this signing key, if any.

        A hub's identity is its signing key, but the peers table is keyed on URL — so the same
        hub announced under a second address becomes a second row. That is not cosmetic: both
        rows are crawled and both re-export the same catalogue, so one operator gets double
        weight in the index. Seen in production on 2026-09-04: the competing-lab hub sat as an
        active peer at ``http://108.165.32.182:9083`` *and* as a pending announcement for
        ``https://hub.modelmarket.dev`` — the same machine under two identities.
        """
        key = (public_key or "").strip()
        if not key:
            return None
        row = self._conn.execute(
            "SELECT url FROM peers WHERE status='active' AND public_key=? AND url<>? LIMIT 1",
            (key, (exclude_url or "").rstrip("/")),
        ).fetchone()
        return row["url"] if row else None

    def list_peers(self) -> list[Peer]:
        # Include key_mismatch so a takeover reject is visible on /federation/peers
        # instead of only in crawler logs.
        rows = self._conn.execute(
            "SELECT * FROM peers WHERE status IN ('active', 'key_mismatch') "
            "ORDER BY CASE status WHEN 'key_mismatch' THEN 0 ELSE 1 END, "
            "trust_score DESC"
        ).fetchall()
        return [_row_to_peer(r) for r in rows]

    def list_pending_peers(self) -> list[Peer]:
        """Peers that announced themselves or crawled us but are NOT approved.

        Deliberately a separate call from :meth:`list_peers`. That one feeds the
        published ``.well-known`` document, and republishing unverified hubs would
        let anyone use this hub to launder their URL into the federation's BFS.
        Pending peers are for the operator's eyes (and the monitor), not for peers.
        """
        rows = self._conn.execute(
            "SELECT * FROM peers WHERE status='pending' ORDER BY first_seen DESC"
        ).fetchall()
        return [_row_to_peer(r) for r in rows]

    def count_pending_peers(self) -> int:
        return self._conn.execute(
            "SELECT COUNT(*) FROM peers WHERE status='pending'"
        ).fetchone()[0]

    def count_pending_hosts(self) -> int:
        """Distinct hostnames among pending peers.

        The cap is keyed on this rather than on rows: a URL is free to mint, so
        `https://x.example/a`, `/b`, `/c` … would fill a row-based cap in one loop. A
        hostname costs something to obtain, which is the property a limit needs.
        """
        from urllib.parse import urlparse

        rows = self._conn.execute(
            "SELECT url FROM peers WHERE status='pending'"
        ).fetchall()
        return len({urlparse(r["url"]).hostname or r["url"] for r in rows})

    def delete_peer(self, url: str) -> bool:
        """Remove a peer and any preview rows it left behind.

        Without this the pending queue was a one-way door: once full, an operator could
        approve entries but never reject them, and an unauthenticated party could hold the
        queue shut permanently.
        """
        self._conn.execute("DELETE FROM peer_preview_capabilities WHERE peer_url=?", (url,))
        self._conn.execute("DELETE FROM peer_assays WHERE peer_url=?", (url,))
        # And what was indexed from it. Deleting an ADMITTED peer left its catalogue rows in
        # search and routing, each answering "Peer hub not found" when bought (found removing
        # a test hub from modelmarket.dev, 2026-10-12).
        self._conn.execute("DELETE FROM capabilities WHERE source_hub=?", (url,))
        cur = self._conn.execute("DELETE FROM peers WHERE url=?", (url,))
        self._conn.commit()
        return cur.rowcount > 0

    def promote_pending_peer(self, url: str) -> bool:
        """Move a pending peer to active. Trust is granted separately, by
        ``set_peer_trusted`` — being active only means the crawler stops treating
        the row as a knock at the door."""
        cur = self._conn.execute(
            "UPDATE peers SET status='active' WHERE url=? AND status='pending'", (url,)
        )
        self._conn.commit()
        return cur.rowcount > 0

    # --- preview catalogue of pending peers ------------------------------
    # These rows live in their own table on purpose. `capabilities` is what
    # search, routing, invoke and the manifest read; a preview row is never in
    # it, so an unapproved peer cannot be reached even by a query that forgets
    # to filter. See migration 023.

    def replace_preview_capabilities(self, peer_url: str, caps: list[dict]) -> int:
        """Replace a pending peer's preview catalogue. Returns rows written."""
        self._conn.execute(
            "DELETE FROM peer_preview_capabilities WHERE peer_url=?", (peer_url,)
        )
        written = 0
        for cap in caps:
            cap_id = str(cap.get("capability_id") or cap.get("id") or "").strip()
            if not cap_id:
                continue
            self._conn.execute("""
                INSERT OR REPLACE INTO peer_preview_capabilities
                    (peer_url, capability_id, product_id, name, description,
                     price_per_call_usd, categories)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                peer_url, cap_id, str(cap.get("product_id") or ""),
                str(cap.get("name") or "")[:200],
                str(cap.get("description") or "")[:500],
                float(cap.get("price_per_call_usd") or cap.get("price_usd") or 0.0),
                json.dumps(cap.get("categories") or []),
            ))
            written += 1
        self._conn.commit()
        return written

    def list_preview_capabilities(self, peer_url: str = "", limit: int = 200) -> list[dict]:
        if peer_url:
            rows = self._conn.execute(
                "SELECT * FROM peer_preview_capabilities WHERE peer_url=? "
                "ORDER BY capability_id LIMIT ?", (peer_url, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM peer_preview_capabilities ORDER BY peer_url, capability_id LIMIT ?",
                (limit,),
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            out.append({
                "peer_url": d.get("peer_url", ""),
                "capability_id": d.get("capability_id", ""),
                "product_id": d.get("product_id", ""),
                "name": d.get("name", ""),
                "description": d.get("description", ""),
                "price_per_call_usd": d.get("price_per_call_usd", 0.0),
                "categories": _json_list(d.get("categories", "[]")),
                "seen_at": d.get("seen_at", ""),
                "quarantined": True,  # always — the table has no other kind of row
            })
        return out

    def count_preview_capabilities(self, peer_url: str = "") -> int:
        if peer_url:
            return self._conn.execute(
                "SELECT COUNT(*) FROM peer_preview_capabilities WHERE peer_url=?", (peer_url,)
            ).fetchone()[0]
        return self._conn.execute(
            "SELECT COUNT(*) FROM peer_preview_capabilities"
        ).fetchone()[0]

    def clear_preview_capabilities(self, peer_url: str) -> int:
        cur = self._conn.execute(
            "DELETE FROM peer_preview_capabilities WHERE peer_url=?", (peer_url,)
        )
        self._conn.commit()
        return cur.rowcount

    # --- inbound federation telemetry ------------------------------------

    def record_inbound_federation(
        self, hub_url: str, user_agent: str = "", max_rows: int = 500
    ) -> None:
        """Note that ``hub_url`` fetched our discovery document.

        Only the self-declared hub URL and User-Agent are stored — never the
        client IP. Knowing *that* a hub reads us is operationally useful;
        keeping a log of who connects from where is not, and would be a
        liability the moment this database is shared or leaked.
        """
        # An unauthenticated header must not be an unbounded write. Known hubs keep
        # updating; unknown ones stop being recorded once the log is full.
        if max_rows and self._conn.execute(
            "SELECT COUNT(*) FROM federation_inbound"
        ).fetchone()[0] >= max_rows and self._conn.execute(
            "SELECT 1 FROM federation_inbound WHERE hub_url=?", (hub_url,)
        ).fetchone() is None:
            return
        self._conn.execute("""
            INSERT INTO federation_inbound (hub_url, user_agent, first_seen, last_seen, hits)
            VALUES (?, ?, ?, ?, 1)
            ON CONFLICT(hub_url) DO UPDATE SET
                last_seen=excluded.last_seen,
                user_agent=excluded.user_agent,
                hits=federation_inbound.hits + 1
        """, (hub_url, user_agent[:200], _utc_now_iso(), _utc_now_iso()))
        self._conn.commit()

    def list_inbound_federation(self, limit: int = 100) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM federation_inbound ORDER BY last_seen DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Observed sellers (spec §2.7, observed_sellers.py) ─────────────────

    def upsert_observed_seller(
        self,
        origin: str,
        *,
        consent: dict,
        allowed_routes: list[str] | None = None,
        pinned_pay_to: str = "",
        name: str = "",
    ) -> None:
        """Record (or re-confirm) a seller's consent. Keeps its last observation, but a new
        ``pinned_pay_to`` replaces the old pin: that is how the operator re-confirms one."""
        now = _utc_now_iso()
        self._conn.execute("""
            INSERT INTO observed_sellers
                (origin, name, allowed_routes_json, pinned_pay_to, consent_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(origin) DO UPDATE SET
                name=excluded.name,
                allowed_routes_json=excluded.allowed_routes_json,
                pinned_pay_to=excluded.pinned_pay_to,
                consent_json=excluded.consent_json,
                updated_at=excluded.updated_at
        """, (
            origin, name[:120], json.dumps(list(allowed_routes or [])), pinned_pay_to[:128],
            json.dumps(consent), now, now,
        ))
        self._conn.commit()

    def save_observed_seller_observation(self, origin: str, observation: dict) -> None:
        self._conn.execute("""
            UPDATE observed_sellers SET
                name=?, discovery_url=?, pinned_pay_to=?, observed_at=?, last_error=?, routes_json=?
            WHERE origin=?
        """, (
            str(observation.get("name") or "")[:120],
            str(observation.get("discovery_url") or "")[:500],
            str(observation.get("pinned_pay_to") or "")[:128],
            str(observation.get("observed_at") or ""),
            str(observation.get("last_error") or "")[:500],
            json.dumps(observation.get("routes") or []),
            origin,
        ))
        self._conn.commit()

    def list_observed_sellers(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM observed_sellers ORDER BY created_at, origin"
        ).fetchall()
        out = []
        for row in rows:
            d = dict(row)
            for key, default in (("allowed_routes_json", []), ("consent_json", {}), ("routes_json", [])):
                raw = d.pop(key, None)
                try:
                    value = json.loads(raw) if isinstance(raw, str) else raw
                except json.JSONDecodeError:
                    value = None
                d[key[: -len("_json")]] = value if isinstance(value, type(default)) else default
            out.append(d)
        return out

    def get_observed_seller(self, origin: str) -> dict | None:
        return next((s for s in self.list_observed_sellers() if s["origin"] == origin), None)

    def delete_observed_seller(self, origin: str) -> bool:
        """Consent withdrawn: the record and its observations go, not just the listing."""
        cur = self._conn.execute("DELETE FROM observed_sellers WHERE origin=?", (origin,))
        self._conn.commit()
        return bool(getattr(cur, "rowcount", 0))

    def save_peer_assay(self, dossier: dict) -> None:
        """Store the last assay scorecard. Does not itself toggle ``peers.trusted``."""
        url = str(dossier.get("url") or "").strip().rstrip("/")
        if not url:
            return
        self._conn.execute("""
            INSERT OR REPLACE INTO peer_assays
                (peer_url, verdict, checks_json, sandbox_json, advertised_key, ran_at, note)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            url,
            str(dossier.get("verdict") or "fail")[:16],
            json.dumps(dossier.get("checks") or []),
            json.dumps(dossier.get("sandbox") or {}),
            str(dossier.get("advertised_key") or "")[:256],
            str(dossier.get("ran_at") or _utc_now_iso()),
            str(dossier.get("note") or "")[:500],
        ))
        self._conn.commit()

    def get_peer_assay(self, peer_url: str) -> dict | None:
        url = (peer_url or "").strip().rstrip("/")
        if not url:
            return None
        row = self._conn.execute(
            "SELECT * FROM peer_assays WHERE peer_url=?", (url,),
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        checks = d.get("checks_json") or "[]"
        sandbox = d.get("sandbox_json") or "{}"
        if isinstance(checks, str):
            try:
                checks = json.loads(checks)
            except json.JSONDecodeError:
                checks = []
        if isinstance(sandbox, str):
            try:
                sandbox = json.loads(sandbox)
            except json.JSONDecodeError:
                sandbox = {}
        peer = self.get_peer(url)
        trusted = bool(peer and peer.trusted)
        sandbox_obj = sandbox if isinstance(sandbox, dict) else {}
        return {
            "url": d.get("peer_url") or url,
            "verdict": d.get("verdict") or "fail",
            "trusted": trusted,
            "indexed": trusted,
            "auto_promoted": bool(sandbox_obj.get("auto_promoted")),
            "quarantined": not trusted,
            "advertised_key": d.get("advertised_key") or "",
            "checks": checks if isinstance(checks, list) else [],
            "sandbox": sandbox_obj,
            "note": d.get("note") or "",
            "ran_at": d.get("ran_at") or "",
        }

    def get_peer(self, url: str) -> Peer | None:
        row = self._conn.execute("SELECT * FROM peers WHERE url=?", (url,)).fetchone()
        return _row_to_peer(row) if row else None

    def set_peer_trusted(self, url: str, trusted: bool) -> bool:
        """Operator approval: mark a peer trusted/untrusted. Returns True if a peer was updated."""
        cur = self._conn.execute(
            "UPDATE peers SET trusted=? WHERE url=?", (int(bool(trusted)), url)
        )
        self._conn.commit()
        return (cur.rowcount or 0) > 0

    def record_peer_key_mismatch(
        self, url: str, *, pinned_key: str, advertised_key: str,
    ) -> bool:
        """Persist a pin mismatch so /federation/peers can surface it.

        Does not change ``public_key`` (the pin stays fail-closed). Returns True
        if a peer row was updated.
        """
        reason = "peer rejected: key changed"
        cur = self._conn.execute(
            """
            UPDATE peers
               SET status='key_mismatch',
                   pin_reject_reason=?,
                   advertised_public_key=?
             WHERE url=?
            """,
            (reason, advertised_key or "", url),
        )
        self._conn.commit()
        return (cur.rowcount or 0) > 0

    def record_peer_pq_mismatch(
        self, url: str, *, pinned_pq_key: str, advertised_pq_key: str,
    ) -> bool:
        """Persist a POST-QUANTUM pin mismatch or a downgrade, so the desk can surface it.

        Deliberately its own status rather than reusing ``key_mismatch``: the classical pin is
        intact, so an operator reading "key changed" would look for the wrong rotation and repin
        the wrong key. The two reasons are also distinguished — a peer that stopped advertising a
        PQ key is the downgrade attack, and one advertising a different key is a rotation with a
        remedy (`POST /federation/peers/repin` with `pq_public_key`).

        Does not change ``pq_public_key``: the pin stays fail-closed. Returns True if a row was
        updated.
        """
        reason = ("peer rejected: post-quantum key withdrawn"
                  if not advertised_pq_key else "peer rejected: post-quantum key changed")
        cur = self._conn.execute(
            """
            UPDATE peers
               SET status='pq_key_mismatch',
                   pin_reject_reason=?,
                   advertised_pq_public_key=?
             WHERE url=?
            """,
            (reason, advertised_pq_key or "", url),
        )
        self._conn.commit()
        return (cur.rowcount or 0) > 0

    def repin_peer_public_key(
        self,
        url: str,
        public_key: str | None = None,
        *,
        trusted: bool | None = True,
        previous_public_key: str | None = None,
        pq_public_key: str | None = None,
        previous_pq_public_key: str | None = None,
    ) -> dict:
        """Operator re-pin after a legitimate key rotation — classical, post-quantum, or both.

        ``public_key`` became optional when the post-quantum pin arrived: a peer may rotate its
        ML-DSA key without touching Ed25519 (recovering a lost volume, moving to a higher ML-DSA
        parameter set), and demanding the classical key for that would invite an operator to paste
        the current value back in, which is a chance to paste the wrong one. At least one of the
        two is required.

        Both ``previous_*`` arguments are optimistic concurrency: when set they must match the
        current pin, so a re-pin cannot race another one or be applied to a peer that has moved on
        since the operator read the desk.

        Without this path a pinned PQ key is a one-way door — the crawler refuses a changed key
        forever and the only remedy is editing the database by hand. Clears key_mismatch state.
        Returns a small audit dict; raises ValueError on precondition failure.
        """
        key = (public_key or "").strip()
        pq_key = (pq_public_key or "").strip()
        if not key and not pq_key:
            raise ValueError("public_key or pq_public_key is required")
        row = self._conn.execute("SELECT * FROM peers WHERE url=?", (url,)).fetchone()
        if row is None:
            raise ValueError(f"peer not found: {url}")
        current = dict(row)
        prior = (current.get("public_key") or "").strip()
        prior_pq = (current.get("pq_public_key") or "").strip()
        if previous_public_key is not None and previous_public_key.strip() != prior:
            raise ValueError(
                "previous_public_key does not match the current pin "
                f"(have {prior[:16]}…)"
            )
        if previous_pq_public_key is not None and previous_pq_public_key.strip() != prior_pq:
            raise ValueError(
                "previous_pq_public_key does not match the current PQ pin "
                f"(have {prior_pq[:16] or '(none)'}…)"
            )
        sets = ["status='active'", "pin_reject_reason=''", "advertised_public_key=''"]
        args: list = []
        if key:
            sets.insert(0, "public_key=?")
            args.append(key)
        if pq_key:
            # Cleared together with the pin it belongs to, exactly as the classical pair is: a
            # stale "advertised" value must not outlive the incident that recorded it.
            sets.append("pq_public_key=?")
            sets.append("advertised_pq_public_key=''")
            args.append(pq_key)
        trusted_out = bool(current.get("trusted", 0))
        if trusted is not None:
            sets.append("trusted=?")
            args.append(int(bool(trusted)))
            trusted_out = bool(trusted)
        args.append(url)
        self._conn.execute(f"UPDATE peers SET {', '.join(sets)} WHERE url=?", args)
        self._conn.commit()
        return {
            "url": url,
            "public_key": key or prior,
            "previous_public_key": prior,
            "pq_public_key": pq_key or prior_pq,
            "previous_pq_public_key": prior_pq,
            "rotated": [n for n, v in (("ed25519", key), ("ml-dsa-65", pq_key)) if v],
            "trusted": trusted_out,
            "status": "active",
        }

    def peer_count(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM peers WHERE status='active'").fetchone()[0]

    # ── Stats ─────────────────────────────────────────────────

    def record_invocation(self, stat: InvocationStat) -> None:
        outcome = normalize_outcome(stat.outcome, success=bool(stat.success))
        caller_class = str(getattr(stat, "caller_class", "") or "")
        if not valid_caller_class(caller_class):
            caller_class = ""
        purpose = normalize_purpose(getattr(stat, "purpose", ""))
        self._conn.execute("""
            INSERT INTO invocation_stats
                (capability_id, product_id, source_hub, price_usd, latency_ms,
                 success, timestamp, consumer_hub, outcome, caller_class, purpose)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            stat.capability_id, stat.product_id, stat.source_hub,
            stat.price_usd, stat.latency_ms,
            1 if outcome == "ok" else 0,
            stat.timestamp, stat.consumer_hub, outcome, caller_class, purpose,
        ))
        self._conn.commit()

    # ── Buyer-confirmed deliveries (deliveries.py) ────────────

    def record_delivery_confirmation(self, c: Any) -> bool:
        """Count one confirmation. False when that transaction was already counted for that kind."""
        exists = self._conn.execute(
            "SELECT 1 FROM delivery_confirmations WHERE id = ?", (c.id,)
        ).fetchone()
        if exists:
            return False
        self._conn.execute(
            "INSERT INTO delivery_confirmations (id, source_hub, product_id, kind, buyer_hash, confirmed_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (c.id, c.source_hub, c.product_id, c.kind, c.buyer_hash,
             time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())),
        )
        self._conn.commit()
        return True

    def deliveries_30d(self) -> dict[tuple[str, str], dict[str, int]]:
        """Per seller (source_hub, product_id): deliveries and refunds buyers confirmed in 30 days,
        and how many distinct buyers confirmed a delivery."""
        since = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 30 * 86400))
        rows = self._conn.execute(
            "SELECT source_hub, product_id, "
            "SUM(CASE WHEN kind = 'delivery' THEN 1 ELSE 0 END) AS confirmed, "
            "COUNT(DISTINCT CASE WHEN kind = 'delivery' THEN buyer_hash END) AS buyers, "
            "SUM(CASE WHEN kind = 'refund' THEN 1 ELSE 0 END) AS refunded "
            "FROM delivery_confirmations WHERE confirmed_at >= ? GROUP BY source_hub, product_id",
            (since,),
        ).fetchall()
        return {(r[0], r[1]): {"confirmed": int(r[2] or 0), "distinct_buyers": int(r[3] or 0),
                               "refunded": int(r[4] or 0)} for r in rows}

    def observations_30d(self) -> dict[str, dict[str, tuple[int, int]]]:
        """Observed invocations in the last 30 days, as ``(attempts, successes)``.

        Returns ``{"by_capability": {...}, "by_hub": {...}}`` from one pass over the
        stats table.

        The manifest publishes a ``success_rate_30d`` and a ``trust_score`` for every row,
        but a rate with nothing behind it is not a measurement — it is the crawler's
        neutral baseline (``0.5``, deliberately chosen so a peer cannot claim 99% and
        dominate routing on first index). From the number alone a consumer cannot tell a
        measured 0.5 from an unobserved one, and every one of the catalogue's rows is the
        latter. Publishing the count next to the rate is what makes that distinction
        available to the buyer instead of only to us.
        """
        since = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 30 * 86400))
        rows = self._conn.execute(
            "SELECT capability_id, source_hub, "
            "SUM(CASE WHEN outcome IN ('refused', 'incomplete') THEN 0 ELSE 1 END) "
            "AS attempts, "
            "SUM(CASE WHEN outcome = 'ok' THEN 1 ELSE 0 END) AS successes "
            "FROM invocation_stats WHERE timestamp >= ? "
            "GROUP BY capability_id, source_hub",
            (since,),
        ).fetchall()

        by_capability: dict[str, tuple[int, int]] = {}
        by_hub: dict[str, tuple[int, int]] = {}
        for row in rows:
            r = dict(row)
            attempts = int(r.get("attempts") or 0)
            successes = int(r.get("successes") or 0)
            cap_id = str(r.get("capability_id") or "")
            hub = str(r.get("source_hub") or "local")
            if cap_id:
                prev = by_capability.get(cap_id, (0, 0))
                by_capability[cap_id] = (prev[0] + attempts, prev[1] + successes)
            prev_hub = by_hub.get(hub, (0, 0))
            by_hub[hub] = (prev_hub[0] + attempts, prev_hub[1] + successes)

        return {"by_capability": by_capability, "by_hub": by_hub}

    def recent_stats(self, limit: int = 50) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM invocation_stats ORDER BY timestamp DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def consumer_traffic_totals(self, self_labels: Any = None, *,
                                policy: Any = None, hub_url: str = "") -> dict[str, int]:
        """Lifetime external-vs-operator-self split over the WHOLE stats table.

        ``/stats/live`` already classified traffic, but only across the rows it
        happened to return — the counters are named ``*_in_page`` for that reason. The
        public card then printed that pair next to ``total_invocations``, so a 505-row
        history sat beside an "80 external / 0 self" split of the newest 80 rows and read
        as a breakdown of the 505. These totals cover exactly the rows the total counts.

        With ``policy`` (an ``ecosystem.EcosystemPolicy``) the split is the one the feed
        uses, row for row: ``policy.sql_self_condition`` is the SQL twin of
        ``policy.classify``, in ONE condition so a row that is SELF for two reasons is
        counted once. ``self_labels`` is the older label-only form (kept for callers that
        have no policy): each label is matched with and without a trailing slash so no
        dialect-specific ``RTRIM`` is needed on PostgreSQL.
        """
        total = int(self._conn.execute("SELECT COUNT(*) FROM invocation_stats").fetchone()[0])
        if policy is not None:
            condition, params = policy.sql_self_condition(hub_url)
            own = int(self._conn.execute(
                f"SELECT COUNT(*) FROM invocation_stats WHERE {condition}", tuple(params),
            ).fetchone()[0])
            return {"external": max(0, total - own), "operator_self": own}
        variants: set[str] = set()
        for label in self_labels or ():
            base = str(label).strip().rstrip("/")
            if base:
                variants.update((base, base + "/"))
        if not variants:
            return {"external": total, "operator_self": 0}
        ordered = sorted(variants)
        placeholders = ",".join("?" for _ in ordered)
        own = int(self._conn.execute(
            "SELECT COUNT(*) FROM invocation_stats "
            f"WHERE COALESCE(consumer_hub, '') IN ({placeholders})",
            tuple(ordered),
        ).fetchone()[0])
        return {"external": max(0, total - own), "operator_self": own}

    def stats_summary(self) -> dict[str, Any]:
        """Aggregate stats for the live ticker and public status pages."""
        total = self._conn.execute("SELECT COUNT(*) FROM invocation_stats").fetchone()[0]
        success = self._conn.execute(
            "SELECT COUNT(*) FROM invocation_stats WHERE outcome='ok'"
        ).fetchone()[0]
        fail = self._conn.execute(
            "SELECT COUNT(*) FROM invocation_stats WHERE outcome='fail'"
        ).fetchone()[0]
        refused = self._conn.execute(
            "SELECT COUNT(*) FROM invocation_stats WHERE outcome='refused'"
        ).fetchone()[0]
        # Its own counter, not folded into refusals: an invoke that arrived without the
        # coordinates the capability needs is not a decision anybody took.
        incomplete = self._conn.execute(
            "SELECT COUNT(*) FROM invocation_stats WHERE outcome='incomplete'"
        ).fetchone()[0]
        avg_price = self._conn.execute(
            "SELECT AVG(price_usd) FROM invocation_stats"
        ).fetchone()[0] or 0
        avg_latency = self._conn.execute(
            "SELECT AVG(latency_ms) FROM invocation_stats"
        ).fetchone()[0] or 0
        now = time.time()
        hour_ago = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now - 3600))
        day_ago = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now - 86400))
        revenue_hour = self._conn.execute(
            "SELECT COALESCE(SUM(price_usd), 0) FROM invocation_stats WHERE timestamp >= ?",
            (hour_ago,),
        ).fetchone()[0]
        # Invoked volume inside the same windows the invocation counters use.
        # Without this, every consumer that wanted "volume over the last 24h" had to
        # reach for a channel figure (``settled_volume_usd``) that carries NO time
        # window at all, and paint a lifetime total under a 24h label — which is
        # exactly what the ecosystem monitor did.
        volume_day = self._conn.execute(
            "SELECT COALESCE(SUM(price_usd), 0) FROM invocation_stats WHERE timestamp >= ?",
            (day_ago,),
        ).fetchone()[0]
        volume_total = self._conn.execute(
            "SELECT COALESCE(SUM(price_usd), 0) FROM invocation_stats"
        ).fetchone()[0]
        invocations_1h = self._conn.execute(
            "SELECT COUNT(*) FROM invocation_stats WHERE timestamp >= ?",
            (hour_ago,),
        ).fetchone()[0]
        invocations_24h = self._conn.execute(
            "SELECT COUNT(*) FROM invocation_stats WHERE timestamp >= ?",
            (day_ago,),
        ).fetchone()[0]
        failed_24h = self._conn.execute(
            "SELECT COUNT(*) FROM invocation_stats "
            "WHERE timestamp >= ? AND outcome='fail'",
            (day_ago,),
        ).fetchone()[0]
        refused_24h = self._conn.execute(
            "SELECT COUNT(*) FROM invocation_stats "
            "WHERE timestamp >= ? AND outcome='refused'",
            (day_ago,),
        ).fetchone()[0]
        incomplete_24h = self._conn.execute(
            "SELECT COUNT(*) FROM invocation_stats "
            "WHERE timestamp >= ? AND outcome='incomplete'",
            (day_ago,),
        ).fetchone()[0]
        p50_24h = self._latency_percentile(day_ago, 0.5)
        p95_24h = self._latency_percentile(day_ago, 0.95)
        rps_1h = round(invocations_1h / 3600.0, 4) if invocations_1h else 0.0
        demo_caps = self._conn.execute(
            "SELECT COUNT(*) FROM capabilities WHERE source_hub='local' AND is_demo=1"
        ).fetchone()[0]
        real_local_caps = self._conn.execute(
            "SELECT COUNT(*) FROM capabilities WHERE source_hub='local' AND COALESCE(is_demo, 0)=0"
        ).fetchone()[0]
        return {
            "total_invocations": total,
            "successful_invocations": success,
            "failed_invocations": int(fail),
            "refused_invocations": int(refused),
            "incomplete_invocations": int(incomplete),
            "success_rate": scored_success_rate(
                ok=int(success), fail=int(fail), refused=int(refused),
                incomplete=int(incomplete),
            ),
            "avg_price_usd": round(avg_price, 4),
            "avg_latency_ms": round(avg_latency, 1),
            "revenue_per_hour_usd": round(revenue_hour, 4),
            "volume_1h_usd": round(float(revenue_hour or 0), 4),
            "volume_24h_usd": round(float(volume_day or 0), 4),
            "volume_total_usd": round(float(volume_total or 0), 4),
            "invocations_1h": int(invocations_1h),
            "invocations_24h": int(invocations_24h),
            "failed_invocations_24h": int(failed_24h),
            "refused_invocations_24h": int(refused_24h),
            "incomplete_invocations_24h": int(incomplete_24h),
            "rps_1h": rps_1h,
            "p50_latency_ms_24h": p50_24h,
            "p95_latency_ms_24h": p95_24h,
            "peers_count": self.peer_count(),
            "capabilities_count": self.count_capabilities(),
            # What the storefront may honestly show. `capabilities_count` counts the table,
            # including local rows with no execution path — the number that let the landing
            # page advertise "12 capabilities" while /manifest and /search served none of
            # them, because those read the filtered set. See count_offerable().
            "offerable_capabilities_count": self.count_offerable(),
            "federated_capabilities_count": self.count_federated(),
            "demo_capabilities_count": int(demo_caps),
            "real_local_capabilities_count": int(real_local_caps),
        }

    def _latency_percentile(self, since_iso: str, pct: float) -> float | None:
        """Nearest-rank p50/p95 latency (ms) for invocations since ``since_iso``."""
        count = self._conn.execute(
            "SELECT COUNT(*) FROM invocation_stats WHERE timestamp >= ?",
            (since_iso,),
        ).fetchone()[0]
        if not count:
            return None
        offset = max(0, int(math.ceil(count * pct)) - 1)
        row = self._conn.execute(
            "SELECT latency_ms FROM invocation_stats WHERE timestamp >= ? "
            "ORDER BY latency_ms ASC LIMIT 1 OFFSET ?",
            (since_iso, offset),
        ).fetchone()
        return round(float(row[0]), 1) if row else None

    # ── Reputation ────────────────────────────────────────────

    def has_reputation_event(self, consumer_hub: str, signature: str) -> bool:
        """Has this exact signed event from this consumer already been recorded?

        The signature is over the event's canonical form, so the same bytes arriving
        twice ARE the same event. Before this check a peer could replay one validly
        signed `invocation_success` any number of times (100 per request, no rate limit)
        and inflate a provider's success rate and estimated bond — trust.py reads the
        last 10 events for both. Keyed on `signature` rather than a UNIQUE column so
        legacy rows with an empty signature are left alone.
        """
        if not signature:
            return False
        row = self._conn.execute(
            "SELECT 1 FROM reputation_events WHERE consumer_hub=? AND signature=? LIMIT 1",
            (consumer_hub, signature),
        ).fetchone()
        return row is not None

    def record_reputation_event(self, event: ReputationEvent) -> bool:
        """Store one signed event. Returns False (and stores nothing) for a replay."""
        if event.signature and self.has_reputation_event(event.consumer_hub, event.signature):
            return False
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
        return True

    def reputation_events_for(self, provider_hub: str, limit: int = 100) -> list[ReputationEvent]:
        rows = self._conn.execute(
            "SELECT * FROM reputation_events WHERE provider_hub=? ORDER BY timestamp DESC LIMIT ?",
            (provider_hub, limit),
        ).fetchall()
        return [_row_to_reputation(r) for r in rows]

    # ── Maintenance ───────────────────────────────────────────

    def close(self) -> None:
        self._backend.close()

    # ── Supply security ───────────────────────────────────────

    def supply_stake_get(self, publisher_id: str) -> float:
        row = self._conn.execute(
            "SELECT amount_usd, slashed_usd FROM supply_stakes WHERE publisher_id=?",
            (publisher_id,),
        ).fetchone()
        if not row:
            return 0.0
        d = dict(row)
        return max(0.0, float(d.get("amount_usd", 0)) - float(d.get("slashed_usd", 0)))

    def supply_stake_tx_exists(self, tx_hash: str) -> bool:
        """True if a non-empty stake tx_hash was already recorded (replay guard).

        Prevents a single on-chain deposit from being claimed as stake by (or for)
        multiple publishers to spoof trust scores / clear the stake gate.
        """
        tx = (tx_hash or "").strip()
        if not tx:
            return False
        row = self._conn.execute(
            "SELECT 1 FROM supply_stakes WHERE tx_hash = ? LIMIT 1", (tx,)
        ).fetchone()
        return row is not None

    def supply_stake_add(self, publisher_id: str, amount_usd: float, tx_hash: str = "") -> float:
        row = self._conn.execute(
            "SELECT amount_usd FROM supply_stakes WHERE publisher_id=?",
            (publisher_id,),
        ).fetchone()
        if row:
            new_amount = float(dict(row)["amount_usd"]) + amount_usd
            self._conn.execute(
                "UPDATE supply_stakes SET amount_usd=?, tx_hash=?, updated_at=datetime('now') WHERE publisher_id=?",
                (new_amount, tx_hash, publisher_id),
            )
        else:
            self._conn.execute(
                "INSERT INTO supply_stakes (publisher_id, amount_usd, slashed_usd, tx_hash) VALUES (?, ?, 0, ?)",
                (publisher_id, amount_usd, tx_hash),
            )
        self._conn.commit()
        return self.supply_stake_get(publisher_id)

    def supply_stake_slash(self, publisher_id: str, amount_usd: float) -> tuple[float, float]:
        remaining_before = self.supply_stake_get(publisher_id)
        slashed = min(remaining_before, amount_usd)
        self._conn.execute("""
            UPDATE supply_stakes SET slashed_usd = slashed_usd + ?, updated_at = datetime('now')
            WHERE publisher_id=?
        """, (slashed, publisher_id))
        self._conn.commit()
        return slashed, self.supply_stake_get(publisher_id)

    # ── Fault / slash event log (calibrated slashing) ─────────
    # Durable counters: a restart must neither amnesty a failure streak
    # (supply_fault_events) nor forget how much was already slashed today
    # (supply_slash_events → cool-down + rolling daily cap).

    def supply_fault_log(self, publisher_id: str, kind: str, product_id: str = "", capability_id: str = "", consumer_id: str = "") -> None:
        self._conn.execute(
            "INSERT INTO supply_fault_events (publisher_id, kind, product_id, capability_id, consumer_id) VALUES (?, ?, ?, ?, ?)",
            (publisher_id, kind, product_id, capability_id, consumer_id),
        )
        self._conn.commit()

    def supply_fault_count_recent(self, publisher_id: str, kind: str, window_s: float) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) FROM supply_fault_events "
            "WHERE publisher_id=? AND kind=? AND created_at >= ?",
            (publisher_id, kind, _utc_cutoff(window_s)),
        ).fetchone()
        return int(row[0]) if row else 0

    def supply_fault_distinct_consumers_recent(self, publisher_id: str, kind: str, window_s: float) -> int:
        """Distinct non-empty consumer_ids that logged this fault kind in the window.

        Griefing defense for the verified-failure ladder: one buyer's repeated failures
        are one voice, so a slash needs several DISTINCT consumers to agree."""
        row = self._conn.execute(
            "SELECT COUNT(DISTINCT consumer_id) FROM supply_fault_events "
            "WHERE publisher_id=? AND kind=? AND consumer_id != '' "
            "AND created_at >= ?",
            (publisher_id, kind, _utc_cutoff(window_s)),
        ).fetchone()
        return int(row[0]) if row else 0

    def supply_fault_clear(self, publisher_id: str, kind: str) -> None:
        self._conn.execute(
            "DELETE FROM supply_fault_events WHERE publisher_id=? AND kind=?",
            (publisher_id, kind),
        )
        self._conn.commit()

    def supply_slash_log(self, publisher_id: str, amount_usd: float, reason: str, evidence_kind: str = "") -> None:
        self._conn.execute(
            "INSERT INTO supply_slash_events (publisher_id, amount_usd, reason, evidence_kind) VALUES (?, ?, ?, ?)",
            (publisher_id, amount_usd, reason, evidence_kind),
        )
        self._conn.commit()

    def supply_slash_total_recent(self, publisher_id: str, hours: float = 24.0) -> float:
        row = self._conn.execute(
            "SELECT COALESCE(SUM(amount_usd), 0) FROM supply_slash_events "
            "WHERE publisher_id=? AND created_at >= ?",
            (publisher_id, _utc_cutoff(hours * 3600)),
        ).fetchone()
        return float(row[0]) if row else 0.0

    def supply_slash_last_age_s(self, publisher_id: str) -> float | None:
        """Seconds since this publisher's most recent slash event, or None if never slashed.
        Age is computed in Python (MAX(created_at) → parse → subtract) rather than with
        ``julianday()``, which PostgreSQL does not have."""
        row = self._conn.execute(
            "SELECT MAX(created_at) FROM supply_slash_events WHERE publisher_id=?",
            (publisher_id,),
        ).fetchone()
        if not row or row[0] is None:
            return None
        ts = _parse_db_ts(row[0])
        if ts is None:
            return None
        return max(0.0, (datetime.now(timezone.utc) - ts).total_seconds())

    def supply_slash_events_recent(self, publisher_id: str, limit: int = 50) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT amount_usd, reason, evidence_kind, created_at FROM supply_slash_events "
            "WHERE publisher_id=? ORDER BY id DESC LIMIT ?",
            (publisher_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Federated slash attestation persistence ───────────────

    def slash_attestation_save(self, issuer_hub: str, seq: int, envelope_json: str, tier: str) -> None:
        # INSERT OR IGNORE (not REPLACE): the attestation log is append-only, so a
        # same-(issuer, seq) write must never silently overwrite an already-recorded
        # envelope. Callers guard against re-persisting an existing key (ingest skips
        # known keys; authored slashes reserve a fresh seq), so IGNORE is a backstop
        # that preserves the first-written envelope rather than forging equivocation.
        self._conn.execute(
            "INSERT OR IGNORE INTO slash_attestations (issuer_hub, seq, envelope_json, tier) VALUES (?, ?, ?, ?)",
            (issuer_hub, seq, envelope_json, tier),
        )
        self._conn.commit()

    def slash_attestation_append(self, issuer_hub: str, env_factory: Any, tier: str, *, max_retries: int = 8) -> tuple[int, dict[str, Any]]:
        """Atomically allocate the next per-issuer ``seq`` and durably store an AUTHORED
        attestation, retrying on a ``(issuer_hub, seq)`` PK collision.

        This is the multi-worker/connection-safe replacement for author-time in-memory seq:
        two processes sharing the DB can compute the same ``MAX(seq)+1``, but only one INSERT
        wins the primary key — the loser rolls back (to drop its stale snapshot), re-reads the
        now-higher MAX, and retries. ``env_factory(seq)`` builds+signs the envelope for the
        reserved seq (its signature covers the seq, so it must be built per-attempt). Raises
        if no seq can be allocated, so the caller never serves a seq that isn't persisted."""
        for _ in range(max(1, max_retries)):
            row = self._conn.execute(
                "SELECT COALESCE(MAX(seq), 0) + 1 FROM slash_attestations WHERE issuer_hub=?",
                (issuer_hub,),
            ).fetchone()
            seq = int(row[0])
            env = env_factory(seq)
            try:
                self._conn.execute(
                    "INSERT INTO slash_attestations (issuer_hub, seq, envelope_json, tier) VALUES (?, ?, ?, ?)",
                    (issuer_hub, seq, json.dumps(env, ensure_ascii=False), tier),
                )
                self._conn.commit()
                return seq, env
            except Exception as exc:
                # End the failed transaction so the retry's SELECT sees a fresh snapshot
                # (including the concurrent writer's committed row), then decide.
                with contextlib.suppress(Exception):
                    self._conn.rollback()
                if type(exc).__name__ in ("IntegrityError", "UniqueViolation"):
                    continue  # a concurrent writer took this seq — retry with fresh MAX
                raise
        raise RuntimeError(f"could not allocate a unique slash attestation seq for {issuer_hub}")

    def slash_attestation_load_all(self) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT issuer_hub, seq, envelope_json, tier FROM slash_attestations"
        ).fetchall()
        return [dict(r) for r in rows]

    def self_bond_register(self, agent_id: str, evm_address: str, ceiling_usd: float, bond_usd: float, token: str = "USDC", commitment: str = "") -> dict[str, Any]:
        row = self._conn.execute("SELECT agent_id FROM self_bonds WHERE agent_id=?", (agent_id,)).fetchone()
        if row:
            self._conn.execute(
                "UPDATE self_bonds SET evm_address=?, ceiling_usd=?, bond_usd=?, token=?, commitment=?, updated_at=datetime('now') WHERE agent_id=?",
                (evm_address, ceiling_usd, bond_usd, token, commitment, agent_id),
            )
        else:
            self._conn.execute(
                "INSERT INTO self_bonds (agent_id, evm_address, ceiling_usd, bond_usd, token, commitment) VALUES (?, ?, ?, ?, ?, ?)",
                (agent_id, evm_address, ceiling_usd, bond_usd, token, commitment),
            )
        self._conn.commit()
        return self.self_bond_get(agent_id) or {}

    def self_bond_get(self, agent_id: str) -> dict[str, Any] | None:
        row = self._conn.execute("SELECT * FROM self_bonds WHERE agent_id=?", (agent_id,)).fetchone()
        return dict(row) if row else None

    def self_bond_record_slash(self, agent_id: str, amount_usd: float) -> None:
        self._conn.execute(
            "UPDATE self_bonds SET slashed_usd = slashed_usd + ?, updated_at = datetime('now') WHERE agent_id=?",
            (amount_usd, agent_id),
        )
        self._conn.commit()

    def supply_publish_log(self, publisher_id: str, product_id: str, invoke_url: str) -> None:
        self._conn.execute(
            "INSERT INTO supply_publish_events (publisher_id, product_id, invoke_url) VALUES (?, ?, ?)",
            (publisher_id, product_id, invoke_url),
        )
        self._conn.commit()

    def supply_publish_count_recent(self, publisher_id: str, hours: int = 1) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) FROM supply_publish_events "
            "WHERE publisher_id=? AND created_at >= ?",
            (publisher_id, _utc_cutoff(hours * 3600)),
        ).fetchone()
        return int(row[0]) if row else 0

    # ── Supply-chain admission ──────────────────────────────────

    def supply_audit_record(self, record: dict[str, Any]) -> None:
        """Persist one bounded decision without retaining the publisher dossier."""
        self._conn.execute(
            """
            INSERT INTO supply_chain_audits
                (audit_id, publisher_id, product_id, capability_id, manifest_sha256,
                 mode, status, decision, score, risk_tier, findings_json,
                 remediations_json, owasp_risks_json, signature, auditor_pubkey,
                 metis_status, metis_verification_id, error_code,
                 attestations_json, permissions_sha256, permissions_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record["audit_id"],
                record.get("publisher_id", ""),
                record.get("product_id", ""),
                record.get("capability_id", ""),
                record.get("manifest_sha256", ""),
                record.get("mode", "advisory"),
                record.get("status", "unavailable"),
                record.get("decision", ""),
                record.get("score"),
                record.get("risk_tier", ""),
                json.dumps(record.get("findings") or [], ensure_ascii=False),
                json.dumps(record.get("remediations") or [], ensure_ascii=False),
                json.dumps(record.get("owasp_agentic_risks") or [], ensure_ascii=False),
                record.get("signature", ""),
                record.get("auditor_pubkey", ""),
                record.get("metis_status", "skipped"),
                record.get("metis_verification_id", ""),
                record.get("error_code", ""),
                json.dumps(record.get("attestations") or {}, ensure_ascii=False),
                record.get("permissions_sha256", ""),
                json.dumps(record.get("permissions") or {}, ensure_ascii=False),
            ),
        )
        self._conn.commit()

    def supply_audit_declaration(
        self, product_id: str, capability_id: str
    ) -> dict[str, Any] | None:
        """The most recent declaration this capability was admitted under.

        A violation report must be judged against what the *publisher* declared,
        never against anything the reporter supplies — otherwise an observer picks
        the declaration it wants to contradict.
        """
        row = self._conn.execute(
            """
            SELECT publisher_id, permissions_json, permissions_sha256
            FROM supply_chain_audits
            WHERE product_id=? AND capability_id=? AND permissions_sha256 != ''
            ORDER BY created_at DESC, id DESC LIMIT 1
            """,
            (product_id, capability_id),
        ).fetchone()
        if row is None:
            return None
        record = dict(row)
        try:
            permissions = json.loads(record.get("permissions_json") or "{}")
        except ValueError:
            permissions = {}
        return {
            "publisher_id": record.get("publisher_id", ""),
            "permissions": permissions if isinstance(permissions, dict) else {},
            "permissions_sha256": record.get("permissions_sha256", ""),
        }

    MAX_VIOLATION_REPORTERS = 32

    def supply_permission_violation_record(
        self,
        *,
        publisher_id: str,
        product_id: str,
        capability_id: str,
        permission: str,
        permissions_sha256: str,
        reporter_pubkey: str,
        signature: str,
        consumer_id: str = "",
    ) -> bool:
        """Store one signed observation. Returns False when it is a duplicate.

        The UNIQUE constraint is the consensus rule in the schema: the same
        reporter contradicting the same declaration twice is one voice, so a
        single observer can never reach the distinct-reporter threshold alone.

        Storage is capped per (capability, permission, declaration): anyone can
        mint fresh keypairs, so an uncapped intake is an unbounded table on a
        public route. Past the cap the report is refused rather than stored —
        the threshold has long since been crossed by then, so nothing is lost.
        """
        existing = self._conn.execute(
            """
            SELECT COUNT(*) FROM supply_permission_violations
            WHERE product_id=? AND capability_id=? AND permission=? AND permissions_sha256=?
            """,
            (product_id, capability_id, permission, permissions_sha256.lower()),
        ).fetchone()
        if existing and int(existing[0]) >= self.MAX_VIOLATION_REPORTERS:
            return False
        try:
            self._conn.execute(
                """
                INSERT INTO supply_permission_violations
                    (publisher_id, product_id, capability_id, permission,
                     permissions_sha256, reporter_pubkey, signature, consumer_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    publisher_id, product_id, capability_id, permission,
                    permissions_sha256.lower(), reporter_pubkey, signature, consumer_id,
                ),
            )
        except Exception as exc:
            # Name-based so the same code holds on SQLite and PostgreSQL.
            with contextlib.suppress(Exception):
                self._conn.rollback()
            if type(exc).__name__ in ("IntegrityError", "UniqueViolation"):
                return False
            raise
        self._conn.commit()
        return True

    def supply_permission_violations_for(
        self, product_id: str, capability_id: str, permissions_sha256: str, limit: int = 64,
        *, bound_only: bool = False,
    ) -> list[dict[str, Any]]:
        """Reports bound to exactly this declaration — a new one retires the old.

        ``bound_only`` restricts the result to reports whose reporter the hub
        AUTHENTICATED (``consumer_id != ''``). Anything that FEEDS A THRESHOLD must ask for
        it: an Ed25519 keypair is free, so counting reports by key lets one actor satisfy a
        two-reporter rule with two throwaway keys. The unfiltered view still exists because
        the store's own contents are a legitimate thing to inspect (the report cap, the
        operator's audit trail) — it is only unsafe as consensus input.
        """
        where = "product_id=? AND capability_id=? AND permissions_sha256=?"
        if bound_only:
            where += " AND consumer_id != ''"
        rows = self._conn.execute(
            f"""
            SELECT permission, reporter_pubkey, signature
            FROM supply_permission_violations
            WHERE {where}
            ORDER BY created_at DESC LIMIT ?
            """,
            (product_id, capability_id, permissions_sha256.lower(), page_limit(limit, maximum=VIOLATION_REPORTS_MAX)),
        ).fetchall()
        return [dict(row) for row in rows]

    def supply_permission_violation_reporters(
        self, product_id: str, capability_id: str, permissions_sha256: str, permission: str
    ) -> int:
        row = self._conn.execute(
            """
            SELECT COUNT(DISTINCT reporter_pubkey) FROM supply_permission_violations
            WHERE product_id=? AND capability_id=? AND permissions_sha256=? AND permission=?
            """,
            (product_id, capability_id, permissions_sha256.lower(), permission),
        ).fetchone()
        return int(row[0]) if row else 0

    def supply_permission_violation_bound_reporters(
        self, product_id: str, capability_id: str, permissions_sha256: str, permission: str
    ) -> int:
        """Distinct reporters whose identity the hub AUTHENTICATED, per report.

        ``supply_permission_violation_reporters`` counts DISTINCT reporter_pubkey, and an
        Ed25519 keypair is free: two throwaway keys satisfied the two-reporter consensus
        and slashed a publisher's stake at zero cost. Only ``consumer_id`` is written when
        the hub could verify who the caller is (see api.supply_permission_violation), so
        this is the count the slash ladder may act on -- the same rule
        ``supply_fault_distinct_consumers_recent`` already applies to verified failures.
        """
        row = self._conn.execute(
            """
            SELECT COUNT(DISTINCT consumer_id) FROM supply_permission_violations
            WHERE product_id=? AND capability_id=? AND permissions_sha256=? AND permission=?
              AND consumer_id != ''
            """,
            (product_id, capability_id, permissions_sha256.lower(), permission),
        ).fetchone()
        return int(row[0]) if row else 0

    def supply_audit_update_metis(
        self, audit_id: str, metis: dict[str, Any], signature: str
    ) -> None:
        """Refresh Metis status without destroying the original admission signature.

        The poll signature is retained inside ``metis_detail_json`` so operators can
        still prove the advisory refresh, while ``signature`` stays the publish-time
        decision receipt Monitor and Hub clients already cached.
        """
        detail = dict(metis)
        if signature:
            detail["poll_signature"] = str(signature)[:512]
        self._conn.execute(
            """
            UPDATE supply_chain_audits
            SET metis_status=?, metis_detail_json=?, updated_at=datetime('now')
            WHERE audit_id=?
            """,
            (
                str(metis.get("status") or "failed"),
                json.dumps(detail, ensure_ascii=False),
                audit_id,
            ),
        )
        self._conn.commit()

    @staticmethod
    def _public_supply_audit(row: Any) -> dict[str, Any]:
        item = dict(row)

        def _json_list(name: str) -> list[Any]:
            try:
                value = json.loads(str(item.get(name) or "[]"))
            except (TypeError, ValueError, json.JSONDecodeError):
                return []
            return value if isinstance(value, list) else []

        def _json_object(name: str) -> dict[str, Any]:
            try:
                value = json.loads(str(item.get(name) or "{}"))
            except (TypeError, ValueError, json.JSONDecodeError):
                return {}
            return value if isinstance(value, dict) else {}

        return {
            "audit_id": item.get("audit_id"),
            "publisher_id": item.get("publisher_id"),
            "product_id": item.get("product_id"),
            "capability_id": item.get("capability_id"),
            "manifest_sha256": item.get("manifest_sha256"),
            "mode": item.get("mode"),
            "status": item.get("status"),
            "decision": item.get("decision") or None,
            "score": item.get("score"),
            "risk_tier": item.get("risk_tier") or None,
            "findings": _json_list("findings_json"),
            "remediations": _json_list("remediations_json"),
            "owasp_agentic_risks": _json_list("owasp_risks_json"),
            # What the gate cryptographically verified. Counts, booleans and a
            # digest — publishable for the same reason the findings are, and the
            # only way an outside reader can tell proof from prose.
            "attestations": _json_object("attestations_json"),
            "permissions_sha256": item.get("permissions_sha256") or "",
            "receipt": {
                "signature": item.get("signature") or None,
                "auditor_pubkey": item.get("auditor_pubkey") or None,
            },
            "metis": {
                "status": item.get("metis_status") or "skipped",
                "verification_id": item.get("metis_verification_id") or None,
                **_json_object("metis_detail_json"),
            },
            "error_code": item.get("error_code") or None,
            "created_at": item.get("created_at"),
            "updated_at": item.get("updated_at"),
        }

    def supply_audits_recent(self, limit: int = 20) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM supply_chain_audits ORDER BY id DESC LIMIT ?",
            (page_limit(limit, maximum=SUPPLY_AUDITS_RECENT_MAX),),
        ).fetchall()
        return [self._public_supply_audit(row) for row in rows]

    def supply_audits_pending(self, limit: int = 5) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """
            SELECT audit_id, metis_verification_id
            FROM supply_chain_audits
            WHERE metis_status IN ('pending', 'running')
              AND metis_verification_id <> ''
            ORDER BY id ASC LIMIT ?
            """,
            (page_limit(limit, maximum=SUPPLY_AUDITS_PENDING_MAX),),
        ).fetchall()
        return [dict(row) for row in rows]

    def supply_audit_summary(self) -> dict[str, Any]:
        total_row = self._conn.execute(
            """
            SELECT
              COUNT(*) AS total,
              SUM(CASE WHEN decision='approve' THEN 1 ELSE 0 END) AS approved,
              SUM(CASE WHEN decision='review' THEN 1 ELSE 0 END) AS review,
              SUM(CASE WHEN decision='reject' THEN 1 ELSE 0 END) AS rejected,
              SUM(CASE WHEN status='unavailable' THEN 1 ELSE 0 END) AS unavailable,
              SUM(CASE WHEN metis_status IN ('pending','running') THEN 1 ELSE 0 END) AS pending
            FROM supply_chain_audits
            """
        ).fetchone()
        latest = self._conn.execute(
            "SELECT decision, score, risk_tier, metis_status, capability_id, product_id, created_at "
            "FROM supply_chain_audits ORDER BY id DESC LIMIT 1"
        ).fetchone()
        totals = dict(total_row) if total_row else {}
        latest_item = dict(latest) if latest else None
        return {
            "total": int(totals.get("total") or 0),
            "approved": int(totals.get("approved") or 0),
            "review": int(totals.get("review") or 0),
            "rejected": int(totals.get("rejected") or 0),
            "unavailable": int(totals.get("unavailable") or 0),
            "metis_pending": int(totals.get("pending") or 0),
            "latest": (
                {
                    "decision": latest_item.get("decision") or None,
                    "score": latest_item.get("score"),
                    "risk_tier": latest_item.get("risk_tier") or None,
                    "metis_status": latest_item.get("metis_status") or "skipped",
                    "capability_id": latest_item.get("capability_id") or None,
                    "product_id": latest_item.get("product_id") or None,
                    "created_at": latest_item.get("created_at"),
                }
                if latest_item
                else None
            ),
        }

    def supply_capability_by_invoke_url(self, invoke_url: str) -> Capability | None:
        row = self._conn.execute(
            "SELECT * FROM capabilities WHERE invoke_url=? AND source_hub='local' LIMIT 1",
            (invoke_url,),
        ).fetchone()
        return _row_to_capability(row) if row else None

    def trust_add_edge(self, src: str, dst: str, weight: float, event_type: str) -> None:
        self._conn.execute(
            "INSERT INTO trust_graph_edges (src, dst, weight, event_type) VALUES (?, ?, ?, ?)",
            (src, dst, weight, event_type),
        )
        self._conn.commit()

    def trust_list_edges(self, limit: int = 500) -> list[tuple[str, str, float, str]]:
        rows = self._conn.execute(
            "SELECT src, dst, weight, event_type FROM trust_graph_edges ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [(r["src"], r["dst"], float(r["weight"]), r["event_type"]) for r in rows]

    def supply_set_publisher_trust(self, publisher_id: str, trust_score: float) -> None:
        self._conn.execute(
            "UPDATE capabilities SET trust_score=?, stake_usd=? WHERE publisher_id=? AND source_hub='local'",
            (trust_score, self.supply_stake_get(publisher_id), publisher_id),
        )
        self._conn.commit()


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
        invoke_url=d.get("invoke_url", "") or "",
        publisher_id=d.get("publisher_id", "") or "",
        payout_address=d.get("payout_address", "") or "",
        provider_pubkey=d.get("provider_pubkey", "") or "",
        stake_usd=float(d.get("stake_usd") or 0.0),
        is_demo=bool(d.get("is_demo", 0)),
        peer_endpoint=d.get("peer_endpoint", "") or "",
        catalogue_evidence=_json_parse(d.get("catalogue_evidence", "{}")),
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
        categories=_json_list(d.get("categories", "[]")),
        trusted=bool(d.get("trusted", 0)),
        status=d.get("status") or "active",
        pin_reject_reason=d.get("pin_reject_reason") or "",
        advertised_public_key=d.get("advertised_public_key") or "",
        first_seen=d.get("first_seen") or "",
        description=d.get("description") or "",
        hub_version=d.get("hub_version") or "",
        declared_id=d.get("declared_id") or "",
        mcp_endpoint=d.get("mcp_endpoint") or "",
        pq_public_key=d.get("pq_public_key") or "",
        advertised_pq_public_key=d.get("advertised_pq_public_key") or "",
        declared_contracts=_json_obj(d.get("declared_contracts", "{}")),
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



def _utc_now_iso() -> str:
    """UTC timestamp in the same shape the crawler already writes for last_crawl."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _json_obj(val: Any) -> dict[str, Any]:
    """Parse a stored JSON object; tolerate legacy/missing/garbage values.

    Rows written before migration 030 hold NULL and rows written by an older build hold
    ``''``. Neither is an error — the peer simply had not declared anything yet.
    """
    if isinstance(val, dict):
        return val
    if isinstance(val, str) and val.strip():
        try:
            parsed = json.loads(val)
            if isinstance(parsed, dict):
                return parsed
        except (json.JSONDecodeError, TypeError):
            return {}
    return {}


def _json_list(val: Any) -> list[str]:
    """Parse a stored JSON list of category strings; tolerate legacy/missing values."""
    if isinstance(val, list):
        return [str(x) for x in val]
    if isinstance(val, str) and val.strip():
        try:
            parsed = json.loads(val)
            if isinstance(parsed, list):
                return [str(x) for x in parsed]
        except (json.JSONDecodeError, TypeError):
            return []
    return []
