"""A write that fails under lock contention must not freeze the shared connection.

Reproduced from hub.modelmarket.dev, 2026-09-22: one API write timed out behind the
crawler's write lock, the implicit transaction stayed open, and for 18 hours every read
on the request connection returned the snapshot from that moment — an empty catalogue —
while the crawler's own connection kept the file current.
"""

import sqlite3

import pytest

from aimarket_hub import db_backend
from aimarket_hub.db_backend import SQLiteBackend


def test_a_locked_write_does_not_pin_the_snapshot(tmp_path, monkeypatch):
    monkeypatch.setattr(db_backend, "_SQLITE_BUSY_TIMEOUT_S", 0.2)
    path = tmp_path / "hub.db"
    api = SQLiteBackend(path)
    api.execute("CREATE TABLE t (v INTEGER)")
    api.execute("INSERT INTO t VALUES (1)")
    api.commit()

    crawler = sqlite3.connect(str(path), timeout=5)
    crawler.execute("BEGIN IMMEDIATE")
    crawler.execute("UPDATE t SET v = 2")
    with pytest.raises(sqlite3.OperationalError):
        api.execute("UPDATE t SET v = 99")
    crawler.commit()
    # The first read after the failure is where the snapshot gets pinned…
    assert api.execute("SELECT v FROM t").fetchone()[0] == 2

    # …so the second one is where a stuck connection shows it.
    crawler.execute("UPDATE t SET v = 3")
    crawler.commit()
    assert api.execute("SELECT v FROM t").fetchone()[0] == 3

    # And the connection can write again.
    api.execute("UPDATE t SET v = 4")
    api.commit()
    assert crawler.execute("SELECT v FROM t").fetchone()[0] == 4
