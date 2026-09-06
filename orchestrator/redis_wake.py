"""Redis-backed pipeline worker wake signals (distributed queue stub → real).

When ``AIFACTORY_PIPELINE_QUEUE_BACKEND=redis``, workers subscribe to a shared
Redis list so multiple pipeline-worker containers can wake each other without
polling SQLite/Postgres alone.

Env:
  REDIS_URL or AIFACTORY_REDIS_URL — default redis://redis:6379/0
  AIFACTORY_PIPELINE_WAKE_KEY — default aicom:pipeline:wake
"""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Callable
from urllib.parse import quote

logger = logging.getLogger(__name__)

_WAKE_KEY = os.environ.get("AIFACTORY_PIPELINE_WAKE_KEY", "aicom:pipeline:wake")


def redis_url() -> str:
    password = os.environ.get("REDIS_PASSWORD", "")
    if password:
        host = os.environ.get("AIFACTORY_REDIS_HOST", "redis").strip() or "redis"
        port = os.environ.get("AIFACTORY_REDIS_PORT", "6379").strip() or "6379"
        db = os.environ.get("AIFACTORY_REDIS_DB", "0").strip() or "0"
        return f"redis://:{quote(password, safe='')}@{host}:{port}/{db}"
    return (
        os.environ.get("AIFACTORY_REDIS_URL", "").strip()
        or os.environ.get("REDIS_URL", "").strip()
        or "redis://redis:6379/0"
    )


def publish_wake(reason: str = "") -> bool:
    """Push a wake signal for all pipeline workers. Returns False when not using redis."""
    from orchestrator.queue_backend import pipeline_queue_backend

    if pipeline_queue_backend() != "redis":
        return False
    try:
        import redis

        client = redis.from_url(redis_url(), decode_responses=True)
        try:
            client.lpush(_WAKE_KEY, reason or str(time.time()))
            return True
        finally:
            client.close()
    except Exception as exc:
        logger.warning("redis wake publish failed: %s", exc)
        return False


class RedisWakeListener:
    """Background thread: BRPOP wake key → callback (typically worker.signal_new_work)."""

    def __init__(self, on_wake: Callable[[], None], *, stop_event: threading.Event | None = None):
        self._on_wake = on_wake
        self._stop = stop_event or threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, name="redis-wake-listener", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        try:
            import redis
        except ImportError:
            logger.warning("redis package not installed — wake listener disabled")
            return
        client = redis.from_url(redis_url(), decode_responses=True)
        try:
            while not self._stop.is_set():
                try:
                    item = client.brpop(_WAKE_KEY, timeout=2)
                    if item and not self._stop.is_set():
                        self._on_wake()
                except Exception as exc:
                    if not self._stop.is_set():
                        logger.debug("redis wake listen: %s", exc)
                    time.sleep(1.0)
        finally:
            client.close()
