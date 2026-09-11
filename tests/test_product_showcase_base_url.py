"""Showcase capture must use a base URL reachable from the app process (8080 in Docker)."""

from __future__ import annotations

import json
from unittest.mock import patch

from web.backend.services import product_showcase as ps


def test_resolve_showcase_base_url_rewrites_9080_in_docker(monkeypatch):
    monkeypatch.delenv("AIFACTORY_SHOWCASE_BASE_URL", raising=False)
    monkeypatch.delenv("AIFACTORY_PUBLIC_URL", raising=False)
    with patch.object(ps.Path, "is_file", return_value=True):
        url = ps._resolve_showcase_capture_base_url("http://127.0.0.1:9080")
    assert url == "http://127.0.0.1:8080"


def test_resolve_showcase_base_url_explicit_passthrough(monkeypatch):
    with patch.object(ps.Path, "is_file", return_value=True):
        url = ps._resolve_showcase_capture_base_url("https://magic-ai-factory.com")
    assert url == "https://magic-ai-factory.com"


def test_list_showcase_gallery_skips_missing_clip(tmp_path, monkeypatch):
    recordings = tmp_path / "recordings"
    recordings.mkdir()
    idx_dir = tmp_path / "state"
    idx_dir.mkdir()
    idx_file = idx_dir / "product_showcase_index.json"
    idx_file.write_text(
        '{"entries": [{"product_id": "prod-x", "clip": "ghost.webm", "preview_url": "http://x"}]}',
        encoding="utf-8",
    )
    monkeypatch.setattr(ps, "RECORDINGS_DIR", recordings)
    monkeypatch.setattr(ps, "_index_path", lambda: idx_file)
    result = ps.list_showcase_gallery()
    assert result["count"] == 0
    assert result["entries"] == []
    assert json.loads(idx_file.read_text()) == {"entries": []}
