"""Factory restore preview and snapshot replace."""

from __future__ import annotations

import json
import stat
import zipfile
from pathlib import Path

import pytest


def _make_backup_zip(path: Path, *, product_html: str = "<html>backup</html>") -> None:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        manifest = {
            "backup_type": "aicom_factory_full",
            "exported_at_utc": "2026-01-01T00:00:00Z",
            "workspace_id": "default",
        }
        zf.writestr("_BACKUP_MANIFEST.json", json.dumps(manifest))
        zf.writestr("state/pipeline.db", b"sqlite-backup")
        zf.writestr("code/prod-backup/index.html", product_html)
        zf.writestr("config/admin_config_overlay.yaml", "general: {}\n")


def test_preview_restore_warnings(tmp_path, monkeypatch):
    data = tmp_path / "data"
    (data / "state").mkdir(parents=True)
    (data / "state" / "pipeline.db").write_bytes(b"x")
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(data))

    from web.backend.services.factory_backup import save_restore_upload, preview_restore

    zpath = tmp_path / "upload.zip"
    _make_backup_zip(zpath)
    token, _ = save_restore_upload(zpath.read_bytes())
    prev = preview_restore(token)
    assert prev["restore_mode"] == "full_snapshot_replace"
    assert any("REPLACE" in w or "replace" in w.lower() for w in prev["warnings"])


def test_restore_rejects_zipslip(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir(parents=True)
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(data))

    from web.backend.services.factory_backup import save_restore_upload, restore_factory_from_upload

    zpath = tmp_path / "evil.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "_BACKUP_MANIFEST.json",
            json.dumps({"backup_type": "aicom_factory_full", "workspace_id": "default"}),
        )
        zf.writestr("../../../../tmp/pwned.txt", "evil")

    token, _ = save_restore_upload(zpath.read_bytes())
    with pytest.raises(ValueError, match="traversal|Absolute"):
        restore_factory_from_upload(token, create_pre_restore_backup=False)


def test_restore_replaces_data(tmp_path, monkeypatch):
    data = tmp_path / "data"
    (data / "code" / "prod-live").mkdir(parents=True)
    (data / "code" / "prod-live" / "index.html").write_text("live", encoding="utf-8")
    (data / "state").mkdir(parents=True)
    (data / "state" / "pipeline.db").write_bytes(b"live-db")
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(data))

    from web.backend.services.factory_backup import save_restore_upload, restore_factory_from_upload

    zpath = tmp_path / "upload.zip"
    _make_backup_zip(zpath, product_html="<html>restored</html>")
    token, _ = save_restore_upload(zpath.read_bytes())
    res = restore_factory_from_upload(token, create_pre_restore_backup=False)
    assert res["ok"] is True
    assert (data / "code" / "prod-backup" / "index.html").read_text() == "<html>restored</html>"
    assert not (data / "code" / "prod-live").exists()


@pytest.mark.parametrize("operation", ["preview_restore", "restore_factory_from_upload"])
def test_restore_token_cannot_select_or_delete_another_zip(tmp_path, monkeypatch, operation):
    from web.backend.services import factory_backup

    data = tmp_path / "data"
    data.mkdir()
    other = data / "another.zip"
    _make_backup_zip(other)
    original = other.read_bytes()
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(data))
    with pytest.raises(ValueError, match="restore token"):
        getattr(factory_backup, operation)("../another")
    assert other.read_bytes() == original


@pytest.mark.parametrize("old_directory_symlink", [False, True])
def test_restore_preserves_recovery_files_and_unlinks_old_symlinks(tmp_path, monkeypatch, old_directory_symlink):
    from web.backend.services.factory_backup import save_restore_upload, restore_factory_from_upload

    data = tmp_path / "data"
    backups = data / "backups"
    backups.mkdir(parents=True)
    (backups / "keep.zip").write_bytes(b"existing backup")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep.txt").write_text("host file")
    if old_directory_symlink:
        (data / "linked-directory").symlink_to(outside, target_is_directory=True)
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(data))
    path = tmp_path / "upload.zip"
    _make_backup_zip(path)
    with zipfile.ZipFile(path, "a") as archive:
        # Legacy backups could contain these directories. They must not overwrite
        # the preserved recovery copies, nor any pending upload on this instance.
        archive.writestr("backups/keep.zip", b"overwrite")
        archive.writestr("_restore_uploads/pending.zip", b"overwrite")
    token, _ = save_restore_upload(path.read_bytes())
    pending = data / "_restore_uploads" / "pending.zip"
    pending.write_bytes(b"pending upload")
    result = restore_factory_from_upload(token, create_pre_restore_backup=False)
    assert result["ok"] is True
    assert (backups / "keep.zip").read_bytes() == b"existing backup"
    assert pending.read_bytes() == b"pending upload"
    assert not (data / "linked-directory").is_symlink()
    assert (outside / "keep.txt").read_text() == "host file"


def test_backup_restore_roundtrip_preserves_private_and_executable_file_modes(tmp_path, monkeypatch):
    from web.backend.services.factory_backup import (
        build_factory_backup_zip, restore_factory_from_upload, save_restore_upload,
    )

    data = tmp_path / "data"
    secret = data / "secrets" / "fixture.key"
    executable = data / "code" / "product" / "run.sh"
    secret.parent.mkdir(parents=True)
    executable.parent.mkdir(parents=True)
    secret.write_text("fixture-only-secret")
    executable.write_text("#!/bin/sh\nexit 0\n")
    secret.chmod(0o600)
    executable.chmod(0o755)
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(data))
    path, _ = build_factory_backup_zip()
    try:
        token, _ = save_restore_upload(path.read_bytes())
    finally:
        path.unlink()
    restore_factory_from_upload(token, create_pre_restore_backup=False)
    assert secret.read_text() == "fixture-only-secret"
    assert stat.S_IMODE(secret.stat().st_mode) == 0o600
    assert stat.S_IMODE(executable.stat().st_mode) == 0o755
