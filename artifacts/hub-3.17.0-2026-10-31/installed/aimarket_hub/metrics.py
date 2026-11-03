"""Prometheus metrics for the AIMarket Hub.

Exposed at ``GET /metrics`` (Prometheus text format). Scrape from the factory
Prometheus job ``aimarket-hub`` — see ``prometheus.yml`` and
``docs/observability-prometheus.md``.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Iterator

from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
    CONTENT_TYPE_LATEST,
)

REGISTRY = CollectorRegistry(auto_describe=True)

hub_up = Gauge(
    "aimarket_hub_up",
    "1 if the hub process is serving requests",
    registry=REGISTRY,
)
hub_up.set(1)

invokes_total = Counter(
    "aimarket_hub_invokes_total",
    "Total /ai-market/v2/invoke attempts by capability and result class",
    ["capability", "result"],
    registry=REGISTRY,
)

invoke_duration_seconds = Histogram(
    "aimarket_hub_invoke_duration_seconds",
    "Wall time of /ai-market/v2/invoke handlers",
    ["capability"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0),
    registry=REGISTRY,
)

payment_required_total = Counter(
    "aimarket_hub_payment_required_total",
    "Invokes rejected with HTTP 402 payment_required",
    ["capability"],
    registry=REGISTRY,
)

# Federation health. A peer whose key pin stops matching is rejected fail-closed
# and its catalogue silently freezes at whatever was last indexed — the hub keeps
# serving, so nothing else goes red. One such peer sat rejected for five days,
# taking a paid capability out of the catalogue, with a bar on an analytics
# dashboard as the only symptom. These two gauges are what an alert can watch.
federation_peers_rejected = Gauge(
    "aimarket_hub_federation_peers_rejected",
    "Federation peers whose advertised signing key does not match the pinned one",
    registry=REGISTRY,
)

federation_peer_stalest_crawl_seconds = Gauge(
    "aimarket_hub_federation_peer_stalest_crawl_seconds",
    "Age in seconds of the oldest successful crawl among known peers "
    "(-1 when no peer has ever been crawled)",
    registry=REGISTRY,
)


mcp_requests_total = Counter(
    "aimarket_hub_mcp_requests_total",
    "MCP gateway requests by JSON-RPC method, tool and client family — the stranger funnel "
    "(initialize → tools/list → tools/call)",
    ["method", "tool", "client"],
    registry=REGISTRY,
)

_MCP_LABEL_CHARS = frozenset("abcdefghijklmnopqrstuvwxyz0123456789_-/")


def record_mcp_request(method: str, tool: str = "-", client: str = "unknown") -> None:
    """Count one MCP request. Labels come from fixed allowlists in the gateway; anything
    else collapses to "other" here as well, so a caller can never mint a new series."""
    def _label(value: str) -> str:
        value = str(value or "-").lower()[:40]
        return value if value and set(value) <= _MCP_LABEL_CHARS | {"-"} else "other"

    mcp_requests_total.labels(_label(method), _label(tool), _label(client)).inc()


a2a_requests_total = Counter(
    "aimarket_hub_a2a_requests_total",
    "A2A traffic: Agent Card reads and /a2a JSON-RPC calls by method and outcome. A "
    "marketplace-invoke task is counted by the state it reached (completed, input_required, "
    "auth_required, rejected, failed, canceled), so it shows whether A2A buyers end up paying.",
    ["method", "result"],
    registry=REGISTRY,
)

# The A2A 1.0 method names. Anything else a caller sends is counted as "other", so the
# label set is fixed by this list, never by traffic.
A2A_METHODS = frozenset({
    "SendMessage", "SendStreamingMessage", "GetTask", "ListTasks", "CancelTask",
    "SubscribeToTask", "GetExtendedAgentCard", "CreateTaskPushNotificationConfig",
    "GetTaskPushNotificationConfig", "ListTaskPushNotificationConfigs",
    "DeleteTaskPushNotificationConfig",
})
_A2A_RESULT_CHARS = frozenset("abcdefghijklmnopqrstuvwxyz0123456789_")


def record_a2a_request(method: str, result: str) -> None:
    method = method if method in A2A_METHODS or method in ("agent-card", "-") else "other"
    result = str(result or "ok").lower()[:40]
    if not set(result) <= _A2A_RESULT_CHARS:
        result = "other"
    a2a_requests_total.labels(method, result).inc()


verify_appeals_total = Counter(
    "aimarket_hub_verify_appeals_total",
    "Pay-on-Verified appeals by appellant and outcome. upheld = the appeal court agreed "
    "with the first verdict, overturned = it did not, indeterminate = it reached no genuine "
    "verdict. upheld / (upheld + overturned) is the first instance's agreement rate — the "
    "research signal for calibrating the first-instance jury. Resets with the process; the "
    "durable record is GET /ai-market/v2/verification/appeals/stats.",
    ["party", "outcome"],
    registry=REGISTRY,
)

_APPEAL_PARTIES = frozenset({"buyer", "seller"})
_APPEAL_OUTCOMES = frozenset({"upheld", "overturned", "indeterminate"})


def record_verify_appeal(party: str, outcome: str) -> None:
    party = party if party in _APPEAL_PARTIES else "other"
    outcome = outcome if outcome in _APPEAL_OUTCOMES else "other"
    verify_appeals_total.labels(party, outcome).inc()


def set_federation_peer_health(rejected: int, stalest_crawl_age_s: float | None) -> None:
    """Publish federation peer health. ``None`` age means no peer crawled yet."""
    federation_peers_rejected.set(max(0, int(rejected)))
    federation_peer_stalest_crawl_seconds.set(
        -1.0 if stalest_crawl_age_s is None else max(0.0, float(stalest_crawl_age_s))
    )


def _cap_label(capability_id: str | None) -> str:
    raw = (capability_id or "unknown").strip() or "unknown"
    # Keep cardinality bounded for Prometheus.
    return raw[:96]


def record_invoke(capability_id: str | None, result: str, duration_s: float | None = None) -> None:
    """Record one invoke outcome. ``result`` is a short class: ok, payment_required, error, …"""
    cap = _cap_label(capability_id)
    label = (result or "error").strip()[:32] or "error"
    invokes_total.labels(capability=cap, result=label).inc()
    if label == "payment_required":
        payment_required_total.labels(capability=cap).inc()
    if duration_s is not None and duration_s >= 0:
        invoke_duration_seconds.labels(capability=cap).observe(duration_s)


@contextmanager
def track_invoke(capability_id: str | None) -> Iterator[dict[str, str]]:
    """Context manager: sets ``slot['result']`` (default ``ok``) and records on exit."""
    slot: dict[str, str] = {"result": "ok", "capability": _cap_label(capability_id)}
    t0 = time.perf_counter()
    try:
        yield slot
    except Exception:
        if slot.get("result") == "ok":
            slot["result"] = "error"
        raise
    finally:
        record_invoke(
            slot.get("capability") or capability_id,
            slot.get("result") or "error",
            duration_s=time.perf_counter() - t0,
        )


def metrics_payload() -> tuple[bytes, str]:
    """Return (body, content_type) for the /metrics HTTP response."""
    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST
