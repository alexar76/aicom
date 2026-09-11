import json
from pathlib import Path

from core.calibration import calibrated_min_confidence, calibration_summary


def _seed(data_root: Path, decisions, outcomes):
    a = data_root / "autonomy" / "surrogate_decisions.jsonl"
    a.parent.mkdir(parents=True, exist_ok=True)
    a.write_text("\n".join(json.dumps(d) for d in decisions) + "\n", encoding="utf-8")
    o = data_root / "discovery" / "outcomes.jsonl"
    o.parent.mkdir(parents=True, exist_ok=True)
    o.write_text("\n".join(json.dumps(x) for x in outcomes) + "\n", encoding="utf-8")


def test_summary_measures_approve_accuracy(tmp_path):
    # 2 approves panned out, 2 did not — accuracy 0.5 at high confidence (over-confident).
    decisions = [
        {"point": "post_devops_gate", "decision": "approve", "confidence": 0.9, "product_id": f"p{i}"}
        for i in range(4)
    ]
    outcomes = [
        {"product_id": "p0", "reached": "COMPLETED", "ev": 1.0},
        {"product_id": "p1", "reached": "COMPLETED", "ev": 0.5},
        {"product_id": "p2", "reached": "FAILED", "ev": -1.0},
        {"product_id": "p3", "reached": "FAILED", "ev": -1.0},
    ]
    _seed(tmp_path, decisions, outcomes)

    summary = calibration_summary(tmp_path)["per_point"]["post_devops_gate"]
    assert summary["n"] == 4
    assert summary["approve_accuracy"] == 0.5
    assert summary["mean_confidence"] == 0.9


def test_calibrated_threshold_raises_for_overconfident_gate(tmp_path, monkeypatch):
    decisions = [
        {"point": "post_devops_gate", "decision": "approve", "confidence": 0.9, "product_id": f"p{i}"}
        for i in range(6)
    ]
    outcomes = [{"product_id": f"p{i}", "reached": "FAILED", "ev": -1.0} for i in range(6)]
    _seed(tmp_path, decisions, outcomes)

    monkeypatch.setenv("AIFACTORY_AUTONOMY_CALIBRATION", "1")
    # accuracy 0.0 vs mean_confidence 0.9 → threshold pushed up from 0.55.
    raised = calibrated_min_confidence(tmp_path, "post_devops_gate", 0.55)
    assert raised > 0.55


def test_disabled_returns_base(tmp_path, monkeypatch):
    monkeypatch.delenv("AIFACTORY_AUTONOMY_CALIBRATION", raising=False)
    assert calibrated_min_confidence(tmp_path, "post_devops_gate", 0.55) == 0.55
