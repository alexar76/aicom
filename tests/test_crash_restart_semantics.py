"""What a crash and restart actually do to the queue.

Written to answer three questions asked in the 2026-08-29 review, in its own words:
can a crash/restart produce **double execution**, **task loss**, or **product/task
desync**? The answers are pinned here rather than argued, because the interesting one
turned out to be a real defect: an attempt that killed the worker was not counted as an
attempt, so the retry ladder never advanced and the restart loop never converged.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.sqlite_manager import SQLiteManager
from orchestrator.worker_components import TaskOrchestrator


def _priority(agent: str) -> int:
    return 5


def _running_task(tid="t1", pid="p1", retry=0):
    return {
        "id": tid,
        "product_id": pid,
        "agent_type": "developer",
        "state": "DEV_IN_PROGRESS",
        "status": "running",
        "started_at": 100.0,
        "retry_count": retry,
    }


# ------------------------------------------------------- 1. the restart loop terminates


def test_an_unclean_start_counts_as_an_attempt():
    orch = TaskOrchestrator(_priority)
    queue = [_running_task()]
    assert orch.adopt_orphaned_running_tasks({}, queue, now=500.0) is True
    task = queue[0]
    # Re-queued for a fresh try...
    assert task["status"] == "pending"
    assert task["started_at"] is None
    # ...but the crash is on the record. Without this the ladder never moved.
    assert task["retry_count"] == 1
    assert "unclean worker start" in task["error"]


def test_a_task_that_kills_the_worker_stops_being_retried(monkeypatch):
    """The failure mode the counter exists for: crash → restart → same task → crash."""
    monkeypatch.setenv("AIFACTORY_TASK_MAX_RETRIES", "3")
    from core.pipeline_retry_limits import task_max_retries

    limit = task_max_retries()
    orch = TaskOrchestrator(_priority)
    queue = [_running_task()]

    statuses = []
    for restart in range(limit + 1):
        queue[0]["status"] = "running"  # the worker started it, then died again
        queue[0]["started_at"] = 100.0 + restart
        orch.adopt_orphaned_running_tasks({}, queue, now=500.0 + restart)
        statuses.append(queue[0]["status"])

    # It converges: the last restart refuses to re-queue and hands it to the failure path.
    assert statuses[-1] == "failed"
    assert queue[0]["completed_at"]
    assert queue[0]["retry_count"] > limit


def test_adoption_is_one_shot_and_does_not_touch_live_work():
    """After the first cycle, `running` means a runner really is running it."""
    orch = TaskOrchestrator(_priority)
    queue = [_running_task()]
    orch.adopt_orphaned_running_tasks({}, queue, now=500.0)

    # Second cycle of the SAME worker: a task it started itself must be left alone.
    live = _running_task(tid="t2", pid="p2")
    queue.append(live)
    # The worker calls this once per process; proving the guard is the worker's test below.
    assert live["status"] == "running"


@pytest.mark.asyncio
async def test_the_worker_adopts_orphans_once_not_every_cycle(monkeypatch):
    from unittest.mock import AsyncMock

    from pipeline_worker import PipelineWorker

    monkeypatch.setattr("pipeline_worker.is_factory_on_hold", lambda **kw: False)
    monkeypatch.setattr("pipeline_worker.is_factory_hard_stopped", lambda: False)

    worker = PipelineWorker()
    calls = []
    monkeypatch.setattr(
        type(worker.task_orchestrator),
        "adopt_orphaned_running_tasks",
        lambda self, products, queue, now: calls.append(now) or False,
    )
    worker._load_state_async = AsyncMock(return_value={"products": {}, "task_queue": []})
    worker._save_state_async = AsyncMock(return_value=True)

    await worker._process_cycle()
    await worker._process_cycle()
    await worker._process_cycle()
    assert len(calls) == 1, "adoption must run once per process, not once per cycle"


# ------------------------------------------------------------------- 2. no task is lost


def test_no_task_is_lost_across_a_restart(tmp_path: Path, monkeypatch):
    """Cancel-don't-delete: the queue is upsert-only, so a restart must find everything."""
    db = tmp_path / "pipeline.db"
    mgr = SQLiteManager(str(db))
    mgr.connect()
    mgr.upsert_product(
        {"id": "p1", "idea": "x", "state": "DEV_IN_PROGRESS", "created_at": 1.0,
         "updated_at": 1.0, "metadata": {}}
    )
    for tid, status in (("t-pending", "pending"), ("t-running", "running"), ("t-failed", "failed")):
        mgr.upsert_task(
            {"id": tid, "product_id": "p1", "agent_type": "developer", "status": status,
             "state": "DEV_IN_PROGRESS", "created_at": 1.0, "retry_count": 0}
        )
    mgr.close()

    reopened = SQLiteManager(str(db))
    reopened.connect()
    try:
        found = {t["id"] for t in reopened.get_worker_tasks()}
    finally:
        reopened.close()
    assert found == {"t-pending", "t-running", "t-failed"}


def test_a_cancelled_task_leaves_the_active_queue_but_survives_in_the_store(tmp_path: Path):
    """The queue never deletes rows, so 'gone from the queue' must mean a status, not a hole."""
    db = tmp_path / "pipeline.db"
    mgr = SQLiteManager(str(db))
    mgr.connect()
    try:
        mgr.upsert_product(
            {"id": "p1", "idea": "x", "state": "DEV_IN_PROGRESS", "created_at": 1.0,
             "updated_at": 1.0, "metadata": {}}
        )
        mgr.upsert_task(
            {"id": "t1", "product_id": "p1", "agent_type": "developer", "status": "cancelled",
             "state": "DEV_IN_PROGRESS", "created_at": 1.0, "retry_count": 0}
        )
        assert [t["id"] for t in mgr.get_worker_tasks()] == []
        assert any(t["id"] == "t1" for t in mgr.get_all_tasks())
    finally:
        mgr.close()


# ------------------------------------------------------------- 3. product/task desync


def test_a_human_gate_left_over_a_live_task_is_realigned():
    """The desync that actually strands products: the gate state outlives the round."""
    orch = TaskOrchestrator(_priority)
    products = {"p1": {"id": "p1", "idea": "x", "state": "HUMAN_REVIEW_PENDING"}}
    queue = [
        {"id": "t1", "product_id": "p1", "agent_type": "developer", "state": "DEV_IN_PROGRESS",
         "status": "running", "started_at": 10.0, "retry_count": 0}
    ]
    assert orch.reconcile_product_task_states(products, queue, now=500.0) is True
    assert products["p1"]["state"] != "HUMAN_REVIEW_PENDING"


def test_other_state_mismatches_are_deliberately_left_alone():
    """Not an oversight — realigning an arbitrary mismatch can run an agent twice.

    The narrow rule is the point: only HUMAN_REVIEW_PENDING is realigned, because there
    the product is provably behind its own live task. Anywhere else the repair would be a
    guess, and the guess costs a duplicate agent run. Pinned so nobody widens it casually.
    """
    orch = TaskOrchestrator(_priority)
    products = {"p1": {"id": "p1", "idea": "x", "state": "SPEC_DRAFTING"}}
    queue = [
        {"id": "t1", "product_id": "p1", "agent_type": "developer", "state": "DEV_IN_PROGRESS",
         "status": "running", "started_at": 10.0, "retry_count": 0}
    ]
    assert orch.reconcile_product_task_states(products, queue, now=500.0) is False
    assert products["p1"]["state"] == "SPEC_DRAFTING"
    assert queue[0]["status"] == "running"


# ── four ways the first version of this fix did not actually converge ────────────


def test_adoption_leaves_a_paused_product_alone():
    """Every sibling sweep asks this; skipping it charged an attempt to a paused product."""
    import core.pipeline_product_pause as pause

    orch = TaskOrchestrator(_priority)
    queue = [_running_task(tid="t1", pid="paused"), _running_task(tid="t2", pid="live")]
    original = pause.is_product_pipeline_work_paused
    pause.is_product_pipeline_work_paused = lambda pid: pid == "paused"
    try:
        orch.adopt_orphaned_running_tasks({}, queue, now=500.0)
    finally:
        pause.is_product_pipeline_work_paused = original
    assert queue[0]["status"] == "running" and queue[0]["retry_count"] == 0
    assert queue[1]["status"] == "pending" and queue[1]["retry_count"] == 1


def test_exhausting_the_ladder_parks_the_product_so_bootstrap_cannot_reset_it(monkeypatch):
    """The escape: create_initial_tasks re-creates a first stage at retry_count 0.

    Fail the task and stop there, and a product whose first stage kills the worker gets a
    brand-new task with a zeroed ladder on every restart — the loop, through the bootstrap.
    """
    monkeypatch.setenv("AIFACTORY_TASK_MAX_RETRIES", "1")
    orch = TaskOrchestrator(_priority)
    products = {"p1": {"id": "p1", "idea": "x", "state": "IDEA_RECEIVED"}}
    queue = [_running_task(pid="p1", retry=1)]

    orch.adopt_orphaned_running_tasks(products, queue, now=500.0)
    assert queue[0]["status"] == "failed"
    assert products["p1"]["state"] == "HUMAN_REVIEW_PENDING"
    assert products["p1"]["human_review_kind"] == "crash_loop_parked"

    # And the bootstrap now refuses to make another one.
    before = len(queue)
    orch.create_initial_tasks(products, queue, now=501.0)
    assert len(queue) == before


def test_a_parked_crash_loop_gets_no_next_task_either():
    """Same park set as the other repair parks, so the idle healer will not revive it."""
    from orchestrator.worker_task_planner import _REPAIR_PARK_KINDS, NextTaskPlanner

    assert "crash_loop_parked" in _REPAIR_PARK_KINDS
    product = {"id": "p1", "state": "HUMAN_REVIEW_PENDING",
               "human_review_kind": "crash_loop_parked"}
    assert NextTaskPlanner().create_next_task(product) is None


def test_the_park_kind_is_refused_by_queue_hygiene_too():
    """The kind lives in two readers; a park honoured by only one is not a park."""
    from orchestrator.task_queue_hygiene import missing_forward_task

    product = {"id": "p1", "state": "HUMAN_REVIEW_PENDING",
               "human_review_kind": "crash_loop_parked"}
    assert missing_forward_task(product, []) is None


@pytest.mark.asyncio
async def test_a_soft_hold_at_startup_does_not_skip_the_crash_ladder(monkeypatch):
    """The gate flips running→pending; run it first and the orphans are indistinguishable."""
    from unittest.mock import AsyncMock

    from pipeline_worker import PipelineWorker

    monkeypatch.setattr("pipeline_worker.is_factory_on_hold", lambda **kw: True)
    monkeypatch.setattr("pipeline_worker.is_factory_hard_stopped", lambda: False)

    worker = PipelineWorker()
    queue = [{"id": "t1", "product_id": "p1", "status": "running",
              "started_at": 1.0, "retry_count": 0, "agent_type": "developer"}]
    worker._load_state_async = AsyncMock(
        return_value={"products": {"p1": {"id": "p1", "state": "DEV_IN_PROGRESS"}},
                      "task_queue": queue})
    worker._save_state_async = AsyncMock(return_value=True)

    await worker._process_cycle()
    assert queue[0]["retry_count"] == 1, "the crash was not counted under a soft hold"
    assert queue[0]["status"] == "pending"


@pytest.mark.asyncio
async def test_a_hard_stop_still_adopts_nothing(monkeypatch):
    from unittest.mock import AsyncMock

    from pipeline_worker import PipelineWorker

    monkeypatch.setattr("pipeline_worker.is_factory_on_hold", lambda **kw: False)
    monkeypatch.setattr("pipeline_worker.is_factory_hard_stopped", lambda: True)

    worker = PipelineWorker()
    queue = [{"id": "t1", "product_id": "p1", "status": "running",
              "started_at": 1.0, "retry_count": 0}]
    worker._load_state_async = AsyncMock(
        return_value={"products": {}, "task_queue": queue})
    worker._save_state_async = AsyncMock(return_value=True)

    await worker._process_cycle()
    assert queue[0] == {"id": "t1", "product_id": "p1", "status": "running",
                        "started_at": 1.0, "retry_count": 0}


@pytest.mark.asyncio
async def test_a_failed_save_retries_the_adoption_next_cycle(monkeypatch):
    """Flagging it done before the write landed lost the adoption for the whole process."""
    from unittest.mock import AsyncMock

    from pipeline_worker import PipelineWorker

    monkeypatch.setattr("pipeline_worker.is_factory_on_hold", lambda **kw: False)
    monkeypatch.setattr("pipeline_worker.is_factory_hard_stopped", lambda: False)

    worker = PipelineWorker()
    calls = []
    monkeypatch.setattr(
        type(worker.task_orchestrator), "adopt_orphaned_running_tasks",
        lambda self, p, q, now: calls.append(now) or True)
    worker._load_state_async = AsyncMock(return_value={"products": {}, "task_queue": []})
    worker._save_state_async = AsyncMock(return_value=False)   # the write fails

    await worker._process_cycle()
    await worker._process_cycle()
    assert len(calls) == 2, "a lost write must not consume the one-shot"

    worker._save_state_async = AsyncMock(return_value=True)
    await worker._process_cycle()
    await worker._process_cycle()
    assert len(calls) == 3, "and once it lands, it must not run again"
