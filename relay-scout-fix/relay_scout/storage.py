from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from relay_scout.models import Snapshot


def snapshot_root() -> Path:
    root = os.environ.get("RELAY_SCOUT_DATA_DIR")
    if root:
        return Path(root)
    return Path(os.environ.get("RELAY_SCOUT_HOME", Path.home() / ".relay-scout"))


def init_db(db_path: Path | None = None) -> Path:
    path = db_path or (snapshot_root() / "relay_scout.db")
    path.parent.mkdir(parents=True, exist_ok=True)
    with _connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                endpoint_name TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                status_code INTEGER NOT NULL,
                latency_ms REAL NOT NULL,
                payload TEXT,
                error TEXT
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_snapshots_endpoint_id ON snapshots(endpoint_name, id)"
        )
        conn.commit()
    return path


@contextmanager
def _connect(path: Path):
    conn = sqlite3.connect(str(path))
    try:
        yield conn
    finally:
        conn.close()


def save_snapshot(snapshot: Snapshot, db_path: Path | None = None) -> int:
    path = init_db(db_path)
    with _connect(path) as conn:
        cur = conn.execute(
            """
            INSERT INTO snapshots (endpoint_name, timestamp, status_code, latency_ms, payload, error)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                snapshot.endpoint_name,
                snapshot.timestamp,
                snapshot.status_code,
                snapshot.latency_ms,
                json.dumps(snapshot.response_json) if snapshot.response_json is not None else None,
                snapshot.error,
            ),
        )
        conn.commit()
        return int(cur.lastrowid)


def get_last_two_snapshots(endpoint_name: str, db_path: Path | None = None) -> list[Snapshot]:
    path = init_db(db_path)
    with _connect(path) as conn:
        rows = conn.execute(
            """
            SELECT endpoint_name, timestamp, status_code, latency_ms, payload, error
            FROM snapshots WHERE endpoint_name = ?
            ORDER BY id DESC LIMIT 2
            """,
            (endpoint_name,),
        ).fetchall()
    out: list[Snapshot] = []
    for row in reversed(rows):
        payload = json.loads(row[4]) if row[4] else None
        out.append(
            Snapshot(
                endpoint_name=row[0],
                timestamp=row[1],
                status_code=int(row[2]),
                latency_ms=float(row[3]),
                response_json=payload if isinstance(payload, dict) else None,
                error=row[5],
            )
        )
    return out
