"""Agent execution logs API — tail reads, llm_calls exclusion, time filters."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from web.backend.api.admin.dashboard.helpers import load_agent_execution_logs
from web.backend.core.admin_roles import AdminRole, require_admin_with_rbac


@pytest.fixture
def agent_logs_client(tmp_path, monkeypatch):
    logs = tmp_path / "logs"
    logs.mkdir(parents=True)
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("AIFACTORY_LOGS_DIR", str(logs))

    from web.backend.api.admin.dashboard import routes_products  # noqa: F401

    app = FastAPI()
    from web.backend.api.admin.dashboard._router import router

    app.include_router(router)
    app.dependency_overrides[require_admin_with_rbac] = lambda: AdminRole.ADMIN
    return TestClient(app), logs


def _write_agent_line(path: Path, agent: str, message: str, ts: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"agent": agent, "message": message, "time": ts}) + "\n")


def test_load_agent_execution_logs_excludes_llm_calls(tmp_path, monkeypatch):
    logs = tmp_path / "logs"
    logs.mkdir()
    monkeypatch.setenv("AIFACTORY_LOGS_DIR", str(logs))
    now = time.time()
    _write_agent_line(logs / "developer.jsonl", "developer", "done", now)
    _write_agent_line(logs / "llm_calls.jsonl", "should-skip", "llm row", now)

    out = load_agent_execution_logs(limit=50)
    assert out["total"] == 1
    assert out["logs"][0]["agent"] == "developer"


def test_load_agent_execution_logs_since_until(tmp_path, monkeypatch):
    logs = tmp_path / "logs"
    logs.mkdir()
    monkeypatch.setenv("AIFACTORY_LOGS_DIR", str(logs))
    base = 1_700_000_000.0
    _write_agent_line(logs / "qa.jsonl", "qa", "old", base)
    _write_agent_line(logs / "qa.jsonl", "qa", "new", base + 3600)

    out = load_agent_execution_logs(since=base + 1000, until=base + 5000, limit=10)
    assert out["total"] == 1
    assert out["logs"][0]["message"] == "new"


def test_get_agent_logs_route(agent_logs_client):
    client, logs = agent_logs_client
    now = time.time()
    _write_agent_line(logs / "pm.jsonl", "pm", "spec ready", now)

    resp = client.get("/api/admin/agent/logs?limit=20")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] >= 1
    assert any(row.get("agent") == "pm" for row in data["logs"])


def test_routes_products_defines_logger():
    text = (
        Path(__file__).resolve().parents[1]
        / "web/backend/api/admin/dashboard/routes_products.py"
    ).read_text(encoding="utf-8")
    assert "logger = logging.getLogger(__name__)" in text
