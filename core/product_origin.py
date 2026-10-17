"""Classify how a pipeline product entered the factory.

**On-demand** = explicitly requested by a human (admin "New product", the public
guest fast-path landing generator). **Autonomous** = produced by the Director /
Discovery layer without a direct human request.

This distinction is recorded on products for analytics; it does **not** bypass
factory pause — when ``general.factory_on_hold`` is set, all agent work stops.
"""

from __future__ import annotations

from typing import Any


#: How a public submission's brief begins: the guest landing generator's charter and the
#: funnel lead form. Products created before ``visitor_submission`` existed carry only this.
_VISITOR_BRIEF_PREFIXES = ("PRIMARY DELIVERABLE (guest)", "Funnel lead from ")


def is_visitor_submission(product: Any) -> bool:
    """True when a member of the public wrote this idea (guest landing generator, funnel form).

    Their wording is theirs, not a showcase: it stays out of the public build gallery, its
    replay permalink, the sitemap and the storefront grid (owner, 2026-10-14). The /builds page
    printed a visitor's company name verbatim, and half its cards were unbuilt guest ideas.

    Detection: the ``visitor_submission`` marker set at creation; the funnel's persisted
    ``owner_email`` / ``funnel_lead_source``; a ``guest-*`` / ``funnel-lead`` tag where tags
    survived; and, for older rows whose tags the SQL store dropped, the brief's prefix.
    """
    if not isinstance(product, dict):
        return False
    if product.get("visitor_submission"):
        return True
    if product.get("owner_email") or product.get("funnel_lead_source"):
        return True
    meta = product.get("metadata") if isinstance(product.get("metadata"), dict) else {}
    for tags in (product.get("tags"), meta.get("tags")):
        if isinstance(tags, (list, tuple)) and any(
            str(t) == "funnel-lead" or str(t).startswith("guest-") for t in tags
        ):
            return True
    return str(product.get("admin_instructions") or "").startswith(_VISITOR_BRIEF_PREFIXES)


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
