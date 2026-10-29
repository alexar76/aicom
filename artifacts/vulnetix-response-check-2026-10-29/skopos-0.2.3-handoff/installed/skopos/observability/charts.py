"""Plotly charts for Skopos Observability."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import plotly.graph_objects as go

from skopos.charts import PALETTE, chart_layout


def chart_kpi_gauges(kpis: dict[str, float | None]) -> go.Figure:
    labels = ["Hub", "Factory", "Metis", "Invoke RPS", "402 RPS", "p99 s"]
    keys = ["hub_up", "factory_up", "metis_up", "invoke_rps", "payment_required_rps", "p99_s"]
    values = [float(kpis.get(k) or 0.0) for k in keys]
    colors = [PALETTE[i % len(PALETTE)] for i in range(len(labels))]
    fig = go.Figure(
        data=[
            go.Bar(
                x=labels,
                y=values,
                marker_color=colors,
                text=[f"{v:.3g}" for v in values],
                textposition="outside",
            )
        ]
    )
    fig.update_layout(**chart_layout(), title="Fleet KPIs", yaxis_title="value", height=360)
    return fig


def chart_timeseries_matrix(series: list[dict[str, Any]], title: str) -> go.Figure:
    fig = go.Figure()
    for i, row in enumerate(series or []):
        metric = row.get("metric") or {}
        name = (
            metric.get("capability")
            or metric.get("result")
            or metric.get("job")
            or metric.get("__name__")
            or f"s{i}"
        )
        ts = row.get("timestamps") or []
        vals = row.get("values") or []
        if not ts:
            continue
        x = [datetime.fromtimestamp(t, tz=timezone.utc) for t in ts]
        fig.add_trace(
            go.Scatter(
                x=x,
                y=vals,
                mode="lines",
                name=str(name)[:48],
                line={"color": PALETTE[i % len(PALETTE)], "width": 2},
            )
        )
    if not fig.data:
        fig.add_annotation(text="No time series yet", xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False)
    layout = {**chart_layout(), "title": title, "height": 420}
    layout["legend"] = {**(layout.get("legend") or {}), "orientation": "h"}
    fig.update_layout(**layout)
    return fig


def chart_heatmap_by_capability(rows: list[dict[str, Any]], title: str = "Invoke intensity") -> go.Figure:
    """Build a simple capability × result heatmap from instant vectors."""
    caps: list[str] = []
    results: list[str] = []
    grid: dict[tuple[str, str], float] = {}
    for row in rows:
        metric = row.get("metric") or {}
        cap = str(metric.get("capability") or "unknown")[:40]
        res = str(metric.get("result") or "n/a")[:24]
        val = float(row.get("value") or 0.0)
        caps.append(cap)
        results.append(res)
        grid[(cap, res)] = val
    caps_u = sorted(set(caps)) or ["—"]
    res_u = sorted(set(results)) or ["—"]
    z = [[grid.get((c, r), 0.0) for r in res_u] for c in caps_u]
    fig = go.Figure(
        data=go.Heatmap(
            z=z,
            x=res_u,
            y=caps_u,
            colorscale="Tealgrn",
            colorbar={"title": "rate"},
        )
    )
    layout = {**chart_layout(), "title": title, "height": max(360, 28 * len(caps_u))}
    base_margin = dict(layout.get("margin") or {})
    base_margin["l"] = max(int(base_margin.get("l") or 0), 160)
    layout["margin"] = base_margin
    fig.update_layout(**layout)
    return fig


def targets_table_rows(live: bool, kpis: dict[str, float | None]) -> list[dict[str, Any]]:
    def status(v: float | None) -> str:
        if v is None:
            return "unknown"
        return "up" if v >= 0.5 else "down"

    return [
        {
            "target": "aimarket-hub",
            "job": "aimarket-hub",
            "status": status(kpis.get("hub_up")),
            "source": "live" if live else "demo",
        },
        {
            "target": "ai-factory",
            "job": "aicom",
            "status": status(kpis.get("factory_up")),
            "source": "live" if live else "demo",
        },
        {
            "target": "metis",
            "job": "metis",
            "status": status(kpis.get("metis_up")),
            "source": "live" if live else "demo",
        },
    ]
