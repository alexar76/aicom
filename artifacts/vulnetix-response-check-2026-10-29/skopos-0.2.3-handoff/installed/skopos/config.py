from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml

_env_loaded = False
_env_mtime: float = 0.0

_PROXY_VARS = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
    "NO_PROXY",
    "no_proxy",
)


def _strip_proxy_env() -> None:
    for name in _PROXY_VARS:
        os.environ.pop(name, None)


def _alias_legacy_env(old_prefix: str, new_prefix: str) -> None:
    """Map STATS_* → SKOPOS_* when the new name is unset (migration from standalone Stats)."""
    for key, val in list(os.environ.items()):
        if not key.startswith(old_prefix):
            continue
        alias = new_prefix + key[len(old_prefix) :]
        if alias not in os.environ:
            os.environ[alias] = val


def load_app_env() -> None:
    """Load project .env (reloads when .env changes). Never use IDE proxy."""
    global _env_loaded, _env_mtime
    _strip_proxy_env()
    root = Path(__file__).resolve().parents[1]
    env_path = root / ".env"
    mtime = env_path.stat().st_mtime if env_path.exists() else 0.0
    if _env_loaded and mtime == _env_mtime:
        return
    try:
        from dotenv import load_dotenv
    except ImportError:
        _env_loaded = True
        _env_mtime = mtime
        return
    # Do not override non-empty process env (Docker Compose / systemd secrets win).
    # Stale baked `/app/.env` in an image must never clobber live keys in production.
    load_dotenv(env_path, override=False)
    _alias_legacy_env("STATS_", "SKOPOS_")
    _strip_proxy_env()
    _env_loaded = True
    _env_mtime = mtime


SourceType = Literal["ssh_nginx_access_log", "ssh_http_access_log"]


SSHMode = Literal["direct", "wrapper"]


@dataclass(frozen=True)
class SSHConfig:
    host: str
    port: int
    user: str
    key_path: str | None = None
    key_passphrase_env: str | None = None
    #: ``direct`` pipes shell scripts to the host and needs a shell-capable
    #: account. ``wrapper`` sends only op tokens to a key pinned to
    #: ``skopos-collect``; see :mod:`skopos.remote_ops`.
    mode: SSHMode = "direct"
    #: Per-server override for the host-key trust store.
    known_hosts_path: str | None = None


@dataclass(frozen=True)
class ApacheConfig:
    enabled: bool = False
    access_log_path: str = "/var/log/apache2/access.log"
    access_log_paths: list[str] | None = None
    auto_discover_logs: bool = True
    auto_discover_docker_logs: bool = False
    docker_log_containers: list[str] | None = None


@dataclass(frozen=True)
class NginxConfig:
    access_log_path: str = "/var/log/nginx/access.log"
    access_log_paths: list[str] | None = None
    auto_discover_logs: bool = True
    auto_discover_docker_logs: bool = False
    docker_log_containers: list[str] | None = None


#: How a server's data reaches SKOPOS.
#:
#: ``direct-ssh``  SKOPOS pipes shell scripts into the host. The original
#:                 behaviour; needs a shell-capable account and is the widest
#:                 credential of the three.
#: ``agent-ssh``   SKOPOS connects to a key pinned to ``skopos-node ssh-op``. The
#:                 host runs the collection and prints one document; the only
#:                 thing that crosses the wire is a verb.
#: ``agent-push``  The host posts its document to SKOPOS. No inbound credential
#:                 exists at all, so a compromise of SKOPOS gains no access to
#:                 the fleet. This is the recommended transport.
Transport = Literal["direct-ssh", "agent-ssh", "agent-push"]

TRANSPORTS: tuple[str, ...] = ("direct-ssh", "agent-ssh", "agent-push")

#: Transports SKOPOS reaches out over. Everything else arrives on its own.
SSH_TRANSPORTS = frozenset({"direct-ssh", "agent-ssh"})


@dataclass(frozen=True)
class ServerConfig:
    name: str
    source: SourceType
    ssh: SSHConfig
    nginx: NginxConfig
    apache: ApacheConfig | None = None
    transport: Transport = "direct-ssh"

    @property
    def is_push(self) -> bool:
        return self.transport == "agent-push"

    @property
    def uses_ssh(self) -> bool:
        return self.transport in SSH_TRANSPORTS


DEFAULT_SECURITY_SCAN_INTERVAL_MINUTES = 60
DEFAULT_TELEGRAM_BOT_TOKEN_ENV = "TELEGRAM_BOT_TOKEN"
DEFAULT_TELEGRAM_NOTIFY_INTERVAL_MINUTES = 60


@dataclass(frozen=True)
class AppConfig:
    db_path: str
    database_url: str | None = None
    geoip_mmdb_path: str | None = None
    asn_tsv_path: str | None = None
    poll_interval_seconds: int = 5
    batch_lines_per_server: int = 4000
    #: Delete stored request rows older than this many days, once per collect
    #: cycle. Default 90; 0 keeps everything. See :func:`skopos.db.prune_old_requests`.
    http_retention_days: int = 90
    security_auto_scan: bool = True
    security_scan_interval_minutes: int = DEFAULT_SECURITY_SCAN_INTERVAL_MINUTES
    telegram_enabled: bool = False
    telegram_bot_token_env: str = DEFAULT_TELEGRAM_BOT_TOKEN_ENV
    telegram_chat_id: str | None = None
    telegram_notify_interval_minutes: int = DEFAULT_TELEGRAM_NOTIFY_INTERVAL_MINUTES
    servers: list[ServerConfig] = None  # type: ignore[assignment]


def config_warnings(cfg: AppConfig) -> list[str]:
    """Posture problems that are worth saying out loud but not worth refusing to start over.

    These are all things a working deployment can have today. Failing to load
    would take the dashboard down over a pre-existing condition; saying nothing
    would let it persist forever. So they surface in the UI instead.
    """
    out: list[str] = []
    servers = cfg.servers or []

    by_key: dict[str, list[str]] = {}
    for s in servers:
        if s.uses_ssh and s.ssh.key_path:
            by_key.setdefault(s.ssh.key_path, []).append(s.name)
    for key_path, names in sorted(by_key.items()):
        if len(names) > 1:
            out.append(
                f"One SSH key ({key_path}) opens {len(names)} hosts "
                f"({', '.join(sorted(names))}). Stealing it costs you all of them — "
                "give each host its own key."
            )

    for s in servers:
        if s.uses_ssh and (s.ssh.user or "").strip() == "root":
            out.append(
                f"'{s.name}' is collected as root over SSH. Switch it to the agent, "
                "or to a dedicated unprivileged user."
            )
        if s.transport == "direct-ssh":
            out.append(
                f"'{s.name}' uses direct-ssh, which needs a full shell on the host. "
                "The agent transports need far less."
            )
    return out


def _require(d: dict[str, Any], key: str) -> Any:
    if key not in d:
        raise ValueError(f"Missing required config key: {key}")
    return d[key]


def load_config(path: str) -> AppConfig:
    p = Path(path).expanduser().resolve()
    raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("Config must be a YAML mapping at the top-level.")

    servers_raw = _require(raw, "servers")
    if not isinstance(servers_raw, list) or not servers_raw:
        raise ValueError("Config 'servers' must be a non-empty list.")

    servers: list[ServerConfig] = []
    for item in servers_raw:
        if not isinstance(item, dict):
            raise ValueError("Each server entry must be a mapping.")
        name = str(_require(item, "name"))
        source = _require(item, "source")
        if source not in ("ssh_nginx_access_log", "ssh_http_access_log"):
            raise ValueError(
                f"Unsupported source '{source}' for server '{name}'. "
                "Use ssh_nginx_access_log or ssh_http_access_log."
            )

        transport = str(item.get("transport", "direct-ssh")).strip().lower()
        if transport not in TRANSPORTS:
            raise ValueError(
                f"server '{name}': transport must be one of {', '.join(TRANSPORTS)}, "
                f"got '{transport}'"
            )

        # A push server never gets connected to, so it needs an address to label
        # its rows with and nothing else. Letting it omit the whole ssh block is
        # what makes "no inbound credential" true on paper as well as in fact.
        ssh_raw = item.get("ssh")
        if ssh_raw is None and transport == "agent-push":
            address = str(item.get("address") or "").strip()
            if not address:
                raise ValueError(
                    f"server '{name}': agent-push servers need an 'address' "
                    "(or an 'ssh' block) so their traffic can be attributed"
                )
            ssh_raw = {"host": address, "port": 22, "user": "-"}
        if ssh_raw is None:
            raise ValueError(f"server '{name}': Missing required config key: ssh")
        if not isinstance(ssh_raw, dict):
            raise ValueError(f"server '{name}': ssh must be a mapping")
        if "address" in item and transport == "agent-push":
            ssh_raw = {**ssh_raw, "host": str(item["address"]).strip() or ssh_raw.get("host")}
        ssh_mode = str(ssh_raw.get("mode", "direct")).strip().lower()
        if ssh_mode not in ("direct", "wrapper"):
            raise ValueError(
                f"server '{name}': ssh.mode must be 'direct' or 'wrapper', got '{ssh_mode}'"
            )
        ssh = SSHConfig(
            host=str(_require(ssh_raw, "host")),
            port=int(ssh_raw.get("port", 22)),
            user=str(_require(ssh_raw, "user")),
            key_path=(str(ssh_raw["key_path"]) if "key_path" in ssh_raw else None),
            key_passphrase_env=(
                str(ssh_raw["key_passphrase_env"]) if "key_passphrase_env" in ssh_raw else None
            ),
            mode=ssh_mode,  # type: ignore[arg-type]
            known_hosts_path=(
                str(ssh_raw["known_hosts_path"]) if "known_hosts_path" in ssh_raw else None
            ),
        )

        nginx_raw = item.get("nginx") or {}
        if not isinstance(nginx_raw, dict):
            raise ValueError(f"server '{name}': nginx must be a mapping")
        extra_paths = nginx_raw.get("access_log_paths")
        if extra_paths is not None and not isinstance(extra_paths, list):
            raise ValueError(f"server '{name}': nginx.access_log_paths must be a list")
        docker_containers = nginx_raw.get("docker_log_containers")
        if docker_containers is not None and not isinstance(docker_containers, list):
            raise ValueError(f"server '{name}': nginx.docker_log_containers must be a list")
        nginx = NginxConfig(
            access_log_path=str(nginx_raw.get("access_log_path", "/var/log/nginx/access.log")),
            access_log_paths=[str(x) for x in extra_paths] if extra_paths else None,
            auto_discover_logs=bool(nginx_raw.get("auto_discover_logs", True)),
            auto_discover_docker_logs=bool(nginx_raw.get("auto_discover_docker_logs", False)),
            docker_log_containers=[str(x) for x in docker_containers] if docker_containers else None,
        )

        apache_raw = item.get("apache")
        apache: ApacheConfig | None = None
        if apache_raw is not None:
            if not isinstance(apache_raw, dict):
                raise ValueError(f"server '{name}': apache must be a mapping")
            ap_extra = apache_raw.get("access_log_paths")
            if ap_extra is not None and not isinstance(ap_extra, list):
                raise ValueError(f"server '{name}': apache.access_log_paths must be a list")
            ap_docker = apache_raw.get("docker_log_containers")
            if ap_docker is not None and not isinstance(ap_docker, list):
                raise ValueError(f"server '{name}': apache.docker_log_containers must be a list")
            apache = ApacheConfig(
                enabled=bool(apache_raw.get("enabled", True)),
                access_log_path=str(apache_raw.get("access_log_path", "/var/log/apache2/access.log")),
                access_log_paths=[str(x) for x in ap_extra] if ap_extra else None,
                auto_discover_logs=bool(apache_raw.get("auto_discover_logs", True)),
                auto_discover_docker_logs=bool(apache_raw.get("auto_discover_docker_logs", False)),
                docker_log_containers=[str(x) for x in ap_docker] if ap_docker else None,
            )

        servers.append(
            ServerConfig(
                name=name,
                source=source,
                ssh=ssh,
                nginx=nginx,
                apache=apache,
                transport=transport,  # type: ignore[arg-type]
            )
        )

    seen_names: set[str] = set()
    for s in servers:
        if s.name in seen_names:
            # Two servers sharing a name share a dedup namespace and a status
            # row, so one silently overwrites the other's data.
            raise ValueError(f"Duplicate server name: '{s.name}'")
        seen_names.add(s.name)

    # A key that opens more than one host makes "per-host key" a description of
    # the config file rather than of the blast radius. This is only fatal for
    # agent-ssh, where a dedicated key is part of what the operator opted into;
    # for the legacy transport it is reported by config_warnings() instead, so
    # an existing fleet keeps running while the problem stays visible.
    keys_seen: dict[str, str] = {}
    for s in servers:
        if s.transport != "agent-ssh" or not s.ssh.key_path:
            continue
        owner = keys_seen.get(s.ssh.key_path)
        if owner is not None:
            raise ValueError(
                f"servers '{owner}' and '{s.name}' share the SSH key "
                f"'{s.ssh.key_path}'. Give each agent-ssh host its own key so one "
                "stolen key does not open the whole fleet."
            )
        keys_seen[s.ssh.key_path] = s.name

    scan_interval = int(raw.get("security_scan_interval_minutes", DEFAULT_SECURITY_SCAN_INTERVAL_MINUTES))
    scan_interval = max(5, min(1440, scan_interval))

    notify_interval = int(
        raw.get("telegram_notify_interval_minutes", DEFAULT_TELEGRAM_NOTIFY_INTERVAL_MINUTES)
    )
    notify_interval = max(5, min(10080, notify_interval))

    chat_raw = raw.get("telegram_chat_id")
    chat_id = str(chat_raw).strip() if chat_raw not in (None, "") else None

    db_url_raw = raw.get("database_url")
    if db_url_raw in (None, ""):
        db_url_raw = os.environ.get("SKOPOS_DATABASE_URL")
    database_url = str(db_url_raw).strip() if db_url_raw not in (None, "") else None

    retention_raw = raw.get("http_retention_days")
    if retention_raw in (None, ""):
        retention_raw = os.environ.get("SKOPOS_HTTP_RETENTION_DAYS", "90")
    try:
        http_retention_days = max(0, int(retention_raw))
    except (TypeError, ValueError):
        http_retention_days = 90

    return AppConfig(
        db_path=str(raw.get("db_path", "./skopos.sqlite3")),
        database_url=database_url,
        geoip_mmdb_path=(str(raw["geoip_mmdb_path"]) if raw.get("geoip_mmdb_path") else None),
        asn_tsv_path=(str(raw["asn_tsv_path"]) if raw.get("asn_tsv_path") else None),
        poll_interval_seconds=int(raw.get("poll_interval_seconds", 5)),
        batch_lines_per_server=int(raw.get("batch_lines_per_server", 4000)),
        http_retention_days=http_retention_days,
        security_auto_scan=bool(raw.get("security_auto_scan", True)),
        security_scan_interval_minutes=scan_interval,
        telegram_enabled=bool(raw.get("telegram_enabled", False)),
        telegram_bot_token_env=str(
            raw.get("telegram_bot_token_env", DEFAULT_TELEGRAM_BOT_TOKEN_ENV)
        ),
        telegram_chat_id=chat_id,
        telegram_notify_interval_minutes=notify_interval,
        servers=servers,
    )
