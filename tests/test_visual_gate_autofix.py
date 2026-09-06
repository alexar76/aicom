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


def test_autofix_dedupes_api_js_when_api_ts_exists(tmp_path: Path):
    front = tmp_path / "frontend" / "src"
    front.mkdir(parents=True)
    (front / "api.ts").write_text("export const api = {};\n", encoding="utf-8")
    (front / "api.js").write_text("export const api = {};\n", encoding="utf-8")
    (front / "App.tsx").write_text("import { api } from './api';\n", encoding="utf-8")
    (tmp_path / "index.html").write_text("<html><body></body></html>", encoding="utf-8")
    apply_visual_gate_autofix(tmp_path)
    assert (front / "api.ts").is_file()
    assert not (front / "api.js").is_file()


def test_autofix_injects_mobile_nav_when_mq_without_toggle(tmp_path: Path):
    (tmp_path / "style.css").write_text(
        "@media (max-width: 720px) { body { padding: 8px; } }\n",
        encoding="utf-8",
    )
    (tmp_path / "index.html").write_text(
        "<!DOCTYPE html><html><body><header>App</header></body></html>",
        encoding="utf-8",
    )
    apply_visual_gate_autofix(tmp_path)
    html = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert "aria-expanded" in html
    assert "aicom-autofix-nav-toggle" in html


def test_autofix_injects_page_shell_css_and_repairs_bare_main(tmp_path: Path):
    front = tmp_path / "frontend" / "src" / "pages"
    styles = tmp_path / "frontend" / "src" / "styles"
    front.mkdir(parents=True)
    styles.mkdir(parents=True)
    (front / "Branding.tsx").write_text(
        '<main className="" style={{ padding: "32px 0 64px" }}><form></form></main>\n',
        encoding="utf-8",
    )
    (styles / "app.css").write_text(
        "body { margin: 0; }\n.container { max-width: 1120px; }\n",
        encoding="utf-8",
    )
    actions = apply_visual_gate_autofix(tmp_path)
    css = (tmp_path / "frontend" / "src" / "styles" / "app.css").read_text(encoding="utf-8")
    assert "aicom-visual-gate-autofix page shell" in css
    assert ".page-shell" in css
    tsx = (front / "Branding.tsx").read_text(encoding="utf-8")
    assert 'className="page-shell"' in tsx
    assert any("Branding.tsx" in a for a in actions)


def test_is_test_hygiene_llm_finding():
    from web.backend.services.qa_llm_finding_filters import is_test_hygiene_llm_finding

    assert is_test_hygiene_llm_finding(
        {
            "source": "llm_review",
            "file": "backend/tests/conftest.py",
            "title": "Conftest sets SESSION_SECRET via os.environ.setdefault",
        }
    )
    assert is_test_hygiene_llm_finding(
        {
            "source": "llm_review",
            "file": "backend/tests/integration/test_handoff.py",
            "title": "Test isolation: shared SQLite file causes data leakage",
        }
    )
    assert not is_test_hygiene_llm_finding(
        {
            "source": "llm_review",
            "file": "backend/app/auth.py",
            "title": "Missing rate limit on login",
        }
    )
