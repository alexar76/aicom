"""Prominent AI ecosystem health briefing card."""

from __future__ import annotations

import hashlib
import os

import streamlit as st

from skopos.agent.config import load_agent_config
from skopos.agent.ecosystem_briefing import (
    EcosystemBriefing,
    TrafficSnapshot,
    fallback_ecosystem_briefing,
    load_briefing,
    mood_color,
    traffic_snapshot_from_df,
)
from skopos.config import load_config, load_app_env
from skopos.i18n import t
from skopos.period_picker import PeriodRange
from skopos.security.posture import SecurityPosture


def _briefing_cache_signature(agent_path: str) -> str:
    load_app_env()
    agent_cfg = load_agent_config(agent_path)
    prov = agent_cfg.providers.get(agent_cfg.default_provider)
    env_name = prov.api_key_env if prov else ""
    key = os.environ.get(env_name or "", "")
    fp = hashlib.sha256(key.encode()).hexdigest()[:10] if key else "none"
    return f"{agent_cfg.default_provider}:{fp}"


def _traffic_cache_key(traffic: TrafficSnapshot | None) -> str:
    if traffic is None:
        return "none"
    seg = traffic.top_segment or "-"
    return (
        f"{traffic.requests}|{traffic.unique_ips}|{seg}|"
        f"{traffic.top_segment_share_pct}|{traffic.error_rate_pct}|{traffic.active_hosts}"
    )


def _traffic_from_key(key: str) -> TrafficSnapshot | None:
    if key == "none":
        return None
    parts = key.split("|")
    if len(parts) < 6:
        return None
    return TrafficSnapshot(
        requests=int(parts[0]),
        unique_ips=int(parts[1]),
        top_segment=parts[2] if parts[2] != "-" else None,
        top_segment_share_pct=float(parts[3]),
        error_rate_pct=float(parts[4]),
        active_hosts=int(parts[5]),
    )


class BriefingLoadError(RuntimeError):
    """Non-AI briefing — do not cache in Streamlit."""

    def __init__(self, briefing: EcosystemBriefing):
        self.briefing = briefing
        super().__init__(briefing.error or "briefing not from AI")


@st.cache_resource(ttl=900, show_spinner=False)
def _cached_briefing(
    config_path: str,
    agent_path: str,
    posture_computed_at: str,
    fleet_score: int,
    period_since: str,
    period_until: str,
    traffic_key: str,
    locale: str,
    refresh_nonce: int,
    agent_signature: str,
) -> EcosystemBriefing:
    from skopos.db_dialect import resolve_db_target
    from skopos.security.posture_loader import load_security_posture

    load_app_env()
    cfg = load_config(config_path)
    posture = load_security_posture(resolve_db_target(cfg), cfg, agent_yaml_path=agent_path)
    period_label = f"{period_since} → {period_until}"
    traffic = _traffic_from_key(traffic_key)
    return _load_briefing_or_raise(
        config_path,
        agent_path,
        posture,
        period_label=period_label,
        traffic=traffic,
        locale=locale,
    )


def _load_briefing_or_raise(
    config_path: str,
    agent_path: str,
    posture: SecurityPosture,
    *,
    period_label: str,
    traffic: TrafficSnapshot | None,
    locale: str,
) -> EcosystemBriefing:
    cfg = load_config(config_path)
    briefing = load_briefing(
        cfg,
        agent_path,
        posture,
        period_label=period_label,
        traffic=traffic,
        locale=locale,
    )
    if briefing.source != "ai":
        raise BriefingLoadError(briefing)
    return briefing


def _briefing_card_css(mood: str, accent: str) -> str:
    th = __import__("skopos.themes", fromlist=["get_active_theme"]).get_active_theme()
    return f"""
    <style>
    .ai-briefing-wrap {{
        margin: 0 0 1.5rem 0;
        animation: fadeUp 0.55s ease-out;
    }}
    .ai-briefing-card {{
        background: {th.card_bg};
        border: 1px solid {accent}44;
        border-left: 4px solid {accent};
        border-radius: 18px;
        padding: 1.35rem 1.5rem 1.25rem;
        box-shadow: {th.card_shadow};
    }}
    .ai-briefing-head {{
        display: flex;
        align-items: flex-start;
        gap: 0.85rem;
        margin-bottom: 0.85rem;
    }}
    .ai-briefing-icon {{
        font-size: 1.75rem;
        line-height: 1;
        filter: drop-shadow(0 2px 6px {accent}55);
    }}
    .ai-briefing-title {{
        font-size: 1.05rem;
        font-weight: 800;
        letter-spacing: -0.02em;
        color: {th.text};
        margin: 0;
    }}
    .ai-briefing-meta {{
        font-size: 0.82rem;
        color: {th.text_muted};
        margin-top: 0.2rem;
    }}
    .ai-briefing-meta strong {{
        color: {accent};
    }}
    .ai-briefing-body {{
        font-size: 1.02rem;
        line-height: 1.65;
        color: {th.text};
        white-space: pre-wrap;
    }}
    .ai-briefing-source {{
        font-size: 0.72rem;
        color: {th.text_muted};
        margin-top: 0.75rem;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }}
    </style>
    """


def _mood_label(locale: str, mood: str) -> str:
    return t(f"briefing.mood_{mood}", locale)


@st.fragment
def render_ecosystem_briefing_card(
    *,
    config_path: str,
    agent_path: str,
    posture: SecurityPosture,
    period: PeriodRange,
    traffic_df=None,
    locale: str,
    traffic_snapshot: TrafficSnapshot | None = None,
    lazy: bool = False,
) -> EcosystemBriefing:
    """Render the AI health briefing prominently below the page hero."""
    if "briefing_refresh" not in st.session_state:
        st.session_state.briefing_refresh = 0

    traffic = traffic_snapshot if traffic_snapshot is not None else traffic_snapshot_from_df(traffic_df)
    traffic_key = _traffic_cache_key(traffic)
    agent_signature = _briefing_cache_signature(agent_path)

    head_l, head_r = st.columns([11, 1], gap="small")
    with head_l:
        st.markdown(f"**🩺 {t('briefing.title', locale)}**")
    refresh_requested = False
    with head_r:
        if st.button("↻", key="briefing_refresh_btn", help=t("briefing.refresh", locale)):
            st.session_state.briefing_refresh += 1
            _cached_briefing.clear()
            refresh_requested = True

    # Analytics must never wait for a remote LLM during its initial render.
    # The rules-based card is complete and immediate; the existing refresh
    # action opts into the AI rewrite inside this isolated fragment.
    if lazy and not refresh_requested:
        briefing = fallback_ecosystem_briefing(posture, traffic, locale=locale)
    else:
        with st.spinner(t("briefing.loading", locale)):
            try:
                briefing = _cached_briefing(
                    config_path,
                    agent_path,
                    posture.computed_at_utc,
                    posture.fleet_score,
                    period.since_iso(),
                    period.until_iso(),
                    traffic_key,
                    locale,
                    st.session_state.briefing_refresh,
                    agent_signature,
                )
            except BriefingLoadError as exc:
                briefing = exc.briefing

    accent = mood_color(briefing.mood)
    mood_label = _mood_label(locale, briefing.mood)
    if briefing.source == "ai":
        source_label = t("briefing.source_ai", locale)
    elif briefing.source == "rules_api_error":
        err = (briefing.error or t("common.error", locale)).split("(")[0].strip()
        source_label = t("briefing.source_api_error", locale, error=err[:120])
    elif briefing.source == "rules_incomplete_ai":
        source_label = t("briefing.source_incomplete_ai", locale)
    else:
        source_label = t("briefing.source_rules", locale)

    st.markdown(_briefing_card_css(briefing.mood, accent), unsafe_allow_html=True)
    st.markdown(
        f"""
        <div class="ai-briefing-wrap">
          <div class="ai-briefing-card">
            <div class="ai-briefing-head">
              <div class="ai-briefing-icon">🩺</div>
              <div>
                <div class="ai-briefing-meta">
                  <strong>{mood_label}</strong>
                  · {t("briefing.score_line", locale, score=briefing.fleet_score, grade=briefing.grade)}
                </div>
              </div>
            </div>
            <div class="ai-briefing-body">{_escape_html(briefing.text)}</div>
            <div class="ai-briefing-source">{_escape_label(source_label)}</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    return briefing


def _escape_html(text: str) -> str:
    import html

    safe = html.escape(text)
    return safe.replace("\n\n", "<br><br>").replace("\n", "<br>")


def _escape_label(text: str) -> str:
    """Escape a ONE-LINE label for an `unsafe_allow_html` block.

    Not `_escape_html`: that turns newlines into `<br>`, which is right for a body and wrong for a
    label — a label that can grow lines can push the rest of the panel around.

    This exists because `source_label` reaches the markup below carrying an upstream HTTP error
    body: `providers.py` raises `LLMProviderError(f"LLM HTTP {status}: {resp.text[:500]}")` and
    that text becomes `briefing.error`. It was interpolated raw while its sibling
    `briefing.body` was escaped on the very next line, so whoever answered the LLM request could
    inject markup into the operator's panel.
    """
    import html
    import re

    return html.escape(re.sub(r"\s+", " ", str(text or ""))).strip()
