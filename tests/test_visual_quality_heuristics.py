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


def test_tailwind_breakpoints_count_as_tokens_and_media():
    issues = analyze_visual_quality(
        index_html='<html lang="en"><head><meta name="viewport" content="width=device-width"></head>'
        '<body><div id="root"></div></body></html>',
        css_bundle="@tailwind base; @tailwind components; @tailwind utilities;",
        js_bundle='<main className="sm:grid md:flex lg:hidden"><h1>Sentinel</h1></main>',
        spec={"delivery_profile": "marketing_landing"},
    )
    codes = {i["code"] for i in issues}
    assert "visual_insufficient_design_tokens" not in codes, codes
    assert "visual_no_media_queries" not in codes, codes
    assert "visual_weak_main_landmark" not in codes, codes


def test_jsx_loading_flag_counts_as_skeleton():
    issues = analyze_visual_quality(
        index_html='<html lang="en"><head><meta name="viewport" content="width=device-width"></head>'
        "<body><main></main></body></html>",
        css_bundle=":root { --bg: #111; --text: #eee; --accent: #0f0; } :focus-visible { outline: 1px solid #0f0; }",
        js_bundle="""
          const [loading, setLoading] = useState(true);
          const [error, setError] = useState(null);
          return (
            <main>
              {loading && <Spinner />}
              {error && <p>failed</p>}
              {items.length === 0 && <p>no results</p>}
              <div aria-live="polite" className="toast" />
            </main>
          );
        """,
        spec={"delivery_profile": "full_software"},
    )
    codes = {i["code"] for i in issues}
    assert "visual_app_missing_skeleton" not in codes, codes
    assert "visual_app_missing_empty_state" not in codes, codes
    assert "visual_app_missing_error_ui" not in codes, codes
