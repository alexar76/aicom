"""Premium dashboard styling and chart wrappers."""

from __future__ import annotations

import html as html_lib
import time
from contextlib import contextmanager
from collections.abc import Iterator

import plotly.graph_objects as go
import pandas as pd
import streamlit as st

from skopos.charts import prevent_label_overlap
from skopos.themes import apply_chart_theme, get_active_theme

PLOTLY_CONFIG = {
    "displayModeBar": False,
    "staticPlot": False,
    "responsive": True,
}


def inject_css(theme=None) -> None:
    from skopos.themes import build_app_css

    th = theme or get_active_theme()
    st.markdown(build_app_css(th), unsafe_allow_html=True)


@contextmanager
def page_loading(message: str) -> Iterator[None]:
    """In-page spinner for long DB work.

    SKOPOS hides Streamlit's header (where the native Running pill lives), and
    ``@st.cache_data(show_spinner=False)`` suppresses the function-name toast —
    so first analytics paint used to sit on an empty chart well with no cue.
    """
    slot = st.empty()
    text = html_lib.escape(message)
    slot.markdown(
        f'<div class="skopos-page-loading" role="status" aria-live="polite">'
        f'<span class="skopos-page-loading-wheel" aria-hidden="true"></span>'
        f"<span>{text}</span></div>",
        unsafe_allow_html=True,
    )
    try:
        yield
    finally:
        slot.empty()


class SectionLoadProgress:
    """Small, local progress indicator for one dashboard's data dependencies."""

    def __init__(self, message: str, total: int, *, complete_message: str):
        self.message = message
        self.total = max(int(total), 1)
        self.complete_message = complete_message
        self.current = 0
        self.started = time.monotonic()
        self.status = st.empty()
        self.status.markdown(
            f'<div class="skopos-page-loading skopos-section-loading" role="status" '
            f'aria-live="polite"><span class="skopos-page-loading-wheel" '
            f'aria-hidden="true"></span><span>{html_lib.escape(message)}</span></div>',
            unsafe_allow_html=True,
        )
        self.widget = st.progress(0.0, text=f"{message} · 0/{self.total}")

    def advance(self, detail: str | None = None) -> None:
        self.current = min(self.current + 1, self.total)
        text = f"{self.message} · {self.current}/{self.total}"
        if detail:
            text += f" · {detail}"
        self.widget.progress(self.current / self.total, text=text)

    def close(self, *, failed: bool = False) -> None:
        elapsed = time.monotonic() - self.started
        if failed:
            return
        self.widget.progress(1.0, text=f"{self.complete_message} · {self.total}/{self.total}")
        self.widget.empty()
        self.status.empty()
        # Fast cache hits should feel instant, not noisy. A real refresh gets a
        # completion notification after the local bar has kept the user informed.
        if elapsed >= 0.8:
            st.toast(self.complete_message, icon="✅")


@contextmanager
def section_loading(
    message: str,
    total: int,
    *,
    complete_message: str,
    slot=None,
) -> Iterator[SectionLoadProgress]:
    """Show determinate progress while cached/fresh section data is resolved."""
    if slot is None:
        progress = SectionLoadProgress(message, total, complete_message=complete_message)
    else:
        # The placeholder is emitted beside the selected dashboard header.  Its
        # contents can then update while the already-rendered cached cards stay
        # exactly where they are.
        with slot.container():
            progress = SectionLoadProgress(message, total, complete_message=complete_message)
    try:
        yield progress
    except Exception:
        progress.close(failed=True)
        raise
    else:
        progress.close()


def inject_shell_css(theme=None) -> None:
    from skopos.themes import build_critical_shell_css

    th = theme or get_active_theme()
    st.markdown(build_critical_shell_css(th), unsafe_allow_html=True)


def inject_all_theme_css(theme=None) -> None:
    """Inject full theme bundle as early as possible (before widgets) to avoid flash."""
    from skopos.agent_portal import inject_agent_portal
    from skopos.nav_chrome import build_nav_chrome_js
    from skopos.premium_chrome import build_premium_chrome_css, build_premium_tooltip_js
    from skopos.ui_topbar import build_topbar_css, inject_topbar_js
    from skopos.themes import (
        build_app_css,
        build_critical_shell_css,
        build_portal_overlay_css,
        build_security_css,
        build_sidebar_layout_css,
        build_widget_css,
    )
    th = theme or get_active_theme()
    st.markdown(
        build_critical_shell_css(th, collapsed=False)
        + build_app_css(th)
        + build_portal_overlay_css(th)
        + build_widget_css(th)
        + build_sidebar_layout_css(th, collapsed=False)
        + build_security_css(th)
        + build_premium_chrome_css(th)
        + build_topbar_css(th)
        + build_premium_tooltip_js()
        + build_nav_chrome_js(),
        unsafe_allow_html=True,
    )
    inject_agent_portal()
    inject_topbar_js()


def hero(title: str, subtitle: str) -> None:
    import html

    from skopos.i18n import active_locale, t

    th = get_active_theme()
    loc = active_locale()
    st.markdown(
        f'<div class="theme-badge">{html.escape(t(th.label_key, loc))}</div>',
        unsafe_allow_html=True,
    )
    st.markdown(f'<div class="hero-title">{title}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="hero-sub">{subtitle}</div>', unsafe_allow_html=True)


def section_head(text: str) -> None:
    st.markdown(f'<div class="section-head">{text}</div>', unsafe_allow_html=True)


def prepare_display_df(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize a dataframe for st.dataframe / PyArrow (unique headers, display-safe cells)."""
    out = df.copy()
    seen: dict[str, int] = {}
    new_cols: list[str] = []
    for col in out.columns:
        name = str(col)
        if name in seen:
            seen[name] += 1
            name = f"{name} ({seen[name]})"
        else:
            seen[name] = 1
        new_cols.append(name)
    out.columns = new_cols
    for col in out.columns:
        if pd.api.types.is_float_dtype(out[col]):
            non_null = out[col].dropna()
            if non_null.empty or (non_null % 1 == 0).all():
                out[col] = out[col].astype("Int64")
        elif out[col].dtype == object:
            out[col] = out[col].map(_display_cell)
    return out


def _display_cell(value) -> str:
    try:
        if value is None or pd.isna(value):
            return "—"
    except (TypeError, ValueError):
        if value is None:
            return "—"
    return str(value)


def display_dataframe(df: pd.DataFrame, **kwargs) -> None:
    try:
        st.dataframe(prepare_display_df(df), **kwargs)
    except (ValueError, TypeError):
        st.dataframe(prepare_display_df(df.astype(str)), **kwargs)


def display_labeled_df(
    df: pd.DataFrame,
    columns: list[tuple[str, str, str]],
    ctx,
    **kwargs,
) -> None:
    """Render a table with stable internal column keys and translated headers."""
    from skopos.app_shell import T

    subset = df[[name for name, _key, _kind in columns]].copy()
    col_config: dict[str, st.column_config.Column] = {}
    for name, key, kind in columns:
        label = T(ctx, key)
        if kind == "number":
            col_config[name] = st.column_config.NumberColumn(label, format="%d")
            if pd.api.types.is_float_dtype(subset[name]):
                subset[name] = subset[name].astype("Int64")
        elif kind == "datetime":
            col_config[name] = st.column_config.TextColumn(label)
            subset[name] = subset[name].map(_display_cell)
        else:
            col_config[name] = st.column_config.TextColumn(label)
            if subset[name].dtype == object:
                subset[name] = subset[name].map(_display_cell)
    try:
        st.dataframe(subset, column_config=col_config, **kwargs)
    except (ValueError, TypeError):
        labeled = subset.rename(columns={name: T(ctx, key) for name, key, _kind in columns})
        display_dataframe(labeled, **kwargs)


def plot(fig: go.Figure, *, key: str | None = None, height: int | None = None) -> None:
    """Render plotly chart with premium config and smooth transitions."""
    th = get_active_theme()
    meta = fig.layout.meta if fig.layout.meta else {}
    chart_kind = meta.get("stats_chart") if isinstance(meta, dict) else getattr(meta, "stats_chart", None)
    if chart_kind != "threat_universe":
        apply_chart_theme(fig, th)
        prevent_label_overlap(fig)
    if height is not None:
        fig.update_layout(height=height)
    # Fold analytics period into uirevision so Plotly does not reuse traces
    # when the user switches 24h ↔ 7d (a fixed revision made charts look stuck).
    period_rev = ""
    try:
        from skopos.period_picker import SESSION_CUSTOM_KEY, SESSION_PRESET_KEY

        period_rev = (
            f"{st.session_state.get(SESSION_PRESET_KEY, '')}-"
            f"{int(bool(st.session_state.get(SESSION_CUSTOM_KEY)))}"
        )
    except Exception:
        period_rev = ""
    fig.update_layout(uirevision=f"stats-{th.id}-{key or 'chart'}-{period_rev}")
    # theme=None — do not let Streamlit override our colors with faded UI tokens
    st.plotly_chart(
        fig,
        use_container_width=True,
        config=PLOTLY_CONFIG,
        key=key,
        theme=None,
    )


FULLSCREEN_STATE_PREFIX = "stats_fs_"


def _fullscreen_state_key(chart_key: str) -> str:
    return f"{FULLSCREEN_STATE_PREFIX}{chart_key}"


def clear_fullscreen_state(session=None) -> None:
    """Drop chart fullscreen flags on full page runs (browser refresh, navigation).

    Fragment-only reruns (expand/collapse button) do not call prime_theme(), so
    toggled fullscreen survives until the user refreshes or leaves the page.
    """
    store = session if session is not None else st.session_state
    for key in list(store.keys()):
        if str(key).startswith(FULLSCREEN_STATE_PREFIX):
            store.pop(key, None)


def _toggle_fullscreen(chart_key: str) -> None:
    fs_key = _fullscreen_state_key(chart_key)
    st.session_state[fs_key] = not bool(st.session_state.get(fs_key, False))


@st.fragment
def plot_fullscreen(
    fig: go.Figure,
    *,
    key: str,
    locale: str = "en",
    caption: str | None = None,
    expanded_height: int = 920,
) -> None:
    """Render a 3D map/globe with expand-to-fullscreen and collapse back."""
    from skopos.i18n import t
    from skopos.themes import build_fullscreen_chart_css

    fs_key = _fullscreen_state_key(key)
    expanded = bool(st.session_state.get(fs_key, False))

    if expanded:
        st.markdown('<div class="skopos-fs-marker" aria-hidden="true"></div>', unsafe_allow_html=True)
        st.markdown(build_fullscreen_chart_css(get_active_theme()), unsafe_allow_html=True)

    bar_left, bar_right = st.columns([5, 1])
    with bar_left:
        if caption and not expanded:
            st.caption(caption)
    with bar_right:
        label = t("common.collapse_map", locale) if expanded else t("common.expand_map", locale)
        icon = "✕" if expanded else "⛶"
        st.button(
            f"{icon} {label}",
            key=f"fs_btn_{key}",
            use_container_width=True,
            on_click=_toggle_fullscreen,
            args=(key,),
        )

    if expanded:
        th = get_active_theme()
        fig_fs = go.Figure(fig)
        fig_fs.update_layout(
            height=expanded_height,
            margin=dict(l=0, r=0, t=36, b=0),
            paper_bgcolor=th.globe_paper_bg,
        )
        if fig_fs.layout.scene is not None:
            fig_fs.update_layout(scene=dict(bgcolor=th.globe_scene_bg))
        plot(fig_fs, key=f"{key}__expanded", height=expanded_height)
    else:
        plot(fig, key=key)


def metric_row(metrics: list[tuple[str, str]], delays: list[int] | None = None) -> None:
    cols = st.columns(len(metrics))
    for i, (label, value) in enumerate(metrics):
        delay = (delays or [0] * len(metrics))[i]
        with cols[i]:
            st.markdown(
                f'<div style="animation-delay:{delay}ms"></div>',
                unsafe_allow_html=True,
            )
            st.metric(label, value)
