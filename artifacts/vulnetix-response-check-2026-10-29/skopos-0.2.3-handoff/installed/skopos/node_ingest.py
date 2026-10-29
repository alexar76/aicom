"""Authenticate a pushed report and turn it into rows.

The order of operations here is the security design, so it is worth stating
plainly:

1. Read headers. Verify the HMAC over the **raw body bytes** before the body is
   parsed, so an unauthenticated peer never reaches the JSON parser.
2. Resolve ``key_id`` to a server through the credential table. The report's own
   content has no say in which server it belongs to.
3. Claim the sequence number in one conditional UPDATE. A replayed or reordered
   report loses the race and is dropped.
4. Only then validate the document and ingest it, through the same enrich and
   dedup path SSH-collected lines take.

Two kinds of document arrive on that path. Log lines from a monitored host are
the original and carry no ``kind``; a board pushed by the remediation conductor
declares ``kind: remediation`` and is routed to its own store instead.

Every authentication failure returns the same thing. Distinguishing "unknown
key" from "bad signature" from "revoked" would let anyone with a socket
enumerate the fleet.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass

from . import node_store
from .collector import ingest_lines
from .config import AppConfig, ServerConfig
from .db import connect_for_config, init_db, upsert_collector_status
from .geoip import GeoIPResolver
from .log_sources import LogSource
from .node_protocol import (
    HDR_NODE,
    HDR_SEQ,
    HDR_SIGNATURE,
    HDR_TIMESTAMP,
    MAX_CLOCK_SKEW_SECONDS,
    MAX_SEQ_ADVANCE,
    ProtocolError,
    parse_int_header,
    verify,
)
from .node_report import NodeReport, parse_report
from .node_store import NodeCredential

logger = logging.getLogger("skopos.node")

#: Burned when the key is unknown, so an attacker cannot tell "no such node"
#: from "wrong signature" by timing the response.
_DUMMY_SECRET = b"\x00" * 32

#: A credential id is minted by us as "nk_" plus hex; nothing else is valid.
_KEY_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

#: Knock events accepted from one report. See the note where it is applied.
MAX_KNOCK_EVENTS_PER_REPORT = 500

#: A document declaring this kind is a remediation board from the conductor
#: rather than log lines from a monitored host. Deployed agents send no ``kind``
#: at all, so they keep taking the path they always took — the alternative,
#: teaching ``node_report`` about a second section, would mean bumping
#: PROTOCOL_VERSION and re-rolling every agent in the fleet at once.
REMEDIATION_KIND = "remediation"

#: Jobs accepted from one push. The board is small; an unbounded list of them is
#: not, and the endpoint's 8 MiB ceiling is far too generous to be the limit.
MAX_REMEDIATION_JOBS = 200

#: Seconds of live GeoIP HTTP lookups one pushed report may spend, log lines and
#: knocks together. Without a local MaxMind database every unseen address is a
#: rate-limited request (~150 ms each on prod), and the count caps still allowed
#: hundreds of them per pass: a host catching up after an outage ran past the
#: 120 s its unit and nginx both allow, never saw its 200, and re-sent the same
#: backlog every tick. Addresses past the budget are stored without a country.
PUSH_GEO_HTTP_BUDGET_S = 40


class AuthError(Exception):
    """Authentication failed. The reason is for our logs, never for the peer."""


class IngestError(Exception):
    """The request authenticated but the document was not acceptable."""


class SeqConflict(Exception):
    """A correctly signed report reused a sequence number that is already spent.

    Distinct from :class:`AuthError` on purpose. The signature has already been
    verified by the time this is raised, so telling this caller which number to
    use next reveals nothing to anyone who could not compute it anyway — and it
    is what lets a node that fell behind recover on its own instead of retrying
    the same number until someone notices.
    """

    def __init__(self, next_seq: int):
        super().__init__(f"sequence number already used; next is {next_seq}")
        self.next_seq = next_seq


@dataclass(frozen=True)
class IngestResult:
    server_name: str
    accepted: int
    duplicates: int
    rejected: int
    clock_skew_s: int


def authenticate(con, headers, body: bytes) -> tuple[NodeCredential, int, int]:
    """Verify a signed report. Returns (credential, seq, clock_skew_seconds)."""
    key_id = str(headers.get(HDR_NODE, "") or "").strip()
    signature = str(headers.get(HDR_SIGNATURE, "") or "").strip()

    if not key_id or not signature or len(key_id) > 64:
        raise AuthError("missing credentials")
    # Header folding survives parsing with the CRLF intact, and .strip() does not
    # touch an interior one. A newline here would break the signing string's
    # field separation and land verbatim in the log line below.
    if not _KEY_ID_RE.match(key_id) or not signature.isascii():
        raise AuthError("malformed credentials")
    try:
        timestamp = parse_int_header(headers.get(HDR_TIMESTAMP), label="timestamp")
        seq = parse_int_header(headers.get(HDR_SEQ), label="seq")
    except ProtocolError as e:
        raise AuthError(str(e)) from e
    if seq < 1:
        raise AuthError("seq must be positive")

    credential = node_store.get_credential(con, key_id)

    if credential is None:
        # Do the verification anyway and throw the answer away, so that "no such
        # node" and "wrong signature" cost the same and the fleet cannot be
        # enumerated by timing.
        verify(_DUMMY_SECRET, signature, key_id=key_id, timestamp=timestamp, seq=seq, body=body)
        raise AuthError(f"unknown key_id {key_id}")

    if not verify(
        credential.secret, signature, key_id=key_id, timestamp=timestamp, seq=seq, body=body
    ):
        raise AuthError(f"bad signature for {key_id}")

    # Signature first, revocation second: a revoked key must not be usable as an
    # oracle for whether a key_id ever existed.
    if credential.revoked:
        raise AuthError(f"revoked key {key_id}")

    skew = int(time.time()) - timestamp
    if abs(skew) > MAX_CLOCK_SKEW_SECONDS:
        raise AuthError(f"clock skew {skew}s for {key_id}")

    if seq > credential.last_seq + MAX_SEQ_ADVANCE:
        # A jump this large is a reinstall or a cloned credential, not a gap.
        raise AuthError(f"seq jumped from {credential.last_seq} to {seq} for {key_id}")

    if not node_store.claim_seq(con, key_id, seq):
        current = node_store.get_credential(con, key_id)
        raise SeqConflict((current.last_seq if current else seq) + 1)

    return credential, seq, skew


def _server_for(cfg: AppConfig, server_name: str) -> ServerConfig:
    for s in cfg.servers or []:
        if s.name == server_name:
            return s
    raise IngestError(f"server '{server_name}' is not configured")


def unrouted_credentials(cfg: AppConfig, con) -> list[dict]:
    """Live credentials that no agent-push entry in ``cfg`` would accept.

    Nothing fails loudly when a servers.yaml loses an enrolled host: the node
    keeps signing reports, each one authenticates, spends a sequence number and
    is refused with a 400, and the dashboard simply stops hearing from it. A
    deploy runs this against the file it is about to mount, before going live.
    """
    push = {s.name for s in cfg.servers or [] if s.is_push}
    return [
        c for c in node_store.list_credentials(con)
        if not c.get("revoked_at_utc") and c.get("server_name") not in push
    ]


def ingest_report(
    cfg: AppConfig,
    credential: NodeCredential,
    report: NodeReport,
    *,
    clock_skew_s: int = 0,
    peer_ip: str | None = None,
) -> IngestResult:
    """Store a validated report under the server its credential names."""
    server = _server_for(cfg, credential.server_name)
    if not server.is_push:
        # Accepting a push for a server configured as pull would let the two
        # paths fight over the same dedup namespace and status row.
        raise IngestError(
            f"server '{server.name}' is configured as {server.transport}, not agent-push"
        )

    con = connect_for_config(cfg)
    try:
        init_db(con)
        from .asn_db import get_resolver as get_asn_resolver

        asn = get_asn_resolver(getattr(cfg, "asn_tsv_path", None))
        geo = GeoIPResolver(getattr(cfg, "geoip_mmdb_path", None), asn_resolver=asn)
        geo.limit_http_to(PUSH_GEO_HTTP_BUDGET_S)
        try:

            lines: list[tuple[LogSource, str]] = []
            source_ids: list[str] = []
            for src in report.sources:
                source = LogSource(id=src.id, kind=src.kind, parser=src.parser)
                source_ids.append(src.id)
                for ln in src.lines:
                    lines.append((source, ln))

            fetched, inserted = ingest_lines(
                con,
                server_name=server.name,
                server_ip=server.ssh.host,
                lines=lines,
                geo=geo,
                asn=asn,
            )

            # Same resolver: the knocks get whatever is left of the lookup budget
            # after the visitor rows, and reuse the answers those already got.
            _ingest_security(con, server, report, cfg=cfg, geo=geo)
            _ingest_disks(con, server, report)

            import json as _json

            upsert_collector_status(
                con,
                server_name=server.name,
                ok=True,
                fetched_lines=fetched,
                inserted_rows=inserted,
                log_paths=_json.dumps(source_ids),
            )
        finally:
            geo.close()

        node_store.record_report(
            con,
            credential.key_id,
            ip=peer_ip,
            agent_version=report.agent_version,
            clock_skew_s=clock_skew_s,
        )
        return IngestResult(
            server_name=server.name,
            accepted=inserted,
            duplicates=max(0, fetched - inserted - report.rejected_lines),
            rejected=report.rejected_lines,
            clock_skew_s=clock_skew_s,
        )
    finally:
        con.close()


def _recent_snapshot_age_minutes(con, server_name: str) -> float | None:
    """Minutes since this server's last stored posture snapshot, if any."""
    from datetime import datetime, timezone

    row = con.execute(
        "SELECT max(scanned_at_utc) AS latest FROM security_snapshots WHERE server_name = ?",
        (server_name,),
    ).fetchone()
    latest = (row["latest"] if isinstance(row, dict) else row[0]) if row else None
    if not latest:
        return None
    try:
        parsed = datetime.fromisoformat(str(latest).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return (datetime.now(tz=timezone.utc) - parsed).total_seconds() / 60.0


def _pseudo_mount(disk: dict) -> bool:
    """A mount that is not a disk of its own: tmpfs, and Docker's overlays (each repeats the
    root filesystem's numbers, dozens per host)."""
    fs, mount = str(disk.get("filesystem") or ""), str(disk.get("mount") or "")
    return (fs in ("tmpfs", "devtmpfs", "overlay", "shm", "squashfs", "efivarfs", "none")
            or mount.startswith(("/var/lib/docker/", "/run", "/dev", "/sys", "/proc", "/snap/")))


def _ingest_disks(con, server: ServerConfig, report: NodeReport) -> None:
    """The host's disk usage from every report that carries a probe — cheap (one df section, one
    row), unlike the hourly posture snapshot, so an alerter can see a disk fill in minutes."""
    if not report.probe:
        return
    try:
        from .db import now_utc_iso
        from .security.probe import _parse_disks, _split_sections
        from .security.store import init_security_db, save_disks

        disks = [d for d in _parse_disks(_split_sections(report.probe).get("disk", "")) if not _pseudo_mount(d)]
        if disks:
            init_security_db(con)
            save_disks(con, server.name, now_utc_iso(), disks)
    except Exception:
        logger.exception("Could not store the pushed disk usage for %s", server.name)


def _ingest_security(con, server: ServerConfig, report: NodeReport, *, cfg=None,
                     geo: GeoIPResolver | None = None) -> None:
    """Store the probe and port-knock sections, if the agent sent them.

    Rate-limited to the configured scan interval rather than run on every
    report. Correlating port knocks pulls a week of this server's HTTP history,
    which on a host with millions of rows takes long enough that doing it every
    few minutes turned a routine ingest into a gateway timeout — while producing
    a posture reading nobody asked for more often than hourly.
    """
    if not report.probe and not report.knocks:
        return

    from .security.store import init_security_db

    # The age check below reads security_snapshots, which may not exist yet on a
    # database whose first posture data arrives by push rather than by scan.
    init_security_db(con)

    interval = getattr(cfg, "security_scan_interval_minutes", 60) if cfg else 60
    age = _recent_snapshot_age_minutes(con, server.name)
    if age is not None and age < interval:
        return
    if report.probe is None:
        # A knocks-only report stores no snapshot, so the age check above would
        # never advance and every single report would re-run the week-long
        # correlation — the exact cost this limit exists to avoid. Knocks ride
        # along with a probe or they wait for the next one.
        return

    from .db import now_utc_iso
    from .security.audit import audit_snapshot
    from .security.knock_analyzer import enrich_knocks, http_probes_from_db
    from .security.port_knocks import events_from_knock_output
    from .security.probe import snapshot_from_probe_output
    from .security.store import insert_knock_events, save_scan

    scanned_at = now_utc_iso()

    if report.probe:
        try:
            snap = snapshot_from_probe_output(
                report.probe,
                server_name=server.name,
                host=server.ssh.host,
                scanned_at_utc=scanned_at,
            )
            save_scan(con, snap, audit_snapshot(snap), transport="agent-push")
        except Exception:
            # A malformed probe section must not cost us the log lines that came
            # with it — they are already committed by the time we get here.
            logger.exception("Could not store the pushed probe for %s", server.name)

    if report.knocks:
        try:
            own_geo = geo is None
            if own_geo:
                # The configured database, not None: falling back to HTTP means one
                # outbound request per unseen address, which is exactly what the cap
                # below exists to bound.
                from .asn_db import get_resolver as get_asn_resolver

                geo = GeoIPResolver(
                    getattr(cfg, "geoip_mmdb_path", None) if cfg else None,
                    asn_resolver=get_asn_resolver(getattr(cfg, "asn_tsv_path", None) if cfg else None),
                )
            try:
                events = events_from_knock_output(report.knocks)
                if len(events) > MAX_KNOCK_EVENTS_PER_REPORT:
                    # A node chooses this content outright. 512 KiB of minimal
                    # "SRC=… DPT=…" lines is over 20,000 distinct addresses, and
                    # enrichment resolves each one; unbounded, a single report
                    # becomes minutes of outbound lookups.
                    logger.warning(
                        "%s sent %d knock events; keeping the newest %d",
                        server.name, len(events), MAX_KNOCK_EVENTS_PER_REPORT,
                    )
                    events = events[-MAX_KNOCK_EVENTS_PER_REPORT:]
                merged = events + http_probes_from_db(con, server.name, hours=168)
                insert_knock_events(
                    con, server.name, server.ssh.host, enrich_knocks(merged, geo=geo)
                )
            finally:
                if own_geo:
                    geo.close()
        except Exception:
            logger.exception("Could not store pushed port knocks for %s", server.name)


def ingest_remediation(
    cfg: AppConfig,
    credential: NodeCredential,
    doc: dict,
    *,
    clock_skew_s: int = 0,
    peer_ip: str | None = None,
) -> IngestResult:
    """Store a pushed remediation board under the server its credential names.

    Same binding rule as a log report: the conductor is provisioned as its own
    agent-push entry, and the ``component``/``host`` labels inside the document
    are display text. Only the credential decides whose rows these are.
    """
    from .node_remediation import record_remediation

    server = _server_for(cfg, credential.server_name)
    if not server.is_push:
        raise IngestError(
            f"server '{server.name}' is configured as {server.transport}, not agent-push"
        )

    jobs = doc.get("jobs")
    if not isinstance(jobs, list):
        raise IngestError("remediation document has no jobs list")
    if len(jobs) > MAX_REMEDIATION_JOBS:
        raise IngestError(f"remediation document carries more than {MAX_REMEDIATION_JOBS} jobs")

    con = connect_for_config(cfg)
    try:
        counts = record_remediation(con, server_name=server.name, jobs=jobs)
        node_store.record_report(
            con,
            credential.key_id,
            ip=peer_ip,
            agent_version=str(doc.get("agent_version") or "")[:32] or None,
            clock_skew_s=clock_skew_s,
        )
    finally:
        con.close()

    return IngestResult(
        server_name=server.name,
        accepted=counts.accepted,
        duplicates=counts.duplicates,
        rejected=counts.rejected,
        clock_skew_s=clock_skew_s,
    )


def authenticate_request(
    cfg: AppConfig, headers, body: bytes
) -> tuple[NodeCredential, int]:
    """Verify a report's signature. Cheap: one row lookup and one HMAC.

    Split from the ingest so a caller can admit work *after* deciding the caller
    is real. Letting an unauthenticated request occupy an ingest slot would let
    anyone with a socket fill them all and stop the fleet reporting.
    """
    con = connect_for_config(cfg)
    try:
        node_store.init_node_db(con)
        credential, _seq, skew = authenticate(con, headers, body)
        return credential, skew
    finally:
        con.close()


def ingest_authenticated(
    cfg: AppConfig,
    credential: NodeCredential,
    headers,
    body: bytes,
    *,
    clock_skew_s: int = 0,
    peer_ip: str | None = None,
) -> IngestResult:
    """Decompress, validate and store an already-authenticated report."""
    import json

    payload = body
    if (headers.get("Content-Encoding") or "").strip().lower() == "gzip":
        from .node_protocol import decompress

        payload = decompress(body)

    try:
        doc = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise IngestError("body is not valid JSON") from e
    except RecursionError as e:
        raise IngestError("body is nested too deeply") from e

    if isinstance(doc, dict) and doc.get("kind") == REMEDIATION_KIND:
        return ingest_remediation(
            cfg, credential, doc, clock_skew_s=clock_skew_s, peer_ip=peer_ip
        )

    report = parse_report(doc)
    return ingest_report(cfg, credential, report, clock_skew_s=clock_skew_s, peer_ip=peer_ip)


def handle_report(cfg: AppConfig, headers, body: bytes, *, peer_ip: str | None = None) -> IngestResult:
    """Authenticate and ingest in one call. Convenience for tests and the CLI.

    ``body`` is the raw request body exactly as received. The signature covers
    these bytes, so verification happens before decompression and before the
    JSON parser — an unauthenticated peer never reaches either.
    """
    credential, skew = authenticate_request(cfg, headers, body)
    return ingest_authenticated(
        cfg, credential, headers, body, clock_skew_s=skew, peer_ip=peer_ip
    )


def handle_enroll(cfg: AppConfig, doc: dict, *, peer_ip: str | None = None) -> dict:
    """Exchange a single-use ticket for a credential.

    The secret is minted here and returned once, over TLS. It is never written
    into the installer, so a downloaded installer that leaks is a burnt ticket
    rather than a permanent key.
    """
    import base64

    ticket = str((doc or {}).get("ticket") or "").strip()
    hostname = str((doc or {}).get("hostname") or "")[:128]
    if not ticket or len(ticket) > 128:
        raise AuthError("malformed ticket")

    con = connect_for_config(cfg)
    try:
        node_store.init_node_db(con)
        server_name = node_store.claim_ticket(con, ticket)
        if not server_name:
            raise AuthError("ticket is unknown, expired, or already used")

        key_id, secret = node_store.issue_credential(con, server_name)
        node_store.record_event(
            con,
            kind="enrolled",
            key_id=key_id,
            server_name=server_name,
            detail=f"hostname={hostname} ip={peer_ip}",
        )
        con.commit()
        return {
            "key_id": key_id,
            "secret_b64": base64.b64encode(secret).decode("ascii"),
            "server_name": server_name,
        }
    finally:
        con.close()
