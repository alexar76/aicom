"""An operator reopen must queue a task the worker can advance from."""

import pytest

from web.backend.services.pipeline_reopen import coherent_task_state


def test_developer_reopen_cannot_carry_a_pre_developer_state():
    """The real strand: developer + ARCHITECTURE_READY completed, nothing queued next."""
    assert coherent_task_state("developer", "ARCHITECTURE_READY") == "DEV_FIXING"


@pytest.mark.parametrize(
    "agent,expected",
    [
        ("pm", "PLANNING"),
        ("architect", "DESIGNING"),
        ("developer", "DEV_FIXING"),
        ("qa", "TESTING"),
        ("security", "SECURITY_REVIEW"),
        ("devops", "DEPLOYING"),
    ],
)
def test_each_agent_gets_its_own_stage(agent, expected):
    assert coherent_task_state(agent, None) == expected
    assert coherent_task_state(agent, expected) == expected


def test_matching_request_is_honoured_without_complaint():
    assert coherent_task_state("qa", "TESTING") == "TESTING"


def test_unknown_agent_falls_back_to_the_request():
    assert coherent_task_state("mystery", "SOME_STATE") == "SOME_STATE"
    assert coherent_task_state("mystery", None) == "PLANNING"


def test_case_and_whitespace_are_normalised():
    assert coherent_task_state("  Developer ", " architecture_ready ") == "DEV_FIXING"
