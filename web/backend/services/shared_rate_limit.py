"""Cross-worker rate limits via PersistentSecurityStore (SQLite WAL), memory fallback."""

from __future__ import annotations

import logging
import threading
import time
from collections import deque

from fastapi import HTTPException

logger = logging.getLogger(__name__)

_mem_lock = threading.Lock()
_mem: dict[str, deque[float]] = {}


def enforce_shared_rate_limit(
    key: str,
    *,
    max_hits: int,
    window_seconds: float = 3600.0,
    detail: str = "Too many requests. Please try again later.",
) -> None:
    """Raise HTTP 429 when ``key`` exceeds ``max_hits`` in the sliding window.

    Prefers the shared SQLite security store so uvicorn workers share one quota.
    Falls back to process-local memory if the store is unavailable.
    """
    if max_hits <= 0:
        return
    store = None
    try:
        from core.persistent_security_store import get_persistent_security_store

        store = get_persistent_security_store()
    except Exception as exc:
        logger.debug("shared rate-limit store import failed: %s", exc)
        store = None

    if store is not None:
        try:
            count = store.recent_attempt_count(key, window_seconds)
            if count >= max_hits:
                raise HTTPException(status_code=429, detail=detail)
            store.record_attempt(key)
            return
        except HTTPException:
            raise
        except Exception as exc:
            logger.warning("shared rate-limit store failed, using memory: %s", exc)

    now = time.time()
    with _mem_lock:
        win = _mem.setdefault(key, deque())
        while win and now - win[0] > window_seconds:
            win.popleft()
        if len(win) >= max_hits:
            raise HTTPException(status_code=429, detail=detail)
        win.append(now)
