"""Append-only admin panel user action log (who did what, when)."""

from __future__ import annotations

import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any, Optional

from core.logging_utils import log_suppressed
from core.paths import admin_actions_log_path

logger = logging.getLogger(__name__)

_MAX_DETAILS_JSON = 8000
_MAX_READ_BYTES = 4 * 1024 * 1024


def _log_path() -> Path:
    p = admin_actions_log_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def log_admin_action(
    *,
    actor_username: str,
    action: str,
    resource: str,
    details: dict[str, Any] | None = None,
    ip_address: str = "",
    actor_user_id: str | None = None,
    actor_type: str = "admin",
) -> dict[str, Any]:
    """Persist one admin/system action. Never raises."""
    entry: dict[str, Any] = {
        "id": uuid.uuid4().hex[:16],
        "ts": time.time(),
        "actor_username": str(actor_username or "unknown").strip().lower()[:64],
        "actor_user_id": actor_user_id or None,
        "actor_type": actor_type,
        "action": str(action or "unknown")[:128],
        "resource": str(resource or "")[:256],
        "details": details or {},
        "ip_address": str(ip_address or "")[:64],
    }
    try:
        raw = json.dumps(entry, ensure_ascii=False, default=str)
        if len(raw) > _MAX_DETAILS_JSON:
            entry["details"] = {"truncated": True, "preview": str(details)[:500]}
            raw = json.dumps(entry, ensure_ascii=False, default=str)
        path = _log_path()
        with open(path, "a", encoding="utf-8") as f:
            f.write(raw + "\n")
    except OSError as exc:
        log_suppressed(logger, "admin action log write failed", exc_info=exc)
    return entry


def log_admin_action_from_request(
    request,
    admin: dict | None,
    *,
    action: str,
    resource: str,
    details: dict[str, Any] | None = None,
) -> None:
    """Resolve actor from JWT/admin dict and client IP."""
    from web.backend.http.client_ip import client_ip
    from web.backend.services import admin_users_store as aus

    username = "unknown"
    user_id: str | None = None
    if admin:
        username = str(admin.get("sub") or admin.get("username") or "unknown").strip().lower()
        row = aus.get_user_by_username(username)
        if row:
            user_id = str(row.get("id") or "") or None
    log_admin_action(
        actor_username=username,
        actor_user_id=user_id,
        action=action,
        resource=resource,
        details=details,
        ip_address=client_ip(request),
    )


def query_admin_actions(
    *,
    username: str | None = None,
    user_id: str | None = None,
    limit: int = 100,
    since: float | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """
    Return newest-first entries matching username and/or user_id.
    Scans the JSONL tail (bounded read). Returns (entries, total_matched_before_limit).
    """
    path = _log_path()
    if not path.is_file():
        return [], 0

    lim = max(1, min(int(limit), 500))
    uname = (username or "").strip().lower() or None
    uid = (user_id or "").strip() or None

    try:
        size = path.stat().st_size
        read_from = max(0, size - _MAX_READ_BYTES)
        with open(path, "rb") as f:
            if read_from:
                f.seek(read_from)
            blob = f.read().decode("utf-8", errors="replace")
    except OSError:
        return [], 0

    lines = [ln for ln in blob.splitlines() if ln.strip()]
    matched: list[dict[str, Any]] = []
    for line in reversed(lines):
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if since is not None:
            try:
                if float(row.get("ts") or 0) < since:
                    continue
            except (TypeError, ValueError):
                continue
        if uname and str(row.get("actor_username") or "").lower() != uname:
            continue
        if uid and str(row.get("actor_user_id") or "") != uid:
            continue
        matched.append(row)

    total = len(matched)
    return matched[:lim], total
