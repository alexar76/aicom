"""First-run checklist and empty-state onboarding."""

from __future__ import annotations

import os

import streamlit as st

from skopos.i18n import safe_page_link, t


def _step_row(*, done: bool, title: str, hint: str) -> str:
    icon = "✅" if done else "⬜"
    return f"{icon} **{title}** — {hint}"


def render_analytics_onboarding(*, locale: str, has_traffic: bool, server_count: int) -> None:
    st.markdown(f"### 🚀 {t('onboarding.title', locale)}")
    st.caption(t("onboarding.analytics_intro", locale))
    steps = [
        _step_row(
            done=server_count > 0,
            title=t("onboarding.step_servers", locale),
            hint=t("onboarding.step_servers_hint", locale),
        ),
        _step_row(
            done=has_traffic,
            title=t("onboarding.step_collect", locale),
            hint=t("onboarding.step_collect_hint", locale),
        ),
        _step_row(
            done=has_traffic,
            title=t("onboarding.step_explore", locale),
            hint=t("onboarding.step_explore_hint", locale),
        ),
    ]
    st.markdown("\n\n".join(steps))
    if not has_traffic:
        st.info(t("onboarding.analytics_cta", locale))
        safe_page_link("pages/0_Quick_Start.py", label=f"🚀 {t('app.quick_start', locale)}")


def render_security_onboarding(*, locale: str, has_scan: bool, server_count: int) -> None:
    st.markdown(f"### 🚀 {t('onboarding.title', locale)}")
    st.caption(t("onboarding.security_intro", locale))
    steps = [
        _step_row(
            done=server_count > 0,
            title=t("onboarding.step_servers", locale),
            hint=t("onboarding.step_servers_hint", locale),
        ),
        _step_row(
            done=has_scan,
            title=t("onboarding.step_scan", locale),
            hint=t("onboarding.step_scan_hint", locale),
        ),
        _step_row(
            done=has_scan,
            title=t("onboarding.step_report", locale),
            hint=t("onboarding.step_report_hint", locale),
        ),
    ]
    st.markdown("\n\n".join(steps))
    if not has_scan:
        st.info(t("onboarding.security_cta", locale))
        safe_page_link("pages/0_Quick_Start.py", label=f"🚀 {t('app.quick_start', locale)}")


def render_password_warning(*, locale: str) -> None:
    try:
        from skopos.auth_store import (
            dashboard_password_configured,
            password_expired,
            password_expires_in_days,
        )
    except Exception:
        if not os.environ.get("SKOPOS_DASHBOARD_PASSWORD", "").strip():
            st.sidebar.warning(t("auth.no_password_warn", locale))
        return

    if not dashboard_password_configured():
        st.sidebar.warning(t("auth.no_password_warn", locale))
        return
    if password_expired():
        remaining = password_expires_in_days() or 0
        st.sidebar.error(t("auth.expired", locale, days=int(abs(remaining))))
