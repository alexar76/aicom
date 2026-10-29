"""Parse fail2ban service state from security probe output."""

from __future__ import annotations

import re
from dataclasses import dataclass

_IP_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")


@dataclass(frozen=True)
class Fail2banStatus:
    service_active: bool
    jails: tuple[str, ...]
    currently_banned: int
    recent_ban_ips: tuple[str, ...]
    sshd_jail: bool
    summary: str

    @property
    def is_protecting(self) -> bool:
        return self.service_active and (self.sshd_jail or self.currently_banned > 0 or bool(self.recent_ban_ips))


def _service_active(raw: str) -> bool:
    match = re.search(r"__SERVICE__\s*\n(\S+)", raw, re.IGNORECASE)
    if match:
        return match.group(1).strip().lower() in ("active", "running")
    for line in raw.splitlines():
        token = line.strip().lower()
        if token in ("active", "running"):
            return True
        if token in ("inactive", "failed", "dead"):
            return False
    return bool(re.search(r"number of jail", raw, re.IGNORECASE))


def parse_fail2ban_section(text: str) -> Fail2banStatus:
    """Best-effort parse of ===FAIL2BAN=== probe section."""
    raw = (text or "").strip()
    if not raw:
        return Fail2banStatus(
            service_active=False,
            jails=(),
            currently_banned=0,
            recent_ban_ips=(),
            sshd_jail=False,
            summary="not detected",
        )

    service_active = _service_active(raw)

    # fail2ban-client status: "Status for the jail: sshd" or global "Jail list: sshd, nginx"
    jails: list[str] = []
    jail_match = re.search(r"jail list:\s*(.+)", raw, re.IGNORECASE)
    if jail_match:
        jails = [j.strip() for j in re.split(r"[,\s]+", jail_match.group(1).strip()) if j.strip()]

    banned = 0
    ban_match = re.search(r"currently banned:\s*(\d+)", raw, re.IGNORECASE)
    if ban_match:
        banned = int(ban_match.group(1))

    recent: list[str] = []
    for line in raw.splitlines():
        if "ban" not in line.lower():
            continue
        for ip in _IP_RE.findall(line):
            if ip not in recent:
                recent.append(ip)
    recent = recent[-8:]

    sshd_jail = any(j.lower() == "sshd" or j.lower().startswith("sshd-") for j in jails)
    if not sshd_jail and re.search(r"status for the jail:\s*['\"]?sshd", raw, re.IGNORECASE):
        sshd_jail = True

    if service_active:
        parts = ["service active"]
        if jails:
            parts.append(f"jails: {', '.join(jails)}")
        if banned:
            parts.append(f"currently banned: {banned}")
        elif recent:
            parts.append(f"recent bans in log: {len(recent)}")
        summary = "; ".join(parts)
    elif "fail2ban" in raw.lower() or recent:
        summary = "installed but service not active"
    else:
        summary = "not detected"

    return Fail2banStatus(
        service_active=service_active,
        jails=tuple(jails),
        currently_banned=banned,
        recent_ban_ips=tuple(recent),
        sshd_jail=sshd_jail,
        summary=summary,
    )


def format_fail2ban_line(server_name: str, status: Fail2banStatus) -> str:
    if status.is_protecting:
        extra = ""
        if status.recent_ban_ips:
            extra = f"; recent bans: {', '.join(status.recent_ban_ips[:3])}"
        elif status.currently_banned:
            extra = f"; {status.currently_banned} IP(s) banned now"
        return f"- {server_name}: fail2ban ACTIVE ({status.summary}){extra}"
    if status.service_active:
        return f"- {server_name}: fail2ban running but sshd jail unclear ({status.summary})"
    return f"- {server_name}: fail2ban NOT active ({status.summary})"
