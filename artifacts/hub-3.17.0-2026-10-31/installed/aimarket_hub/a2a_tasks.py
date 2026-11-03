"""The A2A Task records behind ``marketplace-invoke`` (migration 036).

A2A 1.0 requires a SendMessage that does work to answer with a Task the client can come
back to: pay for it, cancel it, read it again after a timeout. This store is that record
and nothing more. It is NOT a second ledger — money moves only inside the invoke path this
bridge calls, which reserves, captures and releases on its own; a task row that is lost,
stale or wrong can misreport a call, never charge for one.

What a row keeps, and for how long, follows from who can read it:

* **Ids are server-generated and unguessable** (``a2at_`` + 24 hex, like job ids). An id is
  a bearer capability for a task nobody authenticated for (an anonymous x402 buyer), and a
  second factor for one that was.
* **Each row is bound to a principal hash** — the credit account, the mandate, or an
  anonymous per-caller token — never to the key or proof itself. Neither an API key nor a
  mandate proof nor an x402 payment payload is ever written here.
* **The exact invoke bytes are kept only while the task can still be resumed** (waiting for
  a payment or for credentials) and are purged the moment it reaches a terminal state or
  expires: they are the buyer's input, and after that point nothing needs them. Only their
  sha256 stays, so a retried SendMessage can be told apart from a different request that
  reuses a messageId.

Every state change is ONE conditional statement (``… WHERE task_state IN (…) AND revision =
?``), for the same reason the credits ledger works that way: two concurrent follow-ups — a
client retrying a payment while the first attempt is still in flight — must not both run
the invoke. Exactly one wins the claim; the other reads the task back.
"""
from __future__ import annotations

import json
import logging
import secrets
import time
from typing import Any

from aimarket_hub.db_backend import returning, returning_one

logger = logging.getLogger(__name__)

# A2A 1.0 TaskState names (ProtoJSON enum form).
SUBMITTED = "TASK_STATE_SUBMITTED"
WORKING = "TASK_STATE_WORKING"
COMPLETED = "TASK_STATE_COMPLETED"
FAILED = "TASK_STATE_FAILED"
CANCELED = "TASK_STATE_CANCELED"
REJECTED = "TASK_STATE_REJECTED"
INPUT_REQUIRED = "TASK_STATE_INPUT_REQUIRED"
AUTH_REQUIRED = "TASK_STATE_AUTH_REQUIRED"

TERMINAL = frozenset({COMPLETED, FAILED, CANCELED, REJECTED})
INTERRUPTED = frozenset({INPUT_REQUIRED, AUTH_REQUIRED})
ALL_STATES = frozenset({SUBMITTED, WORKING}) | TERMINAL | INTERRUPTED

#: How long a task may wait for a payment or credentials. Past it the task FAILS and its
#: input is purged. Longer than the 300 s x402 invoice on purpose: an expired invoice is
#: not the end of the task — the next attempt is answered with fresh terms.
DEFAULT_INTERRUPTED_TTL_S = 900
#: A WORKING row older than this belongs to an invoke that can no longer be running (the
#: process that ran it restarted). Pay-on-Verified can hold an invoke for 300 s; this is
#: comfortably past any real call. Only for rows written before leases existed: a leased row
#: is recovered as soon as its lease lapses (recover_stale in a2a.py).
WORKING_STALE_S = 1800
#: How long a WORKING task is held by the process running it without a renewal. The runner
#: renews every LEASE_S / 3, so a live call never loses it; a process that died loses all of
#: its tasks within this, and the next sweep recovers them.
LEASE_S = 90.0
#: This process, as the owner of the leases it takes.
PROCESS_ID = secrets.token_hex(8)
#: The lease a recovery holds while it reads the ledger and moves an abandoned task on.
RECOVERY_OWNER = f"recover:{PROCESS_ID}"
#: How long a finished task (without its input) stays readable by GetTask/ListTasks.
DEFAULT_RETENTION_S = 7 * 86_400
ANONYMOUS_FAILURE_RETENTION_S = 3600
#: History is a record of the exchange, not an archive; a task that needs more than this
#: many rounds is a client looping.
MAX_HISTORY = 32
_SWEEP_EVERY_S = 60.0

_INTERRUPTED_SQL = f"('{INPUT_REQUIRED}', '{AUTH_REQUIRED}')"
_TERMINAL_SQL = "(" + ", ".join(f"'{s}'" for s in sorted(TERMINAL)) + ")"


def new_task_id() -> str:
    return f"a2at_{secrets.token_hex(12)}"


def is_task_id(value: Any) -> bool:
    text = str(value or "")
    return len(text) == 29 and text.startswith("a2at_") and all(c in "0123456789abcdef" for c in text[5:])


def iso(ts: float) -> str:
    """RFC 3339 UTC with milliseconds — the ProtoJSON form of google.protobuf.Timestamp."""
    whole = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(ts))
    return f"{whole}.{int((ts % 1) * 1000):03d}Z"


def load_json(text: Any, default: Any) -> Any:
    """A stored JSON column, or ``default`` when it is missing, corrupt or the wrong type."""
    try:
        value = json.loads(text or "")
    except (TypeError, ValueError):
        return default
    return value if isinstance(value, type(default)) else default


def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


class A2ATaskStore:
    """A2A tasks on the hub's shared connection (``db._conn``)."""

    def __init__(self, conn: Any, *, interrupted_ttl_s: int = DEFAULT_INTERRUPTED_TTL_S,
                 retention_s: int = DEFAULT_RETENTION_S):
        self._conn = conn
        self.interrupted_ttl_s = max(60, int(interrupted_ttl_s))
        self.retention_s = max(3600, int(retention_s))
        self._swept_at = 0.0

    # ── reads ──────────────────────────────────────────────────────────────

    def get(self, task_id: str) -> dict[str, Any] | None:
        if not is_task_id(task_id):
            return None
        row = self._conn.execute("SELECT * FROM a2a_tasks WHERE task_id = ?", (task_id,)).fetchone()
        return dict(row) if row else None

    def by_message(self, principal: str, context_id: str, message_id: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT * FROM a2a_tasks WHERE principal_hash = ? AND context_id = ? AND message_id = ?",
            (principal, context_id, message_id),
        ).fetchone()
        return dict(row) if row else None

    def list(self, principal: str, *, context_id: str = "", state: str = "", updated_after: float = 0.0,
             limit: int = 50, offset: int = 0) -> tuple[list[dict[str, Any]], int]:
        """A principal's tasks, newest first, and how many match in total."""
        where = ["principal_hash = ?"]
        params: list[Any] = [principal]
        if context_id:
            where.append("context_id = ?")
            params.append(context_id)
        if state:
            where.append("task_state = ?")
            params.append(state)
        if updated_after:
            where.append("updated_at > ?")
            params.append(updated_after)
        clause = " AND ".join(where)
        total_row = self._conn.execute(f"SELECT COUNT(*) AS n FROM a2a_tasks WHERE {clause}", tuple(params)).fetchone()
        rows = self._conn.execute(
            f"SELECT * FROM a2a_tasks WHERE {clause} ORDER BY updated_at DESC, task_id DESC LIMIT ? OFFSET ?",
            (*params, int(limit), int(offset)),
        ).fetchall()
        return [dict(r) for r in rows], int((dict(total_row) if total_row else {}).get("n") or 0)

    # ── writes: each one a single conditional statement ─────────────────────

    def create(self, *, principal: str, context_id: str, message_id: str, product_id: str,
               capability_id: str, source_hub: str, invoke_b64: str, invoke_sha256: str,
               history: list[dict[str, Any]], now: float | None = None) -> tuple[dict[str, Any], bool]:
        """Claim (principal, contextId, messageId) for a new task, already WORKING.

        Returns ``(row, created)``. ``created`` is False when a task for this message exists
        already — a retried SendMessage — and the row is that task, untouched. The UNIQUE
        index decides, not a read before the insert: two copies of one request arriving
        together (a proxy retrying a slow call) must not both run it and both pay.
        """
        now = time.time() if now is None else now
        task_id = new_task_id()
        status = {"state": WORKING, "timestamp": iso(now)}
        won = returning_one(
            self._conn,
            "INSERT INTO a2a_tasks (task_id, context_id, principal_hash, message_id, last_message_id, "
            "task_state, product_id, capability_id, source_hub, invoke_body, invoke_sha256, "
            "status_json, history_json, revision, created_at, updated_at, expires_at, lease_owner, lease_until) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?) "
            "ON CONFLICT DO NOTHING RETURNING task_id",
            (task_id, context_id, principal, message_id, message_id, WORKING, product_id, capability_id,
             source_hub, invoke_b64, invoke_sha256, _dumps(status), _dumps(history[-MAX_HISTORY:]),
             now, now, now + self.interrupted_ttl_s, PROCESS_ID, now + LEASE_S),
        )
        self._conn.commit()
        if won is not None:
            return self.get(task_id) or {}, True
        existing = self.by_message(principal, context_id, message_id)
        if existing is None:  # pragma: no cover - a conflict on the random primary key
            raise RuntimeError("a2a task id collision; retry the request")
        return existing, False

    def claim(self, task_id: str, *, message_id: str, now: float | None = None) -> dict[str, Any] | None:
        """Take an interrupted task back to WORKING for one follow-up message.

        None when this caller did not win: the task is not waiting (it is running, finished
        or expired), or this very message was already processed — a retried follow-up must
        not run the invoke, and so pay, a second time.
        """
        now = time.time() if now is None else now
        status = {"state": WORKING, "timestamp": iso(now)}
        won = returning_one(
            self._conn,
            f"UPDATE a2a_tasks SET task_state = ?, last_message_id = ?, status_json = ?, "
            f"revision = revision + 1, updated_at = ?, lease_owner = ?, lease_until = ?, invoke_started = 0, "
            f"invoke_rail = '' "
            f"WHERE task_id = ? AND task_state IN {_INTERRUPTED_SQL} AND expires_at >= ? "
            f"AND last_message_id <> ? RETURNING task_id",
            (WORKING, message_id, _dumps(status), now, PROCESS_ID, now + LEASE_S, task_id, now, message_id),
        )
        self._conn.commit()
        return self.get(task_id) if won is not None else None

    def finish(self, row: dict[str, Any], *, state: str, status: dict[str, Any],
               artifacts: list[dict[str, Any]] | None = None, metadata: dict[str, Any] | None = None,
               history_add: list[dict[str, Any]] | None = None, x402_nonce: str | None = None,
               invoke_b64: str | None = None, invoke_sha256: str | None = None,
               awaiting: str = "", waits_until: float | None = None,
               now: float | None = None) -> dict[str, Any]:
        """Record the outcome of the round this caller claimed (``row`` is the claimed row).

        A terminal state purges the stored invoke bytes; an interrupted one keeps them (or the
        replacement a follow-up brought) and restarts the waiting clock. Conditional on the
        revision the claim produced, so a sweep that expired the task meanwhile is not
        overwritten by a late answer.

        ``awaiting`` names an owner approval the task now waits on (mandates.md §5.6), and
        ``waits_until`` replaces the waiting clock with that approval's own expiry: an owner
        has a day to answer, not the fifteen minutes a payment gets.
        """
        now = time.time() if now is None else now
        history = load_json(row.get("history_json"), [])
        history.extend(history_add or [])
        keep_body = state in INTERRUPTED
        body = (invoke_b64 if invoke_b64 is not None else str(row.get("invoke_body") or "")) if keep_body else ""
        digest = invoke_sha256 if invoke_sha256 is not None else str(row.get("invoke_sha256") or "")
        if keep_body:
            expires = max(now + self.interrupted_ttl_s, float(waits_until or 0))
        else:
            expires = float(row.get("expires_at") or now)
        won = returning_one(
            self._conn,
            "UPDATE a2a_tasks SET task_state = ?, status_json = ?, artifacts_json = ?, metadata_json = ?, "
            "history_json = ?, x402_nonce = ?, invoke_body = ?, invoke_sha256 = ?, awaiting = ?, "
            "revision = revision + 1, updated_at = ?, expires_at = ? "
            "WHERE task_id = ? AND task_state = ? AND revision = ? AND lease_owner = ? RETURNING task_id",
            (state, _dumps(status), _dumps(artifacts or []), _dumps(metadata or {}),
             _dumps(history[-MAX_HISTORY:]),
             str(row.get("x402_nonce") or "") if x402_nonce is None else x402_nonce,
             body, digest, awaiting if keep_body else "", now, expires,
             row["task_id"], WORKING, int(row.get("revision") or 0), PROCESS_ID),
        )
        self._conn.commit()
        if won is None:
            # Money is unaffected (the invoke settled on its own); only this record is late.
            logger.warning("a2a: task %s changed while its invoke ran; outcome %s not recorded",
                           row["task_id"], state)
        return self.get(row["task_id"]) or row

    def cancel(self, row: dict[str, Any], *, status: dict[str, Any], history_add: list[dict[str, Any]] | None = None,
               now: float | None = None) -> dict[str, Any] | None:
        """CANCELED, but only from a waiting state and only if nothing changed since ``row``
        was read. None when the task was not cancelable at that instant."""
        now = time.time() if now is None else now
        history = load_json(row.get("history_json"), [])
        history.extend(history_add or [])
        won = returning_one(
            self._conn,
            f"UPDATE a2a_tasks SET task_state = ?, status_json = ?, history_json = ?, invoke_body = '', "
            f"awaiting = '', revision = revision + 1, updated_at = ? "
            f"WHERE task_id = ? AND task_state IN {_INTERRUPTED_SQL} AND revision = ? RETURNING task_id",
            (CANCELED, _dumps(status), _dumps(history[-MAX_HISTORY:]), now, row["task_id"],
             int(row.get("revision") or 0)),
        )
        self._conn.commit()
        return self.get(row["task_id"]) if won is not None else None

    # ── a running invoke: its lease and what it reserved ───────────────────

    def renew(self, task_id: str, *, now: float | None = None) -> bool:
        """Keep this process's lease on a running task. False when the task is no longer
        this process's to run (it finished, or a sweep took it as abandoned)."""
        now = time.time() if now is None else now
        won = returning_one(
            self._conn,
            "UPDATE a2a_tasks SET lease_until = ? WHERE task_id = ? AND task_state = ? AND lease_owner = ? "
            "RETURNING task_id", (now + LEASE_S, task_id, WORKING, PROCESS_ID), commit=True,
        )
        return won is not None

    def started(self, task_id: str, *, rail: str, now: float | None = None) -> None:
        """The invoke is about to be sent: from here on money may move. ``rail`` says on which
        rail (credits, x402, trial or none), which decides what a recovery can know."""
        self._conn.execute(
            "UPDATE a2a_tasks SET invoke_started = ?, invoke_rail = ? WHERE task_id = ? AND task_state = ? "
            "AND lease_owner = ?", (time.time() if now is None else now, rail[:20], task_id, WORKING, PROCESS_ID),
        )
        self._conn.commit()

    def note_charge(self, task_id: str, receipt_id: str, kind: str, *, now: float | None = None) -> None:
        """Name a reservation or debit BEFORE it is made, so a hub that dies mid-call can find it."""
        self._conn.execute(
            "INSERT INTO a2a_task_charges (task_id, receipt_id, kind, created_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT DO NOTHING", (task_id, receipt_id, kind[:20], time.time() if now is None else now),
        )
        self._conn.commit()

    def charges(self, task_id: str) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT receipt_id, kind FROM a2a_task_charges WHERE task_id = ? ORDER BY created_at, receipt_id",
            (task_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def stale(self, now: float | None = None, *, limit: int = 50) -> list[dict[str, Any]]:
        """WORKING tasks whose lease lapsed: the process running them is gone."""
        now = time.time() if now is None else now
        rows = self._conn.execute(
            "SELECT * FROM a2a_tasks WHERE task_state = ? AND lease_until > 0 AND lease_until < ? "
            "ORDER BY updated_at LIMIT ?", (WORKING, now, int(limit)),
        ).fetchall()
        return [dict(r) for r in rows]

    def take_stale(self, row: dict[str, Any], *, now: float | None = None) -> dict[str, Any] | None:
        """Take an abandoned task's lease for a recovery — one conditional statement, so the
        runner (should it be alive after all) can no longer renew it or record its outcome,
        and two sweeps cannot both recover one task. None when this caller did not win."""
        now = time.time() if now is None else now
        won = returning_one(
            self._conn,
            "UPDATE a2a_tasks SET lease_owner = ?, lease_until = ? WHERE task_id = ? AND task_state = ? "
            "AND lease_until > 0 AND lease_until < ? RETURNING task_id",
            (RECOVERY_OWNER, now + LEASE_S, row["task_id"], WORKING, now), commit=True,
        )
        return self.get(row["task_id"]) if won is not None else None

    def resolve_stale(self, row: dict[str, Any], *, state: str, status: dict[str, Any],
                      metadata: dict[str, Any] | None = None, now: float | None = None) -> dict[str, Any] | None:
        """Move an abandoned task on: back to waiting (its input kept, so a follow-up runs it)
        or to a terminal state (its input purged). Only by the recovery that took its lease."""
        now = time.time() if now is None else now
        history = load_json(row.get("history_json"), [])
        message = status.get("message")
        if isinstance(message, dict):
            history.append(message)
        waiting = state in INTERRUPTED
        won = returning_one(
            self._conn,
            "UPDATE a2a_tasks SET task_state = ?, status_json = ?, history_json = ?, metadata_json = ?, "
            "invoke_body = CASE WHEN ? = 1 THEN invoke_body ELSE '' END, lease_owner = '', lease_until = 0, "
            "revision = revision + 1, updated_at = ?, expires_at = ? "
            "WHERE task_id = ? AND task_state = ? AND revision = ? AND lease_owner = ? RETURNING task_id",
            (state, _dumps(status), _dumps(history[-MAX_HISTORY:]),
             _dumps(metadata if metadata is not None else load_json(row.get("metadata_json"), {})),
             1 if waiting else 0, now, now + self.interrupted_ttl_s if waiting else float(row.get("expires_at") or now),
             row["task_id"], WORKING, int(row.get("revision") or 0), RECOVERY_OWNER),
            commit=True,
        )
        return self.get(row["task_id"]) if won is not None else None

    def waiting_on(self, approval_id: str) -> list[dict[str, Any]]:
        """Tasks still waiting on an owner approval (mandates.md §5.6)."""
        if not approval_id:
            return []
        rows = self._conn.execute(
            f"SELECT * FROM a2a_tasks WHERE awaiting = ? AND task_state IN {_INTERRUPTED_SQL}", (approval_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def resolve_waiting(self, row: dict[str, Any], *, state: str, status: dict[str, Any],
                        history_add: list[dict[str, Any]] | None = None, metadata: dict[str, Any] | None = None,
                        now: float | None = None) -> dict[str, Any] | None:
        """Move a task that waits on its owner, without a client message: to a terminal state
        (the owner said no) or to the same waiting state with a new status (the owner said yes
        and the client may now continue). Conditional on the revision ``row`` was read at, like
        every other change. None when the task moved meanwhile."""
        now = time.time() if now is None else now
        history = load_json(row.get("history_json"), [])
        history.extend(history_add or [])
        terminal = state in TERMINAL
        won = returning_one(
            self._conn,
            f"UPDATE a2a_tasks SET task_state = ?, status_json = ?, history_json = ?, metadata_json = ?, "
            f"invoke_body = CASE WHEN ? = 1 THEN '' ELSE invoke_body END, awaiting = '', "
            f"revision = revision + 1, updated_at = ? "
            f"WHERE task_id = ? AND task_state IN {_INTERRUPTED_SQL} AND revision = ? RETURNING task_id",
            (state, _dumps(status), _dumps(history[-MAX_HISTORY:]),
             _dumps(metadata if metadata is not None else load_json(row.get("metadata_json"), {})),
             1 if terminal else 0, now, row["task_id"], int(row.get("revision") or 0)),
        )
        self._conn.commit()
        return self.get(row["task_id"]) if won is not None else None

    # ── housekeeping ───────────────────────────────────────────────────────

    def sweep(self, now: float | None = None, *, force: bool = False) -> dict[str, int]:
        """Expire what waited too long, fail what can no longer be running, forget old tasks.

        Throttled to once a minute: it runs on the request path rather than in a loop of its
        own, so a hub with no A2A traffic does no work for it.
        """
        now = time.time() if now is None else now
        if not force and now - self._swept_at < _SWEEP_EVERY_S:
            return {"expired": 0, "orphaned": 0, "deleted": 0, "task_ids": [], "ran": False}
        self._swept_at = now
        expired_status = _dumps({
            "state": FAILED, "timestamp": iso(now),
            "message": _agent_note("The task expired waiting for a payment, credentials or its owner's approval; "
                                   "its input was deleted. Send a new message to try again."),
        })
        orphaned_status = _dumps({
            "state": FAILED, "timestamp": iso(now),
            "message": _agent_note("The hub restarted while this task was running, so its outcome "
                                   "was not recorded here. A charge, if any, is on your receipts "
                                   "and balance; do not assume the call ran."),
        })
        # RETURNING the ids, so the facade can tell these tasks' push subscribers (a2a_push).
        expired = returning(
            self._conn,
            f"UPDATE a2a_tasks SET task_state = ?, status_json = ?, invoke_body = '', awaiting = '', "
            f"revision = revision + 1, updated_at = ? "
            f"WHERE task_state IN {_INTERRUPTED_SQL} AND expires_at < ? RETURNING task_id",
            (FAILED, expired_status, now, now),
            commit=True,
        )
        # Only rows without a lease (written before leases existed): a leased row is recovered
        # by the facade, which can look at the ledger, as soon as its lease lapses.
        orphaned = returning(
            self._conn,
            "UPDATE a2a_tasks SET task_state = ?, status_json = ?, invoke_body = '', "
            "revision = revision + 1, updated_at = ? WHERE task_state = ? AND lease_until = 0 AND updated_at < ? "
            "RETURNING task_id",
            (FAILED, orphaned_status, now, WORKING, now - WORKING_STALE_S),
            commit=True,
        )
        self._conn.execute(
            f"DELETE FROM a2a_task_charges WHERE task_id IN (SELECT task_id FROM a2a_tasks WHERE "
            f"task_state IN {_TERMINAL_SQL} AND updated_at < ?)", (now - self.retention_s,),
        )
        deleted = self._conn.execute(
            f"DELETE FROM a2a_tasks WHERE (task_state IN {_TERMINAL_SQL} AND updated_at < ?) "
            "OR (principal_hash LIKE 'anon:%' AND task_state IN (?, ?) AND updated_at < ?)",
            (now - self.retention_s, FAILED, REJECTED, now - ANONYMOUS_FAILURE_RETENTION_S),
        )
        self._conn.commit()

        def _count(cursor: Any) -> int:
            try:
                return max(0, int(getattr(cursor, "rowcount", 0) or 0))
            except (TypeError, ValueError):
                return 0

        return {"expired": len(expired), "orphaned": len(orphaned), "deleted": _count(deleted),
                "task_ids": [str(r["task_id"]) for r in [*expired, *orphaned]], "ran": True}


class ChargeJournal:
    """The credits ledger as one A2A task's invoke sees it.

    Every reservation and debit is named in ``a2a_task_charges`` BEFORE the money moves. If
    the process dies mid-call, the hub can then read, receipt by receipt, what the call
    reserved and whether any of it was captured — instead of failing the task with "you may
    have been charged" (a2a.py, recover_stale). Anything that does not move money passes
    straight through.
    """

    def __init__(self, inner: Any, store: "A2ATaskStore", task_id: str):
        self._inner = inner
        self._store = store
        self._task_id = task_id

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    def _note(self, receipt_id: str, kind: str) -> None:
        if receipt_id:
            self._store.note_charge(self._task_id, receipt_id, kind)

    def hold(self, account_id: str, amount_usd: float, receipt_id: str) -> dict[str, Any]:
        self._note(receipt_id, "hold")
        return self._inner.hold(account_id, amount_usd, receipt_id)

    def hold_allowance(self, account_id: str, amount_usd: float, receipt_id: str) -> dict[str, Any]:
        self._note(receipt_id, "allowance")
        hold = getattr(self._inner, "hold_allowance", None) or self._inner.hold
        return hold(account_id, amount_usd, receipt_id)

    def debit(self, account_id: str, amount_usd: float, receipt_id: str = "", note: str = "",
              **kwargs: Any) -> dict[str, Any]:
        self._note(receipt_id, "debit")
        return self._inner.debit(account_id, amount_usd, receipt_id=receipt_id, note=note, **kwargs)


def _agent_note(text: str) -> dict[str, Any]:
    return {"role": "ROLE_AGENT", "messageId": f"a2am_{secrets.token_hex(8)}",
            "parts": [{"text": text, "mediaType": "text/plain"}]}


def render(row: dict[str, Any], *, history_length: int | None = None,
           include_artifacts: bool = True) -> dict[str, Any]:
    """The A2A ``Task`` object for a stored row."""
    status = load_json(row.get("status_json"), {})
    status["state"] = str(row.get("task_state") or status.get("state") or WORKING)
    status.setdefault("timestamp", iso(float(row.get("updated_at") or time.time())))
    message = status.get("message")
    if isinstance(message, dict):
        message.setdefault("taskId", row["task_id"])
        message.setdefault("contextId", row["context_id"])
    task: dict[str, Any] = {"id": row["task_id"], "contextId": row["context_id"], "status": status}
    if include_artifacts:
        artifacts = load_json(row.get("artifacts_json"), [])
        if artifacts:
            task["artifacts"] = artifacts
    history = load_json(row.get("history_json"), [])
    if history_length is not None:
        history = history[-history_length:] if history_length > 0 else []
    if history:
        task["history"] = history
    metadata = load_json(row.get("metadata_json"), {})
    if metadata:
        task["metadata"] = metadata
    return task
