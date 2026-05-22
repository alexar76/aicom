"""
Pipeline task queue backend selector (inline today; Redis/Celery reserved).

Set ``AIFACTORY_PIPELINE_QUEUE_BACKEND=redis`` when a distributed worker is deployed.
Until then the pipeline worker polls SQLite/Postgres in-process.
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
