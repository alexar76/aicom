"""Plotly chart styling per theme: registered templates, hover colours, layout keyword
arguments and axes.
"""

from __future__ import annotations

from .catalog import get_active_theme, is_light_theme, Theme, theme_surface_bg, THEMES


_PLOTLY_TEMPLATES_READY = False


def ensure_plotly_templates() -> None:
    """Register SKOPOS Plotly templates with readable hoverlabel for every theme.

    Stock ``plotly_white`` / ``plotly_dark`` leave hoverlabel bgcolor unset; Plotly
    then paints a near-white unified hover box. Combined with light ``chart_font`` on
    dark UIs that yields invisible tooltip text ("country=… value=…") everywhere.
    """
    global _PLOTLY_TEMPLATES_READY
    if _PLOTLY_TEMPLATES_READY:
        return
    try:
        import copy

        import plotly.io as pio
    except ImportError:
        return

    for theme in THEMES.values():
        base_name = "plotly_white" if is_light_theme(theme.id) else "plotly_dark"
        payload = copy.deepcopy(pio.templates[base_name].to_plotly_json())
        layout = payload.setdefault("layout", {})
        layout["hoverlabel"] = {
            "bgcolor": theme_surface_bg(theme),
            "bordercolor": theme.accent,
            "align": "left",
            "font": {
                "family": "Inter, system-ui, sans-serif",
                "size": 13,
                "color": _plotly_hover_font(theme),
            },
        }
        layout["font"] = {
            "family": "Inter, system-ui, sans-serif",
            "color": theme.chart_font,
        }
        layout["paper_bgcolor"] = theme.chart_paper_bg
        layout["plot_bgcolor"] = theme.chart_plot_bg
        pio.templates[f"skopos_{theme.id}"] = payload

    _PLOTLY_TEMPLATES_READY = True


def skopos_plotly_template(theme: Theme) -> str:
    """Return the registered template name for ``theme`` (registers on first use)."""
    ensure_plotly_templates()
    return f"skopos_{theme.id}"


def plotly_hover_bg(theme: Theme) -> str:
    """Plotly hoverlabel.bgcolor must be a solid color, not CSS gradients."""
    return _plotly_hover_bg(theme)


def plotly_hover_font(theme: Theme) -> str:
    """High-contrast hover text — paired with :func:`plotly_hover_bg`."""
    return _plotly_hover_font(theme)


def _plotly_hover_bg(theme: Theme) -> str:
    """Solid hover box for every theme (never fall back to white on dark UIs)."""
    # Reuse the same solid surfaces as contrast checks so ocean/aurora/etc. are covered.
    return theme_surface_bg(theme)


def _plotly_hover_font(theme: Theme) -> str:
    """Readable text on the hover box (light text on dark surfaces, vice versa)."""
    if is_light_theme(theme.id):
        return "#1a1a1a"
    return "#f4f7fb"


def chart_layout_kwargs(theme: Theme | None = None) -> dict:
    th = theme or get_active_theme()
    hover_bg = _plotly_hover_bg(th)
    hover_font = _plotly_hover_font(th)
    return dict(
        template=skopos_plotly_template(th),
        paper_bgcolor=th.chart_paper_bg,
        plot_bgcolor=th.chart_plot_bg,
        font=dict(family="Inter, system-ui, sans-serif", size=14, color=th.chart_font),
        margin=dict(l=32, r=32, t=64, b=48),
        hoverlabel=dict(
            bgcolor=hover_bg,
            bordercolor=th.accent,
            font=dict(size=13, family="Inter, system-ui, sans-serif", color=hover_font),
        ),
        transition=dict(duration=600, easing="cubic-in-out"),
    )


def apply_chart_theme(fig, theme: Theme | None = None):
    """Force readable Plotly text — axes, legend, titles, trace labels."""
    th = theme or get_active_theme()
    color = th.chart_font
    grid = th.chart_grid
    axis_kw = dict(
        automargin=True,
        title_standoff=14,
        tickfont=dict(color=color, size=12),
        title=dict(font=dict(color=color, size=13)),
        linecolor=grid,
        tickcolor=color,
        gridcolor=grid,
        zerolinecolor=grid,
    )
    fig.update_xaxes(**axis_kw)
    fig.update_yaxes(**axis_kw)
    fig.update_coloraxes(
        colorbar=dict(
            tickfont=dict(color=color, size=12),
            title=dict(font=dict(color=color, size=13)),
            outlinecolor=grid,
        )
    )
    fig.update_layout(
        font=dict(family="Inter, system-ui, sans-serif", size=14, color=color),
        legend=dict(
            font=dict(color=color, size=12),
            title=dict(font=dict(color=color, size=12)),
        ),
        hoverlabel=dict(
            bgcolor=_plotly_hover_bg(th),
            bordercolor=th.accent,
            font=dict(size=13, family="Inter, system-ui, sans-serif", color=_plotly_hover_font(th)),
        ),
    )
    fig.update_traces(
        textfont=dict(color=color, size=12),
        selector=dict(type="bar"),
    )
    fig.update_traces(
        textfont=dict(color=color, size=12),
        selector=dict(type="pie"),
    )
    fig.update_traces(
        outsidetextfont=dict(color=color, size=12),
        insidetextfont=dict(color=color, size=11),
        selector=dict(type="pie"),
    )
    fig.update_traces(
        textfont=dict(color=color, size=12),
        selector=dict(type="scatter"),
    )
    if fig.layout.scene:
        scene_font = dict(tickfont=dict(color=color, size=11), title=dict(font=dict(color=color, size=12)))
        fig.update_layout(scene=dict(xaxis=scene_font, yaxis=scene_font, zaxis=scene_font))
    return fig


# Backwards-compatible alias
apply_chart_axes = apply_chart_theme
