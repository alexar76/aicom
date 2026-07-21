"""Per-product pipeline pause and factory focus mode (one active product at a time)."""

from __future__ import annotations

import logging
from typing import Any

from core.config_merge import load_merged_config
from core.paths import config_path

logger = logging.getLogger(__name__)

FOCUS_CONFIG_KEY = "general.factory_focus_product_id"


def get_factory_focus_product_id(*, config: dict[str, Any] | None = None) -> str | None:
    """When set, only this product receives pipeline agent/LLM work."""
    if config is not None:
        general = config.get("general")
        if isinstance(general, dict):
            raw = general.get("factory_focus_product_id")
        else:
            raw = config.get(FOCUS_CONFIG_KEY)
    else:
        try:
            merged = load_merged_config(config_path())
        except Exception as exc:
            logger.debug("factory_focus_product_id config read failed: %s", exc)
            return None
        general = merged.get("general")
        raw = general.get("factory_focus_product_id") if isinstance(general, dict) else None
    if raw is None:
        return None
    pid = str(raw).strip()
    return pid or None


def is_product_pipeline_work_paused(product_id: str, *, config: dict[str, Any] | None = None) -> bool:
    """
    When True, the pipeline worker skips starting, executing, retrying, and idle-healing
    tasks for this product. Focus mode pauses all products except the focus target.
    """
    pid = str(product_id or "").strip()
    if not pid:
        return False
    focus_id = get_factory_focus_product_id(config=config)
    if focus_id and pid != focus_id:
        return True
    try:
        from web.backend.services.product_followup import is_product_pipeline_on_hold

        return is_product_pipeline_on_hold(pid)
    except Exception:
        return False


def is_factory_focus_mode_active(*, config: dict[str, Any] | None = None) -> bool:
    return get_factory_focus_product_id(config=config) is not None
