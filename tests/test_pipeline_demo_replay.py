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

    ud = dr_root / "public" / "pipeline_demo_replay"
    ud.mkdir(parents=True, exist_ok=True)
    (ud / "demo_123.webm").write_bytes(b"WEBM")

    cfg = load_raw_config()
    cfg["enabled"] = True
    cfg["source"] = "upload"
    cfg["media_filename"] = "demo_123.webm"
    cfg["video_url"] = None
    save_config(cfg)

    m = metrics_demo_replay_slice()
    assert m["play_url"].startswith("/api/public/pipeline-demo-replay")


def test_resolve_uploaded_media_prefers_mp4_sibling(dr_root):
    from web.backend.services.pipeline_demo_replay import load_raw_config, resolve_uploaded_media_path, save_config

    ud = dr_root / "public" / "pipeline_demo_replay"
    ud.mkdir(parents=True, exist_ok=True)
    (ud / "pipeline-demo-latest.mp4").write_bytes(b"MP4")
    cfg = load_raw_config()
    cfg["source"] = "upload"
    cfg["media_filename"] = "pipeline-demo-latest.webm"
    save_config(cfg)
    path = resolve_uploaded_media_path(cfg)
    assert path is not None
    assert path.name == "pipeline-demo-latest.mp4"


def test_public_demo_replay_no_auth(tmp_path, monkeypatch):
    """Uploaded clip must stream without Bearer — HTML5 video cannot send it."""
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path))
    from fastapi.testclient import TestClient

    from web.backend.main import app

    ud = tmp_path / "public" / "pipeline_demo_replay"
    ud.mkdir(parents=True, exist_ok=True)
    (ud / "demo_ci.webm").write_bytes(b"WEBM-TEST-BYTES")

    cfg_path = tmp_path / "config" / "pipeline_demo_replay.json"
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(
        json.dumps(
            {
                "enabled": True,
                "title": "CI",
                "source": "upload",
                "media_filename": "demo_ci.webm",
                "video_url": None,
            }
        ),
        encoding="utf-8",
    )

    with TestClient(app) as c:
        r = c.get("/api/public/pipeline-demo-replay")
        assert r.status_code == 200
        assert "video/" in (r.headers.get("content-type") or "")
        assert r.content == b"WEBM-TEST-BYTES"

        cfg_path.write_text(json.dumps({"enabled": False}), encoding="utf-8")
        r2 = c.get("/api/public/pipeline-demo-replay")
        assert r2.status_code == 404


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
