from __future__ import annotations

import re

from .config import ServerConfig
from .remote_ops import op_discover_nginx_logs, run_server_op


def _nginx_get(server: ServerConfig, key: str, default=None):
    """Read nginx config fields safely (handles cached dataclass instances from older runs)."""
    return getattr(server.nginx, key, default)


def discover_access_logs(server: ServerConfig) -> list[str]:
    out = run_server_op(server, op_discover_nginx_logs())
    paths: list[str] = []
    for ln in out.splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("# STDERR:"):
            continue
        if ln in paths:
            continue
        paths.append(ln)
    return paths


def resolve_log_paths(server: ServerConfig) -> list[str]:
    explicit = list(_nginx_get(server, "access_log_paths") or [])
    auto_discover = bool(_nginx_get(server, "auto_discover_logs", True))
    if not auto_discover:
        return explicit

    discovered: list[str] = []
    if auto_discover:
        try:
            discovered = discover_access_logs(server)
        except Exception:
            discovered = []

    merged: list[str] = []
    for p in explicit + discovered:
        if p and p not in merged:
            merged.append(p)

    default_path = _nginx_get(server, "access_log_path", "/var/log/nginx/access.log")
    if not merged and default_path:
        merged = [default_path]

    # Keep only plausible nginx access logs.
    out: list[str] = []
    for p in merged:
        if "access" not in p.lower():
            continue
        if p.endswith(".gz"):
            continue
        out.append(p)
    return out or ([default_path] if default_path else [])


def host_from_log_path(log_path: str) -> str | None:
    # /var/log/nginx/lottery.modelmarket.dev.access.log -> lottery.modelmarket.dev
    m = re.search(r"/([^/]+)\.access\.log$", log_path)
    if not m:
        return None
    name = m.group(1)
    if name in ("access", "nginx"):
        return None
    return name.replace("_", ".")
