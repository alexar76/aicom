from __future__ import annotations

import math

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from .countries import alpha2_to_alpha3
from .geo_centroids import alpha2_to_centroid
from .geo_earth import build_country_border_lines, build_textured_earth_mesh, latlon_to_xyz
from .i18n import t
from .themes import (
    apply_chart_theme,
    chart_layout_kwargs,
    get_active_theme,
    plotly_hover_bg,
    plotly_hover_font,
    skopos_plotly_template,
)

# GA / Yandex Metrika inspired palette
PALETTE = [
    "#4285F4",
    "#34A853",
    "#FBBC04",
    "#EA4335",
    "#9334E6",
    "#00ACC1",
    "#FF6D00",
    "#7CB342",
    "#E91E63",
    "#5C6BC0",
]

CHART_LAYOUT = chart_layout_kwargs()  # legacy import; prefer chart_layout()


def chart_layout() -> dict:
    return chart_layout_kwargs()


def _chart_layout() -> dict:
    return chart_layout_kwargs()


def short_path_label(path: str, *, max_len: int = 34) -> str:
    """Compact filesystem path for chart tick labels."""
    p = (path or "").strip()
    if p == "/":
        return "/"
    p = p.rstrip("/")
    if not p:
        return "/"
    if len(p) <= max_len:
        return p

    docker_markers = ("/overlay2/", "/overlayfs/", "/rootfs/overlay", "/docker/")
    if any(marker in p for marker in docker_markers):
        parts = [x for x in p.split("/") if x]
        leaf = parts[-1]
        if leaf in {"merged", "upper", "work", "rootfs"} and len(parts) >= 2:
            leaf = parts[-2]
        prefix = "docker …/"
        room = max(8, max_len - len(prefix) - 1)
        return f"{prefix}{leaf[:room]}…"

    return f"…{p[-(max_len - 1):]}"


def prevent_label_overlap(fig: go.Figure) -> go.Figure:
    """Keep category tick labels from colliding with each other or axis titles."""
    if fig.data and all(getattr(trace, "type", None) == "indicator" for trace in fig.data):
        return fig
    fig.update_xaxes(automargin=True, title_standoff=14)
    fig.update_yaxes(automargin=True, title_standoff=14)

    x_labels: list[str] = []
    y_labels: list[str] = []
    for trace in fig.data:
        x = getattr(trace, "x", None)
        y = getattr(trace, "y", None)
        if x is not None:
            x_labels.extend(str(v) for v in x if isinstance(v, str))
        if y is not None:
            y_labels.extend(str(v) for v in y if isinstance(v, str))

    def _max_len(labels: list[str]) -> int:
        return max((len(s) for s in labels), default=0)

    max_x, max_y = _max_len(x_labels), _max_len(y_labels)
    margin = fig.layout.margin
    m = dict(
        l=margin.l if margin and margin.l is not None else 32,
        r=margin.r if margin and margin.r is not None else 32,
        t=margin.t if margin and margin.t is not None else 64,
        b=margin.b if margin and margin.b is not None else 48,
    )

    if max_x > 12:
        angle = -35 if max_x <= 24 else (-55 if max_x <= 40 else -90)
        fig.update_xaxes(tickangle=angle)
        extra = max_x * (2.4 if angle != -90 else 3.8)
        m["b"] = max(m["b"], min(240, int(48 + extra)))

    if max_y > 12:
        m["l"] = max(m["l"], min(360, int(40 + max_y * 6.5)))

    # Horizontal bars with outside value labels — extend x range so digits are not clipped.
    for trace in fig.data:
        if getattr(trace, "type", None) != "bar":
            continue
        if (getattr(trace, "orientation", None) or "v") != "h":
            continue
        textpos = getattr(trace, "textposition", None)
        if textpos not in ("outside", "auto"):
            continue
        x_vals = trace.x
        if x_vals is None:
            continue
        nums: list[float] = []
        for v in x_vals:
            if v is None:
                continue
            try:
                nums.append(float(v))
            except (TypeError, ValueError):
                continue
        if not nums:
            continue
        max_val = max(nums)
        if max_val <= 0:
            continue
        max_label = f"{int(max_val):,}" if max_val >= 10 else f"{max_val:g}"
        label_width = len(max_label)
        pad_ratio = max(0.14, 0.06 + label_width * 0.018)
        # Each bar already carries its value as an outside text label, so the
        # numeric value-axis ticks are redundant. Worse: when long category labels
        # (git URLs, /ws?token=… paths) make automargin widen the opposite side,
        # the plot area collapses and those ticks pile into an unreadable stack of
        # overlapping digits under the axis title. Hide them — the bar labels stay.
        fig.update_xaxes(range=[0, max_val * (1 + pad_ratio)], showticklabels=False)
        m["r"] = max(m["r"], 24 + label_width * 8)
        trace.cliponaxis = False
        break

    fig.update_layout(margin=m)
    return fig


def _apply(fig: go.Figure, height: int = 440) -> go.Figure:
    th = get_active_theme()
    fig.update_layout(**_chart_layout(), height=height, showlegend=False)
    fig.update_xaxes(showgrid=True, zeroline=False)
    fig.update_yaxes(showgrid=True, zeroline=False)
    apply_chart_theme(fig, th)
    prevent_label_overlap(fig)
    fig.update_layout(title=dict(x=0.02, xanchor="left", font=dict(size=16, color=th.chart_title)))
    return fig


def _apply_donut(fig: go.Figure, title: str, height: int = 520) -> go.Figure:
    """Donut / pie — legend below chart, no title overlap."""
    th = get_active_theme()
    n_slices = len(fig.data[0].labels) if fig.data and hasattr(fig.data[0], "labels") else 5
    bottom_margin = min(180, 80 + n_slices * 8)
    base = {k: v for k, v in _chart_layout().items() if k != "margin"}
    hover_bg = plotly_hover_bg(th)
    fig.update_layout(
        **base,
        height=height,
        title=dict(text=title, x=0.5, xanchor="center", y=0.98, font=dict(size=16, color=th.chart_title)),
        margin=dict(l=24, r=24, t=56, b=bottom_margin),
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="top",
            y=-0.08 - (n_slices // 8) * 0.06,
            xanchor="center",
            x=0.5,
            font=dict(size=12, color=th.chart_font),
            bgcolor=f"rgba(0,0,0,0)" if th.id in ("dark", "midnight") else "rgba(255,255,255,0)",
        ),
    )
    apply_chart_theme(fig, th)
    if fig.data:
        fig.update_traces(
            textposition="inside",
            textinfo="percent",
            textfont=dict(color="#ffffff", size=12),
            pull=[0.02] * n_slices,
            hoverlabel=dict(bgcolor=hover_bg, font=dict(color=plotly_hover_font(th))),
        )
    return fig


def _is_country_preagg(df: pd.DataFrame) -> bool:
    cols = set(df.columns)
    return "country_code" in cols and "requests" in cols and (
        "visitors" in cols or "unique_ips" in cols
    ) and "remote_addr" not in cols


def _country_df(df: pd.DataFrame, metric: str = "requests") -> pd.DataFrame:
    if _is_country_preagg(df):
        g = df.copy()
        if "visitors" not in g.columns:
            g["visitors"] = g["unique_ips"]
        g = g[g["country_code"].notna() & (g["country_code"] != "INT")]
        if g.empty:
            return g
        sort_col = "requests" if metric == "requests" else "visitors"
        g = g.sort_values(sort_col, ascending=False)
        total_req = g["requests"].sum()
        total_vis = g["visitors"].sum()
        g["share_requests_pct"] = (g["requests"] / total_req * 100).round(1) if total_req else 0
        g["share_visitors_pct"] = (g["visitors"] / total_vis * 100).round(1) if total_vis else 0
        g["value"] = g["requests"] if metric == "requests" else g["visitors"]
        g["share_pct"] = g["share_requests_pct"] if metric == "requests" else g["share_visitors_pct"]
        g["label"] = g.apply(
            lambda r: f"{r['country_name']} ({r['country_code']})" if r.get("country_name") else r["country_code"],
            axis=1,
        )
        return g

    base = df[df["country_code"].notna() & (df["country_code"] != "INT")].copy()
    if base.empty:
        return base
    g = (
        base.groupby("country_code", dropna=True)
        .agg(
            country_name=("country_name", lambda s: next((x for x in s if x), None)),
            requests=("remote_addr", "count"),
            visitors=("remote_addr", "nunique"),
        )
        .reset_index()
    )
    if g.empty:
        return g
    sort_col = "requests" if metric == "requests" else "visitors"
    g = g.sort_values(sort_col, ascending=False)
    total_req = g["requests"].sum()
    total_vis = g["visitors"].sum()
    g["share_requests_pct"] = (g["requests"] / total_req * 100).round(1) if total_req else 0
    g["share_visitors_pct"] = (g["visitors"] / total_vis * 100).round(1) if total_vis else 0
    g["value"] = g["requests"] if metric == "requests" else g["visitors"]
    g["share_pct"] = g["share_requests_pct"] if metric == "requests" else g["share_visitors_pct"]
    g["label"] = g.apply(
        lambda r: f"{r['country_name']} ({r['country_code']})" if r["country_name"] else r["country_code"],
        axis=1,
    )
    return g


def _ct(key: str, locale: str, **kwargs) -> str:
    return t(f"charts.{key}", locale, **kwargs)


def _metric_label(metric: str, locale: str = "en") -> str:
    return _ct("metric_requests", locale) if metric == "requests" else _ct("metric_visitors", locale)


def _weekday_labels(locale: str) -> list[str]:
    return [
        _ct("dow_mon", locale),
        _ct("dow_tue", locale),
        _ct("dow_wed", locale),
        _ct("dow_thu", locale),
        _ct("dow_fri", locale),
        _ct("dow_sat", locale),
        _ct("dow_sun", locale),
    ]


def _earth_sphere(res_u: int = 72, res_v: int = 36) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    u = np.linspace(0, 2 * np.pi, res_u)
    v = np.linspace(0, np.pi, res_v)
    uu, vv = np.meshgrid(u, v)
    x = np.cos(uu) * np.sin(vv)
    y = np.sin(uu) * np.sin(vv)
    z = np.cos(vv)
    return x, y, z


def _apply_globe(fig: go.Figure, *, title: str, height: int = 620) -> go.Figure:
    th = get_active_theme()
    fig.update_layout(
        template=skopos_plotly_template(th),
        paper_bgcolor=th.globe_paper_bg,
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, system-ui, sans-serif", size=13, color=th.globe_title),
        margin=dict(l=0, r=0, t=56, b=0),
        height=height,
        title=dict(text=title, x=0.5, xanchor="center", font=dict(size=17, color=th.globe_title)),
        hoverlabel=dict(
            bgcolor=plotly_hover_bg(th),
            bordercolor=th.accent,
            font=dict(size=13, family="Inter, system-ui, sans-serif", color=plotly_hover_font(th)),
        ),
        scene=dict(
            bgcolor=th.globe_scene_bg,
            xaxis=dict(visible=False),
            yaxis=dict(visible=False),
            zaxis=dict(visible=False),
            aspectmode="data",
            camera=dict(eye=dict(x=1.75, y=1.55, z=0.9)),
            dragmode="orbit",
        ),
        showlegend=False,
    )
    return fig


def _apply_geo(fig: go.Figure, *, title: str, height: int = 620) -> go.Figure:
    th = get_active_theme()
    dark = th.id not in ("light", "premium", "slate")
    fig.update_geos(
        showframe=False,
        showcoastlines=True,
        coastlinecolor="rgba(255,255,255,0.35)" if dark else "rgba(55,65,81,0.55)",
        showland=True,
        landcolor="#1a2332" if dark else "#f3f4f6",
        showocean=True,
        oceancolor=th.globe_scene_bg if dark else "#dbeafe",
        bgcolor=th.globe_paper_bg,
        projection_type="natural earth",
        lataxis_range=[-60, 85],
    )
    fig.update_layout(
        template=skopos_plotly_template(th),
        paper_bgcolor=th.globe_paper_bg,
        font=dict(family="Inter, system-ui, sans-serif", size=13, color=th.globe_title),
        margin=dict(l=0, r=0, t=56, b=0),
        height=height,
        title=dict(text=title, x=0.5, xanchor="center", font=dict(size=17, color=th.globe_title)),
        hoverlabel=dict(
            bgcolor=plotly_hover_bg(th),
            bordercolor=th.accent,
            font=dict(size=13, family="Inter, system-ui, sans-serif", color=plotly_hover_font(th)),
        ),
        coloraxis_colorbar=dict(
            title=dict(text="", font=dict(color=th.chart_font)),
            tickfont=dict(color=th.chart_font),
            len=0.75,
        ),
    )
    return fig


def chart_countries_map_2d(df: pd.DataFrame, metric: str = "requests", *, locale: str = "en") -> go.Figure:
    """Flat world choropleth — default geography view."""
    g = _country_df(df, metric=metric)
    if g.empty:
        fig = go.Figure()
        fig.add_annotation(text=_ct("no_country_data", locale), showarrow=False, font=dict(size=16))
        return _apply(fig, 480)

    g = g.copy()
    g["iso_alpha"] = g["country_code"].map(alpha2_to_alpha3)
    g = g[g["iso_alpha"].notna()]
    if g.empty:
        fig = go.Figure()
        fig.add_annotation(text=_ct("no_geo_coords", locale), showarrow=False, font=dict(size=16))
        return _apply(fig, 480)

    color_col = "requests" if metric == "requests" else "visitors"
    scale = (
        ["#1a237e", "#4285F4", "#82b1ff", "#e3f2fd"]
        if metric == "requests"
        else ["#1b5e20", "#34A853", "#81c784", "#e8f5e9"]
    )

    fig = px.choropleth(
        g,
        locations="iso_alpha",
        locationmode="ISO-3",
        color=color_col,
        hover_name="label",
        custom_data=["requests", "visitors", "share_pct"],
        color_continuous_scale=scale,
        labels={
            color_col: _metric_label(metric, locale),
            "requests": _ct("hover_requests", locale),
            "visitors": _ct("hover_unique_ip", locale),
            "share_pct": _ct("hover_share", locale),
        },
    )
    fig.update_traces(
        hovertemplate=(
            "<b>%{hovertext}</b><br>"
            f"{_metric_label(metric, locale)}: %{{z:,.0f}}<br>"
            f"{_ct('hover_requests', locale)}: %{{customdata[0]:,.0f}}<br>"
            f"{_ct('hover_unique_ip', locale)}: %{{customdata[1]:,.0f}}<br>"
            f"{_ct('hover_share', locale)}: %{{customdata[2]}}%<extra></extra>"
        )
    )
    title = _ct("map_2d_title", locale, metric=_metric_label(metric, locale).lower())
    return _apply_geo(fig, title=title)


def chart_countries_map(df: pd.DataFrame, metric: str = "requests", *, locale: str = "en") -> go.Figure:
    """Interactive 3D globe with visit pillars per country."""
    g = _country_df(df, metric=metric)
    if g.empty:
        fig = go.Figure()
        fig.add_annotation(text=_ct("no_country_data", locale), showarrow=False, font=dict(size=16))
        return _apply(fig, 480)

    color_col = "requests" if metric == "requests" else "visitors"
    scale = ["#1a237e", "#4285F4", "#82b1ff", "#e3f2fd"] if metric == "requests" else ["#1b5e20", "#34A853", "#81c784", "#e8f5e9"]

    g = g.copy()
    g["lat"] = g["country_code"].map(lambda c: (alpha2_to_centroid(c) or (None, None))[0])
    g["lon"] = g["country_code"].map(lambda c: (alpha2_to_centroid(c) or (None, None))[1])
    g = g[g["lat"].notna() & g["lon"].notna()]
    if g.empty:
        fig = go.Figure()
        fig.add_annotation(text=_ct("no_geo_coords", locale), showarrow=False, font=dict(size=16))
        return _apply(fig, 480)

    max_val = max(float(g[color_col].max()), 1.0)
    fig = go.Figure()

    # Textured Earth (Blue Marble + country borders)
    earth = build_textured_earth_mesh()
    fig.add_trace(
        go.Mesh3d(
            **earth,
            hoverinfo="skip",
            showscale=False,
            lighting=dict(ambient=0.62, diffuse=0.88, specular=0.18, roughness=0.85),
        )
    )
    bx, by, bz = build_country_border_lines()
    if bx:
        fig.add_trace(
            go.Scatter3d(
                x=bx,
                y=by,
                z=bz,
                mode="lines",
                line=dict(color="rgba(255,255,255,0.42)", width=1.5),
                hoverinfo="skip",
                showlegend=False,
            )
        )

    # Subtle atmosphere glow
    ax, ay, az = _earth_sphere(48, 24)
    fig.add_trace(
        go.Surface(
            x=ax * 1.03,
            y=ay * 1.03,
            z=az * 1.03,
            colorscale=[[0, "rgba(66,133,244,0)"], [1, "rgba(66,133,244,0.12)"]],
            opacity=0.35,
            showscale=False,
            hoverinfo="skip",
        )
    )

    # Pillars + markers per country
    for row in g.itertuples():
        val = float(getattr(row, color_col))
        lat, lon = float(row.lat), float(row.lon)
        height = 0.04 + 0.42 * (val / max_val)
        x0, y0, z0 = latlon_to_xyz(lat, lon, 1.0)
        x1, y1, z1 = latlon_to_xyz(lat, lon, 1.0 + height)
        t = val / max_val
        color = scale[min(int(t * (len(scale) - 1)), len(scale) - 1)]
        width = 2 + 6 * t

        fig.add_trace(
            go.Scatter3d(
                x=[x0, x1],
                y=[y0, y1],
                z=[z0, z1],
                mode="lines",
                line=dict(color=color, width=width),
                hoverinfo="skip",
                showlegend=False,
            )
        )
        hover = (
            f"<b>{row.country_name or row.country_code}</b><br>"
            f"{_metric_label(metric, locale)}: {val:,.0f}<br>"
            f"{_ct('hover_requests', locale)}: {row.requests:,}<br>"
            f"{_ct('hover_unique_ip', locale)}: {row.visitors:,}<br>"
            f"{_ct('hover_share', locale)}: {row.share_pct}%"
        )
        fig.add_trace(
            go.Scatter3d(
                x=[x1],
                y=[y1],
                z=[z1],
                mode="markers",
                marker=dict(
                    size=5 + 18 * math.sqrt(t),
                    color=color,
                    opacity=0.95,
                    line=dict(width=1, color="rgba(255,255,255,0.6)"),
                ),
                text=[hover],
                hoverinfo="text",
                showlegend=False,
            )
        )

    title = _ct("globe_title", locale, metric=_metric_label(metric, locale).lower())
    return _apply_globe(fig, title=title)


def chart_countries_bar(df: pd.DataFrame, top_n: int = 15, metric: str = "requests", *, locale: str = "en") -> go.Figure:
    g = _country_df(df, metric=metric).head(top_n)
    if g.empty:
        return _apply(go.Figure(), 400)
    g = g.sort_values("value")
    colors = ["#aecbfa", "#4285F4"] if metric == "requests" else ["#ceead6", "#34A853"]
    fig = px.bar(
        g,
        x="value",
        y="label",
        orientation="h",
        color="value",
        color_continuous_scale=colors,
        title=_ct("top_countries", locale, n=top_n, metric=_metric_label(metric, locale).lower()),
        text="value",
    )
    fig.update_traces(textposition="outside", cliponaxis=False)
    fig.update_layout(showlegend=False, coloraxis_showscale=False)
    fig.update_xaxes(title_text=_metric_label(metric, locale))
    return _apply(fig, max(320, 28 * len(g)))


def chart_countries_donut(df: pd.DataFrame, top_n: int = 8, metric: str = "requests", *, locale: str = "en") -> go.Figure:
    g = _country_df(df, metric=metric)
    if g.empty:
        return _apply(go.Figure(), 380)
    val_col = "requests" if metric == "requests" else "visitors"
    top = g.head(top_n)
    other = g.iloc[top_n:][val_col].sum()
    labels = top["label"].tolist()
    values = top[val_col].tolist()
    if other > 0:
        labels.append(_ct("other", locale))
        values.append(other)
    unit = _ct("unit_requests", locale) if metric == "requests" else _ct("unit_visitors", locale)
    fig = go.Figure(
        data=[
            go.Pie(
                labels=labels,
                values=values,
                hole=0.55,
                marker=dict(colors=PALETTE * 3, line=dict(color="#fff", width=2)),
                hovertemplate=f"%{{label}}<br>%{{value:,}} {unit}<br>%{{percent}}<extra></extra>",
            )
        ]
    )
    return _apply_donut(fig, title=_ct("country_share", locale, metric=_metric_label(metric, locale).lower()))


def chart_countries_timeline(df: pd.DataFrame, top_n: int = 6, metric: str = "requests", *, locale: str = "en") -> go.Figure:
    if {"hour", "country", "value"}.issubset(df.columns) and "remote_addr" not in df.columns:
        agg = df.dropna(subset=["hour"]).copy()
        if agg.empty:
            return _apply(go.Figure(), 400)
        fig = px.area(
            agg,
            x="hour",
            y="value",
            color="country",
            color_discrete_sequence=PALETTE,
            title=_ct("metric_by_country_hourly", locale, metric=_metric_label(metric, locale)),
        )
        fig.update_layout(hovermode="x unified", yaxis_title=_metric_label(metric, locale))
        return _apply(fig, 420)

    tdf = df.dropna(subset=["ts_utc"]).copy()
    if tdf.empty:
        return _apply(go.Figure(), 400)
    top_codes = _country_df(df, metric=metric).head(top_n)["country_code"].tolist()
    tdf = tdf[tdf["country_code"].isin(top_codes)]
    if tdf.empty:
        return _apply(go.Figure(), 400)
    tdf["hour"] = tdf["ts_utc"].dt.floor("h")
    tdf["country"] = tdf["country_name"].fillna(tdf["country_code"])
    if metric == "requests":
        agg = tdf.groupby(["hour", "country"]).size().reset_index(name="value")
    else:
        agg = (
            tdf.groupby(["hour", "country"])["remote_addr"]
            .nunique()
            .reset_index(name="value")
        )
    fig = px.area(
        agg,
        x="hour",
        y="value",
        color="country",
        color_discrete_sequence=PALETTE,
        title=_ct("metric_by_country_hourly", locale, metric=_metric_label(metric, locale)),
    )
    fig.update_layout(hovermode="x unified", yaxis_title=_metric_label(metric, locale))
    return _apply(fig, 420)


def chart_traffic_timeline(df: pd.DataFrame, granularity: str = "hour", *, locale: str = "en") -> go.Figure:
    if {"bucket", "requests", "visitors"}.issubset(df.columns) and "remote_addr" not in df.columns:
        agg = df.dropna(subset=["bucket"]).copy()
        title = _ct("requests_by_day", locale) if granularity == "day" else _ct("requests_by_hour", locale)
    else:
        tdf = df.dropna(subset=["ts_utc"]).copy()
        if tdf.empty:
            return _apply(go.Figure(), 380)
        if granularity == "day":
            tdf["bucket"] = tdf["ts_utc"].dt.floor("D")
            title = _ct("requests_by_day", locale)
        else:
            tdf["bucket"] = tdf["ts_utc"].dt.floor("h")
            title = _ct("requests_by_hour", locale)
        agg = (
            tdf.groupby("bucket")
            .agg(requests=("remote_addr", "count"), visitors=("remote_addr", "nunique"))
            .reset_index()
        )
    if agg.empty:
        return _apply(go.Figure(), 380)
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=agg["bucket"],
            y=agg["requests"],
            mode="lines",
            fill="tozeroy",
            name=_ct("metric_requests", locale),
            line=dict(color="#4285F4", width=2.5, shape="spline"),
            fillcolor="rgba(66,133,244,0.12)",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=agg["bucket"],
            y=agg["visitors"],
            mode="lines",
            name=_ct("hover_unique_ip", locale),
            line=dict(color="#34A853", width=2.5, dash="dot", shape="spline"),
        )
    )
    fig.update_layout(title=title, hovermode="x unified")
    fig = _apply(fig, 420)
    fig.update_layout(
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.04, x=1, xanchor="right"),
    )
    return fig


def chart_top_dimension(df: pd.DataFrame, column: str, title: str, top_n: int = 12) -> go.Figure:
    if column in df.columns and "requests" in df.columns and "remote_addr" not in df.columns:
        g = (
            df[df[column].notna() & (df[column].astype(str) != "")]
            [[column, "requests"]]
            .sort_values("requests", ascending=False)
            .head(top_n)
            .sort_values("requests")
        )
    else:
        g = (
            df[df[column].notna() & (df[column].astype(str) != "")]
            .groupby(column)
            .size()
            .reset_index(name="requests")
            .sort_values("requests", ascending=False)
            .head(top_n)
            .sort_values("requests")
        )
    if g.empty:
        return _apply(go.Figure(), 360)
    fig = px.bar(
        g,
        x="requests",
        y=column,
        orientation="h",
        title=title,
        color="requests",
        color_continuous_scale=["#c8e6c9", "#34A853"],
        text="requests",
    )
    fig.update_layout(showlegend=False, coloraxis_showscale=False)
    fig.update_traces(textposition="outside", cliponaxis=False)
    return _apply(fig, max(300, 26 * len(g)))


def chart_donut_dimension(df: pd.DataFrame, column: str, title: str, top_n: int = 7, *, locale: str = "en") -> go.Figure:
    if column in df.columns and "requests" in df.columns and "remote_addr" not in df.columns:
        g = (
            df[df[column].notna() & (df[column].astype(str) != "")]
            [[column, "requests"]]
            .sort_values("requests", ascending=False)
        )
    else:
        g = (
            df[df[column].notna() & (df[column].astype(str) != "")]
            .groupby(column)
            .size()
            .reset_index(name="requests")
            .sort_values("requests", ascending=False)
        )
    if g.empty:
        return _apply(go.Figure(), 360)
    top = g.head(top_n)
    other = g.iloc[top_n:]["requests"].sum()
    labels = top[column].tolist()
    values = top["requests"].tolist()
    if other > 0:
        labels.append(_ct("other", locale))
        values.append(other)
    fig = go.Figure(
        data=[
            go.Pie(
                labels=labels,
                values=values,
                hole=0.52,
                marker=dict(colors=PALETTE * 3, line=dict(color="#fff", width=2)),
                hovertemplate="%{label}<br>%{value:,}<extra></extra>",
            )
        ]
    )
    return _apply_donut(fig, title=title, height=500)


def chart_status_codes(df: pd.DataFrame, *, locale: str = "en") -> go.Figure:
    if {"class", "requests"}.issubset(df.columns) and "status" not in df.columns:
        g = df.copy().sort_values("class")
    else:
        tmp = df.dropna(subset=["status"]).copy()
        if tmp.empty:
            return _apply(go.Figure(), 320)
        tmp["status_num"] = pd.to_numeric(tmp["status"], errors="coerce")
        tmp = tmp.dropna(subset=["status_num"])
        if tmp.empty:
            return _apply(go.Figure(), 320)
        tmp["class"] = tmp["status_num"].astype(int).floordiv(100).astype(str) + "xx"
        g = tmp.groupby("class").size().reset_index(name="requests").sort_values("class")
    if g.empty:
        return _apply(go.Figure(), 320)
    colors = {"2xx": "#34A853", "3xx": "#4285F4", "4xx": "#FBBC04", "5xx": "#EA4335"}
    fig = px.bar(
        g,
        x="class",
        y="requests",
        title=_ct("http_status", locale),
        color="class",
        color_discrete_map=colors,
        text="requests",
    )
    fig.update_layout(showlegend=False)
    return _apply(fig, 320)


def chart_heatmap_hourly(df: pd.DataFrame, *, locale: str = "en") -> go.Figure:
    dow_labels = _weekday_labels(locale)
    if {"dow", "hour", "requests"}.issubset(df.columns) and "ts_utc" not in df.columns:
        tdf = df.copy()
        tdf["dow"] = pd.to_numeric(tdf["dow"], errors="coerce")
        tdf["hour"] = pd.to_numeric(tdf["hour"], errors="coerce")
        tdf = tdf.dropna(subset=["dow", "hour"])
        if tdf.empty:
            return _apply(go.Figure(), 380)
        # SQL uses ISO dow 1=Mon … 7=Sun
        tdf["dow_label"] = tdf["dow"].astype(int).clip(1, 7).map(lambda d: dow_labels[d - 1])
        pivot = (
            tdf.groupby(["dow_label", "hour"])["requests"]
            .sum()
            .unstack(fill_value=0)
            .reindex(dow_labels, fill_value=0)
        )
        pivot = pivot.reindex(columns=list(range(24)), fill_value=0)
    else:
        tdf = df.dropna(subset=["ts_utc"]).copy()
        if tdf.empty:
            return _apply(go.Figure(), 380)
        tdf["dow"] = tdf["ts_utc"].dt.day_name()
        tdf["hour"] = tdf["ts_utc"].dt.hour
        order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        tdf["dow"] = pd.Categorical(tdf["dow"], categories=order, ordered=True)
        pivot = tdf.groupby(["dow", "hour"]).size().unstack(fill_value=0)
        pivot.index = [dow_labels[order.index(d)] for d in pivot.index]
    fig = px.imshow(
        pivot,
        labels=dict(
            x=_ct("heatmap_hour", locale),
            y=_ct("heatmap_dow", locale),
            color=_ct("metric_requests", locale),
        ),
        color_continuous_scale=["#f8f9fa", "#4285F4"],
        title=_ct("heatmap_title", locale),
        aspect="auto",
    )
    return _apply(fig, 360)


def chart_treemap_pages(df: pd.DataFrame, top_n: int = 40, *, locale: str = "en") -> go.Figure:
    if {"host", "path", "requests"}.issubset(df.columns) and "remote_addr" not in df.columns:
        g = df.head(top_n).copy()
        g["host"] = g["host"].fillna("unknown")
        g["path"] = g["path"].fillna("/")
    else:
        tdf = df.copy()
        tdf["host"] = tdf["host"].fillna("unknown")
        tdf["path"] = tdf["path"].fillna("/")
        g = (
            tdf.groupby(["host", "path"])
            .size()
            .reset_index(name="requests")
            .sort_values("requests", ascending=False)
            .head(top_n)
        )
    if g.empty:
        return _apply(go.Figure(), 420)
    fig = px.treemap(
        g,
        path=["host", "path"],
        values="requests",
        color="requests",
        color_continuous_scale=["#e8f0fe", "#4285F4"],
        title=_ct("treemap_title", locale),
    )
    return _apply(fig, 480)


def chart_ecosystem(df: pd.DataFrame, *, locale: str = "en") -> go.Figure:
    if {"ecosystem_segment", "requests"}.issubset(df.columns) and "remote_addr" not in df.columns:
        g = df.sort_values("requests", ascending=False)
    else:
        g = (
            df.groupby("ecosystem_segment")
            .size()
            .reset_index(name="requests")
            .sort_values("requests", ascending=False)
        )
    if g.empty:
        return _apply(go.Figure(), 360)
    fig = px.bar(
        g,
        x="ecosystem_segment",
        y="requests",
        title=_ct("ecosystem_title", locale),
        color="requests",
        color_continuous_scale=["#d1c4e9", "#9334E6"],
        text="requests",
    )
    fig.update_layout(showlegend=False, coloraxis_showscale=False)
    return _apply(fig, 360)


def chart_countries_by_category(
    df: pd.DataFrame,
    *,
    metric: str = "requests",
    locale: str = "en",
    title_key: str = "countries_by_host",
    category_col: str = "entity",
) -> go.Figure:
    g = df.copy()
    if category_col not in g.columns:
        if "host" in g.columns:
            category_col = "host"
        elif "server_name" in g.columns:
            category_col = "server_name"
        else:
            return _apply(go.Figure(), 400)
    if "value" not in g.columns:
        value_col = "requests" if metric == "requests" else "visitors"
        if value_col in g.columns:
            g["value"] = g[value_col]
        else:
            return _apply(go.Figure(), 400)
    if "country" not in g.columns:
        if "country_name" in g.columns:
            g["country"] = g["country_name"].fillna(g.get("country_code"))
        elif "country_code" in g.columns:
            g["country"] = g["country_code"]
        else:
            return _apply(go.Figure(), 400)
    g[category_col] = g[category_col].fillna("unknown")
    if g.empty or g["value"].sum() == 0:
        return _apply(go.Figure(), 400)
    fig = px.bar(
        g,
        x=category_col,
        y="value",
        color="country",
        title=_ct(title_key, locale, metric=_metric_label(metric, locale).lower()),
        color_discrete_sequence=PALETTE,
        barmode="stack",
    )
    fig.update_layout(xaxis_tickangle=-25, yaxis_title=_metric_label(metric, locale))
    return _apply(fig, 420)


def chart_countries_by_host(df: pd.DataFrame, top_countries: int = 8, metric: str = "requests", *, locale: str = "en") -> go.Figure:
    _ = top_countries
    if "entity" not in df.columns and "host" in df.columns:
        df = df.rename(columns={"host": "entity"})
    return chart_countries_by_category(
        df, metric=metric, locale=locale, title_key="countries_by_host", category_col="entity"
    )
