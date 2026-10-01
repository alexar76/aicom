"""Smoke: packaging full_stack_fastapi HTML passes visual-quality heuristics for app-like spec."""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PKG_ROOT = ROOT / "packaging" / "templates" / "full_stack_fastapi"


def _load_packaging_app():
    path = PKG_ROOT / "app" / "main.py"
    spec = importlib.util.spec_from_file_location("_pkg_full_stack_main", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.app


@pytest.fixture(scope="module")
def full_stack_app():
    pytest.importorskip("fastapi")
    return _load_packaging_app()


def _inline_scripts(html: str) -> str:
    parts = []
    for m in re.finditer(r"<script([^>]*)>([\s\S]*?)</script>", html, re.I):
        attrs = m.group(1) or ""
        if re.search(r"\bsrc\s*=", attrs, re.I):
            continue
        parts.append(m.group(2) or "")
    return "\n".join(parts)


def test_packaging_dashboard_passes_visual_heuristics(full_stack_app):
    from fastapi.testclient import TestClient

    from web.backend.services.demo_quality import _collect_css_rules
    from web.backend.services.visual_quality_heuristics import (
        VISUAL_STRICT_GATE_CODES,
        analyze_visual_quality,
    )

    client = TestClient(full_stack_app)
    r = client.get("/")
    assert r.status_code == 200
    html = r.text
    css = _collect_css_rules(html, "")
    js = _inline_scripts(html)
    spec = {"delivery_profile": "full_software"}
    issues = analyze_visual_quality(index_html=html, css_bundle=css, js_bundle=js, spec=spec)
    strict_hits = {i["code"] for i in issues} & VISUAL_STRICT_GATE_CODES
    assert not strict_hits, issues
