"""Per-product pipeline pause and factory focus mode (one active product at a time)."""

from __future__ import annotations

import logging
from typing import Any

from core.config_merge import load_merged_config
from core.paths import config_path

logger = logging.getLogger(__name__)

FOCUS_CONFIG_KEY = "general.factory_focus_product_id"


def _raw_focus_value(config: dict[str, Any] | None = None) -> Any:
    if config is not None:
        general = config.get("general")
        if isinstance(general, dict):
            return general.get("factory_focus_product_id")
        return config.get(FOCUS_CONFIG_KEY)
    try:
        merged = load_merged_config(config_path())
    except Exception as exc:
        logger.debug("factory_focus_product_id config read failed: %s", exc)
        return None
    general = merged.get("general")
    return general.get("factory_focus_product_id") if isinstance(general, dict) else None


def get_factory_focus_product_ids(*, config: dict[str, Any] | None = None) -> list[str]:
    """Products allowed to receive pipeline agent/LLM work while focus mode is on.

    Accepts a single id, a comma-separated string, or a YAML list — an operator
    reworking two products at once should not have to choose between them.
    """
    raw = _raw_focus_value(config)
    if raw is None:
        return []
    if isinstance(raw, (list, tuple, set)):
        candidates = [str(x) for x in raw]
    else:
        candidates = str(raw).replace(";", ",").split(",")
    return [pid for pid in (c.strip() for c in candidates) if pid]


def get_factory_focus_product_id(*, config: dict[str, Any] | None = None) -> str | None:
    """First focus product, or ``None``. Kept for single-target callers/UI."""
    ids = get_factory_focus_product_ids(config=config)
    return ids[0] if ids else None


def is_product_pipeline_work_paused(product_id: str, *, config: dict[str, Any] | None = None) -> bool:
    """
    When True, the pipeline worker skips starting, executing, retrying, and idle-healing
    tasks for this product. Focus mode pauses all products except the focus target.
    """
    pid = str(product_id or "").strip()
    if not pid:
        return False
    focus_ids = get_factory_focus_product_ids(config=config)
    if focus_ids and pid not in focus_ids:
        return True
    try:
        from web.backend.services.product_followup import is_product_pipeline_on_hold

        return is_product_pipeline_on_hold(pid)
    except Exception:
        return False


def is_factory_focus_mode_active(*, config: dict[str, Any] | None = None) -> bool:
    return bool(get_factory_focus_product_ids(config=config))
