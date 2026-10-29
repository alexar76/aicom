"""Warm collect + security scan after fleet membership changes.

Saving ``servers.yaml`` alone only updates the config the floating agent
reloads each turn. Without a collect/scan pass the assistant still has no
snapshots, traffic rows, or findings for the new host. Call
:func:`warm_fleet_after_save` from Settings / Quick Start so that path is
automatic.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Iterable

from .collector import CollectResult, collect_once
from .config import AppConfig, ServerConfig
from .db_dialect import resolve_db_target
from .security.collector import ScanResult, scan_server

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class FleetWarmupResult:
    server_names: tuple[str, ...]
    collect: tuple[CollectResult, ...]
    scans: tuple[ScanResult, ...]

    @property
    def ok(self) -> bool:
        if not self.server_names:
            return True
        collect_ok = all(r.fetched_lines >= 0 for r in self.collect) if self.collect else True
        # Push-only fleets may have nothing to collect; scans still matter.
        scan_targets = [s for s in self.scans]
        if not scan_targets and not self.collect:
            return True
        scan_ok = any(s.ok for s in scan_targets) if scan_targets else collect_ok
        return bool(scan_ok or any(r.inserted_rows > 0 for r in self.collect))


def _names(servers: Iterable[ServerConfig]) -> set[str]:
    return {s.name for s in servers}


def new_or_changed_server_names(
    before: Iterable[ServerConfig] | None,
    after: Iterable[ServerConfig],
) -> list[str]:
    """Names that are new or whose SSH endpoint / transport changed."""
    prev = {s.name: s for s in (before or [])}
    out: list[str] = []
    for s in after:
        old = prev.get(s.name)
        if old is None:
            out.append(s.name)
            continue
        if (
            old.ssh.host != s.ssh.host
            or int(old.ssh.port) != int(s.ssh.port)
            or old.ssh.user != s.ssh.user
            or old.transport != s.transport
            or old.source != s.source
        ):
            out.append(s.name)
    return out


def warm_fleet(
    cfg: AppConfig,
    *,
    server_names: Iterable[str] | None = None,
) -> FleetWarmupResult:
    """Collect nginx/Apache logs + security-scan the given (or all) servers."""
    wanted = {n.strip() for n in (server_names or []) if str(n).strip()}
    targets = [
        s
        for s in cfg.servers
        if not s.is_push and (not wanted or s.name in wanted)
    ]
    names = tuple(s.name for s in targets)
    if not names:
        return FleetWarmupResult(server_names=(), collect=(), scans=())

    _log.info("Fleet warmup starting for: %s", ", ".join(names))
    collect_results = collect_once(cfg, server_names=set(names))
    mmdb = getattr(cfg, "geoip_mmdb_path", None)
    db_target = resolve_db_target(cfg)
    scans: list[ScanResult] = []
    for s in targets:
        try:
            scans.append(scan_server(s, db_target, mmdb_path=mmdb))
        except Exception as exc:
            _log.exception("Fleet warmup scan failed for %s", s.name)
            scans.append(ScanResult(server_name=s.name, ok=False, error=repr(exc)))
    _log.info(
        "Fleet warmup done: collect=%s scans_ok=%s",
        len(collect_results),
        sum(1 for s in scans if s.ok),
    )
    return FleetWarmupResult(
        server_names=names,
        collect=tuple(collect_results),
        scans=tuple(scans),
    )


def warm_fleet_after_save(
    cfg: AppConfig,
    *,
    previous_servers: Iterable[ServerConfig] | None = None,
    warm_all_if_none_new: bool = False,
) -> FleetWarmupResult:
    """Warm newly added/changed hosts so the AI assistant has live context."""
    focus = new_or_changed_server_names(previous_servers, cfg.servers)
    if not focus and warm_all_if_none_new:
        focus = [s.name for s in cfg.servers if not s.is_push]
    if not focus:
        return FleetWarmupResult(server_names=(), collect=(), scans=())
    prev_names = _names(previous_servers or [])
    for s in cfg.servers:
        if s.name not in prev_names and s.name not in focus and not s.is_push:
            focus.append(s.name)
    return warm_fleet(cfg, server_names=focus)
