"""Telegram + deduped alerts when a pipeline product enters FAILED."""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from pathlib import Path
from typing import Any

from core.paths import data_root

logger = logging.getLogger(__name__)

_DEDUPE_PATH = Path(data_root()) / "state" / "pipeline_failed_telegram_sent.json"
_DEDUPE_LOCK = threading.Lock()


def failure_reason_from_product(product: dict[str, Any]) -> str:
    for key in ("failure_reason", "last_error", "error"):
        v = product.get(key)
        if v and str(v).strip():
            return str(v).strip()
    meta = product.get("metadata") or {}
    if isinstance(meta, dict):
        for key in ("failure_reason", "error"):
            v = meta.get(key)
            if v and str(v).strip():
                return str(v).strip()
    return ""


def _dedupe_key(product_id: str, reason: str) -> str:
    digest = hashlib.sha256(f"{product_id}\n{reason[:2000]}".encode()).hexdigest()[:24]
    return digest


def _already_sent(product_id: str, reason: str) -> bool:
    key = _dedupe_key(product_id, reason)
    with _DEDUPE_LOCK:
        try:
            if not _DEDUPE_PATH.is_file():
                return False
            data = json.loads(_DEDUPE_PATH.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return False
            return data.get(product_id) == key
        except Exception:
            return False


def _mark_sent(product_id: str, reason: str) -> None:
    key = _dedupe_key(product_id, reason)
    with _DEDUPE_LOCK:
        data: dict[str, str] = {}
        try:
            if _DEDUPE_PATH.is_file():
                raw = json.loads(_DEDUPE_PATH.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    data = {str(k): str(v) for k, v in raw.items()}
        except Exception:
            data = {}
        data[product_id] = key
        if len(data) > 500:
            for pid in list(data.keys())[:-400]:
                data.pop(pid, None)
        _DEDUPE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _DEDUPE_PATH.write_text(json.dumps(data, indent=0), encoding="utf-8")


def notify_pipeline_product_failed(
    product_id: str,
    *,
    product: dict[str, Any] | None = None,
    task: dict[str, Any] | None = None,
    failure_reason: str | None = None,
) -> None:
    """Fire-and-forget: Telegram (and corporate chat) when product becomes FAILED."""
    pid = (product_id or "").strip()
    if not pid:
        return

    def _run() -> None:
        try:
            row = dict(product) if isinstance(product, dict) else {}
            tasks: list[dict[str, Any]] = []
            if task and isinstance(task, dict):
                tasks = [task]

            if not row or (not failure_reason_from_product(row) and not tasks):
                try:
                    from orchestrator.sqlite_manager import SQLiteManager
                    import os

                    db = Path(os.environ.get("SQLITE_PATH", "/app/data/state/pipeline.db"))
                    if db.is_file():
                        sm = SQLiteManager(str(db))
                        sm.connect()
                        try:
                            loaded = sm.get_product(pid)
                            if loaded:
                                row = loaded
                            if not tasks:
                                tasks = sm.get_tasks_by_product(pid)
                        finally:
                            sm.close()
                except Exception:
                    logger.debug("pipeline_failed_notify: sqlite load skipped", exc_info=True)

            reason = (failure_reason or "").strip() or failure_reason_from_product(row)
            if not reason and task:
                reason = str(task.get("error") or "").strip()
            if not reason and tasks:
                for t in reversed(tasks):
                    if str(t.get("status") or "").lower() == "failed":
                        reason = str(t.get("error") or "").strip()
                        if reason:
                            break

            if _already_sent(pid, reason or "unknown"):
                return

            from web.backend.services.pipeline_failure_report import build_failure_report
            from web.backend.services.telegram_pipeline_notify import notify_telegram_pipeline_failed

            report = build_failure_report(row, tasks)
            idea = str(row.get("idea") or "")
            notify_telegram_pipeline_failed(
                product_id=pid,
                headline=str(report.get("headline") or "Pipeline failed"),
                cause_plain=str(report.get("cause_plain") or reason or "Unknown failure"),
                failure_reason=reason or str(report.get("failure_reason") or ""),
                failed_agent=str(report.get("failed_agent") or task.get("agent_type") if task else "") or None,
                idea_snippet=idea,
            )

            try:
                from web.backend.services.corporate_standup import append_chat_message

                short_id = f"{pid[:12]}…" if len(pid) > 12 else pid
                append_chat_message(
                    username="Pipeline (alert)",
                    text=(
                        f"**FAILED** `{short_id}`\n"
                        f"_{report.get('headline') or 'Pipeline stopped'}_\n"
                        f"{report.get('cause_plain') or reason}"
                    )[:3500],
                    admin_username="system",
                    role="agent",
                    kind="pipeline_failed",
                )
            except Exception:
                logger.debug("corporate chat failed notify skipped", exc_info=True)

            _mark_sent(pid, reason or str(report.get("cause_plain") or "unknown"))
        except Exception:
            logger.exception("notify_pipeline_product_failed failed for %s", pid)

    threading.Thread(target=_run, daemon=True, name=f"failed-notify-{pid[:8]}").start()
