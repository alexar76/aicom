"""Public build-replay API: sanitized agent-stage timeline + gallery feed.

The replay is a public, unauthenticated boundary, so the most important
assertions here are negative: prompts, secrets, raw output and error strings
must never appear in the JSON.
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def seeded(tmp_path, monkeypatch):
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "pipeline.db"))

    from core.paths import pipeline_db_path
    from orchestrator.sqlite_manager import SQLiteManager

    sm = SQLiteManager(str(pipeline_db_path()))
    sm.connect()
    now = time.time()
    sm.upsert_product(
        {
            "id": "p1",
            "idea": "A tool to split bills with friends",
            "state": "COMPLETED",
            "created_at": now - 3000,
            "updated_at": now,
            "metadata": {"category": "saas", "spec": {"product_name": "SplitEasy"}},
        }
    )
    # analyst: output deliberately laced with things that must NOT leak
    sm.upsert_task(
        {
            "id": "t1",
            "product_id": "p1",
            "agent_type": "analyst",
            "status": "COMPLETED",
            "state": "market_researched",
            "created_at": now - 3000,
            "started_at": now - 2990,
            "completed_at": now - 2900,
            "output_data": {
                "verdict": "go",
                "score": 0.91,
                "category": "saas",
                "api_key": "sk-SECRET-LEAK",
                "prompt": "SYSTEM PROMPT LEAK",
                "raw_text": "free form blob " * 40,
            },
        }
    )
    sm.upsert_task(
        {
            "id": "t2",
            "product_id": "p1",
            "agent_type": "developer",
            "status": "COMPLETED",
            "state": "code_committed",
            "created_at": now - 2800,
            "started_at": now - 2700,
            "completed_at": now - 1800,
            "retry_count": 2,
            "output_data": {"files_written": 7, "tech_stack_label": "Next.js + FastAPI", "secret_token": "abc"},
        }
    )
    sm.upsert_task(
        {
            "id": "t3",
            "product_id": "p1",
            "agent_type": "landing_developer",
            "status": "COMPLETED",
            "state": "code_committed",
            "created_at": now - 1700,
            "started_at": now - 1700,
            "completed_at": now - 1690,
            "output_data": {},
        }
    )
    sm.upsert_task(
        {
            "id": "t4",
            "product_id": "p1",
            "agent_type": "security",
            "status": "FAILED",
            "state": "security_scanned",
            "created_at": now - 1600,
            "started_at": now - 1600,
            "completed_at": now - 1500,
            "error": "boom referencing /etc/passwd",
            "output_data": {"findings_count": 3, "passed": False},
        }
    )
    sm.close()
    yield tmp_path


def _client() -> TestClient:
    from web.backend.main import app

    return TestClient(app)


def test_build_replay_shape_and_ordering(seeded):
    res = _client().get("/api/public/build/p1")
    assert res.status_code == 200
    data = res.json()

    build = data["build"]
    assert build["title"] == "SplitEasy"
    assert build["shipped"] is True
    assert build["state"] == "COMPLETED"
    assert build["stage_count"] == 4
    assert build["repair_rounds"] == 1
    assert build["product_url"] == "/product/p1"

    stages = data["stages"]
    assert [s["agent"] for s in stages] == ["analyst", "developer", "landing_developer", "security"]

    dev = stages[1]
    assert dev["duration_sec"] == 900.0
    assert dev["retry_count"] == 2
    assert dev["highlights"]["files"] == 7
    assert dev["highlights"]["stack"] == "Next.js + FastAPI"

    # landing fast-path agent must be mirrored with its own label
    assert stages[2]["label"] == "Landing Developer"

    sec = stages[3]
    assert sec["status"] == "failed"
    assert sec["had_error"] is True
    assert sec["highlights"]["findings"] == 3
    assert sec["highlights"]["passed"] is False


def test_build_replay_never_leaks_secrets(seeded):
    blob = _client().get("/api/public/build/p1").text
    for forbidden in (
        "sk-SECRET-LEAK",
        "SYSTEM PROMPT LEAK",
        "secret_token",
        "abc",
        "free form blob",
        "/etc/passwd",
        "api_key",
        "prompt",
    ):
        assert forbidden not in blob, f"replay leaked: {forbidden}"


def test_build_replay_missing_is_404(seeded):
    assert _client().get("/api/public/build/does-not-exist").status_code == 404


def test_builds_feed(seeded):
    res = _client().get("/api/public/builds")
    assert res.status_code == 200
    data = res.json()
    assert data["count"] == 1
    card = data["builds"][0]
    assert card["id"] == "p1"
    assert card["title"] == "SplitEasy"
    assert card["stage_count"] == 4
    assert card["replay_url"] == "/build/p1"


def test_builds_feed_limit_validation(seeded):
    assert _client().get("/api/public/builds?limit=0").status_code == 422
    assert _client().get("/api/public/builds?limit=999").status_code == 422
