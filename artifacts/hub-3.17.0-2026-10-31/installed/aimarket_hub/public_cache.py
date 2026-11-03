"""A short-lived, shared memo for the hub's expensive public documents.

`/.well-known/ai-market.json` and `/ai-market/v2/stats/live` are the same for every caller
and cost a catalogue scan, a dozen ledger reads and (for the well-known) a full-document
signature. On 2026-10-16 `hub.attestedmemory.net` went down twice while a monitor asked
for both every 1.5 s: each answer took 0.3-0.5 s on a crowded CPU, they ran on the single
event loop, and `/health` queued behind them until the edge gave up. The handlers now
build these documents in a worker thread, and this memo means a burst of callers costs
one build per TTL instead of one per caller.

Single-flight on purpose: when the entry expires under load, the first caller rebuilds and
the rest wait for that build rather than each starting their own.

The TTL is read on every call so an operator (or a test) can change it without a restart;
0 turns the memo off.
"""

from __future__ import annotations

import os
import threading
import time
from collections.abc import Callable, Hashable
from typing import Any

# Expired entries are swept once the memo holds more keys than this. The key space is
# bounded by its callers (the stats page limit is clamped to 200), so this is a tidy-up,
# not the thing that bounds memory.
_SWEEP_AT = 64


def ttl_from_env(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return max(0.0, float(raw))
    except ValueError:
        return default


class PublicDocumentCache:
    """Memo of ``build()`` results per key, each kept for ``ttl_s`` seconds.

    ``get`` is synchronous and may block while another thread builds the same document,
    so call it from a worker thread (``run_in_threadpool``), never on the event loop.
    """

    def __init__(self, ttl_env: str, default_ttl_s: float) -> None:
        self.ttl_env = ttl_env
        self.default_ttl_s = default_ttl_s
        self._entries: dict[Hashable, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def ttl_s(self) -> float:
        return ttl_from_env(self.ttl_env, self.default_ttl_s)

    def _fresh(self, key: Hashable, ttl: float) -> tuple[bool, Any]:
        hit = self._entries.get(key)
        if hit is not None and time.monotonic() - hit[0] < ttl:
            return True, hit[1]
        return False, None

    def get(self, key: Hashable, build: Callable[[], Any]) -> Any:
        ttl = self.ttl_s()
        if ttl <= 0:
            return build()
        found, value = self._fresh(key, ttl)
        if found:
            return value
        with self._lock:
            # Somebody may have rebuilt it while we waited for the lock.
            found, value = self._fresh(key, ttl)
            if found:
                return value
            value = build()  # an exception propagates and caches nothing
            now = time.monotonic()
            if len(self._entries) >= _SWEEP_AT:
                self._entries = {
                    k: v for k, v in self._entries.items() if now - v[0] < ttl
                }
            self._entries[key] = (now, value)
            return value

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
