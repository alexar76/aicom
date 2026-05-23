"""Database backend selection and SQLite persistence."""

from pathlib import Path

from ai_service_mesh.db import MeshStore
from ai_service_mesh.db_backend import create_backend


def test_create_backend_defaults_to_sqlite(tmp_path: Path):
    backend = create_backend(database_url="", db_path=tmp_path / "mesh.db")
    assert backend.backend_type == "sqlite"
    backend.close()


def test_mesh_store_uses_sqlite_by_default(tmp_path: Path):
    store = MeshStore(tmp_path / "data")
    assert store.backend_type == "sqlite"
    task = store.create_task("test intent", 1.0, "")
    assert store.get_task(task.id) is not None
    store.close()


def test_health_reports_database_type(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["database"] == "sqlite"


def test_fail_stale_tasks_dead_letters_in_progress(tmp_path: Path):
    from datetime import datetime, timedelta, timezone

    from ai_service_mesh.models import TaskStatus

    store = MeshStore(tmp_path / "data")
    task = store.create_task("stale job", 2.0, "")
    old = (datetime.now(timezone.utc) - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    store._execute(
        "UPDATE tasks SET status=?, created_at=? WHERE id=?",
        (TaskStatus.VERIFYING.value, old, task.id),
    )
    n = store.fail_stale_tasks(600)
    assert n == 1
    updated = store.get_task(task.id)
    assert updated is not None
    assert updated.status == TaskStatus.FAILED
    assert updated.error == "task_timeout_dead_letter"
    store.close()
