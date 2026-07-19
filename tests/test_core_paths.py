"""Tests for configurable data paths (audit: no hardcoded /app/data in new code)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from core.paths import (
    agent_artifact_dir,
    app_root,
    architecture_json_path,
    batch_pipeline_queue_path,
    code_dir,
    data_root,
    director_decisions_path,
    escalations_log_path,
    firewall_rules_path,
    logs_dir,
    marketing_content_path,
    metrics_history_path,
    pipeline_db_path,
    pipeline_json_path,
    resolve_data_root,
    scripts_dir,
    specification_path,
    venv_python,
)


def test_data_root_from_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path / "data"))
    assert data_root() == tmp_path / "data"
    assert code_dir("prod-x") == tmp_path / "data" / "code" / "prod-x"
    assert agent_artifact_dir("pm", "prod-x") == tmp_path / "data" / "pm" / "prod-x"


def test_pipeline_paths_from_state_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    root = tmp_path / "data"
    state = root / "state"
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(root))
    monkeypatch.setenv("AIFACTORY_STATE_DIR", str(state))
    monkeypatch.delenv("SQLITE_PATH", raising=False)
    monkeypatch.delenv("AICOM_PIPELINE_JSON", raising=False)
    assert pipeline_json_path() == state / "pipeline.json"
    assert pipeline_db_path() == state / "pipeline.db"
    assert logs_dir() == root / "logs"
    assert metrics_history_path() == root / "logs" / "metrics_history.jsonl"
    assert director_decisions_path() == state / "director_decisions.json"
    assert escalations_log_path() == root / "logs" / "escalations.jsonl"
    assert specification_path("prod-x") == root / "specs" / "prod-x" / "specification.json"
    assert architecture_json_path("prod-x") == root / "arch" / "prod-x" / "architecture.json"
    assert marketing_content_path("prod-x") == state / "prod-x" / "marketing_content.json"


def test_resolve_data_root_override(tmp_path: Path) -> None:
    custom = tmp_path / "custom-data"
    assert resolve_data_root(custom) == custom
    assert resolve_data_root(str(custom)) == custom


def test_app_root_and_runtime_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    app = tmp_path / "factory"
    monkeypatch.setenv("AIFACTORY_APP_ROOT", str(app))
    assert app_root() == app
    assert scripts_dir() == app / "scripts"
    assert venv_python() == app / "venv" / "bin" / "python"


def test_firewall_and_batch_queue_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    root = tmp_path / "data"
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(root))
    assert firewall_rules_path() == root / "config" / "firewall_rules.json"
    assert batch_pipeline_queue_path() == root / "state" / "batch_pipeline_queue.json"
