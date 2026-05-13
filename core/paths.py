from __future__ import annotations

import os
from pathlib import Path


def data_root() -> Path:
    return Path(os.environ.get("AIFACTORY_DATA_ROOT", "/app/data"))


def config_path() -> Path:
    """Primary platform YAML path (same resolution as :func:`core.config_merge.config_yaml_path` unless overridden)."""
    p = os.environ.get("AIFACTORY_CONFIG_PATH")
    if p:
        return Path(p)
    from core.config_merge import config_yaml_path

    return config_yaml_path()


def state_dir() -> Path:
    return Path(os.environ.get("AIFACTORY_STATE_DIR", str(data_root() / "state")))


def logs_dir() -> Path:
    return Path(os.environ.get("AIFACTORY_LOGS_DIR", str(data_root() / "logs")))


def pipeline_json_path() -> Path:
    return Path(os.environ.get("AICOM_PIPELINE_JSON", str(state_dir() / "pipeline.json")))


def pipeline_db_path() -> Path:
    return Path(os.environ.get("SQLITE_PATH", str(state_dir() / "pipeline.db")))


def workspace_id() -> str:
    return os.environ.get("AIFACTORY_WORKSPACE_ID", "default").strip() or "default"
