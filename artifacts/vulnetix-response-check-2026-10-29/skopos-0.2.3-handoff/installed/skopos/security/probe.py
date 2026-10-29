from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field

from ..config import ServerConfig
from ..remote_ops import op_probe, run_server_op
from .docker_insights import parse_docker_section
from .fail2ban_status import parse_fail2ban_section


@dataclass
class PortInfo:
    proto: str
    address: str
    port: int
    process: str | None = None
    bind_scope: str = "unknown"  # public | localhost | all


@dataclass
class ServerSnapshot:
    server_name: str
    host: str
    scanned_at_utc: str
    hostname: str | None = None
    kernel: str | None = None
    uptime: str | None = None
    cpu_cores: int | None = None
    cpu_idle_pct: float | None = None
    load_1: float | None = None
    load_5: float | None = None
    load_15: float | None = None
    mem_total_mb: int | None = None
    mem_used_mb: int | None = None
    mem_used_pct: float | None = None
    disks: list[dict] = field(default_factory=list)
    net_rx_bytes: int | None = None
    net_tx_bytes: int | None = None
    ports: list[PortInfo] = field(default_factory=list)
    firewall_status: str | None = None
    failed_logins: list[str] = field(default_factory=list)
    recent_logins: list[str] = field(default_factory=list)
    docker_containers: list[dict] = field(default_factory=list)
    sshd_config: dict[str, str] = field(default_factory=dict)
    fail2ban_active: bool = False
    fail2ban_jails: list[str] = field(default_factory=list)
    fail2ban_banned_count: int = 0
    fail2ban_recent_ips: list[str] = field(default_factory=list)
    raw_sections: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["ports"] = [asdict(p) for p in self.ports]
        return d

    @classmethod
    def from_dict(cls, data: dict) -> ServerSnapshot:
        ports = [PortInfo(**p) for p in data.get("ports") or []]
        fields = {k: v for k, v in {**data, "ports": ports}.items() if k in cls.__dataclass_fields__}
        return cls(**fields)


def _split_sections(text: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    current = "_head"
    buf: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("===") and stripped.endswith("==="):
            sections[current] = "\n".join(buf).strip()
            current = stripped.strip("=").strip().lower()
            buf = []
        elif line.startswith("# STDERR:"):
            continue
        else:
            buf.append(line)
    sections[current] = "\n".join(buf).strip()
    return sections


def _parse_cpu_idle(section: str) -> float | None:
    for line in section.splitlines():
        if line.startswith("cpu "):
            parts = [int(x) for x in line.split()[1:]]
            if len(parts) >= 4:
                idle = parts[3] + (parts[4] if len(parts) > 4 else 0)
                total = sum(parts)
                return round(idle / total * 100, 1) if total else None
    return None


def _parse_mem(section: str) -> tuple[int | None, int | None, float | None]:
    for line in section.splitlines():
        if line.lower().startswith("mem:"):
            parts = line.split()
            if len(parts) >= 3:
                total, used = int(parts[1]), int(parts[2])
                pct = round(used / total * 100, 1) if total else None
                return total, used, pct
    return None, None, None


def _parse_disks(section: str) -> list[dict]:
    rows: list[dict] = []
    lines = section.splitlines()
    if len(lines) < 2:
        return rows
    for line in lines[1:]:
        parts = line.split()
        if len(parts) < 6:
            continue
        use_pct = parts[4].rstrip("%")
        try:
            pct = float(use_pct)
        except ValueError:
            pct = None
        rows.append(
            {
                "filesystem": parts[0],
                "size": parts[1],
                "used": parts[2],
                "avail": parts[3],
                "use_pct": pct,
                "mount": parts[5],
            }
        )
    return rows


def _parse_net(section: str) -> tuple[int | None, int | None]:
    rx = tx = 0
    found = False
    for line in section.splitlines()[2:]:
        if ":" not in line:
            continue
        name, stats = line.split(":", 1)
        if name.strip() in ("lo", "Lo"):
            continue
        parts = stats.split()
        if len(parts) >= 16:
            rx += int(parts[0])
            tx += int(parts[8])
            found = True
    return (rx, tx) if found else (None, None)


_ADDR_PORT_RE = re.compile(r"(?P<host>[\d.a-f:*\[\]]+):(?P<port>\d+)")


def _bind_scope(addr: str) -> str:
    a = addr.rsplit(":", 1)[0]
    if a in ("0.0.0.0", "[::]", "*"):
        return "public"
    if a.startswith("127.") or a == "::1" or a.startswith("[::1]"):
        return "localhost"
    return "other"


def _parse_ports(section: str) -> list[PortInfo]:
    ports: list[PortInfo] = []
    seen: set[tuple[str, str, int]] = set()
    for line in section.splitlines():
        line = line.strip()
        upper = line.upper()
        if not line or upper.startswith("STATE") or "LISTEN" not in upper:
            continue
        parts = line.split()
        proto = parts[0].lower() if parts else "tcp"
        proc = parts[-1] if parts and "users:" in parts[-1] else None
        local: str | None = None
        try:
            idx = next(i for i, p in enumerate(parts) if p.upper() == "LISTEN")
            if idx + 3 < len(parts):
                local = parts[idx + 3]
        except StopIteration:
            pass
        if not local or ":" not in local:
            m = _ADDR_PORT_RE.search(line)
            local = f"{m.group('host')}:{m.group('port')}" if m else None
        if not local or ":" not in local:
            continue
        host_part, port_s = local.rsplit(":", 1)
        port_s = port_s.split("%")[0]
        try:
            port = int(port_s)
        except ValueError:
            continue
        key = (proto, host_part, port)
        if key in seen:
            continue
        seen.add(key)
        ports.append(
            PortInfo(
                proto=proto,
                address=host_part,
                port=port,
                process=proc,
                bind_scope=_bind_scope(local),
            )
        )
    return sorted(ports, key=lambda p: (p.bind_scope != "public", p.port))


def _parse_docker(section: str) -> list[dict]:
    return parse_docker_section(section)


def _parse_sshd(section: str) -> dict[str, str]:
    cfg: dict[str, str] = {}
    for line in section.splitlines():
        if line.startswith("#") or " " not in line:
            continue
        k, v = line.split(None, 1)
        cfg[k] = v.strip()
    return cfg


def snapshot_from_probe_output(
    raw: str, *, server_name: str, host: str, scanned_at_utc: str
) -> ServerSnapshot:
    """Parse raw probe output into a snapshot.

    Split out from :func:`probe_server` so the same parser serves both transports:
    SSH pulls the output, a push node produces it locally and ships it.
    """
    sections = _split_sections(raw)
    meta_lines = [ln for ln in sections.get("meta", "").splitlines() if ln.strip()]
    snap = ServerSnapshot(
        server_name=server_name,
        host=host,
        scanned_at_utc=scanned_at_utc,
        hostname=meta_lines[0] if meta_lines else None,
        kernel=meta_lines[1] if len(meta_lines) > 1 else None,
        uptime=meta_lines[2] if len(meta_lines) > 2 else None,
        raw_sections={k: v[:4000] for k, v in sections.items()},
    )
    cpu_sec = sections.get("cpu", "")
    for line in cpu_sec.splitlines():
        if line.strip().isdigit():
            snap.cpu_cores = int(line.strip())
            break
    snap.cpu_idle_pct = _parse_cpu_idle(cpu_sec)
    snap.mem_total_mb, snap.mem_used_mb, snap.mem_used_pct = _parse_mem(sections.get("mem", ""))
    snap.disks = _parse_disks(sections.get("disk", ""))
    snap.net_rx_bytes, snap.net_tx_bytes = _parse_net(sections.get("net", ""))
    load = sections.get("load", "").split()
    if len(load) >= 3:
        try:
            snap.load_1, snap.load_5, snap.load_15 = float(load[0]), float(load[1]), float(load[2])
        except ValueError:
            pass
    snap.ports = _parse_ports(sections.get("ports", ""))
    snap.firewall_status = sections.get("firewall", "")[:2000] or None
    auth = sections.get("auth", "")
    snap.recent_logins = [ln for ln in auth.splitlines() if ln.strip() and "Failed password" not in ln][:8]
    snap.failed_logins = [ln for ln in auth.splitlines() if "Failed password" in ln][:8]
    snap.docker_containers = _parse_docker(sections.get("docker", ""))
    snap.sshd_config = _parse_sshd(sections.get("sshd", ""))
    fb = parse_fail2ban_section(sections.get("fail2ban", ""))
    snap.fail2ban_active = fb.is_protecting
    snap.fail2ban_jails = list(fb.jails)
    snap.fail2ban_banned_count = fb.currently_banned
    snap.fail2ban_recent_ips = list(fb.recent_ban_ips)
    return snap


def probe_server(server: ServerConfig, *, scanned_at_utc: str) -> ServerSnapshot:
    raw = run_server_op(server, op_probe())
    return snapshot_from_probe_output(
        raw,
        server_name=server.name,
        host=server.ssh.host,
        scanned_at_utc=scanned_at_utc,
    )


def snapshot_json(snap: ServerSnapshot) -> str:
    return json.dumps(snap.to_dict(), ensure_ascii=False)
