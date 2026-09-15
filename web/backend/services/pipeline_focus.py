"""Apply or clear factory focus mode — one active pipeline product at a time."""

from __future__ import annotations

import logging
from typing import Any

from core.pipeline_product_pause import get_factory_focus_product_id

logger = logging.getLogger(__name__)

_TERMINAL_STATES = frozenset({"COMPLETED", "DEPLOYED_PRODUCTION", "FAILED", "CANCELLED"})
_PROFILE_WEIGHT = {"full_software": 100, "marketing_landing": 20, "landing_fast": 10}


def _delivery_profile(product: dict[str, Any]) -> str:
    spec = product.get("spec") or {}
    if isinstance(spec, str):
        spec = {}
    raw = product.get("delivery_profile") or (spec.get("delivery_profile") if isinstance(spec, dict) else None)
    return str(raw or "").strip().lower()


def suggest_focus_product(products: dict[str, dict[str, Any]]) -> str | None:
    """Pick the heaviest in-progress product (prefers full_software)."""
    best_id: str | None = None
    best_score = -1
    for pid, product in products.items():
        st = str(product.get("state") or "").upper()
        if st in _TERMINAL_STATES:
            continue
        dp = _delivery_profile(product)
        score = _PROFILE_WEIGHT.get(dp, 0)
        score += int(product.get("quality_repair_round") or 0) * 5
        if st in ("DEV_FIXING", "BUG_FOUND", "EVOLUTION_ANALYZING", "QA_TESTING"):
            score += 25
        if score > best_score:
            best_score = score
            best_id = str(pid)
    return best_id


def sync_pipeline_hold_flags(product_ids: list[str], *, focus_product_id: str | None) -> dict[str, bool]:
    """Mirror focus mode into per-product pipeline_on_hold for Pipeline UI."""
    from web.backend.services.product_followup import set_product_pipeline_on_hold

    holds: dict[str, bool] = {}
    focus = str(focus_product_id).strip() if focus_product_id else ""
    for pid in product_ids:
        on_hold = bool(focus and pid != focus)
        set_product_pipeline_on_hold(pid, on_hold)
        holds[pid] = on_hold
    return holds


def apply_pipeline_focus_mode(
    config,
    *,
    focus_product_id: str | None,
    resume_factory: bool = True,
    products: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Set ``general.factory_focus_product_id``, optionally resume the factory,
    and sync ``pipeline_on_hold`` on all known products.
    """
    from web.backend.api.admin.dashboard.helpers import _load_pipeline_products_for_metrics

    if products is None:
        products = _load_pipeline_products_for_metrics()

    pid = str(focus_product_id).strip() if focus_product_id else ""
    if pid and pid not in products:
        raise ValueError(f"Unknown product_id: {pid}")

    if pid:
        config.set("general.factory_focus_product_id", pid)
    else:
        config.set("general.factory_focus_product_id", None)

    if resume_factory:
        config.set("general.factory_on_hold", False)

    holds = sync_pipeline_hold_flags(list(products.keys()), focus_product_id=pid or None)
    paused_count = sum(1 for v in holds.values() if v)

    return {
        "focus_product_id": pid or None,
        "factory_on_hold": bool(config.get("general.factory_on_hold", False)),
        "paused_count": paused_count,
        "active_count": len(holds) - paused_count,
        "pipeline_holds": holds,
    }


def focus_mode_status(*, config: dict[str, Any] | None = None) -> dict[str, Any]:
    from web.backend.api.admin.dashboard.helpers import _load_pipeline_products_for_metrics

    products = _load_pipeline_products_for_metrics()
    focus_id = get_factory_focus_product_id(config=config)
    suggested = suggest_focus_product(products)
    paused = 0
    if focus_id:
        paused = sum(1 for pid in products if str(pid) != focus_id)
    return {
        "focus_product_id": focus_id,
        "suggested_product_id": suggested,
        "paused_count": paused,
        "active_count": max(0, len(products) - paused) if focus_id else len(products),
        "total_products": len(products),
    }
