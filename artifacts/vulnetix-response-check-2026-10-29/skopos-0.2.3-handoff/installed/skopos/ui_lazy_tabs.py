"""Server-side lazy dashboard navigation.

``st.tabs`` renders every tab body during the same script run.  That is a bad
fit for data-heavy dashboards: a hidden chart can delay the visible one.  This
module renders a tab-like radio rail and returns exactly one active key, so the
page can execute only that section.
"""

from __future__ import annotations

import html
from collections.abc import Sequence

import streamlit as st

from skopos.ui_tab_deeplink import inject_tab_deeplink


def render_lazy_tabs(
    group: str,
    tabs: Sequence[tuple[str, str]],
    *,
    default: str | None = None,
) -> str:
    """Render all dashboard choices and return the one body to execute."""
    if not tabs:
        raise ValueError("at least one lazy tab is required")

    keys = [str(key) for key, _label in tabs]
    labels = {str(key): str(label) for key, label in tabs}
    if len(set(keys)) != len(keys):
        raise ValueError("lazy tab keys must be unique")

    state_key = f"_skopos_lazy_tab_{group}"
    fallback = default if default in keys else keys[0]
    selected = st.session_state.get(state_key)
    if selected not in keys:
        # URL deep links work without waiting for the client-side bridge.  The
        # bridge below additionally covers navigation initiated by the agent,
        # which stores the desired tab in sessionStorage.
        try:
            desired = str(st.query_params.get("tab", "")).strip().lower()
        except Exception:
            desired = ""
        st.session_state[state_key] = desired if desired in keys else fallback

    st.markdown(
        f'<span class="skopos-lazy-tabs-marker" data-group="{html.escape(group)}"></span>',
        unsafe_allow_html=True,
    )
    active = st.radio(
        "Dashboard",
        keys,
        format_func=lambda key: labels[key],
        horizontal=True,
        key=state_key,
        label_visibility="collapsed",
    )
    inject_tab_deeplink(keys, lazy_group=group)
    return str(active)
