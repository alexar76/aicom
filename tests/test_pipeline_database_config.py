"""Pipeline database backend resolution and URL masking."""

from __future__ import annotations

import os

import pytest

from core.pipeline_database import (
    apply_pipeline_db_config_from_app_config,
    mask_database_url,
    pipeline_db_backend,
    pipeline_uses_sql_store,
)


class _Cfg:
    def __init__(self, data: dict):
        self._data = data

    def get(self, key: str, default=None):
        return self._data.get(key, default)


def test_mask_database_url_hides_password():
    masked = mask_database_url("postgresql://user:secret@db.example.com:5432/aicom")
    assert "secret" not in masked
    assert "user" in masked


def test_apply_config_postgres(monkeypatch):
    monkeypatch.delenv("PIPELINE_DB_BACKEND", raising=False)
    cfg = _Cfg(
        {
            "general.pipeline_db_backend": "postgres",
            "general.pipeline_database_url": "postgresql://u:p@localhost/db",
        }
    )
    apply_pipeline_db_config_from_app_config(cfg)
    assert os.environ.get("PIPELINE_DB_BACKEND") == "postgres"
    assert os.environ.get("USE_SQLITE") == "false"
    assert "postgresql://" in os.environ.get("PIPELINE_DATABASE_URL", "")


def test_apply_config_sqlite(monkeypatch):
    monkeypatch.setenv("PIPELINE_DB_BACKEND", "postgres")
    cfg = _Cfg({"general.pipeline_db_backend": "sqlite", "general.pipeline_database_url": ""})
    apply_pipeline_db_config_from_app_config(cfg)
    assert os.environ.get("PIPELINE_DB_BACKEND") == "sqlite"
    assert os.environ.get("USE_SQLITE") == "true"


def test_pipeline_uses_sql_store():
    os.environ["PIPELINE_DB_BACKEND"] = "postgres"
    os.environ["USE_SQLITE"] = "false"
    assert pipeline_uses_sql_store() is True
    assert pipeline_db_backend() == "postgres"
