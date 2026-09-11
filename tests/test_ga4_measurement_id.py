"""Tests for GA4 measurement id extraction from admin head HTML."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.ga4_measurement_id import extract_ga4_measurement_id_from_html  # noqa: E402


def test_loader_url_uppercase():
    html = '<script async src="https://www.googletagmanager.com/gtag/js?id=G-67NJ81W2YY"></script>'
    assert extract_ga4_measurement_id_from_html(html) == "G-67NJ81W2YY"


def test_loader_url_lowercase():
    html = '<script async src="https://www.googletagmanager.com/gtag/js?id=g-67nj81w2yy"></script>'
    assert extract_ga4_measurement_id_from_html(html) == "G-67NJ81W2YY"


def test_gtag_config_single_quotes():
    html = "window.foo=1; gtag('config', 'g-67nj81w2yy');"
    assert extract_ga4_measurement_id_from_html(html) == "G-67NJ81W2YY"


def test_html_entity_quoted():
    html = '&lt;script src=&quot;https://www.googletagmanager.com/gtag/js?id=G-67NJ81W2YY&quot;&gt;&lt;/script&gt;'
    assert extract_ga4_measurement_id_from_html(html) == "G-67NJ81W2YY"


def test_measurement_id_json():
    html = '{"measurement_id":"G-ABCDEFGHIJK"}'
    assert extract_ga4_measurement_id_from_html(html) == "G-ABCDEFGHIJK"
