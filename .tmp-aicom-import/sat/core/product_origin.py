"""Classify how a pipeline product entered the factory.

**On-demand** = explicitly requested by a human (admin "New product", the public
guest fast-path landing generator). **Autonomous** = produced by the Director /
Discovery layer without a direct human request.

This distinction is recorded on products for analytics; it does **not** bypass
factory pause — when ``general.factory_on_hold`` is set, all agent work stops.
"""

from __future__ import annotations

from typing import Any


def is_on_demand_product(product: Any) -> bool:
    """True when the product was explicitly requested by a human.

    Detection order (any match wins):
      1. ``on_demand`` marker — set by the web API at creation
         (``web.backend.main._append_product_to_pipeline``).
      2. ``landing_fast_path`` — guest/admin fast-path landings are always
         human-requested. (The landing fast-path agents ``landing_architect`` /
         ``landing_developer`` are mirrored across the codebase; this is one of
         the places that special-cases the fast path.)
      3. A ``guest-*`` tag — defensive fallback for guest landings created before
         the ``on_demand`` marker existed.
    """
    if not isinstance(product, dict):
        return False
    if product.get("on_demand"):
        return True
    if product.get("landing_fast_path"):
        return True
    tags = product.get("tags")
    if isinstance(tags, (list, tuple)):
        for tag in tags:
            ts = str(tag)
            if ts == "guest-landing" or ts.startswith("guest-"):
                return True
    return False
