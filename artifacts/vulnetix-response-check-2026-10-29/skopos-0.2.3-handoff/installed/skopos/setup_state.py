"""Detect first-run / quick-start progress and wizard dismissal state."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from skopos.agent.config import get_provider, load_agent_config
from skopos.atomic_io import write_text_atomic
from skopos.config import AppConfig, load_config
from skopos.config_paths import project_root
from skopos.db import connect, init_db
from skopos.db_dialect import is_postgres_url, resolve_db_target
from skopos.security.store import latest_snapshots, scan_history_summary
from skopos.ssh_setup import resolve_key_path

_WIZARD_STATE_FILE = project_root() / ".skopos_wizard.json"


@dataclass(frozen=True)
class SetupStatus:
    config_exists: bool
    config_valid: bool
    server_count: int
    ssh_key_exists: bool
    password_set: bool
    ai_key_set: bool
    has_traffic: bool
    has_scan: bool
    wizard_dismissed: bool

    @property
    def complete(self) -> bool:
        return self.config_valid and self.server_count > 0 and self.has_traffic and self.has_scan

    @property
    def needs_wizard(self) -> bool:
        return not self.wizard_dismissed and not self.complete


def _wizard_state() -> dict:
    if not _WIZARD_STATE_FILE.is_file():
        return {}
    try:
        data = json.loads(_WIZARD_STATE_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def is_wizard_dismissed() -> bool:
    return bool(_wizard_state().get("dismissed"))


def dismiss_wizard() -> None:
    payload = {
        "dismissed": True,
        "dismissed_at_utc": datetime.now(tz=timezone.utc).isoformat(),
    }
    write_text_atomic(_WIZARD_STATE_FILE, json.dumps(payload, indent=2))


def reset_wizard_dismissed() -> None:
    if _WIZARD_STATE_FILE.is_file():
        _WIZARD_STATE_FILE.unlink(missing_ok=True)


def try_load_config(path: str) -> AppConfig | None:
    try:
        return load_config(path)
    except Exception:
        return None


def default_app_config(servers: list | None = None) -> AppConfig:
    return AppConfig(
        db_path="./skopos.sqlite3",
        geoip_mmdb_path="./GeoLite2-Country.mmdb",
        poll_interval_seconds=5,
        batch_lines_per_server=4000,
        security_auto_scan=True,
        security_scan_interval_minutes=60,
        servers=servers or [],
    )


def _has_traffic(db_target: str) -> bool:
    if not is_postgres_url(db_target):
        p = Path(db_target).expanduser()
        if not p.is_file():
            return False
    try:
        con = connect(db_target)
        init_db(con)
        row = con.execute("SELECT COUNT(*) AS c FROM http_requests LIMIT 1").fetchone()
        con.close()
        if isinstance(row, dict):
            return bool(int(row.get("c") or 0) > 0)
        return bool(row and int(row[0]) > 0)
    except Exception:
        return False


def _has_scan(db_target: str, server_names: list[str]) -> bool:
    if not is_postgres_url(db_target):
        p = Path(db_target).expanduser()
        if not p.is_file():
            return False
    try:
        con = connect(db_target)
        init_db(con)
        if server_names:
            snaps = latest_snapshots(con, server_names)
            if snaps:
                con.close()
                return True
        summary = scan_history_summary(con, server_names or None)
        con.close()
        return bool(summary.get("total_scans"))
    except Exception:
        return False


def _password_configured() -> bool:
    try:
        from skopos.auth_store import dashboard_password_configured

        return dashboard_password_configured()
    except Exception:
        return bool(os.environ.get("SKOPOS_DASHBOARD_PASSWORD", "").strip())


def _ai_key_configured(agent_path: str) -> bool:
    try:
        agent_cfg = load_agent_config(agent_path)
        prov = get_provider(agent_cfg)
    except Exception:
        return False
    if prov.kind in ("ollama", "lmstudio"):
        return True
    return bool(prov.api_key)


def evaluate_setup(
    config_path: str = "./servers.yaml",
    agent_path: str = "./agent.yaml",
    *,
    key_path: str | None = None,
) -> SetupStatus:
    p = Path(config_path).expanduser()
    config_exists = p.is_file()
    cfg = try_load_config(config_path) if config_exists else None
    server_count = len(cfg.servers) if cfg else 0
    db_target = resolve_db_target(cfg) if cfg else "./skopos.sqlite3"
    server_names = [s.name for s in cfg.servers] if cfg else []
    preferred_key = key_path
    if cfg and cfg.servers and cfg.servers[0].ssh.key_path:
        preferred_key = cfg.servers[0].ssh.key_path
    key_info = resolve_key_path(preferred_key)

    return SetupStatus(
        config_exists=config_exists,
        config_valid=cfg is not None,
        server_count=server_count,
        ssh_key_exists=key_info.exists,
        password_set=_password_configured(),
        ai_key_set=_ai_key_configured(agent_path),
        has_traffic=_has_traffic(db_target),
        has_scan=_has_scan(db_target, server_names),
        wizard_dismissed=is_wizard_dismissed(),
    )


def suggest_wizard_step(status: SetupStatus) -> int:
    if not status.config_valid or status.server_count == 0:
        return 1
    if not status.ssh_key_exists:
        return 2
    if not status.password_set or not status.ai_key_set:
        return 3
    if not status.has_traffic:
        return 4
    if not status.has_scan:
        return 5
    return 6
