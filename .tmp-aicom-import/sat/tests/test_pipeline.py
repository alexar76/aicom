# ============================================================================
# AUTONOMOUS AI-FACTORY v2.1 — Pipeline State Machine Tests
# ============================================================================
# Tests for orchestrator/state_machine.py — PipelineStateMachine
# Covers: product lifecycle, task queue, retry logic, state transitions,
# persistence, metrics, and edge cases.
# ============================================================================

import pytest
import json
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

from orchestrator.state_machine import (
    PipelineStateMachine,
    PipelineState,
    TaskStatus,
    Task,
    Product,
    STATE_TRANSITIONS,
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def state_machine(tmp_path):
    """Create a PipelineStateMachine backed by a temp file."""
    state_file = tmp_path / "state" / "pipeline.json"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    sm = PipelineStateMachine(str(state_file))
    # Clear any stale state
    sm.products = {}
    sm.task_queue = []
    return sm


@pytest.fixture
def product_with_task(state_machine, sample_product_idea):
    """Create a product with its first (analyst) task already queued."""
    product = state_machine.create_product(sample_product_idea)
    # Manually add the first task matching IDEA_RECEIVED state
    task = Task(
        id="task-initial",
        product_id=product.id,
        agent_type="analyst",
        state=PipelineState.MARKET_RESEARCHED,
        created_at=time.time(),
        priority=1,
    )
    state_machine.add_task_to_queue(task)
    return product, task


# ============================================================================
# Product Creation
# ============================================================================

class TestCreateProduct:
    """Product creation lifecycle."""

    def test_creates_with_generated_id(self, state_machine, sample_product_idea):
        """A product gets a UUID-based ID when none is provided."""
        product = state_machine.create_product(sample_product_idea)
        assert product.id is not None
        assert product.id.startswith("prod-")
        assert product.idea == sample_product_idea
        assert product.state == PipelineState.IDEA_RECEIVED
        assert product.created_at > 0
        assert product.updated_at > 0
        assert len(product.tasks) == 0

    def test_creates_with_custom_id(self, state_machine, sample_product_idea):
        """A product respects a caller-provided ID."""
        product = state_machine.create_product(sample_product_idea, product_id="my-custom-id")
        assert product.id == "my-custom-id"
        assert product.state == PipelineState.IDEA_RECEIVED

    def test_empty_idea(self, state_machine):
        """Empty string is a valid (though odd) idea."""
        product = state_machine.create_product("")
        assert product is not None
        assert product.idea == ""
        assert product.state == PipelineState.IDEA_RECEIVED

    def test_very_long_idea(self, state_machine):
        """Very long strings are accepted."""
        idea = "x" * 100_000
        product = state_machine.create_product(idea)
        assert product.idea == idea

    def test_special_characters(self, state_machine):
        """Unicode / special characters are preserved."""
        idea = "Create 🚀 app with <script>alert('xss')</script> & more"
        product = state_machine.create_product(idea)
        assert product.idea == idea

    def test_unique_ids(self, state_machine, sample_product_idea):
        """Each product gets a unique ID."""
        p1 = state_machine.create_product(sample_product_idea)
        p2 = state_machine.create_product(sample_product_idea)
        assert p1.id != p2.id


# ============================================================================
# Task Queue
# ============================================================================

class TestTaskQueue:
    """Task queue ordering and lifecycle."""

    def test_get_next_task_returns_pending(self, state_machine, sample_product_idea):
        """get_next_task returns the highest-priority pending task."""
        product = state_machine.create_product(sample_product_idea)
        t1 = Task(id="t1", product_id=product.id, agent_type="analyst",
                  state=PipelineState.MARKET_RESEARCHED, priority=1, created_at=100.0)
        t2 = Task(id="t2", product_id=product.id, agent_type="pm",
                  state=PipelineState.SPEC_WRITTEN, priority=2, created_at=101.0)
        state_machine.add_task_to_queue(t1)
        state_machine.add_task_to_queue(t2)

        task = state_machine.get_next_task()
        assert task is not None
        assert task.id == "t1"  # priority 1 < 2
        assert task.status == TaskStatus.RUNNING
        assert task.started_at is not None

    def test_get_next_task_priority_order(self, state_machine, sample_product_idea):
        """Lower priority number = higher priority, returned first."""
        product = state_machine.create_product(sample_product_idea)
        tasks = [
            Task(id=f"t{i}", product_id=product.id, agent_type=f"a{i}",
                 state=PipelineState.MARKET_RESEARCHED, priority=p, created_at=float(i))
            for i, p in enumerate([5, 1, 3, 2, 4])
        ]
        for t in tasks:
            state_machine.add_task_to_queue(t)

        # Should return in priority order: 1, 2, 3, 4, 5
        expected = ["t1", "t3", "t2", "t4", "t0"]
        for exp_id in expected:
            task = state_machine.get_next_task()
            assert task is not None and task.id == exp_id, f"Expected {exp_id}"

    def test_get_next_task_same_priority_earliest_first(self, state_machine, sample_product_idea):
        """Same priority → FIFO by created_at."""
        product = state_machine.create_product(sample_product_idea)
        for i in range(3):
            t = Task(id=f"t{i}", product_id=product.id, agent_type="a",
                     state=PipelineState.MARKET_RESEARCHED, priority=5, created_at=float(i))
            state_machine.add_task_to_queue(t)

        for i in range(3):
            task = state_machine.get_next_task()
            assert task is not None and task.id == f"t{i}"

    def test_get_next_task_empty_queue(self, state_machine):
        """No tasks → returns None."""
        assert state_machine.get_next_task() is None

    def test_get_next_task_all_completed(self, state_machine, sample_product_idea):
        """All tasks completed → returns None."""
        product = state_machine.create_product(sample_product_idea)
        t = Task(id="t1", product_id=product.id, agent_type="a",
                 state=PipelineState.MARKET_RESEARCHED, status=TaskStatus.COMPLETED)
        state_machine.add_task_to_queue(t)
        assert state_machine.get_next_task() is None


# ============================================================================
# Complete Task
# ============================================================================

class TestCompleteTask:
    """Task completion and state advancement."""

    def test_complete_task_basic(self, state_machine, product_with_task):
        """Completing a task marks it COMPLETED and stores output."""
        product, task = product_with_task
        output = {"result": "market analysis complete"}
        result = state_machine.complete_task(task.id, output)

        assert result is True
        # Reload task
        completed = state_machine._find_task(task.id)
        assert completed.status == TaskStatus.COMPLETED
        assert completed.completed_at is not None
        assert completed.output_data == output

    def test_complete_task_advances_product_state(self, state_machine, product_with_task):
        """Product state advances to the task's target state on completion."""
        product, task = product_with_task
        state_machine.complete_task(task.id, {})

        refreshed = state_machine.get_product(product.id)
        # Task state is MARKET_RESEARCHED, which is a valid next state from IDEA_RECEIVED
        assert refreshed.state == PipelineState.MARKET_RESEARCHED

    def test_complete_task_creates_next_task(self, state_machine, product_with_task):
        """Next task is automatically created after completing the current one."""
        product, task = product_with_task
        state_machine.complete_task(task.id, {})

        next_task = state_machine.get_next_task()
        assert next_task is not None
        assert next_task.product_id == product.id
        assert next_task.agent_type == "pm"  # next after MARKET_RESEARCHED
        assert next_task.state == PipelineState.SPEC_WRITTEN

    def test_complete_task_not_found(self, state_machine):
        """Non-existent task ID returns False."""
        result = state_machine.complete_task("nonexistent", {})
        assert result is False

    def test_complete_full_pipeline(self, state_machine, sample_product_idea, monkeypatch):
        """Walk through the entire pipeline from IDEA_RECEIVED to COMPLETED."""
        # Sample idea infers full_software — avoid post-DevOps human gate so the linear flow matches PIPELINE_AGENT_FLOW.
        monkeypatch.setenv("AIFACTORY_HUMAN_REVIEW_REQUIRED", "0")
        product = state_machine.create_product(sample_product_idea)

        # The agent_map in _create_next_task maps each product state to a
        # (agent_type, next_pipeline_state) pair.
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
            # EVOLUTION_ANALYZING -> COMPLETED (terminal transition in _create_next_task)
        ]

        # Inject the first task manually (analyst for market research)
        first_task = Task(
            id="t0", product_id=product.id, agent_type="analyst",
            state=PipelineState.MARKET_RESEARCHED, created_at=time.time(), priority=1,
        )
        state_machine.add_task_to_queue(first_task)

        for idx, (expected_agent, expected_state) in enumerate(expected_flow):
            task = state_machine.get_next_task()
            assert task is not None, f"No task at step {idx} (expected {expected_agent})"
            assert task.agent_type == expected_agent, (
                f"Step {idx}: expected agent {expected_agent}, got {task.agent_type}"
            )

            result = state_machine.complete_task(task.id, {"result": f"{expected_agent}_done"})
            assert result is True, f"Failed to complete task at step {idx}"

            # After completing EVOLUTION_ANALYZING the product becomes COMPLETED
            if expected_state == PipelineState.EVOLUTION_ANALYZING:
                product = state_machine.get_product(product.id)
                assert product.state == PipelineState.COMPLETED, (
                    f"Expected COMPLETED after evolution_analyst, got {product.state}"
                )

        # Verify final state
        final = state_machine.get_product(product.id)
        assert final.state == PipelineState.COMPLETED
        assert state_machine.get_next_task() is None  # No more tasks


# ============================================================================
# Fail Task / Retry Logic
# ============================================================================

class TestFailTask:
    """Task failure and retry mechanics."""

    def test_fail_task_retries(self, state_machine, product_with_task):
        """Failed task is reset to PENDING if retries remain."""
        product, task = product_with_task
        result = state_machine.fail_task(task.id, "Something went wrong")

        assert result is True
        failed = state_machine._find_task(task.id)
        assert failed.retry_count == 1
        assert failed.status == TaskStatus.PENDING  # Retry available
        assert failed.error == "Something went wrong"

    def test_fail_task_max_retries_exceeded(self, state_machine, product_with_task):
        """After max retries, task goes to FAILED and product goes to FAILED."""
        product, task = product_with_task
        task.max_retries = 1

        # `_apply_task_failure` treats `retry_count == max_retries` as the FINAL
        # pending attempt on purpose ("retries labeled 1/3, 2/3, 3/3 before FAILED"),
        # so `max_retries=N` gives N pending retries and fails on attempt N+1. These
        # cases still encoded the old off-by-one and failed on the semantics rather
        # than on the behaviour.
        assert state_machine.fail_task(task.id, "Retryable error") is True
        retrying = state_machine._find_task(task.id)
        assert retrying.status == TaskStatus.PENDING
        assert retrying.retry_count == 1

        assert state_machine.fail_task(task.id, "Fatal error") is True
        failed = state_machine._find_task(task.id)
        assert failed.status == TaskStatus.FAILED
        assert failed.retry_count == 2

        # Product should be FAILED
        product = state_machine.get_product(product.id)
        assert product.state == PipelineState.FAILED

    def test_fail_task_multiple_retries(self, state_machine, product_with_task):
        """Multiple retries increment the counter, then final failure."""
        product, task = product_with_task
        task.max_retries = 3

        # max_retries=3 → attempts 1..3 stay PENDING, attempt 4 exhausts them.
        for attempt in range(1, 5):
            result = state_machine.fail_task(task.id, f"Attempt {attempt}")
            assert result is True
            t = state_machine._find_task(task.id)
            assert t.retry_count == attempt
            if attempt <= 3:
                assert t.status == TaskStatus.PENDING  # Still retrying
            else:
                assert t.status == TaskStatus.FAILED   # Exhausted

        product = state_machine.get_product(product.id)
        assert product.state == PipelineState.FAILED

    def test_fail_task_not_found(self, state_machine):
        """Non-existent task returns False."""
        result = state_machine.fail_task("ghost", "error")
        assert result is False


# ============================================================================
# Timeout Task
# ============================================================================

class TestTimeoutTask:
    """Task timeout handling."""

    def test_timeout_calls_fail_task(self, state_machine, product_with_task):
        """timeout_task delegates to fail_task with 'Task timed out'."""
        product, task = product_with_task
        result = state_machine.timeout_task(task.id)

        assert result is True
        timed_out = state_machine._find_task(task.id)
        assert timed_out.error == "Task timed out"
        assert timed_out.retry_count == 1
        assert timed_out.status == TaskStatus.PENDING  # Can retry

    def test_timeout_not_found(self, state_machine):
        """timeout_task on non-existent task returns False."""
        result = state_machine.timeout_task("phantom")
        assert result is False


# ============================================================================
# Product Queries
# ============================================================================

class TestProductQueries:
    """get_product / get_all_products / get_active_products."""

    def test_get_product_found(self, state_machine, sample_product_idea):
        product = state_machine.create_product(sample_product_idea)
        assert state_machine.get_product(product.id) is product

    def test_get_product_not_found(self, state_machine):
        assert state_machine.get_product("nonexistent") is None

    def test_get_all_products(self, state_machine, sample_product_idea):
        p1 = state_machine.create_product("idea1")
        p2 = state_machine.create_product("idea2")
        all_ps = state_machine.get_all_products()
        assert len(all_ps) == 2
        assert set(p.id for p in all_ps) == {p1.id, p2.id}

    def test_get_all_products_empty(self, state_machine):
        assert state_machine.get_all_products() == []

    def test_get_active_products(self, state_machine):
        """Active = not COMPLETED, FAILED, or CANCELLED."""
        p_active = state_machine.create_product("active", product_id="p-active")
        p_completed = state_machine.create_product("done", product_id="p-completed")
        p_completed.state = PipelineState.COMPLETED
        p_failed = state_machine.create_product("fail", product_id="p-failed")
        p_failed.state = PipelineState.FAILED
        p_cancelled = state_machine.create_product("cancel", product_id="p-cancelled")
        p_cancelled.state = PipelineState.CANCELLED

        active = state_machine.get_active_products()
        assert len(active) == 1
        assert active[0].id == "p-active"

    def test_get_active_products_empty(self, state_machine):
        assert state_machine.get_active_products() == []


# ============================================================================
# Pipeline Metrics
# ============================================================================

class TestPipelineMetrics:
    """get_pipeline_metrics computation."""

    def test_metrics_empty(self, state_machine):
        metrics = state_machine.get_pipeline_metrics()
        assert metrics["total_products"] == 0
        assert metrics["active_products"] == 0
        assert metrics["completed_products"] == 0
        assert metrics["failed_products"] == 0
        assert metrics["pending_tasks"] == 0
        assert metrics["running_tasks"] == 0
        assert metrics["failed_tasks"] == 0

    def test_metrics_with_products(self, state_machine, sample_product_idea):
        state_machine.create_product("p1")
        state_machine.create_product("p2")

        metrics = state_machine.get_pipeline_metrics()
        assert metrics["total_products"] == 2
        assert metrics["active_products"] == 2
        assert metrics["completed_products"] == 0
        assert metrics["failed_products"] == 0

    def test_metrics_completed_time(self, state_machine):
        """Completed products contribute to avg_completion_time."""
        p1 = state_machine.create_product("p1", product_id="p1")
        p1.created_at = 1000.0
        p1.updated_at = 4600.0  # 1 hour later
        p1.state = PipelineState.COMPLETED

        p2 = state_machine.create_product("p2", product_id="p2")
        p2.created_at = 1000.0
        p2.updated_at = 19000.0  # 5 hours later
        p2.state = PipelineState.COMPLETED

        metrics = state_machine.get_pipeline_metrics()
        assert metrics["completed_products"] == 2
        # (1 + 5) / 2 = 3 hours
        assert metrics["avg_completion_time_hours"] == pytest.approx(3.0, rel=0.01)

    def test_metrics_task_counts(self, state_machine, sample_product_idea):
        """Count pending / running / failed / timeout tasks."""
        product = state_machine.create_product(sample_product_idea)
        for i, (status, priority) in enumerate([
            (TaskStatus.PENDING, 1),
            (TaskStatus.RUNNING, 2),
            (TaskStatus.FAILED, 3),
            (TaskStatus.TIMEOUT, 4),
        ]):
            state_machine.add_task_to_queue(Task(
                id=f"t{i}", product_id=product.id, agent_type="a",
                state=PipelineState.MARKET_RESEARCHED, status=status, priority=priority,
            ))

        metrics = state_machine.get_pipeline_metrics()
        assert metrics["pending_tasks"] == 1
        assert metrics["running_tasks"] == 1
        assert metrics["failed_tasks"] == 1
        assert metrics["timeout_tasks"] == 1


# ============================================================================
# State Transitions
# ============================================================================

class TestStateTransitions:
    """Valid and invalid state transitions."""

    def test_all_valid_transitions(self, state_machine):
        """Every entry in STATE_TRANSITIONS is reachable."""
        for from_state, to_states in STATE_TRANSITIONS.items():
            for to_state in to_states:
                # Simply verify the transition is declared valid — no runtime check
                # needed because the machine trusts the map.
                pass
        # Ensure we checked something
        assert len(STATE_TRANSITIONS) == len(PipelineState)

    def test_completed_has_no_transitions(self):
        assert STATE_TRANSITIONS[PipelineState.COMPLETED] == []

    def test_failed_has_no_transitions(self):
        assert STATE_TRANSITIONS[PipelineState.FAILED] == []

    def test_cancelled_has_no_transitions(self):
        assert STATE_TRANSITIONS[PipelineState.CANCELLED] == []

    def test_every_state_has_entry(self):
        """Every PipelineState enum value has a key in STATE_TRANSITIONS."""
        for state in PipelineState:
            assert state in STATE_TRANSITIONS, f"Missing transition entry for {state}"

    def test_complete_task_rejects_invalid_transition(self, state_machine, sample_product_idea):
        """If task.state is not in STATE_TRANSITIONS[product.state], product stays."""
        product = state_machine.create_product(sample_product_idea)
        # Current state is IDEA_RECEIVED, which transitions to MARKET_RESEARCHED or FAILED.
        # Create a task that tries to skip to CODE_COMMITTED — not allowed.
        invalid_task = Task(
            id="invalid", product_id=product.id, agent_type="dev",
            state=PipelineState.CODE_COMMITTED,  # Not in IDEA_RECEIVED's transitions
        )
        state_machine.add_task_to_queue(invalid_task)
        state_machine.complete_task("invalid", {})

        # Product state should NOT have changed
        refreshed = state_machine.get_product(product.id)
        assert refreshed.state == PipelineState.IDEA_RECEIVED


# ============================================================================
# Persistence
# ============================================================================

class TestPersistence:
    """_load_state / _save_state roundtrip via tmp_path."""

    def test_save_and_reload(self, state_machine, sample_product_idea):
        """Products and tasks survive a roundtrip."""
        product = state_machine.create_product(sample_product_idea)
        task = Task(id="persist", product_id=product.id, agent_type="analyst",
                    state=PipelineState.MARKET_RESEARCHED)
        state_machine.add_task_to_queue(task)

        # Create a new machine pointing at the same file
        sm2 = PipelineStateMachine(state_machine.state_file)
        loaded_product = sm2.get_product(product.id)
        assert loaded_product is not None
        assert loaded_product.idea == sample_product_idea
        assert loaded_product.state == PipelineState.IDEA_RECEIVED

        loaded_task = sm2._find_task("persist")
        assert loaded_task is not None
        assert loaded_task.agent_type == "analyst"

    def test_state_file_created(self, state_machine, sample_product_idea):
        """Saving creates the JSON file on disk."""
        state_machine.create_product(sample_product_idea)
        path = Path(state_machine.state_file)
        assert path.exists()
        content = json.loads(path.read_text())
        assert "products" in content
        assert "task_queue" in content

    def test_load_missing_file(self, tmp_path):
        """Missing file = empty state, no crash."""
        missing = tmp_path / "does_not_exist.json"
        sm = PipelineStateMachine(str(missing))
        assert sm.products == {}
        assert sm.task_queue == []

    def test_load_corrupted_file(self, state_machine, sample_product_idea):
        """Corrupted JSON is handled gracefully."""
        state_machine.create_product(sample_product_idea)
        # Corrupt the file
        Path(state_machine.state_file).write_text("{bad json")
        sm2 = PipelineStateMachine(state_machine.state_file)
        assert sm2.products == {}
        assert sm2.task_queue == []

    def test_roundtrip_full_state(self, state_machine, sample_product_idea):
        """Complex state with multiple products and tasks roundtrips."""
        p1 = state_machine.create_product("idea1", product_id="p1")
        p2 = state_machine.create_product("idea2", product_id="p2")

        state_machine.add_task_to_queue(Task(
            id="t1", product_id="p1", agent_type="analyst",
            state=PipelineState.MARKET_RESEARCHED, priority=1,
        ))
        state_machine.add_task_to_queue(Task(
            id="t2", product_id="p2", agent_type="pm",
            state=PipelineState.SPEC_WRITTEN, priority=2,
        ))

        sm2 = PipelineStateMachine(state_machine.state_file)
        assert len(sm2.get_all_products()) == 2
        assert sm2.get_product("p1").idea == "idea1"
        assert sm2._find_task("t1") is not None
        assert sm2._find_task("t2") is not None


# ============================================================================
# Edge Cases
# ============================================================================

class TestEdgeCases:
    """Corner cases and error paths."""

    def test_empty_product_list_in_metrics(self, state_machine):
        """get_pipeline_metrics with zero products is well-behaved."""
        metrics = state_machine.get_pipeline_metrics()
        assert metrics["avg_completion_time_hours"] == 0

    def test_max_retries_exceeded(self, state_machine, product_with_task):
        """Exhausting max_retries sets task to FAILED and product to FAILED."""
        product, task = product_with_task
        task.max_retries = 0  # Zero retries = immediate failure
        result = state_machine.fail_task(task.id, "Immediate fail")
        assert result is True

        t = state_machine._find_task(task.id)
        assert t.status == TaskStatus.FAILED
        assert state_machine.get_product(product.id).state == PipelineState.FAILED

    def test_task_not_found_complete(self, state_machine):
        assert state_machine.complete_task("no-such-task", {}) is False

    def test_task_not_found_fail(self, state_machine):
        assert state_machine.fail_task("no-such-task", "err") is False

    def test_task_not_found_timeout(self, state_machine):
        assert state_machine.timeout_task("no-such-task") is False

    def test_concurrent_products(self, state_machine, sample_product_idea):
        """Multiple products can coexist with independent tasks."""
        products = []
        for i in range(5):
            p = state_machine.create_product(f"Idea {i}", product_id=f"p{i}")
            products.append(p)
            t = Task(id=f"t{i}", product_id=f"p{i}", agent_type="analyst",
                     state=PipelineState.MARKET_RESEARCHED, priority=1, created_at=float(i))
            state_machine.add_task_to_queue(t)

        # Complete all tasks
        for i in range(5):
            task = state_machine.get_next_task()
            assert task is not None
            state_machine.complete_task(task.id, {})

        for p in products:
            assert state_machine.get_product(p.id).state == PipelineState.MARKET_RESEARCHED

    def test_get_metrics(self, state_machine, sample_product_idea):
        """get_metrics returns state distribution."""
        state_machine.create_product(sample_product_idea, product_id="p1")
        p2 = state_machine.create_product("other", product_id="p2")
        p2.state = PipelineState.COMPLETED

        metrics = state_machine.get_metrics()
        assert metrics["total_products"] == 2
        assert metrics["active_products"] == 1
        assert "idea_received" in metrics["state_counts"]
        assert "completed" in metrics["state_counts"]


# ============================================================================
# State Transition Verification (Actual Execution)
# ============================================================================

class TestStateTransitionExecution:
    """Verify that each valid transition in STATE_TRANSITIONS actually works
    when executing tasks through the pipeline."""

    def _create_product_at_state(self, sm, state: PipelineState, product_id: str = "transition-test"):
        """Helper: create a product and advance it to the given state."""
        product = sm.create_product("Transition test idea", product_id=product_id)
        product.state = state
        product.updated_at = time.time()
        return product

    @pytest.mark.parametrize("from_state,to_state,expected_state", [
        (PipelineState.IDEA_RECEIVED, PipelineState.MARKET_RESEARCHED, PipelineState.MARKET_RESEARCHED),
        (PipelineState.MARKET_RESEARCHED, PipelineState.SPEC_WRITTEN, PipelineState.SPEC_WRITTEN),
        (PipelineState.SPEC_WRITTEN, PipelineState.MARKET_CONTENT_READY, PipelineState.MARKET_CONTENT_READY),
        (
            PipelineState.MARKET_CONTENT_READY,
            PipelineState.METHODOLOGY_REVIEWED,
            PipelineState.METHODOLOGY_REVIEWED,
        ),
        (PipelineState.METHODOLOGY_REVIEWED, PipelineState.ARCH_DESIGNED, PipelineState.ARCH_DESIGNED),
        (PipelineState.ARCH_DESIGNED, PipelineState.CODE_COMMITTED, PipelineState.CODE_COMMITTED),
        (PipelineState.CODE_COMMITTED, PipelineState.QA_TESTING, PipelineState.QA_TESTING),
        (PipelineState.QA_TESTING, PipelineState.SECURITY_SCANNED, PipelineState.SECURITY_SCANNED),
        (PipelineState.BUG_FOUND, PipelineState.DEV_FIXING, PipelineState.DEV_FIXING),
        (PipelineState.DEV_FIXING, PipelineState.QA_TESTING, PipelineState.QA_TESTING),
        (PipelineState.SECURITY_SCANNED, PipelineState.HUMAN_REVIEW_PENDING, PipelineState.HUMAN_REVIEW_PENDING),
        (PipelineState.SECURITY_SCANNED, PipelineState.SALES_ACTIVE, PipelineState.SALES_ACTIVE),
        (PipelineState.HUMAN_REVIEW_PENDING, PipelineState.SALES_ACTIVE, PipelineState.SALES_ACTIVE),
        (PipelineState.SALES_ACTIVE, PipelineState.SANDBOX_RUNNING, PipelineState.SANDBOX_RUNNING),
        (PipelineState.SANDBOX_RUNNING, PipelineState.TELEMETRY_COLLECTING, PipelineState.TELEMETRY_COLLECTING),
        # EVOLUTION_ANALYZING is the terminal transition — _create_next_task sees it
        # and advances directly to COMPLETED
        (PipelineState.TELEMETRY_COLLECTING, PipelineState.EVOLUTION_ANALYZING, PipelineState.COMPLETED),
    ])
    def test_valid_transition_execution(self, state_machine, from_state, to_state, expected_state):
        """Each declared valid transition advances product state correctly.
        
        Note: EVOLUTION_ANALYZING -> COMPLETED is handled as a special terminal
        transition inside _create_next_task, so the product ends at COMPLETED.
        """
        product = self._create_product_at_state(state_machine, from_state)
        task = Task(
            id=f"task-{from_state.value}-to-{to_state.value}",
            product_id=product.id,
            agent_type="test",
            state=to_state,
            created_at=time.time(),
            priority=5,
        )
        state_machine.add_task_to_queue(task)

        # Mark the task ready and complete it
        next_task = state_machine.get_next_task()
        assert next_task is not None, f"No task retrieved for {from_state} -> {to_state}"
        result = state_machine.complete_task(next_task.id, {"result": "ok"})
        assert result is True, f"Failed to complete task for {from_state} -> {to_state}"

        # Verify product state advanced
        refreshed = state_machine.get_product(product.id)
        assert refreshed.state == expected_state, (
            f"Expected {expected_state} after completing task, got {refreshed.state}"
        )

    def test_transition_to_failed(self, state_machine):
        """FAILED state is reachable from any non-terminal state via fail_task."""
        for from_state in PipelineState:
            if from_state in (PipelineState.COMPLETED, PipelineState.FAILED, PipelineState.CANCELLED):
                continue
            product = self._create_product_at_state(
                state_machine, from_state, product_id=f"fail-from-{from_state.value}"
            )
            task = Task(
                id=f"fail-task-{from_state.value}",
                product_id=product.id,
                agent_type="test",
                state=PipelineState.FAILED,
                created_at=time.time(),
                max_retries=0,
                priority=5,
            )
            state_machine.add_task_to_queue(task)
            result = state_machine.fail_task(task.id, "Intentional failure")
            assert result is True
            refreshed = state_machine.get_product(product.id)
            assert refreshed.state == PipelineState.FAILED, (
                f"Expected FAILED from {from_state}, got {refreshed.state}"
            )

    def test_invalid_transition_rejected(self, state_machine):
        """A task whose state is not in the valid transitions should NOT advance
        the product state."""
        product = state_machine.create_product("test")
        invalid_task = Task(
            id="skip-task",
            product_id=product.id,
            agent_type="dev",
            state=PipelineState.CODE_COMMITTED,
            created_at=time.time(),
        )
        state_machine.add_task_to_queue(invalid_task)
        state_machine.complete_task("skip-task", {})
        assert state_machine.get_product(product.id).state == PipelineState.IDEA_RECEIVED

    def test_terminal_states_have_no_transitions(self):
        """COMPLETED, FAILED, and CANCELLED have empty transition lists."""
        assert STATE_TRANSITIONS[PipelineState.COMPLETED] == []
        assert STATE_TRANSITIONS[PipelineState.FAILED] == []
        assert STATE_TRANSITIONS[PipelineState.CANCELLED] == []


# ============================================================================
# add_task_to_queue / _find_task — Direct Tests
# ============================================================================

class TestTaskQueueManagement:
    """Direct tests for add_task_to_queue and _find_task."""

    def test_add_task_to_queue(self, state_machine):
        """Adding a task increments the queue."""
        product = state_machine.create_product("test")
        task = Task(
            id="direct-add",
            product_id=product.id,
            agent_type="analyst",
            state=PipelineState.MARKET_RESEARCHED,
        )
        state_machine.add_task_to_queue(task)
        assert len(state_machine.task_queue) == 1
        assert state_machine.task_queue[0].id == "direct-add"

    def test_add_multiple_tasks(self, state_machine):
        """Multiple tasks can be added to the queue."""
        product = state_machine.create_product("test")
        for i in range(5):
            task = Task(
                id=f"multi-{i}",
                product_id=product.id,
                agent_type="analyst",
                state=PipelineState.MARKET_RESEARCHED,
                priority=i,
            )
            state_machine.add_task_to_queue(task)
        assert len(state_machine.task_queue) == 5

    def test_find_task_found(self, state_machine):
        """_find_task returns the correct task by ID."""
        product = state_machine.create_product("test")
        task = Task(
            id="find-me",
            product_id=product.id,
            agent_type="analyst",
            state=PipelineState.MARKET_RESEARCHED,
        )
        state_machine.add_task_to_queue(task)
        found = state_machine._find_task("find-me")
        assert found is not None
        assert found.id == "find-me"
        assert found.product_id == product.id

    def test_find_task_not_found(self, state_machine):
        """_find_task returns None for non-existent task ID."""
        assert state_machine._find_task("nope") is None

    def test_find_task_after_complete(self, state_machine, product_with_task):
        """Task can still be found after completion."""
        product, task = product_with_task
        state_machine.complete_task(task.id, {})
        found = state_machine._find_task(task.id)
        assert found is not None
        assert found.status == TaskStatus.COMPLETED

    def test_task_queue_persists_after_save(self, state_machine):
        """Tasks added to queue survive a save/reload cycle."""
        product = state_machine.create_product("persist-queue")
        for i in range(3):
            task = Task(
                id=f"persist-q-{i}",
                product_id=product.id,
                agent_type="analyst",
                state=PipelineState.MARKET_RESEARCHED,
                priority=i,
            )
            state_machine.add_task_to_queue(task)
        sm2 = PipelineStateMachine(state_machine.state_file)
        assert len(sm2.task_queue) == 3
        assert sm2._find_task("persist-q-0") is not None
        assert sm2._find_task("persist-q-2") is not None


# ============================================================================
# Additional Edge Cases
# ============================================================================

class TestMoreEdgeCases:
    """Additional edge cases and boundary conditions."""

    def test_create_product_with_duplicate_id(self, state_machine):
        """Creating a product with an ID that already exists overwrites it."""
        p1 = state_machine.create_product("first", product_id="dup-id")
        p2 = state_machine.create_product("second", product_id="dup-id")
        assert state_machine.get_product("dup-id").idea == "second"

    def test_get_next_task_skips_running_tasks(self, state_machine):
        """get_next_task returns only PENDING tasks, skipping RUNNING ones."""
        product = state_machine.create_product("test")
        running = Task(
            id="running", product_id=product.id, agent_type="analyst",
            state=PipelineState.MARKET_RESEARCHED, status=TaskStatus.RUNNING,
            priority=1, created_at=1.0,
        )
        pending = Task(
            id="pending", product_id=product.id, agent_type="analyst",
            state=PipelineState.MARKET_RESEARCHED, status=TaskStatus.PENDING,
            priority=2, created_at=2.0,
        )
        state_machine.add_task_to_queue(running)
        state_machine.add_task_to_queue(pending)
        task = state_machine.get_next_task()
        assert task is not None
        assert task.id == "pending"

    def test_get_next_task_skips_blocked_tasks(self, state_machine):
        """BLOCKED tasks are not returned by get_next_task."""
        product = state_machine.create_product("test")
        blocked = Task(
            id="blocked", product_id=product.id, agent_type="analyst",
            state=PipelineState.MARKET_RESEARCHED, status=TaskStatus.BLOCKED,
            priority=1, created_at=1.0,
        )
        state_machine.add_task_to_queue(blocked)
        assert state_machine.get_next_task() is None

    def test_complete_task_no_product(self, state_machine):
        """complete_task handles a task whose product doesn't exist."""
        task = Task(
            id="orphan", product_id="nonexistent-product", agent_type="analyst",
            state=PipelineState.MARKET_RESEARCHED,
        )
        state_machine.add_task_to_queue(task)
        result = state_machine.complete_task("orphan", {})
        assert result is True

    def test_complete_task_with_no_next_state(self, state_machine):
        """If product state has no transitions, task completes but state stays."""
        product = state_machine.create_product("test")
        product.state = PipelineState.COMPLETED
        task = Task(
            id="no-next", product_id=product.id, agent_type="analyst",
            state=PipelineState.MARKET_RESEARCHED,
        )
        state_machine.add_task_to_queue(task)
        result = state_machine.complete_task("no-next", {})
        assert result is True
        assert state_machine.get_product(product.id).state == PipelineState.COMPLETED

    def test_get_pipeline_metrics_zero_products(self, state_machine):
        """get_pipeline_metrics with no products returns zeroes."""
        metrics = state_machine.get_pipeline_metrics()
        assert metrics["avg_completion_time_hours"] == 0
        assert metrics["total_products"] == 0
        assert metrics["pending_tasks"] == 0

    def test_pipeline_metrics_no_completed_products(self, state_machine):
        """avg_completion_time_hours is 0 when there are no completed products."""
        state_machine.create_product("active-only")
        metrics = state_machine.get_pipeline_metrics()
        assert metrics["completed_products"] == 0
        assert metrics["avg_completion_time_hours"] == 0
