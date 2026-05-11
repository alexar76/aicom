"""
Prometheus Metrics
===================
Central metrics module for Prometheus instrumentation.
Defines all counters, histograms, and gauges used across AI-Factory components.
"""

from __future__ import annotations

import logging
from typing import Optional

from prometheus_client import Counter, Histogram, Gauge, CollectorRegistry, generate_latest

logger = logging.getLogger(__name__)

# ── Registry ────────────────────────────────────────────────────────────────
# Shared registry so all metrics are collected together
REGISTRY = CollectorRegistry(auto_describe=True)


# ── Pipeline Metrics ────────────────────────────────────────────────────────

pipeline_products_total = Gauge(
    "pipeline_products_total",
    "Number of products currently in each pipeline state",
    ["state"],
    registry=REGISTRY,
)

pipeline_tasks_total = Counter(
    "pipeline_tasks_total",
    "Total number of tasks by status (completed, failed, timedout)",
    ["status"],
    registry=REGISTRY,
)

pipeline_products_created_total = Counter(
    "pipeline_products_created_total",
    "Total number of products created",
    registry=REGISTRY,
)

pipeline_task_duration_seconds = Histogram(
    "pipeline_task_duration_seconds",
    "Duration of agent tasks in seconds",
    ["agent_type"],
    buckets=(1, 5, 10, 30, 60, 120, 300, 600, 1800, 3600),
    registry=REGISTRY,
)


# ── Director Metrics ────────────────────────────────────────────────────────

director_decisions_total = Counter(
    "director_decisions_total",
    "Total number of Director AI decisions generated",
    ["action", "type"],
    registry=REGISTRY,
)

director_analysis_duration_seconds = Histogram(
    "director_analysis_duration_seconds",
    "Duration of Director AI analysis cycles in seconds",
    buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 120.0),
    registry=REGISTRY,
)


# ── LLM Metrics ─────────────────────────────────────────────────────────────

llm_requests_total = Counter(
    "llm_requests_total",
    "Total number of LLM requests by provider and status",
    ["provider", "status"],
    registry=REGISTRY,
)

llm_request_duration_seconds = Histogram(
    "llm_request_duration_seconds",
    "Duration of LLM requests in seconds",
    ["provider"],
    buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0),
    registry=REGISTRY,
)

llm_provider_health = Gauge(
    "llm_provider_health",
    "Health status of LLM providers (1=healthy, 0=unhealthy)",
    ["provider"],
    registry=REGISTRY,
)


# ── Active Products Gauge (helper, no label) ────────────────────────────────

pipeline_active_products = Gauge(
    "pipeline_active_products",
    "Number of currently active products in the pipeline",
    registry=REGISTRY,
)


class PrometheusMetrics:
    """
    Convenience wrapper around Prometheus metrics.
    
    Provides helper methods that components can call to update
    metrics without importing the raw metric objects directly.
    """

    # ── Pipeline ────────────────────────────────────────────────────────

    @staticmethod
    def inc_product_created():
        """Increment the product creation counter."""
        pipeline_products_created_total.inc()

    @staticmethod
    def inc_task(status: str):
        """Increment the task counter for a given status."""
        pipeline_tasks_total.labels(status=status).inc()

    @staticmethod
    def observe_task_duration(agent_type: str, duration_sec: float):
        """Observe the duration of an agent task."""
        pipeline_task_duration_seconds.labels(agent_type=agent_type).observe(duration_sec)

    @staticmethod
    def set_state_count(state: str, count: int):
        """Set the number of products in a given pipeline state."""
        pipeline_products_total.labels(state=state).set(count)

    @staticmethod
    def set_active_products(count: int):
        """Set the number of active products."""
        pipeline_active_products.set(count)

    @staticmethod
    def update_pipeline_gauges(products: list) -> None:
        """
        Update all pipeline gauges from a list of product objects.
        
        Args:
            products: List of product objects with a ``state`` attribute
                      that has a ``value`` string (e.g. PipelineState enum).
        """
        from collections import Counter as CollectionsCounter
        state_counts: dict[str, int] = CollectionsCounter()
        active = 0
        terminal_states = {"completed", "failed", "cancelled"}

        for p in products:
            state_val = p.state.value if hasattr(p.state, "value") else str(p.state)
            state_counts[state_val] += 1
            if state_val not in terminal_states:
                active += 1

        for state, count in state_counts.items():
            PrometheusMetrics.set_state_count(state, count)
        PrometheusMetrics.set_active_products(active)

    # ── Director ────────────────────────────────────────────────────────

    @staticmethod
    def inc_decision(action: str, decision_type: str):
        """Increment the decision counter for a given action and type."""
        director_decisions_total.labels(action=action, type=decision_type).inc()

    @staticmethod
    def observe_analysis_duration(duration_sec: float):
        """Observe the duration of a Director analysis cycle."""
        director_analysis_duration_seconds.observe(duration_sec)

    # ── LLM ─────────────────────────────────────────────────────────────

    @staticmethod
    def inc_llm_request(provider: str, status: str):
        """Increment the LLM request counter for a given provider and status."""
        llm_requests_total.labels(provider=provider, status=status).inc()

    @staticmethod
    def observe_llm_duration(provider: str, duration_sec: float):
        """Observe the duration of an LLM request."""
        llm_request_duration_seconds.labels(provider=provider).observe(duration_sec)

    @staticmethod
    def set_provider_health(provider: str, healthy: bool):
        """Set the health gauge for a provider (1=healthy, 0=unhealthy)."""
        llm_provider_health.labels(provider=provider).set(1 if healthy else 0)


def get_registry() -> CollectorRegistry:
    """Return the shared Prometheus registry for exposing metrics."""
    return REGISTRY
