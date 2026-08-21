"""Tests for deterministic visual gate autofix."""

from __future__ import annotations

import tempfile
from pathlib import Path

from web.backend.services.visual_gate_autofix import apply_visual_gate_autofix


def test_autofix_injects_focus_main_and_rewrites_loopback():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        html = """<!DOCTYPE html><html><head><title>x</title></head><body>
<a href="#">Buy</a>
<a href="#pricing">Pricing</a>
<link rel="stylesheet" href="./static/style.css">
<script src="http://127.0.0.1:8000/app.js"></script>
</body></html>"""
        (root / "index.html").write_text(html, encoding="utf-8")
        actions = apply_visual_gate_autofix(root)
        assert "index.html" in actions
        out = (root / "index.html").read_text(encoding="utf-8")
        assert ":focus-visible" in out or "focus-visible" in out
        assert "<main" in out
        assert "127.0.0.1" not in out
        assert 'id="pricing"' in out
        assert (root / "static" / "style.css").is_file()
        assert "#1d4ed8" not in out
        assert "aicom-autofix-cta" not in out


def test_autofix_strips_cta_poison_and_does_not_reinject():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        html = """<!DOCTYPE html><html><head>
<style id="aicom-autofix-focus">
:focus-visible { outline: 2px solid #6366f1; }
/* aicom-visual-gate-autofix — WCAG-friendly default CTA/nav contrast */
button, .btn, [role="button"], header a, nav a {
  color: #ffffff !important;
  background-color: #1d4ed8 !important;
}
header, nav {
  color: #ffffff;
  background-color: #0f172a;
}
</style>
<style id="aicom-autofix-cta">button{color:#fff !important}</style>
</head><body><nav class="navbar"><a class="btn-primary" href="#go">Go</a></nav>
<main id="go"></main></body></html>"""
        (root / "index.html").write_text(html, encoding="utf-8")
        apply_visual_gate_autofix(root)
        out = (root / "index.html").read_text(encoding="utf-8")
        assert "#1d4ed8" not in out
        assert "aicom-autofix-cta" not in out
        assert ":focus-visible" in out or "focus-visible" in out


def test_heal_preview_presentation_strips_and_relinks(tmp_path: Path):
    from web.backend.services.visual_gate_autofix import heal_preview_presentation

    html = """<!DOCTYPE html><html><head>
<style id="aicom-autofix-cta">button, .btn, [role="button"], header a, nav a {
  color: #ffffff !important; background-color: #1d4ed8 !important;
}</style>
<link rel="stylesheet" href="frontend/style.css">
</head><body>
<nav class="navbar"></nav>
<section class="hero-section"><a class="btn-primary" href="#x">Go</a></section>
<div class="streak-pulse"></div>
</body></html>"""
    (tmp_path / "index.html").write_text(html, encoding="utf-8")
    (tmp_path / "style.css").write_text(
        ".navbar{display:flex}.hero-section{display:grid}.btn-primary{background:teal}.streak-pulse{opacity:1}",
        encoding="utf-8",
    )
    (tmp_path / "frontend").mkdir()
    (tmp_path / "frontend" / "style.css").write_text(".landing-nav{color:red}.hero{padding:1rem}", encoding="utf-8")
    heal_preview_presentation(tmp_path)
    out = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert "aicom-autofix-cta" not in out
    assert "#1d4ed8" not in out
    assert 'href="frontend/style.css"' not in out
    assert "style.css" in out


def test_autofix_skips_preview_venv_tree():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "index.html").write_text("<html><body></body></html>", encoding="utf-8")
        venv = root / ".aicom_sandbox" / "sb" / "preview-venv" / "lib" / "site-packages"
        venv.mkdir(parents=True)
        (venv / "loopback.yml").write_text("url: http://127.0.0.1:8000\n", encoding="utf-8")
        apply_visual_gate_autofix(root)
        assert "127.0.0.1" in (venv / "loopback.yml").read_text(encoding="utf-8")
