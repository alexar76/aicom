"""Unit tests for ``product_pulse`` stage mapping and payload shape."""

from __future__ import annotations

from pathlib import Path

from web.backend.services.product_pulse import (
    build_product_pulse,
    find_task_for_stage,
)


def test_find_task_for_stage_developer_dev_alias():
    tasks = [{"agent_type": "dev", "status": "running", "started_at": 1.0}]
    t = find_task_for_stage(tasks, "developer")
    assert t is not None
    assert t["agent_type"] == "dev"


def test_build_product_pulse_counts_completed_stages(tmp_path: Path):
    tasks = [
        {"agent_type": "analyst", "status": "completed", "product_id": "p1"},
        {"agent_type": "pm", "status": "completed", "product_id": "p1"},
        {"agent_type": "marketing", "status": "running", "started_at": 0.0, "product_id": "p1"},
    ]
    row = {
        "id": "p1",
        "state": "CODE_COMMITTED",
        "tasks": tasks,
        "architecture": {"tech_stack": {"frontend": "Next.js", "backend": "none", "database": "SQLite"}},
        "spec": {"delivery_profile": "marketing_landing"},
        "economics": {},
    }
    pulse = build_product_pulse(row, light=True, data_root=tmp_path)
    assert pulse["completed_stages"] == 3
    assert pulse["total_stages"] == 11
    assert pulse["current_stage"] == "marketing"
    assert "Next.js" in pulse["tech_stack"]
    assert len(pulse["stage_dots"]) == 11


def test_quality_red_when_telemetry_gates_fail(tmp_path: Path):
    pid = "p-gate"
    tel_dir = tmp_path / "telemetry" / pid
    tel_dir.mkdir(parents=True)
    (tel_dir / "demo_quality_gate.json").write_text('{"gates_all_passed": false}', encoding="utf-8")
    row = {
        "id": pid,
        "state": "QA_TESTING",
        "tasks": [{"agent_type": "qa", "status": "completed", "product_id": pid}],
        "architecture": {},
        "spec": {},
        "economics": {},
    }
    pulse = build_product_pulse(row, light=False, data_root=tmp_path)
    assert pulse["quality_pulse"] == "red"
