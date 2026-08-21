"""A product whose state disagrees with its own queue never advances again."""

import time

from orchestrator.task_queue_hygiene import reconcile_product_task_states


def _task(pid, agent, state, status="running"):
    return {"product_id": pid, "agent_type": agent, "state": state, "status": status}


def test_stale_human_gate_over_a_running_developer_is_realigned():
    """Exactly the shape that stranded a product three times today."""
    now = time.time()
    products = {"p1": {"state": "HUMAN_REVIEW_PENDING", "updated_at": now}}
    queue = [_task("p1", "developer", "DEV_FIXING")]

    assert reconcile_product_task_states(products, queue, now) is True
    assert products["p1"]["state"] == "BUG_FOUND"


def test_qa_task_realigns_to_its_own_state():
    now = time.time()
    products = {"p1": {"state": "HUMAN_REVIEW_PENDING", "updated_at": now}}
    queue = [_task("p1", "qa", "TESTING")]

    assert reconcile_product_task_states(products, queue, now) is True
    assert products["p1"]["state"] == "TESTING"


def test_a_genuine_human_gate_with_no_active_task_is_left_alone():
    """Waiting for a human is a legitimate resting state, not a strand."""
    now = time.time()
    products = {"p1": {"state": "HUMAN_REVIEW_PENDING", "updated_at": now - 99999}}
    assert reconcile_product_task_states(products, [], now) is False
    assert products["p1"]["state"] == "HUMAN_REVIEW_PENDING"


def test_matching_state_is_not_touched():
    now = time.time()
    products = {"p1": {"state": "BUG_FOUND", "updated_at": now}}
    queue = [_task("p1", "developer", "DEV_FIXING")]
    assert reconcile_product_task_states(products, queue, now) is False


def test_terminal_products_are_never_realigned():
    now = time.time()
    for state in ("COMPLETED", "FAILED", "CANCELLED"):
        products = {"p1": {"state": state, "updated_at": now}}
        queue = [_task("p1", "developer", "DEV_FIXING")]
        assert reconcile_product_task_states(products, queue, now) is False
        assert products["p1"]["state"] == state


def test_working_state_with_no_task_is_reported_not_guessed(caplog):
    """Guessing the next stage risks running an agent twice; say so loudly instead."""
    now = time.time()
    products = {"p1": {"state": "ARCHITECTURE_READY", "updated_at": now - 4000}}
    with caplog.at_level("ERROR"):
        assert reconcile_product_task_states(products, [], now) is False
    assert any("stranded" in r.message for r in caplog.records)
    assert products["p1"]["state"] == "ARCHITECTURE_READY"


def test_a_recently_updated_working_state_is_not_called_stranded(caplog):
    now = time.time()
    products = {"p1": {"state": "DEV_FIXING", "updated_at": now - 30}}
    with caplog.at_level("ERROR"):
        reconcile_product_task_states(products, [], now)
    assert not any("stranded" in r.message for r in caplog.records)
