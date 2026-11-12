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


@pytest.mark.parametrize("include_sandboxes", [False, True])
def test_backup_excludes_previous_backups_and_pending_uploads(tmp_path, monkeypatch, include_sandboxes):
    data = tmp_path / "data"
    for dirname in ("backups", "_restore_uploads", "code"):
        (data / dirname).mkdir(parents=True)
        (data / dirname / "fixture.txt").write_text(dirname)
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(data))
    from web.backend.services.factory_backup import build_factory_backup_zip

    path, _ = build_factory_backup_zip(include_sandboxes=include_sandboxes)
    try:
        with zipfile.ZipFile(path) as archive:
            assert "code/fixture.txt" in archive.namelist()
            assert not any(n.startswith(("backups/", "_restore_uploads/")) for n in archive.namelist())
    finally:
        path.unlink()


def test_backup_does_not_read_symlink_targets_outside_data(tmp_path, monkeypatch):
    data = tmp_path / "data"
    code = data / "code" / "generated"
    code.mkdir(parents=True)
    outside = tmp_path / "host-secret.txt"
    outside.write_text("fixture-only-host-secret")
    (code / "leaked.txt").symlink_to(outside)
    (code / "host-directory").symlink_to(tmp_path, target_is_directory=True)
    (code / "index.html").write_text("normal product")
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(data))
    from web.backend.services.factory_backup import build_factory_backup_zip

    path, _ = build_factory_backup_zip(include_sandboxes=True)
    try:
        with zipfile.ZipFile(path) as archive:
            assert archive.read("code/generated/index.html") == b"normal product"
            assert "code/generated/leaked.txt" not in archive.namelist()
            assert not any(b"fixture-only-host-secret" in archive.read(n) for n in archive.namelist())
    finally:
        path.unlink()
