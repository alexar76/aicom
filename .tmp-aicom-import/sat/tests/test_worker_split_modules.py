"""Unit tests for the pieces split out of pipeline_worker.py.

Each module is exercised without a worker, a state file or an event loop full of agents —
that is the point of having split them.
"""

import asyncio

import pytest

from orchestrator.worker_dispatch import DispatchOutcome, TaskDispatcher
from orchestrator.worker_hold_gate import HoldGate
from orchestrator.worker_idle_healer import IdleProductHealer
from orchestrator.worker_task_planner import DEFAULT_PRIORITY, NextTaskPlanner


# --------------------------------------------------------------------------- hold gate


def _gate(*, hard=False, hold=False, focus=()):
    return HoldGate(
        is_hard_stopped=lambda: hard,
        is_on_hold=lambda: hold,
        focus_ids=lambda: list(focus),
    )


def test_hold_gate_open_when_nothing_is_held():
    verdict = _gate().evaluate([{"status": "running"}])
    assert verdict.proceed is True
    assert verdict.soft_hold is False
    assert verdict.reset_running == 0


def test_hold_gate_hard_stop_wins_over_focus_mode():
    verdict = _gate(hard=True, hold=True, focus=("prod-1",)).evaluate([])
    assert verdict.proceed is False
    assert verdict.reset_running == 0  # hard stop parks the queue as-is, it does not rewrite it
    assert "hard-stop" in verdict.reason.lower()


def test_hold_gate_focus_mode_downgrades_a_soft_hold_to_running():
    verdict = _gate(hold=True, focus=("prod-1", "prod-2")).evaluate([{"status": "running"}])
    assert verdict.proceed is True
    assert verdict.soft_hold is False
    assert verdict.focus_ids == ("prod-1", "prod-2")


def test_hold_gate_soft_hold_returns_running_tasks_to_pending():
    queue = [
        {"id": "t1", "status": "running", "started_at": 1},
        {"id": "t2", "status": "pending"},
        {"id": "t3", "status": "RUNNING"},
    ]
    verdict = _gate(hold=True).evaluate(queue)
    assert verdict.proceed is False
    assert verdict.reset_running == 2
    assert [t["status"] for t in queue] == ["pending", "pending", "pending"]


def test_hold_gate_propagates_a_switch_that_raises():
    def _boom():
        raise RuntimeError("config unreadable")

    gate = HoldGate(is_hard_stopped=_boom, is_on_hold=_boom, focus_ids=_boom)
    # Deliberately NOT swallowed, and this pins it: an unreadable hold switch is not evidence
    # that the factory may run. The caller's cycle-level handler logs it and the next poll
    # retries, which is what the pre-split code did.
    with pytest.raises(RuntimeError):
        gate.evaluate([])


# -------------------------------------------------------------------------- dispatcher


def _run(coro):
    return asyncio.run(coro)


def test_dispatcher_runs_every_running_task_once():
    seen = []
    queue = [
        {"id": "a", "status": "running", "product_id": "p1"},
        {"id": "b", "status": "pending", "product_id": "p1"},
        {"id": "c", "status": "running", "product_id": "p2"},
    ]

    async def run_task(task):
        seen.append(task["id"])

    d = TaskDispatcher(concurrency=lambda: 4, is_paused=lambda pid: False, before_task=lambda pid: None)
    outcome = _run(d.dispatch(queue, run_task))
    assert sorted(seen) == ["a", "c"]
    assert outcome.dispatched == 2
    assert outcome.changed is True


def test_dispatcher_returns_paused_products_to_pending_and_skips_them():
    seen = []
    queue = [
        {"id": "a", "status": "running", "product_id": "paused", "started_at": 5},
        {"id": "b", "status": "running", "product_id": "live"},
    ]

    async def run_task(task):
        seen.append(task["id"])

    d = TaskDispatcher(
        concurrency=lambda: 4,
        is_paused=lambda pid: pid == "paused",
        before_task=lambda pid: None,
    )
    outcome = _run(d.dispatch(queue, run_task))
    assert seen == ["b"]
    assert outcome.paused_back == 1
    assert queue[0]["status"] == "pending"
    # `started_at` must go with it, or the stale-running sweep dates the next run from the old start.
    assert "started_at" not in queue[0]


def test_dispatcher_one_failure_does_not_cancel_the_others():
    seen = []
    queue = [{"id": str(i), "status": "running", "product_id": "p"} for i in range(4)]

    async def run_task(task):
        if task["id"] == "2":
            raise RuntimeError("agent exploded")
        seen.append(task["id"])

    d = TaskDispatcher(concurrency=lambda: 4, is_paused=lambda pid: False, before_task=lambda pid: None)
    outcome = _run(d.dispatch(queue, run_task))
    assert sorted(seen) == ["0", "1", "3"]
    assert len(outcome.errors) == 1
    assert outcome.dispatched == 4


def test_dispatcher_honours_the_concurrency_bound():
    live = 0
    peak = 0
    queue = [{"id": str(i), "status": "running", "product_id": "p"} for i in range(8)]

    async def run_task(task):
        nonlocal live, peak
        live += 1
        peak = max(peak, live)
        await asyncio.sleep(0.01)
        live -= 1

    d = TaskDispatcher(concurrency=lambda: 3, is_paused=lambda pid: False, before_task=lambda pid: None)
    _run(d.dispatch(queue, run_task))
    assert peak <= 3


def test_dispatcher_reads_concurrency_at_dispatch_time():
    values = iter([1, 5])
    d = TaskDispatcher(concurrency=lambda: next(values), is_paused=lambda pid: False, before_task=lambda pid: None)

    async def run_task(task):
        return None

    _run(d.dispatch([{"id": "a", "status": "running", "product_id": "p"}], run_task))
    _run(d.dispatch([{"id": "b", "status": "running", "product_id": "p"}], run_task))
    # Both calls consumed a value: the bound is not frozen at construction.
    with pytest.raises(StopIteration):
        next(values)


def test_dispatch_outcome_with_nothing_to_do_is_not_a_change():
    d = TaskDispatcher(concurrency=lambda: 2, is_paused=lambda pid: False, before_task=lambda pid: None)

    async def run_task(task):
        raise AssertionError("must not be called")

    outcome = _run(d.dispatch([{"id": "a", "status": "pending"}], run_task))
    assert outcome == DispatchOutcome(dispatched=0, paused_back=0, errors=[])
    assert outcome.changed is False


# ------------------------------------------------------------------------- idle healer


def _healer(**kw):
    kw.setdefault("create_next_task", lambda p: {"id": f"t-{p['id']}", "agent_type": "developer", "state": "DEV"})
    kw.setdefault("get_priority", lambda a: 5)
    kw.setdefault("on_hold", lambda pid: False)
    kw.setdefault("append_task", lambda q, t, p, gp: (q.append(t), True)[1])
    return IdleProductHealer(**kw)


def test_idle_healer_queues_the_next_step_for_an_idle_product():
    products = {"p1": {"id": "p1", "state": "DEV_IN_PROGRESS"}}
    queue = []
    outcome = _healer().heal(products, queue)
    assert outcome.healed_product_ids == {"p1"}
    assert outcome.healed_task_ids == {"t-p1"}
    assert len(queue) == 1


@pytest.mark.parametrize("state", ["COMPLETED", "FAILED", "CANCELLED", "IDEA_RECEIVED"])
def test_idle_healer_leaves_terminal_and_not_yet_started_products_alone(state):
    products = {"p1": {"id": "p1", "state": state}}
    queue = []
    assert _healer().heal(products, queue).changed is False
    assert queue == []


def test_idle_healer_skips_a_product_that_already_has_live_work():
    products = {"p1": {"id": "p1", "state": "DEV_IN_PROGRESS"}}
    for status in ("pending", "RUNNING"):
        queue = [{"id": "x", "product_id": "p1", "status": status}]
        assert _healer().heal(products, queue).changed is False
        assert len(queue) == 1


def test_idle_healer_respects_holds():
    products = {"p1": {"id": "p1", "state": "DEV_IN_PROGRESS"}}
    queue = []
    assert _healer(on_hold=lambda pid: True).heal(products, queue).changed is False


def test_idle_healer_reports_nothing_when_the_queue_refuses_the_task():
    products = {"p1": {"id": "p1", "state": "DEV_IN_PROGRESS"}}
    queue = []
    outcome = _healer(append_task=lambda q, t, p, gp: False).heal(products, queue)
    # Hygiene rejected the append (duplicate/regressive): claiming a dirty product would
    # make the worker persist a change that never happened.
    assert outcome.changed is False
    assert outcome.healed_task_ids == set()


def test_idle_healer_skips_products_with_no_next_step():
    products = {"p1": {"id": "p1", "state": "DEV_IN_PROGRESS"}}
    assert _healer(create_next_task=lambda p: None).heal(products, []).changed is False


# ------------------------------------------------------------------------- task planner


def test_planner_priority_falls_back_to_the_default_for_unknown_agents():
    planner = NextTaskPlanner()
    assert planner.priority("not-an-agent") == DEFAULT_PRIORITY


def test_planner_bug_context_is_bounded():
    planner = NextTaskPlanner()
    product = {"id": "p1", "bugs": [{"description": "x" * 50_000}]}
    assert len(planner.latest_bug_context(product)) <= 8000 + 200


# ------------------------------------------------------------- wiring into the worker
# The unit tests above prove the pieces. These prove the cycle still goes THROUGH them —
# a split that leaves a component constructed but unused passes every test above.

from unittest.mock import AsyncMock  # noqa: E402

from pipeline_worker import PipelineWorker  # noqa: E402


def _worker_with_state(monkeypatch, products, task_queue, *, hold=False, hard=False):
    monkeypatch.setattr("pipeline_worker.is_factory_on_hold", lambda **kw: hold)
    monkeypatch.setattr("pipeline_worker.is_factory_hard_stopped", lambda: hard)
    worker = PipelineWorker()
    worker._load_state_async = AsyncMock(
        return_value={"products": products, "task_queue": task_queue}
    )
    worker._save_state_async = AsyncMock(return_value=True)
    return worker


@pytest.mark.asyncio
async def test_cycle_dispatches_running_tasks_through_the_dispatcher(monkeypatch):
    worker = _worker_with_state(
        monkeypatch,
        {"p1": {"id": "p1", "state": "DEV_IN_PROGRESS"}},
        [{"id": "t1", "product_id": "p1", "status": "running", "agent_type": "developer"}],
    )
    worker._process_task = AsyncMock(return_value=None)
    await worker._process_cycle()
    worker._process_task.assert_awaited_once()
    assert worker._process_task.await_args.args[0]["id"] == "t1"


@pytest.mark.asyncio
async def test_cycle_runs_the_recovery_sweeps(monkeypatch):
    worker = _worker_with_state(monkeypatch, {}, [])
    called = []
    monkeypatch.setattr(
        type(worker.task_orchestrator),
        "run_recovery_sweeps",
        lambda self, p, q, now: called.append(now) or False,
    )
    await worker._process_cycle()
    assert called, "Phase 0 must still run its recovery sweeps"


@pytest.mark.asyncio
async def test_cycle_heals_an_idle_product_through_the_healer(monkeypatch):
    worker = _worker_with_state(
        monkeypatch, {"p1": {"id": "p1", "state": "DEV_IN_PROGRESS"}}, []
    )
    seen = []
    monkeypatch.setattr(
        type(worker.idle_healer),
        "heal",
        lambda self, products, queue: seen.append(sorted(products)) or __import__(
            "orchestrator.worker_idle_healer", fromlist=["HealOutcome"]
        ).HealOutcome(),
    )
    await worker._process_cycle()
    assert seen == [["p1"]]


@pytest.mark.asyncio
async def test_cycle_hard_stop_runs_nothing_at_all(monkeypatch):
    worker = _worker_with_state(
        monkeypatch,
        {"p1": {"id": "p1", "state": "DEV_IN_PROGRESS"}},
        [{"id": "t1", "product_id": "p1", "status": "running"}],
        hard=True,
    )
    worker._process_task = AsyncMock(return_value=None)
    called = []
    monkeypatch.setattr(
        type(worker.task_orchestrator),
        "run_recovery_sweeps",
        lambda self, p, q, now: called.append(now) or False,
    )
    await worker._process_cycle()
    worker._process_task.assert_not_awaited()
    worker._save_state_async.assert_not_awaited()
    assert called == []
    # The queue is parked untouched — a hard stop is not a place to rewrite task rows.
    assert worker._load_state_async.return_value["task_queue"][0]["status"] == "running"


@pytest.mark.asyncio
async def test_a_plain_soft_hold_does_not_log_every_cycle(monkeypatch, caplog):
    """The pre-split code was silent here; a line per poll turns a pause into log noise."""
    import logging

    worker = _worker_with_state(
        monkeypatch, {"p1": {"id": "p1", "state": "SPEC_DRAFTING"}},
        [{"id": "t1", "product_id": "p1", "status": "pending"}], hold=True,
    )
    with caplog.at_level(logging.INFO):
        await worker._process_cycle()
    assert "Factory on hold" not in caplog.text


@pytest.mark.asyncio
async def test_a_soft_hold_that_resets_running_tasks_still_says_so(monkeypatch, caplog):
    import logging

    worker = _worker_with_state(
        monkeypatch, {"p1": {"id": "p1", "state": "DEV_IN_PROGRESS"}},
        [{"id": "t1", "product_id": "p1", "status": "running", "started_at": 1.0}], hold=True,
    )
    # Not the first cycle: at startup a `running` task is an orphan and is adopted instead,
    # which is a different event with its own message and its own test.
    worker._adopted_orphans = True
    with caplog.at_level(logging.INFO):
        await worker._process_cycle()
    assert "reset 1 running task" in caplog.text
