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


def test_autofix_skips_preview_venv_tree():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "index.html").write_text("<html><body></body></html>", encoding="utf-8")
        venv = root / ".aicom_sandbox" / "sb" / "preview-venv" / "lib" / "site-packages"
        venv.mkdir(parents=True)
        (venv / "loopback.yml").write_text("url: http://127.0.0.1:8000\n", encoding="utf-8")
        apply_visual_gate_autofix(root)
        assert "127.0.0.1" in (venv / "loopback.yml").read_text(encoding="utf-8")
