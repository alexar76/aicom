import time
from pathlib import Path

from orchestrator.runtime_guards import RuntimeGuards


def test_release_critic_requires_real_feedback(monkeypatch, tmp_path: Path):
    root = tmp_path / "data"
    (root / "specs" / "prod-x").mkdir(parents=True, exist_ok=True)
    (root / "arch" / "prod-x").mkdir(parents=True, exist_ok=True)
    (root / "feedback").mkdir(parents=True, exist_ok=True)
    (root / "specs" / "prod-x" / "specification.json").write_text(
        '{"specification":{"core_features":[{"name":"A"},{"name":"B"},{"name":"C"}]}}',
        encoding="utf-8",
    )
    (root / "arch" / "prod-x" / "architecture.json").write_text(
        '{"architecture":{"modules":[1,2,3],"ownership":"x","migration":"y","service":"z"}}',
        encoding="utf-8",
    )
    (root / "arch" / "prod-x" / "design_system.json").write_text(
        '{"design_system":{"tokens":{"a":1,"b":2,"c":3,"d":4,"e":5,"f":6}}}',
        encoding="utf-8",
    )

    monkeypatch.setenv("AIFACTORY_RELEASE_MIN_REAL_FEEDBACK", "1")
    monkeypatch.setenv("AIFACTORY_QUALITY_CONSTITUTION_ENABLED", "0")
    g = RuntimeGuards(str(root))
    ok, issues = g.release_critic("prod-x", {"production_mode": True})
    assert ok is False
    assert any("real_user_validation_failed" in x for x in issues)


def test_release_critic_optional_human_review_allows_progress_without_decision(monkeypatch, tmp_path: Path):
    root = tmp_path / "data"
    (root / "specs" / "prod-x").mkdir(parents=True, exist_ok=True)
    (root / "arch" / "prod-x").mkdir(parents=True, exist_ok=True)
    (root / "feedback").mkdir(parents=True, exist_ok=True)
    (root / "state" / "prod-x").mkdir(parents=True, exist_ok=True)
    (root / "telemetry" / "prod-x").mkdir(parents=True, exist_ok=True)
    (root / "code" / "prod-x").mkdir(parents=True, exist_ok=True)
    (root / "specs" / "prod-x" / "specification.json").write_text(
        '{"specification":{"core_features":[{"name":"A"},{"name":"B"},{"name":"C"}]}}',
        encoding="utf-8",
    )
    (root / "arch" / "prod-x" / "architecture.json").write_text(
        '{"architecture":{"modules":[1,2,3],"ownership":"x","migration":"y","service":"z"}}',
        encoding="utf-8",
    )
    (root / "arch" / "prod-x" / "design_system.json").write_text(
        '{"design_system":{"tokens":{"a":1,"b":2,"c":3,"d":4,"e":5,"f":6}}}',
        encoding="utf-8",
    )
    (root / "code" / "prod-x" / "implementation_plan.json").write_text("{}", encoding="utf-8")
    (root / "state" / "prod-x" / "lifecycle_release.json").write_text("{}", encoding="utf-8")
    (root / "telemetry" / "prod-x" / "benchmark_summary.json").write_text("{}", encoding="utf-8")
    (root / "bugs" / "prod-x").mkdir(parents=True, exist_ok=True)
    (root / "bugs" / "prod-x" / "qa_report.json").write_text(
        '{"qa_result":{"security_issues":[],"quality_gates":{"domain_acceptance_pack":{"passed":true},"acceptance_traceability":{"passed":true},"maintainability_review":{"passed":true},"demo_quality":{"issues":[]},"perf_slo":{"passed":true},"traceability_matrix":{"passed":true},"browser_preview_e2e":{"passed":true},"backend_runtime_e2e":{"passed":true}}}}',
        encoding="utf-8",
    )

    monkeypatch.setenv("AIFACTORY_RELEASE_MIN_REAL_FEEDBACK", "0")
    monkeypatch.setenv("AIFACTORY_QUALITY_CONSTITUTION_ENABLED", "1")
    monkeypatch.setenv("AIFACTORY_HUMAN_REVIEW_MODE", "optional")
    g = RuntimeGuards(str(root))
    ok, issues = g.release_critic("prod-x", {"production_mode": True})
    assert ok is True
    assert all("human_review" not in x for x in issues)


def test_release_critic_required_human_review_blocks_without_approve(monkeypatch, tmp_path: Path):
    root = tmp_path / "data"
    (root / "specs" / "prod-x").mkdir(parents=True, exist_ok=True)
    (root / "arch" / "prod-x").mkdir(parents=True, exist_ok=True)
    (root / "feedback").mkdir(parents=True, exist_ok=True)
    (root / "specs" / "prod-x" / "specification.json").write_text(
        '{"specification":{"core_features":[{"name":"A"},{"name":"B"},{"name":"C"}]}}',
        encoding="utf-8",
    )
    (root / "arch" / "prod-x" / "architecture.json").write_text(
        '{"architecture":{"modules":[1,2,3],"ownership":"x","migration":"y","service":"z"}}',
        encoding="utf-8",
    )
    (root / "arch" / "prod-x" / "design_system.json").write_text(
        '{"design_system":{"tokens":{"a":1,"b":2,"c":3,"d":4,"e":5,"f":6}}}',
        encoding="utf-8",
    )
    monkeypatch.setenv("AIFACTORY_RELEASE_MIN_REAL_FEEDBACK", "0")
    monkeypatch.setenv("AIFACTORY_QUALITY_CONSTITUTION_ENABLED", "0")
    monkeypatch.setenv("AIFACTORY_HUMAN_REVIEW_MODE", "required")
    g = RuntimeGuards(str(root))
    ok, issues = g.release_critic("prod-x", {"production_mode": True})
    assert ok is False
    assert any("human_review_required_pending" in x for x in issues)


def test_release_critic_blocks_on_low_benchmark_pass_rate(monkeypatch, tmp_path: Path):
    root = tmp_path / "data"
    (root / "specs" / "prod-x").mkdir(parents=True, exist_ok=True)
    (root / "arch" / "prod-x").mkdir(parents=True, exist_ok=True)
    (root / "feedback").mkdir(parents=True, exist_ok=True)
    (root / "reports").mkdir(parents=True, exist_ok=True)
    (root / "specs" / "prod-x" / "specification.json").write_text(
        '{"specification":{"core_features":[{"name":"A"},{"name":"B"},{"name":"C"}]}}',
        encoding="utf-8",
    )
    (root / "arch" / "prod-x" / "architecture.json").write_text(
        '{"architecture":{"modules":[1,2,3],"ownership":"x","migration":"y","service":"z"}}',
        encoding="utf-8",
    )
    (root / "arch" / "prod-x" / "design_system.json").write_text(
        '{"design_system":{"tokens":{"a":1,"b":2,"c":3,"d":4,"e":5,"f":6}}}',
        encoding="utf-8",
    )
    (root / "reports" / "benchmark_scorecard.json").write_text(
        f'{{"generated_at":{time.time()},"runs_last_7d":4,"latest":{{"pass_rate":0.42}}}}',
        encoding="utf-8",
    )
    monkeypatch.setenv("AIFACTORY_RELEASE_MIN_REAL_FEEDBACK", "0")
    monkeypatch.setenv("AIFACTORY_QUALITY_CONSTITUTION_ENABLED", "0")
    g = RuntimeGuards(str(root))
    ok, issues = g.release_critic("prod-x", {"production_mode": True})
    assert ok is False
    assert any("benchmark_gate:" in x for x in issues)
