"""Factory restore preview and snapshot replace."""

from __future__ import annotations

import json
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
