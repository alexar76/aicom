"""Watchdog -> state machine -> real SQLite -> event bus and production replay router."""

from __future__ import annotations

import asyncio
import time
from contextlib import ExitStack

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI

import core.events as events
from orchestrator.state_machine import PipelineState, PipelineStateMachine, Task, TaskStatus
from orchestrator.timeout_manager import TimeoutManager
from web.backend.api.build_replay_public import router as replay_router

pytestmark = [pytest.mark.asyncio, pytest.mark.component_integration]


@pytest_asyncio.fixture
async def pipeline_stack(tmp_path, monkeypatch):
    db = tmp_path / "pipeline.db"
    for key, value in {
        "AIFACTORY_DATA_ROOT": str(tmp_path), "SQLITE_PATH": str(db),
        "USE_SQLITE": "true", "PIPELINE_DB_BACKEND": "sqlite",
        "AIFACTORY_TASK_MAX_RETRIES": "1",
    }.items():
        monkeypatch.setenv(key, value)
    bus = events.EventBus()
    monkeypatch.setattr(events, "_event_bus", bus)
    delivered = asyncio.Queue()

    async def receive(event):
        await delivered.put(event)

    bus.subscribe("TaskCompleted", receive)
    app = FastAPI()
    app.include_router(replay_router, prefix="/api")
    with ExitStack() as cleanup:
        def reopen():
            machine = PipelineStateMachine(
                state_file=str(tmp_path / "unused.json"), use_sqlite=True, db_path=str(db),
            )
            cleanup.callback(machine.close)
            return machine

        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                yield reopen, client, delivered, db
        finally:
            await bus.shutdown()


def _seed(machine):
    product = machine.create_product("An internal quality-check product", product_id="prod-integration")
    task = Task(
        id="analyst-integration", product_id=product.id, agent_type="analyst",
        state=PipelineState.MARKET_RESEARCHED, created_at=time.time(), max_retries=1,
        input_data={"prompt": "private-input-marker"},
    )
    machine.add_task_to_queue(task)
    assert machine.get_next_task().id == task.id
    return task.id


async def _expire(machine, task_id):
    watchdog = TimeoutManager()

    def expired(expired_id):
        assert machine.timeout_task(expired_id) is True
        watchdog._running = False

    watchdog.start_task(task_id, "analyst", expired, custom_timeout=0)
    watchdog._running = True
    await watchdog._monitor_loop(0)
    assert watchdog.get_active_timeouts() == {}


@pytest.mark.parametrize("exhaust_retries", [False, True])
async def test_timeout_retry_survives_restart_and_reaches_public_replay(pipeline_stack, exhaust_retries):
    reopen, client, delivered, _ = pipeline_stack
    first = reopen()
    task_id = _seed(first)
    await _expire(first, task_id)
    first.close()

    # Both consumers start from the same stored pending retry, as after a restart.
    owner, competitor = reopen(), reopen()
    task = owner.get_next_task()
    assert task.id == task_id
    assert task.retry_count == 1
    assert task.max_retries == 1
    assert task.input_data == {"prompt": "private-input-marker"}
    assert competitor.get_next_task() is None, "a persisted retry still has only one owner"
    if exhaust_retries:
        await _expire(owner, task_id)
        expected_state, expected_status = PipelineState.FAILED, TaskStatus.FAILED
    else:
        assert owner.complete_task(task_id, {
            "verdict": "go", "score": 0.9,
            "api_key": "private-output-marker", "prompt": "private-input-marker",
        }) is True
        expected_state, expected_status = PipelineState.MARKET_RESEARCHED, TaskStatus.COMPLETED
    owner.close()
    competitor.close()

    # Inspect a fresh connection, not the state machine that performed the write.
    reader = reopen()
    assert reader.get_product("prod-integration").state == expected_state
    stored = reader.sqlite_manager.get_task(task_id)
    assert stored["status"] == expected_status.value
    assert stored["retry_count"] == (2 if exhaust_retries else 1)
    pending = [t for t in reader.task_queue if t.status == TaskStatus.PENDING]
    assert [t.agent_type for t in pending] == ([] if exhaust_retries else ["pm"])

    event = await asyncio.wait_for(delivered.get(), timeout=5)
    assert event.task_id == task_id
    assert event.status == expected_status.value
    response = await client.get("/api/public/build/prod-integration")
    assert response.status_code == 200
    replay = response.json()
    assert replay["build"]["state"] == expected_state.name
    stage = next(s for s in replay["stages"] if s["agent"] == "analyst")
    assert stage["status"] == expected_status.value
    assert stage["retry_count"] == stored["retry_count"]
    assert stage["had_error"] is True
    if not exhaust_retries:
        assert stage["highlights"] == {"verdict": "go", "score": 0.9}
    for private in ("private-input-marker", "private-output-marker", "Task timed out", "output_data", "input_data"):
        assert private not in response.text


async def test_corrupt_database_returns_safe_503_and_recovers_after_restore(pipeline_stack):
    reopen, client, _, db = pipeline_stack
    machine = reopen()
    _seed(machine)
    machine.close()
    backup = db.read_bytes()
    db.write_bytes(b"corrupt database: /private/internal-database-marker")
    failed = await client.get("/api/public/build/prod-integration")
    assert failed.status_code == 503
    assert failed.json() == {"detail": "replay unavailable"}
    assert "internal-database-marker" not in failed.text

    db.write_bytes(backup)
    recovered = await client.get("/api/public/build/prod-integration")
    assert recovered.status_code == 200
    assert recovered.json()["stages"][0]["status"] == "running"
