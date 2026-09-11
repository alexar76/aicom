"""Push live pipeline snapshot gauges into Prometheus (API process /metrics)."""

from __future__ import annotations

import asyncio
import logging

from web.backend.api.admin.dashboard.helpers import _fast_pipeline_metrics
from web.backend.api.metrics import PrometheusMetrics

logger = logging.getLogger(__name__)

_SYNC_INTERVAL_SEC = int(__import__("os").environ.get("AIFACTORY_PIPELINE_METRICS_INTERVAL_SEC", "30"))


def sync_pipeline_prometheus_gauges() -> None:
    """Refresh pipeline/task gauges from SQLite or pipeline.json."""
    try:
        pipeline, state_distribution = _fast_pipeline_metrics()
    except Exception as exc:
        logger.warning("Pipeline Prometheus sync skipped: %s", exc)
        return

    for state, count in (state_distribution or {}).items():
        PrometheusMetrics.set_state_count(str(state), int(count))

    PrometheusMetrics.set_active_products(int(pipeline.get("active_products") or 0))

    task_counts = {
        "pending": int(pipeline.get("pending_tasks") or 0),
        "running": int(pipeline.get("running_tasks") or 0),
        "completed": int(pipeline.get("completed_products") or 0),
        "failed": int(pipeline.get("failed_products") or 0),
        "timedout": int(pipeline.get("timed_out_tasks") or 0),
    }
    PrometheusMetrics.set_task_status_counts(task_counts)

    PrometheusMetrics.set_pipeline_totals(
        total_products=int(pipeline.get("total_products") or 0),
        completed_products=int(pipeline.get("completed_products") or 0),
        failed_products=int(pipeline.get("failed_products") or 0),
    )


async def pipeline_prometheus_sync_loop() -> None:
    while True:
        try:
            await asyncio.to_thread(sync_pipeline_prometheus_gauges)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Pipeline Prometheus sync failed: %s", exc)
        await asyncio.sleep(_SYNC_INTERVAL_SEC)
