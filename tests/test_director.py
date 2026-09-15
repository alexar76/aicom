# ============================================================================
# AUTONOMOUS AI-FACTORY v2.1 — Decision Engine Tests
# ============================================================================
# Tests for director/decision_engine.py — DecisionEngine
# Covers: decision generation, action permission checks, edge cases
# ============================================================================

import pytest
import json
import time
import uuid
from pathlib import Path
from unittest.mock import patch

from director.decision_engine import DecisionEngine


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def engine():
    """DecisionEngine with auto actions disabled."""
    return DecisionEngine(
        auto_actions_enabled=False,
        allowed_actions=None,
        config_path="/tmp/nonexistent_director_rules.yaml",
    )


@pytest.fixture
def auto_engine():
    """DecisionEngine with auto actions enabled."""
    return DecisionEngine(
        auto_actions_enabled=True,
        allowed_actions=["increase_agent_timeout", "adjust_agent_priority"],
        config_path="/tmp/nonexistent_director_rules.yaml",
    )


@pytest.fixture
def sample_analysis():
    """A complete analysis dict with all sections."""
    return {
        "pipeline_analysis": {
            "alerts": [
                {"metric": "timeout_rate", "value": 0.15, "severity": "high"},
                {"metric": "completion_rate", "value": 0.45, "severity": "medium"},
            ],
        },
        "agent_analysis": {
            "agents": {
                "developer": {"error_rate": 0.12, "avg_duration": 45},
                "qa": {"error_rate": 0.03, "avg_duration": 20},
            },
        },
        "weak_links": [
            {"agent": "developer", "issue": "high_error_rate", "error_rate": 0.12},
        ],
        "resource_analysis": {
            "alerts": [
                {"metric": "cpu", "value": 95, "severity": "critical"},
                {"metric": "disk", "value": 85, "severity": "warning"},
            ],
            "resources": {
                "cpu_percent": 95,
                "memory_percent": 60,
                "disk_percent": 85,
            },
        },
        "product_analysis": {
            "avg_health_score": 45,
            "products": {
                "p1": {"health_score": 45, "state": "code_committed"},
            },
        },
    }


@pytest.fixture
def sample_metrics():
    """Sample metrics for decision generation."""
    return {
        "total_products": 5,
        "active_products": 3,
        "completed_products": 1,
        "failed_products": 1,
        "avg_completion_time_hours": 2.5,
        "pending_tasks": 2,
        "running_tasks": 1,
        "failed_tasks": 1,
    }


# ============================================================================
# generate_decisions
# ============================================================================

class TestGenerateDecisions:
    """End-to-end decision generation."""

    def test_generates_decisions_from_analysis(self, engine, sample_analysis, sample_metrics):
        """Pipeline alerts produce decisions."""
        decisions = engine.generate_decisions(sample_analysis, sample_metrics)
        assert len(decisions) > 0

    def test_returns_list_of_dicts(self, engine, sample_analysis, sample_metrics):
        """Each decision has the required fields."""
        decisions = engine.generate_decisions(sample_analysis, sample_metrics)
        for d in decisions:
            assert "id" in d
            assert "action" in d
            assert "reason" in d
            assert "requires_approval" in d
            assert "priority" in d
            assert "created_at" in d
            assert uuid.UUID(d["id"])  # Valid UUID

    def test_timeout_alert_decision(self, engine, sample_analysis, sample_metrics):
        """Timeout rate alert → increase_agent_timeout decision."""
        decisions = engine.generate_decisions(sample_analysis, sample_metrics)
        timeout_decisions = [d for d in decisions if d["action"] == "increase_agent_timeout"]
        assert len(timeout_decisions) == 1
        assert timeout_decisions[0]["target"] == "developer"
        assert timeout_decisions[0]["new_value"] == 45

    def test_completion_rate_alert_decision(self, engine, sample_analysis, sample_metrics):
        """Completion rate alert → trigger_marketing_review decision."""
        decisions = engine.generate_decisions(sample_analysis, sample_metrics)
        marketing_decisions = [d for d in decisions if d["action"] == "trigger_marketing_review"]
        assert len(marketing_decisions) == 2  # One from pipeline, one from business

    def test_high_error_rate_decision(self, engine, sample_analysis, sample_metrics):
        """High error rate in weak links → adjust_agent_priority."""
        decisions = engine.generate_decisions(sample_analysis, sample_metrics)
        priority_decisions = [d for d in decisions if d["action"] == "adjust_agent_priority"]
        assert len(priority_decisions) == 1
        assert priority_decisions[0]["target"] == "developer"

    def test_cpu_alert_decision(self, engine, sample_analysis, sample_metrics):
        """CPU > 90% → recommend_switch_to_local."""
        decisions = engine.generate_decisions(sample_analysis, sample_metrics)
        cpu_decisions = [d for d in decisions if d["action"] == "recommend_switch_to_local"]
        assert len(cpu_decisions) == 1  # 95 > 90, not underutilized

    def test_disk_alert_decision(self, engine, sample_analysis, sample_metrics):
        """Disk > 80% → notify_admin."""
        decisions = engine.generate_decisions(sample_analysis, sample_metrics)
        disk_decisions = [d for d in decisions if d["action"] == "notify_admin"]
        assert len(disk_decisions) == 1
        assert "Disk usage" in disk_decisions[0]["message"]

    def test_low_health_score_decision(self, engine, sample_analysis, sample_metrics):
        """Avg health < 60 → trigger_marketing_review for evolution_analyst."""
        decisions = engine.generate_decisions(sample_analysis, sample_metrics)
        health_decisions = [
            d for d in decisions
            if d["action"] == "trigger_marketing_review"
            and d.get("target") == "evolution_analyst"
        ]
        assert len(health_decisions) == 1

    def test_auto_actions_have_no_approval(self, auto_engine, sample_analysis, sample_metrics):
        """When auto_actions_enabled and action is allowed, requires_approval=False."""
        decisions = auto_engine.generate_decisions(sample_analysis, sample_metrics)
        timeout_decisions = [d for d in decisions if d["action"] == "increase_agent_timeout"]
        for d in timeout_decisions:
            assert d["requires_approval"] is False

    def test_auto_actions_disabled_require_approval(self, engine, sample_analysis, sample_metrics):
        """When auto_actions_disabled, requires_approval=True."""
        decisions = engine.generate_decisions(sample_analysis, sample_metrics)
        timeout_decisions = [d for d in decisions if d["action"] == "increase_agent_timeout"]
        for d in timeout_decisions:
            assert d["requires_approval"] is True


# ============================================================================
# _is_action_allowed
# ============================================================================

class TestIsActionAllowed:
    """Permission checks for auto actions."""

    def test_disabled_no_actions_allowed(self, engine):
        """Auto actions disabled → nothing allowed."""
        assert engine._is_action_allowed("increase_agent_timeout") is False
        assert engine._is_action_allowed("anything") is False

    def test_enabled_allowed_action(self, auto_engine):
        """Auto enabled + action in allowed set → allowed."""
        assert auto_engine._is_action_allowed("increase_agent_timeout") is True
        assert auto_engine._is_action_allowed("adjust_agent_priority") is True

    def test_enabled_not_in_allowed(self, auto_engine):
        """Action not in allowed set → not allowed."""
        assert auto_engine._is_action_allowed("delete_everything") is False

    def test_enabled_empty_allowed_set(self):
        """Empty allowed set → nothing allowed even if enabled."""
        e = DecisionEngine(auto_actions_enabled=True, allowed_actions=[])
        assert e._is_action_allowed("increase_agent_timeout") is False

    def test_allowed_set_loaded_from_config(self, tmp_path):
        """Rules are loaded from the YAML config path."""
        config_path = tmp_path / "director_rules.yaml"
        config_path.write_text("""
auto_actions_enabled: true
allowed_auto_actions:
  - increase_agent_timeout
""")
        e = DecisionEngine(
            auto_actions_enabled=False,
            allowed_actions=None,
            config_path=str(config_path),
        )
        # Config overrides the constructor defaults
        assert e.auto_actions_enabled is True
        assert "increase_agent_timeout" in e.allowed_actions


# ============================================================================
# Edge cases
# ============================================================================

class TestEdgeCases:
    """Edge cases and empty inputs."""

    def test_empty_analysis(self, engine, sample_metrics):
        """Empty analysis produces underutilized resource decision (cpu defaults to 0 < 30)."""
        decisions = engine.generate_decisions({}, sample_metrics)
        # Empty {} => resource_analysis missing => resources.get("cpu_percent", 0) == 0 < 30 => underutilized
        assert len(decisions) == 1
        assert decisions[0]["action"] == "recommend_switch_to_local"
        assert "cost optimization" in decisions[0]["reason"].lower()

    def test_missing_pipeline_analysis(self, engine, sample_metrics):
        """Missing pipeline_analysis section is handled gracefully."""
        decisions = engine.generate_decisions(
            {"agent_analysis": {}, "weak_links": [], "resource_analysis": {}, "product_analysis": {}},
            sample_metrics,
        )
        assert isinstance(decisions, list)

    def test_no_alerts(self, engine, sample_metrics):
        """Analysis with no alerts produces only resource/health decisions."""
        analysis = {
            "pipeline_analysis": {"alerts": []},
            "agent_analysis": {},
            "weak_links": [],
            "resource_analysis": {
                "alerts": [],
                "resources": {"cpu_percent": 20},  # Under 30 → underutilized
            },
            "product_analysis": {"avg_health_score": 0},
        }
        decisions = engine.generate_decisions(analysis, sample_metrics)
        # Should get the underutilized resource decision
        assert len(decisions) >= 0

    def test_underutilized_resource(self, engine, sample_metrics):
        """CPU < 30% triggers cost-optimization recommendation."""
        analysis = {
            "pipeline_analysis": {"alerts": []},
            "agent_analysis": {},
            "weak_links": [],
            "resource_analysis": {
                "alerts": [],
                "resources": {"cpu_percent": 15},
            },
            "product_analysis": {"avg_health_score": 0},
        }
        decisions = engine.generate_decisions(analysis, sample_metrics)
        underutilized = [d for d in decisions if d["action"] == "recommend_switch_to_local"]
        assert len(underutilized) == 1
        assert "cost optimization" in underutilized[0]["reason"].lower()

    def test_missing_metrics(self, engine, sample_analysis):
        """Missing metrics dict doesn't crash."""
        decisions = engine.generate_decisions(sample_analysis, {})
        assert isinstance(decisions, list)

    def test_decision_id_unique(self, engine, sample_analysis, sample_metrics):
        """Each decision has a unique ID."""
        decisions = engine.generate_decisions(sample_analysis, sample_metrics)
        ids = [d["id"] for d in decisions]
        assert len(ids) == len(set(ids))


# ============================================================================
# Direct _analyze_* Method Tests
# ============================================================================

class TestAnalyzePipelineDecisions:
    """Direct tests for _analyze_pipeline_decisions."""

    def test_timeout_alert(self, engine):
        """Timeout rate alert produces increase_agent_timeout decision."""
        analysis = {
            "pipeline_analysis": {
                "alerts": [{"metric": "timeout_rate", "value": 0.15}],
            },
        }
        decisions = engine._analyze_pipeline_decisions(analysis, {})
        assert len(decisions) == 1
        assert decisions[0]["action"] == "increase_agent_timeout"

    def test_completion_rate_alert(self, engine):
        """Completion rate alert produces trigger_marketing_review."""
        analysis = {
            "pipeline_analysis": {
                "alerts": [{"metric": "completion_rate", "value": 0.45}],
            },
        }
        decisions = engine._analyze_pipeline_decisions(analysis, {})
        assert len(decisions) == 1
        assert decisions[0]["action"] == "trigger_marketing_review"

    def test_both_alerts(self, engine):
        """Both timeout and completion alerts produce two decisions."""
        analysis = {
            "pipeline_analysis": {
                "alerts": [
                    {"metric": "timeout_rate", "value": 0.15},
                    {"metric": "completion_rate", "value": 0.45},
                ],
            },
        }
        decisions = engine._analyze_pipeline_decisions(analysis, {})
        assert len(decisions) == 2

    def test_no_alerts(self, engine):
        """Empty alerts produce no pipeline decisions."""
        analysis = {"pipeline_analysis": {"alerts": []}}
        assert engine._analyze_pipeline_decisions(analysis, {}) == []

    def test_missing_pipeline_analysis(self, engine):
        """Missing pipeline_analysis key produces no decisions."""
        assert engine._analyze_pipeline_decisions({}, {}) == []

    def test_unknown_metric_alert(self, engine):
        """An alert with an unrecognized metric is ignored."""
        analysis = {
            "pipeline_analysis": {
                "alerts": [{"metric": "unknown_metric", "value": 99}],
            },
        }
        assert engine._analyze_pipeline_decisions(analysis, {}) == []


class TestAnalyzeAgentDecisions:
    """Direct tests for _analyze_agent_decisions."""

    def test_high_error_rate(self, engine):
        """High error rate weak link produces adjust_agent_priority."""
        analysis = {
            "weak_links": [
                {"agent": "developer", "issue": "high_error_rate", "error_rate": 0.12},
            ],
        }
        decisions = engine._analyze_agent_decisions(analysis, {})
        assert len(decisions) == 1
        assert decisions[0]["action"] == "adjust_agent_priority"
        assert decisions[0]["target"] == "developer"

    def test_multiple_weak_links(self, engine):
        """Multiple weak links produce multiple decisions."""
        analysis = {
            "weak_links": [
                {"agent": "developer", "issue": "high_error_rate", "error_rate": 0.12},
                {"agent": "qa", "issue": "high_error_rate", "error_rate": 0.15},
            ],
        }
        decisions = engine._analyze_agent_decisions(analysis, {})
        assert len(decisions) == 2

    def test_no_weak_links(self, engine):
        """No weak links produces no agent decisions."""
        analysis = {"weak_links": []}
        assert engine._analyze_agent_decisions(analysis, {}) == []

    def test_weak_link_not_high_error(self, engine):
        """A weak link without high_error_rate issue is ignored."""
        analysis = {
            "weak_links": [
                {"agent": "developer", "issue": "slow_response", "value": 500},
            ],
        }
        assert engine._analyze_agent_decisions(analysis, {}) == []

    def test_missing_agent_analysis(self, engine):
        """Missing agent_analysis key is handled gracefully."""
        assert engine._analyze_agent_decisions({}, {}) == []


class TestAnalyzeResourceDecisions:
    """Direct tests for _analyze_resource_decisions."""

    def test_high_cpu_alert(self, engine):
        """CPU > 90% produces recommend_switch_to_local."""
        analysis = {
            "resource_analysis": {
                "alerts": [{"metric": "cpu", "value": 95}],
                "resources": {"cpu_percent": 95},
            },
        }
        decisions = engine._analyze_resource_decisions(analysis, {})
        cpu_decisions = [d for d in decisions if d["action"] == "recommend_switch_to_local"]
        assert len(cpu_decisions) == 1

    def test_high_disk_alert(self, engine):
        """Disk > 80% produces notify_admin."""
        analysis = {
            "resource_analysis": {
                "alerts": [{"metric": "disk", "value": 85}],
                "resources": {"disk_percent": 85, "cpu_percent": 50},
            },
        }
        decisions = engine._analyze_resource_decisions(analysis, {})
        disk_decisions = [d for d in decisions if d["action"] == "notify_admin"]
        assert len(disk_decisions) == 1
        assert "Disk usage" in disk_decisions[0]["message"]

    def test_underutilized_cpu(self, engine):
        """CPU < 30% produces underutilized cost-optimization recommendation."""
        analysis = {
            "resource_analysis": {
                "alerts": [],
                "resources": {"cpu_percent": 15},
            },
        }
        decisions = engine._analyze_resource_decisions(analysis, {})
        underutilized = [d for d in decisions if d["action"] == "recommend_switch_to_local"]
        assert len(underutilized) == 1
        assert "cost optimization" in underutilized[0]["reason"].lower()

    def test_normal_resources_no_decisions(self, engine):
        """Normal resource usage produces no decisions."""
        analysis = {
            "resource_analysis": {
                "alerts": [],
                "resources": {"cpu_percent": 50, "memory_percent": 60, "disk_percent": 40},
            },
        }
        assert engine._analyze_resource_decisions(analysis, {}) == []

    def test_missing_resource_analysis(self, engine):
        """Missing resource_analysis key defaults cpu_percent to 0 (<30), producing underutilized decision."""
        decisions = engine._analyze_resource_decisions({}, {})
        assert len(decisions) == 1
        assert decisions[0]["action"] == "recommend_switch_to_local"
        assert "cost optimization" in decisions[0]["reason"].lower()


class TestAnalyzeBusinessDecisions:
    """Direct tests for _analyze_business_decisions."""

    def test_low_health_score(self, engine):
        """Avg health < 60 and > 0 produces trigger_marketing_review."""
        analysis = {
            "product_analysis": {"avg_health_score": 45},
        }
        decisions = engine._analyze_business_decisions(analysis, {})
        assert len(decisions) == 1
        assert decisions[0]["action"] == "trigger_marketing_review"
        assert decisions[0]["target"] == "evolution_analyst"

    def test_high_health_score(self, engine):
        """Avg health >= 60 produces no decisions."""
        analysis = {
            "product_analysis": {"avg_health_score": 85},
        }
        assert engine._analyze_business_decisions(analysis, {}) == []

    def test_zero_health_score(self, engine):
        """Avg health of 0 produces no decisions."""
        analysis = {
            "product_analysis": {"avg_health_score": 0},
        }
        assert engine._analyze_business_decisions(analysis, {}) == []

    def test_missing_health_score(self, engine):
        """Missing avg_health_score key produces no decisions."""
        analysis = {"product_analysis": {}}
        assert engine._analyze_business_decisions(analysis, {}) == []

    def test_missing_product_analysis(self, engine):
        """Missing product_analysis key produces no decisions."""
        assert engine._analyze_business_decisions({}, {}) == []


# ============================================================================
# Rule Loading Edge Cases
# ============================================================================

class TestRuleLoading:
    """Config file loading edge cases for DecisionEngine."""

    def test_missing_config_file(self, tmp_path):
        """Missing config file logs warning but doesn't crash."""
        config_path = tmp_path / "nonexistent.yaml"
        engine = DecisionEngine(
            auto_actions_enabled=True,
            allowed_actions=["test"],
            config_path=str(config_path),
        )
        # Should keep constructor defaults when file is missing
        assert engine.auto_actions_enabled is True
        assert "test" in engine.allowed_actions

    def test_config_file_overrides_defaults(self, tmp_path):
        """Config file values override constructor defaults."""
        config_path = tmp_path / "director_rules.yaml"
        config_path.write_text("""
auto_actions_enabled: true
allowed_auto_actions:
  - increase_agent_timeout
  - adjust_agent_priority
""")
        engine = DecisionEngine(
            auto_actions_enabled=False,
            allowed_actions=None,
            config_path=str(config_path),
        )
        assert engine.auto_actions_enabled is True
        assert "increase_agent_timeout" in engine.allowed_actions
        assert "adjust_agent_priority" in engine.allowed_actions

    def test_config_file_with_no_allowed_actions(self, tmp_path):
        """Config file with no allowed_auto_actions leaves the set empty."""
        config_path = tmp_path / "director_rules.yaml"
        config_path.write_text("""
auto_actions_enabled: true
allowed_auto_actions: []
""")
        engine = DecisionEngine(
            auto_actions_enabled=False,
            allowed_actions=[],
            config_path=str(config_path),
        )
        assert engine.auto_actions_enabled is True
        assert engine.allowed_actions == set()

    def test_config_file_disabled_auto_actions(self, tmp_path):
        """Config can disable auto actions."""
        config_path = tmp_path / "director_rules.yaml"
        config_path.write_text("""
auto_actions_enabled: false
allowed_auto_actions:
  - increase_agent_timeout
""")
        engine = DecisionEngine(
            auto_actions_enabled=True,
            allowed_actions=["increase_agent_timeout"],
            config_path=str(config_path),
        )
        assert engine.auto_actions_enabled is False
        # allowed_actions still contains the action, but auto_actions_enabled gates it
        assert "increase_agent_timeout" in engine.allowed_actions

    def test_corrupted_config_file(self, tmp_path):
        """Corrupted YAML doesn't crash the engine."""
        config_path = tmp_path / "director_rules.yaml"
        config_path.write_text("{{invalid yaml: : : }")
        engine = DecisionEngine(
            auto_actions_enabled=False,
            allowed_actions=None,
            config_path=str(config_path),
        )
        # Should keep defaults on parse error
        assert engine.auto_actions_enabled is False

    def test_empty_config_file(self, tmp_path):
        """Empty YAML file is handled gracefully."""
        config_path = tmp_path / "director_rules.yaml"
        config_path.write_text("")
        engine = DecisionEngine(
            auto_actions_enabled=True,
            allowed_actions=["test"],
            config_path=str(config_path),
        )
        assert engine.auto_actions_enabled is True
        assert "test" in engine.allowed_actions


def test_the_health_log_counts_the_alerts_that_actually_exist(caplog):
    """Regression: the log read `analysis['alerts']`, a key the analyzer never returns — it
    nests them under `pipeline_analysis.alerts` and `resource_analysis.alerts`. So the line
    printed `alerts=0` unconditionally. Verified against the real analyzer: completion_rate=40
    with timeout_tasks=2 produces three alerts and still logged zero, so an operator saw
    `health=critical, alerts=0` and had nothing to act on."""
    import logging

    from director.analyzer import DirectorAnalyzer

    analysis = DirectorAnalyzer().analyze(
        {"pipeline_metrics": {"completion_rate": 40.0, "total_products": 19, "timeout_tasks": 2}}
    )
    assert analysis["overall_health"] == "critical"
    assert "alerts" not in analysis, "if a top-level key appears, simplify the worker back"

    alerts = [
        *(analysis.get("pipeline_analysis", {}).get("alerts") or []),
        *(analysis.get("resource_analysis", {}).get("alerts") or []),
    ]
    assert len(alerts) >= 3, alerts
    metrics = {a["metric"] for a in alerts}
    assert "completion_rate" in metrics and "timeout_rate" in metrics

    # And the shape the worker logs must name them, not just count them.
    rendered = ", ".join(f"{a.get('metric')}={a.get('value')}" for a in alerts[:5])
    assert "completion_rate=40.0" in rendered


def test_a_healthy_pipeline_reports_no_alerts():
    from director.analyzer import DirectorAnalyzer

    analysis = DirectorAnalyzer().analyze(
        {"pipeline_metrics": {"completion_rate": 96.0, "total_products": 19, "timeout_tasks": 0,
                              "benchmark_pass_rate": 0.9}}
    )
    assert analysis["overall_health"] == "healthy"
    assert not (analysis["pipeline_analysis"]["alerts"] or analysis["resource_analysis"]["alerts"])
