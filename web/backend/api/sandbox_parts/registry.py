"""The sandbox registry and its cleanup: saving it, workdirs, tearing a sandbox down, expiry
and dead-preview reaping, stale workdir sweeps.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Optional

from core.logging_utils import log_suppressed

# Logged under the sandbox module's own name, whatever package path it was imported by.
logger = logging.getLogger(__name__.rsplit(".", 2)[0] + ".sandbox")


def _save_registry() -> None:
    try:
        sandbox_api._SANDBOX_REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = sandbox_api._SANDBOX_REGISTRY_PATH.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(sandbox_api._active_sandboxes, f)
        tmp.replace(sandbox_api._SANDBOX_REGISTRY_PATH)
    except Exception as e:
        logger.warning("sandbox registry save failed: %s", e)


def _reap_preview_resources_bg() -> None:
    try:
        from web.backend.services.sandbox_docker import reap_stale_preview_resources

        reap_stale_preview_resources()
    except Exception as exc:
        log_suppressed(logger, "sandbox preview GC", exc_info=exc)


def _sandbox_workdir(product_id: str | None, sandbox_id: str) -> Path | None:
    """``<code_dir>/.aicom_sandbox/<sid>`` — one sandbox's preview venv + SPA overlay."""
    if not product_id:
        return None
    code_dir = sandbox_api._get_product_code_dir(str(product_id))
    if code_dir is None:
        return None
    sid = re.sub(r"[^\w-]", "_", (sandbox_id or "sandbox")[:48])
    if not sid or sid.startswith("."):
        return None
    return code_dir / ".aicom_sandbox" / sid


def _tree_bytes(path: Path) -> int:
    total = 0
    for root, _dirs, files in os.walk(path):
        for fn in files:
            try:
                total += os.lstat(os.path.join(root, fn)).st_size
            except OSError:
                continue
    return total


def remove_sandbox_workdir(product_id: str | None, sandbox_id: str) -> int:
    """Delete a sandbox's preview tree; return bytes freed (0 when there was nothing)."""
    target = sandbox_api._sandbox_workdir(product_id, sandbox_id)
    if target is None or target.is_symlink() or not target.is_dir():
        return 0
    freed = sandbox_api._tree_bytes(target)
    shutil.rmtree(target, ignore_errors=True)
    return freed


def _teardown_sandbox_resources(sandbox_id: str, entry: dict[str, Any] | None = None) -> None:
    """Release everything a preview holds — process, containers, disk.

    Admin stop, cap eviction, TTL expiry and the dead-process reaper all go through here, so
    the four paths cannot drift apart again (expiry used to release nothing at all).
    """
    entry = entry if entry is not None else (sandbox_api._active_sandboxes.get(sandbox_id) or {})
    try:
        sandbox_api.stop_preview_for_sandbox(sandbox_id)  # uvicorn child + its ephemeral Postgres
    except Exception as exc:
        log_suppressed(logger, "sandbox teardown: preview", exc_info=exc)
    try:
        sandbox_api.stop_compose_for_sandbox(sandbox_id)
    except Exception as exc:
        log_suppressed(logger, "sandbox teardown: compose", exc_info=exc)
    if entry.get("docker_mode"):
        for verb in ("stop", "rm"):
            try:
                subprocess.run(
                    ["docker", verb, sandbox_id], capture_output=True, text=True, timeout=15
                )
            except (subprocess.TimeoutExpired, OSError) as exc:
                log_suppressed(logger, f"sandbox teardown: docker {verb}", exc_info=exc)
    freed = 0
    try:
        freed = sandbox_api.remove_sandbox_workdir(entry.get("product_id"), sandbox_id)
    except Exception as exc:
        log_suppressed(logger, "sandbox teardown: workdir", exc_info=exc)
    if freed:
        logger.info("sandbox %s: removed preview tree (%.0f MB)", sandbox_id[:24], freed / 2**20)


def _prune_expired_and_teardown() -> int:
    """Drop expired rows (under the registry lock) and release what they held (outside it)."""
    from web.backend.services.sandbox_guards import pop_expired_sandboxes

    with sandbox_api._registry_lock:
        before = len(sandbox_api._active_sandboxes)
        expired = pop_expired_sandboxes(sandbox_api._active_sandboxes)
        if len(sandbox_api._active_sandboxes) != before:
            sandbox_api._save_registry()
    for sid, entry in expired:
        try:
            sandbox_api._teardown_sandbox_resources(sid, entry)
        except Exception as exc:
            log_suppressed(logger, "sandbox expiry teardown", exc_info=exc)
    if expired:
        logger.warning(
            "sandbox registry: %d preview(s) expired, resources released", len(expired)
        )
    return len(expired)


def _reap_dead_previews() -> int:
    """Rows whose uvicorn exited while the app kept running: close them, release resources."""
    dead = sandbox_api.exited_preview_sandboxes()
    if not dead:
        return 0
    rows: list[tuple[str, dict[str, Any]]] = []
    with sandbox_api._registry_lock:
        for sid in dead:
            entry = sandbox_api._active_sandboxes.get(sid)
            if isinstance(entry, dict) and entry.get("status") == "running":
                entry["status"] = "stopped"
                entry["stopped_at"] = time.time()
                entry["stopped_reason"] = "preview_exited"
            rows.append((sid, dict(entry) if isinstance(entry, dict) else {}))
        sandbox_api._save_registry()
    for sid, entry in rows:
        sandbox_api._teardown_sandbox_resources(sid, entry)
    logger.warning(
        "sandbox: %d preview process(es) exited on their own, rows closed: %s",
        len(rows),
        ", ".join(sid[:24] for sid, _ in rows),
    )
    return len(rows)


def sweep_once() -> dict[str, int]:
    """One maintenance pass: stopped rows, expired rows, exited processes, orphaned disk, DinD."""
    with sandbox_api._registry_lock:
        stale = [
            (sid, dict(e))
            for sid, e in sandbox_api._active_sandboxes.items()
            if isinstance(e, dict) and e.get("status") != "running"
        ]
    for sid, entry in stale:  # boot orphans: their Postgres / venv are still there
        sandbox_api._teardown_sandbox_resources(sid, entry)
    result = {"expired": sandbox_api._prune_expired_and_teardown(), "exited": sandbox_api._reap_dead_previews()}
    result["workdirs"], _freed = sandbox_api._sweep_stale_workdirs()
    sandbox_api._maybe_gc_preview_resources()
    return result


def _sweep_interval_s() -> float:
    raw = (os.environ.get("AIFACTORY_SANDBOX_SWEEP_INTERVAL_S") or "60").strip()
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 60.0


def _sweeper_loop(interval_s: float) -> None:
    while True:
        try:
            sandbox_api.sweep_once()
        except Exception as exc:
            log_suppressed(logger, "sandbox sweeper", exc_info=exc)
        time.sleep(interval_s)


def _lookup_sandbox(sandbox_id: str) -> Optional[dict]:
    """Return sandbox dict, reloading from disk on cache miss (multi-worker safety)."""
    sb = sandbox_api._active_sandboxes.get(sandbox_id)
    if sb is not None:
        return sb
    sandbox_api._load_registry()
    return sandbox_api._active_sandboxes.get(sandbox_id)


def _get_product_code_dir(product_id: str) -> Optional[Path]:
    """Get the code directory for a product, if it exists."""
    root = sandbox_api.resolve_product_code_dir(product_id)
    return root if root.exists() else None


# Imported last on purpose: this code reads sandbox's state, settings and helpers at
# call time (where tests patch them), and either module may load first.
from .. import sandbox as sandbox_api  # noqa: E402
