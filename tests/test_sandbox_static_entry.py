"""Sandbox static preview entry resolution."""

from __future__ import annotations

from pathlib import Path

from web.backend.services import sandbox_static_entry as sse


def test_resolve_prefers_root_index(tmp_path: Path):
    body = "root " * 100
    (tmp_path / "index.html").write_text(f"<html>{body}</html>", encoding="utf-8")
    (tmp_path / "frontend").mkdir()
    (tmp_path / "frontend" / "landing").mkdir(parents=True)
    (tmp_path / "frontend" / "landing" / "index.html").write_text(f"<html>{body}</html>", encoding="utf-8")
    assert sse.resolve_static_preview_relpath(tmp_path) == "index.html"


def test_resolve_nested_landing_when_no_root(tmp_path: Path):
    body = "nested " * 100
    (tmp_path / "frontend" / "landing").mkdir(parents=True)
    (tmp_path / "frontend" / "landing" / "index.html").write_text(f"<html>{body}</html>", encoding="utf-8")
    assert sse.resolve_static_preview_relpath(tmp_path) == "frontend/landing/index.html"


def test_full_software_capable_with_compose(tmp_path: Path):
    (tmp_path / "frontend" / "landing").mkdir(parents=True)
    (tmp_path / "frontend" / "landing" / "index.html").write_text(
        "<html>" + "x" * 500 + "</html>",
        encoding="utf-8",
    )
    (tmp_path / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
    ok, reasons = sse.full_software_storefront_preview_capable("prod-x", code_root=tmp_path)
    assert ok is True
    assert reasons == []


def test_storefront_front_page_ready_nested(tmp_path: Path):
    code = tmp_path / "code" / "prod-x"
    (code / "frontend" / "landing").mkdir(parents=True)
    (code / "frontend" / "landing" / "index.html").write_text(
        "<html><body>" + "content " * 80 + "</body></html>",
        encoding="utf-8",
    )
    ok, rel, reasons = sse.storefront_front_page_ready("prod-x", code_root=code)
    assert ok is True
    assert rel == "frontend/landing/index.html"
    assert reasons == []


def test_full_software_landing_only_without_stack_fails(tmp_path: Path):
    (tmp_path / "frontend" / "landing").mkdir(parents=True)
    (tmp_path / "frontend" / "landing" / "index.html").write_text(
        "<html>" + "x" * 500 + "</html>",
        encoding="utf-8",
    )
    ok, reasons = sse.full_software_storefront_preview_capable("prod-x", code_root=tmp_path)
    assert ok is False
    assert "full_software_landing_only_no_app_stack" in reasons


def test_is_unbuilt_spa_dev_shell_detects_vite_entry():
    html = """<!DOCTYPE html><html><body><div id="root"></div>
    <script type="module" src="./src/main.tsx"></script></body></html>"""
    assert sse.is_unbuilt_spa_dev_shell(html) is True


def test_is_unbuilt_spa_dev_shell_allows_built_bundle():
    html = """<!DOCTYPE html><html><body><div id="root"></div>
    <script type="module" src="./assets/index-a1b2c3.js"></script></body></html>"""
    assert sse.is_unbuilt_spa_dev_shell(html) is False


def test_resolve_skips_vite_dev_shell(tmp_path: Path):
    (tmp_path / "frontend").mkdir()
    (tmp_path / "frontend" / "index.html").write_text(
        "<!DOCTYPE html><html><body><div id='root'></div>"
        '<script type="module" src="./src/main.tsx"></script>'
        + "x" * 500
        + "</body></html>",
        encoding="utf-8",
    )
    assert sse.resolve_static_preview_relpath(tmp_path) is None


def test_resolve_prefers_nested_when_root_css_mismatched(tmp_path: Path):
    pad = "<!-- " + ("pad " * 80) + " -->"
    (tmp_path / "index.html").write_text(
        f"""<!DOCTYPE html><html><head>
<link rel="stylesheet" href="frontend/style.css">
</head><body>
<nav class="navbar"></nav>
<section class="hero-section"><a class="btn-primary">Try the Demo Now</a></section>
<div class="streak-pulse"></div>
{pad}
</body></html>""",
        encoding="utf-8",
    )
    (tmp_path / "style.css").write_text(
        ".navbar{display:flex}.hero-section{display:grid}.btn-primary{background:teal}.streak-pulse{animation:p 1s infinite}",
        encoding="utf-8",
    )
    (tmp_path / "frontend").mkdir()
    (tmp_path / "frontend" / "style.css").write_text(
        ".landing-nav{display:flex}.hero{padding:2rem}.cta-chip{background:#0d9488}.signature-streak{animation:pulse 1s}",
        encoding="utf-8",
    )
    (tmp_path / "frontend" / "index.html").write_text(
        f"""<!DOCTYPE html><html><head>
<link rel="stylesheet" href="./style.css">
</head><body>
<nav class="landing-nav"></nav>
<section class="hero"><span class="cta-chip">Go</span></section>
<div class="signature-streak"></div>
{pad}
</body></html>""",
        encoding="utf-8",
    )
    assert sse.resolve_static_preview_relpath(tmp_path) == "frontend/index.html"


def test_resolve_prefers_dist_over_vite_dev_shell(tmp_path: Path):
    (tmp_path / "frontend").mkdir()
    (tmp_path / "frontend" / "dist").mkdir(parents=True)
    (tmp_path / "frontend" / "index.html").write_text(
        "<!DOCTYPE html><script type='module' src='./src/main.tsx'></script>" + "x" * 500,
        encoding="utf-8",
    )
    (tmp_path / "frontend" / "dist" / "index.html").write_text(
        "<html><body>" + "built " * 80 + "</body></html>",
        encoding="utf-8",
    )
    assert sse.resolve_static_preview_relpath(tmp_path) == "frontend/dist/index.html"
