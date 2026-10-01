"""
Pipeline task queue backend selector (inline default; Redis wake for multi-worker).

Set ``AIFACTORY_PIPELINE_QUEUE_BACKEND=redis`` with ``AIFACTORY_REDIS_URL`` so
pipeline workers wake each other via ``orchestrator/redis_wake.py``.
Task state remains in SQLite/Postgres; Redis carries wake signals only.
"""

from __future__ import annotations

import os
from typing import Literal

QueueBackend = Literal["inline", "redis"]


def pipeline_queue_backend() -> QueueBackend:
    raw = os.environ.get("AIFACTORY_PIPELINE_QUEUE_BACKEND", "inline").strip().lower()
    if raw in ("redis", "celery", "temporal"):
        return "redis"
    return "inline"


def worker_identity() -> str:
    return os.environ.get("AIFACTORY_PIPELINE_WORKER_ID", "worker-1").strip() or "worker-1"
