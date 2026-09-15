"""
Director analyzer
=================
Converts raw metrics into health bands and alert lists.
"""

from __future__ import annotations

import os
from typing import Any


class DirectorAnalyzer:
    """Rule-based analyzer used by Director cycle."""

    def analyze(self, metrics: dict[str, Any]) -> dict[str, Any]:
        pipeline = metrics.get("pipeline_metrics") or {}
        completion_rate = float(pipeline.get("completion_rate") or 0.0)
        timeout_tasks = int(pipeline.get("timeout_tasks") or 0)
        total_products = int(pipeline.get("total_products") or 0)
        benchmark_pass_rate = float(pipeline.get("benchmark_pass_rate") or 0.0)
        benchmark_regression = float(pipeline.get("benchmark_regression") or 0.0)
        mttr_hours = float(pipeline.get("mean_time_to_remediation_hours") or 0.0)
        target_pass = float(os.environ.get("AIFACTORY_PIPELINE_SLO_TARGET_PASS_RATE", "0.75"))
        max_regression = float(os.environ.get("AIFACTORY_PIPELINE_SLO_MAX_REGRESSION", "0.05"))
        max_mttr_hours = float(os.environ.get("AIFACTORY_PIPELINE_SLO_MAX_MTTR_HOURS", "12"))

        alerts: list[dict[str, Any]] = []
        if completion_rate < 70:
            alerts.append({"metric": "completion_rate", "severity": "high", "value": completion_rate})
        elif completion_rate < 85:
            alerts.append({"metric": "completion_rate", "severity": "medium", "value": completion_rate})
        if timeout_tasks > 0:
            alerts.append({"metric": "timeout_rate", "severity": "medium", "value": timeout_tasks})
        if benchmark_pass_rate < target_pass:
            alerts.append({"metric": "pipeline_slo_pass_rate", "severity": "high", "value": benchmark_pass_rate})
        if benchmark_regression > max_regression:
            alerts.append({"metric": "pipeline_slo_regression", "severity": "high", "value": benchmark_regression})
        if mttr_hours > max_mttr_hours:
            alerts.append({"metric": "pipeline_slo_mttr", "severity": "medium", "value": mttr_hours})

        if total_products == 0:
            health = "degraded"
        elif completion_rate >= 90 and timeout_tasks == 0:
            health = "healthy"
        elif completion_rate >= 75:
            health = "degraded"
        else:
            health = "critical"

        return {
            "overall_health": health,
            "pipeline_analysis": {
                "alerts": alerts,
                "completion_rate": completion_rate,
                "timeout_tasks": timeout_tasks,
                "slo": {
                    "target_pass_rate": target_pass,
                    "max_regression": max_regression,
                    "max_mttr_hours": max_mttr_hours,
                    "actual_pass_rate": benchmark_pass_rate,
                    "actual_regression": benchmark_regression,
                    "actual_mttr_hours": mttr_hours,
                    "passed": (
                        benchmark_pass_rate >= target_pass
                        and benchmark_regression <= max_regression
                        and mttr_hours <= max_mttr_hours
                    ),
                },
            },
            "resource_analysis": {"alerts": []},
            "agent_analysis": {},
            "weak_links": [],
            "product_analysis": metrics.get("product_metrics") or {},
        }
