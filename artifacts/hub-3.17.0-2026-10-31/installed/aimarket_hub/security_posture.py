"""Aggregate security signals for the fleet alerter — counts only, never who.

The alerter watched uptime and money and no security event: a signup-farming run or a
key-guessing sweep on the credit rail showed nowhere until the grant budget was gone. The
hub now counts the two events that mark them and serves the counts (and the share of the
daily signup-grant budget already spent) at ``GET /ai-market/v2/security/posture``.

In memory, per process, over a sliding hour: a restart forgets them, which is fine for an
alert that looks at the last hour. Timestamps only — no address, key or account is kept.
"""
from __future__ import annotations

import threading
import time
from collections import deque

WINDOW_S = 3600
# Bounded so a flood cannot grow memory: past this, the oldest timestamps drop first and
# the count saturates at the cap, which still reads as "far over any threshold".
_MAX_EVENTS = 50_000

SIGNUP_REFUSED = "signup_refused"
BAD_API_KEY = "bad_api_key"

_lock = threading.Lock()
_events: dict[str, deque[float]] = {}
# One request can look the same key up more than once (middleware, then the route), so a
# repeat of the same token within _DEDUP_S counts once. Tokens are opaque hashes, in memory.
_DEDUP_S = 5.0
_seen: dict[str, float] = {}


def record(kind: str, now: float | None = None) -> None:
    ts = time.time() if now is None else now
    with _lock:
        q = _events.setdefault(kind, deque(maxlen=_MAX_EVENTS))
        q.append(ts)


def record_once(kind: str, token: str, now: float | None = None) -> None:
    """Record ``kind`` unless the same ``token`` was recorded in the last few seconds."""
    ts = time.time() if now is None else now
    key = f"{kind}:{token}"
    with _lock:
        last = _seen.get(key)
        if last is not None and ts - last < _DEDUP_S:
            return
        _seen[key] = ts
        if len(_seen) > 4096:
            for k in [k for k, v in _seen.items() if ts - v >= _DEDUP_S]:
                _seen.pop(k, None)
        q = _events.setdefault(kind, deque(maxlen=_MAX_EVENTS))
        q.append(ts)


def count(kind: str, window_s: float = WINDOW_S, now: float | None = None) -> int:
    cutoff = (time.time() if now is None else now) - window_s
    with _lock:
        q = _events.get(kind)
        if not q:
            return 0
        while q and q[0] < cutoff:
            q.popleft()
        return len(q)


def reset() -> None:
    with _lock:
        _events.clear()
        _seen.clear()
