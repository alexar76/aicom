"""Regression: sandbox helpers must not shadow imported code_dir()."""

from __future__ import annotations

import json
from pathlib import Path

from web.backend.api import sandbox as sandbox_api


def test_product_has_code_twice_no_shadowing(tmp_path, monkeypatch):
    pid = "prod-shadow-test"
    product_dir = tmp_path / "code" / pid
    product_dir.mkdir(parents=True)
    (product_dir / "index.html").write_text("<html></html>", encoding="utf-8")
    manifest = {"files": [{"path": "index.html"}]}
    (product_dir / "code_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    monkeypatch.setattr(sandbox_api, "resolve_product_code_dir", lambda p: tmp_path / "code" / p)

    assert sandbox_api._product_has_code(pid) is True
    assert sandbox_api._product_has_code(pid) is True


def test_product_has_html_twice_no_shadowing(tmp_path, monkeypatch):
    pid = "prod-html-test"
    product_dir = tmp_path / "code" / pid
    product_dir.mkdir(parents=True)
    (product_dir / "page.html").write_text("<html></html>", encoding="utf-8")

    monkeypatch.setattr(sandbox_api, "resolve_product_code_dir", lambda p: tmp_path / "code" / p)

    assert sandbox_api._product_has_html_files(pid) is True
    assert sandbox_api._product_has_html_files(pid) is True
