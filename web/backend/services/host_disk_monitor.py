"""
Host disk space monitoring with optional Telegram alerts.

Thresholds resolve in order: **env** (ops override) → **Admin → Settings** (`general.disk_*` in
merged config) → built-in defaults.

  - **warning**: ≥ used % **or** free &lt; GB
  - **critical**: ≥ used % **or** free &lt; GB
  - Same level repeats at most once per cooldown (hours in Settings; ``AIFACTORY_DISK_ALERT_COOLDOWN_SEC`` in env).
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from core.paths import data_root, state_dir

logger = logging.getLogger(__name__)

DiskLevel = Literal["ok", "warning", "critical"]

_STATE_FILE = state_dir() / "disk_alert_state.json"

DEFAULT_DISK_WARN_USED_PCT = 90.0
DEFAULT_DISK_CRIT_USED_PCT = 96.0
DEFAULT_DISK_WARN_FREE_GB = 4.0
DEFAULT_DISK_CRIT_FREE_GB = 1.0
DEFAULT_DISK_ALERT_COOLDOWN_HOURS = 8.0
DEFAULT_DISK_MONITOR_INTERVAL_MINUTES = 15


@dataclass(frozen=True)
class DiskSnapshot:
    path: str
    total_gb: float
    used_gb: float
    free_gb: float
    used_pct: float
    level: DiskLevel


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)))
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except ValueError:
        return default


def _read_general() -> dict[str, Any]:
    try:
        from web.backend.services.telegram_pipeline_notify import _read_general

        gen = _read_general()
        return gen if isinstance(gen, dict) else {}
    except Exception:
        return {}


def _clamp(val: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, val))


def normalize_disk_monitor_settings(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Validate admin Settings payload for disk monitor fields."""
    raw = payload if isinstance(payload, dict) else {}
    warn_pct = _clamp(
        float(raw.get("disk_warn_used_pct", DEFAULT_DISK_WARN_USED_PCT)),
        50.0,
        99.0,
    )
    crit_pct = _clamp(
        float(raw.get("disk_crit_used_pct", DEFAULT_DISK_CRIT_USED_PCT)),
        warn_pct,
        99.9,
    )
    warn_gb = _clamp(float(raw.get("disk_warn_free_gb", DEFAULT_DISK_WARN_FREE_GB)), 0.1, 512.0)
    crit_gb = _clamp(
        float(raw.get("disk_crit_free_gb", DEFAULT_DISK_CRIT_FREE_GB)),
        0.05,
        warn_gb,
    )
    cooldown_h = _clamp(
        float(raw.get("disk_alert_cooldown_hours", DEFAULT_DISK_ALERT_COOLDOWN_HOURS)),
        0.5,
        168.0,
    )
    interval_m = int(
        _clamp(
            float(raw.get("disk_monitor_interval_minutes", DEFAULT_DISK_MONITOR_INTERVAL_MINUTES)),
            1.0,
            120.0,
        )
    )
    return {
        "disk_warn_used_pct": round(warn_pct, 1),
        "disk_crit_used_pct": round(crit_pct, 1),
        "disk_warn_free_gb": round(warn_gb, 2),
        "disk_crit_free_gb": round(crit_gb, 2),
        "disk_alert_cooldown_hours": round(cooldown_h, 2),
        "disk_monitor_interval_minutes": interval_m,
        "telegram_notify_host_disk": bool(raw.get("telegram_notify_host_disk", True)),
    }


def disk_monitor_settings_from_config(config: Any | None = None) -> dict[str, Any]:
    """Current effective settings for Admin GET (config file values, not env overrides)."""
    if config is None:
        gen = _read_general()
    else:
        gen = config.get("general") if hasattr(config, "get") else {}
        if not isinstance(gen, dict):
            gen = {}
    return normalize_disk_monitor_settings(
        {
            "disk_warn_used_pct": gen.get("disk_warn_used_pct", DEFAULT_DISK_WARN_USED_PCT),
            "disk_crit_used_pct": gen.get("disk_crit_used_pct", DEFAULT_DISK_CRIT_USED_PCT),
            "disk_warn_free_gb": gen.get("disk_warn_free_gb", DEFAULT_DISK_WARN_FREE_GB),
            "disk_crit_free_gb": gen.get("disk_crit_free_gb", DEFAULT_DISK_CRIT_FREE_GB),
            "disk_alert_cooldown_hours": gen.get(
                "disk_alert_cooldown_hours", DEFAULT_DISK_ALERT_COOLDOWN_HOURS
            ),
            "disk_monitor_interval_minutes": gen.get(
                "disk_monitor_interval_minutes", DEFAULT_DISK_MONITOR_INTERVAL_MINUTES
            ),
            "telegram_notify_host_disk": gen.get("telegram_notify_host_disk", True),
        }
    )


def _setting_float(
    gen_key: str,
    env_key: str,
    default: float,
    *,
    lo: float,
    hi: float,
) -> float:
    if os.environ.get(env_key, "").strip():
        return _clamp(_env_float(env_key, default), lo, hi)
    gen = _read_general()
    try:
        val = float(gen.get(gen_key, default))
    except (TypeError, ValueError):
        val = default
    return _clamp(val, lo, hi)


def warn_used_pct() -> float:
    return _setting_float(
        "disk_warn_used_pct",
        "AIFACTORY_DISK_WARN_USED_PCT",
        DEFAULT_DISK_WARN_USED_PCT,
        lo=50.0,
        hi=99.0,
    )


def crit_used_pct() -> float:
    return max(
        warn_used_pct(),
        _setting_float(
            "disk_crit_used_pct",
            "AIFACTORY_DISK_CRIT_USED_PCT",
            DEFAULT_DISK_CRIT_USED_PCT,
            lo=50.0,
            hi=99.9,
        ),
    )


def warn_free_gb() -> float:
    return _setting_float(
        "disk_warn_free_gb",
        "AIFACTORY_DISK_WARN_FREE_GB",
        DEFAULT_DISK_WARN_FREE_GB,
        lo=0.1,
        hi=512.0,
    )


def crit_free_gb() -> float:
    return min(
        warn_free_gb(),
        _setting_float(
            "disk_crit_free_gb",
            "AIFACTORY_DISK_CRIT_FREE_GB",
            DEFAULT_DISK_CRIT_FREE_GB,
            lo=0.05,
            hi=512.0,
        ),
    )


def alert_cooldown_sec() -> int:
    if os.environ.get("AIFACTORY_DISK_ALERT_COOLDOWN_SEC", "").strip():
        return max(300, _env_int("AIFACTORY_DISK_ALERT_COOLDOWN_SEC", int(DEFAULT_DISK_ALERT_COOLDOWN_HOURS * 3600)))
    gen = _read_general()
    try:
        hours = float(gen.get("disk_alert_cooldown_hours", DEFAULT_DISK_ALERT_COOLDOWN_HOURS))
    except (TypeError, ValueError):
        hours = DEFAULT_DISK_ALERT_COOLDOWN_HOURS
    return max(300, int(_clamp(hours, 0.5, 168.0) * 3600))


def monitor_interval_sec() -> int:
    if os.environ.get("AIFACTORY_DISK_MONITOR_INTERVAL_SEC", "").strip():
        return max(60, _env_int("AIFACTORY_DISK_MONITOR_INTERVAL_SEC", DEFAULT_DISK_MONITOR_INTERVAL_MINUTES * 60))
    gen = _read_general()
    try:
        minutes = int(float(gen.get("disk_monitor_interval_minutes", DEFAULT_DISK_MONITOR_INTERVAL_MINUTES)))
    except (TypeError, ValueError):
        minutes = DEFAULT_DISK_MONITOR_INTERVAL_MINUTES
    return max(60, int(_clamp(float(minutes), 1.0, 120.0) * 60))


def monitor_paths() -> list[Path]:
    raw = (os.environ.get("AIFACTORY_DISK_MONITOR_PATHS") or "").strip()
    if raw:
        return [Path(p.strip()) for p in raw.split(",") if p.strip()]
    return [data_root(), Path("/")]


def classify_disk_usage(path: Path) -> DiskSnapshot | None:
    try:
        u = shutil.disk_usage(path)
    except OSError as exc:
        logger.debug("disk usage unavailable for %s: %s", path, exc)
        return None
    total_gb = u.total / (1024**3)
    free_gb = u.free / (1024**3)
    used_gb = (u.total - u.free) / (1024**3)
    used_pct = (used_gb / total_gb * 100.0) if total_gb > 0 else 0.0
    level: DiskLevel = "ok"
    if used_pct >= crit_used_pct() or free_gb < crit_free_gb():
        level = "critical"
    elif used_pct >= warn_used_pct() or free_gb < warn_free_gb():
        level = "warning"
    return DiskSnapshot(
        path=str(path),
        total_gb=round(total_gb, 2),
        used_gb=round(used_gb, 2),
        free_gb=round(free_gb, 2),
        used_pct=round(used_pct, 1),
        level=level,
    )


def worst_disk_snapshot() -> tuple[DiskLevel, list[DiskSnapshot]]:
    snaps: list[DiskSnapshot] = []
    for p in monitor_paths():
        s = classify_disk_usage(p)
        if s is not None:
            snaps.append(s)
    if not snaps:
        return "ok", []
    order = {"ok": 0, "warning": 1, "critical": 2}
    worst = max(snaps, key=lambda s: order[s.level])
    return worst.level, snaps


def disk_monitor_live_status() -> dict[str, Any]:
    """Serializable snapshot for Admin Settings (uses effective thresholds)."""
    level, snaps = worst_disk_snapshot()
    return {
        "level": level,
        "thresholds": {
            "warn_used_pct": warn_used_pct(),
            "crit_used_pct": crit_used_pct(),
            "warn_free_gb": warn_free_gb(),
            "crit_free_gb": crit_free_gb(),
            "alert_cooldown_hours": round(alert_cooldown_sec() / 3600.0, 2),
            "monitor_interval_minutes": round(monitor_interval_sec() / 60.0),
        },
        "paths": [
            {
                "path": s.path,
                "used_pct": s.used_pct,
                "free_gb": s.free_gb,
                "total_gb": s.total_gb,
                "level": s.level,
            }
            for s in snaps
        ],
    }


def _load_state() -> dict[str, Any]:
    if not _STATE_FILE.is_file():
        return {}
    try:
        data = json.loads(_STATE_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save_state(state: dict[str, Any]) -> None:
    try:
        _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = _STATE_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
        tmp.replace(_STATE_FILE)
    except OSError as exc:
        logger.warning("disk alert state save failed: %s", exc)


def telegram_disk_notify_enabled() -> bool:
    from web.backend.services.telegram_pipeline_notify import (
        _read_general,
        telegram_pipeline_config,
    )

    cfg = telegram_pipeline_config()
    if not cfg.get("enabled") or not cfg.get("token") or not cfg.get("chat_id"):
        return False
    gen = _read_general()
    if "telegram_notify_host_disk" in gen:
        return bool(gen.get("telegram_notify_host_disk"))
    return os.environ.get("AIFACTORY_TELEGRAM_NOTIFY_HOST_DISK", "1").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def _format_alert_message(level: DiskLevel, snaps: list[DiskSnapshot]) -> str:
    lines = [
        "AI-Factory · Disk space",
        f"Status: {level.upper()}",
        "",
    ]
    for s in snaps:
        lines.append(
            f"• `{s.path}` — {s.used_pct}% used, {s.free_gb} GB free "
            f"({s.used_gb}/{s.total_gb} GB)"
        )
    lines.append("")
    if level == "critical":
        lines.append(
            "Action: free space (disk_cleanup cron, prune Docker, old sandboxes) "
            "or new previews fall back to static-only."
        )
    else:
        lines.append("Action: consider cleanup before disk fills up.")
    return "\n".join(lines)


def check_disk_and_notify_telegram(*, force: bool = False) -> DiskLevel:
    """
    Evaluate disk; send Telegram when level is warning/critical and cooldown allows.
    Returns worst level seen.
    """
    level, snaps = worst_disk_snapshot()
    if level == "ok":
        return level
    if not force and not telegram_disk_notify_enabled():
        logger.info("disk %s but Telegram host-disk notify disabled", level)
        return level

    state = _load_state()
    now = time.time()
    last_level = str(state.get("last_level") or "")
    last_at = float(state.get("last_sent_at") or 0)
    if not force and last_level == level and (now - last_at) < alert_cooldown_sec():
        return level

    from web.backend.services.telegram_pipeline_notify import send_telegram_message_sync

    ok, detail = send_telegram_message_sync(_format_alert_message(level, snaps))
    if ok:
        _save_state({"last_level": level, "last_sent_at": now, "snapshots": [s.path for s in snaps]})
        logger.warning("disk alert sent to Telegram: %s", level)
    else:
        logger.warning("disk alert Telegram failed: %s", detail)
    return level


async def host_disk_monitor_loop() -> None:
    """Background loop — interval from Settings or ``AIFACTORY_DISK_MONITOR_INTERVAL_SEC``."""
    while True:
        try:
            import asyncio

            await asyncio.to_thread(check_disk_and_notify_telegram)
        except Exception:
            logger.exception("host disk monitor tick failed")
        await asyncio.sleep(monitor_interval_sec())
