"""Global minimum interval between outbound LLM HTTP calls."""

from __future__ import annotations

import os
import threading
import time

_lock = threading.Lock()
_last_call_at = 0.0


def llm_min_interval_sec() -> float:
    raw = os.environ.get("LLM_MIN_INTERVAL_SEC", "2.0")
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 2.0


def wait_before_llm_call() -> None:
    interval = llm_min_interval_sec()
    if interval <= 0:
        return
    global _last_call_at
    with _lock:
        now = time.monotonic()
        wait = interval - (now - _last_call_at)
        if wait > 0:
            time.sleep(wait)
        _last_call_at = time.monotonic()
