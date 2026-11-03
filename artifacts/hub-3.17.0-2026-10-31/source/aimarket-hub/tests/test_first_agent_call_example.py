"""The example must distinguish signed accounting from a delivered result."""
from pathlib import Path
import runpy
import sys
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def example():
    return runpy.run_path(str(Path(__file__).resolve().parents[1] / "examples/first-agent-call.py"))


def test_verified_receipt_without_weather_is_not_success(example):
    assert example["show_result"]({
        "id": "old-live-task", "status": {"state": "TASK_STATE_COMPLETED"},
        "receipt_verified": True,
        "artifacts": [{"name": "result", "parts": [{"data": None}]}],
    }) == 4


@pytest.mark.parametrize("already_completed", [False, True])
def test_payment_continues_existing_task_without_another_invoke(example, monkeypatch, already_completed):
    client = MagicMock()
    delivered = {"id": "paid-task", "status": {"state": "TASK_STATE_COMPLETED"},
                 "receipt_verified": True,
                 "artifacts": [{"name": "result", "parts": [{"data": {"reading": "weather"}}]}]}
    client.get_task.return_value = (delivered if already_completed else {
        "id": "paid-task", "status": {"state": "TASK_STATE_INPUT_REQUIRED"},
    })
    client.pay_x402.return_value = delivered
    monkeypatch.setitem(example["main"].__globals__, "A2AClient", MagicMock(return_value=client))
    monkeypatch.setattr(sys, "argv", ["example", "--task-id", "paid-task", "--payment-tx", "0x" + "11" * 32])
    assert example["main"]() == 0
    client.invoke.assert_not_called()
    client.search.assert_not_called()
    assert client.pay_x402.call_count == (0 if already_completed else 1)
    client.close.assert_called_once()
