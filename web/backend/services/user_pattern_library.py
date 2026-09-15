"""Cloud-synced pattern snippets (JSON documents) stored in factory data dir."""

from __future__ import annotations

import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any

from core.paths import data_root as factory_data_root

logger = logging.getLogger(__name__)

MAX_PATTERNS = 128


def _path() -> Path:
    p = factory_data_root() / "config" / "user_pattern_library.json"
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
        logger.warning("user_pattern_library: load failed: %s", e)
        return []


def _save(rows: list[dict[str, Any]]) -> None:
    _path().write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")


def list_patterns() -> list[dict[str, Any]]:
    rows = _load()
    rows.sort(key=lambda r: float(r.get("updated_at") or r.get("created_at") or 0), reverse=True)
    return rows[:MAX_PATTERNS]


def upsert_pattern(
    *,
    pattern_id: str | None,
    name: str,
    tags: list[str],
    document: dict[str, Any],
) -> dict[str, Any]:
    rows = _load()
    now = time.time()
    pid = (pattern_id or "").strip() or uuid.uuid4().hex[:16]
    name_clean = (name or "").strip() or "Untitled"
    tag_clean = [str(t).strip() for t in (tags or []) if str(t).strip()][:24]
    doc = document if isinstance(document, dict) else {}
    rec: dict[str, Any] = {
        "id": pid,
        "name": name_clean,
        "tags": tag_clean,
        "document": doc,
        "updated_at": now,
    }
    found = False
    out: list[dict[str, Any]] = []
    for r in rows:
        if str(r.get("id")) == pid:
            rec["created_at"] = float(r.get("created_at") or now)
            out.append(rec)
            found = True
        else:
            out.append(r)
    if not found:
        rec["created_at"] = now
        out.insert(0, rec)
    _save(out[:MAX_PATTERNS])
    return rec


def delete_pattern(pattern_id: str) -> bool:
    pid = (pattern_id or "").strip()
    if not pid:
        return False
    rows = _load()
    new_rows = [r for r in rows if str(r.get("id")) != pid]
    if len(new_rows) == len(rows):
        return False
    _save(new_rows)
    return True
