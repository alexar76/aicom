"""Admin Files tab artifact helpers (no full dashboard import — avoids passlib in bare CI)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from fastapi import HTTPException

_ROOT = Path(__file__).resolve().parents[1]
_ARTIFACT_FILES = _ROOT / "web/backend/api/admin/dashboard/artifact_files.py"


def _artifact_files_module():
    spec = importlib.util.spec_from_file_location(
        "admin_artifact_files_under_test", _ARTIFACT_FILES
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_sanitize_admin_product_id_rejects_traversal():
    mod = _artifact_files_module()
    with pytest.raises(HTTPException) as exc:
        mod.sanitize_admin_product_id("../evil")
    assert exc.value.status_code == 400


def test_walk_artifact_files_empty_when_missing(tmp_path, monkeypatch):
    mod = _artifact_files_module()
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path))
    dirs = mod.admin_product_artifact_category_dirs("prod-test-files")
    paths, truncated = mod.walk_artifact_files(dirs["code"])
    assert paths == []
    assert truncated is False
