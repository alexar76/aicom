"""Unified DB connection wrapper (SQLite + PostgreSQL)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .db_dialect import Backend, adapt_sql, backend_for_target, is_integrity_error, require_psycopg, split_sql_script


class DbCursor:
    def __init__(self, cursor: Any, *, backend: Backend, lastrowid: int | None = None):
        self._cursor = cursor
        self._backend = backend
        self._lastrowid = lastrowid

    @property
    def lastrowid(self) -> int | None:
        if self._lastrowid is not None:
            return self._lastrowid
        return getattr(self._cursor, "lastrowid", None)

    @property
    def rowcount(self) -> int:
        value = getattr(self._cursor, "rowcount", -1)
        return value if isinstance(value, int) else -1

    def fetchall(self) -> list[Any]:
        return self._cursor.fetchall()

    def fetchone(self) -> Any:
        return self._cursor.fetchone()


class DbConnection:
    """Minimal sqlite3-compatible surface used across SKOPOS."""

    def __init__(self, con: Any, *, backend: Backend):
        self._con = con
        self.backend = backend

    @property
    def connection(self) -> Any:
        """Underlying driver connection (for pandas.read_sql_query)."""
        return self._con

    def execute(self, sql: str, params: tuple | list = ()) -> DbCursor:
        sql = adapt_sql(sql, self.backend)
        if self.backend == "postgresql":
            cur = self._con.cursor()
            if " RETURNING " in sql.upper():
                cur.execute(sql, params)
                row = cur.fetchone()
                last_id = int(row["id"]) if row and "id" in row else None
                return DbCursor(cur, backend=self.backend, lastrowid=last_id)
            cur.execute(sql, params)
            return DbCursor(cur, backend=self.backend)
        cur = self._con.execute(sql, params)
        return DbCursor(cur, backend=self.backend)

    def cursor(self) -> Any:
        if self.backend == "postgresql":
            return self._con.cursor()
        return self._con.cursor()

    def commit(self) -> None:
        self._con.commit()

    def close(self) -> None:
        self._con.close()

    def executescript(self, script: str) -> None:
        if self.backend == "postgresql":
            for stmt in split_sql_script(script):
                self.execute(stmt)
            self.commit()
            return
        self._con.executescript(script)


def connect_sqlite(db_path: str) -> DbConnection:
    import os
    import sqlite3
    import stat

    raw = db_path.strip()
    # ":memory:" must not pass through Path.resolve() — that creates literal files
    # named ":memory:" in the working directory (pytest + accidental mirror push).
    if raw == ":memory:" or raw.startswith("file::memory:"):
        con = sqlite3.connect(raw, check_same_thread=False)
        con.row_factory = sqlite3.Row
        return DbConnection(con, backend="sqlite")

    p = Path(raw).expanduser().resolve()
    p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(p), check_same_thread=False)
    con.row_factory = sqlite3.Row
    if p.exists() and os.name != "nt":
        try:
            mode = stat.S_IMODE(p.stat().st_mode)
            if mode & (stat.S_IRGRP | stat.S_IROTH | stat.S_IWGRP | stat.S_IWOTH):
                p.chmod(stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass
    return DbConnection(con, backend="sqlite")


def connect_postgres(url: str) -> DbConnection:
    psycopg = require_psycopg()
    from psycopg.rows import dict_row

    con = psycopg.connect(url, autocommit=False, row_factory=dict_row)
    return DbConnection(con, backend="postgresql")


def connect(target: str) -> DbConnection:
    if backend_for_target(target) == "postgresql":
        return connect_postgres(target)
    return connect_sqlite(target)


def connect_for_config(cfg) -> DbConnection:
    from .db_dialect import resolve_db_target

    return connect(resolve_db_target(cfg))


__all__ = ["DbConnection", "DbCursor", "connect", "connect_for_config", "connect_sqlite", "connect_postgres", "is_integrity_error"]
