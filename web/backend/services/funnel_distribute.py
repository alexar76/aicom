"""Post-COMPLETED distribution: hub listing, launch metadata."""

from __future__ import annotations

import logging
import os
import time
from typing import Any

logger = logging.getLogger(__name__)


def _truthy(name: str, default: str = "1") -> bool:
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes", "on")


def on_product_completed(product_id: str, product: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Best-effort growth actions when a product reaches COMPLETED.
    Does not lower quality gates — runs only after ship.
    """
    result: dict[str, Any] = {"product_id": product_id, "hub_list": None, "blog": False}
    pid = str(product_id or "").strip()
    if not pid:
        return result

    if _truthy("AIFACTORY_FUNNEL_AUTO_HUB_LIST", "1"):
        result["hub_list"] = _auto_hub_list(pid)

    try:
        from web.backend.services.product_blog import publish_product_launch_blog_post

        if publish_product_launch_blog_post(pid, product=product, capture_screenshot=True):
            result["blog"] = True
    except Exception:
        logger.warning("funnel distribute blog skipped for %s", pid, exc_info=True)

    result["distributed_at"] = time.time()
    return result


def _auto_hub_list(product_id: str) -> dict[str, Any] | None:
    try:
        from aimarket_hub.auto_listing import auto_list_product
        from aimarket_hub.database import HubDatabase
        from aimarket_hub.factory_bridge import import_factory_products
        from core.paths import pipeline_json_path

        db = HubDatabase()
        pipeline_path = str(pipeline_json_path())
        listed = auto_list_product(product_id, db=db, pipeline_path=pipeline_path)
        if not isinstance(listed, dict):
            listed = {"product_id": product_id, "listed_capabilities": listed}
        try:
            listed["factory_bridge_imported"] = import_factory_products(db, pipeline_path)
        except Exception as exc:
            listed["factory_bridge_error"] = str(exc)[:200]
        return listed
    except ImportError:
        logger.debug("aimarket-hub not available for auto_list")
        return None
    except Exception as e:
        logger.warning("funnel hub auto_list failed for %s: %s", product_id, e)
        return {"error": str(e)[:300]}
