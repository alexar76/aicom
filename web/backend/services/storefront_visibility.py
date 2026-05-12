"""
Storefront visibility while a shipped product is in remediation.

The persistent flag lives in ``product_followup/{id}.json`` (see
``product_followup.storefront_established_listing``) so it survives SQLite
pipeline rows that only round-trip a subset of metadata keys.
"""

from __future__ import annotations

from typing import Any

from web.backend.services.product_followup import storefront_established_listing_enabled

# Pipeline states after a product has shipped and is cycling through repair agents again.
REPAIR_LISTABLE_STATES = frozenset(
    {
        "BUG_FOUND",
        "DEV_FIXING",
        "CODE_COMMITTED",
        "CODE_TESTING",
        "QA_TESTING",
        "SECURITY_SCANNED",
        "SALES_ACTIVE",
        "SANDBOX_RUNNING",
        "TELEMETRY_COLLECTING",
        "EVOLUTION_ANALYZING",
        "HUMAN_REVIEW_PENDING",
    }
)


def is_mid_repair_storefront_visible(
    product_id: str,
    product: dict[str, Any],
    *,
    state_upper: str,
    has_generated_code: bool,
    storefront_blocked: bool,
) -> bool:
    if not storefront_established_listing_enabled(product_id):
        return False
    if storefront_blocked or not has_generated_code:
        return False
    if state_upper in ("FAILED", "COMPLETED", "DEPLOYED_PRODUCTION"):
        return False
    return state_upper in REPAIR_LISTABLE_STATES
