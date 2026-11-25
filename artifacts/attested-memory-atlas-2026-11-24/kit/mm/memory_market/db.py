"""Small dual-dialect database facade used by the provider services.

PostgreSQL is selected by the service-specific DSN (or DATABASE_URL).  SQLite is
kept deliberately as an explicit development/test fallback.  The facade owns a
psycopg pool and keeps one checked-out connection for an explicit transaction;
standalone statements use and release a pool connection immediately.
"""

from __future__ import annotations

import contextvars
import re
import sqlite3
import threading
from contextlib import contextmanager
from typing import Any


def _translate(sql: str) -> str:
    sql = re.sub(r"(?im)^\s*PRAGMA\s+[^;]+;?\s*", "", sql)
    sql = re.sub(r"\bAUTOINCREMENT\b", "", sql, flags=re.I)
    sql = re.sub(r"\bdatetime\('now'\)\b", "CURRENT_TIMESTAMP", sql, flags=re.I)
    sql = sql.replace("?", "%s")
    return sql


class _DetachedCursor:
    def __init__(self, rows: list[Any], rowcount: int):
        self._rows, self._index, self.rowcount = rows, 0, rowcount

    def fetchone(self):
        if self._index >= len(self._rows):
            return None
        row = self._rows[self._index]
        self._index += 1
        return row

    def fetchall(self):
        rows = self._rows[self._index:]
        self._index = len(self._rows)
        return rows


class Database:
    def __init__(self, db_path: str, dsn_env: str):
        import os

        self.db_path = db_path
        self.url = (os.getenv(dsn_env) or os.getenv("DATABASE_URL") or "").strip()
        self._tx: contextvars.ContextVar[Any] = contextvars.ContextVar(
            f"{dsn_env.lower()}_tx", default=None
        )
        self._lock = threading.RLock()
        self._pool = None
        self._sqlite = None
        if self.url:
            if not self.url.startswith(("postgresql://", "postgres://")):
                raise RuntimeError(f"{dsn_env} must be a PostgreSQL DSN")
            from psycopg.rows import dict_row
            from psycopg_pool import ConnectionPool

            self._pool = ConnectionPool(self.url, min_size=1, max_size=10,
                                        kwargs={"row_factory": dict_row})
            with self._pool.connection() as conn:
                conn.execute("SELECT 1")
        else:
            self._sqlite = sqlite3.connect(db_path, check_same_thread=False)
            self._sqlite.row_factory = sqlite3.Row

    @property
    def is_postgres(self) -> bool:
        return self._pool is not None

    def _execute_pg(self, sql: str, params=()):
        tx = self._tx.get()
        if tx is not None:
            return tx[1].execute(_translate(sql), params)
        assert self._pool is not None
        with self._pool.connection() as conn:
            cursor = conn.execute(_translate(sql), params)
            if cursor.description:
                return _DetachedCursor(list(cursor.fetchall()), cursor.rowcount)
            return _DetachedCursor([], cursor.rowcount)

    def execute(self, sql: str, params=()):
        if self.is_postgres:
            return self._execute_pg(sql, params)
        with self._lock:
            return self._sqlite.execute(sql, params)

    def executescript(self, script: str):
        if not self.is_postgres:
            return self._sqlite.executescript(script)
        for statement in script.split(";"):
            if statement.strip():
                self._execute_pg(statement)

    def insert_or_update_rate_limit(self, ip: str, now: int, per_minute: int = 5,
                                    per_hour: int = 30) -> bool:
        """Atomically consume one payment-order request budget for an IP.

        The row lock makes this limiter work across all API workers when the
        service uses PostgreSQL. SQLite keeps the same semantics under its
        process-local lock for development and tests.
        """
        minute_start = now - (now % 60)
        hour_start = now - (now % 3600)
        with self._lock, self:
            lock = " FOR UPDATE" if self.is_postgres else ""
            row = self.execute(
                "SELECT minute_start, minute_count, hour_start, hour_count "
                "FROM payment_rate_limits WHERE ip = ?" + lock, (ip,),
            ).fetchone()
            if row is None:
                self.execute(
                    "INSERT INTO payment_rate_limits "
                    "(ip, minute_start, minute_count, hour_start, hour_count) "
                    "VALUES (?, ?, 1, ?, 1)",
                    (ip, minute_start, hour_start),
                )
                return True
            current_minute = int(row["minute_count"]) if int(row["minute_start"]) == minute_start else 0
            current_hour = int(row["hour_count"]) if int(row["hour_start"]) == hour_start else 0
            if current_minute >= per_minute or current_hour >= per_hour:
                return False
            self.execute(
                "UPDATE payment_rate_limits SET minute_start=?, minute_count=?, "
                "hour_start=?, hour_count=? WHERE ip=?",
                (minute_start, current_minute + 1, hour_start, current_hour + 1, ip),
            )
            return True

    def __enter__(self):
        if not self.is_postgres:
            self._sqlite.__enter__()
            return self
        assert self._pool is not None
        manager = self._pool.connection()
        conn = manager.__enter__()
        self._tx.set((manager, conn))
        return self

    def __exit__(self, exc_type, exc, tb):
        if not self.is_postgres:
            return self._sqlite.__exit__(exc_type, exc, tb)
        manager, conn = self._tx.get()
        try:
            if exc_type is None:
                conn.commit()
            else:
                conn.rollback()
        finally:
            self._tx.set(None)
            return manager.__exit__(exc_type, exc, tb)

    def commit(self):
        if self.is_postgres:
            tx = self._tx.get()
            if tx is not None:
                tx[1].commit()
        else:
            with self._lock:
                self._sqlite.commit()

    def rollback(self):
        if self.is_postgres:
            tx = self._tx.get()
            if tx is not None:
                tx[1].rollback()
        else:
            with self._lock:
                self._sqlite.rollback()

    def close(self):
        if self._pool is not None:
            self._pool.close()
        elif self._sqlite is not None:
            self._sqlite.close()


def production_dsn_configured(db: Database) -> bool:
    return db.is_postgres
