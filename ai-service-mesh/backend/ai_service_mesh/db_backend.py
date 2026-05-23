"""Database backend abstraction — SQLite and PostgreSQL with dialect translation.

AI Service Mesh uses the same pattern as AIMarket Hub:
  - `SQLiteBackend` — default single-file store under MESH_DATA_DIR
  - `PostgresBackend` — production HA via MESH_DATABASE_URL or DATABASE_URL

Factory:
    create_backend(database_url="") -> DBBackend
"""

from __future__ import annotations

import logging
import os
import re
import sqlite3
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)

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

    def executemany(self, sql: str, seq: list) -> Any: ...

    def executescript(self, sql: str) -> Any: ...

    def fetchone(self) -> dict | None: ...

    def fetchall(self) -> list[dict]: ...

    def commit(self) -> None: ...

    def close(self) -> None: ...

    def get_connection(self) -> Any: ...

    @property
    def rowcount(self) -> int: ...


# ── SQL Dialect Translation ─────────────────────────────────────────

_RE_INSERT_OR_REPLACE = re.compile(
    r"INSERT\s+OR\s+REPLACE\s+INTO\s+(\w+)\s*\((.*?)\)\s*VALUES\s*\((.*?)\)",
    re.IGNORECASE | re.DOTALL,
)
_RE_DATETIME_NOW = re.compile(r"datetime\('now'\)", re.IGNORECASE)
_RE_PRAGMA = re.compile(r"PRAGMA\s+\w+.*?;", re.IGNORECASE)
_RE_AUTOINCREMENT = re.compile(r"AUTOINCREMENT", re.IGNORECASE)
_RE_INTEGER_PK = re.compile(r"INTEGER\s+PRIMARY\s+KEY", re.IGNORECASE)


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
    def _translate_upsert(m: re.Match) -> str:
        table = m.group(1)
        cols = m.group(2)
        vals = m.group(3)
        actual_table = table_name_for_upsert or table
        conflict_cols = unique_cols or ["id"]
        conflict_clause = ", ".join(conflict_cols)
        set_clause = ", ".join(
            f"{c.strip()} = EXCLUDED.{c.strip()}"
            for c in cols.split(",")
        )
        return (
            f"INSERT INTO {actual_table} ({cols}) VALUES ({vals})\n"
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

    # Replace SQLite ? placeholders with PostgreSQL %s
    # Must be careful not to replace ? inside string literals.
    # Simple approach: replace ? not inside quotes
    result = _replace_placeholders(result)

    return result


def _replace_placeholders(sql: str) -> str:
    """Replace ? placeholders with %s, skipping those inside string literals."""
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
                # Look ahead for non-placeholder ? (like in "??")
                out.append("%s")
            else:
                out.append(c)
        i += 1
    return "".join(out)


# ── SQLite Backend ──────────────────────────────────────────────────


class SQLiteBackend:
    """SQLite backend — zero-dependency, single-file database.

    Follows the existing patterns: WAL mode, foreign_keys ON,
    sqlite3.Row row factory.
    """

    def __init__(self, db_path: str | Path = ".mesh_data/mesh.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(
            str(self.db_path), check_same_thread=False
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._last_cursor: Any = None
        logger.info("SQLite backend initialized: %s", self.db_path)

    @property
    def backend_type(self) -> str:
        return "sqlite"

    def cursor(self) -> Any:
        """Return a raw sqlite3.Cursor for backward compat with legacy code."""
        return self._conn.cursor()

    def execute(self, sql: str, params: tuple = ()) -> Any:
        self._last_cursor = self._conn.execute(sql, params)
        return self._last_cursor

    def executemany(self, sql: str, seq: list) -> Any:
        self._last_cursor = self._conn.executemany(sql, seq)
        return self._last_cursor

    def executescript(self, sql: str) -> Any:
        self._last_cursor = self._conn.executescript(sql)
        return self._last_cursor

    def fetchone(self) -> dict | None:
        if self._last_cursor:
            row = self._last_cursor.fetchone()
            return dict(row) if row else None
        return None

    def fetchall(self) -> list[dict]:
        if self._last_cursor:
            return [dict(r) for r in self._last_cursor.fetchall()]
        return []

    def commit(self) -> None:
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()
        logger.info("SQLite backend closed: %s", self.db_path)

    def get_connection(self) -> Any:
        """Return a context-managed connection that auto-closes on exit."""
        from contextlib import closing
        conn = sqlite3.connect(str(self.db_path), timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return closing(conn)

    @property
    def rowcount(self) -> int:
        return self._last_cursor.rowcount if self._last_cursor else 0


# ── PostgreSQL Backend ──────────────────────────────────────────────


class PostgresBackend:
    """PostgreSQL backend — connection pooling via psycopg_pool.

    Uses psycopg 3 with connection pool (min=2, max=8).
    Row results are returned as dicts (RealDictRow-compatible).

    DATABASE_URL is validated to reject dangerous options parameters
    that could enable SQL injection or path manipulation.
    """

    def __init__(self, database_url: str):
        import psycopg
        from psycopg.rows import dict_row
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
            kwargs={"row_factory": dict_row},
        )
        # Test connection on startup
        with self._pool.connection() as conn:
            conn.execute("SELECT 1")
        logger.info("PostgreSQL connection pool ready (min=2, max=8)")

    @property
    def backend_type(self) -> str:
        return "postgresql"

    def cursor(self) -> Any:
        """Return a psycopg cursor for backward compat with legacy code."""
        self._last_conn = self._pool.getconn()
        return self._last_conn.cursor()

    def execute(self, sql: str, params: tuple = ()) -> Any:
        # Translate SQL dialect
        pg_sql = sqlite_to_pg(sql)
        conn = self._pool.getconn()
        try:
            self._last_cursor = conn.execute(pg_sql, params)
            self._last_conn = conn
            return self._last_cursor
        except Exception:
            self._pool.putconn(conn)
            raise

    def executemany(self, sql: str, seq: list) -> Any:
        pg_sql = sqlite_to_pg(sql)
        conn = self._pool.getconn()
        try:
            self._last_cursor = conn.executemany(pg_sql, seq)
            self._last_conn = conn
            return self._last_cursor
        except Exception:
            self._pool.putconn(conn)
            raise

    def executescript(self, sql: str) -> Any:
        conn = self._pool.getconn()
        try:
            with conn.transaction():
                pg_sql = sqlite_to_pg(sql)
                for stmt in pg_sql.split(";"):
                    stmt = stmt.strip()
                    if stmt and not stmt.startswith("--"):
                        conn.execute(stmt)
            self._last_cursor = None
            self._last_conn = conn
        except Exception:
            self._pool.putconn(conn)
            raise

    def fetchone(self) -> dict | None:
        if hasattr(self, "_last_cursor") and self._last_cursor:
            row = self._last_cursor.fetchone()
            return dict(row) if row else None
        return None

    def fetchall(self) -> list[dict]:
        if hasattr(self, "_last_cursor") and self._last_cursor:
            return [dict(r) for r in self._last_cursor.fetchall()]
        return []

    def commit(self) -> None:
        conn = getattr(self, "_last_conn", None)
        if conn is None:
            return
        try:
            conn.commit()
        finally:
            self._pool.putconn(conn)
            self._last_conn = None

    def close(self) -> None:
        self._pool.close()
        logger.info("PostgreSQL backend closed")

    def get_connection(self) -> Any:
        """Return a connection from the pool (for context manager usage)."""
        return self._pool.connection()

    @property
    def rowcount(self) -> int:
        return self._last_cursor.rowcount if hasattr(self, "_last_cursor") and self._last_cursor else 0


# ── Factory ─────────────────────────────────────────────────────────


def create_backend(
    database_url: str = "",
    db_path: str | Path = ".mesh_data/mesh.db",
) -> DBBackend:
    """Create SQLite or PostgreSQL backend for the mesh store."""
    url = (
        database_url
        or os.environ.get("MESH_DATABASE_URL", "")
        or os.environ.get("DATABASE_URL", "")
    )

    if url and url.startswith(("postgresql://", "postgres://")):
        return PostgresBackend(url)

    path = os.environ.get("MESH_SQLITE_PATH", str(db_path))
    return SQLiteBackend(path)
