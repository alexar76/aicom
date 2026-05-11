"""Post-DevOps human gate (full_software) and admin approve/reject persistence."""

from __future__ import annotations

import json

import pytest

from agents.product_profile import MARKETING_LANDING, post_devops_human_gate_required


def test_gate_required_full_software_by_default(monkeypatch):
    monkeypatch.delenv("AIFACTORY_POST_DEVOPS_HUMAN_GATE", raising=False)
    monkeypatch.setenv("AIFACTORY_HUMAN_REVIEW_REQUIRED", "1")
    product = {"delivery_profile": "full_software", "idea": "saas api"}
    assert post_devops_human_gate_required(product) is True


def test_gate_skipped_marketing_landing(monkeypatch):
    monkeypatch.delenv("AIFACTORY_POST_DEVOPS_HUMAN_GATE", raising=False)
    monkeypatch.setenv("AIFACTORY_HUMAN_REVIEW_REQUIRED", "1")
    product = {"delivery_profile": MARKETING_LANDING, "idea": "landing page"}
    assert post_devops_human_gate_required(product) is False


def test_gate_global_disable(monkeypatch):
    monkeypatch.delenv("AIFACTORY_POST_DEVOPS_HUMAN_GATE", raising=False)
    monkeypatch.setenv("AIFACTORY_HUMAN_REVIEW_REQUIRED", "0")
    product = {"delivery_profile": "full_software", "idea": "api"}
    assert post_devops_human_gate_required(product) is False


def test_gate_explicit_force_on(monkeypatch):
    monkeypatch.setenv("AIFACTORY_POST_DEVOPS_HUMAN_GATE", "1")
    monkeypatch.setenv("AIFACTORY_HUMAN_REVIEW_REQUIRED", "0")
    product = {"delivery_profile": MARKETING_LANDING, "idea": "landing"}
    assert post_devops_human_gate_required(product) is True


@pytest.fixture
def pipeline_json_only(tmp_path, monkeypatch):
    monkeypatch.setenv("USE_SQLITE", "0")
    state_dir = tmp_path / "state"
    state_dir.mkdir(parents=True)
    pj = state_dir / "pipeline.json"
    monkeypatch.setenv("AICOM_PIPELINE_JSON", str(pj))
    fb_root = tmp_path / "feedback"
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path))
    return pj, fb_root


def test_approve_writes_sales_task(pipeline_json_only):
    pj, fb_root = pipeline_json_only
    data = {
        "products": {"p1": {"id": "p1", "idea": "idea", "state": "HUMAN_REVIEW_PENDING"}},
        "task_queue": [],
    }
    pj.write_text(json.dumps(data), encoding="utf-8")

    from web.backend.services.human_pipeline import approve_post_devops_human_review

    res = approve_post_devops_human_review("p1", "note")
    assert res.get("ok") is True
    assert res.get("task_id")

    loaded = json.loads(pj.read_text(encoding="utf-8"))
    assert loaded["products"]["p1"]["state"] == "SALES_ACTIVE"
    tasks = loaded["task_queue"]
    assert any(t.get("agent_type") == "sales" and t.get("product_id") == "p1" for t in tasks)

    fb_files = list(fb_root.glob("fb-*.json"))
    assert fb_files, "feedback file expected"
    fb = json.loads(fb_files[0].read_text(encoding="utf-8"))
    assert fb.get("review_decision") == "approve"


def test_reject_queues_dev_fixing(pipeline_json_only):
    pj, _fb_root = pipeline_json_only
    data = {
        "products": {"p1": {"id": "p1", "idea": "idea", "state": "HUMAN_REVIEW_PENDING", "quality_repair_round": 0}},
        "task_queue": [],
    }
    pj.write_text(json.dumps(data), encoding="utf-8")

    from web.backend.services.human_pipeline import reject_post_devops_human_review

    res = reject_post_devops_human_review("p1", "please fix deploy scripts and env docs")
    assert res.get("ok") is True

    loaded = json.loads(pj.read_text(encoding="utf-8"))
    assert loaded["products"]["p1"]["state"] == "BUG_FOUND"
    assert any(
        t.get("agent_type") == "developer" and str(t.get("state", "")).upper() == "DEV_FIXING"
        for t in loaded["task_queue"]
    )


def test_approve_wrong_state(pipeline_json_only):
    pj, _ = pipeline_json_only
    data = {"products": {"p1": {"id": "p1", "idea": "i", "state": "QA_TESTING"}}, "task_queue": []}
    pj.write_text(json.dumps(data), encoding="utf-8")

    from web.backend.services.human_pipeline import approve_post_devops_human_review

    res = approve_post_devops_human_review("p1")
    assert res.get("ok") is False
    assert res.get("reason") == "not_at_human_gate"
