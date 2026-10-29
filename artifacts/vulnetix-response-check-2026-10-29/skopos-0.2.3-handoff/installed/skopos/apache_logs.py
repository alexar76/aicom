"""Discover Apache access logs on remote hosts (Debian/Ubuntu + RHEL paths)."""

from __future__ import annotations

import re

from .config import ServerConfig
from .remote_ops import op_discover_apache_logs, run_server_op


def _apache_get(server: ServerConfig, key: str, default=None):
    apache = getattr(server, "apache", None)
    if apache is None:
        return default
    return getattr(apache, key, default)


def discover_access_logs(server: ServerConfig) -> list[str]:
    out = run_server_op(server, op_discover_apache_logs())
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
    if not bool(_apache_get(server, "enabled", False)):
        return []

    explicit = list(_apache_get(server, "access_log_paths") or [])
    auto_discover = bool(_apache_get(server, "auto_discover_logs", True))
    if explicit and not auto_discover:
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

    default_path = _apache_get(server, "access_log_path", "/var/log/apache2/access.log")
    if not merged and default_path:
        merged = [default_path]

    # Every path here is authoritative (explicit config, default, or a CustomLog/
    # TransferLog directive — never an ErrorLog), so we do NOT drop by filename:
    # Apache vhosts routinely log to files without "access" in the name. Only skip
    # rotated .gz archives.
    out: list[str] = []
    for p in merged:
        if p.endswith(".gz"):
            continue
        out.append(p)
    return out or ([default_path] if default_path else [])


_GENERIC_LOG_NAMES = {"access", "apache2", "httpd", "other_vhosts", "ssl", "vhost"}


def host_from_log_path(log_path: str) -> str | None:
    """Infer a vhost host from an Apache access-log filename.

    Handles the common vhost naming conventions:
      example.com.access.log · example.com-access.log · example.com_access.log
      example.com_access_log · example.com-access_log (RHEL-style)
    """
    for pat in (
        r"/([^/]+)[._-]access\.log$",   # <host>{.,-,_}access.log
        r"/([^/]+)[._-]access_log$",    # <host>{.,-,_}access_log (RHEL)
    ):
        m = re.search(pat, log_path)
        if m:
            name = m.group(1)
            if name.lower() not in _GENERIC_LOG_NAMES:
                return name.replace("_", ".")
    return None
