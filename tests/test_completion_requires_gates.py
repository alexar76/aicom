"""A completion marker is not evidence the product works."""

import json

import pytest

from orchestrator.pipeline_state_sync import infer_product_state_from_tasks, quality_gates_failed


def _qa_report(tmp_path, pid, passed):
    d = tmp_path / "bugs" / pid
    d.mkdir(parents=True, exist_ok=True)
    (d / "qa_report.json").write_text(
        json.dumps({"qa_result": {"quality_gates_all_passed": passed}}), encoding="utf-8"
    )


def _tasks(pid):
    return [{"product_id": pid, "agent_type": "__complete__", "status": "completed",
             "state": "COMPLETED"}]


def test_a_marker_is_ignored_when_the_gates_failed(tmp_path, monkeypatch):
    """The real incident: COMPLETED with boot, build, module health and journey all failing."""
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path))
    _qa_report(tmp_path, "prod-x", False)
    assert quality_gates_failed("prod-x") is True
    assert infer_product_state_from_tasks(_tasks("prod-x")) != "COMPLETED"


def test_a_marker_is_honoured_when_the_gates_passed(tmp_path, monkeypatch):
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path))
    _qa_report(tmp_path, "prod-y", True)
    assert quality_gates_failed("prod-y") is False
    assert infer_product_state_from_tasks(_tasks("prod-y")) == "COMPLETED"


def test_a_product_with_no_qa_report_is_not_blocked(tmp_path, monkeypatch):
    """Absence of a report is not evidence of failure — landings never run this gate."""
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path))
    assert quality_gates_failed("prod-never-tested") is False
    assert infer_product_state_from_tasks(_tasks("prod-never-tested")) == "COMPLETED"


def test_a_corrupt_report_does_not_block_completion(tmp_path, monkeypatch):
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path))
    d = tmp_path / "bugs" / "prod-bad"
    d.mkdir(parents=True)
    (d / "qa_report.json").write_text("{not json", encoding="utf-8")
    assert quality_gates_failed("prod-bad") is False


def test_missing_product_id_is_harmless():
    assert quality_gates_failed("") is False
    assert quality_gates_failed(None) is False
