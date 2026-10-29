"""Prior-check persistence (sqlite) — the memory the diff runs against.

One row per check: resource_url, ISO timestamp, and the full result JSON.
The latest row for a URL is the baseline for the next check's diff. The
database is the service's only state; lose it and every check becomes a
"first check" again (the diff says so honestly).
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from datetime import datetime, timezone


def _iso_of(epoch_seconds: float) -> str:
    return (
        datetime.fromtimestamp(epoch_seconds, tz=timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


class CheckStore:
    def __init__(self, path: str):
        self._path = path
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        with self._lock:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS checks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    resource_url TEXT NOT NULL,
                    checked_at TEXT NOT NULL,
                    result_json TEXT NOT NULL
                )
                """
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_checks_url ON checks (resource_url, id)"
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS nudges (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    dedupe_key TEXT NOT NULL UNIQUE,
                    sender TEXT NOT NULL,
                    stall TEXT NOT NULL,
                    route TEXT NOT NULL,
                    defect_code TEXT NOT NULL,
                    first_seen TEXT NOT NULL,
                    received_epoch REAL NOT NULL,
                    message_json TEXT NOT NULL
                )
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS nudge_optouts (
                    stall TEXT PRIMARY KEY,
                    wallet TEXT NOT NULL,
                    received_epoch REAL NOT NULL
                )
                """
            )
            self._conn.commit()

    def latest(self, resource_url: str) -> dict | None:
        """The most recent stored result for this URL, or None."""
        with self._lock:
            row = self._conn.execute(
                "SELECT result_json FROM checks WHERE resource_url = ? ORDER BY id DESC LIMIT 1",
                (resource_url,),
            ).fetchone()
        if row is None:
            return None
        try:
            return json.loads(row[0])
        except ValueError:
            return None

    def save(self, result: dict) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO checks (resource_url, checked_at, result_json) VALUES (?, ?, ?)",
                (result["resource_url"], result["checked_at"], json.dumps(result)),
            )
            self._conn.commit()

    def count(self, resource_url: str) -> int:
        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(*) FROM checks WHERE resource_url = ?", (resource_url,)
            ).fetchone()
        return int(row[0]) if row else 0

    # --- nudges ----------------------------------------------------------
    # The fleet-health nudge inbox (app/nudge.py): signed inbound
    # mail about broken routes, stored verbatim, deduped on
    # (sender, route, defect, first_seen). Opt-outs live beside the
    # mail: a stall whose payTo signed an opt-out is never nudged
    # again, and enforcement reads this table (the sender engine
    # syncs it into its own registry before every send).

    def store_nudge(self, message: dict, dedupe_key: str) -> bool:
        """Store one verified nudge. Returns False when the dedupe
        key already exists — a re-sent identical nudge is a
        duplicate delivery, not a second entry."""
        now = time.time()
        defect = message.get("defect") or {}
        with self._lock:
            cur = self._conn.execute(
                "INSERT OR IGNORE INTO nudges (dedupe_key, sender, "
                "stall, route, defect_code, first_seen, "
                "received_epoch, message_json) VALUES (?, ?, ?, ?, "
                "?, ?, ?, ?)",
                (
                    dedupe_key,
                    str(message["sender"]),
                    str(message["stall"]),
                    str(message.get("route", "")),
                    str(defect.get("code", "")),
                    str(message.get("first_seen", "")),
                    now,
                    json.dumps(message, sort_keys=True),
                ),
            )
            self._conn.commit()
            return cur.rowcount > 0

    def nudge_count(self) -> int:
        with self._lock:
            row = self._conn.execute("SELECT COUNT(*) FROM nudges").fetchone()
        return int(row[0])

    def nudges_since(self, sender: str, since_epoch: float) -> int:
        """Verified nudges received from one sender after an epoch —
        the rate limiter's count (duplicates included: a re-send is
        still a knock)."""
        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(*) FROM nudges WHERE lower(sender) = "
                "lower(?) AND received_epoch > ?",
                (sender, since_epoch),
            ).fetchone()
        return int(row[0])

    def list_nudges(self, limit: int = 50) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT received_epoch, message_json FROM nudges "
                "ORDER BY id DESC LIMIT ?",
                (max(1, min(int(limit), 500)),),
            ).fetchall()
        return [
            {
                "received_at": _iso_of(row[0]),
                "message": json.loads(row[1]),
            }
            for row in rows
        ]

    def record_optout(self, stall: str, wallet: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO nudge_optouts (stall, wallet, "
                "received_epoch) VALUES (?, ?, ?)",
                (stall.rstrip("/"), wallet, time.time()),
            )
            self._conn.commit()

    def list_optouts(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT stall, wallet, received_epoch FROM "
                "nudge_optouts ORDER BY stall"
            ).fetchall()
        return [
            {"stall": row[0], "wallet": row[1], "recorded_at": _iso_of(row[2])}
            for row in rows
        ]

    def is_opted_out(self, stall: str) -> bool:
        with self._lock:
            row = self._conn.execute(
                "SELECT 1 FROM nudge_optouts WHERE stall = ?",
                (stall.rstrip("/"),),
            ).fetchone()
        return row is not None
