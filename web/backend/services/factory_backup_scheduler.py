"""
Daily scheduled factory backup → ``data/backups/``.

Settings live in admin.json (same file as Director standup). Checked every minute
from the web backend lifespan loop.
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from web.backend.services.corporate_standup import load_admin_config, save_admin_config
from web.backend.services.factory_backup import (
    list_on_disk_factory_backups,
    persist_factory_backup_to_disk,
    prune_factory_backups_on_disk,
)
from web.backend.services.public_demo_guard import is_public_demo

logger = logging.getLogger(__name__)

DEFAULT_TIME = "03:00"
DEFAULT_TIMEZONE = "UTC"
DEFAULT_RETENTION = 7


def normalize_hhmm(value: str | None) -> str:
    raw = (value or DEFAULT_TIME).strip()
    if not re.match(r"^\d{1,2}:\d{1,2}$", raw):
        return DEFAULT_TIME
    parts = raw.split(":")
    h, m = int(parts[0]), int(parts[1])
    if h < 0 or h > 23 or m < 0 or m > 59:
        return DEFAULT_TIME
    return f"{h:02d}:{m:02d}"


def normalize_timezone(value: str | None) -> str:
    tz_name = (value or DEFAULT_TIMEZONE).strip() or DEFAULT_TIMEZONE
    try:
        ZoneInfo(tz_name)
        return tz_name
    except Exception:
        return DEFAULT_TIMEZONE


def schedule_from_config(cfg: dict[str, Any]) -> dict[str, Any]:
    retention = cfg.get("factory_backup_schedule_retention", DEFAULT_RETENTION)
    try:
        retention_n = max(1, min(int(retention), 365))
    except (TypeError, ValueError):
        retention_n = DEFAULT_RETENTION
    return {
        "enabled": bool(cfg.get("factory_backup_schedule_enabled", False)),
        "time": normalize_hhmm(cfg.get("factory_backup_schedule_time")),
        "timezone": normalize_timezone(cfg.get("factory_backup_schedule_timezone")),
        "include_sandboxes": bool(cfg.get("factory_backup_schedule_include_sandboxes", False)),
        "retention": retention_n,
        "last_date": cfg.get("factory_backup_schedule_last_date"),
        "last_run_utc": cfg.get("factory_backup_schedule_last_run"),
        "last_file": cfg.get("factory_backup_schedule_last_file"),
        "last_error": cfg.get("factory_backup_schedule_last_error"),
        "on_disk_backups": list_on_disk_factory_backups(limit=15),
        "public_demo": is_public_demo(),
    }


def apply_schedule_patch(cfg: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    if "enabled" in patch and patch["enabled"] is not None:
        cfg["factory_backup_schedule_enabled"] = bool(patch["enabled"])
    if "time" in patch and patch["time"] is not None:
        cfg["factory_backup_schedule_time"] = normalize_hhmm(str(patch["time"]))
    if "timezone" in patch and patch["timezone"] is not None:
        cfg["factory_backup_schedule_timezone"] = normalize_timezone(str(patch["timezone"]))
    if "include_sandboxes" in patch and patch["include_sandboxes"] is not None:
        cfg["factory_backup_schedule_include_sandboxes"] = bool(patch["include_sandboxes"])
    if "retention" in patch and patch["retention"] is not None:
        try:
            cfg["factory_backup_schedule_retention"] = max(1, min(int(patch["retention"]), 365))
        except (TypeError, ValueError) as e:
            raise ValueError("retention must be an integer between 1 and 365") from e
    save_admin_config(cfg)
    return schedule_from_config(cfg)


def run_scheduled_backup_sync(cfg: dict[str, Any]) -> dict[str, Any]:
    sched = schedule_from_config(cfg)
    result = persist_factory_backup_to_disk(include_sandboxes=sched["include_sandboxes"])
    removed = prune_factory_backups_on_disk(retention=sched["retention"])
    result["pruned_files"] = removed
    return result


def maybe_run_scheduled_factory_backup() -> None:
    if is_public_demo():
        return

    cfg = load_admin_config()
    if not cfg.get("factory_backup_schedule_enabled", False):
        return

    sched = schedule_from_config(cfg)
    tz = ZoneInfo(sched["timezone"])
    now = datetime.now(tz)
    if now.strftime("%H:%M") != sched["time"]:
        return

    today = now.strftime("%Y-%m-%d")
    if cfg.get("factory_backup_schedule_last_date") == today:
        return

    logger.info("Running scheduled factory backup for %s at %s", today, sched["time"])
    try:
        result = run_scheduled_backup_sync(cfg)
        cfg = load_admin_config()
        cfg["factory_backup_schedule_last_date"] = today
        cfg["factory_backup_schedule_last_run"] = result.get("saved_at_utc")
        cfg["factory_backup_schedule_last_file"] = result.get("relative_path")
        cfg.pop("factory_backup_schedule_last_error", None)
        save_admin_config(cfg)
        logger.info(
            "Scheduled factory backup saved: %s (%s bytes, pruned %d old)",
            result.get("relative_path"),
            result.get("size_bytes"),
            len(result.get("pruned_files") or []),
        )
    except Exception as e:
        logger.exception("Scheduled factory backup failed: %s", e)
        cfg = load_admin_config()
        cfg["factory_backup_schedule_last_error"] = str(e)
        save_admin_config(cfg)


async def factory_backup_scheduler_loop(app: Any) -> None:
    while True:
        await asyncio.sleep(60)
        try:
            await asyncio.to_thread(maybe_run_scheduled_factory_backup)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Factory backup scheduler tick failed")
