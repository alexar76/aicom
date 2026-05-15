from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

QUEUE_PATH = Path("/app/data/state/batch_pipeline_queue.json")


def _default_queue_doc() -> dict[str, Any]:
    return {"updated_at": time.time(), "items": []}


def load_batch_queue(path: Path = QUEUE_PATH) -> dict[str, Any]:
    if not path.exists():
        return _default_queue_doc()
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(doc, dict):
            return _default_queue_doc()
        if not isinstance(doc.get("items"), list):
            doc["items"] = []
        return doc
    except Exception:
        return _default_queue_doc()


def save_batch_queue(doc: dict[str, Any], path: Path = QUEUE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    doc["updated_at"] = time.time()
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")


def enqueue_batch_items(items: list[dict[str, Any]], path: Path = QUEUE_PATH) -> None:
    doc = load_batch_queue(path)
    existing = doc.get("items") if isinstance(doc.get("items"), list) else []
    existing.extend(items)
    doc["items"] = existing[-5000:]
    save_batch_queue(doc, path)


def summarize_batch(batch_id: str, path: Path = QUEUE_PATH) -> dict[str, Any]:
    doc = load_batch_queue(path)
    rows = [x for x in (doc.get("items") or []) if str(x.get("batch_id")) == batch_id]
    by_status: dict[str, int] = {}
    created_products: list[str] = []
    for row in rows:
        st = str(row.get("status") or "unknown")
        by_status[st] = by_status.get(st, 0) + 1
        if st == "created" and row.get("product_id"):
            created_products.append(str(row.get("product_id")))
    return {
        "batch_id": batch_id,
        "count": len(rows),
        "status_counts": by_status,
        "created_products": created_products,
        "items": rows[-200:],
        "updated_at": doc.get("updated_at"),
    }


def retry_failed_items(batch_id: str, path: Path = QUEUE_PATH) -> dict[str, Any]:
    doc = load_batch_queue(path)
    items = doc.get("items") if isinstance(doc.get("items"), list) else []
    retried = 0
    now = time.time()
    for row in items:
        if str(row.get("batch_id")) != batch_id:
            continue
        if str(row.get("status")) == "failed":
            row["status"] = "queued"
            row.pop("error", None)
            row["updated_at"] = now
            retried += 1
    doc["items"] = items
    save_batch_queue(doc, path)
    return {"batch_id": batch_id, "retried": retried}


def _active_products_count(products: dict[str, Any]) -> int:
    active = 0
    for p in products.values():
        st = str((p or {}).get("state") or "").upper()
        if st not in ("COMPLETED", "FAILED", "CANCELLED"):
            active += 1
    return active


def _build_product_from_queue_item(item: dict[str, Any]) -> dict[str, Any]:
    from llm.content_languages import product_locale_fields

    product_id = f"prod-{uuid.uuid4().hex[:12]}"
    ts = time.time()
    locale_fields = product_locale_fields(
        interface_locale=item.get("interface_locale"),
        content_locale=item.get("content_locale"),
    )
    return {
        "id": product_id,
        "idea": str(item.get("idea") or "").strip(),
        "admin_instructions": item.get("admin_instructions"),
        "delivery_profile": str(item.get("delivery_profile") or "full_software"),
        "production_mode": bool(item.get("production_mode", False)),
        **locale_fields,
        "category": "saas",
        "tags": [],
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


def drain_batch_queue_into_state(
    state: dict[str, Any],
    max_to_start: int = 2,
    active_limit: int = 30,
    path: Path = QUEUE_PATH,
) -> dict[str, Any]:
    """
    Materialize queued ideas into pipeline products with concurrency control.
    """
    doc = load_batch_queue(path)
    items = doc.get("items") if isinstance(doc.get("items"), list) else []
    products = state.get("products") if isinstance(state.get("products"), dict) else {}
    started = 0
    active_count = _active_products_count(products)
    now = time.time()
    for item in items:
        if started >= max_to_start:
            break
        if str(item.get("status") or "") != "queued":
            continue
        if active_count >= active_limit:
            break
        idea = str(item.get("idea") or "").strip()
        if not idea:
            item["status"] = "failed"
            item["error"] = "empty idea"
            item["updated_at"] = now
            continue
        product = _build_product_from_queue_item(item)
        products[product["id"]] = product
        item["status"] = "created"
        item["product_id"] = product["id"]
        item["updated_at"] = now
        started += 1
        active_count += 1
    state["products"] = products
    doc["items"] = items
    save_batch_queue(doc, path)
    return {"started": started, "remaining": len([x for x in items if str(x.get("status")) == "queued"])}
