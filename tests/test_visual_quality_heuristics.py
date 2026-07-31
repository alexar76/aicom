"""Unit tests for static visual quality heuristics (Phase 3 gate helpers)."""

from __future__ import annotations

from pathlib import Path

import pytest

from web.backend.services.visual_quality_heuristics import (
    VISUAL_STRICT_GATE_CODES,
    analyze_visual_quality,
    visual_issues_penalty,
)


def test_golden_fixture_passes_app_like_heuristics():
    root = Path(__file__).resolve().parent / "fixtures" / "visual_standards_golden"
    idx = (root / "index.html").read_text(encoding="utf-8")
    css = (root / "style.css").read_text(encoding="utf-8")
    js = (root / "app.js").read_text(encoding="utf-8")
    spec = {"delivery_profile": "full_software"}
    issues = analyze_visual_quality(
        index_html=idx,
        css_bundle=css,
        js_bundle=js,
        spec=spec,
    )
    codes = {i["code"] for i in issues}
    assert not (codes & VISUAL_STRICT_GATE_CODES)


def test_minimal_html_triggers_strict_codes():
    idx = "<html><body><p>x</p></body></html>"
    issues = analyze_visual_quality(
        index_html=idx,
        css_bundle="body{color:red}",
        js_bundle="",
        spec={"delivery_profile": "full_software"},
    )
    codes = {i["code"] for i in issues}
    assert "visual_missing_html_lang" in codes
    assert "visual_missing_viewport_meta" in codes
    assert "visual_insufficient_design_tokens" in codes


def test_visual_penalty_non_negative():
    issues = [{"code": "visual_weak_focus_styles", "detail": "x"}]
    assert visual_issues_penalty(issues) >= 3
