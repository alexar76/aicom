import json
import time
from pathlib import Path

from web.backend.services.release_cockpit import evaluate_release_cockpit, execute_release_protocol


def test_execute_release_protocol_marks_missing_sections(tmp_path: Path):
    pid = "prod-r1"
    (tmp_path / "state" / pid).mkdir(parents=True, exist_ok=True)
    (tmp_path / "state" / pid / "lifecycle_release.json").write_text(
        json.dumps({"lifecycle_release": {"versioning_strategy": "semver"}}),
        encoding="utf-8",
    )
    out = execute_release_protocol(pid, str(tmp_path))
    assert out["executed"] is False
    assert "migration_plan" in out["missing"]


def test_release_cockpit_no_go_when_protocol_not_executed(tmp_path: Path):
    pid = "prod-r2"
    (tmp_path / "bugs" / pid).mkdir(parents=True, exist_ok=True)
    (tmp_path / "telemetry" / pid).mkdir(parents=True, exist_ok=True)
    (tmp_path / "code" / pid).mkdir(parents=True, exist_ok=True)
    (tmp_path / "state" / pid).mkdir(parents=True, exist_ok=True)
    (tmp_path / "telemetry" / pid / "benchmark_summary.json").write_text("{}", encoding="utf-8")
    (tmp_path / "code" / pid / "implementation_plan.json").write_text("{}", encoding="utf-8")
    (tmp_path / "state" / pid / "lifecycle_release.json").write_text(
        json.dumps(
            {
                "lifecycle_release": {
                    "versioning_strategy": "semver",
                    "migration_plan": "safe migrations",
                    "canary_plan": "10 percent",
                    "rollback_plan": "auto rollback",
                    "release_checks": ["qa", "security"],
                }
            }
        ),
        encoding="utf-8",
    )
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
    (tmp_path / "reports").mkdir(parents=True, exist_ok=True)
    (tmp_path / "reports" / "benchmark_scorecard.json").write_text(
        json.dumps(
            {
                "generated_at": time.time(),
                "runs_last_7d": 4,
                "latest": {"pass_rate": 0.9},
            }
        ),
        encoding="utf-8",
    )

    c = evaluate_release_cockpit(pid, str(tmp_path))
    assert c["go_no_go"] == "no-go"
    assert c["checks"]["release_protocol_executed"] is False


def test_release_cockpit_flags_perf_regression(tmp_path: Path):
    pid = "prod-r3"
    (tmp_path / "bugs" / pid).mkdir(parents=True, exist_ok=True)
    (tmp_path / "telemetry" / pid).mkdir(parents=True, exist_ok=True)
    (tmp_path / "code" / pid).mkdir(parents=True, exist_ok=True)
    (tmp_path / "state" / pid).mkdir(parents=True, exist_ok=True)
    (tmp_path / "reports").mkdir(parents=True, exist_ok=True)
    (tmp_path / "telemetry" / pid / "benchmark_summary.json").write_text("{}", encoding="utf-8")
    (tmp_path / "code" / pid / "implementation_plan.json").write_text("{}", encoding="utf-8")
    (tmp_path / "state" / pid / "lifecycle_release.json").write_text(
        json.dumps({"lifecycle_release": {"versioning_strategy": "x", "migration_plan": "x", "canary_plan": "x", "rollback_plan": "x", "release_checks": ["x"]}}),
        encoding="utf-8",
    )
    (tmp_path / "state" / pid / "release_protocol_execution.json").write_text(
        json.dumps({"executed": True}),
        encoding="utf-8",
    )
    (tmp_path / "reports" / "benchmark_scorecard.json").write_text(
        json.dumps(
            {
                "generated_at": time.time(),
                "runs_last_7d": 4,
                "latest": {"pass_rate": 0.9},
            }
        ),
        encoding="utf-8",
    )
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
    hist = tmp_path / "telemetry" / pid / "load_perf_history.jsonl"
    rows = [{"p95_ms": 100, "timestamp": i} for i in range(10)] + [{"p95_ms": 250, "timestamp": i} for i in range(10, 13)]
    hist.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    c = evaluate_release_cockpit(pid, str(tmp_path))
    assert c["checks"]["perf_regression"] is False
    assert c["go_no_go"] == "no-go"

