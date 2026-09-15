"""Server-side product creation templates (synced across devices for the same factory data dir)."""

from __future__ import annotations

import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any

from core.paths import data_root as factory_data_root

logger = logging.getLogger(__name__)

MAX_TEMPLATES = 64


def _path() -> Path:
    p = factory_data_root() / "config" / "user_iteration_templates.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _load() -> list[dict[str, Any]]:
    path = _path()
    if not path.is_file():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, list) else []
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("user_iteration_templates: load failed: %s", e)
        return []


def _save(rows: list[dict[str, Any]]) -> None:
    path = _path()
    path.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")


def list_templates() -> list[dict[str, Any]]:
    rows = _load()
    rows.sort(key=lambda r: float(r.get("updated_at") or r.get("created_at") or 0), reverse=True)
    return rows[:MAX_TEMPLATES]


def upsert_template(
    *,
    template_id: str | None,
    name: str,
    delivery_profile: str,
    production_mode: bool,
    instructions: str,
) -> dict[str, Any]:
    rows = _load()
    now = time.time()
    tid = (template_id or "").strip() or uuid.uuid4().hex[:16]
    name_clean = (name or "").strip() or "Untitled"
    rec = {
        "id": tid,
        "name": name_clean,
        "delivery_profile": delivery_profile,
        "production_mode": bool(production_mode),
        "instructions": instructions or "",
        "updated_at": now,
    }
    found = False
    out: list[dict[str, Any]] = []
    for r in rows:
        if str(r.get("id")) == tid:
            rec["created_at"] = float(r.get("created_at") or now)
            out.append(rec)
            found = True
        else:
            out.append(r)
    if not found:
        rec["created_at"] = now
        out.insert(0, rec)
    _save(out[:MAX_TEMPLATES])
    return rec


def delete_template(template_id: str) -> bool:
    tid = (template_id or "").strip()
    if not tid:
        return False
    rows = _load()
    new_rows = [r for r in rows if str(r.get("id")) != tid]
    if len(new_rows) == len(rows):
        return False
    _save(new_rows)
    return True
