"""
Event-driven pipeline wake: watch ``pipeline.json`` / SQLite DB mtime via watchfiles.

Falls back to no-op when watchfiles is unavailable (worker still uses /wake + adaptive poll).
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Awaitable, Callable

logger = logging.getLogger(__name__)

WakeCallback = Callable[[], None]


async def run_pipeline_state_watch(
    *,
    json_path: Path,
    sqlite_path: Path | None,
    on_wake: WakeCallback,
    stop_event: asyncio.Event,
) -> None:
    """Background task: call ``on_wake`` when pipeline state files change."""
    try:
        from watchfiles import awatch, Change
    except ImportError:
        logger.info(
            "watchfiles not installed — pipeline worker uses /wake + poll only "
            "(pip install watchfiles for inotify-style wakes)"
        )
        await stop_event.wait()
        return

    paths: list[Path] = []
    if json_path.parent.is_dir():
        paths.append(json_path.parent)
    if sqlite_path and sqlite_path.parent.is_dir():
        paths.append(sqlite_path.parent)
    if not paths:
        await stop_event.wait()
        return

    watch_paths = [str(p) for p in paths]
    logger.info("Pipeline state watch started on %s", watch_paths)

    async for changes in awatch(
        *watch_paths,
        stop_event=stop_event,
        rust_timeout=500,
        yield_on_timeout=True,
    ):
        if stop_event.is_set():
            break
        if not changes:
            continue
        relevant = False
        for change, path in changes:
            if change not in (Change.added, Change.modified, Change.deleted):
                continue
            p = Path(path)
            if p == json_path or p.name == json_path.name:
                relevant = True
                break
            if sqlite_path and (p == sqlite_path or p.name == sqlite_path.name):
                relevant = True
                break
        if relevant:
            try:
                on_wake()
            except Exception:
                logger.debug("pipeline state watch on_wake failed", exc_info=True)
