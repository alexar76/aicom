"""Bounded-latency cache for public storefront category totals (shared with listable count).

One full scan (same as ``GET /api/products/categories``) backs both category tabs and
``count_showcase_listable_products`` so admin dashboard, pipeline catalog, and metrics
do not each run multi-second disk-heavy loops.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError as FuturesTimeout
from typing import Any

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="sf_counts")

_lock = threading.Lock()
_cached: dict[str, Any] | None = None
_cached_mono: float = -1e18
_inflight: Future | None = None
_force_refresh = False


def _ttl_sec() -> float:
    return max(5.0, float(os.environ.get("AIFACTORY_STOREFRONT_LISTABLE_CACHE_TTL_SEC", "30")))


def _max_wait_sec() -> float:
    return max(0.5, float(os.environ.get("AIFACTORY_STOREFRONT_LISTABLE_MAX_WAIT_SEC", "8.0")))


def invalidate_storefront_categories_cache() -> None:
    """Call after admin mutations that can change storefront visibility or category buckets."""
    global _force_refresh
    with _lock:
        _force_refresh = True


def _empty_payload(*, pending: bool = False) -> dict[str, Any]:
    return {"categories": [], "total_count": None, "pending": pending, "stale": False}


def _wrap_payload(payload: dict[str, Any], *, stale: bool = False) -> dict[str, Any]:
    out = dict(payload)
    out["stale"] = stale
    out.setdefault("pending", False)
    if "total_count" in out and out["total_count"] is not None:
        out["total_count"] = int(out["total_count"])
    return out


def _work() -> dict[str, Any]:
    from web.backend.api.products import build_storefront_categories_response

    return build_storefront_categories_response()


def get_storefront_categories_cached() -> dict[str, Any]:
    """Return ``{categories, total_count}``; blocks at most ``AIFACTORY_STOREFRONT_LISTABLE_MAX_WAIT_SEC``."""
    global _cached, _cached_mono, _inflight, _force_refresh

    ttl = _ttl_sec()
    max_wait = _max_wait_sec()

    with _lock:
        now = time.monotonic()
        if (
            not _force_refresh
            and _cached is not None
            and (now - _cached_mono) < ttl
        ):
            return _wrap_payload(_cached, stale=False)
        _force_refresh = False

        if _inflight is not None and _inflight.done():
            try:
                pl = _inflight.result()
                if isinstance(pl, dict) and pl.get("total_count") is not None:
                    _cached = pl
                    _cached_mono = time.monotonic()
            except Exception as e:
                logger.warning("storefront counts cache: completed job failed (%s)", e)
            _inflight = None

        now = time.monotonic()
        if _cached is not None and (now - _cached_mono) < ttl:
            return _wrap_payload(_cached, stale=False)

        if _inflight is None:
            _inflight = _executor.submit(_work)
        fut = _inflight

    try:
        payload = fut.result(timeout=max_wait)
        if not isinstance(payload, dict) or payload.get("total_count") is None:
            raise ValueError("invalid categories payload")
        with _lock:
            _cached = payload
            _cached_mono = time.monotonic()
            _inflight = None
        return _wrap_payload(payload, stale=False)
    except FuturesTimeout:
        logger.warning(
            "storefront counts cache: compute exceeded %.1fs — returning stale or pending",
            max_wait,
        )
        with _lock:
            if _cached is not None:
                return _wrap_payload(_cached, stale=True)
            return _empty_payload(pending=True)
    except Exception as e:
        logger.warning("storefront counts cache: compute failed (%s)", e)
        with _lock:
            _inflight = None
            if _cached is not None:
                return _wrap_payload(_cached, stale=True)
        return _empty_payload(pending=True)
