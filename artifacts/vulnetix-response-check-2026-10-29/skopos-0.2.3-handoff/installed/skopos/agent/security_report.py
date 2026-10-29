"""AI consolidated security report with detailed remediation."""

from __future__ import annotations

from datetime import datetime, timezone

from skopos.agent.config import AgentConfig, load_agent_config
from skopos.agent.providers import ChatMessage, LLMProviderError, chat_completion
from skopos.config import AppConfig
from skopos.db import connect_for_config, init_db
from skopos.i18n import t
from skopos.security.posture import SecurityPosture
from skopos.security.report_builder import SecurityReportBundle, build_fallback_security_report, _risk_from_posture

from .context import build_server_context

_LANG = {"en": "English", "ru": "Russian", "es": "Spanish"}

SECURITY_REPORT_PROMPT = """You are a senior DevSecOps lead writing a CONSOLIDATED SECURITY REPORT for the platform owner.

Write the full report in {language} using clear Markdown formatting.

Required sections (use ## headers exactly):

## Executive summary
- Overall risk level: Critical / High / Medium / Low (pick one)
- 3-5 bullet points: what matters most right now

## Fleet posture
- Table or bullet list: each server, score estimate, top concern

## Active threats & findings
Group by severity (Critical → High → Medium). For EACH issue:
- What was detected (specific host, port, path, IP)
- Why it matters (business/security impact)
- Evidence from the data

## Perimeter & intrusion activity
- Port knock / SSH brute-force / suspicious IPs if present in context
- Recommended blocks or fail2ban actions

## Scan history & trends
- Use scan history data if available: improving or degrading posture

## Remediation plan (PRIORITY ORDER)
Numbered checklist. For EACH item include:
1. **Action title** (imperative)
2. **Affected servers**
3. **Steps** — concrete commands or config changes where applicable (ufw, sshd_config, docker prune, etc.)
4. **Priority:** Immediate (today) / 24h / This week
5. **Verification** — how to confirm the fix worked

## Long-term hardening
- 3-5 strategic recommendations (monitoring, auto-scan, backups, least privilege)

Rules:
- Be specific — reference real server names, ports, IPs from the context
- Do NOT invent hosts or findings not in the data
- Prioritize actionable fixes over generic advice
- Include shell commands in fenced ```bash blocks when helpful
- Total length: comprehensive but focused (800-2000 words)"""


def load_security_report(
    app_cfg: AppConfig,
    agent_path: str,
    *,
    posture: SecurityPosture,
    findings_map: dict[str, list[dict]],
    snapshots: list[dict],
    knocks_summary: list[dict] | None = None,
    scan_history_summary: dict | None = None,
    server_name: str | None = None,
    provider_id: str | None = None,
    locale: str = "en",
) -> SecurityReportBundle:
    """Generate AI report or fall back to rule-based consolidated report."""
    fallback = build_fallback_security_report(
        posture=posture,
        findings_map=findings_map,
        snapshots=snapshots,
        knocks_summary=knocks_summary,
        locale=locale,
        scan_history_summary=scan_history_summary,
    )

    try:
        agent_cfg = load_agent_config(agent_path)
    except Exception as e:
        return SecurityReportBundle(
            markdown=fallback.markdown,
            risk_level=fallback.risk_level,
            source="rules",
            error=str(e),
            generated_at_utc=fallback.generated_at_utc,
        )

    prov_id = provider_id or agent_cfg.default_provider
    prov = agent_cfg.providers.get(prov_id)
    if not prov:
        return fallback

    if prov.kind in ("openai_compatible", "anthropic_compatible") and not prov.api_key:
        return SecurityReportBundle(
            markdown=fallback.markdown,
            risk_level=fallback.risk_level,
            source="rules",
            error=t("security.agent_no_key", locale, env=prov.api_key_env or "API_KEY"),
            generated_at_utc=fallback.generated_at_utc,
        )

    con = connect_for_config(app_cfg)
    init_db(con)
    try:
        context = build_server_context(app_cfg, con, server_name=server_name, traffic_hours=168)
        context = context[: agent_cfg.max_context_chars]
        lang = _LANG.get(locale, "English")
        messages = [
            ChatMessage(role="system", content=agent_cfg.system_prompt),
            ChatMessage(
                role="user",
                content=f"{SECURITY_REPORT_PROMPT.format(language=lang)}\n\n---\n\n{context}",
            ),
        ]
        report_md = chat_completion(agent_cfg, messages, provider_id=prov_id)
        now = datetime.now(tz=timezone.utc).isoformat()
        risk = _extract_risk(report_md) or fallback.risk_level
        return SecurityReportBundle(
            markdown=report_md.strip(),
            risk_level=risk,
            source="ai",
            provider=prov_id,
            model=prov.model,
            generated_at_utc=now,
        )
    except LLMProviderError as e:
        return SecurityReportBundle(
            markdown=fallback.markdown,
            risk_level=fallback.risk_level,
            source="rules_api_error",
            provider=prov_id,
            model=prov.model if prov else None,
            error=str(e),
            generated_at_utc=fallback.generated_at_utc,
        )
    finally:
        con.close()


def _extract_risk(text: str) -> str | None:
    lower = text.lower()
    for level in ("critical", "high", "medium", "low"):
        if f"risk level: {level}" in lower or f"risk level:** {level}" in lower:
            return level
        if f"overall risk level: {level}" in lower:
            return level
    return None
