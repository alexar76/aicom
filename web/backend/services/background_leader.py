"""One worker process runs the backend's background loops (KI-3).

``uvicorn --workers N`` starts N copies of the app, and the lifespan used to start every
background loop in each of them: N scheduled backups in the same minute writing the same
archive and the same admin config, N stand-ups (N times the LLM bill), N disk alerts, N
pipeline-metric syncs racing one another. Under load that is the multi-worker failure KI-3
describes, made by the app itself rather than by uvicorn.

The leader is whoever holds an exclusive ``flock`` on a file in the state directory. The
kernel releases it when the holder dies, so a worker restarted by uvicorn hands the loops to
another worker within one poll. Non-leaders wait instead of running the loops. A lock that
cannot be taken because the file cannot be opened at all (a read-only data dir) falls back
to running the loops, which is what a single worker does anyway.
"""
from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)

_POLL_S = 30.0
_fd: int | None = None


def _lock_path() -> Path:
    from core.paths import state_dir

    return Path(os.environ.get("AIFACTORY_BACKGROUND_LEADER_LOCK", str(state_dir() / "background-leader.lock")))


def is_leader() -> bool:
    """True once this process holds the lock (and from then on, for its whole life)."""
    global _fd
    if _fd is not None:
        return True
    try:
        import fcntl
    except ImportError:  # pragma: no cover - not POSIX: one process is all there is
        return True
    path = _lock_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(path), os.O_RDWR | os.O_CREAT, 0o600)
    except OSError as exc:
        logger.warning("background leader lock %s unavailable (%s); running the loops here", path, exc)
        return True
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        return False
    os.ftruncate(fd, 0)
    os.write(fd, str(os.getpid()).encode())
    _fd = fd
    logger.info("background loops run in this worker (pid %s)", os.getpid())
    return True


async def leader_only(name: str, loop: Callable[[], Awaitable[None]], *, poll_s: float = _POLL_S) -> None:
    """Run ``loop`` once this process is the leader; until then, wait for the lock."""
    while not is_leader():
        await asyncio.sleep(poll_s)
    logger.debug("starting background loop %s", name)
    await loop()
