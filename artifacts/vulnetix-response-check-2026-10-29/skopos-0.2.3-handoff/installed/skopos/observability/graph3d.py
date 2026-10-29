"""3D service-health graph for Skopos Observability."""

from __future__ import annotations

from typing import Any

import plotly.graph_objects as go

from skopos.charts import PALETTE, chart_layout

# Fixed layout positions for the ecosystem constellation.
NODES: list[dict[str, Any]] = [
    {"id": "factory", "label": "Factory", "xyz": (-2.0, 0.2, 0.0), "kpi": "factory_up"},
    {"id": "hub", "label": "Hub", "xyz": (0.0, 1.2, 0.4), "kpi": "hub_up"},
    {"id": "metis", "label": "Metis", "xyz": (2.0, 0.4, -0.2), "kpi": "metis_up"},
    {"id": "gaia", "label": "GAIA", "xyz": (1.2, -1.4, 0.6), "kpi": None},
    {"id": "oracles", "label": "Oracles", "xyz": (-1.4, -1.2, 0.5), "kpi": None},
    {"id": "skopos", "label": "Skopos", "xyz": (0.2, -0.2, -1.4), "kpi": None},
]

EDGES: list[tuple[str, str]] = [
    ("factory", "hub"),
    ("hub", "oracles"),
    ("hub", "gaia"),
    ("hub", "metis"),
    ("factory", "skopos"),
    ("metis", "skopos"),
    ("oracles", "gaia"),
]


def _node_map() -> dict[str, dict[str, Any]]:
    return {n["id"]: n for n in NODES}


def chart_service_graph_3d(kpis: dict[str, float | None] | None = None) -> go.Figure:
    """Plotly 3D scatter + edge lines colored by health KPIs."""
    kpis = kpis or {}
    nodes = _node_map()

    edge_x: list[float | None] = []
    edge_y: list[float | None] = []
    edge_z: list[float | None] = []
    for a, b in EDGES:
        xa, ya, za = nodes[a]["xyz"]
        xb, yb, zb = nodes[b]["xyz"]
        edge_x += [xa, xb, None]
        edge_y += [ya, yb, None]
        edge_z += [za, zb, None]

    edge_trace = go.Scatter3d(
        x=edge_x,
        y=edge_y,
        z=edge_z,
        mode="lines",
        line={"color": "rgba(140,170,200,0.45)", "width": 4},
        hoverinfo="none",
        name="links",
    )

    xs, ys, zs, texts, colors, sizes = [], [], [], [], [], []
    for n in NODES:
        x, y, z = n["xyz"]
        xs.append(x)
        ys.append(y)
        zs.append(z)
        key = n.get("kpi")
        val = kpis.get(key) if key else None
        if val is None:
            color = PALETTE[2]
            state = "n/a"
            size = 12
        elif val >= 0.5:
            color = PALETTE[1]
            state = "up"
            size = 16
        else:
            color = "#EA4335"
            state = "down"
            size = 18
        colors.append(color)
        sizes.append(size)
        texts.append(f"{n['label']}<br>status={state}")

    node_trace = go.Scatter3d(
        x=xs,
        y=ys,
        z=zs,
        mode="markers+text",
        text=[n["label"] for n in NODES],
        textposition="top center",
        marker={
            "size": sizes,
            "color": colors,
            "opacity": 0.95,
            "line": {"width": 1, "color": "#0b1220"},
        },
        hovertext=texts,
        hoverinfo="text",
        name="services",
    )

    fig = go.Figure(data=[edge_trace, node_trace])
    layout = {**chart_layout(), "title": "Service graph (3D)", "height": 560, "showlegend": False}
    layout["margin"] = {"l": 0, "r": 0, "t": 48, "b": 0}
    layout["scene"] = {
        "xaxis": {"visible": False},
        "yaxis": {"visible": False},
        "zaxis": {"visible": False},
        "bgcolor": "rgba(0,0,0,0)",
    }
    fig.update_layout(**layout)
    return fig
