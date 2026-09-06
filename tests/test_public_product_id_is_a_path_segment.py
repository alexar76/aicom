"""``product_id`` on the public telemetry routes ends up in a filesystem path.

``TelemetryCollector.record_event`` does ``data_root / product_id`` and mkdirs it, so the
schema's old "must start with prod-" check let an unauthenticated
``POST /api/telemetry/event`` with ``prod-../../../..`` create directories and append
attacker-controlled JSONL lines anywhere the process could write.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from web.backend.schemas.api_requests import EvolutionSignalRequest, TelemetryEventRequest

TRAVERSAL = [
    "prod-../../../../tmp/pwned",
    "prod-a/../../b",
    "prod-/etc",
    "prod-..",
    "prod-x/y",
    "prod-x\\y",
]


@pytest.mark.parametrize("pid", TRAVERSAL)
def test_telemetry_event_refuses_a_path_in_product_id(pid: str) -> None:
    with pytest.raises(ValidationError):
        TelemetryEventRequest(product_id=pid, event_type="click")


@pytest.mark.parametrize("pid", TRAVERSAL)
def test_evolution_signal_refuses_a_path_in_product_id(pid: str) -> None:
    with pytest.raises(ValidationError):
        EvolutionSignalRequest(product_id=pid, signal="churn_risk")


@pytest.mark.parametrize("pid", ["prod-bdb1634806de", "prod-a", "prod-A1_b-c"])
def test_real_product_ids_still_pass(pid: str) -> None:
    assert TelemetryEventRequest(product_id=pid, event_type="click").product_id == pid


def test_over_long_product_id_is_refused() -> None:
    with pytest.raises(ValidationError):
        TelemetryEventRequest(product_id="prod-" + "a" * 100, event_type="click")
