"""Nested index.html copied to root must keep nested CSS/JS hrefs."""

from __future__ import annotations

from pathlib import Path

from web.backend.services.code_entrypoint import (
    _rewrite_copied_html,
    ensure_web_entrypoint_at_product_root,
)


def test_rewrite_copied_html_prefixes_relative_assets():
    html = """<html><head>
<link rel="stylesheet" href="./style.css">
<link rel="preconnect" href="https://fonts.googleapis.com">
</head><body><script src="app.js"></script><a href="#pricing">p</a></body></html>"""
    out = _rewrite_copied_html(html, "frontend")
    assert 'href="frontend/style.css"' in out
    assert 'src="frontend/app.js"' in out
    assert "https://fonts.googleapis.com" in out
    assert 'href="#pricing"' in out


def test_ensure_web_entrypoint_rewrites_nested_hrefs(tmp_path: Path, monkeypatch):
    from web.backend.services import code_entrypoint as ce

    monkeypatch.setattr(ce, "data_root", lambda: tmp_path)
    code = tmp_path / "code" / "prod-x"
    (code / "frontend").mkdir(parents=True)
    (code / "frontend" / "index.html").write_text(
        '<html><head><link rel="stylesheet" href="./style.css"></head><body></body></html>',
        encoding="utf-8",
    )
    (code / "frontend" / "style.css").write_text(".hero{color:teal}", encoding="utf-8")
    assert ensure_web_entrypoint_at_product_root("prod-x") is True
    out = (code / "index.html").read_text(encoding="utf-8")
    assert "frontend/style.css" in out
