from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from .audit import SecurityFinding
from skopos.security.fail2ban_status import Fail2banStatus
from .project_audit import ProjectSecurityIssue

_SEV_PENALTY = {"critical": 18, "high": 10, "medium": 5, "low": 2, "info": 0}
_KNOCK_PENALTY_PER_ACTOR = 4
_KNOCK_PENALTY_MAX = 28


@dataclass(frozen=True)
class SecurityAlert:
    id: str
    severity: str
    category: str
    title: str
    message: str
    server_name: str | None = None
    action: str | None = None
    #: When this was last observed. An alert without a time cannot be triaged —
    #: the reader has no way to tell an attack in progress from a stale row.
    last_seen_utc: str | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "last_seen_utc": self.last_seen_utc,
            "severity": self.severity,
            "category": self.category,
            "title": self.title,
            "message": self.message,
            "server_name": self.server_name,
            "action": self.action,
        }


@dataclass
class ServerScore:
    server_name: str
    score: int
    grade: str
    deductions: list[str] = field(default_factory=list)


@dataclass
class SecurityPosture:
    fleet_score: int
    grade: str
    server_scores: list[ServerScore]
    alerts: list[SecurityAlert]
    remarks: list[str]
    computed_at_utc: str

    @property
    def critical_count(self) -> int:
        return sum(1 for a in self.alerts if a.severity == "critical")

    @property
    def high_count(self) -> int:
        return sum(1 for a in self.alerts if a.severity == "high")


def score_to_grade(score: int) -> str:
    if score >= 90:
        return "A"
    if score >= 75:
        return "B"
    if score >= 60:
        return "C"
    if score >= 45:
        return "D"
    return "F"


def _grade_color(grade: str) -> str:
    return {
        "A": "#34A853",
        "B": "#7CB342",
        "C": "#FBBC04",
        "D": "#FF6D00",
        "F": "#EA4335",
    }.get(grade, "#5f6368")


def grade_color(grade: str) -> str:
    return _grade_color(grade)


def _finding_to_alert(f: SecurityFinding, server_name: str) -> SecurityAlert | None:
    if f.severity in ("info",):
        return None
    aid = f"{server_name}:{f.category}:{f.title}"[:120]
    return SecurityAlert(
        id=aid,
        severity=f.severity,
        category=f.category,
        title=f.title,
        message=f.detail,
        server_name=server_name,
        action=f.recommendation,
    )


def _project_to_alert(p: ProjectSecurityIssue) -> SecurityAlert:
    return SecurityAlert(
        id=f"project:{p.category}:{p.title}"[:120],
        severity=p.severity,
        category="project",
        title=p.title,
        message=p.detail,
        server_name=None,
        action=p.recommendation,
    )


def _knock_to_alert(row: dict) -> SecurityAlert | None:
    score = int(row.get("threat_score") or 0)
    if score < 65:
        return None
    ip = row.get("remote_addr", "?")
    sev = "critical" if score >= 90 else "high"
    return SecurityAlert(
        id=f"knock:{ip}:{row.get('servers', '')}"[:120],
        severity=sev,
        category="perimeter",
        title=f"Active threat: {ip}",
        message=row.get("actor_label") or row.get("actor_class", "unknown"),
        server_name=(row.get("servers") or "").split(",")[0] or None,
        action="Block IP in firewall / ensure fail2ban is active; verify SSH key-only auth.",
        last_seen_utc=row.get("last_seen_utc"),
    )


def compute_server_score(
    server_name: str,
    findings: list[SecurityFinding],
    knock_summary: list[dict],
) -> ServerScore:
    score = 100
    deductions: list[str] = []
    for f in findings:
        pen = _SEV_PENALTY.get(f.severity, 0)
        if pen:
            score -= pen
            deductions.append(f"-{pen} {f.severity}: {f.title}")

    server_knocks = [k for k in knock_summary if server_name in (k.get("servers") or "")]
    knock_pen = min(_KNOCK_PENALTY_MAX, sum(_KNOCK_PENALTY_PER_ACTOR for k in server_knocks if (k.get("threat_score") or 0) >= 65))
    if knock_pen:
        score -= knock_pen
        deductions.append(f"-{knock_pen} perimeter: {len(server_knocks)} high-threat actors")

    score = max(0, min(100, score))
    return ServerScore(server_name=server_name, score=score, grade=score_to_grade(score), deductions=deductions)


def build_posture(
    *,
    server_findings: dict[str, list[SecurityFinding]],
    knock_summary: list[dict],
    project_issues: list[ProjectSecurityIssue],
    stale_servers: list[str] | None = None,
    fail2ban_by_server: dict[str, Fail2banStatus] | None = None,
) -> SecurityPosture:
    remarks: list[str] = []
    server_scores: list[ServerScore] = []
    for name, findings in server_findings.items():
        server_scores.append(compute_server_score(name, findings, knock_summary))

    project_alerts = [_project_to_alert(p) for p in project_issues]
    knock_alerts = []
    finding_alerts = []
    for name, findings in server_findings.items():
        for f in findings:
            a = _finding_to_alert(f, name)
            if a:
                finding_alerts.append(a)
    for row in knock_summary:
        a = _knock_to_alert(row)
        if a:
            knock_alerts.append(a)

    if stale_servers:
        for s in stale_servers:
            finding_alerts.append(
                SecurityAlert(
                    id=f"stale:{s}",
                    severity="medium",
                    category="monitoring",
                    title=f"Stale security scan: {s}",
                    message="No security scan in the last 24 hours — posture may be outdated.",
                    server_name=s,
                    action="Run: python skoposctl.py security-scan",
                )
            )

    # Project + config findings first, then perimeter knocks
    merged = project_alerts + finding_alerts + knock_alerts
    seen: set[str] = set()
    unique_alerts: list[SecurityAlert] = []
    for a in sorted(merged, key=lambda x: (_SEV_PENALTY.get(x.severity, 0) * -1, x.title)):
        if a.id in seen:
            continue
        seen.add(a.id)
        unique_alerts.append(a)
    unique_alerts = unique_alerts[:80]

    project_penalty = sum(_SEV_PENALTY.get(p.severity, 0) for p in project_issues)
    if server_scores:
        fleet = int(sum(s.score for s in server_scores) / len(server_scores))
    else:
        fleet = 70
    fleet = max(0, min(100, fleet - min(25, project_penalty // 2)))

    # Remarks — expert audit notes
    if any(f.severity == "critical" for fs in server_findings.values() for f in fs):
        remarks.append("CRITICAL: At least one server has critical misconfiguration — address before next deploy.")
    if any(p.severity in ("critical", "high") for p in project_issues):
        remarks.append("PROJECT: SKOPOS dashboard or secrets need hardening — see Project alerts.")
    high_knocks = [k for k in knock_summary if (k.get("threat_score") or 0) >= 80]
    fb_map = fail2ban_by_server or {}
    if high_knocks:
        active_fb = [name for name, st in fb_map.items() if st.is_protecting]
        missing_fb = [name for name in server_findings if name not in active_fb]
        if active_fb and not missing_fb:
            remarks.append(
                f"PERIMETER: {len(high_knocks)} high-threat IPs probing SSH; fail2ban active on all "
                f"{len(active_fb)} server(s) and blocking attackers."
            )
        elif active_fb:
            remarks.append(
                f"PERIMETER: {len(high_knocks)} high-threat IPs probing SSH; fail2ban active on "
                f"{', '.join(active_fb)} — enable on {', '.join(missing_fb)}."
            )
        else:
            remarks.append(
                f"PERIMETER: {len(high_knocks)} high-threat IPs actively probing SSH — enable fail2ban + key-only auth."
            )
    elif fb_map:
        active_fb = [name for name, st in fb_map.items() if st.is_protecting]
        if active_fb:
            remarks.append(f"FAIL2BAN: active on {', '.join(active_fb)}.")
    fw_inactive = sum(
        1
        for fs in server_findings.values()
        for f in fs
        if f.category == "firewall" and f.severity == "medium" and "inactive" in f.title.lower()
    )
    if fw_inactive:
        remarks.append(f"FIREWALL: {fw_inactive} server(s) without active firewall — default-deny inbound recommended.")

    pwd_auth = sum(1 for fs in server_findings.values() for f in fs if "password authentication" in f.title.lower())
    if pwd_auth:
        remarks.append(f"SSH: PasswordAuthentication enabled on {pwd_auth} server(s) — disable immediately.")

    if fleet >= 85 and not remarks:
        remarks.append("Posture is good. Keep periodic scans and monitor port-knock feed.")

    return SecurityPosture(
        fleet_score=fleet,
        grade=score_to_grade(fleet),
        server_scores=server_scores,
        alerts=unique_alerts[:80],
        remarks=remarks,
        computed_at_utc=datetime.now(tz=timezone.utc).isoformat(),
    )
