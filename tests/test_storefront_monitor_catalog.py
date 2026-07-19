"""Storefront monitor-catalog — real product ids only (no synthetic placeholders)."""

from __future__ import annotations

import asyncio
from unittest.mock import patch


def test_monitor_catalog_returns_real_product_ids():
    with patch(
        "web.backend.services.storefront_counts_cache.get_storefront_categories_cached",
        return_value={
            "categories": [{"id": "saas", "name": "SaaS", "product_count": 1}],
            "total_count": 2,
            "listings": [
                {"id": "prod-real-1", "name": "Real One", "category": "saas", "is_template": False},
                {"id": "prod-real-2", "name": "Real Two", "category": "landings", "is_template": False},
            ],
            "pending": False,
            "stale": False,
        },
    ):
        from web.backend.api.products import monitor_catalog

        body = asyncio.run(monitor_catalog())
    assert body["count"] == 2
    assert body["products"][0]["id"] == "prod-real-1"
    assert all(not p["id"].startswith("cat-") for p in body["products"])


def test_monitor_catalog_pending_without_rows():
    with patch(
        "web.backend.services.storefront_counts_cache.get_storefront_categories_cached",
        return_value={
            "categories": [],
            "total_count": None,
            "listings": [],
            "pending": True,
            "stale": False,
        },
    ):
        from web.backend.api.products import monitor_catalog

        body = asyncio.run(monitor_catalog())
    assert body["products"] == []
    assert body["pending"] is True
