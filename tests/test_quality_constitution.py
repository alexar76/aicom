import json
from pathlib import Path

from web.backend.services.quality_constitution import evaluate_quality_constitution


def test_quality_constitution_fails_when_missing_artifacts(tmp_path: Path):
    result = evaluate_quality_constitution("prod-x", str(tmp_path))
    assert result["passed"] is False
    assert "qa_report_missing" in result["issues"]


def test_quality_constitution_passes_with_all_required_signals(tmp_path: Path):
    pid = "prod-ok"
    (tmp_path / "bugs" / pid).mkdir(parents=True, exist_ok=True)
    (tmp_path / "telemetry" / pid).mkdir(parents=True, exist_ok=True)
    (tmp_path / "code" / pid).mkdir(parents=True, exist_ok=True)
    (tmp_path / "state" / pid).mkdir(parents=True, exist_ok=True)
    (tmp_path / "telemetry" / pid / "benchmark_summary.json").write_text("{}", encoding="utf-8")
    (tmp_path / "code" / pid / "implementation_plan.json").write_text("{}", encoding="utf-8")
    (tmp_path / "state" / pid / "lifecycle_release.json").write_text("{}", encoding="utf-8")
    qa_report = {
        "qa_result": {
            "security_issues": [],
            "quality_gates": {
                "acceptance_traceability": {"passed": True},
                "domain_acceptance_pack": {"passed": True},
                "maintainability_review": {"passed": True},
                "traceability_matrix": {"passed": True},
                "browser_preview_e2e": {"passed": True},
                "backend_runtime_e2e": {"passed": True, "skipped": False},
                "demo_quality": {"issues": []},
                "perf_slo": {"passed": True},
            },
        }
    }
    (tmp_path / "bugs" / pid / "qa_report.json").write_text(json.dumps(qa_report), encoding="utf-8")

    result = evaluate_quality_constitution(pid, str(tmp_path))
    assert result["passed"] is True
