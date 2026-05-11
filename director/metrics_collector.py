"""
Director metrics collector
==========================
Collects platform, pipeline, quality, feedback, and finance snapshots.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


class MetricsCollector:
    """Collects raw metrics consumed by DirectorAnalyzer/InspectorAgent."""

    def __init__(self, data_root: str = "/app/data"):
        self.data_root = Path(data_root)

    def _read_json(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _read_jsonl_count(self, path: Path) -> int:
        if not path.exists():
            return 0
        try:
            return sum(1 for x in path.read_text(encoding="utf-8").splitlines() if x.strip())
        except Exception:
            return 0

    def collect_all(self) -> dict[str, Any]:
        pipeline = self._read_json(self.data_root / "state" / "pipeline.json")
        products = pipeline.get("products") if isinstance(pipeline, dict) else {}
        task_queue = pipeline.get("task_queue") if isinstance(pipeline, dict) else []
        if not isinstance(products, dict):
            products = {}
        if not isinstance(task_queue, list):
            task_queue = []

        completed = sum(1 for p in products.values() if str((p or {}).get("state", "")).upper() in {"COMPLETED", "DEPLOYED_PRODUCTION"})
        failed = sum(1 for p in products.values() if str((p or {}).get("state", "")).upper() == "FAILED")
        active = len(products) - completed - failed
        timeout_tasks = sum(1 for t in task_queue if str(t.get("status") or "").lower() in {"timedout", "timeout"})
        done_tasks = [t for t in task_queue if str(t.get("status") or "").lower() == "completed"]
        remediation_durations_h: list[float] = []
        for t in done_tasks:
            if str(t.get("state") or "").upper() != "DEV_FIXING":
                continue
            started = float(t.get("started_at") or 0.0)
            completed_at = float(t.get("completed_at") or 0.0)
            if started > 0 and completed_at > started:
                remediation_durations_h.append((completed_at - started) / 3600.0)
        mean_remediation_h = (
            round(sum(remediation_durations_h) / max(1, len(remediation_durations_h)), 3)
            if remediation_durations_h
            else 0.0
        )

        owner_directives = self._read_json(self.data_root / "state" / "owner_general_directives.json")
        dir_list = owner_directives.get("directives") if isinstance(owner_directives, dict) else []
        if not isinstance(dir_list, list):
            dir_list = []
        recent_directive_texts = [
            str(d.get("text") or "").strip() for d in dir_list[-8:] if isinstance(d, dict) and str(d.get("text") or "").strip()
        ]

        director_decisions = self._read_json(self.data_root / "state" / "director_decisions.json")
        benchmark_scorecard = self._read_json(self.data_root / "reports" / "benchmark_scorecard.json")
        benchmark_alerts = self._read_json(self.data_root / "reports" / "benchmark_alerts.json")
        benchmark_history = benchmark_scorecard.get("history") if isinstance(benchmark_scorecard, dict) else []
        regression = 0.0
        if isinstance(benchmark_history, list) and len(benchmark_history) >= 2:
            prev = float((benchmark_history[-2] or {}).get("pass_rate") or 0.0)
            cur = float((benchmark_history[-1] or {}).get("pass_rate") or 0.0)
            regression = round(max(0.0, prev - cur), 4)

        feedback_dir = self.data_root / "feedback"
        feedback_count = len(list(feedback_dir.glob("fb-*.json"))) if feedback_dir.exists() else 0
        orders = self._read_json(self.data_root / "store" / "orders.json")
        orders_rows = list(orders.values()) if isinstance(orders, dict) else []
        now = time.time()
        d7 = now - 7 * 24 * 3600
        d14 = now - 14 * 24 * 3600
        rev_7d = sum(float(x.get("amount") or 0.0) for x in orders_rows if float(x.get("created_at") or 0.0) >= d7)
        rev_prev_7d = sum(
            float(x.get("amount") or 0.0)
            for x in orders_rows
            if d14 <= float(x.get("created_at") or 0.0) < d7
        )
        defect_rows = [x for x in (feedback_dir.glob("fb-*.json") if feedback_dir.exists() else [])]
        defects_7d = 0
        defects_prev_7d = 0
        for f in defect_rows:
            row = self._read_json(f)
            ts = float(row.get("created_at") or 0.0)
            if str(row.get("classification") or "") != "bug":
                continue
            if ts >= d7:
                defects_7d += 1
            elif d14 <= ts < d7:
                defects_prev_7d += 1

        return {
            "collected_at": now,
            "pipeline_metrics": {
                "total_products": len(products),
                "active_products": max(0, active),
                "completed_products": completed,
                "failed_products": failed,
                "pending_tasks": sum(1 for t in task_queue if str(t.get("status") or "").lower() == "pending"),
                "running_tasks": sum(1 for t in task_queue if str(t.get("status") or "").lower() == "running"),
                "timeout_tasks": timeout_tasks,
                "completion_rate": round((completed / max(1, len(products))) * 100.0, 2),
                "avg_completion_time_hours": 4.0,
                "mean_time_to_remediation_hours": mean_remediation_h,
                "benchmark_pass_rate": float((benchmark_scorecard.get("latest") or {}).get("pass_rate") or 0.0),
                "benchmark_regression": regression,
            },
            "product_metrics": {
                "avg_health_score": 0,
            },
            "business_metrics": {
                "feedback_items_total": feedback_count,
                "benchmark_runs_total": int(benchmark_scorecard.get("runs_total") or 0),
                "benchmark_alerts_count": len((benchmark_alerts.get("alerts") or [])),
                "revenue_7d": round(rev_7d, 2),
                "revenue_prev_7d": round(rev_prev_7d, 2),
                "defects_7d": defects_7d,
                "defects_prev_7d": defects_prev_7d,
            },
            "director_metrics": {
                "pending_decisions": len((director_decisions.get("pending") or [])) if isinstance(director_decisions, dict) else 0,
                "applied_decisions": len((director_decisions.get("applied") or [])) if isinstance(director_decisions, dict) else 0,
            },
            "owner_chat_metrics": {
                "general_directives_total": len(dir_list),
                "recent_owner_directives": recent_directive_texts,
            },
        }
