"""Docker container inventory, resource usage, and role inference for AI context."""

from __future__ import annotations

import re
from typing import Any

_PS_MARKER = "__PS__"
_SKOPOS_MARKER = "__SKOPOS__"
_META_MARKER = "__META__"

_ROLE_HINTS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"nginx", re.I), "Reverse proxy / HTTP front-end"),
    (re.compile(r"caddy", re.I), "HTTPS reverse proxy"),
    (re.compile(r"traefik", re.I), "Ingress / load balancer"),
    (re.compile(r"postgres|postgresql", re.I), "PostgreSQL database"),
    (re.compile(r"redis", re.I), "Redis cache / message broker"),
    (re.compile(r"mongo", re.I), "MongoDB database"),
    (re.compile(r"mysql|mariadb", re.I), "MySQL/MariaDB database"),
    (re.compile(r"grafana", re.I), "Grafana monitoring dashboards"),
    (re.compile(r"prometheus", re.I), "Prometheus metrics"),
    (re.compile(r"streamlit", re.I), "Streamlit analytics UI"),
    (re.compile(r"fastapi|uvicorn|gunicorn", re.I), "Python HTTP API"),
    (re.compile(r"node|npm", re.I), "Node.js application"),
    (re.compile(r"python", re.I), "Python application"),
    (re.compile(r"docker\.io/library/alpine|alpine:", re.I), "Minimal base / utility container"),
    (re.compile(r"certbot|letsencrypt", re.I), "TLS certificate automation"),
    (re.compile(r"elasticsearch|opensearch", re.I), "Search / log analytics engine"),
    (re.compile(r"kibana", re.I), "Kibana log UI"),
    (re.compile(r"minio", re.I), "S3-compatible object storage"),
    (re.compile(r"rabbitmq", re.I), "RabbitMQ message queue"),
    (re.compile(r"kafka", re.I), "Kafka event streaming"),
    (re.compile(r"vault", re.I), "HashiCorp Vault secrets"),
    (re.compile(r"argus", re.I), "Argus arena service"),
    (re.compile(r"metis", re.I), "Metis oracle / API stack"),
    (re.compile(r"oracle", re.I), "Oracle inference service"),
    (re.compile(r"alien|monitor", re.I), "Observability / monitoring"),
    (re.compile(r"stats|aicom-skopos|skopos", re.I), "SKOPOS analytics dashboard"),
    (re.compile(r"factory|magic-ai", re.I), "AI Factory application"),
    (re.compile(r"pulse", re.I), "Pulse service"),
    (re.compile(r"landing", re.I), "Landing / marketing site"),
    (re.compile(r"hub", re.I), "Hub / federation gateway"),
]


def _clean_name(name: str) -> str:
    return name.lstrip("/").strip()


def infer_container_role(*, name: str, image: str, compose_service: str | None = None) -> str:
    haystack = " ".join(filter(None, [name, image, compose_service or ""]))
    for pattern, role in _ROLE_HINTS:
        if pattern.search(haystack):
            return role
    if compose_service:
        return f"Compose service «{compose_service}»"
    base = image.split(":")[0].split("/")[-1]
    return f"Container running {base}"


def infer_container_summary(
    *,
    name: str,
    image: str,
    role: str,
    ports: str,
    compose_project: str | None,
    compose_service: str | None,
    state: str | None,
) -> str:
    bits: list[str] = [role]
    if compose_project and compose_service:
        bits.append(f"stack {compose_project}/{compose_service}")
    elif compose_service:
        bits.append(f"service {compose_service}")
    if ports:
        bits.append(f"ports {ports}")
    if state and state != "running":
        bits.append(f"state={state}")
    label = name or image
    return f"{label}: " + "; ".join(bits)


def _split_docker_section(section: str) -> tuple[str, str, str]:
    if _PS_MARKER not in section:
        return section, "", ""
    ps, rest = section.split(_PS_MARKER, 1)[1], ""
    stats_text, meta_text = "", ""
    if _SKOPOS_MARKER in ps:
        ps, rest = ps.split(_SKOPOS_MARKER, 1)
        if _META_MARKER in rest:
            stats_text, meta_text = rest.split(_META_MARKER, 1)
        else:
            stats_text = rest
    elif _META_MARKER in ps:
        ps, meta_text = ps.split(_META_MARKER, 1)
    return ps.strip(), stats_text.strip(), meta_text.strip()


def _parse_ps_lines(ps_text: str) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for line in ps_text.splitlines():
        if "|" not in line:
            continue
        parts = (line.split("|") + [""] * 5)[:5]
        name, image, status, state, ports = [p.strip() for p in parts]
        name = _clean_name(name)
        if not name:
            continue
        rows[name] = {
            "name": name,
            "image": image,
            "status": status,
            "state": state or "unknown",
            "ports": ports,
        }
    return rows


def _parse_stats_lines(stats_text: str) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for line in stats_text.splitlines():
        if "|" not in line:
            continue
        parts = (line.split("|") + [""] * 7)[:7]
        name, cpu, mem_usage, mem_pct, net_io, block_io, pids = [p.strip() for p in parts]
        name = _clean_name(name)
        if not name:
            continue
        out[name] = {
            "cpu_percent": cpu,
            "mem_usage": mem_usage,
            "mem_percent": mem_pct,
            "net_io": net_io,
            "block_io": block_io,
            "pids": pids,
        }
    return out


def _parse_meta_lines(meta_text: str) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for line in meta_text.splitlines():
        if "|" not in line:
            continue
        parts = (line.split("|") + [""] * 4)[:4]
        name, compose_service, compose_project, hostname = [p.strip() for p in parts]
        name = _clean_name(name)
        if not name:
            continue
        out[name] = {
            "compose_service": compose_service,
            "compose_project": compose_project,
            "hostname": hostname,
        }
    return out


def _enrich_row(row: dict[str, Any]) -> dict[str, Any]:
    role = infer_container_role(
        name=row.get("name", ""),
        image=row.get("image", ""),
        compose_service=row.get("compose_service"),
    )
    row["role"] = role
    row["summary"] = infer_container_summary(
        name=row.get("name", ""),
        image=row.get("image", ""),
        role=role,
        ports=row.get("ports", ""),
        compose_project=row.get("compose_project"),
        compose_service=row.get("compose_service"),
        state=row.get("state"),
    )
    return row


def parse_docker_section(section: str) -> list[dict[str, Any]]:
    """Parse extended docker probe output into enriched container records."""
    ps_text, stats_text, meta_text = _split_docker_section(section)
    if not ps_text and "|" in section:
        # Legacy: name|image|ports only
        out: list[dict[str, Any]] = []
        for line in section.splitlines():
            if "|" not in line:
                continue
            name, image, ports = (line.split("|") + ["", ""])[:3]
            name = _clean_name(name.strip())
            if not name:
                continue
            row = {
                "name": name,
                "image": image.strip(),
                "ports": ports.strip(),
                "state": "unknown",
                "status": "",
            }
            out.append(_enrich_row(row))
        return out

    rows = _parse_ps_lines(ps_text)
    stats = _parse_stats_lines(stats_text)
    meta = _parse_meta_lines(meta_text)

    all_names = sorted(set(rows) | set(stats) | set(meta))
    out: list[dict[str, Any]] = []
    for name in all_names:
        row: dict[str, Any] = {
            "name": name,
            "image": "",
            "status": "",
            "state": "unknown",
            "ports": "",
        }
        row.update(rows.get(name, {}))
        row.update({k: v for k, v in stats.get(name, {}).items() if v})
        row.update({k: v for k, v in meta.get(name, {}).items() if v})
        out.append(_enrich_row(row))

    out.sort(key=lambda r: (r.get("state") != "running", r.get("name", "")))
    return out


def format_docker_section(containers: list[dict[str, Any]], *, server_name: str | None = None) -> str:
    if not containers:
        return ""
    header = f"### Docker workloads"
    if server_name:
        header += f" — {server_name}"
    lines = [header + "\n"]
    running = [c for c in containers if c.get("state") == "running"]
    other = [c for c in containers if c.get("state") != "running"]
    lines.append(f"Running: {len(running)} · Total listed: {len(containers)}\n\n")

    for c in running + other:
        name = c.get("name", "?")
        state = c.get("state", "?")
        icon = "🟢" if state == "running" else "⚪"
        lines.append(f"{icon} **{name}** — {c.get('role', 'Unknown role')}\n")
        lines.append(f"   - Image: `{c.get('image') or '—'}`\n")
        if c.get("summary"):
            lines.append(f"   - Summary: {c['summary']}\n")
        if c.get("ports"):
            lines.append(f"   - Ports: {c['ports']}\n")
        usage_bits = []
        if c.get("cpu_percent"):
            usage_bits.append(f"CPU {c['cpu_percent']}")
        if c.get("mem_usage"):
            usage_bits.append(f"RAM {c['mem_usage']} ({c.get('mem_percent', '?')})")
        if c.get("net_io"):
            usage_bits.append(f"Net {c['net_io']}")
        if c.get("pids"):
            usage_bits.append(f"PIDs {c['pids']}")
        if usage_bits:
            lines.append(f"   - Usage: {' · '.join(usage_bits)}\n")
        if c.get("compose_project") or c.get("compose_service"):
            lines.append(
                f"   - Compose: {c.get('compose_project') or '—'}/{c.get('compose_service') or '—'}\n"
            )
        if state != "running" and c.get("status"):
            lines.append(f"   - Status: {c['status']}\n")
        lines.append("\n")
    return "".join(lines)
