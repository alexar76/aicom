"""
Append a product to pipeline.json + optional SQLite sync (shared by API and Owner-chat routing).
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_PIPELINE = Path("/app/data/state/pipeline.json")
DEFAULT_DB = os.environ.get("SQLITE_PATH", "/app/data/state/pipeline.db")


def _sync_sqlite_from_json(json_path: Path) -> None:
    if os.environ.get("USE_SQLITE", "").lower() not in ("1", "true", "yes"):
        return
    try:
        from orchestrator.migrate import migrate

        migrate(json_path=str(json_path), db_path=DEFAULT_DB)
    except Exception as e:
        logger.warning("SQLite sync after pipeline write skipped: %s", e)


def append_product_to_pipeline_state(
    product: dict,
    *,
    pipeline_path: Path | None = None,
) -> None:
    """Merge ``product`` into ``pipeline.json`` and migrate to SQLite when enabled."""
    state_file = pipeline_path or DEFAULT_PIPELINE
    if state_file.exists():
        state = json.loads(state_file.read_text(encoding="utf-8"))
    else:
        state = {"products": {}, "task_queue": [], "current_task_id": None}
    state.setdefault("task_queue", [])
    state.setdefault("products", {})
    state["products"][product["id"]] = product
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    _sync_sqlite_from_json(state_file)
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
