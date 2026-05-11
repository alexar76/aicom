"""
SQLite Backend Tests for PipelineStateMachine
==============================================
Tests for PipelineStateMachine with use_sqlite=True and for the SQLiteManager
CRUD operations directly.

These tests run alongside the existing test_pipeline.py (JSON backend) to
ensure the SQLite backend behaves identically.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from orchestrator.state_machine import (
    PipelineStateMachine,
    PipelineState,
    TaskStatus,
    Task,
    Product,
)
from orchestrator.sqlite_manager import SQLiteManager
from orchestrator.migrate import migrate as migrate_json_to_sqlite


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def sqlite_manager(tmp_path):
    """Create a SQLiteManager backed by a temp DB file."""
    db_path = str(tmp_path / "state" / "pipeline.db")
    manager = SQLiteManager(db_path)
    manager.connect()
    yield manager
    manager.close()


@pytest.fixture
def sqlite_state_machine(tmp_path):
    """Create a PipelineStateMachine with use_sqlite=True backed by a temp DB."""
    db_path = str(tmp_path / "state" / "pipeline.db")
    sm = PipelineStateMachine(
        state_file=str(tmp_path / "state" / "pipeline.json"),
        use_sqlite=True,
        db_path=db_path,
    )
    # Clear any stale state
    sm.products = {}
    sm.task_queue = []
    return sm


@pytest.fixture
def sqlite_product_with_task(sqlite_state_machine, sample_product_idea):
    """Create a product with its first task queued (SQLite backend)."""
    product = sqlite_state_machine.create_product(sample_product_idea)
    task = Task(
        id="task-sqlite-initial",
        product_id=product.id,
        agent_type="analyst",
        state=PipelineState.MARKET_RESEARCHED,
        created_at=time.time(),
        priority=1,
    )
    sqlite_state_machine.add_task_to_queue(task)
    return product, task


# ============================================================================
# SQLiteManager CRUD Tests
# ============================================================================


class TestSQLiteManagerCRUD:
    """Direct tests for SQLiteManager product/task CRUD."""

    def test_connect_creates_schema(self, tmp_path):
        """Connecting creates the tables."""
        db_path = str(tmp_path / "test.db")
        mgr = SQLiteManager(db_path)
        mgr.connect()
        tables = mgr.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        table_names = [r["name"] for r in tables]
        assert "products" in table_names
        assert "tasks" in table_names
        mgr.close()

    def test_upsert_and_get_product(self, sqlite_manager):
        """Insert a product and retrieve it."""
        product_dict = {
            "id": "prod-test-1",
            "idea": "Test idea",
            "state": "idea_received",
            "created_at": 1000.0,
            "updated_at": 1000.0,
            "metadata": {},
        }
        sqlite_manager.upsert_product(product_dict)
        loaded = sqlite_manager.get_product("prod-test-1")
        assert loaded is not None
        assert loaded["id"] == "prod-test-1"
        assert loaded["idea"] == "Test idea"
        assert loaded["state"] == "idea_received"

    def test_upsert_product_with_metadata(self, sqlite_manager):
        """Metadata fields (spec, architecture, etc.) are persisted."""
        product_dict = {
            "id": "prod-meta",
            "idea": "Meta test",
            "state": "spec_written",
            "created_at": 1000.0,
            "updated_at": 1000.0,
            "metadata": {
                "spec": {"name": "test", "version": "1.0"},
                "tags": ["ai", "test"],
                "category": "demo",
                "error": None,
            },
        }
        sqlite_manager.upsert_product(product_dict)
        loaded = sqlite_manager.get_product("prod-meta")
        assert loaded["metadata"]["spec"] == {"name": "test", "version": "1.0"}
        assert loaded["metadata"]["tags"] == ["ai", "test"]
        assert loaded["metadata"]["category"] == "demo"

    def test_get_all_products(self, sqlite_manager):
        """get_all_products returns all inserted products."""
        for i in range(3):
            sqlite_manager.upsert_product({
                "id": f"prod-{i}",
                "idea": f"Idea {i}",
                "state": "idea_received",
                "created_at": float(i),
                "updated_at": float(i),
                "metadata": {},
            })
        all_prods = sqlite_manager.get_all_products()
        assert len(all_prods) == 3

    def test_delete_product_cascades(self, sqlite_manager):
        """Deleting a product removes its tasks too."""
        sqlite_manager.upsert_product({
            "id": "prod-del",
            "idea": "Delete me",
            "state": "idea_received",
            "created_at": 1.0,
            "updated_at": 1.0,
            "metadata": {},
        })
        sqlite_manager.upsert_task({
            "id": "task-del",
            "product_id": "prod-del",
            "agent_type": "analyst",
            "status": "PENDING",
            "created_at": 1.0,
            "output_data": {},
        })
        sqlite_manager.delete_product("prod-del")
        assert sqlite_manager.get_product("prod-del") is None
        assert sqlite_manager.get_task("task-del") is None

    def test_upsert_and_get_task(self, sqlite_manager):
        """Insert a task and retrieve it."""
        sqlite_manager.upsert_product({
            "id": "prod-task-test",
            "idea": "Task test",
            "state": "idea_received",
            "created_at": 1.0,
            "updated_at": 1.0,
            "metadata": {},
        })
        task_dict = {
            "id": "task-1",
            "product_id": "prod-task-test",
            "agent_type": "analyst",
            "status": "PENDING",
            "created_at": 1000.0,
            "started_at": None,
            "completed_at": None,
            "output_data": {"result": "analysis_complete"},
            "error": None,
            "priority": 5,
        }
        sqlite_manager.upsert_task(task_dict)
        loaded = sqlite_manager.get_task("task-1")
        assert loaded is not None
        assert loaded["id"] == "task-1"
        assert loaded["output_data"] == {"result": "analysis_complete"}
        assert loaded["agent_type"] == "analyst"

    def test_get_tasks_by_product(self, sqlite_manager):
        """Tasks can be retrieved by product_id."""
        sqlite_manager.upsert_product({
            "id": "prod-tasks",
            "idea": "Tasks",
            "state": "idea_received",
            "created_at": 1.0,
            "updated_at": 1.0,
            "metadata": {},
        })
        for i in range(3):
            sqlite_manager.upsert_task({
                "id": f"t-{i}",
                "product_id": "prod-tasks",
                "agent_type": "analyst",
                "status": "PENDING",
                "created_at": float(i),
                "output_data": {},
            })
        tasks = sqlite_manager.get_tasks_by_product("prod-tasks")
        assert len(tasks) == 3

    def test_get_all_tasks(self, sqlite_manager):
        """get_all_tasks returns all tasks."""
        for i in range(2):
            pid = f"prod-all-tasks-{i}"
            sqlite_manager.upsert_product({
                "id": pid,
                "idea": f"Prod {i}",
                "state": "idea_received",
                "created_at": 1.0,
                "updated_at": 1.0,
                "metadata": {},
            })
            sqlite_manager.upsert_task({
                "id": f"task-all-{i}",
                "product_id": pid,
                "agent_type": "analyst",
                "status": "PENDING",
                "created_at": float(i),
                "output_data": {},
            })
        all_tasks = sqlite_manager.get_all_tasks()
        assert len(all_tasks) == 2

    def test_get_pending_tasks(self, sqlite_manager):
        """get_pending_tasks returns only PENDING tasks."""
        sqlite_manager.upsert_product({
            "id": "prod-pending",
            "idea": "Pending",
            "state": "idea_received",
            "created_at": 1.0,
            "updated_at": 1.0,
            "metadata": {},
        })
        sqlite_manager.upsert_task({
            "id": "pending-1",
            "product_id": "prod-pending",
            "agent_type": "analyst",
            "status": "PENDING",
            "created_at": 1.0,
            "output_data": {},
            "priority": 1,
        })
        sqlite_manager.upsert_task({
            "id": "running-1",
            "product_id": "prod-pending",
            "agent_type": "pm",
            "status": "RUNNING",
            "created_at": 2.0,
            "output_data": {},
            "priority": 2,
        })
        pending = sqlite_manager.get_pending_tasks()
        assert len(pending) == 1
        assert pending[0]["id"] == "pending-1"

    def test_delete_task(self, sqlite_manager):
        """Deleting a task removes it."""
        sqlite_manager.upsert_product({
            "id": "prod-del-task",
            "idea": "Del task",
            "state": "idea_received",
            "created_at": 1.0,
            "updated_at": 1.0,
            "metadata": {},
        })
        sqlite_manager.upsert_task({
            "id": "task-to-delete",
            "product_id": "prod-del-task",
            "agent_type": "analyst",
            "status": "PENDING",
            "created_at": 1.0,
            "output_data": {},
        })
        sqlite_manager.delete_task("task-to-delete")
        assert sqlite_manager.get_task("task-to-delete") is None

    def test_get_metrics(self, sqlite_manager):
        """get_metrics returns aggregate statistics."""
        # Insert one completed product and one active
        sqlite_manager.upsert_product({
            "id": "p-completed",
            "idea": "Completed",
            "state": "completed",
            "created_at": 1000.0,
            "updated_at": 4600.0,
            "metadata": {},
        })
        sqlite_manager.upsert_product({
            "id": "p-active",
            "idea": "Active",
            "state": "idea_received",
            "created_at": 2000.0,
            "updated_at": 2000.0,
            "metadata": {},
        })
        metrics = sqlite_manager.get_metrics()
        assert metrics["total_products"] == 2
        assert metrics["completed_products"] == 1
        assert metrics["active_products"] == 1
        # p-completed: 4600 - 1000 = 3600 sec = 1 hour
        assert metrics["avg_completion_time_hours"] == pytest.approx(1.0, rel=0.01)

    def test_clear_all(self, sqlite_manager):
        """clear_all removes all data."""
        sqlite_manager.upsert_product({
            "id": "p-clear",
            "idea": "Clear",
            "state": "idea_received",
            "created_at": 1.0,
            "updated_at": 1.0,
            "metadata": {},
        })
        sqlite_manager.clear_all()
        assert len(sqlite_manager.get_all_products()) == 0
        assert len(sqlite_manager.get_all_tasks()) == 0


# ============================================================================
# PipelineStateMachine with SQLite — Product Lifecycle
# ============================================================================


class TestSQLiteCreateProduct:
    """Product creation lifecycle with SQLite backend."""

    def test_creates_with_generated_id(self, sqlite_state_machine, sample_product_idea):
        product = sqlite_state_machine.create_product(sample_product_idea)
        assert product.id is not None
        assert product.id.startswith("prod-")
        assert product.state == PipelineState.IDEA_RECEIVED

    def test_creates_with_custom_id(self, sqlite_state_machine, sample_product_idea):
        product = sqlite_state_machine.create_product(
            sample_product_idea, product_id="sqlite-custom-id"
        )
        assert product.id == "sqlite-custom-id"

    def test_product_persisted_to_sqlite(self, sqlite_state_machine, sample_product_idea):
        """After creation, the product is persisted in SQLite."""
        product = sqlite_state_machine.create_product(sample_product_idea)
        # Verify via the underlying manager
        loaded = sqlite_state_machine.sqlite_manager.get_product(product.id)
        assert loaded is not None
        assert loaded["idea"] == sample_product_idea

    def test_unique_ids(self, sqlite_state_machine, sample_product_idea):
        p1 = sqlite_state_machine.create_product(sample_product_idea)
        p2 = sqlite_state_machine.create_product(sample_product_idea)
        assert p1.id != p2.id


# ============================================================================
# PipelineStateMachine with SQLite — Task Queue
# ============================================================================


class TestSQLiteTaskQueue:
    """Task queue operations with SQLite backend."""

    def test_get_next_task_returns_pending(self, sqlite_state_machine, sample_product_idea):
        product = sqlite_state_machine.create_product(sample_product_idea)
        t1 = Task(id="st1", product_id=product.id, agent_type="analyst",
                  state=PipelineState.MARKET_RESEARCHED, priority=1, created_at=100.0)
        t2 = Task(id="st2", product_id=product.id, agent_type="pm",
                  state=PipelineState.SPEC_WRITTEN, priority=2, created_at=101.0)
        sqlite_state_machine.add_task_to_queue(t1)
        sqlite_state_machine.add_task_to_queue(t2)

        task = sqlite_state_machine.get_next_task()
        assert task is not None
        assert task.id == "st1"
        assert task.status == TaskStatus.RUNNING

    def test_get_next_task_empty_queue(self, sqlite_state_machine):
        assert sqlite_state_machine.get_next_task() is None


# ============================================================================
# PipelineStateMachine with SQLite — Complete/Fail Tasks
# ============================================================================


class TestSQLiteCompleteTask:
    """Task completion with SQLite backend."""

    def test_complete_task_basic(self, sqlite_state_machine, sqlite_product_with_task):
        product, task = sqlite_product_with_task
        output = {"result": "sqlite_analysis_complete"}
        result = sqlite_state_machine.complete_task(task.id, output)
        assert result is True

        completed = sqlite_state_machine._find_task(task.id)
        assert completed.status == TaskStatus.COMPLETED
        assert completed.output_data == output

    def test_complete_task_advances_product_state(self, sqlite_state_machine, sqlite_product_with_task):
        product, task = sqlite_product_with_task
        sqlite_state_machine.complete_task(task.id, {})
        refreshed = sqlite_state_machine.get_product(product.id)
        assert refreshed.state == PipelineState.MARKET_RESEARCHED

    def test_complete_task_creates_next_task(self, sqlite_state_machine, sqlite_product_with_task):
        product, task = sqlite_product_with_task
        sqlite_state_machine.complete_task(task.id, {})
        next_task = sqlite_state_machine.get_next_task()
        assert next_task is not None
        assert next_task.agent_type == "pm"
        assert next_task.state == PipelineState.SPEC_WRITTEN

    def test_complete_full_pipeline(self, sqlite_state_machine, sample_product_idea, monkeypatch):
        """Walk through the entire pipeline with SQLite backend."""
        monkeypatch.setenv("AIFACTORY_HUMAN_REVIEW_REQUIRED", "0")
        product = sqlite_state_machine.create_product(sample_product_idea)

        expected_flow = [
            ("analyst", PipelineState.MARKET_RESEARCHED),
            ("pm", PipelineState.SPEC_WRITTEN),
            ("marketing", PipelineState.MARKET_CONTENT_READY),
            ("methodologist", PipelineState.METHODOLOGY_REVIEWED),
            ("architect", PipelineState.ARCH_DESIGNED),
            ("developer", PipelineState.CODE_COMMITTED),
            ("qa", PipelineState.QA_TESTING),
            ("security", PipelineState.SECURITY_SCANNED),
            ("devops", PipelineState.SALES_ACTIVE),
            ("sales", PipelineState.SANDBOX_RUNNING),
            ("devops", PipelineState.TELEMETRY_COLLECTING),
            ("analyst", PipelineState.EVOLUTION_ANALYZING),
        ]

        first_task = Task(
            id="st0", product_id=product.id, agent_type="analyst",
            state=PipelineState.MARKET_RESEARCHED, created_at=time.time(), priority=1,
        )
        sqlite_state_machine.add_task_to_queue(first_task)

        for idx, (expected_agent, expected_state) in enumerate(expected_flow):
            task = sqlite_state_machine.get_next_task()
            assert task is not None, f"No task at step {idx}"
            assert task.agent_type == expected_agent

            result = sqlite_state_machine.complete_task(task.id, {"result": f"{expected_agent}_done"})
            assert result is True

            if expected_state == PipelineState.EVOLUTION_ANALYZING:
                product = sqlite_state_machine.get_product(product.id)
                assert product.state == PipelineState.COMPLETED

        final = sqlite_state_machine.get_product(product.id)
        assert final.state == PipelineState.COMPLETED


class TestSQLiteFailTask:
    """Task failure and retry with SQLite backend."""

    def test_fail_task_retries(self, sqlite_state_machine, sqlite_product_with_task):
        product, task = sqlite_product_with_task
        result = sqlite_state_machine.fail_task(task.id, "SQLite error")
        assert result is True
        failed = sqlite_state_machine._find_task(task.id)
        assert failed.retry_count == 1
        assert failed.status == TaskStatus.PENDING

    def test_fail_task_max_retries_exceeded(self, sqlite_state_machine, sqlite_product_with_task):
        product, task = sqlite_product_with_task
        task.max_retries = 1
        sqlite_state_machine.fail_task(task.id, "Fatal SQLite error")
        failed = sqlite_state_machine._find_task(task.id)
        assert failed.status == TaskStatus.FAILED
        product = sqlite_state_machine.get_product(product.id)
        assert product.state == PipelineState.FAILED

    async def test_retry_keeps_task_pending(self, sqlite_state_machine):
        """Test that incrementing retry_count keeps task in PENDING state."""
        sm = sqlite_state_machine
        product = sm.create_product("Test retry product")
        task = sm.get_next_task()
        assert task is not None

        # Simulate retry: increment retry_count, reset to PENDING
        task.retry_count = 1
        task.status = TaskStatus.PENDING
        task.error = None
        task.started_at = None
        sm._save_state()

        # Verify task is still findable as PENDING
        next_task = sm.get_next_task()
        assert next_task is not None
        assert next_task.id == task.id
        assert next_task.retry_count == 1


# ============================================================================
# PipelineStateMachine with SQLite — Persistence (Load/Save)
# ============================================================================


class TestSQLitePersistence:
    """Verify state survives save/load cycle with SQLite."""

    def test_save_and_reload(self, tmp_path, sample_product_idea):
        """Products and tasks survive a SQLite roundtrip."""
        db_path = str(tmp_path / "state" / "pipeline.db")
        sm1 = PipelineStateMachine(
            state_file=str(tmp_path / "state" / "pipeline.json"),
            use_sqlite=True,
            db_path=db_path,
        )
        sm1.products = {}
        sm1.task_queue = []

        product = sm1.create_product(sample_product_idea)
        task = Task(id="sqlite-persist", product_id=product.id, agent_type="analyst",
                    state=PipelineState.MARKET_RESEARCHED)
        sm1.add_task_to_queue(task)

        # Create a new machine pointing at the same DB
        sm2 = PipelineStateMachine(
            state_file=str(tmp_path / "state" / "pipeline.json"),
            use_sqlite=True,
            db_path=db_path,
        )
        loaded_product = sm2.get_product(product.id)
        assert loaded_product is not None
        assert loaded_product.idea == sample_product_idea
        assert loaded_product.state == PipelineState.IDEA_RECEIVED

        loaded_task = sm2._find_task("sqlite-persist")
        assert loaded_task is not None
        assert loaded_task.agent_type == "analyst"

    def test_roundtrip_full_state(self, tmp_path):
        """Complex state with multiple products and tasks roundtrips via SQLite."""
        db_path = str(tmp_path / "state" / "pipeline.db")
        sm1 = PipelineStateMachine(
            state_file=str(tmp_path / "state" / "pipeline.json"),
            use_sqlite=True,
            db_path=db_path,
        )
        sm1.products = {}
        sm1.task_queue = []

        p1 = sm1.create_product("idea1", product_id="sp1")
        p2 = sm1.create_product("idea2", product_id="sp2")

        sm1.add_task_to_queue(Task(
            id="st1", product_id="sp1", agent_type="analyst",
            state=PipelineState.MARKET_RESEARCHED, priority=1,
        ))
        sm1.add_task_to_queue(Task(
            id="st2", product_id="sp2", agent_type="pm",
            state=PipelineState.SPEC_WRITTEN, priority=2,
        ))

        sm2 = PipelineStateMachine(
            state_file=str(tmp_path / "state" / "pipeline.json"),
            use_sqlite=True,
            db_path=db_path,
        )
        assert len(sm2.get_all_products()) == 2
        assert sm2.get_product("sp1").idea == "idea1"
        assert sm2._find_task("st1") is not None
        assert sm2._find_task("st2") is not None


# ============================================================================
# Migration Tests
# ============================================================================


class TestMigration:
    """Test JSON → SQLite migration."""

    def test_migrate_empty_json(self, tmp_path):
        """Migration with an empty JSON file results in zero counts."""
        json_path = tmp_path / "state" / "pipeline.json"
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps({"products": {}, "task_queue": []}))

        db_path = str(tmp_path / "state" / "migrated.db")
        result = migrate_json_to_sqlite(str(json_path), db_path)
        assert result["products_migrated"] == 0
        assert result["tasks_migrated"] == 0

    def test_migrate_with_data(self, tmp_path, sample_product_idea):
        """Migration transfers products and tasks correctly."""
        # First, create a state machine with JSON and add data
        json_path = tmp_path / "state" / "pipeline.json"
        json_path.parent.mkdir(parents=True, exist_ok=True)
        sm = PipelineStateMachine(str(json_path))
        sm.products = {}
        sm.task_queue = []

        product = sm.create_product(sample_product_idea, product_id="migrate-test-prod")
        task = Task(
            id="migrate-task",
            product_id=product.id,
            agent_type="analyst",
            state=PipelineState.MARKET_RESEARCHED,
        )
        sm.add_task_to_queue(task)
        sm._save_state()  # Ensure JSON is written

        # Now migrate
        db_path = str(tmp_path / "state" / "migrated.db")
        result = migrate_json_to_sqlite(str(json_path), db_path)
        assert result["products_migrated"] == 1
        assert result["tasks_migrated"] == 1

        # Verify data in SQLite
        mgr = SQLiteManager(db_path)
        mgr.connect()
        loaded_product = mgr.get_product("migrate-test-prod")
        assert loaded_product is not None
        assert loaded_product["idea"] == sample_product_idea

        loaded_task = mgr.get_task("migrate-task")
        assert loaded_task is not None
        assert loaded_task["agent_type"] == "analyst"
        mgr.close()

    def test_migrate_merge_preserves_sqlite_when_json_is_stale(self, tmp_path):
        """Repeated JSON→SQLite sync must not regress completed tasks to stale JSON."""
        json_path = tmp_path / "state" / "pipeline.json"
        json_path.parent.mkdir(parents=True, exist_ok=True)
        db_path = str(tmp_path / "state" / "merge.db")

        product_j = {
            "id": "p-merge",
            "idea": "idea",
            "state": "idea_received",
            "tasks": [],
            "created_at": 1.0,
            "updated_at": 2.0,
            "metadata": {},
        }
        task_completed = {
            "id": "t-merge",
            "product_id": "p-merge",
            "agent_type": "analyst",
            "state": "idea_received",
            "status": "completed",
            "input_data": {},
            "output_data": {"ok": True},
            "created_at": 10.0,
            "started_at": 11.0,
            "completed_at": 100.0,
        }
        data_ok = {"products": {"p-merge": product_j}, "task_queue": [task_completed]}
        json_path.write_text(json.dumps(data_ok))
        migrate_json_to_sqlite(str(json_path), db_path)

        mgr = SQLiteManager(db_path)
        mgr.connect()
        assert mgr.get_task("t-merge")["status"] == "completed"
        mgr.close()

        task_running = {**task_completed, "status": "running", "completed_at": None}
        json_path.write_text(
            json.dumps({"products": {"p-merge": product_j}, "task_queue": [task_running]})
        )
        migrate_json_to_sqlite(str(json_path), db_path)

        mgr2 = SQLiteManager(db_path)
        mgr2.connect()
        t = mgr2.get_task("t-merge")
        assert t["status"] == "completed"
        assert t["completed_at"] == 100.0
        assert t["output_data"].get("ok") is True
        mgr2.close()

    def test_migrate_via_state_machine_method(self, tmp_path, sample_product_idea):
        """PipelineStateMachine.migrate_json_to_sqlite() works."""
        json_path = tmp_path / "state" / "pipeline.json"
        json_path.parent.mkdir(parents=True, exist_ok=True)
        sm = PipelineStateMachine(str(json_path))
        sm.products = {}
        sm.task_queue = []

        product = sm.create_product(sample_product_idea, product_id="sm-migrate-prod")
        sm.create_product("Another idea", product_id="sm-migrate-prod-2")
        task = Task(
            id="sm-migrate-task",
            product_id=product.id,
            agent_type="analyst",
            state=PipelineState.MARKET_RESEARCHED,
        )
        sm.add_task_to_queue(task)
        sm._save_state()

        db_path = str(tmp_path / "state" / "sm_migrated.db")
        result = sm.migrate_json_to_sqlite(db_path)
        assert result["products_migrated"] == 2
        assert result["tasks_migrated"] == 1

    def test_migrate_file_not_found(self, tmp_path):
        """Migration raises FileNotFoundError when JSON is missing."""
        from orchestrator.migrate import migrate
        with pytest.raises(FileNotFoundError):
            migrate(
                str(tmp_path / "nonexistent.json"),
                str(tmp_path / "state" / "output.db"),
            )


# ============================================================================
# SQLite Pipeline Metrics
# ============================================================================


class TestSQLiteMetrics:
    """Pipeline metrics computed from SQLite."""

    def test_metrics_via_manager(self, sqlite_state_machine, sample_product_idea):
        """SQLiteManager.get_metrics returns correct values after state machine ops."""
        sqlite_state_machine.create_product(sample_product_idea)
        metrics = sqlite_state_machine.sqlite_manager.get_metrics()
        assert metrics["total_products"] >= 1

    def test_get_pipeline_metrics(self, sqlite_state_machine, sample_product_idea):
        """get_pipeline_metrics works with SQLite backend."""
        sqlite_state_machine.create_product("p1")
        sqlite_state_machine.create_product("p2")
        metrics = sqlite_state_machine.get_pipeline_metrics()
        assert metrics["total_products"] == 2
        assert metrics["active_products"] == 2

    def test_get_metrics(self, sqlite_state_machine, sample_product_idea):
        """get_metrics returns state distribution with SQLite."""
        sqlite_state_machine.create_product(sample_product_idea, product_id="sqlite-p1")
        p2 = sqlite_state_machine.create_product("other", product_id="sqlite-p2")
        p2.state = PipelineState.COMPLETED

        metrics = sqlite_state_machine.get_metrics()
        assert metrics["total_products"] == 2
        assert metrics["active_products"] == 1


# ============================================================================
# Edge Cases with SQLite
# ============================================================================


class TestSQLiteEdgeCases:
    """Edge cases with SQLite backend."""

    def test_create_product_with_duplicate_id(self, sqlite_state_machine):
        p1 = sqlite_state_machine.create_product("first", product_id="sqlite-dup")
        p2 = sqlite_state_machine.create_product("second", product_id="sqlite-dup")
        assert sqlite_state_machine.get_product("sqlite-dup").idea == "second"

    def test_task_not_found(self, sqlite_state_machine):
        assert sqlite_state_machine.complete_task("no-such-sqlite-task", {}) is False
        assert sqlite_state_machine.fail_task("no-such-sqlite-task", "err") is False

    def test_timeout_task(self, sqlite_state_machine, sqlite_product_with_task):
        product, task = sqlite_product_with_task
        result = sqlite_state_machine.timeout_task(task.id)
        assert result is True
        timed_out = sqlite_state_machine._find_task(task.id)
        assert timed_out.error == "Task timed out"

    def test_concurrent_products(self, sqlite_state_machine, sample_product_idea):
        """Multiple products can coexist with independent tasks (SQLite)."""
        products = []
        for i in range(5):
            p = sqlite_state_machine.create_product(f"Idea {i}", product_id=f"sp{i}")
            products.append(p)
            t = Task(id=f"st{i}", product_id=f"sp{i}", agent_type="analyst",
                     state=PipelineState.MARKET_RESEARCHED, priority=1, created_at=float(i))
            sqlite_state_machine.add_task_to_queue(t)

        for i in range(5):
            task = sqlite_state_machine.get_next_task()
            assert task is not None
            sqlite_state_machine.complete_task(task.id, {})

        for p in products:
            assert sqlite_state_machine.get_product(p.id).state == PipelineState.MARKET_RESEARCHED

    def test_sqlite_manager_lazy_connect(self, tmp_path):
        """SQLiteManager auto-connects on first use via the conn property."""
        db_path = str(tmp_path / "lazy.db")
        mgr = SQLiteManager(db_path)
        assert mgr._conn is None  # Not connected yet
        # Trigger connection via property
        conn = mgr.conn
        assert conn is not None
        mgr.close()

    def test_bulk_insert(self, sqlite_manager):
        """Bulk insert methods work correctly."""
        products = [
            {
                "id": f"bulk-{i}",
                "idea": f"Bulk idea {i}",
                "state": "idea_received",
                "created_at": float(i),
                "updated_at": float(i),
                "metadata": {},
            }
            for i in range(5)
        ]
        count = sqlite_manager.bulk_insert_products(products)
        assert count == 5
        assert len(sqlite_manager.get_all_products()) == 5

    def test_json_backend_still_works(self, tmp_path, sample_product_idea):
        """Ensure the original JSON-only path is unaffected."""
        sm = PipelineStateMachine(str(tmp_path / "state" / "pipeline.json"))
        sm.products = {}
        sm.task_queue = []
        product = sm.create_product(sample_product_idea)
        assert product.state == PipelineState.IDEA_RECEIVED
        # No SQLite file should exist
        assert not os.path.exists(str(tmp_path / "state" / "pipeline.db"))
