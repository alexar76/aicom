"""Storage for remediation boards pushed by the conductor.

The conductor runs somewhere else — its own image, its own host, its own disk —
and its ``jobs.jsonl`` is not reachable from the dashboard. So it pushes a
bounded summary of each job over the same signed node channel the fleet uses for
logs, and this module is where that summary lands.

Three properties are the whole design:

* **Identity, not arrival.** One row per (server, finding), keyed on the
  finding id. A pushed summary is at-least-once by construction — the sequence
  number is spent during authentication, so a pusher that times out re-sends the
  same content under the next number — and every other writer in this database
  survives that only because it is idempotent on content. This one keys on the
  finding and treats ``(state, attempts)`` as the revision: a replay updates the
  row it already owns and is reported as a duplicate, never appended.
* **The credential decides whose row it is.** ``server_name`` comes from the
  caller, which resolved it from the authenticated key id. The pushed
  ``component``/``host`` labels are display text and have no say in it.
* **An allowlist, not a scrub.** A summary carries third-party text: MOMUS
  verdict details, Factory errors, a component name that may be an internal
  host label. Only the sections named in :data:`_SECTIONS` survive, every string
  is scrubbed and bounded, and the raw MOMUS ticket — unbounded and
  attacker-influenced — has no way in at all. What is left is stored verbatim as
  JSON next to the indexed columns, so the board can show a timeline the schema
  does not model.

Read-only for the dashboard, and there is no path back to the conductor. The
board here is a mirror; the conductor is the authority.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Iterable

from .db import now_utc_iso
from .db_connection import DbConnection

logger = logging.getLogger("skopos.node")

#: The eight states a job can be in — mirrored from
#: ``skopos.remediation.jobs.JobState`` rather than imported, because importing
#: it executes ``skopos.remediation.__init__`` and that constructs the whole
#: control plane (conductor, Factory and MOMUS clients, operator token) inside
#: whichever process happens to be reading this table.
REMEDIATION_STATES = frozenset({
    "received", "fixing", "retesting", "deploying", "verifying",
    "done", "failed", "escalated",
})

#: Reached the end of the loop, one way or another. Everything else is in flight.
TERMINAL_STATES = ("done", "failed", "escalated")

#: History is the timeline copy the board renders; it is also the only unbounded
#: list in a summary. Newest entries win.
MAX_HISTORY_ENTRIES = 40

#: A single stored summary. Well past what a bounded job needs, small enough that
#: a thousand of them is still a few megabytes.
MAX_SUMMARY_BYTES = 16_384

_MAX_TEXT = 240
_MAX_LABEL = 64
_MAX_ID = 128

# Same two rules the A2A observer applies to agent traffic, for the same reason:
# verdict details and Factory errors are third-party text that ends up on a page
# and in a log line. Duplicated rather than imported — see REMEDIATION_STATES.
_CTRL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")
_SECRETISH = re.compile(r"(?i)(authorization|api[_-]?key|token|secret|password)\s*[:=]\s*\S+")

#: A label that turns out to be a URL or a bare address is infrastructure detail,
#: not a name: ``component`` doubles as the deploy host, and this repo has already
#: leaked private hosts into places that were only ever meant to hold labels.
_URLISH = re.compile(r"[a-zA-Z][a-zA-Z0-9+.-]*://|@")
_ADDRESSISH = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$|^[0-9a-fA-F:]*:[0-9a-fA-F:]*:")

#: The only sections a pushed summary may carry, and the only keys inside them.
#: An allowlist because the alternative is trusting whatever a future conductor
#: decides to serialise: ``ticket`` is not here, so the raw MOMUS ticket cannot
#: reach the database even if the whole ``Job`` is pushed verbatim.
_SECTIONS: dict[str, tuple[str, ...]] = {
    "gate_verdict": (
        "fixed", "outcome", "detail", "checked_at", "verifier_pubkey", "signature",
    ),
    "post_deploy_verdict": (
        "fixed", "outcome", "detail", "checked_at", "verifier_pubkey", "signature",
    ),
    "deploy": (
        "order_id", "service", "image", "conductor_pubkey", "signature", "created_at",
    ),
    "queue": ("state", "claimed_by", "claimed_at"),
    "agent_result": ("deployed", "refused", "reason", "executed_at"),
}

#: Values in these keys are names of things, and are held to the label rules.
_LABEL_KEYS = frozenset({"service", "image", "claimed_by", "host"})


REMEDIATION_SCHEMA_SQLITE = """
CREATE TABLE IF NOT EXISTS remediation_jobs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  server_name TEXT NOT NULL,
  finding_id TEXT NOT NULL,
  component TEXT,
  probe TEXT,
  severity TEXT,
  route TEXT,
  state TEXT NOT NULL,
  attempts INTEGER NOT NULL DEFAULT 0,
  gate_fixed INTEGER,
  gate_outcome TEXT,
  deploy_order_id TEXT,
  deployed INTEGER,
  created_at_utc TEXT,
  updated_at_utc TEXT,
  received_at_utc TEXT NOT NULL,
  summary_json TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_remediation_jobs_finding
  ON remediation_jobs(server_name, finding_id);
CREATE INDEX IF NOT EXISTS idx_remediation_jobs_updated
  ON remediation_jobs(updated_at_utc DESC);
CREATE INDEX IF NOT EXISTS idx_remediation_jobs_state
  ON remediation_jobs(state);
"""

REMEDIATION_SCHEMA_POSTGRES = """
CREATE TABLE IF NOT EXISTS remediation_jobs (
  id BIGSERIAL PRIMARY KEY,
  server_name TEXT NOT NULL,
  finding_id TEXT NOT NULL,
  component TEXT,
  probe TEXT,
  severity TEXT,
  route TEXT,
  state TEXT NOT NULL,
  attempts INTEGER NOT NULL DEFAULT 0,
  gate_fixed BOOLEAN,
  gate_outcome TEXT,
  deploy_order_id TEXT,
  deployed BOOLEAN,
  created_at_utc TEXT,
  updated_at_utc TEXT,
  received_at_utc TEXT NOT NULL,
  summary_json TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_remediation_jobs_finding
  ON remediation_jobs(server_name, finding_id);
CREATE INDEX IF NOT EXISTS idx_remediation_jobs_updated
  ON remediation_jobs(updated_at_utc DESC);
CREATE INDEX IF NOT EXISTS idx_remediation_jobs_state
  ON remediation_jobs(state);
"""

_COLUMNS = (
    "server_name", "finding_id", "component", "probe", "severity", "route",
    "state", "attempts", "gate_fixed", "gate_outcome", "deploy_order_id",
    "deployed", "created_at_utc", "updated_at_utc", "received_at_utc",
    "summary_json",
)


def init_remediation_db(con: DbConnection) -> None:
    script = (
        REMEDIATION_SCHEMA_POSTGRES if con.backend == "postgresql"
        else REMEDIATION_SCHEMA_SQLITE
    )
    con.executescript(script)
    con.commit()


@dataclass(frozen=True)
class RemediationCounts:
    """Same three counters the log ingest reports, with the same meanings."""

    accepted: int = 0
    duplicates: int = 0
    rejected: int = 0


# --- Sanitising -------------------------------------------------------------

def _text(value: Any, *, limit: int = _MAX_TEXT) -> str:
    if value is None:
        # Not json.dumps' "null": callers test the result for emptiness to decide
        # between a value and a NULL column, and that string is neither.
        return ""
    s = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    s = _SECRETISH.sub(r"\1=<redacted>", s)
    s = _CTRL.sub("", s)
    return re.sub(r"\s+", " ", s).strip()[:limit]


def _label(value: Any) -> str:
    """A name for a service, image or host — with the address forms removed."""
    s = _text(value, limit=_MAX_LABEL)
    if not s:
        return ""
    if _URLISH.search(s) or _ADDRESSISH.match(s):
        return "<redacted>"
    return s


def _flag(value: Any) -> bool | None:
    """Tri-state: a missing verdict is not a negative one."""
    if value is None:
        return None
    return bool(value)


def _section(raw: Any, keys: tuple[str, ...]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    out: dict[str, Any] = {}
    for key in keys:
        if key not in raw:
            continue
        value = raw[key]
        if key == "signature":
            # Signatures and verifying keys are public by construction, so they
            # are safe to keep — but only the value, and only enough of it to
            # recognise, never a whole nested envelope.
            value = value.get("value") if isinstance(value, dict) else value
            out[key] = _text(value, limit=_MAX_LABEL)
        elif isinstance(value, bool) or value is None:
            out[key] = value
        elif isinstance(value, (int, float)):
            out[key] = value
        elif key in _LABEL_KEYS:
            out[key] = _label(value)
        else:
            out[key] = _text(value)
    return out


def _history(raw: Any) -> list[dict[str, str]]:
    if not isinstance(raw, list):
        return []
    entries = []
    for item in raw[-MAX_HISTORY_ENTRIES:]:
        if not isinstance(item, dict):
            continue
        entries.append({
            "ts": _text(item.get("ts"), limit=32),
            "state": _text(item.get("state"), limit=32),
            # The notes interpolate MOMUS verdict details and Factory errors —
            # the one place in a summary where a hostile advisory can reach a page.
            "note": _text(item.get("note")),
        })
    return entries


def _summary_json(summary: dict[str, Any]) -> str:
    blob = json.dumps(summary, ensure_ascii=False, sort_keys=True)
    if len(blob) <= MAX_SUMMARY_BYTES:
        return blob
    # Shed the timeline first: it is the only part that grows, and the sections
    # are what the detail view cannot reconstruct from the columns.
    trimmed = {k: v for k, v in summary.items() if k != "history"}
    trimmed["history_truncated"] = True
    blob = json.dumps(trimmed, ensure_ascii=False, sort_keys=True)
    if len(blob) <= MAX_SUMMARY_BYTES:
        return blob
    return json.dumps(
        {"finding_id": summary.get("finding_id", ""), "truncated": True},
        ensure_ascii=False, sort_keys=True,
    )


def normalize_summary(raw: Any, *, server_name: str) -> dict[str, Any] | None:
    """Turn one pushed job summary into a row, or ``None`` if it is not one.

    Rejects rather than coerces on the two fields the rest of this module is
    keyed on: a summary with no finding id has no identity, and one whose state
    is not a known state cannot be counted or labelled — the board would render
    the raw value as a missing translation key.
    """
    if not isinstance(raw, dict):
        return None
    finding_id = _text(raw.get("finding_id"), limit=_MAX_ID)
    state = _text(raw.get("state"), limit=32)
    if not finding_id or state not in REMEDIATION_STATES:
        return None

    try:
        attempts = max(0, min(int(raw.get("attempts") or 0), 99))
    except (TypeError, ValueError):
        attempts = 0

    summary: dict[str, Any] = {
        "finding_id": finding_id,
        "component": _label(raw.get("component")),
        "probe": _text(raw.get("probe"), limit=_MAX_LABEL),
        "severity": _text(raw.get("severity"), limit=32),
        "route": _text(raw.get("route"), limit=32),
        "state": state,
        "attempts": attempts,
        "created_at": _text(raw.get("created_at"), limit=32),
        "updated_at": _text(raw.get("updated_at"), limit=32),
        "history": _history(raw.get("history")),
    }
    for name, keys in _SECTIONS.items():
        section = _section(raw.get(name), keys)
        if section:
            summary[name] = section

    gate = summary.get("gate_verdict") or {}
    deploy = summary.get("deploy") or {}
    agent = summary.get("agent_result") or {}
    return {
        "server_name": server_name,
        "finding_id": finding_id,
        "component": summary["component"],
        "probe": summary["probe"],
        "severity": summary["severity"],
        "route": summary["route"],
        "state": state,
        "attempts": attempts,
        "gate_fixed": _flag(gate.get("fixed")),
        "gate_outcome": _text(gate.get("outcome"), limit=32) or None,
        "deploy_order_id": _text(deploy.get("order_id"), limit=_MAX_ID) or None,
        "deployed": _flag(agent.get("deployed")),
        "created_at_utc": summary["created_at"] or None,
        # Empty rather than "now" on purpose: the freshness guard in
        # record_remediation compares this against the stored value, and a
        # summary that carries no clock of its own must not be able to claim it
        # is newer than one that does.
        "updated_at_utc": summary["updated_at"] or summary["created_at"] or "",
        "received_at_utc": now_utc_iso(),
        "summary_json": _summary_json(summary),
    }


# --- Writing ----------------------------------------------------------------

def _changed(cur) -> bool:
    return int(getattr(cur, "rowcount", 0) or 0) > 0


def record_remediation(
    con: DbConnection,
    *,
    server_name: str,
    jobs: Iterable[Any],
) -> RemediationCounts:
    """Store a pushed board under ``server_name``, once per finding.

    ``server_name`` is the caller's, resolved from the authenticated credential.
    Nothing in ``jobs`` can move a row to another server.
    """
    init_remediation_db(con)
    accepted = duplicates = rejected = 0

    for raw in jobs or []:
        row = normalize_summary(raw, server_name=server_name)
        if row is None:
            rejected += 1
            continue

        existing = con.execute(
            "SELECT state, attempts, updated_at_utc FROM remediation_jobs "
            "WHERE server_name = ? AND finding_id = ?",
            (server_name, row["finding_id"]),
        ).fetchone()

        if existing is None:
            cols = ", ".join(_COLUMNS)
            ph = ",".join("?" * len(_COLUMNS))
            cur = con.execute(
                f"INSERT INTO remediation_jobs({cols}) VALUES ({ph}) ON CONFLICT DO NOTHING",
                tuple(row[c] for c in _COLUMNS),
            )
            if _changed(cur):
                accepted += 1
            else:
                # Lost the race with a concurrent push of the same finding: the
                # row exists and says the same thing, which is the definition of
                # a duplicate here, not a failure.
                duplicates += 1
            continue

        prev = existing if isinstance(existing, dict) else {
            "state": existing[0], "attempts": existing[1], "updated_at_utc": existing[2],
        }
        # The revision. Two pushes agreeing on state and attempts carry the same
        # job, whatever else moved in the envelope around them.
        replay = (
            str(prev["state"]) == row["state"]
            and int(prev["attempts"] or 0) == row["attempts"]
        )

        assignments = ", ".join(f"{c} = ?" for c in _COLUMNS if c != "server_name")
        cur = con.execute(
            f"UPDATE remediation_jobs SET {assignments} "
            "WHERE server_name = ? AND finding_id = ? AND updated_at_utc <= ?",
            tuple(row[c] for c in _COLUMNS if c != "server_name")
            + (server_name, row["finding_id"], row["updated_at_utc"]),
        )
        if not _changed(cur):
            # The stored row is newer. A pusher that retries after a timeout
            # re-sends an old window under a fresh sequence number, and without
            # this guard that re-send would walk a finished job back to "fixing".
            logger.info(
                "remediation push for %s/%s is older than the stored row; kept %s",
                server_name, row["finding_id"], prev["state"],
            )
            duplicates += 1
        elif replay:
            duplicates += 1
        else:
            accepted += 1

    con.commit()
    return RemediationCounts(accepted=accepted, duplicates=duplicates, rejected=rejected)


# --- Reading ----------------------------------------------------------------

def _read(row) -> dict[str, Any]:
    out = dict(row)
    out["gate_fixed"] = _flag(out.get("gate_fixed"))
    out["deployed"] = _flag(out.get("deployed"))
    try:
        out["summary"] = json.loads(out.get("summary_json") or "{}")
    except json.JSONDecodeError:
        out["summary"] = {}
    return out


def recent_jobs(
    con: DbConnection,
    *,
    limit: int = 50,
    server_name: str | None = None,
) -> list[dict[str, Any]]:
    """Newest-first board, bounded. ``summary`` holds the parsed detail."""
    init_remediation_db(con)
    params: list = []
    where = ""
    if server_name:
        where = "WHERE server_name = ?"
        params.append(server_name)
    params.append(max(1, min(int(limit), 500)))
    rows = con.execute(
        f"""
        SELECT * FROM remediation_jobs
        {where}
        ORDER BY updated_at_utc DESC, id DESC
        LIMIT ?
        """,
        params,
    ).fetchall()
    return [_read(r) for r in rows]


def stats(con: DbConnection, *, server_name: str | None = None) -> dict[str, Any]:
    """Board totals. Answers on an empty — or brand new — database."""
    init_remediation_db(con)
    params: list = []
    where = ""
    if server_name:
        where = "WHERE server_name = ?"
        params.append(server_name)

    by_state: dict[str, int] = {}
    for r in con.execute(
        f"SELECT state, COUNT(*) AS cnt FROM remediation_jobs {where} GROUP BY state",
        params,
    ).fetchall():
        d = dict(r)
        by_state[str(d["state"])] = int(d["cnt"] or 0)

    row = dict(
        con.execute(
            f"SELECT MAX(updated_at_utc) AS last_update FROM remediation_jobs {where}",
            params,
        ).fetchone()
    )
    total = sum(by_state.values())
    terminal = sum(by_state.get(s, 0) for s in TERMINAL_STATES)
    return {
        "total": total,
        "by_state": by_state,
        "open": total - terminal,
        "done": by_state.get("done", 0),
        "failed": by_state.get("failed", 0),
        "escalated": by_state.get("escalated", 0),
        "last_update_utc": row.get("last_update") or None,
    }
