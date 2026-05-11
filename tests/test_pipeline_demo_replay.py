"""Pipeline demo replay config + dashboard metrics slice."""

from __future__ import annotations

import json

import pytest


@pytest.fixture
def dr_root(tmp_path, monkeypatch):
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path))
    yield tmp_path


def test_metrics_slice_disabled_by_default(dr_root):
    from web.backend.services.pipeline_demo_replay import metrics_demo_replay_slice

    m = metrics_demo_replay_slice()
    assert m["enabled"] is False
    assert m.get("play_url") is None


def test_external_url_roundtrip(dr_root):
    from web.backend.services.pipeline_demo_replay import (
        admin_public_config,
        load_raw_config,
        metrics_demo_replay_slice,
        save_config,
    )

    cfg = load_raw_config()
    cfg["enabled"] = True
    cfg["source"] = "external_url"
    cfg["video_url"] = "https://cdn.example.test/demo.webm"
    cfg["title"] = "Walkthrough"
    save_config(cfg)

    assert metrics_demo_replay_slice()["play_url"] == "https://cdn.example.test/demo.webm"
    pub = admin_public_config()
    assert pub["source"] == "external_url"
    assert pub["play_url"] == "https://cdn.example.test/demo.webm"


def test_upload_source_play_url(dr_root):
    from web.backend.services.pipeline_demo_replay import (
        load_raw_config,
        metrics_demo_replay_slice,
        save_config,
    )

    cfg = load_raw_config()
    cfg["enabled"] = True
    cfg["source"] = "upload"
    cfg["media_filename"] = "demo_123.webm"
    cfg["video_url"] = None
    save_config(cfg)

    m = metrics_demo_replay_slice()
    assert m["play_url"] == "/api/admin/demo-replay/media/demo_123.webm"


def test_dashboard_includes_demo_replay(dr_root):
    from web.backend.api.admin.dashboard import _build_full_metrics

    cfg_path = dr_root / "config" / "pipeline_demo_replay.json"
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(
        json.dumps(
            {
                "enabled": True,
                "title": "CI",
                "source": "external_url",
                "video_url": "https://ex.test/x.mp4",
                "media_filename": None,
            }
        ),
        encoding="utf-8",
    )

    metrics = _build_full_metrics()
    dr = metrics.get("demo_replay") or {}
    assert dr.get("enabled") is True
    assert dr.get("play_url") == "https://ex.test/x.mp4"
