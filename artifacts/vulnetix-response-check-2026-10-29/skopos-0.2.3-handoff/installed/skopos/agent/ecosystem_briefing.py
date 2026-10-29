"""AI ecosystem health briefing — human-language summary for the dashboard."""

from __future__ import annotations

import re
from dataclasses import dataclass

import pandas as pd
import requests

from skopos.agent.config import AgentConfig, get_provider, load_agent_config
from skopos.agent.providers import (
    ChatMessage,
    LLMProviderError,
    _is_reasoning_model,
    chat_completion_with_fallback,
)
from skopos.config import AppConfig
from skopos.db import connect_for_config, init_db
from skopos.i18n import t
from skopos.security.audit import SecurityFinding
from skopos.security.posture import SecurityPosture, grade_color
from skopos.security.fail2ban_status import format_fail2ban_line
from skopos.security.store import latest_findings_by_server, latest_snapshots
from skopos.security.posture_loader import _fail2ban_from_snapshot


@dataclass(frozen=True)
class TrafficSnapshot:
    requests: int
    unique_ips: int
    top_segment: str | None
    top_segment_share_pct: float
    error_rate_pct: float
    active_hosts: int


@dataclass(frozen=True)
class EcosystemBriefing:
    text: str
    mood: str  # good | caution | urgent
    source: str  # ai | rules_no_key | rules_api_error | rules_incomplete_ai
    fleet_score: int
    grade: str
    error: str | None = None


_LANG = {"en": "English", "ru": "Russian", "es": "Spanish"}

_BRIEFING_PROMPT = """You are the on-call SRE writing a morning briefing for the platform owner.

Based on the ecosystem data below, write a short health assessment in {language}.

Requirements:
- Exactly 2-3 short paragraphs in plain human language
- No JSON, no markdown headers, no numbered lists, no bullet points
- First sentence: overall verdict (things look calm / need attention / urgent issues)
- Mention what is healthy and what worries you; use real server or product names from the data
- If fail2ban status is listed per server, say which servers have it active; do NOT tell the owner to enable fail2ban where it is already active and banning IPs
- If Observability / Prometheus APM is present and live, briefly reflect Hub/Factory health or invoke/402 anomalies when relevant; if unreachable, do not invent metrics
- Last sentence: ONE concrete recommended next step
- Sound like a trusted colleague, not a robot or a compliance report
- Keep under 180 words total
- Write complete sentences only — never stop mid-phrase or mid-word"""


def _normalize_briefing_text(text: str) -> str:
    cleaned = text.strip()
    cleaned = re.sub(r"^#+\s*", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"\*\*(.+?)\*\*", r"\1", cleaned)
    cleaned = re.sub(r"\*(.+?)\*", r"\1", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _briefing_looks_incomplete(text: str) -> bool:
    """Detect truncated model output (common with reasoning models on short budgets)."""
    normalized = _normalize_briefing_text(text)
    if not normalized:
        return True
    words = normalized.split()
    if len(words) < 35:
        return True
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", normalized) if p.strip()]
    if len(paragraphs) < 2:
        return True
    last = paragraphs[-1]
    if len(last.split()) <= 4 and not re.search(r"[.!?…»\"')]\s*$", last):
        return True
    if not re.search(r"[.!?…»\"')]\s*$", normalized):
        return True
    return False


def _pick_briefing_provider(agent_cfg: AgentConfig) -> str:
    """Prefer a fast non-reasoning model for short dashboard briefings."""
    if agent_cfg.briefing_provider and agent_cfg.briefing_provider in agent_cfg.providers:
        return agent_cfg.briefing_provider
    default_id = agent_cfg.default_provider
    default = get_provider(agent_cfg, default_id)
    if not _is_reasoning_model(default.model):
        return default_id
    for pid in ("deepseek", "openrouter", "ollama", "lmstudio"):
        if pid not in agent_cfg.providers:
            continue
        prov = get_provider(agent_cfg, pid)
        if prov.api_key or prov.kind in ("ollama", "lmstudio"):
            if not _is_reasoning_model(prov.model):
                return pid
    return default_id


def _briefing_attempt_chain(agent_cfg: AgentConfig) -> list[tuple[str | None, str | None]]:
    """Ordered (provider_id, model_override) attempts for resilient briefings."""
    chain: list[tuple[str | None, str | None]] = []
    primary = _pick_briefing_provider(agent_cfg)
    if agent_cfg.briefing_model:
        chain.append((primary, agent_cfg.briefing_model))
    chain.append((primary, None))

    if agent_cfg.default_provider != primary:
        default = get_provider(agent_cfg, agent_cfg.default_provider)
        if _is_reasoning_model(default.model):
            chain.append((agent_cfg.default_provider, "deepseek/deepseek-chat"))
        chain.append((agent_cfg.default_provider, None))

    if "openrouter" in agent_cfg.providers and primary != "openrouter":
        or_prov = get_provider(agent_cfg, "openrouter")
        if or_prov.api_key:
            if not _is_reasoning_model(or_prov.model):
                chain.append(("openrouter", or_prov.model))
            else:
                chain.append(("openrouter", "deepseek/deepseek-chat"))
                chain.append(("openrouter", None))

    if "deepseek" in agent_cfg.providers and primary != "deepseek":
        chain.append(("deepseek", None))

    seen: set[tuple[str | None, str | None]] = set()
    out: list[tuple[str | None, str | None]] = []
    for item in chain:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def traffic_snapshot_from_df(df: pd.DataFrame | None) -> TrafficSnapshot | None:
    if df is None or df.empty:
        return None
    requests = len(df)
    unique_ips = int(df["remote_addr"].nunique()) if "remote_addr" in df.columns else 0
    active_hosts = int(df["host"].nunique()) if "host" in df.columns else 0
    status = pd.to_numeric(df["status"], errors="coerce") if "status" in df.columns else pd.Series(dtype=float)
    errors = int((status >= 500).sum()) if not status.empty else 0
    error_rate = round(errors / requests * 100, 1) if requests else 0.0

    top_segment = None
    top_share = 0.0
    if "ecosystem_segment" in df.columns:
        seg = (
            df["ecosystem_segment"]
            .fillna("other")
            .value_counts()
        )
        if not seg.empty:
            top_segment = str(seg.index[0])
            top_share = round(seg.iloc[0] / requests * 100, 1)

    return TrafficSnapshot(
        requests=requests,
        unique_ips=unique_ips,
        top_segment=top_segment,
        top_segment_share_pct=top_share,
        error_rate_pct=error_rate,
        active_hosts=active_hosts,
    )


def _mood_from_score(score: int) -> str:
    if score >= 75:
        return "good"
    if score >= 45:
        return "caution"
    return "urgent"


def _collector_lines(cfg: AppConfig) -> list[str]:
    try:
        con = connect_for_config(cfg)
        rows = con.execute(
            """
            SELECT server_name, last_ok_at_utc, last_error_at_utc, last_error, last_inserted_rows
            FROM collector_status ORDER BY server_name
            """
        ).fetchall()
        con.close()
    except Exception:
        return []
    lines: list[str] = []
    known = {s.name for s in cfg.servers}
    for name, ok_at, err_at, err, inserted in rows:
        if name not in known:
            continue
        if ok_at and (not err or not err_at or ok_at >= err_at):
            lines.append(f"- {name}: last collect OK at {ok_at}, +{inserted or 0} rows")
        elif err:
            lines.append(f"- {name}: collector error — {err}")
        else:
            lines.append(f"- {name}: collector never ran successfully")
    return lines


def _fail2ban_lines(cfg: AppConfig) -> list[str]:
    try:
        con = connect_for_config(cfg)
        init_db(con)
        names = [s.name for s in cfg.servers]
        snaps = {r["server_name"]: r for r in latest_snapshots(con, names)}
        lines: list[str] = []
        for name in names:
            findings_raw = latest_findings_by_server(con, name)
            typed = [
                SecurityFinding(
                    severity=r["severity"],
                    category=r["category"],
                    title=r["title"],
                    detail=r["detail"],
                    recommendation=r.get("recommendation"),
                )
                for r in findings_raw
            ]
            status = _fail2ban_from_snapshot(snaps.get(name), typed)
            lines.append(format_fail2ban_line(name, status))
        con.close()
        return lines
    except Exception:
        return []


def build_ecosystem_health_context(
    cfg: AppConfig,
    posture: SecurityPosture,
    *,
    period_label: str,
    traffic: TrafficSnapshot | None,
) -> str:
    parts: list[str] = ["# Ecosystem health context\n"]
    parts.append(f"Period: {period_label}\n")
    parts.append(f"Fleet security score: {posture.fleet_score}/100 (grade {posture.grade})\n")
    parts.append(f"Active alerts: {posture.critical_count} critical, {posture.high_count} high\n")

    if posture.server_scores:
        parts.append("\n## Per-server scores\n")
        for s in posture.server_scores:
            parts.append(f"- {s.server_name}: {s.score}/100 ({s.grade})\n")

    if posture.remarks:
        parts.append("\n## Expert remarks\n")
        for r in posture.remarks:
            parts.append(f"- {r}\n")

    if posture.alerts:
        parts.append("\n## Top alerts\n")
        for a in posture.alerts[:8]:
            parts.append(f"- [{a.severity.upper()}] {a.title}: {a.message}\n")

    if traffic:
        parts.append("\n## HTTP traffic (selected period)\n")
        parts.append(f"- Requests: {traffic.requests:,}\n")
        parts.append(f"- Unique visitors (IPs): {traffic.unique_ips:,}\n")
        parts.append(f"- Active hosts: {traffic.active_hosts}\n")
        parts.append(f"- 5xx error rate: {traffic.error_rate_pct}%\n")
        if traffic.top_segment:
            parts.append(
                f"- Busiest ecosystem segment: {traffic.top_segment} "
                f"({traffic.top_segment_share_pct}% of requests)\n"
            )

    collectors = _collector_lines(cfg)
    if collectors:
        parts.append("\n## Log collectors\n")
        parts.extend(f"{line}\n" for line in collectors)

    fail2ban = _fail2ban_lines(cfg)
    if fail2ban:
        parts.append("\n## fail2ban (per server)\n")
        parts.extend(f"{line}\n" for line in fail2ban)

    parts.append("\n## Fleet servers\n")
    for s in cfg.servers:
        parts.append(f"- {s.name} @ {s.ssh.host}\n")

    try:
        from skopos.observability.context_fmt import format_observability_context

        parts.append(format_observability_context(include_hub_breakdown=False))
    except Exception:
        pass

    return "".join(parts)


def fallback_ecosystem_briefing(
    posture: SecurityPosture,
    traffic: TrafficSnapshot | None,
    *,
    locale: str,
    source: str = "rules_no_key",
    error: str | None = None,
) -> EcosystemBriefing:
    mood = _mood_from_score(posture.fleet_score)
    paragraphs: list[str] = []

    if mood == "good":
        paragraphs.append(
            t(
                "briefing.fallback_verdict_good",
                locale,
                score=posture.fleet_score,
                grade=posture.grade,
            )
        )
    elif mood == "caution":
        paragraphs.append(
            t(
                "briefing.fallback_verdict_caution",
                locale,
                score=posture.fleet_score,
                grade=posture.grade,
            )
        )
    else:
        paragraphs.append(
            t(
                "briefing.fallback_verdict_urgent",
                locale,
                score=posture.fleet_score,
                grade=posture.grade,
                critical=posture.critical_count,
                high=posture.high_count,
            )
        )

    if traffic and traffic.requests > 0:
        seg_part = ""
        if traffic.top_segment:
            seg_part = t(
                "briefing.fallback_segment",
                locale,
                segment=traffic.top_segment,
                share=traffic.top_segment_share_pct,
            )
        paragraphs.append(
            t(
                "briefing.fallback_traffic",
                locale,
                requests=f"{traffic.requests:,}",
                ips=f"{traffic.unique_ips:,}",
                hosts=traffic.active_hosts,
                errors=traffic.error_rate_pct,
                segment_part=seg_part,
            )
        )
    else:
        paragraphs.append(t("briefing.fallback_no_traffic", locale))

    action = posture.remarks[0] if posture.remarks else t("briefing.fallback_default_action", locale)
    paragraphs.append(t("briefing.fallback_next_step", locale, action=action))

    return EcosystemBriefing(
        text="\n\n".join(paragraphs),
        mood=mood,
        source=source,
        fleet_score=posture.fleet_score,
        grade=posture.grade,
        error=error,
    )


def _api_error_briefing(
    posture: SecurityPosture,
    traffic: TrafficSnapshot | None,
    *,
    locale: str,
    error: str,
) -> EcosystemBriefing:
    return fallback_ecosystem_briefing(
        posture,
        traffic,
        locale=locale,
        source="rules_api_error",
        error=error[:240],
    )


def generate_ecosystem_briefing(
    cfg: AppConfig,
    agent_cfg: AgentConfig,
    posture: SecurityPosture,
    *,
    period_label: str,
    traffic: TrafficSnapshot | None,
    locale: str = "en",
    provider_id: str | None = None,
) -> EcosystemBriefing:
    context = build_ecosystem_health_context(
        cfg,
        posture,
        period_label=period_label,
        traffic=traffic,
    )
    language = _LANG.get(locale, "English")
    prov_id = provider_id or _pick_briefing_provider(agent_cfg)
    prov = get_provider(agent_cfg, prov_id)

    if not prov.api_key and prov.kind in ("openai_compatible", "anthropic_compatible"):
        return fallback_ecosystem_briefing(posture, traffic, locale=locale)

    messages = [
        ChatMessage(
            role="system",
            content=(
                "You write clear, human ecosystem health briefings for production operators. "
                "Never use markdown formatting. Always finish every sentence and paragraph."
            ),
        ),
        ChatMessage(
            role="user",
            content=f"{_BRIEFING_PROMPT.format(language=language)}\n\n---\n\n{context}",
        ),
    ]
    attempts = [(prov_id, agent_cfg.briefing_model)] if provider_id else _briefing_attempt_chain(agent_cfg)
    try:
        text, _used_provider, _used_model = chat_completion_with_fallback(
            agent_cfg,
            messages,
            attempts,
            temperature=0.35,
            max_tokens=4096,
        )
        text = _normalize_briefing_text(text)
        if not text:
            raise LLMProviderError("empty briefing")
        if _briefing_looks_incomplete(text):
            return fallback_ecosystem_briefing(
                posture,
                traffic,
                locale=locale,
                source="rules_incomplete_ai",
            )
    except (LLMProviderError, requests.RequestException, OSError) as e:
        return _api_error_briefing(posture, traffic, locale=locale, error=str(e))

    return EcosystemBriefing(
        text=text,
        mood=_mood_from_score(posture.fleet_score),
        source="ai",
        fleet_score=posture.fleet_score,
        grade=posture.grade,
    )


def load_briefing(
    cfg: AppConfig,
    agent_path: str,
    posture: SecurityPosture,
    *,
    period_label: str,
    traffic: TrafficSnapshot | None,
    locale: str,
) -> EcosystemBriefing:
    from skopos.config import load_app_env

    load_app_env()
    agent_cfg = load_agent_config(agent_path)
    return generate_ecosystem_briefing(
        cfg,
        agent_cfg,
        posture,
        period_label=period_label,
        traffic=traffic,
        locale=locale,
    )


def mood_color(mood: str) -> str:
    return {
        "good": grade_color("A"),
        "caution": grade_color("C"),
        "urgent": grade_color("F"),
    }.get(mood, grade_color("C"))
