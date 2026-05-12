"""Storefront keeps listing products that were once marketplace-eligible while they re-run repair."""

from __future__ import annotations

import pytest


def test_merge_mark_storefront_established_listing(tmp_path, monkeypatch):
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path))
    from web.backend.services import product_followup as pf

    assert pf.merge_mark_storefront_established_listing("prod-a") is True
    assert pf.merge_mark_storefront_established_listing("prod-a") is False
    assert pf.storefront_established_listing_enabled("prod-a") is True


def test_mid_repair_visible_only_with_flag_and_state(tmp_path, monkeypatch):
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path))
    from web.backend.services.product_followup import merge_mark_storefront_established_listing
    from web.backend.services.storefront_visibility import is_mid_repair_storefront_visible

    pid = "prod-b"
    merge_mark_storefront_established_listing(pid)
    product = {"state": "BUG_FOUND"}
    assert is_mid_repair_storefront_visible(
        pid,
        product,
        state_upper="BUG_FOUND",
        has_generated_code=True,
        storefront_blocked=False,
    )
    assert not is_mid_repair_storefront_visible(
        "prod-unknown",
        product,
        state_upper="BUG_FOUND",
        has_generated_code=True,
        storefront_blocked=False,
    )
    assert not is_mid_repair_storefront_visible(
        pid,
        product,
        state_upper="IDEA_RECEIVED",
        has_generated_code=True,
        storefront_blocked=False,
    )


def test_mid_repair_matches_storefront_grid_branch(monkeypatch, tmp_path):
    """Mirrors the mid-repair branch of ``_public_storefront_grid_accepts`` without importing FastAPI."""
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path))
    from web.backend.services.product_followup import merge_mark_storefront_established_listing
    from web.backend.services.storefront_visibility import is_mid_repair_storefront_visible

    pid = "prod-grid-1"
    product = {"id": pid, "state": "BUG_FOUND"}
    merge_mark_storefront_established_listing(pid)
    assert is_mid_repair_storefront_visible(
        pid,
        product,
        state_upper="BUG_FOUND",
        has_generated_code=True,
        storefront_blocked=False,
    )
