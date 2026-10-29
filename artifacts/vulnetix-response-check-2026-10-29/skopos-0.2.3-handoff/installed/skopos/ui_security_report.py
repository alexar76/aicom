"""Consolidated security report UI."""

from __future__ import annotations

import streamlit as st

from skopos.agent.security_report import load_security_report
from skopos.config import AppConfig
from skopos.i18n import t
from skopos.security.posture import SecurityPosture
from skopos.security.report_builder import SecurityReportBundle
from skopos.themes import get_active_theme


def _report_css(risk: str) -> str:
    th = get_active_theme()
    accent = {
        "critical": "#EA4335",
        "high": "#FF6D00",
        "medium": "#FBBC04",
        "low": "#34A853",
    }.get(risk, th.accent)
    return f"""
    <style>
    .sec-report-wrap {{ margin: 0 0 1.5rem 0; animation: fadeUp 0.5s ease-out; }}
    .sec-report-header {{
        background: {th.card_bg};
        border: 1px solid {accent}55;
        border-left: 5px solid {accent};
        border-radius: 16px;
        padding: 1.25rem 1.5rem;
        margin-bottom: 1rem;
        box-shadow: {th.card_shadow};
    }}
    .sec-report-risk {{
        display: inline-block;
        padding: 0.25rem 0.75rem;
        border-radius: 999px;
        background: {accent}22;
        color: {accent};
        font-weight: 700;
        font-size: 0.85rem;
        text-transform: uppercase;
        letter-spacing: 0.06em;
    }}
    .sec-report-body {{
        background: {th.card_bg};
        border: 1px solid {th.card_border};
        border-radius: 16px;
        padding: 1.5rem 1.75rem;
        box-shadow: {th.card_shadow};
        line-height: 1.65;
    }}
    </style>
    """


def _source_label(bundle: SecurityReportBundle, locale: str) -> str:
    if bundle.source == "ai":
        prov = bundle.provider or "AI"
        return t("report.source_ai", locale, provider=prov, model=bundle.model or "")
    if bundle.source == "rules_api_error":
        err = (bundle.error or "")[:100]
        return t("report.source_api_error", locale, error=err)
    return t("report.source_rules", locale)


def render_security_report_section(
    *,
    cfg: AppConfig,
    agent_path: str,
    agent_cfg,
    posture: SecurityPosture,
    findings_map: dict[str, list[dict]],
    snapshots: list[dict],
    knocks_summary: list[dict] | None,
    scan_history_summary: dict | None,
    locale: str,
    server_filter: str | None,
) -> None:
    """Full consolidated report tab — instant preview + AI deep-dive."""
    prov_ids = list(agent_cfg.providers.keys())
    default_idx = prov_ids.index(agent_cfg.default_provider) if agent_cfg.default_provider in prov_ids else 0

    risk = "critical" if posture.critical_count else ("high" if posture.high_count else "medium")
    if posture.fleet_score >= 75 and not posture.critical_count and not posture.high_count:
        risk = "low"

    st.markdown(_report_css(risk), unsafe_allow_html=True)

    h1, h2, h3 = st.columns([2, 1, 1])
    with h1:
        st.markdown(
            f'<div class="sec-report-header">'
            f'<span class="sec-report-risk">{t(f"report.risk_{risk}", locale)}</span> '
            f'<span style="margin-left:0.75rem;font-weight:600">'
            f'{t("security.score_label", locale)} {posture.fleet_score}/100 ({posture.grade})</span>'
            f"</div>",
            unsafe_allow_html=True,
        )
    with h2:
        prov_id = st.selectbox(
            t("security.agent_provider", locale),
            prov_ids,
            index=default_idx,
            key="report_provider",
        )
    with h3:
        gen = st.button(
            t("report.generate", locale),
            type="primary",
            use_container_width=True,
            key="report_generate_btn",
        )

    cache_key = f"sec_report_{server_filter or 'all'}_{prov_id}"
    if gen:
        with st.spinner(t("report.generating", locale, provider=prov_id)):
            bundle = load_security_report(
                cfg,
                agent_path,
                posture=posture,
                findings_map=findings_map,
                snapshots=snapshots,
                knocks_summary=knocks_summary,
                scan_history_summary=scan_history_summary,
                server_name=server_filter,
                provider_id=prov_id,
                locale=locale,
            )
            st.session_state[cache_key] = bundle
            st.session_state["sec_report_last_key"] = cache_key

    if cache_key not in st.session_state:
        with st.spinner(t("report.loading_preview", locale)):
            from skopos.security.report_builder import build_fallback_security_report

            st.session_state[cache_key] = build_fallback_security_report(
                posture=posture,
                findings_map=findings_map,
                snapshots=snapshots,
                knocks_summary=knocks_summary,
                locale=locale,
                scan_history_summary=scan_history_summary,
            )

    bundle: SecurityReportBundle = st.session_state[cache_key]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric(t("report.metric_findings", locale), sum(len(v) for v in findings_map.values()))
    c2.metric(t("security.severity_critical", locale), posture.critical_count)
    c3.metric(t("security.severity_high", locale), posture.high_count)
    c4.metric(t("report.metric_servers", locale), len(snapshots))

    st.caption(_source_label(bundle, locale))
    if bundle.error and bundle.source != "ai":
        st.warning(bundle.error)

    st.download_button(
        t("report.download", locale),
        data=bundle.markdown,
        file_name=f"security-report-{server_filter or 'fleet'}.md",
        mime="text/markdown",
        use_container_width=False,
    )

    with st.container(border=True):
        st.markdown(bundle.markdown)

    st.caption(t("report.hint", locale))
