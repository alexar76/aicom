"""Sanitization and spam detection for storefront product titles."""

from __future__ import annotations

from web.backend.services.product_naming import (
    is_placeholder_product_name,
    sanitize_product_display_name,
)


def test_sanitize_collapses_duplicate_hex_runs():
    s = sanitize_product_display_name("EchoScribe 0C4C 0C4C 0C4C 0C4C")
    assert "0C4C 0C4C 0C4C" not in s
    assert s.startswith("EchoScribe")


def test_spam_name_blocked_for_marketplace_gate():
    assert is_placeholder_product_name("EchoScribe 0C4C 0C4C 0C4C 0C4C") is True


def test_collision_style_numeric_suffix_not_spam():
    assert is_placeholder_product_name("EchoScribe (472)") is False
