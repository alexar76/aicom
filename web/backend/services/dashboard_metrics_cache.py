"""Short-TTL in-process cache for GET /api/admin/dashboard (quick + full)."""

from __future__ import annotations

import copy
import logging
import os
import threading
import time
from typing import Any, Callable

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_quick_payload: dict[str, Any] | None = None
_quick_mono: float = -1e18
_full_payload: dict[str, Any] | None = None
_full_mono: float = -1e18


def _quick_ttl_sec() -> float:
    return max(2.0, float(os.environ.get("AIFACTORY_DASHBOARD_QUICK_CACHE_TTL_SEC", "8")))


def _full_ttl_sec() -> float:
    return max(3.0, float(os.environ.get("AIFACTORY_DASHBOARD_FULL_CACHE_TTL_SEC", "15")))


def get_cached_dashboard(*, quick: bool) -> dict[str, Any] | None:
    ttl = _quick_ttl_sec() if quick else _full_ttl_sec()
    with _lock:
        payload = _quick_payload if quick else _full_payload
        mono = _quick_mono if quick else _full_mono
        if payload is None:
            return None
        if (time.monotonic() - mono) >= ttl:
            return None
        return copy.deepcopy(payload)


def set_cached_dashboard(payload: dict[str, Any], *, quick: bool) -> None:
    global _quick_payload, _quick_mono, _full_payload, _full_mono
    with _lock:
        if quick:
            _quick_payload = copy.deepcopy(payload)
            _quick_mono = time.monotonic()
        else:
            _full_payload = copy.deepcopy(payload)
            _full_mono = time.monotonic()


def invalidate_dashboard_metrics_cache() -> None:
    global _quick_payload, _quick_mono, _full_payload, _full_mono
    with _lock:
        _quick_payload = None
        _quick_mono = -1e18
        _full_payload = None
        _full_mono = -1e18


def get_or_build_dashboard(builder: Callable[[], dict[str, Any]], *, quick: bool) -> dict[str, Any]:
    cached = get_cached_dashboard(quick=quick)
    if cached is not None:
        return cached
    try:
        payload = builder()
    except Exception as exc:
        logger.warning("dashboard metrics build failed (quick=%s): %s", quick, exc)
        raise
    set_cached_dashboard(payload, quick=quick)
    return payload
