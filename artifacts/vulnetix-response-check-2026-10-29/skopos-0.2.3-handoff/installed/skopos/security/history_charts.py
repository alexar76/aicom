"""Charts for scan history dashboard."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from skopos.charts import PALETTE, _apply, chart_layout, prevent_label_overlap
from skopos.security.charts import SEVERITY_COLORS
from skopos.security.posture import score_to_grade
from skopos.themes import apply_chart_theme, get_active_theme


def chart_score_timeline(points: list[dict], *, title: str = "Security score over time") -> go.Figure:
    if not points:
        fig = go.Figure()
        fig.update_layout(title=title, height=360)
        return fig
    df = pd.DataFrame(points)
    df["scanned_at_utc"] = pd.to_datetime(df["scanned_at_utc"], utc=True, errors="coerce")
    df["grade"] = df["score"].apply(score_to_grade)
    fig = px.line(
        df,
        x="scanned_at_utc",
        y="score",
        color="server_name",
        markers=True,
        title=title,
        color_discrete_sequence=PALETTE,
        hover_data=["findings_total", "critical", "high", "grade"],
    )
    fig.add_hline(y=75, line_dash="dot", line_color="rgba(52,168,83,0.5)", annotation_text="B")
    fig.add_hline(y=60, line_dash="dot", line_color="rgba(251,188,4,0.5)", annotation_text="C")
    fig.update_layout(**chart_layout(), yaxis_range=[0, 100], height=400, showlegend=True)
    apply_chart_theme(fig, get_active_theme())
    return fig


def chart_findings_trend(trend_rows: list[dict], *, title: str = "Findings trend") -> go.Figure:
    if not trend_rows:
        fig = go.Figure()
        fig.update_layout(title=title, height=360)
        return fig
    df = pd.DataFrame(trend_rows)
    order = ["critical", "high", "medium", "low", "info"]
    df["severity"] = pd.Categorical(df["severity"], categories=order, ordered=True)
    fig = px.bar(
        df,
        x="scan_day",
        y="cnt",
        color="severity",
        title=title,
        color_discrete_map=SEVERITY_COLORS,
        barmode="stack",
    )
    fig.update_layout(**chart_layout(), height=380, xaxis_title="Day", yaxis_title="Findings")
    apply_chart_theme(fig, get_active_theme())
    return fig


def chart_scan_calendar(history: list[dict], *, title: str = "Scan activity") -> go.Figure:
    if not history:
        fig = go.Figure()
        fig.update_layout(title=title, height=280)
        return fig
    df = pd.DataFrame(history)
    df["day"] = pd.to_datetime(df["scanned_at_utc"], utc=True, errors="coerce").dt.date.astype(str)
    daily = df.groupby(["day", "server_name"]).size().reset_index(name="scans")
    fig = px.density_heatmap(
        daily,
        x="day",
        y="server_name",
        z="scans",
        title=title,
        color_continuous_scale=["#0d1117", PALETTE[0], PALETTE[3], "#EA4335"],
    )
    fig.update_layout(**chart_layout(), height=320)
    apply_chart_theme(fig, get_active_theme())
    return fig


def chart_fleet_radar(latest_scores: dict[str, int], *, title: str = "Fleet posture") -> go.Figure:
    if not latest_scores:
        fig = go.Figure()
        fig.update_layout(title=title, height=360)
        return fig
    names = list(latest_scores.keys())
    values = [latest_scores[n] for n in names]
    values_closed = values + [values[0]]
    names_closed = names + [names[0]]
    fig = go.Figure(
        data=go.Scatterpolar(
            r=values_closed,
            theta=names_closed,
            fill="toself",
            fillcolor="rgba(66,133,244,0.25)",
            line=dict(color=PALETTE[0], width=2),
            name="Score",
        )
    )
    fig.update_layout(
        **chart_layout(),
        polar=dict(radialaxis=dict(range=[0, 100], showgrid=True)),
        title=title,
        height=380,
        showlegend=False,
    )
    apply_chart_theme(fig, get_active_theme())
    return fig


def chart_diff_summary(diff: dict, *, title: str = "Scan comparison") -> go.Figure:
    new_n = len(diff.get("new_issues") or [])
    resolved_n = len(diff.get("resolved") or [])
    unchanged = int(diff.get("unchanged_count") or 0)
    fig = go.Figure(
        data=[
            go.Bar(
                x=["New issues", "Resolved", "Unchanged"],
                y=[new_n, resolved_n, unchanged],
                marker_color=[SEVERITY_COLORS["critical"], SEVERITY_COLORS["info"], PALETTE[1]],
                text=[new_n, resolved_n, unchanged],
                textposition="outside",
            )
        ]
    )
    fig.update_layout(**chart_layout(), title=title, height=320, yaxis_title="Findings")
    prevent_label_overlap(fig)
    apply_chart_theme(fig, get_active_theme())
    return fig
