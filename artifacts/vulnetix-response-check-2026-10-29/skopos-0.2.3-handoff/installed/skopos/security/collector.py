from __future__ import annotations

from dataclasses import dataclass

from ..config import AppConfig, ServerConfig
from ..db_dialect import resolve_db_target
from ..db import connect, init_db, now_utc_iso
from ..geoip import GeoIPResolver
from .audit import SecurityFinding, audit_snapshot
from .knock_analyzer import enrich_knocks, http_probes_from_db
from .port_knocks import events_from_knock_output, fetch_port_knocks
from .probe import ServerSnapshot, probe_server
from .store import insert_knock_events, save_scan


@dataclass(frozen=True)
class ScanResult:
    server_name: str
    ok: bool
    snapshot_id: int | None = None
    findings_count: int = 0
    knocks_inserted: int = 0
    error: str | None = None


def _make_geo(mmdb_path: str | None, asn_tsv_path: str | None = None) -> GeoIPResolver:
    from ..asn_db import get_resolver as get_asn_resolver

    return GeoIPResolver(mmdb_path, asn_resolver=get_asn_resolver(asn_tsv_path))


def scan_server(server: ServerConfig, db_target: str, *, mmdb_path: str | None = None) -> ScanResult:
    con = connect(db_target)
    init_db(con)
    geo = _make_geo(mmdb_path)
    try:
        scanned_at = now_utc_iso()

        if server.transport == "agent-ssh":
            # The agent already ran the probe locally; asking it to run one on
            # demand would mean an op that takes parameters, which is exactly
            # what this transport exists to avoid.
            from ..collector import collect_via_agent
            from .probe import snapshot_from_probe_output

            from ..collector import ingest_lines

            lines, _ids, report = collect_via_agent(server)
            # The agent hands over one document, and asking for it advances that
            # host's read offsets. Taking the probe out and dropping the log
            # lines on the floor would silently lose every line collected
            # between the last poll and this scan — so they go in here, through
            # the same path the collector uses. Deduplication makes the overlap
            # with a concurrent poll harmless.
            if lines:
                ingest_lines(
                    con,
                    server_name=server.name,
                    server_ip=server.ssh.host,
                    lines=lines,
                    geo=geo,
                )
            if not report.probe:
                raise RuntimeError(
                    "the agent returned no probe section; is "
                    "skopos-node-privdump.timer running on this host?"
                )
            snap = snapshot_from_probe_output(
                report.probe,
                server_name=server.name,
                host=server.ssh.host,
                scanned_at_utc=scanned_at,
            )
            ssh_events = events_from_knock_output(report.knocks or "")
        else:
            snap = probe_server(server, scanned_at_utc=scanned_at)
            ssh_events = fetch_port_knocks(server)

        findings = audit_snapshot(snap)
        http_events = http_probes_from_db(con, server.name, hours=168)
        all_events = ssh_events + http_events
        enriched = enrich_knocks(all_events, geo=geo)
        knock_n = insert_knock_events(con, server.name, server.ssh.host, enriched)

        sid = save_scan(con, snap, findings, transport=server.transport)
        return ScanResult(
            server_name=server.name,
            ok=True,
            snapshot_id=sid,
            findings_count=len(findings),
            knocks_inserted=knock_n,
        )
    except Exception as e:
        return ScanResult(server_name=server.name, ok=False, error=repr(e))
    finally:
        geo.close()
        con.close()


def scan_all_servers(cfg: AppConfig) -> list[ScanResult]:
    mmdb = getattr(cfg, "geoip_mmdb_path", None)
    # Push hosts scan themselves and send the result; probing them from here
    # would need the inbound credential that transport exists to avoid.
    return [
        scan_server(s, resolve_db_target(cfg), mmdb_path=mmdb)
        for s in cfg.servers
        if not s.is_push
    ]
