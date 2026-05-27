"""Dashboard metrics regression guards."""

from __future__ import annotations

from pathlib import Path


def test_dashboard_helpers_defines_logger():
    text = (
        Path(__file__).resolve().parents[1]
        / "web/backend/api/admin/dashboard/helpers.py"
    ).read_text(encoding="utf-8")
    assert "logger = logging.getLogger(__name__)" in text


def test_helpers_exports_agent_log_loader():
    text = (
        Path(__file__).resolve().parents[1]
        / "web/backend/api/admin/dashboard/helpers.py"
    ).read_text(encoding="utf-8")
    assert "def load_agent_execution_logs(" in text
    assert '_AGENT_LOG_JSONL_SKIP = frozenset({"llm_calls"})' in text


def test_sqlite_get_metrics_uses_lowercase_task_status():
    text = (
        Path(__file__).resolve().parents[1] / "orchestrator/sqlite_manager.py"
    ).read_text(encoding="utf-8")
    assert "lower(trim(status)) = 'running'" in text
    assert "lower(trim(status)) = 'pending'" in text
