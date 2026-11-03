"""Database backend abstraction — SQLite and PostgreSQL with dialect translation.

Provides a unified `DBBackend` protocol with two implementations:
  - `SQLiteBackend` — zero-dependency, single-file database (default)
  - `PostgresBackend` — psycopg_pool-backed, connection pooling, JSONB

When DATABASE_URL is not set, SQLite is used (backward-compatible default).
When DATABASE_URL is set (e.g., postgresql://user:pass@host:5432/db), PostgreSQL is used.

Factory:
    create_backend(database_url="") -> DBBackend

Path resolution (SQLite): an explicit ``db_path`` argument wins over the ambient
``AIMARKET_DB_PATH`` env var — see create_backend for why the reverse was a bug.
"""

from __future__ import annotations

import contextlib
import logging
import os
import re
import sqlite3
import asyncio
import contextvars
import threading
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)

# The hub index database. Also the "caller expressed no preference" marker in
# create_backend, which is the only place AIMARKET_DB_PATH may fill in.
DEFAULT_DB_PATH = "data/hub.db"

#: How long a connection waits for another one to release the write lock before giving up.
#: SQLite's own default is 0 — fail instantly — which is never what a service wants: writes
#: here take milliseconds and the alternative to waiting is a 500 for the caller. Both
#: connections to a given database must use the same value, or the difference shows up as
#: "sometimes it works", depending which one happened to be serving.
_SQLITE_BUSY_TIMEOUT_S = float(os.getenv("AIMARKET_SQLITE_BUSY_TIMEOUT_S", "10") or 10)


# ── Protocol ────────────────────────────────────────────────────────


@runtime_checkable
class DBBackend(Protocol):
    """Protocol for database backends.

    Implementations: SQLiteBackend, PostgresBackend.
    """

    @property
    def backend_type(self) -> str: ...

    def execute(self, sql: str, params: tuple = ()) -> Any: ...

    def executemany(self, sql: str, params_list: list[tuple]) -> Any: ...

    def executescript(self, sql: str) -> Any: ...

    def fetchone(self) -> dict | None: ...

    def fetchall(self) -> list[dict]: ...

    def commit(self) -> None: ...

    def close(self) -> None: ...

    def get_connection(self) -> Any: ...

    @property
    def rowcount(self) -> int: ...


# ── SQL Dialect Translation ─────────────────────────────────────────

# Non-greedy VALUES (.*?) breaks on nested parens (e.g. datetime('now') / NOW()).
# Match the VALUES (...) group with balanced parentheses instead.
_RE_INSERT_OR_REPLACE = re.compile(
    r"INSERT\s+OR\s+REPLACE\s+INTO\s+(\w+)\s*\((.*?)\)\s*VALUES\s*(\((?:[^()]|\([^()]*\))*\))",
    re.IGNORECASE | re.DOTALL,
)
_RE_DATETIME_NOW = re.compile(r"datetime\('now'\)", re.IGNORECASE)
_RE_PRAGMA = re.compile(r"PRAGMA\s+\w+.*?;", re.IGNORECASE)
_RE_AUTOINCREMENT = re.compile(r"AUTOINCREMENT", re.IGNORECASE)
_RE_INTEGER_PK = re.compile(r"INTEGER\s+PRIMARY\s+KEY", re.IGNORECASE)



def _strip_sql_comments(sql: str) -> str:
    """Remove `--` line comments, leaving anything inside a string literal alone.

    Only what a naive `split(";")` needs: a comment can carry a semicolon, a string literal
    can carry `--`, and confusing either for the other turns valid DDL into a syntax error
    at migration time.
    """
    out: list[str] = []
    for line in sql.splitlines():
        in_string = False
        cut = None
        i = 0
        while i < len(line):
            ch = line[i]
            if ch == "'":
                # '' inside a string is an escaped quote, not the end of one.
                if in_string and i + 1 < len(line) and line[i + 1] == "'":
                    i += 2
                    continue
                in_string = not in_string
            elif not in_string and ch == "-" and line.startswith("--", i):
                cut = i
                break
            i += 1
        out.append(line if cut is None else line[:cut])
    return "\n".join(out)


def sqlite_to_pg(sql: str, table_name_for_upsert: str = "", unique_cols: list[str] | None = None) -> str:
    """Translate SQLite SQL to PostgreSQL SQL.

    Handles:
      - INSERT OR REPLACE → INSERT ... ON CONFLICT ... DO UPDATE
      - datetime('now') → NOW()
      - PRAGMA statements → no-op (PostgreSQL has its own WAL/FK)
      - AUTOINCREMENT → removed (SERIAL handles it)
      - INTEGER PRIMARY KEY → SERIAL PRIMARY KEY
      - ? placeholders → %s
    """
    result = sql

    # Remove PRAGMA lines (WAL, foreign_keys — PG handles these natively)
    result = _RE_PRAGMA.sub("-- pragma removed for PostgreSQL\n", result)

    # datetime('now') → NOW()
    result = _RE_DATETIME_NOW.sub("NOW()", result)

    # INSERT OR REPLACE → INSERT ... ON CONFLICT DO UPDATE
    # This is a best-effort translation — the caller should provide
    # table_name_for_upsert + unique_cols for precision.
    # Default unique key for hub tables that use INSERT OR REPLACE without
    # an explicit id (capabilities) is the business UNIQUE, not SERIAL id.
    _DEFAULT_CONFLICT: dict[str, list[str]] = {
        "capabilities": ["capability_id", "product_id", "source_hub"],
        "peers": ["url"],
        "peer_assays": ["peer_url"],
        # Its PRIMARY KEY, from migration 023. Missing here, the fallback below emitted
        # `ON CONFLICT (id)` for a table that has no `id`, so every preview write raised
        # on Postgres — and `_preview_pending_manifest` swallows exceptions and returns 0.
        # Result: "capabilities: 0" for every knocking hub on every Postgres deployment,
        # with the reason only in a suppressed INFO line (hub.attestedmemory.net,
        # 2026-09-08). The fallback is the trap: it produces valid-looking SQL for a key
        # that may not exist, so a table added without an entry here fails at runtime.
        "peer_preview_capabilities": ["peer_url", "capability_id", "product_id"],
        # Migration 033's PRIMARY KEY. Same trap as the line above: without it the
        # fallback emits `ON CONFLICT (id)` for a table that has no `id`, so minting
        # the invoice behind a 402 raises on every Postgres hub — and a 402 that
        # cannot mint its nonce is a sale that cannot be bound to a payment.
        "settle_invoices": ["nonce"],
    }

    def _translate_upsert(m: re.Match) -> str:
        table = m.group(1)
        cols = m.group(2)
        # group(3) is the full "(...)" VALUES list including outer parens
        vals = m.group(3)
        actual_table = table_name_for_upsert or table
        conflict_cols = unique_cols or _DEFAULT_CONFLICT.get(actual_table, ["id"])
        conflict_clause = ", ".join(conflict_cols)
        set_clause = ", ".join(
            f"{c.strip()} = EXCLUDED.{c.strip()}"
            for c in cols.split(",")
            if c.strip() not in conflict_cols
        )
        return (
            f"INSERT INTO {actual_table} ({cols}) VALUES {vals}\n"
            f"ON CONFLICT ({conflict_clause}) DO UPDATE SET {set_clause}"
        )

    result = _RE_INSERT_OR_REPLACE.sub(_translate_upsert, result)

    # INTEGER PRIMARY KEY → SERIAL PRIMARY KEY (for table creation)
    result = _RE_INTEGER_PK.sub("SERIAL PRIMARY KEY", result)
    result = _RE_AUTOINCREMENT.sub("", result)

    # SQLite REAL → PostgreSQL DOUBLE PRECISION
    result = re.sub(r"\bREAL\b", "DOUBLE PRECISION", result, flags=re.IGNORECASE)

    # TEXT without size → TEXT (no change needed, PG supports TEXT)
    # But SQLite TEXT defaults — keep as-is

    # Replace SQLite ? placeholders with PostgreSQL %s.
    # Literal % in SQL (e.g. LIKE '{%') must become %% for psycopg, otherwise
    # "only '%s', '%b', '%t' are allowed as placeholders, got '%'".
    result = _replace_placeholders(result)

    return result


def _replace_placeholders(sql: str) -> str:
    """Escape literal % for psycopg, then replace ? with %s (not inside strings)."""
    # Double every % first so LIKE patterns / printf fragments stay literals.
    # SQLite-dialect SQL has no psycopg placeholders yet, so this is safe.
    sql = sql.replace("%", "%%")
    in_string = False
    string_char = ""
    out: list[str] = []
    i = 0
    while i < len(sql):
        c = sql[i]
        if in_string:
            out.append(c)
            if c == string_char and (i == 0 or sql[i - 1] != "\\"):
                in_string = False
        else:
            if c in ("'", '"'):
                in_string = True
                string_char = c
                out.append(c)
            elif c == "?":
                out.append("%s")
            else:
                out.append(c)
        i += 1
    return "".join(out)


# ── SQLite Backend ──────────────────────────────────────────────────


class _LockedSQLiteCursor:
    """Keep cursor stepping under the shared connection's lock as well as execute.

    sqlite3 releases the GIL while fetching. An unguarded fetch can overlap a
    different thread's execute/commit on this connection and lose a result row.
    """

    def __init__(self, cursor: Any, lock: Any):
        self._cursor = cursor
        self._lock = lock

    def fetchone(self) -> Any:
        with self._lock:
            return self._cursor.fetchone()

    def fetchall(self) -> list:
        with self._lock:
            return self._cursor.fetchall()

    def fetchmany(self, size: int | None = None) -> list:
        with self._lock:
            return self._cursor.fetchmany() if size is None else self._cursor.fetchmany(size)

    def __iter__(self):
        return self

    def __next__(self):
        with self._lock:
            return next(self._cursor)

    def __getattr__(self, name: str) -> Any:
        with self._lock:
            return getattr(self._cursor, name)


class SQLiteBackend:
    """SQLite backend — zero-dependency, single-file database.

    Follows the existing patterns: WAL mode, foreign_keys ON,
    sqlite3.Row row factory.
    """

    def __init__(self, db_path: str | Path = "data/hub.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        # `timeout` IS sqlite's busy timeout, and leaving it unset means ZERO: the very
        # first moment another connection holds the write lock, this one raises
        # "database is locked" instead of waiting out a write that takes milliseconds.
        #
        # This connection serves every request; `get_connection()` below opens a second one
        # to the same file and already asks for 10s. So the patient connection was the
        # occasional one and the impatient connection was the hot path — exactly backwards.
        # Measured 2026-09-05 on independentai.network/hub: federated invokes returned a bare
        # 500 to the caller, eight times out of eight, from `record_invocation` — the work had
        # already been fetched from the peer and was thrown away over a metrics row. A restart
        # cleared it, which is the signature of contention rather than corruption.
        self._conn = sqlite3.connect(
            str(self.db_path), check_same_thread=False, timeout=_SQLITE_BUSY_TIMEOUT_S
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        # One connection is shared across request threads and the crawler.
        # check_same_thread=False alone is not enough: concurrent execute()
        # on the same sqlite3.Connection raises InterfaceError, which the
        # concurrency stake tests hit as empty credited/rejected lists.
        self._lock = threading.RLock()
        self._last_cursor: Any = None
        logger.info("SQLite backend initialized: %s", self.db_path)

    @property
    def backend_type(self) -> str:
        return "sqlite"

    def cursor(self) -> Any:
        """Return a raw sqlite3.Cursor for backward compat with legacy code."""
        return self._conn.cursor()

    def execute(self, sql: str, params: tuple = ()) -> Any:
        with self._lock:
            try:
                self._last_cursor = _LockedSQLiteCursor(self._conn.execute(sql, params), self._lock)
            except sqlite3.Error:
                self._abandon_failed_transaction()
                raise
            return self._last_cursor

    def executemany(self, sql: str, seq: list) -> Any:
        with self._lock:
            try:
                self._last_cursor = _LockedSQLiteCursor(self._conn.executemany(sql, seq), self._lock)
            except sqlite3.Error:
                self._abandon_failed_transaction()
                raise
            return self._last_cursor

    def _abandon_failed_transaction(self) -> None:
        """Roll back the transaction a failed statement left open on the shared connection.

        Python's sqlite3 issues its implicit BEGIN before a write's first step. When that
        step fails — "database is locked" once the crawler, on ITS own connection, holds
        the write lock past the busy timeout — the caller raises and never reaches
        commit(), and the connection every request shares stays inside that transaction
        for the life of the process. Every later read sees the snapshot from the moment
        it failed, and every later write fails on that stale snapshot, so nothing ever
        commits it. hub.modelmarket.dev served an EMPTY catalogue for 18 hours that way
        (2026-09-22) while the crawler kept its own file current, with the WAL grown to
        5.4 GB behind the pinned reader; independentai.network/hub's eight-for-eight 500s
        on 2026-09-05 that "a restart cleared" were the same trap.

        Rolling back discards only the failed statement's transaction. A caller that
        wrote earlier in it without committing loses those writes too — which is what it
        would get from a failed transaction anyway, and far better than a connection
        that can never write again.
        """
        if self._conn.in_transaction:
            try:
                self._conn.rollback()
            except sqlite3.Error as exc:  # pragma: no cover - nothing left to recover
                logger.error("could not roll back a failed SQLite transaction: %s", exc)

    def executescript(self, sql: str) -> Any:
        with self._lock:
            self._last_cursor = self._conn.executescript(sql)
            return self._last_cursor

    def fetchone(self) -> dict | None:
        with self._lock:
            if self._last_cursor:
                row = self._last_cursor.fetchone()
                return dict(row) if row else None
            return None

    def fetchall(self) -> list[dict]:
        with self._lock:
            if self._last_cursor:
                return [dict(r) for r in self._last_cursor.fetchall()]
            return []

    def commit(self) -> None:
        with self._lock:
            self._conn.commit()

    def rollback(self) -> None:
        with self._lock:
            self._conn.rollback()

    def close(self) -> None:
        with self._lock:
            self._conn.close()
        logger.info("SQLite backend closed: %s", self.db_path)

    def get_connection(self) -> Any:
        """Return a context-managed connection that auto-closes on exit."""
        from contextlib import closing
        conn = sqlite3.connect(str(self.db_path), timeout=_SQLITE_BUSY_TIMEOUT_S)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return closing(conn)

    @property
    def rowcount(self) -> int:
        with self._lock:
            return self._last_cursor.rowcount if self._last_cursor else 0


# ── PostgreSQL Backend ──────────────────────────────────────────────


# Leading whitespace / line comments / block comments / opening parens.
_RE_LEADING_NOISE = re.compile(r"^(?:\s+|--[^\n]*\n?|/\*.*?\*/|\()+", re.DOTALL)
# Anything that can write, lock, or advance state. Deliberately broad: a false "not
# read-only" only costs us holding the pooled connection until commit/rollback (the old
# behaviour), while a false "read-only" would release a connection out from under an
# uncommitted write or a row lock. Includes RETURNING (single_winner_statement builds
# `INSERT … RETURNING`, and a bare `SELECT … RETURNING` does not exist) and the
# `SELECT … INTO` / `FOR UPDATE` forms that look like reads but are not.
_RE_WRITE_KEYWORD = re.compile(
    r"\b(?:INSERT|UPDATE|DELETE|MERGE|CREATE|ALTER|DROP|TRUNCATE|GRANT|REVOKE|COPY|CALL"
    r"|VACUUM|ANALYZE|REINDEX|SET|RESET|BEGIN|COMMIT|ROLLBACK|SAVEPOINT|LOCK|INTO"
    r"|RETURNING|NEXTVAL|SETVAL|FOR\s+UPDATE|FOR\s+NO\s+KEY\s+UPDATE|FOR\s+SHARE"
    r"|FOR\s+KEY\s+SHARE|pg_advisory_lock|pg_advisory_xact_lock)\b",
    re.IGNORECASE,
)
_RE_LEADING_SELECT = re.compile(r"SELECT\b", re.IGNORECASE)


def is_read_only_sql(sql: str) -> bool:
    """True only when ``sql`` is certainly a plain read.

    Used to decide whether a pooled PostgreSQL connection can be returned as soon as the
    rows are materialised. Fail-safe direction: unsure ⇒ False.
    """
    stripped = _RE_LEADING_NOISE.sub("", sql)
    if not _RE_LEADING_SELECT.match(stripped):
        return False
    return _RE_WRITE_KEYWORD.search(stripped) is None


class _MaterialisedCursor:
    """The rows of a completed read, detached from the connection that produced them.

    Lets `PostgresBackend.execute` return a pooled connection immediately after a read
    while still honouring the `fetchone()`/`fetchall()`/`rowcount` contract the rest of
    the hub calls afterwards (often much later, or never — which is why holding the
    connection until the fetch was a leak, not a deferral).
    """

    __slots__ = ("_rows", "_index", "rowcount", "description")

    def __init__(self, rows: list, rowcount: int, description: Any = None):
        self._rows = rows
        self._index = 0
        self.rowcount = rowcount
        self.description = description

    @classmethod
    def from_cursor(cls, cursor: Any) -> _MaterialisedCursor:
        rows = list(cursor.fetchall())
        reported = getattr(cursor, "rowcount", None)
        try:
            rowcount = int(reported)
        except (TypeError, ValueError):
            rowcount = len(rows)
        if rowcount < 0:
            rowcount = len(rows)
        return cls(rows, rowcount, getattr(cursor, "description", None))

    def fetchone(self) -> Any:
        if self._index >= len(self._rows):
            return None
        row = self._rows[self._index]
        self._index += 1
        return row

    def fetchmany(self, size: int = 1) -> list:
        rows = self._rows[self._index:self._index + max(0, int(size))]
        self._index += len(rows)
        return rows

    def fetchall(self) -> list:
        rows = self._rows[self._index:]
        self._index = len(self._rows)
        return rows

    def __iter__(self) -> Any:
        while True:
            row = self.fetchone()
            if row is None:
                return
            yield row


class _TranslatingConnection:
    """psycopg connection that runs every statement through :func:`sqlite_to_pg`.

    Deliberately thin: it forwards everything it does not need to touch, so a caller
    cannot tell it apart from the connection it wraps except that its SQL now arrives in
    the right dialect. Rows come back as :class:`_PgRow` (set as the pool's row factory),
    which is what makes ``row[0]`` and ``row["name"]`` both work like sqlite3.Row.
    """

    __slots__ = ("_raw",)

    def __init__(self, raw: Any):
        self._raw = raw

    def execute(self, sql: str, params: Any = ()) -> Any:
        return self._raw.execute(sqlite_to_pg(sql), params)

    def executemany(self, sql: str, seq: Any) -> Any:
        return self._raw.cursor().executemany(sqlite_to_pg(sql), seq)

    def executescript(self, sql: str) -> Any:
        return self._raw.execute(sqlite_to_pg(sql))

    def cursor(self, *a: Any, **kw: Any) -> Any:
        return self._raw.cursor(*a, **kw)

    def commit(self) -> None:
        self._raw.commit()

    def rollback(self) -> None:
        self._raw.rollback()

    def __getattr__(self, name: str) -> Any:
        # Anything else (info, closed, transaction(), …) belongs to psycopg.
        return getattr(self._raw, name)


class _PgRow:
    """A PostgreSQL row that behaves like ``sqlite3.Row``.

    The whole point of this module is to hide the dialect difference between the two
    backends, and a `dict_row` factory leaks one of the biggest: `sqlite3.Row` supports
    BOTH ``row["name"]`` and ``row[0]``, a dict supports only the first. 23 call sites in
    the hub read a scalar as ``fetchone()[0]`` — `SELECT COUNT(*)`, `SUM(...)`, and other
    aggregates that have no natural column name — and every one of them raised
    ``KeyError: 0`` the moment a deployment set DATABASE_URL. Fixing them one by one would
    have meant inventing names for aggregates (psycopg calls them ``count``/``sum``, which
    collide when a query has two) and would leave the next positional read to break again.

    Matches sqlite3.Row's contract deliberately, including the parts that look odd:
      * iteration yields VALUES, not keys — ``for a, b, c in row`` is used in the hub
      * ``keys()`` returns column names, which is also what makes ``dict(row)`` work
        (dict() prefers the mapping protocol when an object exposes ``keys``)
    """

    __slots__ = ("_names", "_values", "_index")

    def __init__(self, names: tuple[str, ...], values: tuple[Any, ...]):
        self._names = names
        self._values = values
        self._index = {name: i for i, name in enumerate(names)}

    def __getitem__(self, key: Any) -> Any:
        if isinstance(key, str):
            try:
                return self._values[self._index[key]]
            except KeyError:
                raise KeyError(key) from None
        return self._values[key]

    def keys(self) -> list[str]:
        return list(self._names)

    def get(self, key: str, default: Any = None) -> Any:
        idx = self._index.get(key)
        return default if idx is None else self._values[idx]

    def __iter__(self):
        # sqlite3.Row iterates over values; `dict(row)` still works via keys().
        return iter(self._values)

    def __len__(self) -> int:
        return len(self._values)

    def __contains__(self, key: Any) -> bool:
        return key in self._index if isinstance(key, str) else key in self._values

    def __repr__(self) -> str:
        return f"_PgRow({dict(zip(self._names, self._values, strict=False))!r})"


def _sqlite_like_row(cursor: Any) -> Any:
    """psycopg row factory producing :class:`_PgRow`."""
    names = tuple(d.name for d in (cursor.description or ()))

    def make(values: tuple[Any, ...]) -> _PgRow:
        return _PgRow(names, tuple(values))

    return make


class _PgSession:
    """One checked-out connection, owned by exactly one execution context.

    Held in a ``ContextVar`` rather than on the backend, because the backend is a
    process-wide singleton and its callers are not. ``asyncio.create_task`` copies the
    context, so a child task would inherit the parent's session value — hence ``owner``:
    a session whose owner is not the caller is not the caller's to use or to hand back.
    """

    __slots__ = ("owner", "backend", "conn", "dirty")

    def __init__(self, owner: tuple, backend: Any, conn: Any) -> None:
        self.owner = owner
        self.backend = backend
        self.conn = conn
        # True once this connection has run a statement that needs commit/rollback. A
        # read-only statement on a clean connection is finished the moment its rows are
        # materialised, so the connection goes straight back to the pool.
        self.dirty = False


_PG_SESSION: contextvars.ContextVar["_PgSession | None"] = contextvars.ContextVar(
    "aimarket_pg_session", default=None,
)

# The rows of the last statement, per context. Deliberately NOT part of the session: a
# read materialises its rows and hands the connection straight back, and callers do
# `execute(...)` then `fetchall()` — often much later. Clearing this together with the
# session made every read return None.
_PG_RESULT: contextvars.ContextVar["tuple | None"] = contextvars.ContextVar(
    "aimarket_pg_result", default=None,
)


def _pg_in_transaction(conn: Any) -> bool:
    """Is this connection inside a transaction (or a failed one)?

    psycopg opens a transaction for ANY statement with autocommit off, SELECT included, so
    a read hands its connection back to the pool INTRANS; psycopg_pool then rolls it back
    and logs a warning per read. On a hub whose front end polls that was seventeen a
    second — 14MB of log in five minutes, and a log nobody can read is one nobody reads.
    Ending the transaction here instead makes the pool's own check a no-op.

    Reads the libpq status rather than guessing, and returns False when the attribute is
    absent so a connection object that does not expose it is simply left alone.
    """
    status = getattr(getattr(conn, "info", None), "transaction_status", None)
    if status is None:
        return False
    try:
        return int(status) != 0  # psycopg TransactionStatus.IDLE == 0
    except (TypeError, ValueError):  # pragma: no cover - defensive
        return False


def _pg_owner() -> tuple:
    """Identity of the current execution context: (thread, asyncio task).

    Both halves are needed. FastAPI runs ``def`` handlers in a worker thread and ``async
    def`` handlers as tasks on one thread, and this backend serves a hub that does both,
    plus a background crawler task.
    """
    task_id = 0
    try:
        task = asyncio.current_task()
    except RuntimeError:  # no running loop — a plain thread
        task = None
    if task is not None:
        task_id = id(task)
    return (threading.get_ident(), task_id)


class PostgresBackend:
    """PostgreSQL backend — connection pooling via psycopg_pool.

    Uses psycopg 3 with connection pool (min=2, max=8).
    Row results are returned as dicts (RealDictRow-compatible).

    DATABASE_URL is validated to reject dangerous options parameters
    that could enable SQL injection or path manipulation.
    """

    def __init__(self, database_url: str):
        from psycopg_pool import ConnectionPool

        # Reject connection strings with dangerous libpq options
        if "options=" in database_url.lower():
            # Only allow specific known-safe options
            if not re.search(r"options=-c\s*application_name=", database_url):
                raise ValueError(
                    "DATABASE_URL with custom 'options=' is rejected for security. "
                    "Use AIMARKET_PG_OPTIONS env var for safe option allowlisting."
                )
        self.database_url = database_url
        masked = re.sub(r":([^@]+)@", ":****@", database_url)
        logger.info("PostgreSQL backend initialized: %s", masked)

        self._pool = ConnectionPool(
            database_url,
            min_size=2,
            max_size=8,
            kwargs={"row_factory": _sqlite_like_row},
        )
        # Test connection on startup
        with self._pool.connection() as conn:
            conn.execute("SELECT 1")
        logger.info("PostgreSQL connection pool ready (min=2, max=8)")

    @property
    def backend_type(self) -> str:
        return "postgresql"

    # ── Pool bookkeeping ────────────────────────────────────────────
    #
    # Every `getconn()` in this class MUST be matched by exactly one `putconn()`, on the
    # success path, the empty-result path and the exception path alike. It was not:
    # `execute()` checked a connection out and only `commit()`/`rollback()` ever handed one
    # back, so a read-only query — which by definition never commits — consumed a pool slot
    # for the life of the process. Eight SELECTs exhausted the pool and the ninth caller
    # blocked on `getconn()` forever, i.e. a read-heavy hub hangs.
    #
    # The fix for that kept ONE connection on the backend and reused it. The backend is a
    # process-wide singleton and its callers are not, so that traded a leak for sharing:
    # two callers in flight at once got the SAME connection, and whichever finished first
    # handed it back to the pool while the other was still using it — its transaction
    # committed or rolled back under it, its `_last_cursor` overwritten, so `fetchall()`
    # could return another caller's rows. Reachable on one thread, no threads required: the
    # crawler holds a dirty connection across an `await`, and the event loop runs a request
    # handler in the gap.
    #
    # So the checked-out connection now lives in a ContextVar keyed by (thread, task): one
    # per request, per background task, per worker thread. Within one context `_acquire`
    # still reuses the held connection, which is what keeps a multi-statement write in a
    # single transaction, and `_release` returns it — from commit, rollback, close, an
    # exception, or the end of a read.

    def _session(self, *, create: bool) -> "_PgSession | None":
        """This context's session, or None. ``create`` checks a connection out."""
        session = _PG_SESSION.get()
        # A session inherited from a parent task (ContextVar values are copied into new
        # tasks) belongs to the parent. Using it would share a connection; handing it back
        # would pull it out from under the parent.
        if session is not None and (
            session.backend is not self or session.owner != _pg_owner()
        ):
            session = None
        if session is None and create:
            session = _PgSession(_pg_owner(), self, self._pool.getconn())
            _PG_SESSION.set(session)
        return session

    def _set_result(self, cursor: Any) -> Any:
        _PG_RESULT.set((_pg_owner(), self, cursor))
        return cursor

    def _result(self) -> Any:
        held = _PG_RESULT.get()
        if held is None:
            return None
        owner, backend, cursor = held
        # Owner-tagged like the session: a child task inherits the value, and returning a
        # parent's rows from its `fetchall()` is the same class of bug as sharing its
        # connection.
        if backend is not self or owner != _pg_owner():
            return None
        return cursor

    def _acquire(self) -> Any:
        session = self._session(create=True)
        assert session is not None  # create=True always returns one
        return session.conn

    def _release(self) -> None:
        session = self._session(create=False)
        if session is None:
            return
        _PG_SESSION.set(None)
        conn = session.conn
        session.dirty = False
        # End a read's transaction ourselves; see _pg_in_transaction. Suppressed because a
        # connection that cannot be rolled back must still go back to the pool — the pool
        # discards a broken one, and losing the slot instead is how the hang started.
        if _pg_in_transaction(conn):
            with contextlib.suppress(Exception):
                conn.rollback()
        self._pool.putconn(conn)

    def _abandon(self, conn: Any) -> None:
        """Return a connection after a failed statement, rolling its transaction back.

        Without the rollback the connection goes back to the pool inside a failed
        transaction, and the next borrower's first statement dies with
        `InFailedSqlTransaction`. The rollback itself must not be able to swallow the
        original exception, hence the suppress.
        """
        with contextlib.suppress(Exception):
            conn.rollback()
        session = self._session(create=False)
        if session is not None and session.conn is conn:
            self._release()
        else:  # pragma: no cover - defensive: _acquire always stores what it hands out
            self._pool.putconn(conn)

    def cursor(self) -> Any:
        """Return a psycopg cursor for backward compat with legacy code.

        Marks the connection dirty: this hands out a raw cursor, so we cannot see what is
        run on it and must assume it needs an explicit commit/rollback to be released.
        """
        conn = self._acquire()
        self._session(create=False).dirty = True  # type: ignore[union-attr]
        return conn.cursor()

    def execute(self, sql: str, params: tuple = ()) -> Any:
        # Translate SQL dialect
        pg_sql = sqlite_to_pg(sql)
        held = self._session(create=False)
        read_only = not (held is not None and held.dirty) and is_read_only_sql(pg_sql)
        conn = self._acquire()
        session = self._session(create=False)
        assert session is not None
        try:
            cursor = conn.execute(pg_sql, params)
        except Exception:
            self._abandon(conn)
            raise
        if read_only:
            # Materialise now and give the slot back. Deferring the fetch to
            # fetchone()/fetchall() (which may never be called at all) is precisely how the
            # connection leaked; an empty result set leaks the same as a full one.
            try:
                self._set_result(_MaterialisedCursor.from_cursor(cursor))
            except Exception:
                self._abandon(conn)
                raise
            self._release()
            return self._result()
        session.dirty = True
        return self._set_result(cursor)

    def executemany(self, sql: str, seq: list) -> Any:
        pg_sql = sqlite_to_pg(sql)
        conn = self._acquire()
        session = self._session(create=False)
        assert session is not None
        try:
            cursor = conn.executemany(pg_sql, seq)
        except Exception:
            self._abandon(conn)
            raise
        session.dirty = True
        return self._set_result(cursor)

    def executescript(self, sql: str) -> Any:
        conn = self._acquire()
        try:
            with conn.transaction():
                # Comments come out BEFORE the split. Splitting on ";" first meant a prose
                # semicolon inside a `--` comment cut the comment in half and handed the
                # tail to Postgres as a statement — a syntax error at migration time, which
                # is a permanent crash loop because the version row is never written. It
                # only skipped a chunk that STARTED with `--`, so the DDL after the comment
                # went down with it. Migration 028 tripped exactly this.
                pg_sql = _strip_sql_comments(sqlite_to_pg(sql))
                for stmt in pg_sql.split(";"):
                    stmt = stmt.strip()
                    if stmt:
                        conn.execute(stmt)
        except Exception:
            self._abandon(conn)
            raise
        # conn.transaction() already committed the block, so nothing is pending: release
        # instead of waiting for a commit() the caller has no reason to make.
        _PG_RESULT.set(None)
        self._release()
        return None

    def fetchone(self) -> dict | None:
        cursor = self._result()
        if cursor:
            row = cursor.fetchone()
            return dict(row) if row else None
        return None

    def fetchall(self) -> list[dict]:
        cursor = self._result()
        if cursor:
            return [dict(r) for r in cursor.fetchall()]
        return []

    def commit(self) -> None:
        session = self._session(create=False)
        if session is None:
            return
        try:
            session.conn.commit()
        finally:
            self._release()

    def rollback(self) -> None:
        session = self._session(create=False)
        if session is None:
            return
        try:
            session.conn.rollback()
        finally:
            self._release()

    def close(self) -> None:
        # Hand the held connection back BEFORE closing the pool: a pool closed with a
        # connection still checked out leaks the underlying socket.
        with contextlib.suppress(Exception):
            self._release()
        self._pool.close()
        logger.info("PostgreSQL backend closed")

    @contextlib.contextmanager
    def get_connection(self) -> Any:
        """A pooled connection that TRANSLATES the SQL it is given.

        Handing out ``self._pool.connection()`` directly was the single biggest
        PostgreSQL defect in the hub: almost every caller works through
        ``with backend.get_connection() as conn: conn.execute(sql, params)`` — the channel
        ledger, the index, the reaper, the obligations — and a raw psycopg connection
        applies NO dialect translation. So on any deployment with DATABASE_URL set, the
        entire runtime query path ran SQLite SQL against PostgreSQL: ``?`` placeholders
        were never rewritten ("the query has 0 placeholders but N parameters were passed"),
        and ``datetime('now')`` was never rewritten either. The translator itself
        (sqlite_to_pg) was fine — it was simply bypassed, and only the DDL path
        (executescript) ever reached it, which is why migrations applied cleanly while
        every subsequent statement failed.
        """
        with self._pool.connection() as raw:
            yield _TranslatingConnection(raw)

    @property
    def rowcount(self) -> int:
        cursor = self._result()
        return cursor.rowcount if cursor else 0


# ── RETURNING on the shared connection ──────────────────────────────


def returning(backend: Any, sql: str, params: tuple = (), *, commit: bool = False) -> list[Any]:
    """Run a write with a RETURNING clause on the SHARED connection and read every row.

    The rows are read under the backend's own lock, in the same critical section as the
    statement. On SQLite a write with RETURNING stays "in progress" until its cursor is
    exhausted, and while it is, ANY commit on the connection — another thread's included —
    fails with "cannot commit transaction - SQL statements in progress". Reading the rows
    after `execute()` returned leaves exactly that window open between two threads; reading
    them inside the lock closes it. A conditional `UPDATE ... RETURNING` is how the credits
    ledger, mandates and subcontracting decide single winners, so this is on their hot path.

    PostgreSQL has no such state and no shared lock; the rows are simply fetched.

    ``commit=True`` commits in the same critical section. A claim and its commit taken as
    two acquisitions leave a gap in which another thread's failing statement can roll the
    shared transaction back — undoing a counter move the caller already counts as made.
    """
    lock = getattr(backend, "_lock", None)
    with (lock if lock is not None else contextlib.nullcontext()):
        cursor = backend.execute(sql, params)
        rows = list(cursor.fetchall()) if cursor is not None else []
        if commit:
            backend.commit()
        return rows


def returning_one(backend: Any, sql: str, params: tuple = (), *, commit: bool = False) -> Any:
    rows = returning(backend, sql, params, commit=commit)
    return rows[0] if rows else None


@contextlib.contextmanager
def atomic(backend: Any):
    """Several statements as ONE transaction on the shared connection.

    On SQLite every request thread shares one connection, and a transaction is only as
    private as the lock around it: another thread's failing statement rolls back what is
    pending on the connection, and a write taken as three separate acquisitions can have
    its first two undone while the third commits — a credit recorded in the ledger whose
    balance never moved. The backend's lock is held from the first statement to the
    commit, and anything raised rolls the whole block back. PostgreSQL sessions are per
    thread; there the block simply commits or rolls back as one.
    """
    lock = getattr(backend, "_lock", None)
    with (lock if lock is not None else contextlib.nullcontext()):
        try:
            yield
        except BaseException:
            with contextlib.suppress(Exception):
                backend.rollback()
            raise
        backend.commit()


# ── Single-winner claims ────────────────────────────────────────────

# Turns the INSERT into a conflict-tolerant statement whose OWN result says whether it
# inserted. Both clauses have identical syntax in SQLite and PostgreSQL. DO NOTHING covers
# UNIQUE/PRIMARY KEY conflicts only — a NOT NULL / CHECK / FK failure still raises, which
# is what we want (those are faults, not lost races).
_ON_CONFLICT_DO_NOTHING = "ON CONFLICT DO NOTHING"
_RETURNING_CLAIM = "RETURNING 1"
_RE_ON_CONFLICT = re.compile(r"\bON\s+CONFLICT\b", re.IGNORECASE)
_RE_CONFLICT_ACTION = re.compile(r"\bDO\s+(NOTHING|UPDATE)\b", re.IGNORECASE)
# RETURNING landed in SQLite 3.35 (2021). Without it there is no per-statement way to tell
# the winner from the loser — see claim_unique.
_SQLITE_RETURNING_MIN_VERSION = (3, 35, 0)


def single_winner_statement(sql: str) -> str:
    """``sql`` (a plain INSERT) rewritten so the statement itself reports who inserted.

    Both clauses are appended here rather than by the caller so no claim site can forget
    one, and each is load-bearing:

    * **ON CONFLICT DO NOTHING** — the loser is a no-op, not an exception. Catching the
      IntegrityError instead is not safe on the shared SQLite connection the hub hands
      every worker thread: rolling back the failed statement reverts a concurrent
      winner's uncommitted row (measured: 3 of 8 racing threads "won" the same key), and
      leaving the transaction open strands the write lock until other connections time
      out.
    * **RETURNING** — the winner gets a row, the loser gets none. Row COUNTS cannot
      decide this: ``cursor.rowcount`` is filled from the connection-global
      ``sqlite3_changes()`` after the step releases the GIL, so a co-resident thread's
      statement overwrites it and every racer reads 0 (measured the same way).
      ``backend.rowcount`` is worse still — a shared attribute.

    A conflict clause the caller wrote itself must be DO NOTHING. ``DO UPDATE`` would make
    RETURNING yield a row for the LOSER too — every racer would read "I won" — and the
    substring test alone would happily append a second, contradictory clause. Refuse
    instead: a claim whose verdict cannot be trusted must not be built.
    """
    statement = sql.rstrip().rstrip(";")
    conflict = _RE_ON_CONFLICT.search(statement)
    if conflict is None:
        statement = f"{statement} {_ON_CONFLICT_DO_NOTHING}"
    else:
        action = _RE_CONFLICT_ACTION.search(statement, conflict.end())
        if action is None or action.group(1).lower() != "nothing":
            raise ValueError(
                "single-winner claim requires ON CONFLICT ... DO NOTHING; "
                f"refusing to build a claim from {sql!r}"
            )
    if " returning " not in f" {statement.lower()} ":
        statement = f"{statement} {_RETURNING_CLAIM}"
    return statement


def claim_unique(backend: DBBackend, sql: str, params: tuple = ()) -> bool:
    """Run an INSERT that a UNIQUE/PRIMARY KEY makes single-winner; True iff WE won.

    The atomic alternative to SELECT-then-INSERT: the database picks the winner, so two
    concurrent claimants can never both proceed. Used for money-critical single-use keys
    (a consumed stake-deposit hash), where every racer writes an IDENTICAL row — so "did
    I win?" can only come from the statement itself, never from reading the table back.

    The claim runs on its OWN connection (``get_connection``), not the backend's shared
    one. ``SQLiteBackend`` hands the same ``sqlite3.Connection`` to every worker thread,
    and concurrent ``commit()`` on it raises ``SystemError: … returned NULL without
    setting an exception`` out of CPython's sqlite3 — a claim that must be durable before
    it counts cannot ride on that. A private connection also keeps the claim out of
    whatever transaction the shared connection has open.

    The write is committed before returning: a claim only the writing transaction can see
    is not a claim. Every error propagates — a claim that could not be EVALUATED must
    never be reported as won.
    """
    is_sqlite = getattr(backend, "backend_type", "") == "sqlite"
    if is_sqlite and sqlite3.sqlite_version_info < _SQLITE_RETURNING_MIN_VERSION:
        # Fail closed rather than guess. The caller is guarding money with this claim.
        raise RuntimeError(
            f"SQLite {sqlite3.sqlite_version} has no RETURNING support (needs "
            f"{'.'.join(map(str, _SQLITE_RETURNING_MIN_VERSION))}+), so a single-winner "
            "claim cannot be decided; refusing rather than allowing a double claim"
        )
    statement = single_winner_statement(sql)
    if not is_sqlite:
        # The pooled connection is raw — the dialect translation PostgresBackend.execute
        # would normally apply (?, datetime('now'), …) has to happen here.
        statement = sqlite_to_pg(statement)
    with backend.get_connection() as conn:
        row = conn.execute(statement, params).fetchone()
        conn.commit()
    return row is not None


# ── Factory ─────────────────────────────────────────────────────────


def create_backend(
    database_url: str = "",
    db_path: str | Path | None = None,
) -> DBBackend:
    """Create the appropriate database backend.

    If database_url is set → PostgreSQL.
    Otherwise → SQLite (backward-compatible default).

    Args:
        database_url: PostgreSQL connection string (optional)
        db_path: SQLite database path (used if database_url is empty). ``None`` (or the
            hub's own default) means "no subsystem chose a path" → AIMARKET_DB_PATH.

    Returns:
        SQLiteBackend or PostgresBackend

    Path precedence — an explicit argument WINS over ``AIMARKET_DB_PATH``. The env var
    used to win over the argument, which silently aliased every SQLite database in the
    process onto one file: the channel ledger asks for ``data/channels.db`` and the
    provenance plugin for ``data/provenance.db``, but any deploy that sets
    AIMARKET_DB_PATH (every Docker image here does) handed all three the hub file while
    each subsystem kept reporting its own path. An ambient default must not silently
    override a caller that named a file — that is not configuration, it is aliasing.

    ``AIMARKET_DB_PATH`` keeps its documented job: it relocates the HUB database, i.e.
    the case where the caller asked for the hub default (or asked for nothing). An
    explicit path that disagrees with the env var is honoured and the ignored env var is
    logged once per distinct pair, so the remaining ambiguity is loud rather than silent.
    Operators who WANT one shared file must now say so per subsystem (e.g.
    ``AIMARKET_CHANNELS_DB_PATH=$AIMARKET_DB_PATH``).
    """
    url = database_url or os.environ.get("DATABASE_URL", "")

    if url and url.startswith(("postgresql://", "postgres://")):
        return PostgresBackend(url)

    env_path = os.environ.get("AIMARKET_DB_PATH", "").strip()
    if env_path:
        # Before anything here can create it: whether the hub file predates this process.
        _env_db_predates_process.setdefault(os.path.abspath(env_path), os.path.exists(env_path))
    requested = None if db_path is None else str(db_path)
    if requested is None or requested == DEFAULT_DB_PATH:
        # Nobody chose a file (or they chose the hub default): AIMARKET_DB_PATH names it.
        return SQLiteBackend(env_path or DEFAULT_DB_PATH)
    if env_path and os.path.abspath(env_path) != os.path.abspath(requested):
        _warn_ignored_env_path(requested, env_path)
    return SQLiteBackend(requested)


# Pairs already reported by _warn_ignored_env_path. The hub constructs a handful of
# backends per process (hub index, channel ledger, provenance, migration CLI); the
# operator needs the warning once per pair, not once per construction.
_reported_path_overrides: set[tuple[str, str]] = set()

# Did the AIMARKET_DB_PATH file exist when this process first looked? If not, this is a
# fresh install: nothing was ever aliased into it, and both messages below are about an
# upgrade that cannot have happened. They printed — one of them at ERROR, in capitals — on
# every first start of the standalone image, the first thing a new operator read
# (2026-10-12), so on a fresh file they go to INFO.
_env_db_predates_process: dict[str, bool] = {}


def _warn_ignored_env_path(requested: str, env_path: str) -> None:
    key = (requested, env_path)
    if key in _reported_path_overrides:
        return
    _reported_path_overrides.add(key)
    if not _env_db_predates_process.get(os.path.abspath(env_path), True) or os.path.exists(requested):
        # Fresh install, or the subsystem already has its own file: the split happened
        # before this start, so there is nothing new to tell (every CLI command on a running
        # hub printed this WARNING, seen 2026-10-12). The upgrade moment itself — hub file
        # present, subsystem file not yet — still warns and errors below.
        logger.info(
            "SQLite path %s for this subsystem, separate from the hub database %s "
            "(fresh install, or already split: nothing to migrate).", requested, env_path,
        )
        return
    logger.warning(
        "SQLite path %s was requested explicitly; ignoring AIMARKET_DB_PATH=%s for this "
        "backend. These were the SAME file before (the env var overrode the argument) — "
        "point this subsystem's own path variable at %s if a shared file was intended.",
        requested, env_path, env_path,
    )
    if os.path.exists(env_path) and not os.path.exists(requested):
        # The upgrade shape. On a hub that ran with AIMARKET_DB_PATH set, this
        # subsystem's tables were created INSIDE the env file, and this process is about
        # to start a brand-new empty one — losing, for the channel ledger, both the open
        # channels and the consumed_deposits replay guard that makes an on-chain deposit
        # single-use. This cannot be auto-migrated from here (the factory does not know
        # which tables belong to the caller), and refusing would break every first start,
        # so it is reported at ERROR with the operator action. See README "Upgrading past
        # the shared-database aliasing".
        logger.error(
            "%s does not exist yet while %s does: if this hub ran with the env var set, "
            "THIS SUBSYSTEM'S EXISTING TABLES ARE STILL IN %s and the new file starts "
            "empty. Migrate them (or point this subsystem's own path variable at %s) "
            "BEFORE serving — for the channel ledger an empty database also resets the "
            "single-use deposit guard.",
            requested, env_path, env_path, env_path,
        )
