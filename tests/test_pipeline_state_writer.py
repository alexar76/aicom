"""Tests for unified pipeline state writer contract."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from core.pipeline_state_writer import (
    append_product_to_pipeline_state,
    pipeline_json_mirror_enabled,
    read_pipeline_state,
    should_recover_json_from_sqlite,
    sqlite_state_newer_than_json,
    write_pipeline_state,
)
from orchestrator.pipeline_worker_persistence import PipelineStatePersistence
from orchestrator.sqlite_manager import SQLiteManager


def test_sql_mode_skips_json_write_without_mirror(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    root = tmp_path / "data"
    state = root / "state"
    state.mkdir(parents=True)
    pj = state / "pipeline.json"
    db = state / "pipeline.db"
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(root))
    monkeypatch.setenv("PIPELINE_DB_BACKEND", "sqlite")
    monkeypatch.setenv("USE_SQLITE", "true")
    monkeypatch.setenv("SQLITE_PATH", str(db))
    monkeypatch.setenv("AICOM_PIPELINE_JSON", str(pj))
    monkeypatch.delenv("AIFACTORY_PIPELINE_MIRROR_JSON", raising=False)

    assert pipeline_json_mirror_enabled() is False
    state_doc = {
        "products": {"p1": {"id": "p1", "idea": "x", "state": "IDEA_RECEIVED", "updated_at": 1.0}},
        "task_queue": [],
        "current_task_id": None,
    }
    assert write_pipeline_state(state_doc) is True
    assert db.is_file()
    assert not pj.is_file()


def test_mirror_writes_json_when_enabled(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    root = tmp_path / "data"
    state = root / "state"
    state.mkdir(parents=True)
    pj = state / "pipeline.json"
    db = state / "pipeline.db"
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(root))
    monkeypatch.setenv("PIPELINE_DB_BACKEND", "sqlite")
    monkeypatch.setenv("USE_SQLITE", "true")
    monkeypatch.setenv("SQLITE_PATH", str(db))
    monkeypatch.setenv("AICOM_PIPELINE_JSON", str(pj))
    monkeypatch.setenv("AIFACTORY_PIPELINE_MIRROR_JSON", "1")

    assert write_pipeline_state({"products": {}, "task_queue": [], "current_task_id": None}) is True
    assert pj.is_file()


def test_recovery_requires_flag_or_newer_sqlite(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    root = tmp_path / "data"
    state_dir = root / "state"
    state_dir.mkdir(parents=True)
    pj = state_dir / "pipeline.json"
    db = state_dir / "pipeline.db"
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(root))
    monkeypatch.setenv("SQLITE_PATH", str(db))
    monkeypatch.setenv("AICOM_PIPELINE_JSON", str(pj))
    monkeypatch.delenv("AIFACTORY_PIPELINE_JSON_RECOVER_FROM_SQLITE", raising=False)

    mgr = SQLiteManager(str(db))
    mgr.connect()
    mgr.upsert_product(
        {"id": "p-rec", "idea": "x", "state": "IDEA_RECEIVED", "created_at": 1.0, "updated_at": 1.0, "metadata": {}}
    )
    mgr.close()

    pj.write_text("{bad", encoding="utf-8")
    time.sleep(0.02)
    Path(db).touch()

    assert sqlite_state_newer_than_json(pj) is True
    assert should_recover_json_from_sqlite(pj) is True

    monkeypatch.setenv("AIFACTORY_PIPELINE_JSON_RECOVER_FROM_SQLITE", "0")
    time.sleep(0.02)
    pj.write_text('{"products":{},"task_queue":[]}', encoding="utf-8")
    Path(db).touch()  # still - we need json older; reset
    old_mtime = pj.stat().st_mtime
    import os

    os.utime(db, (time.time() + 10, time.time() + 10))
    os.utime(pj, (old_mtime, old_mtime))
    assert should_recover_json_from_sqlite(pj) is True

    os.utime(pj, (time.time() + 20, time.time() + 20))
    os.utime(db, (time.time() + 5, time.time() + 5))
    assert sqlite_state_newer_than_json(pj) is False
    assert should_recover_json_from_sqlite(pj) is False

    monkeypatch.setenv("AIFACTORY_PIPELINE_JSON_RECOVER_FROM_SQLITE", "1")
    assert should_recover_json_from_sqlite(pj) is True


def test_load_json_recovery_respects_gate(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    root = tmp_path / "data"
    state_dir = root / "state"
    state_dir.mkdir(parents=True)
    db = state_dir / "pipeline.db"
    pj = state_dir / "pipeline.json"
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(root))
    monkeypatch.setenv("SQLITE_PATH", str(db))
    monkeypatch.setenv("AICOM_PIPELINE_JSON", str(pj))
    monkeypatch.delenv("AIFACTORY_PIPELINE_JSON_RECOVER_FROM_SQLITE", raising=False)

    mgr = SQLiteManager(str(db))
    mgr.connect()
    mgr.upsert_product(
        {"id": "p-persist", "idea": "x", "state": "IDEA_RECEIVED", "created_at": 1.0, "updated_at": 1.0, "metadata": {}}
    )
    mgr.close()

    pj.write_text("{bad", encoding="utf-8")
    import os

    os.utime(pj, (1, 1))
    os.utime(db, (time.time() + 50, time.time() + 50))

    p = PipelineStatePersistence(state_file=pj, use_sql_store=False)
    state = p.load_json_with_recovery()
    assert state is not None
    assert "p-persist" in state["products"]


def test_append_product_sql_primary(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    root = tmp_path / "data"
    state = root / "state"
    state.mkdir(parents=True)
    db = state / "pipeline.db"
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(root))
    monkeypatch.setenv("PIPELINE_DB_BACKEND", "sqlite")
    monkeypatch.setenv("USE_SQLITE", "true")
    monkeypatch.setenv("SQLITE_PATH", str(db))

    product = {"id": "p-new", "idea": "hello", "state": "IDEA_RECEIVED", "updated_at": time.time()}
    assert append_product_to_pipeline_state(product) is True
    loaded = read_pipeline_state()
    assert loaded["products"]["p-new"]["idea"] == "hello"
