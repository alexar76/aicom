"""Agent budgets must fit the work the gates added, or rounds die at the timeout."""

from orchestrator.task_executor_agent import _agent_execute_timeout_sec
from orchestrator.timeout_manager import TimeoutManager


def test_developer_budget_fits_two_full_generations():
    """A repair round regenerates ~85 files and the self-check can send it back.

    Both products failed with "execute exceeded 720s" once the write-time
    self-check started requesting a second pass.
    """
    assert _agent_execute_timeout_sec("developer") >= 1440.0


def test_qa_budget_covers_npm_install_and_the_product_build():
    assert _agent_execute_timeout_sec("qa") >= 900.0


def test_env_override_still_wins():
    import os

    os.environ["AIFACTORY_DEVELOPER_EXECUTE_TIMEOUT_SEC"] = "60"
    try:
        assert _agent_execute_timeout_sec("developer") == 60.0
    finally:
        del os.environ["AIFACTORY_DEVELOPER_EXECUTE_TIMEOUT_SEC"]


def test_the_two_timeout_tables_agree():
    """A shorter watchdog elsewhere would cancel the work this budget allows."""
    tm = TimeoutManager()
    for agent in ("developer", "qa"):
        assert tm._agent_timeouts[agent] >= _agent_execute_timeout_sec(agent)
