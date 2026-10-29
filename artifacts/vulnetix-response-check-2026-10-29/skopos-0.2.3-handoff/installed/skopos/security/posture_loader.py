from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ..config import AppConfig, load_config
from ..db import connect, init_db
from .audit import SecurityFinding
from .fail2ban_status import Fail2banStatus, parse_fail2ban_section
from .posture import SecurityPosture, build_posture
from .project_audit import audit_stats_project
from .store import latest_findings_by_server, latest_snapshots, knock_summary_by_actor, load_snapshot_payload


def _parse_ts(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _fail2ban_from_snapshot(row: dict | None, findings: list[SecurityFinding]) -> Fail2banStatus:
    if row:
        snap = load_snapshot_payload(row)
        if snap.fail2ban_jails or snap.fail2ban_banned_count or snap.fail2ban_recent_ips or snap.fail2ban_active:
            jails = tuple(snap.fail2ban_jails)
            parts: list[str] = []
            if snap.fail2ban_active or jails:
                parts.append("service active")
            if jails:
                parts.append(f"jails: {', '.join(jails)}")
            if snap.fail2ban_banned_count:
                parts.append(f"currently banned: {snap.fail2ban_banned_count}")
            elif snap.fail2ban_recent_ips:
                parts.append(f"recent bans in log: {len(snap.fail2ban_recent_ips)}")
            return Fail2banStatus(
                service_active=bool(snap.fail2ban_active or jails),
                jails=jails,
                currently_banned=snap.fail2ban_banned_count,
                recent_ban_ips=tuple(snap.fail2ban_recent_ips),
                sshd_jail=any(j.lower().startswith("sshd") for j in jails) or snap.fail2ban_active,
                summary="; ".join(parts) or "active",
            )
        raw_fb = (snap.raw_sections or {}).get("fail2ban", "")
        if raw_fb.strip():
            return parse_fail2ban_section(raw_fb)
    for f in findings:
        title = f.title.lower()
        if title == "fail2ban active":
            return Fail2banStatus(
                service_active=True,
                jails=(),
                currently_banned=0,
                recent_ban_ips=(),
                sshd_jail=True,
                summary=f.detail[:160],
            )
        if "fail2ban not detected" in title:
            return parse_fail2ban_section("")
    return parse_fail2ban_section("")


def load_security_posture(
    db_target: str,
    cfg: AppConfig | None = None,
    *,
    agent_yaml_path: str = "./agent.yaml",
    knock_hours: int = 168,
) -> SecurityPosture:
    cfg = cfg or load_config("./servers.yaml")
    con = connect(db_target)
    init_db(con)

    server_names = [s.name for s in cfg.servers]
    server_findings: dict[str, list[SecurityFinding]] = {}
    stale: list[str] = []
    cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=24)

    snaps = latest_snapshots(con, server_names)
    snap_by_name = {r["server_name"]: r for r in snaps}
    fail2ban_by_server: dict[str, Fail2banStatus] = {}

    for name in server_names:
        raw = latest_findings_by_server(con, name)
        server_findings[name] = [
            SecurityFinding(
                severity=r["severity"],
                category=r["category"],
                title=r["title"],
                detail=r["detail"],
                recommendation=r.get("recommendation"),
            )
            for r in raw
        ]
        row = snap_by_name.get(name)
        fail2ban_by_server[name] = _fail2ban_from_snapshot(row, server_findings[name])
        if not row:
            stale.append(name)
        else:
            ts = _parse_ts(row.get("scanned_at_utc"))
            if ts and ts < cutoff:
                stale.append(name)

    knock_summary = knock_summary_by_actor(con, server_names, hours=knock_hours)
    project_issues = audit_stats_project(cfg, agent_yaml_path=agent_yaml_path)
    con.close()

    return build_posture(
        server_findings=server_findings,
        knock_summary=knock_summary,
        project_issues=project_issues,
        stale_servers=stale,
        fail2ban_by_server=fail2ban_by_server,
    )
