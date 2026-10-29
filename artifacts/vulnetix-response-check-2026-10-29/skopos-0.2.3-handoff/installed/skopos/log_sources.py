from __future__ import annotations

from dataclasses import dataclass

from .apache import parse_access_line as parse_apache_line
from .config import ServerConfig
from .nginx import parse_access_line
from .nginx_logs import host_from_log_path as nginx_host_from_log_path
from .remote_ops import OpError, op_discover_docker, op_docker_logs, op_tail, run_server_op
from .uvicorn_log import parse_uvicorn_line


@dataclass(frozen=True)
class LogSource:
    """A remote HTTP access log we can tail over SSH."""

    id: str
    kind: str  # "file" | "docker"
    parser: str  # "nginx" | "apache" | "uvicorn" | "auto"


def discover_docker_http_containers(server: ServerConfig) -> list[str]:
    out = run_server_op(server, op_discover_docker())
    names: list[str] = []
    for ln in out.splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("# STDERR:"):
            continue
        if ln.startswith("docker:"):
            ln = ln[len("docker:") :]
        if ln and ln not in names:
            names.append(ln)
    return names


def resolve_log_sources(server: ServerConfig) -> list[LogSource]:
    """HTTP access logs: nginx files, optional Apache files, public docker containers."""
    from .apache_logs import resolve_log_paths as resolve_apache_paths
    from .nginx_logs import resolve_log_paths as resolve_nginx_paths

    sources: list[LogSource] = []
    seen: set[str] = set()

    for path in resolve_nginx_paths(server):
        sid = f"file:{path}"
        if sid not in seen:
            seen.add(sid)
            sources.append(LogSource(id=sid, kind="file", parser="nginx"))

    if getattr(server, "apache", None) and server.apache.enabled:
        for path in resolve_apache_paths(server):
            sid = f"file:{path}"
            if sid not in seen:
                seen.add(sid)
                sources.append(LogSource(id=sid, kind="file", parser="apache"))

    # Docker HTTP containers are host-level (serve traffic regardless of nginx/apache).
    # Honor explicit lists and auto-discover toggles from EITHER block for symmetry.
    apache_cfg = getattr(server, "apache", None)
    extra_docker = list(getattr(server.nginx, "docker_log_containers", None) or [])
    if apache_cfg is not None and getattr(apache_cfg, "enabled", False):
        for name in getattr(apache_cfg, "docker_log_containers", None) or []:
            if name not in extra_docker:
                extra_docker.append(name)

    auto_docker = bool(getattr(server.nginx, "auto_discover_docker_logs", True))
    if apache_cfg is not None and getattr(apache_cfg, "enabled", False):
        auto_docker = auto_docker or bool(getattr(apache_cfg, "auto_discover_docker_logs", False))

    discovered_docker: list[str] = []
    if auto_docker:
        try:
            discovered_docker = discover_docker_http_containers(server)
        except Exception:
            discovered_docker = []

    for name in extra_docker + discovered_docker:
        sid = f"docker:{name}"
        if sid not in seen:
            seen.add(sid)
            sources.append(LogSource(id=sid, kind="docker", parser="auto"))

    return sources


def fetch_lines(server: ServerConfig, source: LogSource, batch_lines: int) -> list[str]:
    n = max(100, int(batch_lines))
    try:
        if source.kind == "file":
            op = op_tail(source.id[len("file:") :], n)
        elif source.kind == "docker":
            op = op_docker_logs(source.id[len("docker:") :], n)
        else:
            return []
    except (OpError, ValueError):
        # A source we cannot express safely is a source we skip, not a crash: one
        # oddly-named container must not stop the rest of the fleet collecting.
        return []

    out = run_server_op(server, op)
    return [ln for ln in out.splitlines() if ln and not ln.startswith("# STDERR:")]


def parse_line(source: LogSource, line: str):
    if source.parser == "nginx":
        return parse_access_line(line)
    if source.parser == "apache":
        return parse_apache_line(line)
    if source.parser == "uvicorn":
        return parse_uvicorn_line(line)

    # auto: try nginx/apache combined first, then uvicorn.
    pr = parse_access_line(line)
    if pr and pr.remote_addr and pr.method:
        return pr
    uv = parse_uvicorn_line(line)
    if uv:
        return uv
    if pr and pr.remote_addr:
        return pr
    return None


def host_hint(source: LogSource) -> str | None:
    if source.kind == "file" and source.id.startswith("file:"):
        path = source.id[len("file:") :]
        if source.parser == "apache":
            from .apache_logs import host_from_log_path as apache_host

            return apache_host(path) or nginx_host_from_log_path(path)
        return nginx_host_from_log_path(path)
    return None
