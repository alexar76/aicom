"""Analytics dashboard filters — shared between main toolbar and sidebar."""

from __future__ import annotations

from dataclasses import dataclass

import streamlit as st

from skopos.i18n import t


@dataclass(frozen=True)
class AnalyticsFilterState:
    hide_bots: bool
    hide_service: bool
    visitors_only: bool
    sel_servers: list[str]
    sel_hosts: list[str]
    sel_countries: list[str]
    path_contains: str
    hide_datacenter: bool = True


_CHECKBOX_QUERY_PARAMS = {
    "analytics_hide_bots": "fb",
    "analytics_hide_service": "fs",
    "analytics_visitors_only": "fv",
    "analytics_hide_datacenter": "fd",
}


def parse_filter_flag(value, default: bool) -> bool:
    """Parse a compact URL preference without treating arbitrary text as true."""
    if isinstance(value, (list, tuple)):
        value = value[-1] if value else None
    if value is None:
        return default
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _persisted_checkbox_default(state_key: str, default: bool) -> bool:
    param = _CHECKBOX_QUERY_PARAMS.get(state_key)
    if not param:
        return default
    try:
        return parse_filter_flag(st.query_params.get(param), default)
    except Exception:
        return default


def _persist_checkbox(state_key: str, value: bool) -> None:
    param = _CHECKBOX_QUERY_PARAMS.get(state_key)
    if not param:
        return
    encoded = "1" if value else "0"
    try:
        if str(st.query_params.get(param, "")) != encoded:
            st.query_params[param] = encoded
    except Exception:
        pass


def _seed_widget(state_key: str, widget_key: str, default):
    if state_key not in st.session_state:
        if isinstance(default, bool):
            default = _persisted_checkbox_default(state_key, default)
        st.session_state[state_key] = default
    if widget_key not in st.session_state:
        st.session_state[widget_key] = st.session_state[state_key]


def _sync_checkbox(container, *, label: str, state_key: str, widget_key: str, default: bool) -> bool:
    _seed_widget(state_key, widget_key, default)
    container.checkbox(label, key=widget_key)
    st.session_state[state_key] = bool(st.session_state[widget_key])
    _persist_checkbox(state_key, bool(st.session_state[state_key]))
    return bool(st.session_state[state_key])


def _sync_multiselect(
    container,
    *,
    label: str,
    options: list[str],
    state_key: str,
    widget_key: str,
    format_func=None,
    placeholder: str = "",
) -> list[str]:
    _seed_widget(state_key, widget_key, [])
    # Streamlit multiselect ignores `placeholder` when options=[] and shows hardcoded English.
    if not options:
        container.text_input(
            label,
            value="",
            disabled=True,
            placeholder=placeholder,
            key=f"{widget_key}_empty",
        )
        st.session_state[state_key] = []
        return []
    kwargs: dict = {
        "label": label,
        "options": options,
        "placeholder": placeholder,
        "key": widget_key,
    }
    if format_func is not None:
        kwargs["format_func"] = format_func
    container.multiselect(**kwargs)
    st.session_state[state_key] = list(st.session_state[widget_key])
    return list(st.session_state[state_key])


def _sync_text(
    container,
    *,
    label: str,
    state_key: str,
    widget_key: str,
    default: str = "",
    placeholder: str = "",
) -> str:
    _seed_widget(state_key, widget_key, default)
    container.text_input(label, key=widget_key, placeholder=placeholder)
    st.session_state[state_key] = str(st.session_state[widget_key])
    return str(st.session_state[state_key])


def render_analytics_filters(
    container,
    locale: str,
    *,
    key_suffix: str,
    server_opts: list[str],
    host_opts: list[str],
    country_opts: list[str],
    server_labels: dict[str, str],
    compact: bool = False,
) -> AnalyticsFilterState:
    """Render traffic filters; session_state is the source of truth across duplicates."""
    sfx = key_suffix
    if not compact:
        container.markdown(f"**{t('analytics.filters', locale)}**")

    if compact:
        hide_bots = _sync_checkbox(
            container,
            label=t("analytics.hide_bots", locale),
            state_key="analytics_hide_bots",
            widget_key=f"af_hide_bots{sfx}",
            default=True,
        )
        hide_service = _sync_checkbox(
            container,
            label=t("analytics.hide_service", locale),
            state_key="analytics_hide_service",
            widget_key=f"af_hide_service{sfx}",
            default=True,
        )
        visitors_only = _sync_checkbox(
            container,
            label=t("analytics.external_only", locale),
            state_key="analytics_visitors_only",
            widget_key=f"af_visitors_only{sfx}",
            default=True,
        )
        hide_datacenter = _sync_checkbox(
            container,
            label=t("analytics.hide_datacenter", locale),
            state_key="analytics_hide_datacenter",
            widget_key=f"af_hide_datacenter{sfx}",
            default=True,
        )
        col_a, col_b = container.columns(2)
        col_c = None
    else:
        c1, c2, c3, c4 = container.columns(4)
        hide_bots = _sync_checkbox(
            c1,
            label=t("analytics.hide_bots", locale),
            state_key="analytics_hide_bots",
            widget_key=f"af_hide_bots{sfx}",
            default=True,
        )
        hide_service = _sync_checkbox(
            c2,
            label=t("analytics.hide_service", locale),
            state_key="analytics_hide_service",
            widget_key=f"af_hide_service{sfx}",
            default=True,
        )
        visitors_only = _sync_checkbox(
            c3,
            label=t("analytics.external_only", locale),
            state_key="analytics_visitors_only",
            widget_key=f"af_visitors_only{sfx}",
            default=True,
        )
        hide_datacenter = _sync_checkbox(
            c4,
            label=t("analytics.hide_datacenter", locale),
            state_key="analytics_hide_datacenter",
            widget_key=f"af_hide_datacenter{sfx}",
            default=True,
        )
        col_a, col_b, col_c = container.columns(3)

    sel_servers = _sync_multiselect(
        col_a,
        label=t("analytics.servers", locale),
        options=server_opts,
        state_key="analytics_sel_servers",
        widget_key=f"af_servers{sfx}",
        format_func=lambda n: server_labels.get(n, n),
        placeholder=t("common.all_servers", locale),
    )
    sel_hosts = _sync_multiselect(
        col_b,
        label=t("analytics.addresses", locale),
        options=host_opts,
        state_key="analytics_sel_hosts",
        widget_key=f"af_hosts{sfx}",
        placeholder=t("common.all_addresses", locale),
    )
    if col_c is not None:
        sel_countries = _sync_multiselect(
            col_c,
            label=t("analytics.countries", locale),
            options=country_opts,
            state_key="analytics_sel_countries",
            widget_key=f"af_countries{sfx}",
            placeholder=t("common.all_countries", locale),
        )
    else:
        sel_countries = _sync_multiselect(
            container,
            label=t("analytics.countries", locale),
            options=country_opts,
            state_key="analytics_sel_countries",
            widget_key=f"af_countries{sfx}",
            placeholder=t("common.all_countries", locale),
        )

    path_contains = _sync_text(
        container,
        label=t("analytics.path_contains", locale),
        state_key="analytics_path_contains",
        widget_key=f"af_path{sfx}",
        default="",
        placeholder=t("analytics.path_contains_placeholder", locale),
    )

    return AnalyticsFilterState(
        hide_bots=hide_bots,
        hide_service=hide_service,
        visitors_only=visitors_only,
        sel_servers=sel_servers,
        sel_hosts=sel_hosts,
        sel_countries=sel_countries,
        path_contains=path_contains,
        hide_datacenter=hide_datacenter,
    )


def read_analytics_filters() -> AnalyticsFilterState:
    """Read canonical filter values without rendering widgets."""
    return AnalyticsFilterState(
        hide_bots=bool(st.session_state.get("analytics_hide_bots", True)),
        hide_service=bool(st.session_state.get("analytics_hide_service", True)),
        visitors_only=bool(st.session_state.get("analytics_visitors_only", True)),
        sel_servers=list(st.session_state.get("analytics_sel_servers") or []),
        sel_hosts=list(st.session_state.get("analytics_sel_hosts") or []),
        sel_countries=list(st.session_state.get("analytics_sel_countries") or []),
        path_contains=str(st.session_state.get("analytics_path_contains") or ""),
        hide_datacenter=bool(st.session_state.get("analytics_hide_datacenter", True)),
    )
