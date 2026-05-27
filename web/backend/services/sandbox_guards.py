"""Host resource planning for sandbox previews (full stack vs degraded static)."""

from __future__ import annotations

import logging
import os
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from core.paths import data_root

logger = logging.getLogger(__name__)


@dataclass
class SandboxResourcePlan:
    """Whether to run compose/pip/uvicorn or fall back to static-only preview."""

    tier: str  # "full" | "degraded"
    reasons: list[str] = field(default_factory=list)
    startup_warning: str | None = None
    heavy: bool = False
    disk_free_gb: float | None = None
    mem_available_mb: int | None = None


def sandbox_max_concurrent() -> int:
    try:
        return max(1, int(os.environ.get("AIFACTORY_SANDBOX_MAX_CONCURRENT", "2")))
    except ValueError:
        return 2


def storefront_max_concurrent() -> int:
    try:
        return max(1, int(os.environ.get("AIFACTORY_SANDBOX_STOREFRONT_MAX_CONCURRENT", "2")))
    except ValueError:
        return 2


def min_disk_gb_for_full_stack() -> float:
    try:
        return max(0.5, float(os.environ.get("AIFACTORY_SANDBOX_MIN_DISK_GB_FULL", "2.0")))
    except ValueError:
        return 2.0


def min_disk_gb_to_start() -> float:
    """Below this — refuse any preview (503)."""
    try:
        return max(0.1, float(os.environ.get("AIFACTORY_SANDBOX_MIN_DISK_GB_START", "0.35")))
    except ValueError:
        return 0.35


def sandbox_min_free_mb_for_full() -> int:
    try:
        return max(128, int(os.environ.get("AIFACTORY_SANDBOX_MIN_FREE_MB", "512")))
    except ValueError:
        return 512


def host_disk_free_gb(path: Path) -> float | None:
    try:
        usage = shutil.disk_usage(path)
        return usage.free / (1024**3)
    except OSError:
        return None


def host_mem_available_mb() -> int | None:
    try:
        with open("/proc/meminfo", encoding="utf-8") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    kb = int(line.split()[1])
                    return kb // 1024
    except OSError:
        pass
    return None


def prune_expired_sandboxes(active: dict[str, Any]) -> int:
    """Drop expired / non-running registry rows so concurrency limits stay honest."""
    now = time.time()
    removed = 0
    for sid in list(active.keys()):
        sb = active.get(sid)
        if not isinstance(sb, dict):
            active.pop(sid, None)
            removed += 1
            continue
        if sb.get("status") != "running":
            active.pop(sid, None)
            removed += 1
            continue
        expires = sb.get("expires_at")
        if isinstance(expires, (int, float)) and expires < now:
            active.pop(sid, None)
            removed += 1
    if removed:
        logger.info("sandbox registry: pruned %d expired/stale entries", removed)
    return removed


def count_running_sandboxes(active: dict[str, Any]) -> int:
    now = time.time()
    n = 0
    for sb in active.values():
        if sb.get("status") != "running":
            continue
        expires = sb.get("expires_at")
        if isinstance(expires, (int, float)) and expires < now:
            continue
        n += 1
    return n


def enforce_concurrency_limit(active: dict[str, Any], *, storefront: bool) -> None:
    """503 only when too many live previews — never for disk/memory (use degraded tier)."""
    prune_expired_sandboxes(active)
    running = count_running_sandboxes(active)
    cap = storefront_max_concurrent() if storefront else sandbox_max_concurrent()
    if running >= cap:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "sandbox_busy",
                "message": "Too many live previews running. Try again in a minute.",
                "running": running,
                "limit": cap,
            },
        )


def is_heavy_sandbox_product(code_dir: Path) -> bool:
    """Product likely needs compose build and/or long pip install."""
    from web.backend.services.sandbox_compose_preview import find_compose_file
    from web.backend.services.sandbox_preview_env import code_requires_postgres

    if find_compose_file(code_dir) is not None:
        return True
    if code_requires_postgres(code_dir):
        return True
    for name in ("requirements.txt", "backend/requirements.txt", "pyproject.toml"):
        p = code_dir / name
        if p.is_file() and p.stat().st_size > 80:
            return True
    return False


def evaluate_sandbox_resource_plan(
    code_dir: Path | None,
    *,
    has_static_preview: bool,
) -> SandboxResourcePlan:
    """
    Choose full stack (compose / uvicorn / pip) vs degraded static-only preview.

    Full stack is the default when disk and memory allow it.
    """
    disk_path = code_dir if code_dir and code_dir.is_dir() else data_root()
    disk_gb = host_disk_free_gb(disk_path)
    mem_mb = host_mem_available_mb()
    heavy = bool(code_dir and code_dir.is_dir() and is_heavy_sandbox_product(code_dir))

    plan = SandboxResourcePlan(
        tier="full",
        heavy=heavy,
        disk_free_gb=disk_gb,
        mem_available_mb=mem_mb,
    )

    if disk_gb is not None and disk_gb < min_disk_gb_to_start():
        raise HTTPException(
            status_code=503,
            detail={
                "code": "host_disk_full",
                "message": "Server disk is too full to start a preview.",
                "free_gb": round(disk_gb, 2),
                "required_gb": min_disk_gb_to_start(),
            },
        )

    degrade = False
    if disk_gb is not None and disk_gb < min_disk_gb_for_full_stack():
        plan.reasons.append("low_disk")
        degrade = True
    if mem_mb is not None and mem_mb < sandbox_min_free_mb_for_full():
        plan.reasons.append("low_memory")
        degrade = True

    if degrade:
        if not has_static_preview:
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "resources_insufficient",
                    "message": "Not enough disk or memory for a full-stack preview and no static landing is available.",
                    "free_gb": round(disk_gb, 2) if disk_gb is not None else None,
                    "mem_mb": mem_mb,
                },
            )
        plan.tier = "degraded"
        return plan

    if heavy:
        plan.startup_warning = (
            "Full-stack preview (Docker / dependencies) may take several minutes. "
            "The site stays responsive while this runs in the background."
        )
    return plan


def degraded_badge_message(reasons: list[str] | None) -> str:
    codes = reasons or []
    if "low_disk" in codes and "low_memory" in codes:
        return "Static preview only — full backend skipped (low disk and memory)."
    if "low_disk" in codes:
        return "Static preview only — full backend skipped (low disk space)."
    if "low_memory" in codes:
        return "Static preview only — full backend skipped (low memory)."
    return "Static preview only — full backend unavailable on this server."
