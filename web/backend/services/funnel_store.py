"""Persistent funnel leads and waitlist (file-backed)."""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)
_lock = threading.Lock()


def funnel_dir() -> Path:
    from core.paths import data_root

    root = Path(os.environ.get("AIFACTORY_FUNNEL_DIR", str(data_root() / "funnel")))
    root.mkdir(parents=True, exist_ok=True)
    return root


def leads_path() -> Path:
    return funnel_dir() / "leads.json"


def waitlist_path() -> Path:
    return funnel_dir() / "waitlist.jsonl"


def _load_leads_doc() -> dict[str, Any]:
    p = leads_path()
    if not p.is_file():
        return {"leads": {}, "by_token": {}, "by_product": {}}
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(doc, dict):
            doc.setdefault("leads", {})
            doc.setdefault("by_token", {})
            doc.setdefault("by_product", {})
            return doc
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("funnel leads.json unreadable: %s", e)
    return {"leads": {}, "by_token": {}, "by_product": {}}


def _save_leads_doc(doc: dict[str, Any]) -> None:
    p = leads_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(p)


def create_lead_record(
    *,
    email: str,
    idea: str,
    name: str = "",
    company: str = "",
    source: str = "lead_page",
    referral: str | None = None,
    product_id: str | None = None,
) -> dict[str, Any]:
    lead_id = f"lead-{uuid.uuid4().hex[:12]}"
    token = uuid.uuid4().hex
    now = time.time()
    row = {
        "id": lead_id,
        "status_token": token,
        "email": email.strip(),
        "name": (name or "").strip(),
        "company": (company or "").strip(),
        "idea": idea.strip(),
        "source": source,
        "referral": referral,
        "product_id": product_id,
        "status": "received" if not product_id else "pipeline_started",
        "created_at": now,
        "updated_at": now,
        "completed_at": None,
        "notify_sent_at": None,
    }
    with _lock:
        doc = _load_leads_doc()
        doc["leads"][lead_id] = row
        doc["by_token"][token] = lead_id
        if product_id:
            doc["by_product"][product_id] = lead_id
        _save_leads_doc(doc)
    return dict(row)


def update_lead(lead_id: str, **fields: Any) -> dict[str, Any] | None:
    with _lock:
        doc = _load_leads_doc()
        row = doc["leads"].get(lead_id)
        if not row:
            return None
        row.update(fields)
        row["updated_at"] = time.time()
        if fields.get("product_id"):
            doc["by_product"][str(fields["product_id"])] = lead_id
        doc["leads"][lead_id] = row
        _save_leads_doc(doc)
        return dict(row)


def get_lead_by_token(token: str) -> dict[str, Any] | None:
    doc = _load_leads_doc()
    lead_id = doc.get("by_token", {}).get(token)
    if not lead_id:
        return None
    row = doc.get("leads", {}).get(lead_id)
    return dict(row) if row else None


def get_lead_by_product(product_id: str) -> dict[str, Any] | None:
    doc = _load_leads_doc()
    lead_id = doc.get("by_product", {}).get(product_id)
    if not lead_id:
        return None
    row = doc.get("leads", {}).get(lead_id)
    return dict(row) if row else None


def list_leads(limit: int = 500) -> list[dict[str, Any]]:
    doc = _load_leads_doc()
    rows = list(doc.get("leads", {}).values())
    rows.sort(key=lambda r: float(r.get("created_at") or 0), reverse=True)
    return rows[: max(1, limit)]


def append_waitlist_entry(
    *,
    product_id: str,
    email: str,
    name: str = "",
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    row = {
        "ts": time.time(),
        "product_id": product_id.strip(),
        "email": email.strip(),
        "name": (name or "").strip(),
        "meta": meta or {},
    }
    p = waitlist_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        with open(p, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row
