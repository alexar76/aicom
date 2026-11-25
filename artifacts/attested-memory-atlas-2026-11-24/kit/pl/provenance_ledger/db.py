from __future__ import annotations

import contextvars
import re
import sqlite3


def _translate(sql: str) -> str:
    sql = re.sub(r"(?im)^\s*PRAGMA\s+[^;]+;?\s*", "", sql)
    sql = re.sub(r"\bAUTOINCREMENT\b", "", sql, flags=re.I)
    sql = re.sub(r"\bINTEGER\s+PRIMARY\s+KEY\b", "BIGSERIAL PRIMARY KEY", sql, flags=re.I)
    return sql.replace("?", "%s")


class _Cursor:
    def __init__(self, rows, rowcount):
        self.rows, self.index, self.rowcount = list(rows), 0, rowcount

    def fetchone(self):
        if self.index >= len(self.rows):
            return None
        row = self.rows[self.index]
        self.index += 1
        return row

    def fetchall(self):
        rows = self.rows[self.index:]
        self.index = len(self.rows)
        return rows


class Database:
    def __init__(self, db_path: str, dsn_env: str):
        import os
        self.url = (os.getenv(dsn_env) or os.getenv("DATABASE_URL") or "").strip()
        self._tx = contextvars.ContextVar(f"{dsn_env.lower()}_tx", default=None)
        self._pool = None
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
    def is_postgres(self):
        return self._pool is not None

    def execute(self, sql, params=()):
        if not self.is_postgres:
            return self._sqlite.execute(sql, params)
        tx = self._tx.get()
        if tx is not None:
            return tx[1].execute(_translate(sql), params)
        with self._pool.connection() as conn:
            cur = conn.execute(_translate(sql), params)
            return _Cursor(cur.fetchall() if cur.description else [], cur.rowcount)

    def executescript(self, script):
        if not self.is_postgres:
            return self._sqlite.executescript(script)
        for statement in script.split(";"):
            if statement.strip():
                self.execute(statement)

    def __enter__(self):
        if not self.is_postgres:
            self._sqlite.__enter__()
            return self
        manager = self._pool.connection()
        conn = manager.__enter__()
        self._tx.set((manager, conn))
        return self

    def __exit__(self, exc_type, exc, tb):
        if not self.is_postgres:
            return self._sqlite.__exit__(exc_type, exc, tb)
        manager, conn = self._tx.get()
        try:
            (conn.commit if exc_type is None else conn.rollback)()
        finally:
            self._tx.set(None)
            return manager.__exit__(exc_type, exc, tb)

    def close(self):
        if self._pool is not None:
            self._pool.close()
        else:
            self._sqlite.close()
