"""Unit tests for SVG / DOM visual render audit helpers (no Playwright required)."""

from __future__ import annotations

from web.backend.services.visual_render_audit import (
    classify_visual_findings,
    svg_coordinate_spike_in_html,
)


def test_svg_coordinate_spike_detects_huge_literal():
    html = """<!DOCTYPE html><svg xmlns="http://www.w3.org/2000/svg"><path d="M 0 0 L 50000 0"/></svg>"""
    assert svg_coordinate_spike_in_html(html) is True


def test_svg_coordinate_spike_clean_diagram():
    html = """<!DOCTYPE html><svg xmlns="http://www.w3.org/2000/svg"><path d="M 0 0 L 120 80"/></svg>"""
    assert svg_coordinate_spike_in_html(html) is False


def test_classify_viewport_hog_fails_gate():
    fatal, warnings, gate_fail = classify_visual_findings(
        [
            {
                "code": "svg_painted_viewport_hog",
                "tag": "PATH",
                "svgIndex": 0,
                "cw": 900,
                "ch": 700,
                "phase": "after_ui_clicks",
            }
        ]
    )
    assert gate_fail is True
    assert fatal and "visual_svg_viewport_hog" in fatal[0]
    assert not warnings


def test_classify_path_count_warning_only():
    fatal, warnings, gate_fail = classify_visual_findings(
        [{"code": "svg_excessive_path_count", "svgIndex": 1, "n": 120}]
    )
    assert gate_fail is False
    assert not fatal
    assert warnings and "many_paths" in warnings[0]
