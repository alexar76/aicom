"""Exercise watchdog races through real callbacks, without wall-clock sleeps."""

from __future__ import annotations

import asyncio

import pytest

from orchestrator.timeout_manager import TimeoutManager


@pytest.fixture
def clock(monkeypatch):
    now = [100.0]
    monkeypatch.setattr("orchestrator.timeout_manager.time.monotonic", lambda: now[0])
    return now


@pytest.mark.asyncio
async def test_rearmed_id_survives_the_expired_callback(clock):
    manager = TimeoutManager()

    async def rearm(task_id):
        manager.start_task(task_id, "unknown", lambda _: None, custom_timeout=30)
        manager._running = False

    manager.start_task("same", "unknown", rearm, custom_timeout=0)
    manager._running = True
    await manager._monitor_loop(0)
    assert manager.get_active_timeouts() == {"same": 30}


@pytest.mark.asyncio
async def test_callback_can_extend_another_expired_task(clock):
    manager = TimeoutManager()
    called = []

    def first(_):
        manager.extend_timeout("second", 30)
        manager._running = False

    manager.start_task("first", "unknown", first, custom_timeout=0)
    manager.start_task("second", "unknown", called.append, custom_timeout=0)
    manager._running = True
    await manager._monitor_loop(0)
    assert called == []
    assert manager.get_active_timeouts() == {"second": 30}


@pytest.mark.asyncio
async def test_awaitable_returned_by_a_callable_is_awaited(clock):
    manager = TimeoutManager()
    called = []

    async def expired(task_id):
        called.append(task_id)
        manager._running = False

    manager.start_task("one", "unknown", lambda task_id: expired(task_id), custom_timeout=0)
    manager._running = True
    await manager._monitor_loop(0)
    assert called == ["one"]
    assert manager.get_active_timeouts() == {}


@pytest.mark.asyncio
async def test_callback_failure_does_not_stop_other_timeouts(clock, caplog):
    manager = TimeoutManager()
    called = []

    def broken(_):
        raise RuntimeError("callback failed")

    def done(task_id):
        called.append(task_id)
        manager._running = False

    manager.start_task("broken", "unknown", broken, custom_timeout=0)
    manager.start_task("next", "unknown", done, custom_timeout=0)
    manager._running = True
    await manager._monitor_loop(0)
    assert called == ["next"]
    assert "callback failed" in caplog.text
    assert manager.get_active_timeouts() == {}


def test_wall_clock_jumps_do_not_change_deadlines(clock, monkeypatch):
    manager = TimeoutManager()
    manager.start_task("one", "unknown", lambda _: None, custom_timeout=30)
    monkeypatch.setattr("orchestrator.timeout_manager.time.time", lambda: 1e12)
    clock[0] += 7
    assert manager.get_active_timeouts() == {"one": 23}


@pytest.mark.asyncio
async def test_start_is_idempotent_and_stop_reaps_the_monitor():
    manager = TimeoutManager()
    await manager.start_monitoring()
    first = manager._monitor_task
    try:
        await manager.start_monitoring()
        assert manager._monitor_task is first
    finally:
        await manager.stop_monitoring()
    assert first.done()
    assert manager._monitor_task is None
    # No sleeping background task is left behind.
    assert first not in asyncio.all_tasks()

