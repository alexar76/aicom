"""Tests for the pipeline persistence layer split out of PipelineStateMachine.

Covers the properties the inline persistence did not have: saves proportional to
what changed, one long-lived async connection, a task claim that survives two workers
reaching for the same task (and refuses when the store cannot decide), a JSON write a
crash cannot truncate, and a load that refuses to read a broken store as empty.
"""

from __future__ import annotations

import asyncio
import json
import os

import pytest

from orchestrator.pipeline_repository import (
    PipelineRepository,
    PipelineStateLoadError,
    TaskClaimUnavailable,
)
from orchestrator.state_machine import (
    PipelineState,
    PipelineStateMachine,
    Task,
    TaskStatus,
)


def _machine(tmp_path, name: str = "state") -> PipelineStateMachine:
    return PipelineStateMachine(
        state_file=str(tmp_path / name / "pipeline.json"),
        use_sqlite=True,
        db_path=str(tmp_path / name / "pipeline.db"),
    )


def _queue_task(sm: PipelineStateMachine, product_id: str, task_id: str, priority: int = 5) -> Task:
    task = Task(
        id=task_id,
        product_id=product_id,
        agent_type="analyst",
        state=PipelineState.MARKET_RESEARCHED,
        status=TaskStatus.PENDING,
        priority=priority,
        created_at=1_700_000_000.0 + priority,
    )
    sm.add_task_to_queue(task)
    return task


def _count_upserts(sm: PipelineStateMachine) -> dict[str, list[str]]:
    """Wrap the live manager so a save's row writes can be counted."""
    manager = sm.sqlite_manager
    seen: dict[str, list[str]] = {"products": [], "tasks": []}
    original_product, original_task = manager.upsert_product, manager.upsert_task

    def product(payload):
        seen["products"].append(payload["id"])
        return original_product(payload)

    def task(payload):
        seen["tasks"].append(payload["id"])
        return original_task(payload)

    manager.upsert_product = product
    manager.upsert_task = task
    return seen


# ---------------------------------------------------------------------------
# Saves are proportional to the change
# ---------------------------------------------------------------------------


class TestChangeTrackedSaves:
    def test_save_writes_only_the_changed_task(self, tmp_path):
        sm = _machine(tmp_path)
        for i in range(3):
            product = sm.create_product(f"idea {i}")
            _queue_task(sm, product.id, f"task-{i}")

        seen = _count_upserts(sm)
        sm.task_queue[1].status = TaskStatus.COMPLETED
        sm._save_state()

        assert seen["tasks"] == ["task-1"]
        assert seen["products"] == []

    def test_save_with_nothing_changed_writes_nothing(self, tmp_path):
        sm = _machine(tmp_path)
        product = sm.create_product("idea")
        _queue_task(sm, product.id, "task-0")

        seen = _count_upserts(sm)
        sm._save_state()
        sm._save_state()

        assert seen == {"products": [], "tasks": []}

    def test_reload_does_not_rewrite_untouched_state(self, tmp_path):
        sm = _machine(tmp_path)
        product = sm.create_product("idea")
        _queue_task(sm, product.id, "task-0")

        reopened = _machine(tmp_path)
        assert reopened.get_product(product.id) is not None
        seen = _count_upserts(reopened)
        reopened._save_state()

        assert seen == {"products": [], "tasks": []}

    def test_resave_all_rewrites_everything(self, tmp_path):
        sm = _machine(tmp_path)
        for i in range(2):
            product = sm.create_product(f"idea {i}")
            _queue_task(sm, product.id, f"task-{i}")

        seen = _count_upserts(sm)
        sm.resave_all()

        assert sorted(seen["tasks"]) == ["task-0", "task-1"]
        assert len(seen["products"]) == 2

    def test_deploy_hook_fires_only_for_changed_products(self, tmp_path, monkeypatch):
        fired: list[tuple[str, str]] = []
        monkeypatch.setattr(
            PipelineStateMachine,
            "_on_product_saved",
            staticmethod(lambda p: fired.append((p["id"], p["state"]))),
        )
        sm = _machine(tmp_path)
        first = sm.create_product("first")
        second = sm.create_product("second")
        fired.clear()

        sm.products[second.id].state = PipelineState.COMPLETED
        sm._save_state()
        sm._save_state()

        assert fired == [(second.id, PipelineState.COMPLETED.value)]
        assert first.id not in [pid for pid, _ in fired]

    def test_failed_row_is_retried_on_the_next_save(self, tmp_path):
        sm = _machine(tmp_path)
        product = sm.create_product("idea")
        _queue_task(sm, product.id, "task-0")

        manager = sm.sqlite_manager
        original = manager.upsert_task
        manager.upsert_task = lambda payload: (_ for _ in ()).throw(RuntimeError("disk full"))
        sm.task_queue[0].status = TaskStatus.COMPLETED
        sm._save_state()  # swallowed; the row must stay dirty

        manager.upsert_task = original
        seen = _count_upserts(sm)
        sm._save_state()

        assert seen["tasks"] == ["task-0"]

    def test_json_save_is_skipped_when_nothing_moved(self, tmp_path):
        repo = PipelineRepository(
            state_file=str(tmp_path / "pipeline.json"),
            db_path=str(tmp_path / "pipeline.db"),
            use_sqlite=False,
        )
        products = {"p1": {"id": "p1", "state": "idea_received"}}
        tasks = [{"id": "t1", "status": "pending"}]

        assert repo.save_json(products, tasks) is True
        assert repo.save_json(products, tasks) is False

        tasks[0]["status"] = "running"
        assert repo.save_json(products, tasks) is True

    def test_json_save_runs_again_when_the_file_disappears(self, tmp_path):
        state_file = tmp_path / "pipeline.json"
        repo = PipelineRepository(
            state_file=str(state_file), db_path=str(tmp_path / "p.db"), use_sqlite=False
        )
        products = {"p1": {"id": "p1"}}
        assert repo.save_json(products, []) is True
        state_file.unlink()
        assert repo.save_json(products, []) is True


# ---------------------------------------------------------------------------
# One long-lived async connection
# ---------------------------------------------------------------------------


class TestAsyncConnectionLifecycle:
    def test_async_saves_share_one_manager(self, tmp_path, monkeypatch):
        import orchestrator.async_sqlite_manager as async_module

        built: list[object] = []
        real = async_module.AsyncSQLiteManager

        class Counting(real):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                built.append(self)

        monkeypatch.setattr(async_module, "AsyncSQLiteManager", Counting)

        sm = _machine(tmp_path)

        async def scenario():
            product = await sm.acreate_product("idea")
            _queue_task(sm, product.id, "task-0")
            await sm._asave_state()
            sm.task_queue[0].status = TaskStatus.COMPLETED
            await sm._asave_state()
            assert sm._repo._async_manager is not None
            await sm.aclose()
            assert sm._repo._async_manager is None

        asyncio.run(scenario())
        assert len(built) == 1, "the async connection must outlive a single save"

    def test_manager_is_reopened_for_a_new_event_loop(self, tmp_path):
        sm = _machine(tmp_path)

        async def save():
            await sm.acreate_product("idea")
            return sm._repo._async_manager

        first = asyncio.run(save())
        second = asyncio.run(save())

        assert first is not None and second is not None
        assert first is not second, "an aiosqlite connection cannot cross event loops"

    def test_aclose_without_any_async_save_is_a_noop(self, tmp_path):
        sm = _machine(tmp_path)
        asyncio.run(sm.aclose())


# ---------------------------------------------------------------------------
# Task claiming
# ---------------------------------------------------------------------------


class TestAtomicClaim:
    def test_two_machines_cannot_claim_the_same_task(self, tmp_path):
        first = _machine(tmp_path)
        product = first.create_product("idea")
        _queue_task(first, product.id, "task-0")

        second = _machine(tmp_path)
        assert [t.id for t in second.task_queue] == ["task-0"]

        claimed_by_first = first.get_next_task()
        claimed_by_second = second.get_next_task()

        assert claimed_by_first is not None and claimed_by_first.id == "task-0"
        assert claimed_by_second is None, "the same task was handed to two workers"

    def test_loser_moves_on_to_the_next_candidate(self, tmp_path):
        first = _machine(tmp_path)
        product = first.create_product("idea")
        _queue_task(first, product.id, "task-high", priority=1)
        _queue_task(first, product.id, "task-low", priority=9)

        second = _machine(tmp_path)
        assert first.get_next_task().id == "task-high"

        got = second.get_next_task()
        assert got is not None and got.id == "task-low"

    def test_lost_task_adopts_the_stored_status(self, tmp_path):
        first = _machine(tmp_path)
        product = first.create_product("idea")
        _queue_task(first, product.id, "task-0")
        second = _machine(tmp_path)

        first.get_next_task()
        second.get_next_task()

        lost = second._find_task("task-0")
        assert lost.status == TaskStatus.RUNNING
        assert lost.started_at is not None

    def test_lost_task_is_not_written_back_as_pending(self, tmp_path):
        first = _machine(tmp_path)
        product = first.create_product("idea")
        _queue_task(first, product.id, "task-0")
        second = _machine(tmp_path)

        first.get_next_task()
        second.get_next_task()
        second._save_state()

        stored = first.sqlite_manager.get_task("task-0")
        assert stored["status"] == TaskStatus.RUNNING.value

    def test_task_that_exists_only_in_memory_is_claimable(self, tmp_path):
        sm = _machine(tmp_path)
        product = sm.create_product("idea")
        task = Task(
            id="task-unsaved",
            product_id=product.id,
            agent_type="analyst",
            state=PipelineState.MARKET_RESEARCHED,
            status=TaskStatus.PENDING,
            created_at=1_700_000_000.0,
        )
        sm.task_queue.append(task)  # deliberately not persisted

        claimed = sm.get_next_task()
        assert claimed is not None and claimed.id == "task-unsaved"
        # The claim itself put the row in the store, already running.
        assert sm.sqlite_manager.get_task("task-unsaved")["status"] == TaskStatus.RUNNING.value

    def test_an_unsaved_task_is_claimed_by_one_machine_only(self, tmp_path):
        """No row is not proof of ownership: two machines holding the same unsaved task
        and claiming it before either saved both used to win it. The INSERT that claims
        it admits exactly one."""
        first = _machine(tmp_path)
        product = first.create_product("idea")
        second = _machine(tmp_path)
        twin = Task(
            id="task-twin",
            product_id=product.id,
            agent_type="analyst",
            state=PipelineState.MARKET_RESEARCHED,
            status=TaskStatus.PENDING,
            created_at=1_700_000_000.0,
        ).to_dict()

        # Both claims land before either machine saves anything.
        assert first._repo.claim_pending_task("task-twin", 1.0, twin) is True
        assert second._repo.claim_pending_task("task-twin", 2.0, twin) is False
        stored = first.sqlite_manager.get_task("task-twin")
        assert stored["status"] == TaskStatus.RUNNING.value and stored["started_at"] == 1.0

    def test_store_claim_without_a_row_or_a_task_is_refused(self, tmp_path):
        sm = _machine(tmp_path)
        assert sm.sqlite_manager.claim_pending_task("no-such-task", 1.0) is False

    def test_claim_fails_closed_when_the_store_errors(self, tmp_path):
        sm = _machine(tmp_path)
        product = sm.create_product("idea")
        _queue_task(sm, product.id, "task-0")
        sm.sqlite_manager.claim_pending_task = lambda *a, **k: (_ for _ in ()).throw(
            RuntimeError("db gone")
        )

        assert sm.get_next_task() is None
        # Not handed out, and not marked running behind anyone's back either.
        assert sm._find_task("task-0").status == TaskStatus.PENDING

        with pytest.raises(TaskClaimUnavailable):
            sm._repo.claim_pending_task("task-0", 1.0)

    def test_async_claim_fails_closed_when_the_store_errors(self, tmp_path):
        sm = _machine(tmp_path)
        product = sm.create_product("idea")
        _queue_task(sm, product.id, "task-0")

        async def scenario():
            manager = await sm._repo._async_manager_for_loop()

            async def broken(*a, **k):
                raise RuntimeError("db gone")

            manager.claim_pending_task = broken
            try:
                return await sm.aget_next_task()
            finally:
                await sm.aclose()

        assert asyncio.run(scenario()) is None
        assert sm._find_task("task-0").status == TaskStatus.PENDING

    def test_async_claim_of_an_unsaved_task_is_exclusive(self, tmp_path):
        first = _machine(tmp_path)
        product = first.create_product("idea")
        second = _machine(tmp_path)
        twin = Task(
            id="task-twin",
            product_id=product.id,
            agent_type="analyst",
            state=PipelineState.MARKET_RESEARCHED,
            status=TaskStatus.PENDING,
            created_at=1_700_000_000.0,
        ).to_dict()

        async def scenario():
            try:
                return (
                    await first._repo.aclaim_pending_task("task-twin", 1.0, twin),
                    await second._repo.aclaim_pending_task("task-twin", 2.0, twin),
                )
            finally:
                await first.aclose()
                await second.aclose()

        assert asyncio.run(scenario()) == (True, False)

    def test_json_backend_still_claims_in_priority_order(self, tmp_path):
        sm = PipelineStateMachine(state_file=str(tmp_path / "pipeline.json"))
        product = sm.create_product("idea")
        _queue_task(sm, product.id, "task-low", priority=9)
        _queue_task(sm, product.id, "task-high", priority=1)

        assert sm.get_next_task().id == "task-high"
        assert sm.get_next_task().id == "task-low"
        assert sm.get_next_task() is None

    def test_async_claim_is_exclusive_too(self, tmp_path):
        first = _machine(tmp_path)
        product = first.create_product("idea")
        _queue_task(first, product.id, "task-0")
        second = _machine(tmp_path)

        async def scenario():
            try:
                return await first.aget_next_task(), await second.aget_next_task()
            finally:
                await first.aclose()
                await second.aclose()

        claimed_by_first, claimed_by_second = asyncio.run(scenario())
        assert claimed_by_first is not None and claimed_by_first.id == "task-0"
        assert claimed_by_second is None

    def test_concurrent_async_claims_do_not_double_book(self, tmp_path):
        sm = _machine(tmp_path)
        product = sm.create_product("idea")
        _queue_task(sm, product.id, "task-0")

        async def scenario():
            try:
                return await asyncio.gather(sm.aget_next_task(), sm.aget_next_task())
            finally:
                await sm.aclose()

        results = asyncio.run(scenario())
        assert sorted(r is None for r in results) == [False, True]


# ---------------------------------------------------------------------------
# A broken store is not an empty one
# ---------------------------------------------------------------------------


class TestLoadRefusesBrokenState:
    def test_corrupt_json_stops_the_load_and_is_left_on_disk(self, tmp_path):
        path = tmp_path / "pipeline.json"
        path.write_text('{"products": {"p1": ', encoding="utf-8")

        with pytest.raises(PipelineStateLoadError):
            PipelineStateMachine(state_file=str(path))
        assert path.read_text(encoding="utf-8") == '{"products": {"p1": '

    def test_unreadable_row_stops_the_load(self, tmp_path):
        path = tmp_path / "pipeline.json"
        path.write_text(json.dumps({
            "products": {"p1": {"id": "p1", "idea": "x", "state": "no_such_state"}},
            "task_queue": [],
        }), encoding="utf-8")

        with pytest.raises(PipelineStateLoadError):
            PipelineStateMachine(state_file=str(path))

    def test_sqlite_read_failure_stops_the_load(self, tmp_path, monkeypatch):
        from orchestrator import sqlite_manager as sqlite_manager_module

        def broken(self):
            raise RuntimeError("disk I/O error")

        monkeypatch.setattr(sqlite_manager_module.SQLiteManager, "get_all_products", broken)
        with pytest.raises(PipelineStateLoadError):
            _machine(tmp_path)

    def test_missing_file_is_still_an_empty_state(self, tmp_path):
        sm = PipelineStateMachine(state_file=str(tmp_path / "absent.json"))
        assert sm.products == {} and sm.task_queue == []


class TestAtomicJsonSave:
    def test_a_failed_rename_leaves_the_previous_document(self, tmp_path, monkeypatch):
        path = tmp_path / "pipeline.json"
        sm = PipelineStateMachine(state_file=str(path))
        sm.create_product("first", product_id="p1")
        before = path.read_text(encoding="utf-8")

        def crash(*a, **k):
            raise OSError("killed mid-write")

        monkeypatch.setattr(os, "replace", crash)
        sm.create_product("second", product_id="p2")

        assert path.read_text(encoding="utf-8") == before
        assert [p.name for p in tmp_path.iterdir()] == ["pipeline.json"], "temp file cleaned up"

    def test_document_round_trips(self, tmp_path):
        path = tmp_path / "pipeline.json"
        sm = PipelineStateMachine(state_file=str(path))
        sm.create_product("idée", product_id="p1")
        assert PipelineStateMachine(state_file=str(path)).products["p1"].idea == "idée"


# ---------------------------------------------------------------------------
# The split itself
# ---------------------------------------------------------------------------


def test_state_machine_delegates_storage_to_the_repository(tmp_path):
    sm = _machine(tmp_path)
    assert isinstance(sm._repo, PipelineRepository)
    assert sm.sqlite_manager is sm._repo.sqlite_manager
    sm.close()
    assert sm._repo._sqlite_manager is None


def test_migration_still_reaches_sqlite(tmp_path):
    json_machine = PipelineStateMachine(state_file=str(tmp_path / "pipeline.json"))
    product = json_machine.create_product("idea")
    _queue_task(json_machine, product.id, "task-0")

    result = json_machine.migrate_json_to_sqlite(str(tmp_path / "migrated.db"))
    assert result == {"products_migrated": 1, "tasks_migrated": 1}
