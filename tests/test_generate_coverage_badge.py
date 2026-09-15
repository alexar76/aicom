"""Tests for scripts/generate_coverage_badge.py."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.generate_coverage_badge import _color, main


def test_color_thresholds() -> None:
    assert _color(85) == "#4c1"
    assert _color(65) == "#97ca00"
    assert _color(45) == "#dfb317"
    assert _color(25) == "#fe7d37"
    assert _color(10) == "#e05d44"


def test_generate_coverage_badge(tmp_path: Path) -> None:
    cov = tmp_path / "coverage.json"
    out = tmp_path / "badge.svg"
    cov.write_text(
        json.dumps({"totals": {"percent_covered": 45.6}}),
        encoding="utf-8",
    )
    assert main([str(cov), str(out)]) == 0
    svg = out.read_text(encoding="utf-8")
    assert "coverage" in svg
    assert "46%" in svg
