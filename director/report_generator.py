"""
Report Generator
================
Generates markdown reports for Director AI analysis results.
Reports are saved to /data/reports/director/ and displayed in the admin panel.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Optional

from core.paths import director_reports_dir, logs_dir

logger = logging.getLogger(__name__)


class ReportGenerator:
    """
    Generates structured markdown reports from Director AI analysis.
    
    Report format follows the specification:
    - Key metrics table
    - Automatic actions applied
    - Recommendations requiring approval
    - Predictions and forecasts
    """

    def __init__(self, reports_dir: str | Path | None = None):
        self.reports_dir = Path(reports_dir) if reports_dir else director_reports_dir()
        self.reports_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _log(level: str, message: str, **kwargs):
        """Log structured JSONL entry for Director AI operations."""
        log_data = {
            "agent": "director",
            "component": "report_generator",
            "level": level,
            "message": message,
            "time": time.time(),
            **kwargs,
        }
        log_path = logs_dir() / "director.jsonl"
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(log_path, "a") as f:
                f.write(json.dumps(log_data) + "\n")
        except Exception as e:
            logger.warning(f"Failed to write director report_generator log: {e}")

    def generate_report(
        self,
        analysis: dict,
        metrics: dict,
        decisions: list[dict],
        inspector_report: Optional[dict] = None,
    ) -> str:
        """
        Generate a complete Director AI report.
        
        Args:
            analysis: Analysis results from DirectorAnalyzer
            metrics: Raw metrics from MetricsCollector
            decisions: Decisions from DecisionEngine
            
        Returns:
            Markdown report content
        """
        timestamp = time.time()
        period_start = timestamp - 14400  # 4 hours ago
        period_end = timestamp

        from datetime import datetime
        start_str = datetime.fromtimestamp(period_start).strftime("%Y-%m-%d %H:%M")
        end_str = datetime.fromtimestamp(period_end).strftime("%H:%M")

        report = []
        report.append(f"# 📊 Director AI Report | {start_str}-{end_str}")
        report.append("")
        report.append("## 🎯 Key Performance Indicators")
        report.append("")
        report.append(self._generate_kpi_table(analysis, metrics))
        report.append("")
        report.append(self._generate_auto_actions_section(decisions))
        report.append("")
        report.append(self._generate_recommendations_section(decisions))
        report.append("")
        report.append(self._generate_forecast_section(analysis, metrics))
        report.append("")
        report.append(self._generate_inspector_section(inspector_report or analysis.get("inspector_report") or {}))
        report.append("")
        report.append("---")
        report.append(f"*Report generated automatically at {datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S UTC')}*")
        report.append("*For report settings: /admin → Director Settings*")

        content = "\n".join(report)

        # Save report to file
        date_str = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d")
        period_str = f"{datetime.fromtimestamp(period_start).strftime('%H%M')}-{datetime.fromtimestamp(period_end).strftime('%H%M')}"
        filename = f"{date_str}_{period_str}.md"
        filepath = self.reports_dir / filename

        with open(filepath, "w") as f:
            f.write(content)

        self._log("INFO", f"Report generated: {filename}",
                  filename=filename, report_size=len(content))
        logger.info(f"Director report saved: {filepath}")
        return content

    def _generate_inspector_section(self, inspector_report: dict) -> str:
        if not inspector_report:
            return "## 🕵️ Independent Inspector\n\nNo inspector report attached in this cycle."
        summary = inspector_report.get("summary") or {}
        crypto = inspector_report.get("crypto_summary") or {}
        recs = inspector_report.get("recommendations") or []
        lines = [
            "## 🕵️ Independent Inspector",
            "",
            f"- Products reviewed: {summary.get('products_total', 0)}",
            f"- Problematic products: {summary.get('problematic_products', 0)}",
            f"- Benchmark status: {summary.get('benchmark_status', 'unknown')}",
            f"- Benchmark alerts: {summary.get('benchmark_alerts_count', 0)}",
            f"- Fiat revenue (window): {crypto.get('fiat_revenue', 0)}",
            f"- Crypto revenue (window): {crypto.get('crypto_revenue', 0)}",
            "",
            "### Inspector recommendations",
        ]
        if not recs:
            lines.append("- none")
        else:
            for rec in recs:
                lines.append(f"- {rec.get('kind', 'unknown')}: {rec.get('reason', 'n/a')}")
        return "\n".join(lines)

    def _generate_kpi_table(self, analysis: dict, metrics: dict) -> str:
        """Generate the KPI metrics table."""
        pipeline = metrics.get("pipeline_metrics", {})
        resources = metrics.get("resource_metrics", {})
        products = metrics.get("product_metrics", {})

        rows = []

        # Pipeline metrics
        avg_time = pipeline.get("avg_completion_time_hours", 0)
        rows.append(self._kpi_row(
            "Idea→MVP time",
            f"{avg_time:.1f}h",
            "<4h",
            "✅" if avg_time < 4 else ("⚠️" if avg_time < 6 else "❌")
        ))

        completion_rate = pipeline.get("completion_rate", 0)
        rows.append(self._kpi_row(
            "Completion rate",
            f"{completion_rate:.1f}%",
            ">95%",
            "✅" if completion_rate > 95 else ("⚠️" if completion_rate > 80 else "❌")
        ))

        timeout_count = pipeline.get("timeout_tasks", 0)
        total_tasks = pipeline.get("pending_tasks", 0) + pipeline.get("running_tasks", 0) + timeout_count
        timeout_rate = (timeout_count / max(total_tasks, 1)) * 100
        rows.append(self._kpi_row(
            "Agent timeouts",
            f"{timeout_rate:.1f}%",
            "<5%",
            "✅" if timeout_rate < 5 else ("⚠️" if timeout_rate < 10 else "❌")
        ))

        # Resource metrics
        cpu = resources.get("cpu_percent", 0)
        rows.append(self._kpi_row(
            "CPU usage",
            f"{cpu:.0f}%",
            "<80%",
            "✅" if cpu < 80 else ("⚠️" if cpu < 90 else "❌")
        ))

        memory = resources.get("memory_percent", 0)
        rows.append(self._kpi_row(
            "Memory usage",
            f"{memory:.0f}%",
            "<80%",
            "✅" if memory < 80 else ("⚠️" if memory < 90 else "❌")
        ))

        # Product metrics
        avg_health = products.get("avg_health_score", 0)
        if avg_health > 0:
            rows.append(self._kpi_row(
                "Product health",
                f"{avg_health:.0f}/100",
                ">70",
                "✅" if avg_health > 70 else ("⚠️" if avg_health > 50 else "❌")
            ))

        # Overall health
        overall = analysis.get("overall_health", "unknown")
        health_icon = {"healthy": "✅", "degraded": "⚠️", "critical": "❌", "unknown": "❓"}
        rows.append(self._kpi_row(
            "Platform health",
            overall.upper(),
            "healthy",
            health_icon.get(overall, "❓")
        ))

        # Build table
        header = "| Metric | Value | Target | Status |"
        separator = "|--------|-------|--------|--------|"
        return header + "\n" + separator + "\n" + "\n".join(rows)

    def _kpi_row(self, metric: str, value: str, target: str, status: str) -> str:
        return f"| {metric} | {value} | {target} | {status} |"

    def _generate_auto_actions_section(self, decisions: list[dict]) -> str:
        """Generate the automatic actions section."""
        auto_actions = [d for d in decisions if not d.get("requires_approval", True)]
        
        if not auto_actions:
            return "## ⚡ Automatic Actions\n\nNo automatic actions were taken this period."

        lines = ["## ⚡ Automatic Actions (applied)"]
        for i, action in enumerate(auto_actions, 1):
            lines.append(f"{i}. ✅ **{action.get('action', 'Unknown action')}** on **{action.get('target', 'unknown')}**")
            lines.append(f"   - Reason: {action.get('reason', 'N/A')}")
            lines.append("")

        return "\n".join(lines)

    def _generate_recommendations_section(self, decisions: list[dict]) -> str:
        """Generate the recommendations section."""
        recommendations = [d for d in decisions if d.get("requires_approval", True)]
        
        if not recommendations:
            return "## 💡 Recommendations\n\nNo recommendations this period."

        lines = ["## 💡 Recommendations (require approval)"]
        for i, rec in enumerate(recommendations, 1):
            action = rec.get("action", "Unknown")
            target = rec.get("target", "unknown")
            reason = rec.get("reason", "N/A")
            message = rec.get("message", rec.get("task", ""))

            lines.append(f"{i}. **{action}** → **{target}**")
            if message:
                lines.append(f"   - {message}")
            lines.append(f"   - Reason: {reason}")
            lines.append(f"   - Priority: {rec.get('priority', 'medium').upper()}")
            lines.append(f"   `[Approve]` `[Reject]` `[Edit]`")
            lines.append("")

        return "\n".join(lines)

    def _generate_forecast_section(self, analysis: dict, metrics: dict) -> str:
        """Generate the forecast/predictions section."""
        pipeline = metrics.get("pipeline_metrics", {})
        resources = metrics.get("resource_metrics", {})

        lines = ["## 📈 Forecast (next 24h)"]

        # Pipeline forecast
        active = pipeline.get("active_products", 0)
        avg_time = pipeline.get("avg_completion_time_hours", 0)
        if active > 0 and avg_time > 0:
            estimated_completions = max(1, int(24 / max(avg_time, 1)))
            lines.append(f"- Expected product completions: ~{estimated_completions}")
        else:
            lines.append("- No active products in pipeline")

        # Resource forecast
        cpu = resources.get("cpu_percent", 0)
        if cpu > 80:
            lines.append(f"- ⚠️ Risk of CPU overload: {cpu}% current usage")
        else:
            lines.append(f"- Resource usage stable (CPU: {cpu:.0f}%)")

        # Risk assessment
        alerts = analysis.get("pipeline_analysis", {}).get("alerts", [])
        if alerts:
            lines.append(f"- ⚠️ {len(alerts)} active alerts requiring attention")

        lines.append("- Recommended: schedule maintenance during low-activity hours (04:00-06:00)")

        return "\n".join(lines)

    def get_latest_report(self) -> Optional[str]:
        """Get the content of the latest report."""
        reports = sorted(self.reports_dir.glob("*.md"), reverse=True)
        if reports:
            with open(reports[0], "r") as f:
                return f.read()
        return None

    def list_reports(self, limit: int = 10) -> list[dict]:
        """List recent reports with metadata."""
        reports = sorted(self.reports_dir.glob("*.md"), reverse=True)[:limit]
        result = []
        for report in reports:
            stat = report.stat()
            result.append({
                "filename": report.name,
                "created_at": stat.st_mtime,
                "size_bytes": stat.st_size,
            })
        return result
