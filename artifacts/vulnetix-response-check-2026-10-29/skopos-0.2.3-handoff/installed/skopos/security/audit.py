from __future__ import annotations

from dataclasses import asdict, dataclass

from .probe import PortInfo, ServerSnapshot

# Well-known sensitive ports exposed publicly
_RISKY_PUBLIC_PORTS: dict[int, tuple[str, str]] = {
    3306: ("critical", "MySQL exposed to the internet"),
    5432: ("critical", "PostgreSQL exposed to the internet"),
    6379: ("critical", "Redis exposed to the internet"),
    27017: ("critical", "MongoDB exposed to the internet"),
    9200: ("high", "Elasticsearch exposed to the internet"),
    11211: ("high", "Memcached exposed to the internet"),
    2375: ("critical", "Docker API exposed to the internet"),
    2376: ("high", "Docker TLS API exposed publicly"),
    8080: ("medium", "HTTP alt port publicly exposed"),
    8443: ("medium", "HTTPS alt port publicly exposed"),
}


@dataclass(frozen=True)
class SecurityFinding:
    severity: str  # critical | high | medium | low | info
    category: str
    title: str
    detail: str
    recommendation: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def _port_finding(port: PortInfo) -> SecurityFinding | None:
    if port.bind_scope != "public":
        return None
    sev_title = _RISKY_PUBLIC_PORTS.get(port.port)
    if sev_title:
        sev, title = sev_title
        return SecurityFinding(
            severity=sev,
            category="ports",
            title=title,
            detail=f"{port.proto}/{port.port} on {port.address} ({port.process or 'unknown process'})",
            recommendation="Restrict bind to localhost or VPN; use firewall rules.",
        )
    if port.port == 22:
        return SecurityFinding(
            severity="info",
            category="ports",
            title="SSH publicly reachable",
            detail=f"Port 22 open on {port.address}",
            recommendation="Prefer key-only auth, fail2ban, non-default port optional.",
        )
    if port.port in (80, 443):
        return SecurityFinding(
            severity="info",
            category="ports",
            title="Web ports public (expected)",
            detail=f"{port.proto}/{port.port} on {port.address}",
        )
    return SecurityFinding(
        severity="low",
        category="ports",
        title=f"Public port {port.port} open",
        detail=f"{port.proto}/{port.port} on {port.address} ({port.process or 'unknown'})",
        recommendation="Verify this service should be internet-facing.",
    )


def _is_internal_docker_mount(mount: str) -> bool:
    m = mount.lower()
    return "overlay2" in m or "overlayfs" in m or "/docker/" in m


def _consolidate_disk_findings(findings: list[SecurityFinding]) -> list[SecurityFinding]:
    """Merge many docker layer disk alerts into one readable finding."""
    kept: list[SecurityFinding] = []
    docker_medium: list[SecurityFinding] = []
    docker_critical: list[SecurityFinding] = []

    for f in findings:
        if f.category != "resources" or "disk" not in f.title.lower():
            kept.append(f)
            continue
        mount = f.title[f.title.find("(") + 1 : -1] if "(" in f.title else ""
        if _is_internal_docker_mount(mount):
            if f.severity == "critical":
                docker_critical.append(f)
            else:
                docker_medium.append(f)
        else:
            kept.append(f)

    if docker_critical:
        sample = docker_critical[0]
        kept.append(
            SecurityFinding(
                severity="critical",
                category="resources",
                title=f"Docker storage critical ({len(docker_critical)} layers)",
                detail="; ".join(f.detail for f in docker_critical[:4])
                + (f" … +{len(docker_critical) - 4} more" if len(docker_critical) > 4 else ""),
                recommendation=sample.recommendation,
            )
        )
    if docker_medium:
        kept.append(
            SecurityFinding(
                severity="medium",
                category="resources",
                title=f"Docker storage high ({len(docker_medium)} layers)",
                detail="; ".join(f.detail for f in docker_medium[:4])
                + (f" … +{len(docker_medium) - 4} more" if len(docker_medium) > 4 else ""),
                recommendation="Prune unused Docker layers: docker system prune -a",
            )
        )
    return kept


def audit_snapshot(snap: ServerSnapshot) -> list[SecurityFinding]:
    findings: list[SecurityFinding] = []

    if snap.mem_used_pct is not None and snap.mem_used_pct >= 90:
        findings.append(
            SecurityFinding(
                severity="high",
                category="resources",
                title="Memory usage critical",
                detail=f"RAM {snap.mem_used_pct}% used ({snap.mem_used_mb}/{snap.mem_total_mb} MB)",
                recommendation="Investigate memory leaks or add swap / scale up.",
            )
        )
    elif snap.mem_used_pct is not None and snap.mem_used_pct >= 80:
        findings.append(
            SecurityFinding(
                severity="medium",
                category="resources",
                title="Memory usage elevated",
                detail=f"RAM {snap.mem_used_pct}% used",
            )
        )

    for disk in snap.disks:
        pct = disk.get("use_pct")
        mount = disk.get("mount", "?")
        if pct is not None and pct >= 95:
            findings.append(
                SecurityFinding(
                    severity="critical",
                    category="resources",
                    title=f"Disk almost full ({mount})",
                    detail=f"{disk.get('filesystem')} at {pct}% on {mount}",
                    recommendation="Free space or expand volume immediately.",
                )
            )
        elif pct is not None and pct >= 85:
            findings.append(
                SecurityFinding(
                    severity="medium",
                    category="resources",
                    title=f"Disk usage high ({mount})",
                    detail=f"{pct}% used on {mount}",
                )
            )

    if snap.load_1 is not None and snap.cpu_cores:
        ratio = snap.load_1 / max(snap.cpu_cores, 1)
        if ratio >= 2:
            findings.append(
                SecurityFinding(
                    severity="high",
                    category="resources",
                    title="CPU load very high",
                    detail=f"Load {snap.load_1} on {snap.cpu_cores} cores",
                )
            )
        elif ratio >= 1:
            findings.append(
                SecurityFinding(
                    severity="medium",
                    category="resources",
                    title="CPU load elevated",
                    detail=f"Load {snap.load_1} on {snap.cpu_cores} cores",
                )
            )

    fw = (snap.firewall_status or "").lower()
    if not fw or "status: inactive" in fw or fw.strip() == "":
        findings.append(
            SecurityFinding(
                severity="medium",
                category="firewall",
                title="Firewall inactive or unknown",
                detail="ufw/iptables did not report an active ruleset",
                recommendation="Enable ufw or iptables with default-deny inbound policy.",
            )
        )
    elif "status: active" in fw:
        findings.append(
            SecurityFinding(
                severity="info",
                category="firewall",
                title="Firewall active",
                detail=fw.splitlines()[0][:200],
            )
        )

    public_ports = [p for p in snap.ports if p.bind_scope == "public"]
    if not public_ports:
        findings.append(
            SecurityFinding(
                severity="info",
                category="ports",
                title="No public bind ports detected",
                detail="All listening services appear localhost-only or filtered.",
            )
        )
    else:
        seen_titles: set[str] = set()
        for port in public_ports:
            f = _port_finding(port)
            if f and f.title not in seen_titles:
                seen_titles.add(f.title)
                findings.append(f)

    if snap.failed_logins:
        findings.append(
            SecurityFinding(
                severity="high" if len(snap.failed_logins) >= 3 else "medium",
                category="auth",
                title="SSH brute-force attempts detected",
                detail=f"{len(snap.failed_logins)} recent failed logins in auth log sample",
                recommendation="Enable fail2ban, disable password auth, use keys only.",
            )
        )

    # fail2ban presence — use structured probe fields when available
    fb_active = snap.fail2ban_active or bool(snap.fail2ban_jails) or snap.fail2ban_banned_count > 0
    if fb_active or snap.fail2ban_jails:
        detail_parts = []
        if snap.fail2ban_jails:
            detail_parts.append(f"jails: {', '.join(snap.fail2ban_jails)}")
        if snap.fail2ban_banned_count:
            detail_parts.append(f"currently banned: {snap.fail2ban_banned_count}")
        elif snap.fail2ban_recent_ips:
            detail_parts.append(f"recent bans: {', '.join(snap.fail2ban_recent_ips[:3])}")
        findings.append(
            SecurityFinding(
                severity="info",
                category="perimeter",
                title="fail2ban active",
                detail="; ".join(detail_parts) or "Service detected on host",
                recommendation=None,
            )
        )
    elif snap.failed_logins:
        raw = (snap.raw_sections.get("fail2ban") or "") + (snap.raw_sections.get("auth") or "")
        has_fail2ban_log = "fail2ban" in raw.lower() or bool(snap.raw_sections.get("fail2ban", "").strip())
        if not has_fail2ban_log:
            findings.append(
                SecurityFinding(
                    severity="high",
                    category="perimeter",
                    title="fail2ban not detected under active attack",
                    detail="SSH brute-force in logs but no fail2ban activity found",
                    recommendation="Install and enable fail2ban for sshd jail.",
                )
            )

    # SMTP public (common misconfig)
    smtp_public = [p for p in snap.ports if p.bind_scope == "public" and p.port == 25]
    if smtp_public:
        findings.append(
            SecurityFinding(
                severity="medium",
                category="perimeter",
                title="SMTP port 25 publicly exposed",
                detail="Open relay risk if misconfigured",
                recommendation="Block port 25 inbound unless running a mail server; use provider SMTP.",
            )
        )

    root_login = snap.sshd_config.get("PermitRootLogin", "").lower()
    if root_login in ("yes", "without-password", "prohibit-password"):
        sev = "medium" if root_login == "yes" else "low"
        findings.append(
            SecurityFinding(
                severity=sev,
                category="ssh",
                title=f"Root login: {root_login}",
                detail="PermitRootLogin from sshd_config",
                recommendation="Set PermitRootLogin no; use sudo for admin tasks.",
            )
        )

    pwd_auth = snap.sshd_config.get("PasswordAuthentication", "").lower()
    if pwd_auth == "yes":
        findings.append(
            SecurityFinding(
                severity="high",
                category="ssh",
                title="Password authentication enabled",
                detail="PasswordAuthentication yes in sshd_config",
                recommendation="Disable passwords; use SSH keys only.",
            )
        )

    findings = _consolidate_disk_findings(findings)
    sev_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
    findings.sort(key=lambda f: (sev_order.get(f.severity, 9), f.category, f.title))
    return findings
