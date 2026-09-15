"""Unit tests for pipeline state machine transition map."""

from __future__ import annotations

import pytest

from orchestrator.pipeline_transitions import allowed_next_states, can_advance_to, is_terminal
from orchestrator.state_machine import (
    STATE_TRANSITIONS,
    PipelineState,
    PipelineStateMachine,
    Task,
    TaskStatus,
)


def test_every_non_terminal_state_has_at_least_failed_exit():
    for state, nxt in STATE_TRANSITIONS.items():
        if is_terminal(state):
            assert nxt == []
        else:
            assert PipelineState.FAILED in nxt, f"{state} must allow FAILED"


def test_idea_received_advances_to_market_researched():
    assert can_advance_to(PipelineState.IDEA_RECEIVED, PipelineState.MARKET_RESEARCHED)
    assert not can_advance_to(PipelineState.IDEA_RECEIVED, PipelineState.COMPLETED)


def test_completed_has_no_outgoing_transitions():
    assert allowed_next_states(PipelineState.COMPLETED) == []
    assert is_terminal(PipelineState.COMPLETED)


def test_complete_task_advances_product_state(tmp_path):
    sm = PipelineStateMachine(state_file=str(tmp_path / "p.json"), use_sqlite=False)
    product = sm.create_product("widget", "prod-fsm-1")
    task = Task(
        id="task-1",
        product_id=product.id,
        agent_type="analyst",
        state=PipelineState.MARKET_RESEARCHED,
        status=TaskStatus.RUNNING,
        created_at=1.0,
        started_at=1.0,
    )
    product.tasks.append(task)
    sm.task_queue.append(task)
    ok = sm.complete_task(task.id, {"ok": True})
    assert ok is True
    assert sm.products[product.id].state == PipelineState.MARKET_RESEARCHED


@pytest.mark.parametrize(
    "current,target,expected",
    [
        (PipelineState.QA_TESTING, PipelineState.SECURITY_SCANNED, True),
        (PipelineState.QA_TESTING, PipelineState.COMPLETED, False),
        (PipelineState.ARCH_DESIGNED, PipelineState.CODE_COMMITTED, True),
        (PipelineState.ARCH_DESIGNED, PipelineState.DESIGN_CRITIQUED, True),
    ],
)
def test_can_advance_to_param(current, target, expected):
    assert can_advance_to(current, target) is expected
