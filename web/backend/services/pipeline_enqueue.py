"""
Append a product to the active pipeline store (SQL or JSON per ``pipeline_uses_sql_store``).
"""

from __future__ import annotations

import logging
import time
import uuid

from core.pipeline_state_writer import append_product_to_pipeline_state as _append_product

logger = logging.getLogger(__name__)


def append_product_to_pipeline_state(
    product: dict,
    *,
    pipeline_path=None,
) -> None:
    """Merge ``product`` into the configured pipeline backend (see ``core.pipeline_state_writer``)."""
    if not _append_product(product, pipeline_path=pipeline_path):
        raise RuntimeError(f"Failed to append product {product.get('id')} to pipeline store")
    try:
        from web.backend.services.telegram_pipeline_notify import notify_telegram_new_product

        notify_telegram_new_product(
            product_id=str(product.get("id") or ""),
            idea_snippet=str(product.get("idea") or ""),
            source="owner_chat",
        )
    except Exception:
        pass


def build_minimal_product_from_idea(idea: str, admin_instructions: str) -> dict:
    """Create a pipeline product dict (IDEA_RECEIVED) for Owner-originated ideas."""
    product_id = f"prod-{uuid.uuid4().hex[:12]}"
    ts = time.time()
    return {
        "id": product_id,
        "idea": (idea or "").strip(),
        "category": "saas",
        "tags": ["owner-chat"],
        "delivery_profile": "full_software",
        "admin_instructions": admin_instructions,
        "state": "IDEA_RECEIVED",
        "created_at": ts,
        "updated_at": ts,
        "tasks": [],
        "spec": None,
        "architecture": None,
        "code": None,
        "marketing": None,
        "pricing": None,
        "evolution_history": [],
    }
