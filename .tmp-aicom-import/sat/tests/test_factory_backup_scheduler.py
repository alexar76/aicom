"""Factory backup schedule helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from web.backend.services.factory_backup import (
    persist_factory_backup_to_disk,
    prune_factory_backups_on_disk,
)
from web.backend.services.factory_backup_scheduler import (
    normalize_hhmm,
    normalize_timezone,
    schedule_from_config,
)


def test_normalize_hhmm():
    assert normalize_hhmm("3:5") == "03:05"
    assert normalize_hhmm("invalid") == "03:00"


def test_normalize_timezone():
    assert normalize_timezone("Europe/Moscow") == "Europe/Moscow"
    assert normalize_timezone("Not/A/Zone") == "UTC"


def test_schedule_from_config_defaults():
    s = schedule_from_config({})
    assert s["enabled"] is False
    assert s["time"] == "03:00"
    assert s["retention"] == 7


def test_persist_to_disk(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    (data / "state").mkdir()
    (data / "state" / "pipeline.json").write_text('{"products":{}}', encoding="utf-8")
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(data))

    r = persist_factory_backup_to_disk(include_sandboxes=False)
    path = data / "backups" / r["filename"]
    assert path.is_file()
    assert r["size_bytes"] > 0


def test_prune_retention(tmp_path, monkeypatch):
    data = tmp_path / "data"
    bdir = data / "backups"
    bdir.mkdir(parents=True)
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(data))
    for i in range(5):
        p = bdir / f"aicom-factory-backup-test-2025010{i}-120000Z.zip"
        p.write_bytes(b"zip")
        p.touch()
    removed = prune_factory_backups_on_disk(retention=2)
    assert len(removed) == 3
    assert len(list(bdir.glob("aicom-factory-backup-*.zip"))) == 2
