from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from skopos.charts import PALETTE, _apply, chart_layout

ACTOR_COLORS = {
    "ssh_bruteforcer": "#EA4335",
    "port_scanner": "#FF6D00",
    "firewall_prober": "#FBBC04",
    "aggressive_scanner": "#E91E63",
    "banned_attacker": "#9334E6",
    "web_scanner": "#4285F4",
    "ssh_recon": "#00ACC1",
    "suspicious": "#5C6BC0",
    "isolated": "#9AA0A6",
    "unknown": "#80868B",
}


def chart_knocks_by_port(df: pd.DataFrame) -> go.Figure:
    if df.empty or "dest_port" not in df.columns:
        return _apply(go.Figure(), 360)
    g = (
        df[df["dest_port"].notna()]
        .groupby("dest_port")
        .size()
        .reset_index(name="hits")
        .sort_values("hits", ascending=False)
        .head(20)
    )
    fig = px.bar(
        g,
        x="dest_port",
        y="hits",
        color="hits",
        color_continuous_scale=["#e8f0fe", "#4285F4", "#174ea6"],
        title="Knocks by destination port",
        labels={"dest_port": "Port", "hits": "Events"},
    )
    fig.update_layout(**chart_layout(), showlegend=False, height=400)
    return fig


def chart_knocks_timeline(df: pd.DataFrame) -> go.Figure:
    if df.empty or "ts_utc" not in df.columns:
        return _apply(go.Figure(), 320)
    tdf = df.copy()
    tdf["ts_utc"] = pd.to_datetime(tdf["ts_utc"], errors="coerce", utc=True)
    tdf = tdf[tdf["ts_utc"].notna()]
    if tdf.empty:
        return _apply(go.Figure(), 320)
    tdf["hour"] = tdf["ts_utc"].dt.floor("h")
    g = tdf.groupby("hour").size().reset_index(name="hits")
    fig = px.area(
        g,
        x="hour",
        y="hits",
        title="Port knock timeline",
        color_discrete_sequence=[PALETTE[0]],
    )
    fig.update_layout(**chart_layout(), height=360)
    return fig


def chart_knocks_actors(summary: pd.DataFrame) -> go.Figure:
    if summary.empty:
        fig = go.Figure()
        fig.add_annotation(text="No port knock data yet", showarrow=False, font=dict(size=16))
        return _apply(fig, 360)
    g = summary.head(20).sort_values("hits")
    fig = px.bar(
        g,
        x="hits",
        y="remote_addr",
        orientation="h",
        color="actor_class",
        color_discrete_map=ACTOR_COLORS,
        hover_data=["country_name", "actor_label", "ports_targeted", "threat_score"],
        title="Top knocking IPs (classified)",
        labels={"hits": "Events", "remote_addr": "IP"},
    )
    fig.update_layout(**chart_layout(), height=max(400, 28 * len(g)), legend_title="Actor type")
    return fig


def chart_knocks_actor_types(summary: pd.DataFrame) -> go.Figure:
    if summary.empty:
        return _apply(go.Figure(), 340)
    g = summary.groupby("actor_class").agg(ips=("remote_addr", "count"), hits=("hits", "sum")).reset_index()
    fig = px.pie(
        g,
        names="actor_class",
        values="hits",
        color="actor_class",
        color_discrete_map=ACTOR_COLORS,
        title="Knock events by actor classification",
        hole=0.45,
    )
    return _apply(fig, 400)


def chart_knocks_countries(summary: pd.DataFrame) -> go.Figure:
    if summary.empty:
        return _apply(go.Figure(), 340)
    g = (
        summary[summary["country_code"].notna()]
        .groupby(["country_code", "country_name"])
        .agg(hits=("hits", "sum"), ips=("remote_addr", "count"))
        .reset_index()
        .sort_values("hits", ascending=False)
        .head(15)
    )
    if g.empty:
        return _apply(go.Figure(), 340)
    g["label"] = g.apply(
        lambda r: f"{r['country_name'] or r['country_code']} ({r['country_code']})", axis=1
    )
    fig = px.bar(
        g.sort_values("hits"),
        x="hits",
        y="label",
        orientation="h",
        color="hits",
        color_continuous_scale=["#fce8e6", "#EA4335"],
        title="Knocks by source country",
    )
    fig.update_layout(**chart_layout(), showlegend=False, height=max(360, 24 * len(g)))
    return fig


def chart_knocks_heatmap(df: pd.DataFrame) -> go.Figure:
    if df.empty:
        return _apply(go.Figure(), 360)
    tdf = df.copy()
    tdf["ts_utc"] = pd.to_datetime(tdf["ts_utc"], errors="coerce", utc=True)
    tdf = tdf[tdf["ts_utc"].notna() & tdf["dest_port"].notna()]
    if tdf.empty:
        return _apply(go.Figure(), 360)
    tdf["hour"] = tdf["ts_utc"].dt.hour
    top_ports = tdf["dest_port"].value_counts().head(12).index.tolist()
    tdf = tdf[tdf["dest_port"].isin(top_ports)]
    g = tdf.groupby(["hour", "dest_port"]).size().reset_index(name="hits")
    fig = px.density_heatmap(
        g,
        x="hour",
        y="dest_port",
        z="hits",
        color_continuous_scale=["#e8f0fe", "#4285F4", "#174ea6"],
        title="Port × hour heatmap",
        labels={"hour": "Hour (UTC)", "dest_port": "Port"},
    )
    fig.update_layout(**chart_layout(), height=420)
    return fig
