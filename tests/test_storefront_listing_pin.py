"""Storefront: established pin keeps listed products during repair; new listings use quality gates."""

from __future__ import annotations

from unittest.mock import patch

from web.backend.api.products import public_storefront_listing_eligible


def test_established_pin_keeps_dev_fixing_on_storefront():
    pid = "prod-established-pin"
    product = {"state": "DEV_FIXING", "id": pid}
    with patch("web.backend.api.products._product_has_code", return_value=True), patch(
        "web.backend.api.products.public_storefront_blocked",
        return_value=False,
    ), patch(
        "web.backend.api.products._storefront_front_page_gate",
        return_value=(True, []),
    ), patch(
        "web.backend.api.products.established_storefront_pinned",
        return_value=True,
    ), patch(
        "web.backend.api.products.is_mid_repair_storefront_visible",
        return_value=False,
    ):
        ok, reasons = public_storefront_listing_eligible(pid, product)
    assert ok is True
    assert "listed_established_storefront_never_unlisted" in reasons


def test_no_front_page_blocks_even_when_pinned():
    pid = "prod-no-morda"
    product = {"state": "DEV_FIXING", "id": pid}
    with patch("web.backend.api.products._product_has_code", return_value=True), patch(
        "web.backend.api.products.public_storefront_blocked",
        return_value=False,
    ), patch(
        "web.backend.api.products._storefront_front_page_gate",
        return_value=(False, ["storefront_front_page_required", "no_front_page_html"]),
    ):
        ok, reasons = public_storefront_listing_eligible(pid, product)
    assert ok is False
    assert "storefront_front_page_required" in reasons
