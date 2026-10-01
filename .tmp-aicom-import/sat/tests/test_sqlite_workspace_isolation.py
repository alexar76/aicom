from __future__ import annotations

import os
from pathlib import Path

from orchestrator.sqlite_manager import SQLiteManager


def _product(pid: str) -> dict:
    return {
        "id": pid,
        "idea": f"idea {pid}",
        "state": "idea_received",
        "created_at": 1.0,
        "updated_at": 1.0,
        "metadata": {},
    }


def test_workspace_isolation(tmp_path: Path, monkeypatch):
    db = str(tmp_path / "pipeline.db")

    monkeypatch.setenv("AIFACTORY_WORKSPACE_ID", "ws-a")
    a = SQLiteManager(db)
    a.connect()
    a.upsert_product(_product("prod-a"))
    a.close()

    monkeypatch.setenv("AIFACTORY_WORKSPACE_ID", "ws-b")
    b = SQLiteManager(db)
    b.connect()
    b.upsert_product(_product("prod-b"))

    ids_b = {p["id"] for p in b.get_all_products()}
    assert ids_b == {"prod-b"}
    assert b.get_product("prod-a") is None
    b.close()

    monkeypatch.setenv("AIFACTORY_WORKSPACE_ID", "ws-a")
    c = SQLiteManager(db)
    c.connect()
    ids_a = {p["id"] for p in c.get_all_products()}
    assert ids_a == {"prod-a"}
    c.close()
