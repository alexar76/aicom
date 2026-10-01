"""HTML class names must link the CSS that actually styles them."""

from __future__ import annotations

from pathlib import Path

from web.backend.services.preview_stylesheet_heal import (
    heal_product_stylesheets,
    preview_fit_score,
)
from web.backend.services.visual_gate_autofix import apply_visual_gate_autofix


def _pulse_tree(root: Path) -> None:
    (root / "index.html").write_text(
        """<!DOCTYPE html><html><head>
<link rel="stylesheet" href="frontend/fonts.css">
<link rel="stylesheet" href="frontend/style.css">
</head><body>
<nav class="navbar"></nav>
<section class="hero-section"><a class="btn-primary" href="#demo">Try the Demo Now</a></section>
<div class="streak-pulse"></div>
</body></html>""",
        encoding="utf-8",
    )
    (root / "style.css").write_text(
        """
.navbar { display: flex; background: #0f766e; }
.hero-section { display: grid; }
.btn-primary { background: #14b8a6; color: #fff; }
.streak-pulse { animation: pulse 1.4s ease-in-out infinite; }
@keyframes pulse { 50% { opacity: 0.55; } }
""",
        encoding="utf-8",
    )
    (root / "frontend").mkdir()
    (root / "frontend" / "fonts.css").write_text(
        "@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500&display=swap');\n",
        encoding="utf-8",
    )
    (root / "frontend" / "style.css").write_text(
        """
.landing-nav { display: flex; }
.hero { padding: 4rem 0; }
.cta-chip { background: #0d9488; }
.signature-streak { animation: pulse 1s infinite; }
""",
        encoding="utf-8",
    )
    (root / "frontend" / "index.html").write_text(
        """<!DOCTYPE html><html><head>
<link rel="stylesheet" href="./fonts.css">
<link rel="stylesheet" href="./style.css">
</head><body>
<nav class="landing-nav"></nav>
<section class="hero"><span class="cta-chip">Go</span></section>
<div class="signature-streak"></div>
</body></html>""",
        encoding="utf-8",
    )


def test_heal_relinks_root_html_to_matching_theme(tmp_path: Path):
    _pulse_tree(tmp_path)
    assert preview_fit_score(tmp_path, "index.html") < 2
    changed = heal_product_stylesheets(tmp_path)
    assert "index.html" in changed
    html = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert "frontend/fonts.css" in html
    assert 'href="frontend/style.css"' not in html
    assert "style.css" in html
    assert preview_fit_score(tmp_path, "index.html") >= 3


def test_autofix_heals_stylesheet_mismatch(tmp_path: Path):
    _pulse_tree(tmp_path)
    apply_visual_gate_autofix(tmp_path)
    html = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert 'href="frontend/style.css"' not in html
    assert "#1d4ed8" not in html
