"""Consolidated security report — rule-based fallback + structure helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from skopos.i18n import t
from skopos.security.posture import SecurityPosture


@dataclass(frozen=True)
class SecurityReportBundle:
    markdown: str
    risk_level: str  # critical | high | medium | low
    source: str  # ai | rules | rules_api_error
    provider: str | None = None
    model: str | None = None
    generated_at_utc: str = ""
    error: str | None = None


_SEV_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


def _risk_from_posture(posture: SecurityPosture) -> str:
    if posture.critical_count > 0 or posture.fleet_score < 45:
        return "critical"
    if posture.high_count > 0 or posture.fleet_score < 60:
        return "high"
    if posture.fleet_score < 75:
        return "medium"
    return "low"


def _risk_label(locale: str, risk: str) -> str:
    return t(f"report.risk_{risk}", locale)


def build_fallback_security_report(
    *,
    posture: SecurityPosture,
    findings_map: dict[str, list[dict]],
    snapshots: list[dict],
    knocks_summary: list[dict] | None,
    locale: str,
    scan_history_summary: dict | None = None,
) -> SecurityReportBundle:
    risk = _risk_from_posture(posture)
    now = datetime.now(tz=timezone.utc).isoformat()
    lines: list[str] = []

    lines.append(f"# {t('report.title', locale)}")
    lines.append("")
    lines.append(f"**{t('report.risk_label', locale)}:** {_risk_label(locale, risk)} · "
                 f"**{t('security.score_label', locale)}:** {posture.fleet_score}/100 ({posture.grade})")
    lines.append(f"**{t('report.generated', locale)}:** {now[:19]} UTC")
    lines.append("")

    lines.append(f"## {t('report.exec_summary', locale)}")
    if posture.remarks:
        for r in posture.remarks[:6]:
            lines.append(f"- {r}")
    else:
        lines.append(t("report.exec_ok", locale))
    lines.append("")

    lines.append(f"## {t('report.fleet_scores', locale)}")
    for ss in posture.server_scores:
        lines.append(f"- **{ss.server_name}** — {ss.score}/100 ({ss.grade})")
    lines.append("")

    lines.append(f"## {t('report.active_threats', locale)}")
    alerts = [a for a in posture.alerts if a.severity in ("critical", "high", "medium")][:20]
    if alerts:
        for i, a in enumerate(alerts, 1):
            srv = f" [{a.server_name}]" if a.server_name else ""
            lines.append(f"{i}. **[{a.severity.upper()}]** {a.title}{srv}")
            lines.append(f"   - {a.message}")
            if a.action:
                lines.append(f"   - **{t('security.recommendation', locale)}:** {a.action}")
    else:
        lines.append(t("report.no_critical", locale))
    lines.append("")

    lines.append(f"## {t('report.findings_by_server', locale)}")
    for name, findings in sorted(findings_map.items()):
        if not findings:
            continue
        sorted_f = sorted(findings, key=lambda f: _SEV_ORDER.get(f.get("severity", "info"), 9))
        lines.append(f"### {name}")
        for f in sorted_f[:12]:
            sev = f.get("severity", "info").upper()
            lines.append(f"- **[{sev}]** {f.get('title')}")
            if f.get("detail"):
                lines.append(f"  - {f.get('detail')}")
            if f.get("recommendation"):
                lines.append(f"  - → {f.get('recommendation')}")
        extra = len(sorted_f) - 12
        if extra > 0:
            lines.append(f"  - … +{extra} {t('report.more', locale)}")
        lines.append("")

    if knocks_summary:
        hot = [k for k in knocks_summary if int(k.get("threat_score") or 0) >= 65][:10]
        if hot:
            lines.append(f"## {t('report.perimeter', locale)}")
            for row in hot:
                lines.append(
                    f"- **{row.get('remote_addr')}** ({row.get('country_code') or '?'}) "
                    f"— {t('security.knocks_threat', locale)} {row.get('threat_score')}, "
                    f"{row.get('hits')} hits, ports: {row.get('port_list')}"
                )
                lines.append(f"  - **{t('security.recommendation', locale)}:** "
                             f"{t('report.block_ip', locale)}")
            lines.append("")

    if scan_history_summary and scan_history_summary.get("total_scans"):
        lines.append(f"## {t('report.scan_history', locale)}")
        lines.append(
            f"- {t('report.total_scans', locale)}: {scan_history_summary['total_scans']}"
        )
        if scan_history_summary.get("last_scan_utc"):
            lines.append(f"- {t('history.last_scan', locale)}: {scan_history_summary['last_scan_utc'][:19]}")
        lines.append("")

    lines.append(f"## {t('report.remediation', locale)}")
    steps = _remediation_steps(posture, findings_map, locale)
    for i, step in enumerate(steps, 1):
        lines.append(f"{i}. {step}")
    lines.append("")
    lines.append(f"*{t('report.rules_footer', locale)}*")

    return SecurityReportBundle(
        markdown="\n".join(lines),
        risk_level=risk,
        source="rules",
        generated_at_utc=now,
    )


def _remediation_steps(
    posture: SecurityPosture,
    findings_map: dict[str, list[dict]],
    locale: str,
) -> list[str]:
    steps: list[str] = []
    seen: set[str] = set()

    for a in posture.alerts:
        if a.action and a.action not in seen:
            seen.add(a.action)
            steps.append(a.action)

    for findings in findings_map.values():
        for f in sorted(findings, key=lambda x: _SEV_ORDER.get(x.get("severity", "info"), 9)):
            rec = f.get("recommendation")
            if rec and rec not in seen:
                seen.add(rec)
                steps.append(rec)

    if not steps:
        steps.append(t("report.default_action", locale))
    return steps[:15]
