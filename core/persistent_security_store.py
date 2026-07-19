"""SQLite-backed persistence for login rate limits and OIDC nonce replay protection."""

from __future__ import annotations

import logging
import os
import sqlite3
import threading
import time

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_singleton: PersistentSecurityStore | None = None

_SCHEMA = """
CREATE TABLE IF NOT EXISTS rate_limit_attempts (
    key TEXT NOT NULL,
    ts REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_rate_limit_key_ts ON rate_limit_attempts (key, ts);

CREATE TABLE IF NOT EXISTS used_nonces (
    nonce TEXT PRIMARY KEY,
    expires_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_used_nonces_expires ON used_nonces (expires_at);
"""


class PersistentSecurityStore:
    """WAL SQLite store for cross-restart security counters."""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._conn: sqlite3.Connection | None = None
        self._connect()

    def _connect(self) -> None:
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.executescript(_SCHEMA)
        conn.commit()
        self._conn = conn

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._connect()
        assert self._conn is not None
        return self._conn

    def record_attempt(self, key: str, ts: float | None = None) -> None:
        when = ts if ts is not None else time.time()
        with _lock:
            self.conn.execute(
                "INSERT INTO rate_limit_attempts (key, ts) VALUES (?, ?)",
                (key, when),
            )
            self.conn.commit()

    def recent_attempt_count(self, key: str, window_seconds: float) -> int:
        cutoff = time.time() - window_seconds
        with _lock:
            self.conn.execute(
                "DELETE FROM rate_limit_attempts WHERE key = ? AND ts < ?",
                (key, cutoff),
            )
            row = self.conn.execute(
                "SELECT COUNT(*) FROM rate_limit_attempts WHERE key = ? AND ts >= ?",
                (key, cutoff),
            ).fetchone()
            self.conn.commit()
            return int(row[0] if row else 0)

    def clear_attempts(self, key: str) -> None:
        with _lock:
            self.conn.execute("DELETE FROM rate_limit_attempts WHERE key = ?", (key,))
            self.conn.commit()

    def claim_nonce(self, nonce: str, ttl_seconds: float) -> bool:
        """Atomically claim nonce. Returns False when already used (replay)."""
        now = time.time()
        expires_at = now + max(float(ttl_seconds), 1.0)
        with _lock:
            self.conn.execute("DELETE FROM used_nonces WHERE expires_at < ?", (now,))
            cur = self.conn.execute(
                "INSERT OR IGNORE INTO used_nonces (nonce, expires_at) VALUES (?, ?)",
                (nonce, expires_at),
            )
            self.conn.commit()
            return cur.rowcount == 1

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None


def get_persistent_security_store() -> PersistentSecurityStore | None:
    """Lazy singleton; returns None when DB cannot be opened (read-only FS, etc.)."""
    global _singleton
    if _singleton is not None:
        return _singleton
    with _lock:
        if _singleton is not None:
            return _singleton
        try:
            from core.paths import security_store_db_path

            _singleton = PersistentSecurityStore(str(security_store_db_path()))
            return _singleton
        except Exception as exc:
            logger.warning("PersistentSecurityStore unavailable, using in-memory fallback: %s", exc)
            return None


def reset_persistent_security_store_for_tests() -> None:
    """Drop cached singleton (unit tests only)."""
    global _singleton
    with _lock:
        if _singleton is not None:
            _singleton.close()
            _singleton = None
