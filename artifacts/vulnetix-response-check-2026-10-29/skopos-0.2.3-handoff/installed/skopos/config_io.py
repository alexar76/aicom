"""Read/write servers.yaml for the Settings UI."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .config import AppConfig, ApacheConfig, NginxConfig, SSHConfig, ServerConfig, load_config


def _server_to_dict(server: ServerConfig) -> dict[str, Any]:
    ssh: dict[str, Any] = {
        "host": server.ssh.host,
        "port": server.ssh.port,
        "user": server.ssh.user,
    }
    if server.ssh.key_path:
        ssh["key_path"] = server.ssh.key_path
    if server.ssh.key_passphrase_env:
        ssh["key_passphrase_env"] = server.ssh.key_passphrase_env
    # This function rebuilds servers.yaml from scratch, so anything not named here
    # is dropped on the next save from the UI. Silently reverting a server from
    # the restricted wrapper key back to a full shell would be the worst possible
    # way to lose a setting.
    if server.ssh.mode != "direct":
        ssh["mode"] = server.ssh.mode
    if server.ssh.known_hosts_path:
        ssh["known_hosts_path"] = server.ssh.known_hosts_path

    nginx: dict[str, Any] = {
        "access_log_path": server.nginx.access_log_path,
        "auto_discover_logs": server.nginx.auto_discover_logs,
        "auto_discover_docker_logs": server.nginx.auto_discover_docker_logs,
    }
    if server.nginx.access_log_paths:
        nginx["access_log_paths"] = list(server.nginx.access_log_paths)
    if server.nginx.docker_log_containers:
        nginx["docker_log_containers"] = list(server.nginx.docker_log_containers)

    row: dict[str, Any] = {
        "name": server.name,
        "source": server.source,
        "transport": server.transport,
        "ssh": ssh,
        "nginx": nginx,
    }
    if server.is_push:
        # A push server is labelled by its address, and that is what the loader
        # reads. The ssh block stays as written: deleting it would make the
        # switch to agent-push one-way, silently discarding the key path and
        # user an operator would need to switch back or to agent-ssh.
        row["address"] = server.ssh.host
    if server.apache is not None and server.apache.enabled:
        apache: dict[str, Any] = {
            "enabled": True,
            "access_log_path": server.apache.access_log_path,
            "auto_discover_logs": server.apache.auto_discover_logs,
            "auto_discover_docker_logs": server.apache.auto_discover_docker_logs,
        }
        if server.apache.access_log_paths:
            apache["access_log_paths"] = list(server.apache.access_log_paths)
        if server.apache.docker_log_containers:
            apache["docker_log_containers"] = list(server.apache.docker_log_containers)
        row["apache"] = apache
    custom = getattr(server, "ssh_commands", None)
    if custom:
        row["ssh_commands"] = custom
    return row


def _parse_ssh_commands(item: dict[str, Any]) -> list[dict[str, str]]:
    raw = item.get("ssh_commands") or []
    if not isinstance(raw, list):
        return []
    out: list[dict[str, str]] = []
    for row in raw:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "").strip()
        command = str(row.get("command") or "").strip()
        if name and command:
            out.append({"name": name, "command": command})
    return out


def load_config_with_commands(path: str) -> tuple[AppConfig, dict[str, list[dict[str, str]]]]:
    cfg = load_config(path)
    raw = yaml.safe_load(Path(path).expanduser().read_text(encoding="utf-8")) or {}
    commands: dict[str, list[dict[str, str]]] = {}
    for item in raw.get("servers") or []:
        if isinstance(item, dict) and item.get("name"):
            commands[str(item["name"])] = _parse_ssh_commands(item)
    return cfg, commands


def save_config(path: str, cfg: AppConfig, *, ssh_commands: dict[str, list[dict[str, str]]] | None = None) -> None:
    p = Path(path).expanduser().resolve()
    existing = yaml.safe_load(p.read_text(encoding="utf-8")) if p.is_file() else {}
    if not isinstance(existing, dict):
        existing = {}

    servers_out: list[dict[str, Any]] = []
    for server in cfg.servers:
        row = _server_to_dict(server)
        cmds = (ssh_commands or {}).get(server.name) or []
        if cmds:
            row["ssh_commands"] = cmds
        servers_out.append(row)

    payload = {
        **{k: v for k, v in existing.items() if k != "servers"},
        "db_path": cfg.db_path,
        "geoip_mmdb_path": cfg.geoip_mmdb_path,
        "poll_interval_seconds": cfg.poll_interval_seconds,
        "batch_lines_per_server": cfg.batch_lines_per_server,
        "security_auto_scan": cfg.security_auto_scan,
        "security_scan_interval_minutes": cfg.security_scan_interval_minutes,
        "telegram_enabled": cfg.telegram_enabled,
        "telegram_bot_token_env": cfg.telegram_bot_token_env,
        "telegram_chat_id": cfg.telegram_chat_id,
        "telegram_notify_interval_minutes": cfg.telegram_notify_interval_minutes,
        "servers": servers_out,
    }
    if cfg.database_url:
        payload["database_url"] = cfg.database_url
    elif "database_url" in payload:
        del payload["database_url"]
    p.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True, default_flow_style=False),
        encoding="utf-8",
    )


def draft_server_from_form(
    *,
    name: str,
    host: str,
    port: int,
    user: str,
    key_path: str,
    key_passphrase_env: str,
    access_log_path: str,
    auto_discover_logs: bool,
    auto_discover_docker_logs: bool,
    docker_log_containers: str,
    apache_enabled: bool = False,
    apache_access_log_path: str = "/var/log/apache2/access.log",
    apache_auto_discover_logs: bool = True,
    apache_auto_discover_docker_logs: bool = False,
    apache_docker_log_containers: str = "",
    transport: str = "agent-push",
    ssh_mode: str = "direct",
    known_hosts_path: str | None = None,
) -> ServerConfig:
    containers = [c.strip() for c in docker_log_containers.split(",") if c.strip()]
    apache_containers = [c.strip() for c in apache_docker_log_containers.split(",") if c.strip()]
    apache: ApacheConfig | None = None
    if apache_enabled:
        apache = ApacheConfig(
            enabled=True,
            access_log_path=apache_access_log_path.strip() or "/var/log/apache2/access.log",
            auto_discover_logs=apache_auto_discover_logs,
            auto_discover_docker_logs=apache_auto_discover_docker_logs,
            docker_log_containers=apache_containers or None,
        )
    return ServerConfig(
        name=name.strip(),
        source="ssh_http_access_log" if apache_enabled else "ssh_nginx_access_log",
        transport=transport,  # type: ignore[arg-type]
        ssh=SSHConfig(
            host=host.strip(),
            port=int(port),
            user=user.strip(),
            key_path=key_path.strip() or None,
            key_passphrase_env=key_passphrase_env.strip() or None,
            mode=ssh_mode,  # type: ignore[arg-type]
            # Carried through explicitly: the Settings page rebuilds every
            # server through this function on each render, so a field it does
            # not accept is a field that gets erased on the next save.
            known_hosts_path=(known_hosts_path or None),
        ),
        nginx=NginxConfig(
            access_log_path=access_log_path.strip(),
            auto_discover_logs=auto_discover_logs,
            auto_discover_docker_logs=auto_discover_docker_logs,
            docker_log_containers=containers or None,
        ),
        apache=apache,
    )
