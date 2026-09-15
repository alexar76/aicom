"""Factory full-backup ZIP builder."""

from __future__ import annotations

import json
import os
import zipfile
from pathlib import Path

import pytest


def test_build_factory_backup_zip_includes_manifest(tmp_path, monkeypatch):
    data = tmp_path / "data"
    (data / "state").mkdir(parents=True)
    (data / "state" / "pipeline.db").write_bytes(b"sqlite-placeholder")
    (data / "config").mkdir()
    (data / "config" / "admin_config_overlay.yaml").write_text("general: {}\n", encoding="utf-8")
    (data / "code" / "prod-abc").mkdir(parents=True)
    (data / "code" / "prod-abc" / "index.html").write_text("<html></html>", encoding="utf-8")
    (data / "sandboxes" / "heavy").mkdir(parents=True)
    (data / "sandboxes" / "heavy" / "big.bin").write_bytes(b"x" * 100)

    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(data))

    from web.backend.services.factory_backup import build_factory_backup_zip

    zip_path, name = build_factory_backup_zip(include_sandboxes=False)
    try:
        assert name.startswith("aicom-factory-backup-")
        assert zip_path.is_file()
        with zipfile.ZipFile(zip_path) as zf:
            names = zf.namelist()
            assert "state/pipeline.db" in names
            assert "code/prod-abc/index.html" in names
            assert not any(n.startswith("sandboxes/") for n in names)
            manifest = json.loads(zf.read("_BACKUP_MANIFEST.json").decode())
            assert manifest["backup_type"] == "aicom_factory_full"
            assert "sandboxes" in (manifest.get("skipped_top_level_dirs") or [])
    finally:
        zip_path.unlink(missing_ok=True)
