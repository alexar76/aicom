"""
Storefront visibility while a shipped product is in remediation.

The persistent flag lives in ``product_followup/{id}.json`` (see
``product_followup.storefront_established_listing``) so it survives SQLite
pipeline rows that only round-trip a subset of metadata keys.
"""

from __future__ import annotations

from typing import Any

from web.backend.services.product_followup import (
    merge_mark_storefront_established_listing,
    storefront_established_listing_enabled,
)

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


def maybe_persist_storefront_established_for_repair_hold(
    product_id: str,
    *,
    state_upper: str,
    has_generated_code: bool,
    storefront_blocked: bool,
) -> None:
    """
    Once a product has generated code and re-enters repair, keep the storefront card
  visible even if ``storefront_established_listing`` was never written at first ship.
    """
    if storefront_blocked or not has_generated_code:
        return
    if storefront_established_listing_enabled(product_id):
        return
    if state_upper not in REPAIR_LISTABLE_STATES:
        return
    merge_mark_storefront_established_listing(product_id)
    from web.backend.services.sandbox_remediation_badge import ensure_remediation_eta_recorded

    ensure_remediation_eta_recorded(product_id, state_upper=state_upper)


def established_storefront_pinned(
    product_id: str,
    *,
    has_generated_code: bool,
    storefront_blocked: bool,
) -> bool:
    """
    Once a product has been listed on the storefront, keep the card visible until
    an operator explicitly hides it or marks not_pursuing — regardless of quality
    re-checks or pipeline state (including COMPLETED while cycling repair).
    """
    if storefront_blocked or not has_generated_code:
        return False
    return storefront_established_listing_enabled(product_id)


def is_mid_repair_storefront_visible(
    product_id: str,
    product: dict[str, Any],
    *,
    state_upper: str,
    has_generated_code: bool,
    storefront_blocked: bool,
) -> bool:
    """Legacy name: repair-cycle visibility is a subset of ``established_storefront_pinned``."""
    if not established_storefront_pinned(
        product_id,
        has_generated_code=has_generated_code,
        storefront_blocked=storefront_blocked,
    ):
        return False
    if state_upper == "FAILED":
        return False
    if state_upper in REPAIR_LISTABLE_STATES:
        return True
    return state_upper in ("COMPLETED", "DEPLOYED_PRODUCTION")
