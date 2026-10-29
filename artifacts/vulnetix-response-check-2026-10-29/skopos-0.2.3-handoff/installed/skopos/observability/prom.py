"""Prometheus PromQL client for Skopos Observability."""

from __future__ import annotations

import os
import time
from typing import Any
from urllib.parse import urljoin

import httpx

DEFAULT_PROM_URL = "http://127.0.0.1:9090/prometheus"


def prometheus_base_url() -> str:
    return (os.environ.get("SKOPOS_PROMETHEUS_URL") or DEFAULT_PROM_URL).rstrip("/") + "/"


def _get_json(path: str, params: dict[str, Any], timeout: float = 8.0) -> dict[str, Any]:
    base = prometheus_base_url()
    url = urljoin(base, path.lstrip("/"))
    try:
        with httpx.Client(timeout=timeout) as client:
            r = client.get(url, params=params)
            r.raise_for_status()
            data = r.json()
            if not isinstance(data, dict):
                return {"status": "error", "error": "non-object JSON"}
            return data
    except Exception as exc:  # network / parse
        return {"status": "error", "error": str(exc)}


def query_instant(expr: str) -> dict[str, Any]:
    """Return raw Prometheus instant-query JSON (or ``status=error``)."""
    return _get_json("api/v1/query", {"query": expr})


def query_range(expr: str, *, hours: float = 1.0, step: str = "30s") -> dict[str, Any]:
    end = time.time()
    start = end - max(0.1, hours) * 3600.0
    return _get_json(
        "api/v1/query_range",
        {"query": expr, "start": start, "end": end, "step": step},
    )


def parse_instant_vector(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize instant query result to ``[{metric, value}]``."""
    if payload.get("status") != "success":
        return []
    data = payload.get("data") or {}
    result = data.get("result") or []
    out: list[dict[str, Any]] = []
    for row in result:
        if not isinstance(row, dict):
            continue
        metric = row.get("metric") or {}
        value = row.get("value")
        val = None
        if isinstance(value, (list, tuple)) and len(value) >= 2:
            try:
                val = float(value[1])
            except (TypeError, ValueError):
                val = None
        out.append({"metric": metric, "value": val})
    return out


def parse_range_matrix(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize range query to ``[{metric, timestamps, values}]``."""
    if payload.get("status") != "success":
        return []
    data = payload.get("data") or {}
    result = data.get("result") or []
    out: list[dict[str, Any]] = []
    for row in result:
        if not isinstance(row, dict):
            continue
        metric = row.get("metric") or {}
        ts: list[float] = []
        vals: list[float] = []
        for pair in row.get("values") or []:
            if not isinstance(pair, (list, tuple)) or len(pair) < 2:
                continue
            try:
                ts.append(float(pair[0]))
                vals.append(float(pair[1]))
            except (TypeError, ValueError):
                continue
        out.append({"metric": metric, "timestamps": ts, "values": vals})
    return out


def scalar_or_none(expr: str) -> float | None:
    rows = parse_instant_vector(query_instant(expr))
    if not rows:
        return None
    return rows[0].get("value")


def demo_kpis() -> dict[str, float]:
    """Deterministic fallback when Prometheus is unreachable."""
    return {
        "hub_up": 1.0,
        "factory_up": 1.0,
        "metis_up": 1.0,
        "invoke_rps": 0.42,
        "payment_required_rps": 0.05,
        "p99_s": 1.8,
    }


def collect_overview_kpis() -> tuple[dict[str, float | None], bool]:
    """Return (kpis, live). ``live=False`` means demo fallback."""
    hub = scalar_or_none("aimarket_hub_up")
    factory = scalar_or_none('up{job="aicom"}')
    metis = scalar_or_none("metis_up") or scalar_or_none('up{job="metis"}')
    rps = scalar_or_none("sum(rate(aimarket_hub_invokes_total[5m]))")
    pay = scalar_or_none("sum(rate(aimarket_hub_payment_required_total[5m]))")
    p99 = scalar_or_none(
        "histogram_quantile(0.99, sum(rate(aimarket_hub_invoke_duration_seconds_bucket[5m])) by (le))"
    )
    if all(v is None for v in (hub, factory, metis, rps, pay, p99)):
        return demo_kpis(), False  # type: ignore[return-value]
    return {
        "hub_up": hub,
        "factory_up": factory,
        "metis_up": metis,
        "invoke_rps": rps,
        "payment_required_rps": pay,
        "p99_s": p99,
    }, True
