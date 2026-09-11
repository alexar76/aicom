"""build_seo_landings — graceful when courses/catalog.yaml is absent (trimmed GitHub mirror)."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import build_seo_landings as bsl  # noqa: E402


def test_load_courses_without_catalog_file(tmp_path, monkeypatch):
    monkeypatch.setattr(bsl, "CATALOG", tmp_path / "missing-catalog.yaml")
    monkeypatch.setattr(bsl, "ROOT", tmp_path)
    assert bsl._load_courses() == []


def test_build_oracles_skips_when_oracles_ts_missing(monkeypatch):
    monkeypatch.setattr(bsl, "ORACLES_TS", Path("/nonexistent/oracles.ts"))
    assert bsl._build_oracles("https://example.test", {}) == []


def test_build_learn_skips_when_no_courses(monkeypatch):
    monkeypatch.setattr(bsl, "_load_courses", lambda: [])
    assert bsl._build_learn("https://example.test", {}) == []
