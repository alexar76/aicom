from __future__ import annotations

import re
from ..db import DbConnection
from ..db_dialect import cutoff_iso
from dataclasses import dataclass

from ..geoip import GeoIPResolver, is_private_ip
from .port_knocks import PortKnockEvent

# Suspicious HTTP paths treated as web port probes (443/80)
_WEB_PROBE_PATH = re.compile(
    r"(?i)(/wp-|/\.env|/\.git|/phpmyadmin|/admin|/xmlrpc|/cgi-bin|/shell|/boaform|/SDK/)"
)


@dataclass(frozen=True)
class EnrichedKnock:
    remote_addr: str
    dest_port: int | None
    src_port: int | None
    event_type: str
    source_log: str
    username: str | None
    ts_utc: str | None
    country_code: str | None
    country_name: str | None
    actor_class: str
    actor_label: str
    threat_score: int  # 0-100
    line_raw: str


def classify_actor(ip: str, events: list[PortKnockEvent]) -> tuple[str, str, int]:
    """Return actor_class, actor_label, threat_score."""
    n = len(events)
    types = {e.event_type for e in events}
    ports = {e.dest_port for e in events if e.dest_port}
    users = {e.username for e in events if e.username}

    if "fail2ban_ban" in types:
        return "banned_attacker", "Already banned by fail2ban", 90

    ssh_hits = sum(1 for e in events if e.event_type.startswith("ssh_"))
    fw_hits = sum(1 for e in events if e.event_type in ("firewall_block", "kernel_drop"))
    invalid_users = {u for u in users if u and u.lower() not in ("root", "admin")}

    score = min(100, ssh_hits * 8 + fw_hits * 5 + len(ports) * 6)

    if ssh_hits >= 5 or (ssh_hits >= 2 and "ssh_invalid_user" in types):
        label = f"SSH brute-force · {ssh_hits} attempts"
        if invalid_users:
            label += f" · users: {', '.join(list(invalid_users)[:3])}"
        return "ssh_bruteforcer", label, max(score, 75)

    if len(ports) >= 4:
        return "port_scanner", f"Multi-port scan · {len(ports)} ports ({', '.join(str(p) for p in sorted(ports)[:6])})", max(score, 70)

    if fw_hits >= 8:
        return "firewall_prober", f"Repeated firewall blocks · {fw_hits} hits", max(score, 65)

    if n >= 15:
        return "aggressive_scanner", f"High-volume probing · {n} events", max(score, 80)

    if "ssh_invalid_user" in types:
        return "ssh_recon", f"SSH user enumeration · user={next(iter(users), '?')}", max(score, 55)

    if "web_probe" in types:
        return "web_scanner", f"Web vulnerability scan · {n} suspicious requests", max(score, 50)

    if n >= 3:
        return "suspicious", f"Multiple probes · {n} events", max(score, 40)

    if n == 1:
        return "isolated", "Single connection attempt", 15

    return "unknown", f"Probe activity · {n} events", max(score, 25)


def enrich_knocks(
    events: list[PortKnockEvent],
    *,
    geo: GeoIPResolver | None = None,
) -> list[EnrichedKnock]:
    if not events:
        return []

    # Group by IP for classification
    by_ip: dict[str, list[PortKnockEvent]] = {}
    for e in events:
        if is_private_ip(e.remote_addr):
            continue
        by_ip.setdefault(e.remote_addr, []).append(e)

    ip_meta: dict[str, tuple[str, str, int]] = {}
    for ip, group in by_ip.items():
        ip_meta[ip] = classify_actor(ip, group)

    geo_map: dict[str, tuple[str | None, str | None]] = {}
    if geo:
        unique_ips = list(by_ip.keys())
        for ip, info in geo.batch_lookup(unique_ips).items():
            geo_map[ip] = (info.iso_code, info.name)

    out: list[EnrichedKnock] = []
    for e in events:
        if is_private_ip(e.remote_addr):
            continue
        cc, cn = geo_map.get(e.remote_addr, (None, None))
        acl, alabel, score = ip_meta.get(e.remote_addr, ("unknown", "Unknown", 20))
        out.append(
            EnrichedKnock(
                remote_addr=e.remote_addr,
                dest_port=e.dest_port,
                src_port=e.src_port,
                event_type=e.event_type,
                source_log=e.source_log,
                username=e.username,
                ts_utc=e.ts_utc,
                country_code=cc,
                country_name=cn,
                actor_class=acl,
                actor_label=alabel,
                threat_score=score,
                line_raw=e.line_raw,
            )
        )
    return out


def http_probes_from_db(
    con: DbConnection,
    server_name: str,
    *,
    hours: int = 168,
    limit: int = 500,
) -> list[PortKnockEvent]:
    """Derive web port knock events from suspicious HTTP paths in analytics DB."""
    since = cutoff_iso(hours=hours)
    q = """
      SELECT ts_utc, remote_addr, path, status, method, line_raw
      FROM http_requests
      WHERE server_name = ?
        AND remote_addr IS NOT NULL
        AND path IS NOT NULL
        AND (ts_utc IS NULL OR ts_utc >= ?)
      ORDER BY COALESCE(ts_utc, ingested_at_utc) DESC
      LIMIT ?
    """
    try:
        rows = con.execute(q, (server_name, since, limit)).fetchall()
    except Exception:
        return []

    events: list[PortKnockEvent] = []
    seen: set[str] = set()
    for row in rows:
        path = row["path"] or ""
        if not _WEB_PROBE_PATH.search(path):
            continue
        ip = row["remote_addr"]
        if not ip or is_private_ip(str(ip)):
            continue
        # The verbatim line is no longer stored (db.STORE_RAW_LINES), so this
        # summary is now the normal case rather than a fallback. It has to carry
        # the timestamp: the row's identity — here, in the in-batch `seen` set,
        # and in store.record_knock_events' line_sha1 dedup — used to come from
        # the timestamp inside the raw line. Without it fifty probes from one
        # address to /wp-admin collapse into a single event and the actor's
        # `hits` count, which is what the Security page ranks by, drops to one.
        line = row["line_raw"] or (
            f"{row['ts_utc'] or ''} {row['method']} {path} {row['status']} from {ip}".strip()
        )
        if line in seen:
            continue
        seen.add(line)
        port = 443 if path.startswith("/") else 80
        events.append(
            PortKnockEvent(
                remote_addr=str(ip),
                dest_port=port,
                src_port=None,
                event_type="web_probe",
                source_log="http_requests",
                username=None,
                ts_utc=row["ts_utc"],
                line_raw=line[:2000],
            )
        )
    return events
