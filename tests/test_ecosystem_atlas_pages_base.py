"""Project Pages (/aicom/) must prefix atlas CSS/JS or the landing renders unstyled."""
from __future__ import annotations

import tempfile
from pathlib import Path

from scripts.build_ecosystem_atlas import build


def _assert_no_bare_ecosystem_atlas(html: str) -> None:
    assert 'href="/ecosystem-atlas/' not in html
    assert 'src="/ecosystem-atlas/' not in html


def test_github_project_pages_prefix_atlas_assets():
    with tempfile.TemporaryDirectory(prefix="atlas-pages-") as tmp:
        out = Path(tmp)
        build(out, "https://alexar76.github.io/aicom")
        html = (out / "index.html").read_text()
        assert 'href="/aicom/ecosystem-atlas/assets/site.css' in html
        assert 'src="/aicom/ecosystem-atlas/assets/scene.js' in html
        _assert_no_bare_ecosystem_atlas(html)
        assert (out / "ecosystem-atlas/assets/site.css").is_file()
        assert (out / "ecosystem-atlas/assets/scene.js").is_file()


def test_apex_host_keeps_root_absolute_atlas_assets():
    with tempfile.TemporaryDirectory(prefix="atlas-apex-") as tmp:
        out = Path(tmp)
        build(out, "https://ecosystem.modelmarket.dev")
        html = (out / "index.html").read_text()
        assert 'href="/ecosystem-atlas/assets/site.css' in html
        assert 'src="/ecosystem-atlas/assets/scene.js' in html
        assert 'href="/aicom/' not in html
