"""SQLite migration backup and rollback."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from orchestrator import migrate as mig


def test_backup_and_rollback_roundtrip(tmp_path):
    db = tmp_path / "pipeline.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
    conn.execute("INSERT INTO t (v) VALUES ('before')")
    conn.commit()
    conn.close()

    backup = mig._backup_db(str(db))
    assert backup is not None
    assert Path(backup).exists()

    conn = sqlite3.connect(db)
    conn.execute("DELETE FROM t")
    conn.execute("INSERT INTO t (v) VALUES ('after')")
    conn.commit()
    conn.close()

    restored_from = mig.rollback_db(str(db))
    assert restored_from == backup

    conn = sqlite3.connect(db)
    row = conn.execute("SELECT v FROM t").fetchone()
    conn.close()
    assert row[0] == "before"
