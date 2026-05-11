"""
Decision Engine
===============
Generates management decisions based on analysis results.
Supports automatic actions (if enabled) and recommendations for admin.
"""

from __future__ import annotations

import json as json_lib
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Optional

from web.backend.api.metrics import PrometheusMetrics

logger = logging.getLogger(__name__)


class DecisionEngine:
    """
    Generates decisions based on Director AI analysis.
    
    Decision types:
    1. Automatic actions (if enabled in config)
    2. Recommendations (require admin approval)
    3. Alerts (notifications only)
    """

    def __init__(
        self,
        auto_actions_enabled: bool = False,
        allowed_actions: Optional[list[str]] = None,
        config_path: str = "/app/data/config/director_rules.yaml",
    ):
        self.auto_actions_enabled = auto_actions_enabled
        self.allowed_actions = set(allowed_actions or [])
        self.config_path = config_path
        self._load_rules()

    @staticmethod
    def _log(level: str, message: str, **kwargs):
        """Log structured JSONL entry for Director AI operations."""
        log_data = {
            "agent": "director",
            "component": "decision_engine",
            "level": level,
            "message": message,
            "time": time.time(),
            **kwargs,
        }
        log_path = Path("/app/data/logs/director.jsonl")
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(log_path, "a") as f:
                f.write(json_lib.dumps(log_data) + "\n")
        except Exception as e:
            logger.warning(f"Failed to write director decision_engine log: {e}")

    def _load_rules(self):
        """Load decision rules from config."""
        env_auto = os.environ.get("AIFACTORY_DIRECTOR_AUTO_ACTIONS_ENABLED")
        if env_auto is not None:
            self.auto_actions_enabled = env_auto.strip().lower() in {"1", "true", "yes", "on"}
        env_allowed = os.environ.get("AIFACTORY_DIRECTOR_ALLOWED_AUTO_ACTIONS", "").strip()
        if env_allowed:
            self.allowed_actions = {x.strip() for x in env_allowed.split(",") if x.strip()}
        try:
            import yaml
            with open(self.config_path, "r") as f:
                rules = yaml.safe_load(f)
                self.auto_actions_enabled = rules.get("auto_actions_enabled", self.auto_actions_enabled)
                self.allowed_actions = set(rules.get("allowed_auto_actions", list(self.allowed_actions)))
        except FileNotFoundError:
            logger.warning(f"Director rules config not found at {self.config_path}")
        except Exception as e:
            logger.error(f"Failed to load director rules: {e}")

    def generate_decisions(self, analysis: dict, metrics: dict) -> list[dict]:
        """
        Generate decisions based on analysis results.
        
        Args:
            analysis: Analysis results from DirectorAnalyzer
            metrics: Raw metrics from MetricsCollector
            
        Returns:
            List of decisions (auto + recommendations)
        """
        start_time = time.time()
        decisions = []

        # Pipeline decisions
        decisions.extend(self._analyze_pipeline_decisions(analysis, metrics))

        # Agent decisions
        decisions.extend(self._analyze_agent_decisions(analysis, metrics))

        # Resource decisions
        decisions.extend(self._analyze_resource_decisions(analysis, metrics))

        # Business decisions
        decisions.extend(self._analyze_business_decisions(analysis, metrics))
        # Independent inspector recommendations
        decisions.extend(self._analyze_inspector_decisions(analysis, metrics))

        # Record metrics for each decision
        for d in decisions:
            action = d.get("action", "unknown")
            decision_type = d.get("type", "recommendation")
            # Convert requires_approval to type labels: auto if not requires_approval
            label_type = "auto" if not d.get("requires_approval", True) else "recommendation"
            PrometheusMetrics.inc_decision(action, label_type)

        duration = time.time() - start_time
        PrometheusMetrics.observe_analysis_duration(duration)

        auto_count = sum(1 for d in decisions if d.get("type") == "auto")
        rec_count = sum(1 for d in decisions if d.get("type") == "recommendation")
        self._log("INFO", f"Generated {len(decisions)} decisions ({auto_count} auto, {rec_count} recommendations)",
                  decision_count=len(decisions), auto_count=auto_count, recommendation_count=rec_count)
        return decisions

    def _analyze_inspector_decisions(self, analysis: dict, metrics: dict) -> list[dict]:
        """Translate InspectorAgent recommendations into Director decisions."""
        out: list[dict] = []
        inspector = (analysis or {}).get("inspector_report") or {}
        if not inspector:
            return out
        recs = inspector.get("recommendations") or []
        biz = metrics.get("business_metrics") or {}
        revenue_7d = float(biz.get("revenue_7d") or 0.0)
        revenue_prev_7d = float(biz.get("revenue_prev_7d") or 0.0)
        defects_7d = int(biz.get("defects_7d") or 0)
        defects_prev_7d = int(biz.get("defects_prev_7d") or 0)
        growth = ((revenue_7d - revenue_prev_7d) / revenue_prev_7d) if revenue_prev_7d > 0 else 0.0
        defect_delta = defects_7d - defects_prev_7d

        # Weekly mandatory governance: decisions are KPI-driven, not count-driven.
        out.append(
            {
                "id": str(uuid.uuid4()),
                "action": "weekly_profit_review",
                "target": "director",
                "reason": "mandatory_weekly_inspector_decision",
                "requires_approval": False,
                "priority": "high",
                "kpi_snapshot": {
                    "revenue_growth_7d_vs_prev_7d": round(growth, 4),
                    "defect_delta_7d_vs_prev_7d": defect_delta,
                    "kpi_passed": growth > 0 and defect_delta <= 0,
                },
                "created_at": time.time(),
            }
        )

        for rec in recs:
            kind = str(rec.get("kind") or "")
            if kind == "hardening_batch":
                out.append(
                    {
                        "id": str(uuid.uuid4()),
                        "action": "run_catalog_compliance_remediation",
                        "target": "catalog",
                        "reason": "Independent inspector found problematic products",
                        "requires_approval": False,
                        "priority": "high",
                        "created_at": time.time(),
                    }
                )
            elif kind in {"benchmark_required", "benchmark_alerts_present"}:
                out.append(
                    {
                        "id": str(uuid.uuid4()),
                        "action": "trigger_benchmark_run",
                        "target": "director",
                        "reason": rec.get("reason", "inspector_benchmark_signal"),
                        "requires_approval": False,
                        "priority": "high",
                        "created_at": time.time(),
                    }
                )
            elif kind == "focus_chain":
                out.append(
                    {
                        "id": str(uuid.uuid4()),
                        "action": "recommend_crypto_chain_focus",
                        "target": rec.get("target", "crypto"),
                        "reason": rec.get("reason", "inspector_crypto_focus"),
                        "requires_approval": True,
                        "priority": "medium",
                        "created_at": time.time(),
                    }
                )
        return out

    def _analyze_pipeline_decisions(self, analysis: dict, metrics: dict) -> list[dict]:
        """Generate decisions based on pipeline analysis."""
        decisions = []
        pipeline = analysis.get("pipeline_analysis", {})
        alerts = pipeline.get("alerts", [])

        for alert in alerts:
            if alert.get("metric") == "timeout_rate":
                decisions.append({
                    "id": str(uuid.uuid4()),
                    "action": "increase_agent_timeout",
                    "target": "developer",
                    "new_value": 45,
                    "reason": "High timeout rate indicates complex tasks need more time",
                    "requires_approval": not self._is_action_allowed("increase_agent_timeout"),
                    "priority": "high",
                    "created_at": time.time(),
                })

            if alert.get("metric") == "completion_rate":
                decisions.append({
                    "id": str(uuid.uuid4()),
                    "action": "trigger_marketing_review",
                    "target": "marketing",
                    "task": "Review and optimize product descriptions for better conversion",
                    "reason": "Low completion rate may indicate poor product-market fit",
                    "requires_approval": True,
                    "priority": "medium",
                    "created_at": time.time(),
                })
            if alert.get("metric") in {"pipeline_slo_pass_rate", "pipeline_slo_regression", "pipeline_slo_mttr"}:
                decisions.append({
                    "id": str(uuid.uuid4()),
                    "action": "trigger_benchmark_and_rework_cycle",
                    "target": "pipeline",
                    "reason": "pipeline_slo_breach",
                    "requires_approval": False,
                    "priority": "high",
                    "created_at": time.time(),
                })

        return decisions

    def _analyze_agent_decisions(self, analysis: dict, metrics: dict) -> list[dict]:
        """Generate decisions based on agent analysis."""
        decisions = []
        agent_analysis = analysis.get("agent_analysis", {})
        weak_links = analysis.get("weak_links", [])

        for link in weak_links:
            if link.get("issue") == "high_error_rate":
                decisions.append({
                    "id": str(uuid.uuid4()),
                    "action": "adjust_agent_priority",
                    "target": link["agent"],
                    "new_value": 1,  # Lower priority (higher number)
                    "reason": f"Agent '{link['agent']}' has high error rate, reducing priority",
                    "requires_approval": not self._is_action_allowed("adjust_agent_priority"),
                    "priority": "medium",
                    "created_at": time.time(),
                })

        return decisions

    def _analyze_resource_decisions(self, analysis: dict, metrics: dict) -> list[dict]:
        """Generate decisions based on resource analysis."""
        decisions = []
        resource_analysis = analysis.get("resource_analysis", {})
        alerts = resource_analysis.get("alerts", [])

        resources = resource_analysis.get("resources", {})

        for alert in alerts:
            if alert.get("metric") == "cpu" and alert.get("value", 0) > 90:
                decisions.append({
                    "id": str(uuid.uuid4()),
                    "action": "recommend_switch_to_local",
                    "message": "CPU usage critical. Consider switching to lighter models or reducing concurrent tasks.",
                    "reason": "High CPU load may cause pipeline delays",
                    "requires_approval": True,
                    "priority": "high",
                    "created_at": time.time(),
                })

            if alert.get("metric") == "disk" and alert.get("value", 0) > 80:
                decisions.append({
                    "id": str(uuid.uuid4()),
                    "action": "notify_admin",
                    "message": f"Disk usage at {alert['value']}%. Consider cleaning old artifacts.",
                    "reason": "Disk space running low",
                    "requires_approval": True,
                    "priority": "medium",
                    "created_at": time.time(),
                })

        # Check if local model is underutilized
        if resources.get("cpu_percent", 0) < 30:
            decisions.append({
                "id": str(uuid.uuid4()),
                "action": "recommend_switch_to_local",
                "message": "System resources are underutilized. Consider switching from external APIs to local models to save costs.",
                "reason": "Cost optimization opportunity detected",
                "requires_approval": True,
                "priority": "low",
                "created_at": time.time(),
            })

        return decisions

    def _analyze_business_decisions(self, analysis: dict, metrics: dict) -> list[dict]:
        """Generate decisions based on business metrics."""
        decisions = []
        products = analysis.get("product_analysis", {})

        avg_health = products.get("avg_health_score", 0)
        if avg_health < 60 and avg_health > 0:
            decisions.append({
                "id": str(uuid.uuid4()),
                "action": "trigger_marketing_review",
                "target": "evolution_analyst",
                "task": "Review all products with low health scores and create improvement plan",
                "reason": f"Average product health score is low: {avg_health}/100",
                "requires_approval": True,
                "priority": "medium",
                "created_at": time.time(),
            })

        return decisions

    def _is_action_allowed(self, action: str) -> bool:
        """Check if an action is allowed for automatic execution."""
        return self.auto_actions_enabled and action in self.allowed_actions
