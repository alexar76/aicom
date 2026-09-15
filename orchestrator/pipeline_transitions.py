"""Pipeline FSM transition helpers (shared by worker and unit tests)."""

from __future__ import annotations

from orchestrator.state_machine import STATE_TRANSITIONS, PipelineState


def allowed_next_states(state: PipelineState) -> list[PipelineState]:
    return list(STATE_TRANSITIONS.get(state, []))


def can_advance_to(current: PipelineState, target: PipelineState) -> bool:
    return target in STATE_TRANSITIONS.get(current, [])


def is_terminal(state: PipelineState) -> bool:
    return state in (PipelineState.COMPLETED, PipelineState.FAILED, PipelineState.CANCELLED)
