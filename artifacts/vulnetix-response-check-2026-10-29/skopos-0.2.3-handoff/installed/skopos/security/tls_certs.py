"""TLS certificate discovery and expiry monitoring."""

from __future__ import annotations

import ipaddress
import re
import socket
import ssl
from dataclasses import dataclass
from datetime import datetime, timezone

from ..config import ServerConfig
from ..db import now_utc_iso
from ..db_connection import DbConnection
from .audit import SecurityFinding
from .probe import ServerSnapshot
from .store import upsert_tls_certificates

_CERTBOT_DOMAIN_RE = re.compile(r"^\s*Domains:\s*(.+)$", re.IGNORECASE)
_CERTBOT_EXPIRY_RE = re.compile(
    r"^\s*Expiry Date:\s*(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}[^(\n]*)\s*\(VALID:\s*(\d+)\s*days\)",
    re.IGNORECASE,
)
_HOST_RE = re.compile(
    r"^(?=.{1,253}$)(?!-)[a-z0-9-]{1,63}(?<!-)(\.(?!-)[a-z0-9-]{1,63}(?<!-))*\.[a-z]{2,63}$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class TlsCertRecord:
    domain: str
    server_name: str | None
    port: int
    issuer: str | None
    subject: str | None
    sans: tuple[str, ...]
    not_before_utc: str | None
    not_after_utc: str | None
    days_remaining: int | None
    status: str  # ok | warn | critical | expired | error
    error: str | None
    source: str
    checked_at_utc: str


def _utc_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _parse_openssl_date(value: str) -> datetime | None:
    raw = value.strip()
    for fmt in ("%b %d %H:%M:%S %Y %Z", "%Y-%m-%d %H:%M:%S%z", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            dt = datetime.strptime(raw.replace("GMT", "UTC"), fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except ValueError:
            continue
    return None


def is_public_hostname(host: str | None) -> bool:
    if not host:
        return False
    h = host.strip().lower().rstrip(".")
    if not h or h in ("-", "localhost", "_"):
        return False
    if h.startswith("www.") and len(h) > 4:
        h = h[4:]
    try:
        ipaddress.ip_address(h.strip("[]"))
        return False
    except ValueError:
        pass
    return bool(_HOST_RE.match(h))


def normalize_domain(host: str) -> str:
    h = host.strip().lower().rstrip(".")
    if h.startswith("www."):
        return h[4:]
    return h


def parse_certbot_section(text: str) -> list[tuple[str, int | None]]:
    """Return (domain, days_remaining_hint) from certbot certificates output."""
    if not text.strip():
        return []
    out: list[tuple[str, int | None]] = []
    pending_days: int | None = None
    for line in text.splitlines():
        expiry = _CERTBOT_EXPIRY_RE.match(line)
        if expiry:
            try:
                pending_days = int(expiry.group(2))
            except ValueError:
                pending_days = None
            continue
        dom = _CERTBOT_DOMAIN_RE.match(line)
        if not dom:
            continue
        for token in re.split(r"\s+", dom.group(1).strip()):
            if is_public_hostname(token):
                out.append((normalize_domain(token), pending_days))
        pending_days = None
    return out


def discover_domains(
    con: DbConnection,
    server: ServerConfig,
    snap: ServerSnapshot,
    *,
    log_days: int = 45,
) -> dict[str, str]:
    """Map normalized domain -> discovery source label."""
    found: dict[str, str] = {}
    since = (datetime.now(tz=timezone.utc).replace(microsecond=0)).isoformat()
    _ = since  # cutoff computed in SQL via relative days if needed

    rows = con.execute(
        """
        SELECT DISTINCT host FROM http_requests
        WHERE server_name = ?
          AND host IS NOT NULL AND TRIM(host) != ''
          AND ts_utc >= datetime('now', ?)
        LIMIT 200
        """,
        (server.name, f"-{int(log_days)} days"),
    ).fetchall()
    if con.backend == "postgresql":
        rows = con.execute(
            """
            SELECT DISTINCT host FROM http_requests
            WHERE server_name = ?
              AND host IS NOT NULL AND TRIM(host) != ''
              AND ts_utc >= (NOW() AT TIME ZONE 'UTC' - (? || ' days')::interval)::text
            LIMIT 200
            """,
            (server.name, str(log_days)),
        ).fetchall()

    for row in rows:
        host = row["host"] if isinstance(row, dict) else row[0]
        if is_public_hostname(host):
            found[normalize_domain(str(host))] = "access_logs"

    certbot = (snap.raw_sections or {}).get("certbot", "")
    for domain, _days in parse_certbot_section(certbot):
        found.setdefault(domain, "certbot")

    # Public 443 often implies HTTPS vhost — check server hostname if it looks like a domain
    if is_public_hostname(server.ssh.host):
        found.setdefault(normalize_domain(server.ssh.host), "server_host")

    return found


def _issuer_name(cert: dict) -> str | None:
    issuer = cert.get("issuer")
    if not isinstance(issuer, tuple):
        return None
    parts = []
    for item in issuer:
        if isinstance(item, tuple) and len(item) == 2 and item[0] == "organizationName":
            parts.append(str(item[1]))
    if parts:
        return ", ".join(parts)
    for item in issuer:
        if isinstance(item, tuple) and len(item) == 2:
            return str(item[1])
    return None


def _subject_cn(cert: dict) -> str | None:
    subject = cert.get("subject")
    if not isinstance(subject, tuple):
        return None
    for item in subject:
        if isinstance(item, tuple) and len(item) == 2 and item[0] == "commonName":
            return str(item[1])
    return None


def _collect_sans(cert: dict) -> tuple[str, ...]:
    sans: list[str] = []
    for kind, value in cert.get("subjectAltName") or ():
        if kind == "DNS" and value:
            v = str(value).strip().lower()
            if is_public_hostname(v) or v.startswith("*."):
                sans.append(v)
    if not sans:
        cn = _subject_cn(cert)
        if cn:
            sans.append(cn.lower())
    return tuple(dict.fromkeys(sans))


def _status_for_days(days: int | None) -> str:
    if days is None:
        return "error"
    if days < 0:
        return "expired"
    if days < 7:
        return "critical"
    if days < 30:
        return "warn"
    return "ok"


def check_tls_cert(domain: str, *, port: int = 443, timeout: float = 8.0) -> TlsCertRecord:
    checked = now_utc_iso()
    ctx = ssl.create_default_context()
    try:
        with socket.create_connection((domain, port), timeout=timeout) as sock:
            with ctx.wrap_socket(sock, server_hostname=domain) as ssock:
                cert = ssock.getpeercert()
    except Exception as exc:
        return TlsCertRecord(
            domain=domain,
            server_name=None,
            port=port,
            issuer=None,
            subject=None,
            sans=(),
            not_before_utc=None,
            not_after_utc=None,
            days_remaining=None,
            status="error",
            error=str(exc)[:240],
            source="tls_probe",
            checked_at_utc=checked,
        )

    not_before = _parse_openssl_date(str(cert.get("notBefore") or ""))
    not_after = _parse_openssl_date(str(cert.get("notAfter") or ""))
    days_remaining: int | None = None
    if not_after:
        days_remaining = int((not_after - datetime.now(tz=timezone.utc)).total_seconds() // 86400)

    return TlsCertRecord(
        domain=domain,
        server_name=None,
        port=port,
        issuer=_issuer_name(cert),
        subject=_subject_cn(cert),
        sans=_collect_sans(cert),
        not_before_utc=_utc_iso(not_before) if not_before else None,
        not_after_utc=_utc_iso(not_after) if not_after else None,
        days_remaining=days_remaining,
        status=_status_for_days(days_remaining),
        error=None,
        source="tls_probe",
        checked_at_utc=checked,
    )


def finding_from_cert(rec: TlsCertRecord) -> SecurityFinding | None:
    if rec.status == "ok":
        return SecurityFinding(
            severity="info",
            category="tls",
            title=f"TLS certificate OK: {rec.domain}",
            detail=f"Valid until {rec.not_after_utc or '?'} ({rec.days_remaining} days)",
            recommendation=None,
        )
    if rec.status == "warn":
        return SecurityFinding(
            severity="medium",
            category="tls",
            title=f"TLS certificate expiring soon: {rec.domain}",
            detail=f"Expires in {rec.days_remaining} days ({rec.not_after_utc})",
            recommendation="Renew Let's Encrypt / ACME cert before expiry.",
        )
    if rec.status == "critical":
        return SecurityFinding(
            severity="high",
            category="tls",
            title=f"TLS certificate expires imminently: {rec.domain}",
            detail=f"Expires in {rec.days_remaining} days ({rec.not_after_utc})",
            recommendation="Renew certificate immediately.",
        )
    if rec.status == "expired":
        return SecurityFinding(
            severity="critical",
            category="tls",
            title=f"TLS certificate expired: {rec.domain}",
            detail=f"Expired on {rec.not_after_utc}",
            recommendation="Renew certificate and reload nginx/apache.",
        )
    return SecurityFinding(
        severity="medium",
        category="tls",
        title=f"TLS check failed: {rec.domain}",
        detail=rec.error or "Could not retrieve certificate",
        recommendation="Verify DNS, port 443, and certificate installation on the server.",
    )


def check_server_certificates(
    con: DbConnection,
    server: ServerConfig,
    snap: ServerSnapshot,
) -> tuple[list[SecurityFinding], int]:
    domains = discover_domains(con, server, snap)
    if not domains:
        return [], 0

    records: list[TlsCertRecord] = []
    findings: list[SecurityFinding] = []
    for domain, source in sorted(domains.items()):
        rec = check_tls_cert(domain)
        rec = TlsCertRecord(
            domain=rec.domain,
            server_name=server.name,
            port=rec.port,
            issuer=rec.issuer,
            subject=rec.subject,
            sans=rec.sans,
            not_before_utc=rec.not_before_utc,
            not_after_utc=rec.not_after_utc,
            days_remaining=rec.days_remaining,
            status=rec.status,
            error=rec.error,
            source=source if rec.status != "error" else f"{source}+probe_error",
            checked_at_utc=rec.checked_at_utc,
        )
        records.append(rec)
        finding = finding_from_cert(rec)
        if finding and finding.severity != "info":
            findings.append(finding)
        elif finding and rec.status == "ok":
            findings.append(finding)

    upsert_tls_certificates(con, records)
    return findings, len(records)
