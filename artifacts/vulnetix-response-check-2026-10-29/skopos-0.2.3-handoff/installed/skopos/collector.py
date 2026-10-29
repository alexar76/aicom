from __future__ import annotations

import ipaddress
import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable

from .config import AppConfig, load_config

_HTTP_LOG_SOURCES = frozenset({"ssh_nginx_access_log", "ssh_http_access_log"})
from .anonymize import anonymize_parsed
from .asn_db import AsnResolver, get_resolver as get_asn_resolver
from .db import (
    ParsedRequest,
    connect_for_config,
    init_db,
    insert_requests,
    prune_old_requests,
    upsert_collector_status,
)
from .ecosystem import ecosystem_segment
from .enrich import parse_user_agent, referer_domain
from .geoip import GeoIPResolver, is_private_ip
from .host_infer import infer_host
from .log_sources import LogSource, fetch_lines, host_hint, parse_line, resolve_log_sources


@dataclass(frozen=True)
class CollectResult:
    server_name: str
    fetched_lines: int
    inserted_rows: int
    log_paths: tuple[str, ...]


def _enrich_request(
    pr: ParsedRequest,
    *,
    log_source: str,
    server_name: str,
    server_ip: str,
    host_fallback: str | None,
    geo: GeoIPResolver | None,
    geo_map: dict | None = None,
    asn: AsnResolver | None = None,
) -> ParsedRequest | None:
    # Skip docker internal noise — nginx already has the same public traffic.
    if log_source.startswith("docker:"):
        if not pr.remote_addr or is_private_ip(pr.remote_addr):
            return None

    host = pr.host or host_fallback
    seg = ecosystem_segment(pr.path, host=host, log_source=log_source)
    if not host:
        host = infer_host(
            pr.path,
            server_name=server_name,
            ecosystem_segment=seg,
            referer=pr.referer,
        )

    country_code = pr.country_code
    country_name = pr.country_name
    if geo and pr.remote_addr:
        if is_private_ip(pr.remote_addr):
            country_code = "INT"
            country_name = "Internal"
        elif geo_map is not None:
            # No fallback lookup. The caller capped how many addresses this batch
            # may resolve; asking for the ones it left out would issue exactly
            # the flood of outbound requests the cap exists to prevent. An
            # unresolved address keeps whatever the parser gave it.
            info = geo_map.get(pr.remote_addr)
            if info is not None:
                country_code = info.iso_code
                country_name = info.name
        else:
            c = geo.country_for_ip(pr.remote_addr)
            country_code = c.iso_code
            country_name = c.name

    asn_number = pr.asn
    asn_org = pr.asn_org
    if asn is not None and pr.remote_addr and not is_private_ip(pr.remote_addr):
        info = asn.lookup(pr.remote_addr)
        asn_number = info.asn
        asn_org = info.org

    ua = parse_user_agent(pr.user_agent)
    return ParsedRequest(
        **{
            **pr.__dict__,
            "log_source": log_source,
            "ecosystem_segment": seg,
            "server_ip": server_ip,
            "host": host,
            "country_code": country_code,
            "country_name": country_name,
            "ua_browser": ua.browser,
            "ua_os": ua.os,
            "ua_device": ua.device,
            "ua_is_bot": (1 if ua.is_bot else 0) if ua.is_bot is not None else None,
            "referer_domain": referer_domain(pr.referer),
            "asn": asn_number,
            "asn_org": asn_org,
        }
    )


def _parse_source_line(source: LogSource, line: str) -> ParsedRequest | None:
    pr = parse_line(source, line)
    if not pr or not isinstance(pr, ParsedRequest):
        return None
    if not pr.method and not pr.remote_addr:
        return None
    return pr


#: Anything older than this is outside every dashboard window anyway, so a
#: timestamp beyond it is either a broken clock or an attempt to hide a row in
#: the distant past. Either way we keep the line and drop the claim.
_MAX_TS_AGE_DAYS = 400
#: Matches node_protocol.MAX_CLOCK_SKEW_SECONDS. A host the protocol is willing
#: to accept a report from must not then have every one of its rows dropped from
#: every time-window query for being slightly ahead.
_MAX_TS_SKEW_SECONDS = 900

#: PostgreSQL stores bytes_sent as int4. A larger value aborts the transaction,
#: which on a shared batch discards every other line with it.
_MAX_BYTES_SENT = 2**31 - 1

#: How many distinct addresses one batch may resolve. See the note in
#: :func:`ingest_lines`.
MAX_GEO_LOOKUPS_PER_BATCH = 400


def _sane_ts(ts_utc: str | None) -> str | None:
    """Keep a log-derived timestamp only if it could plausibly be real.

    Every dashboard query filters on ``ts_utc``. A line claiming 2099 matches
    every window forever and stretches every chart; one claiming 1970 hides from
    all of them. Neither needs more privilege than writing a log line, so the
    value is checked rather than trusted, and rows that fail keep their content
    but lose their claim to a position in time.
    """
    if not ts_utc:
        return None
    try:
        parsed = datetime.fromisoformat(str(ts_utc).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    now = datetime.now(tz=timezone.utc)
    if parsed > now + timedelta(seconds=_MAX_TS_SKEW_SECONDS):
        return None
    if parsed < now - timedelta(days=_MAX_TS_AGE_DAYS):
        return None
    return ts_utc


def _sanitise(pr: ParsedRequest) -> ParsedRequest:
    """Clamp attacker-influenced fields to what the columns can actually hold.

    Applies to every transport. The values come out of a log line either way, so
    a monitored host has always been able to choose them — push mode only makes
    it easier.
    """
    remote_addr = pr.remote_addr
    if remote_addr:
        try:
            ipaddress.ip_address(remote_addr)
        except ValueError:
            # An unparseable address would otherwise be interpolated into a geo
            # lookup URL and stored as if it meant something.
            remote_addr = None

    bytes_sent = pr.bytes_sent
    if bytes_sent is not None and not (0 <= bytes_sent <= _MAX_BYTES_SENT):
        bytes_sent = None

    status = pr.status
    if status is not None and not (0 <= status <= 999):
        status = None

    user_agent = pr.user_agent
    if user_agent and len(user_agent) > 512:
        # ua_parse runs a large regex corpus; unbounded input is a CPU sink.
        user_agent = user_agent[:512]

    from .redact import redact_parsed

    return ParsedRequest(
        **{
            **pr.__dict__,
            # Secrets out of the URL and the referer. Applied here because this
            # is the one path every transport goes through, so a future one
            # cannot arrive without it.
            **redact_parsed(pr),
            "remote_addr": remote_addr,
            "bytes_sent": bytes_sent,
            "status": status,
            "user_agent": user_agent,
            "ts_utc": _sane_ts(pr.ts_utc),
        }
    )


def ingest_lines(
    con,
    *,
    server_name: str,
    server_ip: str | None,
    lines: Iterable[tuple[LogSource, str]],
    geo: GeoIPResolver | None = None,
    asn: AsnResolver | None = None,
) -> tuple[int, int]:
    """Parse, enrich and store raw log lines. Returns (fetched, inserted).

    The single ingest path for every transport. SSH-pulled output and a pushed
    report go through exactly this code, so a push node gets no shortcut around
    parsing, clamping or deduplication — it can only choose the raw text, which
    is all any monitored host has ever been able to choose.
    """
    staged: list[tuple[LogSource, ParsedRequest]] = []
    fetched = 0
    for src, ln in lines:
        fetched += 1
        pr = _parse_source_line(src, ln)
        if not pr:
            continue
        staged.append((src, _sanitise(pr)))

    # Without a local MaxMind database each unseen address is a live HTTP lookup,
    # rate-limited to a few per second. A batch carrying thousands of distinct
    # addresses — a busy host's first report, or a log full of chosen ones —
    # therefore turns one ingest into minutes of outbound requests, which reads
    # to the sender as a timeout and to the lookup service as abuse. Bound it:
    # the rows still land, they just may not carry a country.
    seen_ips: list[str] = []
    unique: set[str] = set()
    for _, pr in staged:
        if not pr.remote_addr or is_private_ip(pr.remote_addr):
            continue
        if pr.remote_addr in unique:
            continue
        unique.add(pr.remote_addr)
        seen_ips.append(pr.remote_addr)
        if len(seen_ips) >= MAX_GEO_LOOKUPS_PER_BATCH:
            break
    geo_map = geo.prefetch_map(seen_ips) if geo else {}

    parsed: list[ParsedRequest] = []
    for src, pr in staged:
        enriched = _enrich_request(
            pr,
            log_source=src.id,
            server_name=server_name,
            server_ip=server_ip or "",
            host_fallback=host_hint(src) if src.kind == "file" else None,
            geo=geo,
            geo_map=geo_map,
            asn=asn,
        )
        if not enriched:
            continue
        # Reduce the address only now, after geo and ASN have read the real one.
        # The row keeps its country and network; it stops being able to point at a
        # single machine. See :mod:`skopos.anonymize`.
        updates = anonymize_parsed(enriched)
        if updates:
            enriched = ParsedRequest(**{**enriched.__dict__, **updates})
        parsed.append(enriched)

    return fetched, insert_requests(con, server_name, parsed)


def _make_geo(cfg: AppConfig) -> GeoIPResolver:
    path = getattr(cfg, "geoip_mmdb_path", None)
    # Hand it the ASN table. That dump already carries a registry country per
    # range, so with it in hand SKOPOS answers country offline and stops sending
    # each visitor's address to geojs.io for something it already knows.
    return GeoIPResolver(path, asn_resolver=_make_asn(cfg))


def _make_asn(cfg: AppConfig) -> AsnResolver:
    # Module-level cache: the iptoasn TSV parse is too expensive per poll cycle.
    return get_asn_resolver(getattr(cfg, "asn_tsv_path", None))


def collect_via_agent(server) -> tuple[list[tuple[LogSource, str]], list[str], object]:
    """Ask an agent-ssh host for its document and unpack it.

    Same document, same validator and same ingest as the push transport — the
    only difference is who opened the connection. That is deliberate: a second
    parsing path would be a second place for the two to disagree about what a
    host said.
    """
    import json

    from .node_report import parse_report
    from .remote_ops import run_agent_op

    raw = run_agent_op(server, "collect")
    report = parse_report(json.loads(raw))

    lines: list[tuple[LogSource, str]] = []
    source_ids: list[str] = []
    for src in report.sources:
        source = LogSource(id=src.id, kind=src.kind, parser=src.parser)
        source_ids.append(src.id)
        for ln in src.lines:
            lines.append((source, ln))
    return lines, source_ids, report


def collect_once(
    cfg: AppConfig,
    *,
    server_names: set[str] | None = None,
) -> list[CollectResult]:
    con = connect_for_config(cfg)
    init_db(con)
    results: list[CollectResult] = []

    geo = _make_geo(cfg)
    asn = _make_asn(cfg)
    per_source_batch = max(500, int(cfg.batch_lines_per_server))
    wanted = {n for n in (server_names or set()) if n}

    for s in cfg.servers:
        if wanted and s.name not in wanted:
            continue
        if s.source not in _HTTP_LOG_SOURCES:
            continue
        if s.is_push:
            # Its agent delivers on its own schedule; polling it here would both
            # fail and reset its status row to an error.
            continue
        try:
            all_lines: list[tuple[LogSource, str]] = []
            source_ids: list[str] = []

            if s.transport == "agent-ssh":
                all_lines, source_ids, _report = collect_via_agent(s)
            else:
                for src in resolve_log_sources(s):
                    source_ids.append(src.id)
                    for ln in fetch_lines(s, src, per_source_batch):
                        all_lines.append((src, ln))

            fetched, inserted = ingest_lines(
                con,
                server_name=s.name,
                server_ip=s.ssh.host,
                lines=all_lines,
                geo=geo,
                asn=asn,
            )
            upsert_collector_status(
                con,
                server_name=s.name,
                ok=True,
                fetched_lines=fetched,
                inserted_rows=inserted,
                log_paths=json.dumps(source_ids),
            )
            results.append(
                CollectResult(
                    server_name=s.name,
                    fetched_lines=fetched,
                    inserted_rows=inserted,
                    log_paths=tuple(source_ids),
                )
            )
        except Exception as e:
            # Postgres: a failed INSERT leaves the tx aborted — roll back or
            # the status upsert (and every later server) dies on
            # InFailedSqlTransaction.
            try:
                con.connection.rollback()
            except Exception:
                pass
            upsert_collector_status(con, server_name=s.name, ok=False, error=repr(e))
            results.append(
                CollectResult(server_name=s.name, fetched_lines=0, inserted_rows=0, log_paths=())
            )

    # Storage limitation (GDPR Art. 5(1)(e)): drop rows past the configured age
    # once per cycle, so retention is self-maintaining and needs no separate cron.
    # Defaults to 90 days; 0 keeps everything for an operator who wants full history.
    retention_days = int(getattr(cfg, "http_retention_days", 0) or 0)
    if retention_days > 0:
        try:
            prune_old_requests(con, retention_days)
        except Exception:
            try:
                con.connection.rollback()
            except Exception:
                pass

    geo.close()
    con.close()
    return results


def run_forever(cfg: AppConfig | str) -> None:
    log = logging.getLogger(__name__)
    while True:
        live = load_config(cfg) if isinstance(cfg, str) else cfg
        try:
            _ = collect_once(live)
        except Exception:
            log.exception("Collector cycle failed")
        time.sleep(max(1, int(live.poll_interval_seconds)))
