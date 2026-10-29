"""Hand SKOPOS's security findings to MOMUS, so they reach the fix loop.

MOMUS already has the receiving half — `momus.intel.skopos_bridge` translates a SKOPOS
export into MOMUS findings, `POST /skopos/report` accepts one — and for a while nothing
on this side ever called it. The bridge was a door with no road to it.

This is the road. It reads the newest security snapshot per server out of the SKOPOS
database and posts it. It does not scan, does not judge, and does not decide what gets
fixed: whether a finding becomes a ticket is MOMUS's call, and whether that ticket is
dispatched without a human is the autopilot's policy (`skopos.remediation.autopilot`).

Three things it is careful about:

* **One push per snapshot.** MOMUS counts how many separate scans rediscovered a bug —
  `seen_count` — and the autopilot will not dispatch until a defect has reproduced across
  N of them. Re-posting the same snapshot every hour would manufacture that evidence out
  of a single observation, so the id of the last snapshot sent is remembered per server
  and an unchanged snapshot is skipped. Force it with ``--resend`` when re-importing into
  a MOMUS that lost its corpus.
* **Fail closed.** No URL or no operator token means nothing is sent and the caller is told
  why. A pusher that silently did nothing would look exactly like a fleet with no findings.
* **No severity filter here.** `info` is dropped by the bridge on the MOMUS side, which is
  where that rule already lives; duplicating it here would let the two drift apart.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any

import httpx

from ..atomic_io import write_text_atomic
from ..db import DbConnection
from .store import findings_for_snapshot, init_security_db, latest_snapshots

#: Where MOMUS listens. `AUTOPILOT_MOMUS_URL` is the same address the autopilot already
#: talks to on this host, so a deployment that configured one has configured both.
URL_ENV = "SKOPOS_MOMUS_URL"
FALLBACK_URL_ENV = "AUTOPILOT_MOMUS_URL"
TOKEN_ENV = "MOMUS_OPERATOR_TOKEN"

#: `/skopos/report` writes into the queue that opens remediation tickets, so MOMUS gates it
#: on the operator header rather than serving it publicly.
OPERATOR_HEADER = "x-momus-operator"

TIMEOUT_S = 30.0


def momus_url() -> str:
    raw = (os.environ.get(URL_ENV) or os.environ.get(FALLBACK_URL_ENV) or "").strip()
    return raw.rstrip("/")


def operator_token() -> str:
    return (os.environ.get(TOKEN_ENV) or "").strip()


@dataclass
class PushResult:
    server_name: str
    pushed: bool
    reason: str = ""
    snapshot_id: int | None = None
    findings_sent: int = 0
    imported: int | None = None
    http_status: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "server": self.server_name,
            "pushed": self.pushed,
            "reason": self.reason,
            "snapshot_id": self.snapshot_id,
            "findings_sent": self.findings_sent,
            "imported": self.imported,
            "http_status": self.http_status,
        }


@dataclass
class MomusPusher:
    url: str = field(default_factory=momus_url)
    token: str = field(default_factory=operator_token)

    def configured(self) -> tuple[bool, str]:
        if not self.url:
            return False, f"{URL_ENV} is unset — SKOPOS does not know where MOMUS is"
        if not self.token:
            return False, f"{TOKEN_ENV} is unset — MOMUS refuses /skopos/report without it"
        return True, ""

    def post(self, document: dict[str, Any]) -> tuple[int | None, dict[str, Any], str]:
        """POST one export. Returns (status, body, error) — never raises on a dead MOMUS."""
        try:
            r = httpx.post(
                f"{self.url}/skopos/report",
                json=document,
                headers={OPERATOR_HEADER: self.token},
                timeout=TIMEOUT_S,
            )
        except httpx.HTTPError as exc:
            return None, {}, f"MOMUS unreachable: {type(exc).__name__}"
        try:
            body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        except ValueError:
            body = {}
        if r.status_code >= 400:
            detail = str(body.get("detail") or "")[:200]
            return r.status_code, body, f"MOMUS refused it: HTTP {r.status_code} {detail}".strip()
        return r.status_code, body, ""


def build_document(con: DbConnection, snapshot: dict) -> dict[str, Any]:
    """The export shape `momus.intel.skopos_bridge.import_findings` reads.

    ``snapshot_id`` is ours, not MOMUS's — it ignores the extra key. It is here so a
    puller on another host can tell a re-scan from a repeat of the same scan without
    having our database, which is the whole point of the read-only export below.
    """
    findings = findings_for_snapshot(con, int(snapshot["id"]))
    return {
        "server": snapshot["server_name"],
        "snapshot_id": int(snapshot["id"]),
        "observed_at": snapshot.get("scanned_at_utc") or "",
        "findings": [
            {
                "severity": f.get("severity"),
                "category": f.get("category"),
                "title": f.get("title"),
                "detail": f.get("detail"),
                "recommendation": f.get("recommendation"),
            }
            for f in findings
        ],
    }


def push_latest(
    con: DbConnection,
    *,
    server_names: list[str] | None = None,
    resend: bool = False,
    pusher: MomusPusher | None = None,
) -> list[PushResult]:
    """Send the newest snapshot of each server MOMUS has not been told about yet."""
    init_security_db(con)
    pusher = pusher or MomusPusher()
    ok, why = pusher.configured()
    snapshots = latest_snapshots(con, server_names)
    if not ok:
        # Named per server rather than once, so `skoposctl momus-push` prints the same
        # shape whether it is misconfigured or merely idle.
        return [PushResult(s["server_name"], False, why, snapshot_id=int(s["id"]))
                for s in snapshots] or [PushResult("(no servers)", False, why)]

    results: list[PushResult] = []
    for snap in snapshots:
        server = snap["server_name"]
        snapshot_id = int(snap["id"])
        if not resend and last_pushed_snapshot(con, server) == snapshot_id:
            results.append(PushResult(server, False, "already sent — no scan since then",
                                      snapshot_id=snapshot_id))
            continue
        document = build_document(con, snap)
        status, body, error = pusher.post(document)
        if error:
            results.append(PushResult(server, False, error, snapshot_id=snapshot_id,
                                      findings_sent=len(document["findings"]),
                                      http_status=status))
            continue
        imported = body.get("imported")
        # Recorded only after MOMUS accepted it. Marking a snapshot sent on a failed post
        # would skip it for ever, and the next scan would be the first MOMUS ever heard of
        # that host.
        record_push(con, server, snapshot_id, len(document["findings"]),
                    int(imported) if isinstance(imported, int) else 0)
        results.append(PushResult(server, True, "", snapshot_id=snapshot_id,
                                  findings_sent=len(document["findings"]),
                                  imported=imported if isinstance(imported, int) else None,
                                  http_status=status))
    return results


# ── what has already been sent ──────────────────────────────────────────────────
def last_pushed_snapshot(con: DbConnection, server_name: str) -> int | None:
    init_security_db(con)
    row = con.execute(
        "SELECT snapshot_id FROM momus_pushes WHERE server_name = ? "
        "ORDER BY snapshot_id DESC LIMIT 1",
        (server_name,),
    ).fetchone()
    if not row:
        return None
    value = row["snapshot_id"] if isinstance(row, dict) else row[0]
    return int(value)


def record_push(con: DbConnection, server_name: str, snapshot_id: int,
                findings_sent: int, imported: int) -> None:
    from ..db import now_utc_iso

    init_security_db(con)
    con.execute(
        "INSERT INTO momus_pushes(server_name, snapshot_id, findings_sent, imported, pushed_at_utc) "
        "VALUES (?,?,?,?,?) ON CONFLICT DO NOTHING",
        (server_name, snapshot_id, findings_sent, imported, now_utc_iso()),
    )
    con.commit()


# ── running it on a schedule ────────────────────────────────────────────────────
#: Opt-in, and deliberately NOT inferred from "the URL happens to be set". The autopilot
#: already holds a MOMUS address for its own errands; treating that as consent to start
#: reporting the whole fleet's posture would turn a config value into a decision.
ENABLED_ENV = "SKOPOS_MOMUS_PUSH"

CONFIG_PATH_ENV = "SKOPOS_CONFIG_PATH"
INTERVAL_ENV = "SKOPOS_MOMUS_PUSH_INTERVAL_S"


def is_enabled() -> bool:
    return (os.environ.get(ENABLED_ENV) or "").strip().lower() in ("1", "true", "yes", "on")


def push_now(*, config_path: str | None = None, resend: bool = False) -> list[PushResult]:
    """Open the SKOPOS database, push, close. For daemons that hold no connection."""
    from ..config import load_config
    from ..db_connection import connect_for_config

    path = config_path or os.environ.get(CONFIG_PATH_ENV) or "./servers.yaml"
    cfg = load_config(path)
    con = connect_for_config(cfg)
    try:
        return push_latest(con, resend=resend)
    finally:
        con.close()


def run_forever() -> None:  # pragma: no cover - long-running loop
    import logging
    import time

    log = logging.getLogger("skopos.momus_push")
    interval = float(os.environ.get(INTERVAL_ENV) or 900)
    while True:
        try:
            for r in push_now():
                if r.pushed:
                    log.info("pushed %s snapshot=%s findings=%d imported=%s",
                             r.server_name, r.snapshot_id, r.findings_sent, r.imported)
                elif not r.reason.startswith("already sent"):
                    log.warning("%s: %s", r.server_name, r.reason)
        except Exception as exc:  # noqa: BLE001 - a courier that dies must not take the host
            log.warning("push pass failed: %s", type(exc).__name__)
        time.sleep(interval)


def main() -> None:  # pragma: no cover - process entrypoint
    import logging

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    log = logging.getLogger("skopos.momus_push")
    pusher = MomusPusher()
    ok, why = pusher.configured()
    log.info("momus-push starting: momus=%s enabled=%s", pusher.url or "(unset)", is_enabled())
    if not ok:
        log.warning("%s — nothing will be sent", why)
    if not is_enabled():
        log.warning("%s is not set — set it to 1 to report findings to MOMUS", ENABLED_ENV)
    run_forever()


if __name__ == "__main__":  # pragma: no cover
    main()


# ── the cross-host path ─────────────────────────────────────────────────────────
#
# SKOPOS and MOMUS do not live on the same machine, and neither can open a connection
# to the other: MOMUS binds to loopback and its public edge REFUSES every route that
# makes it act — /scan, /retest, /remediate, /a2a/tasks all return 404 there, stated in
# the config as a deliberate second layer behind the operator token. /skopos/report is
# one of those routes, so posting to it from another host is not a matter of carrying
# the right token.
#
# So the direction is inverted. SKOPOS publishes what it found, read-only and behind
# its own token; the machine that CAN reach MOMUS pulls that and posts it over
# loopback. Reads leave SKOPOS, writes stay inside MOMUS, and neither host gains a
# shell or a credential on the other.

EXPORT_URL_ENV = "SKOPOS_EXPORT_URL"
EXPORT_TOKEN_ENV = "SKOPOS_EXPORT_TOKEN"
#: Where the puller remembers which snapshot it last delivered, per server. Without a
#: database of its own it would otherwise re-send the same scan on every tick and
#: inflate the very sighting count MOMUS uses to decide whether a defect is real.
SEEN_PATH_ENV = "SKOPOS_MOMUS_PUSH_STATE"
DEFAULT_SEEN_PATH = "/var/lib/skopos-autopilot/momus-push.json"


def fetch_export(url: str, token: str, *, timeout: float = TIMEOUT_S) -> list[dict[str, Any]]:
    """Read the documents SKOPOS publishes. Raises httpx.HTTPError if it cannot."""
    r = httpx.get(url, headers={"X-Skopos-Export-Token": token}, timeout=timeout)
    r.raise_for_status()
    body = r.json() or {}
    documents = body.get("documents")
    return [d for d in documents or [] if isinstance(d, dict)]


def _load_seen(path: str) -> dict[str, int]:
    try:
        with open(path, encoding="utf-8") as fh:
            raw = json.load(fh)
    except (OSError, ValueError):
        return {}
    return {str(k): int(v) for k, v in raw.items() if isinstance(v, int)}


def _save_seen(path: str, seen: dict[str, int]) -> None:
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        write_text_atomic(path, json.dumps(seen, sort_keys=True))
    except OSError:
        # A puller that cannot remember still delivers; it just re-sends next time.
        # Losing a push because the state file is unwritable would be the worse trade.
        pass


def push_remote(
    *,
    export_url: str | None = None,
    export_token: str | None = None,
    seen_path: str | None = None,
    resend: bool = False,
    pusher: MomusPusher | None = None,
) -> list[PushResult]:
    """Pull SKOPOS's published findings and post them to MOMUS. For the MOMUS host."""
    url = (export_url if export_url is not None else os.environ.get(EXPORT_URL_ENV, "")).strip()
    token = (export_token if export_token is not None
             else os.environ.get(EXPORT_TOKEN_ENV, "")).strip()
    path = seen_path or os.environ.get(SEEN_PATH_ENV) or DEFAULT_SEEN_PATH
    pusher = pusher or MomusPusher()

    if not url:
        return [PushResult("(remote)", False, f"{EXPORT_URL_ENV} is unset")]
    if not token:
        return [PushResult("(remote)", False, f"{EXPORT_TOKEN_ENV} is unset")]
    ok, why = pusher.configured()
    if not ok:
        return [PushResult("(remote)", False, why)]

    try:
        documents = fetch_export(url, token)
    except httpx.HTTPError as exc:
        return [PushResult("(remote)", False, f"SKOPOS export unreachable: {type(exc).__name__}")]
    except ValueError:
        return [PushResult("(remote)", False, "SKOPOS export was not JSON")]

    seen = _load_seen(path)
    results: list[PushResult] = []
    for document in documents:
        server = str(document.get("server") or "")
        snapshot_id = document.get("snapshot_id")
        snapshot_id = int(snapshot_id) if isinstance(snapshot_id, int) else None
        if not server:
            continue
        if not resend and snapshot_id is not None and seen.get(server) == snapshot_id:
            results.append(PushResult(server, False, "already sent — no scan since then",
                                      snapshot_id=snapshot_id))
            continue
        status, body, error = pusher.post(document)
        sent = len(document.get("findings") or [])
        if error:
            results.append(PushResult(server, False, error, snapshot_id=snapshot_id,
                                      findings_sent=sent, http_status=status))
            continue
        if snapshot_id is not None:
            seen[server] = snapshot_id
        imported = body.get("imported")
        results.append(PushResult(server, True, "", snapshot_id=snapshot_id,
                                  findings_sent=sent,
                                  imported=imported if isinstance(imported, int) else None,
                                  http_status=status))
    _save_seen(path, seen)
    return results
