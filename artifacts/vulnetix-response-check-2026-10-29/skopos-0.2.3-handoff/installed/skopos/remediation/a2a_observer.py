"""A2A wire observer — SKOPOS watching the agents talk to each other.

SKOPOS is the fleet's observability satellite, so agent↔agent traffic belongs here. MCP calls are
agent→tool and already show up as ordinary HTTP; A2A is different — it carries *delegations*
between peers (MOMUS asking SKOPOS to remediate, SKOPOS asking MOMUS to re-test as a deploy gate),
and those are the interactions an operator actually needs to see: who asked whom to do what, was it
accepted, how long did it take, what came back.

Every envelope is recorded in both directions:

    IN   a peer delegated a task to us          (MOMUS → SKOPOS: "remediate this finding")
    OUT  we delegated a task to a peer          (SKOPOS → MOMUS: "re-test finding X")

Two deliberate constraints, because A2A payloads are partly attacker-influenced (a finding title
can quote a hostile advisory):

  * we store a BOUNDED, SCRUBBED summary, never the raw envelope — no unbounded text, no control
    characters, no room for a log-injection or a terminal escape to ride along;
  * we never store credentials or tokens; the observer records the shape of the conversation
    (peer, skill, state, timing, artifact kinds), not its secrets.

SQLite so the dashboard can query and rank it, and so a restart keeps the history.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from typing import Any, Iterator

_SCHEMA = """
CREATE TABLE IF NOT EXISTS a2a_events (
    event_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    ts         TEXT NOT NULL,
    direction  TEXT NOT NULL,          -- 'in' | 'out'
    peer       TEXT NOT NULL,          -- the other agent (momus / skopos / factory / …)
    skill      TEXT NOT NULL,          -- remediate / retest / scan / selfaudit
    task_id    TEXT,
    state      TEXT,                   -- submitted|working|completed|failed|rejected
    ok         INTEGER NOT NULL DEFAULT 1,
    latency_ms INTEGER,
    finding_id TEXT,
    summary    TEXT NOT NULL,          -- bounded, scrubbed
    artifacts  TEXT                    -- JSON list of artifact kinds only, never their contents
);
CREATE INDEX IF NOT EXISTS ix_a2a_ts    ON a2a_events(ts);
CREATE INDEX IF NOT EXISTS ix_a2a_peer  ON a2a_events(peer);
CREATE INDEX IF NOT EXISTS ix_a2a_skill ON a2a_events(skill);
"""

# Strip control characters and cap length: A2A text is partly untrusted.
_CTRL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")
_SECRETISH = re.compile(r"(?i)(authorization|api[_-]?key|token|secret|password)\s*[:=]\s*\S+")


def scrub(text: Any, *, limit: int = 240) -> str:
    s = text if isinstance(text, str) else json.dumps(text, ensure_ascii=False, default=str)
    s = _SECRETISH.sub(r"\1=<redacted>", s)
    s = _CTRL.sub("", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s[:limit]


@dataclass
class A2AEvent:
    direction: str
    peer: str
    skill: str
    task_id: str = ""
    state: str = ""
    ok: bool = True
    latency_ms: int | None = None
    finding_id: str = ""
    summary: str = ""
    artifacts: list[str] = field(default_factory=list)
    ts: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class A2AObserver:
    def __init__(self, data_dir: str = "data/remediation"):
        os.makedirs(data_dir, exist_ok=True)
        self._path = os.path.join(data_dir, "a2a_events.db")
        with self._conn() as con:
            con.executescript(_SCHEMA)

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        con = sqlite3.connect(self._path, timeout=10)
        con.row_factory = sqlite3.Row
        try:
            con.execute("PRAGMA journal_mode=WAL")
            yield con
            con.commit()
        finally:
            con.close()

    # ── recording ───────────────────────────────────────────────────────────
    def record(self, event: A2AEvent) -> None:
        with self._conn() as con:
            con.execute(
                """INSERT INTO a2a_events (ts, direction, peer, skill, task_id, state, ok,
                       latency_ms, finding_id, summary, artifacts)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (event.ts, event.direction, event.peer, event.skill, event.task_id, event.state,
                 1 if event.ok else 0, event.latency_ms, event.finding_id,
                 scrub(event.summary), json.dumps(event.artifacts[:8])))

    def record_inbound(self, body: dict[str, Any], *, state: str, note: str = "") -> None:
        """A peer delegated a task to us."""
        inp = (body or {}).get("input") or {}
        ticket = inp.get("ticket") or {}
        self.record(A2AEvent(
            direction="in", peer=str((body or {}).get("from_agent") or "peer"),
            skill=str((body or {}).get("skill") or "?"),
            task_id=str((body or {}).get("task_id") or ""), state=state,
            ok=state not in ("rejected", "failed"),
            finding_id=str(ticket.get("finding_id") or inp.get("finding_id") or ""),
            summary=note or scrub((body or {}).get("message") or ticket.get("component") or ""),
        ))

    def record_outbound(self, *, peer: str, skill: str, finding_id: str = "",
                        state: str = "completed", ok: bool = True,
                        latency_ms: int | None = None, summary: str = "",
                        artifacts: list[str] | None = None) -> None:
        """We delegated a task to a peer (e.g. asked MOMUS to re-test)."""
        self.record(A2AEvent(direction="out", peer=peer, skill=skill, finding_id=finding_id,
                             state=state, ok=ok, latency_ms=latency_ms, summary=summary,
                             artifacts=artifacts or []))

    # ── reading (dashboard / API) ────────────────────────────────────────────
    def recent(self, limit: int = 100, *, peer: str | None = None,
               skill: str | None = None) -> list[dict[str, Any]]:
        where, args = [], []
        if peer:
            where.append("peer = ?"); args.append(peer)
        if skill:
            where.append("skill = ?"); args.append(skill)
        clause = (" WHERE " + " AND ".join(where)) if where else ""
        args.append(int(max(1, min(limit, 500))))
        with self._conn() as con:
            rows = con.execute(
                f"SELECT * FROM a2a_events{clause} ORDER BY event_id DESC LIMIT ?", tuple(args)
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["ok"] = bool(d.get("ok"))
            try:
                d["artifacts"] = json.loads(d.get("artifacts") or "[]")
            except json.JSONDecodeError:
                d["artifacts"] = []
            out.append(d)
        return out

    def stats(self) -> dict[str, Any]:
        with self._conn() as con:
            total = con.execute("SELECT COUNT(*) FROM a2a_events").fetchone()[0]
            by_skill = {str(r[0]): int(r[1]) for r in
                        con.execute("SELECT skill, COUNT(*) FROM a2a_events GROUP BY skill").fetchall()}
            by_peer = {str(r[0]): int(r[1]) for r in
                       con.execute("SELECT peer, COUNT(*) FROM a2a_events GROUP BY peer").fetchall()}
            by_dir = {str(r[0]): int(r[1]) for r in
                      con.execute("SELECT direction, COUNT(*) FROM a2a_events GROUP BY direction").fetchall()}
            rejected = con.execute("SELECT COUNT(*) FROM a2a_events WHERE ok = 0").fetchone()[0]
            avg = con.execute("SELECT AVG(latency_ms) FROM a2a_events WHERE latency_ms IS NOT NULL").fetchone()[0]
        return {"total": int(total), "by_skill": by_skill, "by_peer": by_peer,
                "by_direction": by_dir, "rejected": int(rejected),
                "avg_latency_ms": round(float(avg), 1) if avg is not None else None}
