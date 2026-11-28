"""The ledger: targets, observations, content-addressed blobs, labels, the Merkle log, tree heads.

Backend-neutral: every statement here runs unchanged on SQLite (development) and Postgres
(production) through :mod:`histor.db`. The schema itself lives in :mod:`histor.migrations`.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from histor import merkle
from histor.db import Backend, Tx
from histor.extras import MAX_DIFF_TOOLS, approval_relaxing_diff, approval_relaxing_hints

UNLISTED_RETENTION_DAYS = 90
UNLISTED_HOSTS_PER_DAY = 5000


def sum_counts(counts: Any) -> dict[str, int]:
    """Counters saved as JSON objects, added up; anything that is not one is skipped."""
    total: dict[str, int] = {}
    for c in counts:
        if isinstance(c, dict):
            for k, v in c.items():
                if isinstance(v, int):
                    total[k] = total.get(k, 0) + v
    return total


def dumps(value: Any) -> str:
    text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    try:
        text.encode("utf-8")
    except UnicodeEncodeError:
        # An unpaired surrogate from a stranger's JSON: escaped, it is still the same JSON value,
        # and UTF-8 (so Postgres, and SQLite's encoder) can carry it.
        text = json.dumps(value, ensure_ascii=True, separators=(",", ":"))
    return text


class Store:
    def __init__(self, db: Backend) -> None:
        self.db = db

    @property
    def backend_type(self) -> str:
        return self.db.backend_type

    # -- meta ---------------------------------------------------------------------

    def get_meta(self, key: str) -> str | None:
        with self.db.read() as tx:
            row = tx.one("SELECT value FROM meta WHERE key=?", (key,))
        return row["value"] if row else None

    @staticmethod
    def extras_scheme(tx: Tx) -> str:
        """How this log writes extras digests (histor.extras): ``legacy`` until
        ``python -m histor.extras_rekey`` moves it."""
        from histor.extras import LEGACY, META_KEY, SCHEMES
        row = tx.one("SELECT value FROM meta WHERE key=?", (META_KEY,))
        value = row["value"] if row else LEGACY
        if value not in SCHEMES:
            raise RuntimeError(f"meta {META_KEY}={value!r} is not a scheme this build knows")
        return value

    @staticmethod
    def set_meta(tx: Tx, key: str, value: str) -> None:
        tx.execute(
            "INSERT INTO meta(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )

    # -- blobs --------------------------------------------------------------------

    @staticmethod
    def put_blob(tx: Tx, digest: str, kind: str, body: Any) -> None:
        tx.execute(
            "INSERT INTO blobs(digest, kind, body) VALUES(?, ?, ?) ON CONFLICT(digest) DO NOTHING",
            (digest, kind, dumps(body)),
        )

    def blob_text(self, digest: str, kind: str) -> str | None:
        """The stored JSON as text — served as is, never parsed and re-serialised per request."""
        with self.db.read() as tx:
            row = tx.one("SELECT body FROM blobs WHERE digest=? AND kind=?", (digest, kind))
        return None if row is None else str(row["body"])

    def set_meta_value(self, key: str, value: str) -> None:
        with self.db.transaction() as tx:
            Store.set_meta(tx, key, value)

    def has_blob(self, digest: str, kind: str) -> bool:
        with self.db.read() as tx:
            return tx.one("SELECT 1 AS x FROM blobs WHERE digest=? AND kind=?", (digest, kind)) is not None

    def get_blob(self, digest: str, kind: str | None = None) -> Any | None:
        with self.db.read() as tx:
            row = tx.one("SELECT kind, body FROM blobs WHERE digest=?", (digest,))
        if row is None or (kind is not None and row["kind"] != kind):
            return None
        return json.loads(row["body"])

    # -- robots.txt (histor.robots) ------------------------------------------------

    _ROBOTS_COLUMNS = ("origin", "checked_at", "kind", "http", "body", "digest", "read_at", "unreachable_since", "note")

    def robots_rows(self) -> list[dict[str, Any]]:
        with self.db.read() as tx:
            return tx.execute(f"SELECT {', '.join(self._ROBOTS_COLUMNS)} FROM robots_txt")

    def save_robots(self, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        cols = self._ROBOTS_COLUMNS
        sql = (f"INSERT INTO robots_txt({', '.join(cols)}) VALUES({', '.join('?' for _ in cols)}) ON CONFLICT(origin) "
               f"DO UPDATE SET {', '.join(f'{c}=excluded.{c}' for c in cols[1:])}")
        with self.db.transaction() as tx:
            for row in rows:
                tx.execute(sql, tuple(row.get(c) for c in cols))

    # -- classifier verdicts (advisory, NOT in the signed log) ---------------------

    @staticmethod
    def put_classification(tx: Tx, toolset: str, model: str, verdict: Any, updated_at: str) -> None:
        tx.execute(
            "INSERT INTO classifications(toolset, model, verdict, updated_at) VALUES(?, ?, ?, ?) "
            "ON CONFLICT(toolset, model) DO UPDATE SET verdict=excluded.verdict, updated_at=excluded.updated_at",
            (toolset, model, dumps(verdict), updated_at),
        )

    def classification(self, toolset: str, model: str) -> dict[str, Any] | None:
        """The advisory verdict for a tool set from one model, or None. Not a log entry."""
        with self.db.read() as tx:
            row = tx.one(
                "SELECT verdict, updated_at FROM classifications WHERE toolset=? AND model=?",
                (toolset, model),
            )
        if row is None:
            return None
        out = json.loads(row["verdict"])
        out["updatedAt"] = row["updated_at"]
        return out

    def latest_classification(self, toolset: str) -> dict[str, Any] | None:
        """The most recent advisory verdict for a tool set from ANY model (the verdict names its
        model), or None. Used by /check, which reads stored verdicts and never calls a model."""
        with self.db.read() as tx:
            row = tx.one(
                "SELECT verdict, updated_at FROM classifications WHERE toolset=? "
                "ORDER BY updated_at DESC, model LIMIT 1",
                (toolset,),
            )
        if row is None:
            return None
        out = json.loads(row["verdict"])
        out["updatedAt"] = row["updated_at"]
        return out

    # -- targets ------------------------------------------------------------------

    def target(self, target_id: str) -> dict[str, Any] | None:
        with self.db.read() as tx:
            return tx.one("SELECT * FROM targets WHERE id=?", (target_id,))

    def target_with_extras(self, target_id: str) -> dict[str, Any] | None:
        """Read the target and the extras body at its digest in the same database snapshot."""
        from histor.extras import LEGACY, META_KEY

        with self.db.read() as tx:
            return tx.one(
                "SELECT t.*, b.body AS extras_body, COALESCE(m.value, ?) AS preferred_extras_scheme "
                "FROM targets t LEFT JOIN blobs b ON b.digest=t.current_extras AND b.kind='toolextras' "
                "LEFT JOIN meta m ON m.key=? WHERE t.id=?",
                (LEGACY, META_KEY, target_id),
            )

    def targets_by(self, *, endpoint: str | None = None, name: str | None = None) -> list[dict[str, Any]]:
        with self.db.read() as tx:
            if endpoint:
                return tx.execute("SELECT * FROM targets WHERE endpoint=? ORDER BY delisted, name", (endpoint,))
            return tx.execute("SELECT * FROM targets WHERE name=? ORDER BY delisted, endpoint", (name or "",))

    def observed_target_ids(self, limit: int, offset: int = 0) -> list[tuple[str, str | None]]:
        """Listed targets HISTOR has a tool set for, oldest first: the pages worth indexing."""
        with self.db.read() as tx:
            rows = tx.execute(
                "SELECT id, last_ok FROM targets WHERE delisted=0 AND current_toolset IS NOT NULL ORDER BY first_pinned, id LIMIT ? OFFSET ?",
                (limit, offset),
            )
        return [(r["id"], r["last_ok"]) for r in rows]

    def count_observed_targets(self) -> int:
        with self.db.read() as tx:
            row = tx.one("SELECT COUNT(*) AS n FROM targets WHERE delisted=0 AND current_toolset IS NOT NULL")
        return int((row or {}).get("n") or 0)

    def package_states(self) -> dict[str, dict[str, Any]]:
        """What a crawl needs to plan the package sandbox, for every package target, in one query.
        Asking target by target cost a round trip each — ~47 000 of them — before any package ran."""
        with self.db.read() as tx:
            rows = tx.execute("SELECT id, package_version, package_signals, last_status, last_attempt, last_detail, "
                              "current_subject, current_toolset FROM targets "
                              "WHERE transport = 'stdio'")
        return {r["id"]: r for r in rows}

    def all_targets(self) -> list[dict[str, Any]]:
        with self.db.read() as tx:
            return tx.execute("SELECT * FROM targets ORDER BY name, endpoint")

    def search_targets(self, q: str, *, state: str, limit: int, offset: int) -> tuple[int, list[dict[str, Any]]]:
        where = ["delisted = 0"]
        args: list[Any] = []
        if q:
            needle = "%" + q.lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            where.append(
                "(LOWER(name) LIKE ? ESCAPE '\\' OR LOWER(endpoint) LIKE ? ESCAPE '\\' "
                "OR LOWER(COALESCE(title, '')) LIKE ? ESCAPE '\\')"
            )
            args += [needle, needle, needle]
        state_sql = {
            # Pinned = a tool-set digest on record. A set HISTOR could not digest has a names-only
            # descriptor (current_subject) but nothing a client could be compared with: that is
            # `undigested`, kept apart from `unobserved` (no tool list read at all), which until
            # 2026-10-31 held both (agent-control-standard#38).
            "pinned": "current_toolset IS NOT NULL",
            "changed": "changes > 0",
            "flagged": "(block_matches > 0 OR advise_matches > 0 OR record_matches > 0)",
            "unobserved": "current_subject IS NULL",
            "undigested": "current_subject IS NOT NULL AND current_toolset IS NULL",
        }.get(state)
        if state_sql:
            where.append(state_sql)
        clause = " AND ".join(where)
        with self.db.read() as tx:
            total = int(tx.one(f"SELECT COUNT(*) AS n FROM targets WHERE {clause}", args)["n"])
            rows = tx.execute(
                f"SELECT * FROM targets WHERE {clause} "
                "ORDER BY CASE WHEN current_toolset IS NULL THEN 1 ELSE 0 END, changes DESC, name, endpoint "
                "LIMIT ? OFFSET ?",
                [*args, limit, offset],
            )
        return total, rows

    # -- observations ---------------------------------------------------------------

    def history(self, target_id: str, limit: int = 400) -> list[dict[str, Any]]:
        with self.db.read() as tx:
            return tx.execute(
                "SELECT observed_at, status, detail, subject, toolset, tool_count, server_name, server_version, "
                "package_version, launch, protocol, registry_version, instructions FROM observations WHERE target_id=? "
                "ORDER BY observed_at DESC, id DESC LIMIT ?",
                (target_id, limit),
            )

    def toolset_seen(self, target_id: str, toolset: str) -> dict[str, Any] | None:
        with self.db.read() as tx:
            row = tx.one(
                "SELECT MIN(observed_at) AS first_seen, MAX(observed_at) AS last_seen, COUNT(*) AS n "
                "FROM observations WHERE target_id=? AND toolset=?",
                (target_id, toolset),
            )
        if not row or not int(row["n"] or 0):
            return None
        return {"first_seen": row["first_seen"], "last_seen": row["last_seen"], "observations": int(row["n"])}

    # -- the other-revision reading (migration 027) ---------------------------------

    def revision_reading(self, target_id: str) -> dict[str, Any] | None:
        """What this target listed to a handshake client, as last read beside its log entry."""
        with self.db.read() as tx:
            return tx.one("SELECT * FROM revision_readings WHERE target_id=?", (target_id,))

    def last_protocol(self, target_id: str) -> str:
        """The protocol revision of this target's latest successful reading, or ``""``."""
        with self.db.read() as tx:
            row = tx.one("SELECT protocol FROM observations WHERE target_id=? AND status='ok' "
                         "ORDER BY observed_at DESC LIMIT 1", (target_id,))
        return str((row or {}).get("protocol") or "")

    def revision_reading_index(self) -> dict[str, tuple[str, str]]:
        """``target_id -> (beside_toolset, read_at)`` for every stored reading: what the crawl needs
        to decide whether one is due."""
        with self.db.read() as tx:
            rows = tx.execute("SELECT target_id, beside_toolset, read_at FROM revision_readings")
        return {r["target_id"]: (r["beside_toolset"], r["read_at"]) for r in rows}

    def put_revision_reading(self, target_id: str, *, beside_toolset: str, protocol: str, toolset: str | None,
                             tool_count: int | None, status: str, read_at: str) -> None:
        with self.db.transaction() as tx:
            tx.execute(
                "INSERT INTO revision_readings(target_id, beside_toolset, protocol, toolset, tool_count, status, read_at) "
                "VALUES(?, ?, ?, ?, ?, ?, ?) ON CONFLICT(target_id) DO UPDATE SET beside_toolset=excluded.beside_toolset, "
                "protocol=excluded.protocol, toolset=excluded.toolset, tool_count=excluded.tool_count, "
                "status=excluded.status, read_at=excluded.read_at",
                (target_id, beside_toolset, protocol[:40], toolset, tool_count, status[:40], read_at),
            )

    # -- labels + log ---------------------------------------------------------------

    def label(self, label_id: str) -> dict[str, Any] | None:
        with self.db.read() as tx:
            return tx.one("SELECT * FROM labels WHERE id=?", (label_id,))

    def label_by_digest(self, digest: str) -> dict[str, Any] | None:
        with self.db.read() as tx:
            return tx.one("SELECT * FROM labels WHERE digest=?", (digest,))

    def labels_for(self, target_id: str, limit: int = 50) -> list[dict[str, Any]]:
        with self.db.read() as tx:
            return tx.execute(
                "SELECT id, method, verdict, subject, observed_at, issued_at, digest, leaf_index FROM labels "
                "WHERE target_id=? ORDER BY leaf_index DESC LIMIT ?",
                (target_id, limit),
            )

    # The trees this store holds: the label log, the receipts log (histor.receipts), and the
    # publisher-revision log (histor.signed_revisions). A table name reaches SQL only through
    # this set, never from a caller's string.
    NODE_TABLES = frozenset({"log_nodes", "receipt_log_nodes", "revision_log_nodes"})

    @classmethod
    def _nodes(cls, table: str) -> str:
        if table not in cls.NODE_TABLES:
            raise ValueError(f"unknown log table {table!r}")
        return table

    @classmethod
    def log_size(cls, tx: Tx, table: str = "log_nodes") -> int:
        # MAX over the (level, idx) primary key is an index lookup on both engines; COUNT(*) would
        # scan every leaf on every append once the log holds millions of labels.
        row = tx.one(f"SELECT MAX(idx) AS last FROM {cls._nodes(table)} WHERE level=0")
        return 0 if row is None or row["last"] is None else int(row["last"]) + 1

    def tree_size(self) -> int:
        with self.db.read() as tx:
            return self.log_size(tx)

    @classmethod
    def reader(cls, tx: Tx, table: str = "log_nodes") -> merkle.NodeReader:
        nodes = cls._nodes(table)

        def read(level: int, idx: int) -> bytes:
            row = tx.one(f"SELECT hash FROM {nodes} WHERE level=? AND idx=?", (level, idx))
            if row is None:
                raise KeyError((level, idx))
            return bytes.fromhex(row["hash"])

        return read

    @classmethod
    def append_leaf(cls, tx: Tx, leaf: bytes, table: str = "log_nodes") -> int:
        """Append one leaf inside *tx*. The caller must already hold that log's lock."""
        nodes = cls._nodes(table)
        index = cls.log_size(tx, table)
        for level, idx, digest in merkle.appended_nodes(index, leaf, cls.reader(tx, table)):
            tx.execute(f"INSERT INTO {nodes}(level, idx, hash) VALUES(?, ?, ?)", (level, idx, digest.hex()))
        return index

    def latest_sth(self) -> dict[str, Any] | None:
        with self.db.read() as tx:
            row = tx.one("SELECT body FROM sths ORDER BY tree_size DESC LIMIT 1")
        return json.loads(row["body"]) if row else None

    def sth(self, tree_size: int) -> dict[str, Any] | None:
        with self.db.read() as tx:
            row = tx.one("SELECT body FROM sths WHERE tree_size=?", (tree_size,))
        return json.loads(row["body"]) if row else None

    def cosignature_lines(self, tree_size: int) -> list[str]:
        with self.db.read() as tx:
            rows = tx.execute("SELECT line FROM cosignatures WHERE tree_size=? ORDER BY name", (tree_size,))
        return [row["line"] for row in rows]

    def latest_cosigned(self) -> tuple[int, int] | None:
        """(tree size, number of witnesses) of the largest head any witness co-signed, or None."""
        with self.db.read() as tx:
            row = tx.one("SELECT tree_size, COUNT(*) AS n FROM cosignatures "
                         "WHERE tree_size = (SELECT MAX(tree_size) FROM cosignatures) GROUP BY tree_size")
        return (int(row["tree_size"]), int(row["n"])) if row else None

    def store_cosignatures(self, tree_size: int, lines: list[tuple[str, str]]) -> int:
        """Keep one line per (size, witness name); a repeat replaces. Returns how many were written."""
        now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        with self.db.transaction() as tx:
            for name, line in lines:
                tx.execute("DELETE FROM cosignatures WHERE tree_size=? AND name=?", (tree_size, name))
                tx.execute("INSERT INTO cosignatures(tree_size, name, line, received_at) VALUES(?, ?, ?, ?)",
                           (tree_size, name, line, now))
        return len(lines)

    def entries(self, start: int, end: int) -> list[dict[str, Any]]:
        with self.db.read() as tx:
            return tx.execute(
                "SELECT leaf_index, id, digest, method, verdict, target_id, issued_at FROM labels "
                "WHERE leaf_index >= ? AND leaf_index < ? ORDER BY leaf_index",
                (start, end),
            )

    # -- changes ------------------------------------------------------------------

    @staticmethod
    def _change_row(row: dict[str, Any]) -> dict[str, Any]:
        row = dict(row)
        row["summary"] = json.loads(row["summary"])
        return row

    def changes(self, limit: int = 50, before_id: int | None = None, target_id: str | None = None,
                target_ids: list[str] | None = None, after_id: int | None = None) -> list[dict[str, Any]]:
        """Newest first; with `after_id`, oldest first from just after that id — the order an
        incremental reader (a feed consumer, a mirror) needs to resume where it stopped."""
        sql = "SELECT c.*, t.name, t.endpoint, t.title FROM changes c JOIN targets t ON t.id = c.target_id WHERE 1=1"
        args: list[Any] = []
        if after_id is not None:
            sql += " AND c.id > ?"
            args.append(after_id)
        if target_ids is not None:
            if not target_ids:
                return []
            sql += f" AND c.target_id IN ({', '.join('?' for _ in target_ids)})"
            args.extend(target_ids)
        if before_id:
            sql += " AND c.id < ?"
            args.append(before_id)
        if target_id:
            sql += " AND c.target_id = ?"
            args.append(target_id)
        sql += " ORDER BY c.id " + ("ASC" if after_id is not None else "DESC") + " LIMIT ?"
        args.append(limit)
        with self.db.read() as tx:
            return [self._change_row(r) for r in tx.execute(sql, args)]

    @staticmethod
    def _extras_change_row(row: dict[str, Any], summary: dict[str, Any]) -> dict[str, Any]:
        return {"id": row["seq"], "observedAt": row["observed_at"], "fromExtrasDigest": row["from_extras"],
                "toExtrasDigest": row["to_extras"], "summary": summary}

    def extras_changes(self, target_id: str, limit: int = 20, *,
                       approval_relaxing: bool = False) -> list[dict[str, Any]]:
        """Newest first. Filter a single target's history before limiting results."""
        if approval_relaxing:
            return self._select_approval_changes(limit, target_id=target_id)
        with self.db.read() as tx:
            rows = tx.execute(
                "SELECT seq, observed_at, from_extras, to_extras, summary FROM extras_changes "
                "WHERE target_id=? ORDER BY seq DESC LIMIT ?", (target_id, limit))
        return [self._extras_change_row(r, json.loads(r["summary"])) for r in rows]

    @classmethod
    def _approval_change_row(cls, tx: Tx, row: dict[str, Any]) -> dict[str, Any] | None:
        summary = json.loads(row["summary"])
        matches = {
            name: {"annotations": hints}
            for name, tool in summary["tools"].items()
            if (hints := approval_relaxing_hints(tool.get("annotations", {})))
        }
        if summary.get("truncated"):
            blobs = tx.execute(
                "SELECT digest, body FROM blobs WHERE digest IN (?, ?) AND kind='toolextras'",
                (row["from_extras"], row["to_extras"]))
            by_digest = {b["digest"]: json.loads(b["body"]) for b in blobs}
            if row["from_extras"] in by_digest and row["to_extras"] in by_digest:
                matches = approval_relaxing_diff(by_digest[row["from_extras"]], by_digest[row["to_extras"]])
        if not matches:
            return None
        names = list(matches)[:MAX_DIFF_TOOLS]
        filtered = {"tools": {name: matches[name] for name in names},
                    "changedTools": len(matches), "approvalRelaxing": names}
        if len(matches) > len(names):
            filtered["truncated"] = True
        return cls._extras_change_row(row, filtered)

    def approval_relaxing_change(self, target_id: str, event_id: int) -> dict[str, Any] | None:
        """Resolve an exact event even after it moves beyond the latest page of results."""
        with self.db.read() as tx:
            row = tx.one(
                "SELECT seq, observed_at, from_extras, to_extras, summary FROM extras_changes "
                "WHERE target_id=? AND seq=? AND from_extras IS NOT NULL AND to_extras IS NOT NULL",
                (target_id, event_id))
            return self._approval_change_row(tx, row) if row else None

    def approval_relaxing_changes(
        self, limit: int = 50, before_id: int | None = None, after_id: int | None = None,
        *, target_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Filter extras changes across servers with exclusive sequence cursors.

        Results are newest first unless resuming with ``after_id``, which reads forward.
        """
        return self._select_approval_changes(limit, before_id=before_id, after_id=after_id,
                                             target_id=target_id, include_target=True)

    def _select_approval_changes(
        self, limit: int, *, before_id: int | None = None, after_id: int | None = None,
        target_id: str | None = None, include_target: bool = False,
    ) -> list[dict[str, Any]]:
        # Stored summaries use literal ASCII keys. This cheap prefilter only finds possible
        # matches. Reuse the exact boolean test above and recover hints from truncated summaries.
        # Keep the PostgreSQL predicate in sync with deploy/approval-changes-index.sql.
        find = "strpos" if self.backend_type == "postgresql" else "instr"
        sql = "SELECT c.seq, c.observed_at, c.from_extras, c.to_extras, c.summary"
        if include_target:
            sql += ", t.id AS target_id, t.name AS target_name, t.title AS target_title"
        sql += " FROM extras_changes c"
        if include_target:
            sql += " JOIN targets t ON t.id=c.target_id"
        sql += (
            " WHERE c.from_extras IS NOT NULL AND c.to_extras IS NOT NULL"
            f""" AND ({find}(c.summary, '"readOnlyHint"') > 0"""
            f""" OR {find}(c.summary, '"destructiveHint"') > 0"""
            f""" OR {find}(c.summary, '"truncated"') > 0)"""
        )
        args: list[Any] = []
        if target_id is not None:
            sql += " AND c.target_id=?"
            args.append(target_id)
        if before_id is not None and after_id is not None:
            sql += " AND c.seq < ?"
            args.append(before_id)
        forward = after_id is not None
        comparison, order = (">", "ASC") if forward else ("<", "DESC")
        cursor = after_id if forward else before_id
        batch_size = 100
        items = []
        with self.db.read() as tx:
            while len(items) < limit:
                bound = f" AND c.seq {comparison} ?" if cursor is not None else ""
                params = (*args, cursor, batch_size) if cursor is not None else (*args, batch_size)
                rows = tx.execute(f"{sql}{bound} ORDER BY c.seq {order} LIMIT ?", params)
                for row in rows:
                    change = self._approval_change_row(tx, row)
                    if change is None:
                        continue
                    if include_target:
                        change.update(targetId=row["target_id"], targetName=row["target_name"],
                                      targetTitle=row["target_title"])
                    items.append(change)
                    if len(items) == limit:
                        return items
                if len(rows) < batch_size:
                    break
                cursor = rows[-1]["seq"]
        return items

    def change(self, change_id: int) -> dict[str, Any] | None:
        with self.db.read() as tx:
            row = tx.one(
                "SELECT c.*, t.name, t.endpoint, t.title FROM changes c JOIN targets t ON t.id = c.target_id WHERE c.id=?",
                (change_id,),
            )
        return self._change_row(row) if row else None

    def count_changes_since(self, since: str) -> int:
        with self.db.read() as tx:
            return int(tx.one("SELECT COUNT(*) AS n FROM changes WHERE observed_at >= ?", (since,))["n"])

    # -- publisher-declared tool sets ----------------------------------------------------

    @staticmethod
    def _active_declarations(tx: Tx) -> dict[str, dict[str, str]]:
        """target → {digest: source} for every set a publisher declares now."""
        active: dict[str, dict[str, str]] = {}
        for row in tx.execute("SELECT target_id, toolset, source FROM declared_toolsets WHERE withdrawn_at IS NULL"):
            active.setdefault(row["target_id"], {})[row["toolset"]] = row["source"] or "registry"
        return active

    @staticmethod
    def _apply_declaration(tx: Tx, target_id: str, version: str | None, now: str,
                           registry: list[dict[str, Any]] | None, url: list[dict[str, Any]] | None,
                           active: dict[str, str]) -> tuple[int, int]:
        """What one target's publisher declares now, from its registry entry and from its declaration
        file. ``None`` for a source leaves that source's sets as they are: a file that could not be
        read this time is not a withdrawal. A digest both name counts as the registry's. Returns
        (sets declared now, sets withdrawn). Server-card sets (source 'card') are histor.cards' to manage."""
        active = {d: src for d, src in active.items() if src != "card"}
        filed = ("url", "signed")  # read from the file the entry points at; 'signed': histor.signed_declaration
        keep = {d for d, src in active.items() if (src in filed and url is None) or (src not in filed and registry is None)}
        entries: dict[str, tuple[dict[str, Any], str]] = {}
        for source, sets in (("registry", registry), ("url", url)):
            for d in sets or ():
                if d["digest"] not in keep and d["digest"] not in entries:
                    entries[d["digest"]] = (d, d["source"] if source == "url" and d.get("source") in filed else source)
        for digest, (d, source) in entries.items():
            tx.execute(
                "INSERT INTO declared_toolsets(target_id, toolset, tool_count, when_text, registry_version, "
                "first_declared, last_declared, withdrawn_at, source) VALUES(?, ?, ?, ?, ?, ?, ?, NULL, ?) "
                "ON CONFLICT(target_id, toolset) DO UPDATE SET tool_count=excluded.tool_count, "
                "when_text=excluded.when_text, registry_version=excluded.registry_version, "
                "last_declared=excluded.last_declared, withdrawn_at=NULL, source=excluded.source",
                (target_id, digest, d.get("count"), d.get("when"), version, now, now, source),
            )
        gone = set(active) - keep - set(entries)
        for digest in gone:
            tx.execute("UPDATE declared_toolsets SET withdrawn_at=? WHERE target_id=? AND toolset=?", (now, target_id, digest))
        return len(entries) + len(keep), len(gone)

    @staticmethod
    def _note_read(tx: Tx, target_id: str, url: str, now: str, error: str | None,
                   pointer: str | None = None, statement: str | None = None) -> None:
        """How the last read of a target's declaration file went. A new URL starts a new record.
        *pointer*: for a signed statement, what the listing says (JSON); *statement*: the detail of this
        check (JSON), kept from the last check that produced one."""
        tx.execute(
            "INSERT INTO declaration_urls(target_id, url, first_seen, last_fetched, last_ok, last_error, pointer, statement) "
            "VALUES(?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(target_id) DO UPDATE SET "
            "statement=CASE WHEN excluded.statement IS NOT NULL THEN excluded.statement "
            "WHEN declaration_urls.url = excluded.url THEN declaration_urls.statement ELSE NULL END, "
            "pointer=excluded.pointer, "
            "first_seen=CASE WHEN declaration_urls.url = excluded.url THEN declaration_urls.first_seen ELSE excluded.first_seen END, "
            "last_ok=CASE WHEN excluded.last_ok IS NOT NULL THEN excluded.last_ok "
            "WHEN declaration_urls.url = excluded.url THEN declaration_urls.last_ok ELSE NULL END, "
            "url=excluded.url, last_fetched=excluded.last_fetched, last_error=excluded.last_error",
            (target_id, url, now, now, None if error else now, error, pointer, statement),
        )

    @staticmethod
    def sync_declarations(tx: Tx, targets: list[Any], now: str,
                          files: dict[str, tuple[Any, ...]] | None = None) -> dict[str, Any]:
        """Record what each listed target's publisher declares now (histor.declared): the sets in its
        registry entry, and those in the declaration file the entry points at, read just before this
        transaction (*files*: url → (sets, error)). Only targets in this harvest are touched: a
        registry outage or a delisting withdraws nothing."""
        files = files or {}
        active = Store._active_declarations(tx)
        with_url = {r["target_id"] for r in tx.execute("SELECT target_id FROM declaration_urls")}
        servers: set[str] = set()
        sets = withdrawn = 0
        ignored: list[dict[str, str]] = []
        unread: list[dict[str, str]] = []
        urls: set[str] = set()
        reported: set[str] = set()
        for t in targets:
            if t.declared_ignored and t.name not in reported and len(ignored) < 50:
                reported.add(t.name)
                ignored.extend({"server": t.name, "reason": r} for r in t.declared_ignored[:4])
            if not (t.declared or t.declared_url or t.id in active or t.id in with_url):
                continue
            from_url: list[dict[str, Any]] | None = []
            if t.declared_url:
                read = files.get(t.declared_url, (None, "not read"))
                from_url, error = read[0], read[1]
                pointer = getattr(t, "declared_pointer", None)
                Store._note_read(tx, t.id, t.declared_url, now, error, dumps(pointer) if pointer else None,
                                 dumps(read[2]) if len(read) > 2 and read[2] else None)
                urls.add(t.declared_url)
                if error and t.declared_url not in {u["url"] for u in unread} and len(unread) < 20:
                    unread.append({"server": t.name, "url": t.declared_url, "error": error})
            elif t.id in with_url:
                # The entry no longer points at a file: what the file declared goes with it.
                tx.execute("DELETE FROM declaration_urls WHERE target_id=?", (t.id,))
            n, w = Store._apply_declaration(tx, t.id, t.version, now, list(t.declared), from_url, active.get(t.id, {}))
            if n:
                servers.add(t.name)
                sets += n
            withdrawn += w
        return {"servers": len(servers), "sets": sets, "withdrawn": withdrawn,
                **({"files": len(urls)} if urls else {}), **({"unread": unread} if unread else {}),
                **({"ignored": ignored} if ignored else {})}

    def declaration_files(self) -> list[dict[str, Any]]:
        """Every listed target whose registry entry points at a declaration file."""
        with self.db.read() as tx:
            return [dict(r) for r in tx.execute(
                "SELECT d.target_id, d.url, d.pointer, t.name, t.version FROM declaration_urls d "
                "JOIN targets t ON t.id = d.target_id WHERE t.delisted = 0 ORDER BY d.target_id")]

    def refresh_declarations(self, rows: list[dict[str, Any]], files: dict[str, tuple[Any, ...]],
                             now: str) -> dict[str, Any]:
        """Apply declaration files read between crawls; the registry's own sets are left as they are."""
        changed = withdrawn = 0
        with self.db.transaction() as tx:
            active = Store._active_declarations(tx)
            for row in rows:
                read = files.get(row["url"], (None, "not read"))
                sets, error = read[0], read[1]
                Store._note_read(tx, row["target_id"], row["url"], now, error, row.get("pointer"),
                                 dumps(read[2]) if len(read) > 2 and read[2] else None)
                before = set(active.get(row["target_id"], {}))
                _, w = Store._apply_declaration(tx, row["target_id"], row["version"], now, None, sets,
                                                active.get(row["target_id"], {}))
                withdrawn += w
                if sets is not None and {d["digest"] for d in sets} - before:
                    changed += 1
        urls = {r["url"] for r in rows}
        return {"files": len(urls), "unread": sum(1 for u in urls if files.get(u, (None, "not read"))[1]),
                "targetsWithNewSets": changed, "withdrawn": withdrawn}

    _DECLARED = ("SELECT d.*, CASE WHEN d.source = 'card' THEN c.url ELSE u.url END AS url FROM declared_toolsets d "
                 "LEFT JOIN declaration_urls u ON u.target_id = d.target_id "
                 "LEFT JOIN server_cards c ON c.target_id = d.target_id ")

    # -- MCP server cards (histor.cards) ------------------------------------------------

    def cards_due(self, now: str, limit: int) -> tuple[list[dict[str, Any]], list[str]]:
        """Listed remote endpoints whose card is due (a day after a card read, a week after none was found),
        oldest first; and every listed remote endpoint, to tell host-wide cards apart."""
        from histor.cards import ABSENT_RECHECK_S, FRESH_S
        from histor.remote_schedule import after
        listed = "t.delisted = 0 AND t.skip_reason IS NULL AND t.transport = 'streamable-http'"
        with self.db.read() as tx:
            due = tx.execute(
                "SELECT t.id, t.name, t.endpoint, t.version, c.url AS card_url, c.status AS card_status "
                "FROM targets t LEFT JOIN server_cards c ON c.target_id = t.id "
                f"WHERE {listed} AND (c.target_id IS NULL OR (c.status IN ('absent', 'robots') AND c.checked_at < ?) "
                "OR (c.status NOT IN ('absent', 'robots') AND c.checked_at < ?)) "
                "ORDER BY CASE WHEN c.checked_at IS NULL THEN 0 ELSE 1 END, c.checked_at, t.id LIMIT ?",
                (after(now, -ABSENT_RECHECK_S), after(now, -FRESH_S), limit))
            every = [r["endpoint"] for r in tx.execute(f"SELECT t.endpoint FROM targets t WHERE {listed}")]
        return [dict(r) for r in due], every

    def apply_cards(self, results: list[tuple[dict[str, Any], Any, str | None, list[dict[str, Any]] | None]],
                    now: str) -> dict[str, int]:
        """Record card reads: (target row, histor.cards.Verdict, tool-set digest or None, canonical entries or
        None) each. A card with a full tool list declares its set (source 'card') and withdraws the card's
        earlier sets; a card that is gone or lists no tools withdraws them; a failed read changes nothing
        but the row's date."""
        from histor.cards import DECISIVE, DECLARED
        counts = {"declared": 0, "withdrawn": 0}

        def apply_one(tx: Any, target: dict[str, Any], verdict: Any, digest: str | None,
                      entries: list[dict[str, Any]] | None) -> None:
            tid = target["id"]
            prior = tx.one("SELECT * FROM server_cards WHERE target_id=?", (tid,)) or {}
            found = verdict.status in DECISIVE and verdict.status != "absent"
            tx.execute(
                "INSERT INTO server_cards(target_id, url, checked_at, status, toolset, tool_count, first_seen, last_ok, detail) "
                "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(target_id) DO UPDATE SET url=excluded.url, "
                "checked_at=excluded.checked_at, status=excluded.status, toolset=excluded.toolset, "
                "tool_count=excluded.tool_count, first_seen=excluded.first_seen, last_ok=excluded.last_ok, detail=excluded.detail",
                (tid, verdict.url or prior.get("url"), now, verdict.status,
                 digest if verdict.status == DECLARED else (prior.get("toolset") if verdict.status not in DECISIVE else None),
                 len(entries) if entries is not None else (prior.get("tool_count") if verdict.status not in DECISIVE else None),
                 prior.get("first_seen") or (now if found else None),
                 now if found else prior.get("last_ok"), (verdict.detail or "")[:300] or None))
            if verdict.status not in DECISIVE:
                return
            if verdict.status == DECLARED and digest:
                Store.put_blob(tx, digest, "toolset", entries)
                tx.execute(
                    "INSERT INTO declared_toolsets(target_id, toolset, tool_count, when_text, registry_version, "
                    "first_declared, last_declared, withdrawn_at, source) VALUES(?, ?, ?, NULL, ?, ?, ?, NULL, 'card') "
                    "ON CONFLICT(target_id, toolset) DO UPDATE SET tool_count=excluded.tool_count, "
                    "last_declared=excluded.last_declared, withdrawn_at=NULL, source='card' "
                    "WHERE declared_toolsets.source = 'card' OR declared_toolsets.withdrawn_at IS NOT NULL",
                    (tid, digest, len(entries or []), target.get("version"), now, now))
                counts["declared"] += 1
            gone = tx.execute("SELECT toolset FROM declared_toolsets WHERE target_id=? AND source='card' "
                              "AND withdrawn_at IS NULL AND toolset<>?", (tid, digest or ""))
            for row in gone:
                tx.execute("UPDATE declared_toolsets SET withdrawn_at=? WHERE target_id=? AND toolset=?",
                           (now, tid, row["toolset"]))
            counts["withdrawn"] += len(gone)

        for i in range(0, len(results), 50):
            with self.db.transaction() as tx:
                for item in results[i:i + 50]:
                    apply_one(tx, *item)
        return counts

    def server_card(self, target_id: str) -> dict[str, Any] | None:
        """The endpoint's server card as the API shows it: where, when, what it decided, its tool names."""
        with self.db.read() as tx:
            row = tx.one("SELECT * FROM server_cards WHERE target_id=?", (target_id,))
        if row is None or row["status"] in ("absent", "robots"):
            return None
        names = None
        if row["toolset"]:
            entries = self.get_blob(row["toolset"], "toolset")
            if isinstance(entries, list):
                names = [e.get("name") for e in entries if isinstance(e, dict)]
        return {k: v for k, v in (("url", row["url"]), ("status", row["status"]), ("checkedAt", row["checked_at"]),
                                  ("firstSeen", row["first_seen"]), ("lastOk", row["last_ok"]), ("detail", row["detail"]),
                                  ("toolSetDigest", row["toolset"]), ("toolCount", row["tool_count"]),
                                  ("toolNames", names)) if v is not None}

    def declared_toolset(self, target_id: str, toolset: str) -> dict[str, Any] | None:
        """The publisher's current declaration of this set at this target, if it makes one."""
        with self.db.read() as tx:
            row = tx.one(self._DECLARED + "WHERE d.target_id=? AND d.toolset=? AND d.withdrawn_at IS NULL",
                         (target_id, toolset))
        return dict(row) if row else None

    def declared_toolsets(self, target_id: str) -> list[dict[str, Any]]:
        """Every set the publisher declared at this target, current ones first."""
        with self.db.read() as tx:
            rows = tx.execute(
                self._DECLARED + "WHERE d.target_id=? "
                "ORDER BY CASE WHEN d.withdrawn_at IS NULL THEN 0 ELSE 1 END, d.first_declared, d.toolset",
                (target_id,),
            )
        return [dict(r) for r in rows]

    def declaration_file(self, target_id: str) -> dict[str, Any] | None:
        """The target's declaration file and how its last reads went."""
        with self.db.read() as tx:
            row = tx.one("SELECT url, first_seen, last_fetched, last_ok, last_error, pointer, statement "
                         "FROM declaration_urls WHERE target_id=?", (target_id,))
        if not row:
            return None
        pointer = json.loads(row["pointer"]) if row["pointer"] else None
        return {k: v for k, v in (
            ("url", row["url"]), ("firstSeen", row["first_seen"]), ("lastRead", row["last_fetched"]),
            ("lastOk", row["last_ok"]), ("lastError", row["last_error"]),
            # A signed statement the listing points at (histor.signed_declaration): the pointer's hash and the
            # detail of the last check that produced one.
            ("kind", "signed" if pointer else None), ("pointerHash", pointer["hash"] if pointer else None),
            ("statement", json.loads(row["statement"]) if row["statement"] else None)) if v is not None}

    # -- client reports -------------------------------------------------------------

    def add_client_report(self, target_id: str, toolset: str, day: str) -> None:
        with self.db.transaction() as tx:
            tx.execute(
                "INSERT INTO client_reports(target_id, toolset, day, count) VALUES(?, ?, ?, 1) "
                "ON CONFLICT(target_id, toolset, day) DO UPDATE SET count = client_reports.count + 1",
                (target_id, toolset, day),
            )

    def add_unlisted_query(self, host: str, day: str) -> None:
        """Count one /check for a host HISTOR does not list. A new host on a full day is dropped, so
        a caller inventing hosts cannot grow the table without bound; old days are pruned then too."""
        with self.db.transaction() as tx:
            if tx.one("SELECT 1 AS x FROM unlisted_queries WHERE host=? AND day=?", (host, day)) is None:
                row = tx.one("SELECT COUNT(*) AS n FROM unlisted_queries WHERE day=?", (day,))
                if int((row or {}).get("n") or 0) >= UNLISTED_HOSTS_PER_DAY:
                    return
                cutoff = (datetime.strptime(day, "%Y-%m-%d") - timedelta(days=UNLISTED_RETENTION_DAYS)).strftime("%Y-%m-%d")
                tx.execute("DELETE FROM unlisted_queries WHERE day < ?", (cutoff,))
            tx.execute(
                "INSERT INTO unlisted_queries(host, day, count) VALUES(?, ?, 1) "
                "ON CONFLICT(host, day) DO UPDATE SET count = unlisted_queries.count + 1",
                (host, day),
            )

    def unlisted_queries(self, since_day: str, limit: int = 100) -> list[dict[str, Any]]:
        with self.db.read() as tx:
            rows = tx.execute(
                "SELECT host, SUM(count) AS queries, COUNT(*) AS days, MIN(day) AS first_day, MAX(day) AS last_day "
                "FROM unlisted_queries WHERE day >= ? GROUP BY host ORDER BY queries DESC, host LIMIT ?",
                (since_day, limit),
            )
        return [{**r, "queries": int(r["queries"]), "days": int(r["days"])} for r in rows]

    def client_reports(self, target_id: str, since_day: str, limit: int = 20) -> list[dict[str, Any]]:
        with self.db.read() as tx:
            rows = tx.execute(
                "SELECT toolset, SUM(count) AS reports, MIN(day) AS first_day, MAX(day) AS last_day "
                "FROM client_reports WHERE target_id=? AND day >= ? GROUP BY toolset ORDER BY reports DESC LIMIT ?",
                (target_id, since_day, limit),
            )
        return [{**r, "reports": int(r["reports"])} for r in rows]

    def prune_client_reports(self, before_day: str) -> int:
        """Reports are a rolling window, not an archive; nothing reads past 30 days."""
        with self.db.transaction() as tx:
            rows = tx.execute("DELETE FROM client_reports WHERE day < ? RETURNING day", (before_day,))
        return len(rows)

    def client_report_total(self, since_day: str) -> int:
        with self.db.read() as tx:
            row = tx.one("SELECT COALESCE(SUM(count), 0) AS n FROM client_reports WHERE day >= ?", (since_day,))
        return int(row["n"])

    # -- runs -----------------------------------------------------------------------

    def last_successful_run(self) -> dict[str, Any] | None:
        """The newest finished run whose stats carry no error — what the crawl interval counts from."""
        with self.db.read() as tx:
            rows = tx.execute("SELECT * FROM runs WHERE kind='crawl' AND finished_at IS NOT NULL ORDER BY id DESC LIMIT 50")
        for row in rows:
            stats = json.loads(row["stats"]) if row.get("stats") else {}
            if not stats.get("error"):
                row["stats"] = stats
                return row
        return None

    def mark_interrupted_runs(self, now: str) -> int:
        """A run with no finish time after a restart was interrupted: say so instead of leaving it open.

        The counts it saved while running stay, and it gets its cycle's totals so far from the
        database, so the last run on the desk is not an empty bar until the cycle ends."""
        with self.db.read() as tx:
            rows = tx.execute("SELECT id, started_at, stats, kind FROM runs WHERE finished_at IS NULL")
        for row in rows:
            stats = json.loads(row["stats"]) if row.get("stats") else {}
            stats["error"] = "interrupted: the process restarted before the crawl finished"
            if row["kind"] == "crawl":
                stats["cycle"] = {**(stats.get("cycle") or {}),
                                  **self.cycle_totals(stats.get("cycle_started_at") or row["started_at"])}
            with self.db.transaction() as tx:
                tx.execute("UPDATE runs SET finished_at=?, stats=? WHERE id=?", (now, dumps(stats), row["id"]))
        return len(rows)

    def resume_point(self, run_id: int, now: str, window_s: int) -> dict[str, Any] | None:
        """The cycle a new run continues, or None.

        A run that ended with an error (a restart marks it "interrupted") leaves its targets
        half-read. Walking back from ``run_id`` through the unbroken chain of such runs (up to the
        last successful one) finds the cycle they belong to: the ``cycle_started_at`` they
        recorded or, for runs written before that was recorded, the earliest start. A run that
        started before a recorded cycle belongs to an older one and ends the chain.

        The chain is continued, however old the cycle, while it was making progress: the last
        target it committed (or its newest run's start) is less than ``window_s`` ago. A cycle
        with many restarts used to be thrown away whole once its START was a day old (2026-10-22:
        42 hours and six restarts in, every server was dialled again); now only a process that
        was down for a whole interval starts afresh. The new run keeps the cycle's start, and
        every target attempted since then is not dialled again.
        """
        if window_s <= 0:
            return None
        with self.db.read() as tx:
            rows = tx.execute("SELECT * FROM runs WHERE kind='crawl' AND id < ? ORDER BY id DESC LIMIT 50", (run_id,))
        parse = lambda ts: datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ")  # noqa: E731
        cycle: str | None = None
        known = False   # the cycle start was recorded by a run, not inferred from older runs' starts
        chain: list[dict[str, Any]] = []
        for row in rows:
            if not row.get("finished_at"):
                break
            stats = json.loads(row["stats"]) if row.get("stats") else {}
            if not stats.get("error"):
                break
            if known and cycle is not None and row["started_at"] < cycle:
                break
            chain.append({"id": row["id"], "stats": stats})
            recorded = stats.get("cycle_started_at")
            start = recorded or row["started_at"]
            cycle = start if cycle is None or start < cycle else cycle
            known = known or bool(recorded)
        if cycle is None:
            return None
        last = max(x for x in (self.last_attempt_since(cycle), rows[0]["started_at"],
                               *(c["stats"].get("progress_at") for c in chain)) if x)
        if (parse(now) - parse(last)).total_seconds() >= window_s:
            return None
        return {"run_id": chain[0]["id"], "cycle_started_at": cycle, "runs": [c["id"] for c in chain],
                "classified": sum(int(c["stats"].get("classified") or 0) for c in chain),
                "labels_issued": sum_counts(c["stats"].get("labels_issued") for c in chain)}

    def last_attempt_since(self, since: str) -> str | None:
        with self.db.read() as tx:
            row = tx.one("SELECT MAX(a.attempted_at) AS at FROM crawl_attempts a JOIN runs r ON r.id=a.run_id "
                         "WHERE r.kind='crawl' AND r.started_at>=?", (since,))
        return row["at"] if row else None

    def cycle_totals(self, since: str) -> dict[str, Any]:
        """What a cycle has done since it started, read from what was committed: the targets attempted
        and the status each was last left in, and the changes recorded. Exact however many restarts
        the cycle had, and whatever code wrote its runs."""
        with self.db.read() as tx:
            rows = tx.execute("SELECT last_status, COUNT(*) AS n FROM targets WHERE id IN "
                              "(SELECT a.target_id FROM crawl_attempts a JOIN runs r ON r.id=a.run_id "
                              "WHERE r.kind='crawl' AND r.started_at>=?) GROUP BY last_status", (since,))
            changes = tx.one("SELECT COUNT(*) AS n FROM changes WHERE observed_at >= ? "
                             "AND (run_id IS NULL OR run_id IN (SELECT id FROM runs WHERE kind='crawl' AND started_at>=?))",
                             (since, since))
        statuses = {str(r["last_status"]): int(r["n"]) for r in rows if r["last_status"]}
        return {"startedAt": since, "attempted": sum(statuses.values()), "statuses": statuses,
                "changes": int(changes["n"] or 0)}

    def save_crawl_plan(self, cycle_started_at: str, plan: dict[str, Any], now: str) -> None:
        """The cycle's package plan (histor.crawler); plans of other cycles are dropped."""
        with self.db.transaction() as tx:
            tx.execute("DELETE FROM crawl_plans WHERE cycle_started_at <> ?", (cycle_started_at,))
            tx.execute("INSERT INTO crawl_plans(cycle_started_at, created_at, body) VALUES(?, ?, ?) "
                       "ON CONFLICT(cycle_started_at) DO UPDATE SET created_at=excluded.created_at, body=excluded.body",
                       (cycle_started_at, now, dumps(plan)))

    def crawl_plan(self, cycle_started_at: str) -> dict[str, Any] | None:
        with self.db.read() as tx:
            row = tx.one("SELECT body FROM crawl_plans WHERE cycle_started_at=?", (cycle_started_at,))
        return json.loads(row["body"]) if row else None

    def attempted_since(self, since: str) -> set[str]:
        """Committed attempts belonging to daily crawl runs started at/after the cycle start."""
        with self.db.read() as tx:
            return {r["id"] for r in tx.execute(
                "SELECT a.target_id AS id FROM crawl_attempts a JOIN runs r ON r.id=a.run_id "
                "WHERE r.kind='crawl' AND r.started_at>=?", (since,))}

    @staticmethod
    def record_attempt(tx: Tx, target_id: str, run_id: int, at: str) -> None:
        # Explicit run membership avoids counting the previous cycle's final observation when
        # its timestamp and the next cycle's start land in the same second. Includes legacy runs.
        tx.execute("INSERT INTO crawl_attempts(target_id, run_id, attempted_at) VALUES(?, ?, ?) "
                   "ON CONFLICT(run_id, target_id) DO UPDATE SET attempted_at=excluded.attempted_at",
                   (target_id, run_id, at))

    def set_run_stats(self, run_id: int, stats: dict[str, Any]) -> None:
        with self.db.transaction() as tx:
            tx.execute("UPDATE runs SET stats=? WHERE id=?", (dumps(stats), run_id))

    def last_run(self, finished_only: bool = True, *, kind: str = "crawl") -> dict[str, Any] | None:
        sql = "SELECT * FROM runs WHERE kind=?"
        if finished_only:
            sql += " AND finished_at IS NOT NULL"
        with self.db.read() as tx:
            row = tx.one(sql + " ORDER BY id DESC LIMIT 1", (kind,))
        if row is None:
            return None
        row["stats"] = json.loads(row["stats"]) if row.get("stats") else {}
        return row

    # -- stats ----------------------------------------------------------------------

    def target_counts(self) -> dict[str, int]:
        with self.db.read() as tx:
            row = tx.one(
                "SELECT COUNT(*) AS listed, "
                "SUM(CASE WHEN current_toolset IS NOT NULL THEN 1 ELSE 0 END) AS pinned, "
                "SUM(CASE WHEN current_subject IS NOT NULL AND current_toolset IS NULL THEN 1 ELSE 0 END) AS undigested, "
                "SUM(CASE WHEN changes > 0 THEN 1 ELSE 0 END) AS ever_changed, "
                "SUM(CASE WHEN block_matches > 0 THEN 1 ELSE 0 END) AS block_tier, "
                "SUM(CASE WHEN COALESCE(block_matches, 0) = 0 AND advise_matches > 0 THEN 1 ELSE 0 END) AS advise_only, "
                "SUM(CASE WHEN record_matches > 0 THEN 1 ELSE 0 END) AS name_records, "
                "SUM(CASE WHEN skip_reason IS NOT NULL THEN 1 ELSE 0 END) AS not_attempted "
                "FROM targets WHERE delisted = 0"
            )
            servers = tx.one("SELECT COUNT(DISTINCT name) AS n FROM targets WHERE delisted = 0")
        out = {k: int(v or 0) for k, v in row.items()}
        out["servers"] = int(servers["n"] or 0)
        return out
