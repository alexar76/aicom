"""Notify the pipeline worker to wake immediately after API/CLI state writes."""

from __future__ import annotations

import logging
import os
import urllib.error
import urllib.request

from core.logging_utils import log_suppressed

logger = logging.getLogger(__name__)


def _truthy(name: str, default: str = "1") -> bool:
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes")


def notify_pipeline_worker_wake() -> None:
    """
    POST to the worker health server's ``/wake`` endpoint (same container as API).

    No-op when ``AIFACTORY_PIPELINE_WORKER_WAKE=0`` or health port is disabled.
    """
    if not _truthy("AIFACTORY_PIPELINE_WORKER_WAKE", "1"):
        return
    try:
        port = int(os.environ.get("AIFACTORY_WORKER_HEALTH_PORT", "8091"))
    except ValueError:
        return
    if port <= 0:
        return
    host = (os.environ.get("AIFACTORY_WORKER_HEALTH_HOST") or "127.0.0.1").strip()
    url = f"http://{host}:{port}/wake"
    req = urllib.request.Request(url, data=b"", method="POST")
    try:
        with urllib.request.urlopen(req, timeout=0.35) as resp:
            if resp.status >= 400:
                log_suppressed(
                    logger,
                    "pipeline worker wake returned HTTP %s",
                    resp.status,
                    level=logging.WARNING,
                )
    except urllib.error.URLError as exc:
        log_suppressed(
            logger,
            "pipeline worker wake skipped (worker health not reachable)",
            exc_info=exc,
        )
    except Exception as exc:
        log_suppressed(logger, "pipeline worker wake failed", exc_info=exc)
