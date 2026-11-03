"""Durable record of every DebitAuthorization the hub holds.

Its own SQLite file, with its own schema bootstrap, on purpose: the bridge is optional, so
its tables must not ride the hub's migration chain (which the channel ledger pins by
subsystem) and an operator who never enables the bridge must not acquire its schema.

``receipt_id`` is the primary key because it is the CONTRACT's replay key
(``usedReceipts``): keying on the same value the chain keys on means the store and the
chain cannot disagree about what "the same debit" is. It is also the ledger's receipt
nonce, so one row ties together the off-chain debit, the buyer's signature, and the
on-chain submission.

State machine — a row only ever moves forward:

    pending ──plan ok──▶ planned ──submit──▶ submitted ──receipt──▶ confirmed  (terminal)
       │                    │                    │
       └───────── abandoned ◀────────────────────┘                            (terminal)

A simulation that reverts does NOT move the row: the revert is recorded as the last known
plan and the row stays where it was, because most reverts here are transient by nature (a
nonce gap that a preceding submission will fill, a chain that was unreachable). Only an
operator decision, or a permanently unusable authorization, abandons a row — and an
abandoned row means the hub has no on-chain claim to that money, never that the buyer is
charged twice.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aimarket_hub.escrow_bridge import config

logger = logging.getLogger(__name__)

PENDING = "pending"
PLANNED = "planned"
SUBMITTED = "submitted"
CONFIRMED = "confirmed"
ABANDONED = "abandoned"

_TERMINAL = (CONFIRMED, ABANDONED)

#: Why a row in a nonce window was abandoned when a later call's running total replaced
#: it. Such a row was REPLACED, not given up: its calls are inside its replacement, and
#: if that replacement is withdrawn (its own call was never served) it is the window's
#: claim again — see revive_superseded.
SUPERSEDED_REASON = "replaced by fresh buyer authorization for the same on-chain nonce"
# Forward-only transitions. Anything not listed is refused, so a bug cannot walk a
# confirmed debit back to pending and have it submitted a second time.
_ALLOWED: dict[str, tuple[str, ...]] = {
    # PENDING/PLANNED → CONFIRMED is reachable only through mark_collected_externally(),
    # for a receipt the CONTRACT reports as already used. Without this edge a debit
    # collected out of band (an operator running the CLI, or `cast` from a shell) could
    # never be resolved: the row stayed pending forever and, because submission is strictly
    # nonce-ordered per channel, it blocked every later row on that channel. Observed in
    # production on 2026-07-29 — three stuck rows, two already debited on Base.
    # This is still forward-only; CONFIRMED remains terminal.
    PENDING: (PLANNED, SUBMITTED, CONFIRMED, ABANDONED),
    PLANNED: (PLANNED, SUBMITTED, CONFIRMED, ABANDONED),
    SUBMITTED: (SUBMITTED, CONFIRMED, ABANDONED),
    CONFIRMED: (),
    ABANDONED: (),
}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS debit_authorizations (
    receipt_id      TEXT PRIMARY KEY,
    ledger_channel  TEXT NOT NULL,
    escrow_channel  TEXT NOT NULL,
    chain_id        INTEGER NOT NULL,
    escrow_address  TEXT NOT NULL,
    hub             TEXT NOT NULL,
    token           TEXT NOT NULL,
    depositor       TEXT NOT NULL,
    amount_units    INTEGER NOT NULL,
    nonce           INTEGER NOT NULL,
    deadline        INTEGER NOT NULL,
    signature       TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending',
    attempts        INTEGER NOT NULL DEFAULT 0,
    last_plan_json  TEXT NOT NULL DEFAULT '',
    last_error      TEXT NOT NULL DEFAULT '',
    tx_hash         TEXT NOT NULL DEFAULT '',
    created_at      TEXT NOT NULL,
    submitted_at    TEXT NOT NULL DEFAULT '',
    resolved_at     TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_auth_status ON debit_authorizations(status);
CREATE INDEX IF NOT EXISTS idx_auth_channel ON debit_authorizations(escrow_channel, nonce);
-- One *active* authorization per (escrow channel, nonce). Abandoned/confirmed rows stay
-- for audit but must not permanently block a fresh signature after a stuck pending auth.
CREATE UNIQUE INDEX IF NOT EXISTS idx_auth_channel_nonce_active
    ON debit_authorizations(escrow_channel, nonce)
    WHERE status NOT IN ('abandoned', 'confirmed');
"""


class StoreError(RuntimeError):
    """The store refused an operation that would break one of its invariants."""


def default_db_path() -> str:
    """Configured path, else beside the channel ledger's own database.

    Sitting next to the ledger means the bridge's records share the ledger's backup and
    volume story instead of inventing a second one an operator has to discover.
    """
    configured = config.db_path()
    if configured:
        return configured
    from aimarket_hub import channels as _channels

    return str(Path(getattr(_channels, "_DB_PATH", "data/channels.db")).parent / "escrow_bridge.db")


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


@dataclass(frozen=True)
class AuthorizationRow:
    receipt_id: str
    ledger_channel: str
    escrow_channel: str
    chain_id: int
    escrow_address: str
    hub: str
    token: str
    depositor: str
    amount_units: int
    nonce: int
    deadline: int
    signature: str
    status: str
    attempts: int
    last_plan: dict[str, Any]
    last_error: str
    tx_hash: str
    created_at: str
    resolved_at: str
    # Defaulted, and therefore last: added after the first stores existed, and a
    # dataclass cannot put a non-default field after a defaulted one.
    submitted_at: str = ""

    @property
    def is_terminal(self) -> bool:
        return self.status in _TERMINAL

    def expired(self, *, now: float | None = None) -> bool:
        return self.deadline <= int(now if now is not None else time.time())

    def as_dict(self) -> dict[str, Any]:
        data = {k: getattr(self, k) for k in self.__dataclass_fields__}
        # The signature is the buyer's credential for this debit; operators inspecting the
        # queue have no reason to see it, and logs/JSON dumps are where such things leak.
        data["signature"] = f"<{len(self.signature)} chars>"
        return data


def _row(raw: sqlite3.Row) -> AuthorizationRow:
    try:
        plan = json.loads(raw["last_plan_json"] or "{}")
    except (TypeError, ValueError):
        plan = {}
    return AuthorizationRow(
        receipt_id=raw["receipt_id"], ledger_channel=raw["ledger_channel"],
        escrow_channel=raw["escrow_channel"], chain_id=int(raw["chain_id"]),
        escrow_address=raw["escrow_address"], hub=raw["hub"], token=raw["token"],
        depositor=raw["depositor"], amount_units=int(raw["amount_units"]),
        nonce=int(raw["nonce"]), deadline=int(raw["deadline"]), signature=raw["signature"],
        status=raw["status"], attempts=int(raw["attempts"]),
        last_plan=plan if isinstance(plan, dict) else {}, last_error=raw["last_error"],
        tx_hash=raw["tx_hash"], created_at=raw["created_at"], resolved_at=raw["resolved_at"],
        submitted_at=(raw["submitted_at"] if "submitted_at" in raw.keys() else ""),
    )


class AuthorizationStore:
    """Thread-safe, single-file store. One instance per process is enough."""

    def __init__(self, db_path: str | None = None, *, create: bool = True):
        """``create=False`` refuses to materialise a database that does not exist yet.

        Read-only inspection on a hub that never enabled the bridge must not leave its
        schema behind — the module's whole claim is that an operator who does not opt in
        acquires nothing.
        """
        self.db_path = db_path or default_db_path()
        self._lock = threading.Lock()
        if not create and self.db_path != ":memory:" and not Path(self.db_path).exists():
            raise StoreError(f"no authorization store at {self.db_path}")
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False + an explicit lock: the mirror runs off the request
        # thread, and serialising every write is cheap at this volume.
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(_SCHEMA)
            # Additive migration: `submitted_at` postdates the first stores, and the
            # rolling spend cap reads it. CREATE TABLE IF NOT EXISTS cannot add a column
            # to a database that already exists — production had one with three rows in it.
            have = {r["name"] for r in self._conn.execute(
                "PRAGMA table_info(debit_authorizations)")}
            if "submitted_at" not in have:
                self._conn.execute(
                    "ALTER TABLE debit_authorizations "
                    "ADD COLUMN submitted_at TEXT NOT NULL DEFAULT ''"
                )
            # Migrate legacy unique(channel, nonce) → partial unique on active rows only.
            idx = {
                r["name"]: (r["sql"] or "")
                for r in self._conn.execute(
                    "SELECT name, sql FROM sqlite_master WHERE type='index' "
                    "AND tbl_name='debit_authorizations'"
                )
            }
            if "idx_auth_channel_nonce" in idx:
                self._conn.execute("DROP INDEX IF EXISTS idx_auth_channel_nonce")
            if "idx_auth_channel_nonce_active" not in idx:
                self._conn.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS idx_auth_channel_nonce_active "
                    "ON debit_authorizations(escrow_channel, nonce) "
                    "WHERE status NOT IN ('abandoned', 'confirmed')"
                )
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # ── writes ───────────────────────────────────────────────────────────────

    def record(
        self,
        *,
        receipt_id: str,
        ledger_channel: str,
        escrow_channel: str,
        chain_id: int,
        escrow_address: str,
        hub: str,
        token: str,
        depositor: str,
        amount_units: int,
        nonce: int,
        deadline: int,
        signature: str,
    ) -> AuthorizationRow:
        """Persist a verified authorization. Raises StoreError on a duplicate.

        Refusing a duplicate rather than overwriting is the point: a second authorization
        for a receipt the hub already holds means either a replay or a client bug, and
        silently replacing the stored one would let a later, different amount ride on an
        earlier signature's identity.
        """
        with self._lock:
            try:
                self._conn.execute(
                    "INSERT INTO debit_authorizations (receipt_id, ledger_channel, "
                    "escrow_channel, chain_id, escrow_address, hub, token, depositor, "
                    "amount_units, nonce, deadline, signature, status, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (receipt_id, ledger_channel, escrow_channel, int(chain_id),
                     escrow_address, hub, token, depositor, int(amount_units), int(nonce),
                     int(deadline), signature, PENDING, _now()),
                )
                self._conn.commit()
            except sqlite3.IntegrityError as exc:
                self._conn.rollback()
                text = str(exc).lower()
                if "receipt_id" in text or "primary key" in text:
                    raise StoreError(
                        f"an authorization for receipt {receipt_id} is already stored"
                    ) from exc
                raise StoreError(
                    f"an authorization for escrow channel {escrow_channel[:14]}… at nonce "
                    f"{nonce} is already stored"
                ) from exc
        row = self.get(receipt_id)
        assert row is not None
        return row

    def _transition(self, receipt_id: str, target: str, **fields: Any) -> AuthorizationRow:
        with self._lock:
            raw = self._conn.execute(
                "SELECT * FROM debit_authorizations WHERE receipt_id = ?", (receipt_id,)
            ).fetchone()
            if raw is None:
                raise StoreError(f"no authorization for receipt {receipt_id}")
            current = raw["status"]
            if target not in _ALLOWED.get(current, ()):
                raise StoreError(
                    f"refusing {current} → {target} for receipt {receipt_id}: the state "
                    "machine is forward-only, and a terminal row must never be reopened"
                )
            sets = ["status = ?"]
            args: list[Any] = [target]
            for column, value in fields.items():
                sets.append(f"{column} = ?")
                args.append(value)
            if target in _TERMINAL:
                sets.append("resolved_at = ?")
                args.append(_now())
            args.append(receipt_id)
            self._conn.execute(
                f"UPDATE debit_authorizations SET {', '.join(sets)} WHERE receipt_id = ?",
                args,
            )
            self._conn.commit()
        row = self.get(receipt_id)
        assert row is not None
        return row

    def record_plan(self, receipt_id: str, plan: dict[str, Any]) -> AuthorizationRow:
        """Store a simulation result.

        A FAILED simulation deliberately does not change the status: most reverts here are
        transient (a nonce the preceding submission has not filled yet, an unreachable
        node), and demoting the row would lose the queue position that keeps submissions
        in nonce order.
        """
        ok = bool(plan.get("ok"))
        with self._lock:
            raw = self._conn.execute(
                "SELECT status FROM debit_authorizations WHERE receipt_id = ?", (receipt_id,)
            ).fetchone()
            if raw is None:
                raise StoreError(f"no authorization for receipt {receipt_id}")
            current = raw["status"]
        if current in _TERMINAL:
            # A resolved row cannot be acted on, so writing a plan onto it would only
            # mutate history. Refused for the same reason every other transition out of a
            # terminal state is refused.
            raise StoreError(
                f"refusing {current} → {PLANNED} for receipt {receipt_id}: the state "
                "machine is forward-only, and a terminal row must never be reopened"
            )
        payload = json.dumps(plan, ensure_ascii=False, default=str)
        if not ok or current == SUBMITTED:
            with self._lock:
                self._conn.execute(
                    "UPDATE debit_authorizations SET last_plan_json = ?, last_error = ?, "
                    "attempts = attempts + 1 WHERE receipt_id = ?",
                    (payload, str(plan.get("error", ""))[:300], receipt_id),
                )
                self._conn.commit()
            row = self.get(receipt_id)
            assert row is not None
            return row
        return self._transition(
            receipt_id, PLANNED, last_plan_json=payload, last_error="",
            attempts=(self.get(receipt_id).attempts + 1),
        )

    def mark_submitted(self, receipt_id: str, tx_hash: str) -> AuthorizationRow:
        # submitted_at, not resolved_at: `resolved_at` is only stamped on a TERMINAL state,
        # so without this a broadcast row carries no record of WHEN the hub spent, and the
        # rolling daily cap would have nothing to measure.
        return self._transition(
            receipt_id, SUBMITTED,
            tx_hash=str(tx_hash or ""), last_error="", submitted_at=_now(),
        )

    def mark_confirmed(self, receipt_id: str, tx_hash: str = "") -> AuthorizationRow:
        fields: dict[str, Any] = {"last_error": ""}
        if tx_hash:
            fields["tx_hash"] = tx_hash
        return self._transition(receipt_id, CONFIRMED, **fields)

    def mark_collected_externally(self, receipt_id: str, *, note: str = "") -> AuthorizationRow:
        """Resolve a row whose debit the contract already collected without the hub sending it.

        Call this ONLY after reading ``usedReceipts(receiptId)`` as true on chain
        (``chain.receipt_already_used``). The money is in and cannot be collected twice, so
        CONFIRMED is the truthful terminal state — not ``abandoned``, which asserts the
        opposite (that the hub has no on-chain claim to it).

        ``tx_hash`` stays empty because the hub genuinely does not know it: the flag proves
        collection, not which transaction did it. ``last_error`` carries the explanation so
        an operator reading the row is not left wondering why it is confirmed with no hash.
        """
        return self._transition(
            receipt_id, CONFIRMED,
            last_error=(note or "collected on chain by a debit the hub did not send")[:300],
        )

    def abandon(self, receipt_id: str, reason: str) -> AuthorizationRow:
        """Give up on an authorization. The hub loses its on-chain claim to that debit.

        Never charges anybody anything — it records that this money will not be collected
        on chain, which is exactly the fact an operator needs to see.
        """
        return self._transition(receipt_id, ABANDONED, last_error=str(reason or "")[:300])

    # ── reads ────────────────────────────────────────────────────────────────

    def get(self, receipt_id: str) -> AuthorizationRow | None:
        with self._lock:
            raw = self._conn.execute(
                "SELECT * FROM debit_authorizations WHERE receipt_id = ?", (receipt_id,)
            ).fetchone()
        return _row(raw) if raw else None

    def units_collected_since(self, since_epoch: float) -> int:
        """Base units this hub has SENT to the chain since ``since_epoch``.

        Backs the rolling daily cap, and must be read from the store rather than counted in
        memory so the cap survives a process restart — an unattended timer restarting the
        hub would otherwise reset the budget every time.

        Counts ``submitted`` and ``confirmed`` rows only: those are the ones this hub
        broadcast. Rows resolved by ``mark_collected_externally`` are confirmed but carry no
        tx hash, and they must NOT count against the budget — the hub did not spend anything
        to collect them, so charging them to the cap would throttle it for someone else's
        transaction.
        """
        cutoff = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(max(0.0, since_epoch)))
        with self._lock:
            row = self._conn.execute(
                "SELECT COALESCE(SUM(amount_units), 0) AS units FROM debit_authorizations "
                "WHERE status IN (?, ?) AND tx_hash != '' AND submitted_at >= ?",
                (SUBMITTED, CONFIRMED, cutoff),
            ).fetchone()
        return int(row["units"] if row else 0)

    def unresolved(self, *, escrow_channel: str = "", limit: int = 500) -> list[AuthorizationRow]:
        """Rows still owed to the chain, ordered so the mirror can respect nonce order."""
        query = (
            "SELECT * FROM debit_authorizations WHERE status NOT IN (?, ?) "
            + ("AND escrow_channel = ? " if escrow_channel else "")
            + "ORDER BY escrow_channel, nonce LIMIT ?"
        )
        args: list[Any] = [CONFIRMED, ABANDONED]
        if escrow_channel:
            args.append(escrow_channel)
        args.append(int(limit))
        with self._lock:
            rows = self._conn.execute(query, args).fetchall()
        return [_row(r) for r in rows]

    def get_by_channel_nonce(self, escrow_channel: str, nonce: int) -> AuthorizationRow | None:
        """Lookup one authorization by (escrow channel, nonce), if any."""
        with self._lock:
            raw = self._conn.execute(
                "SELECT * FROM debit_authorizations WHERE escrow_channel = ? AND nonce = ? "
                "ORDER BY created_at DESC LIMIT 1",
                (escrow_channel, int(nonce)),
            ).fetchone()
        return _row(raw) if raw is not None else None

    def active_at(self, escrow_channel: str, nonce: int) -> AuthorizationRow | None:
        """The one LIVE authorization at (escrow channel, nonce), if any.

        `idx_auth_channel_nonce_active` makes this at most one row, so unlike
        `get_by_channel_nonce` — which returns the newest row of ANY status and ties on
        `created_at` when two land in the same second — this answers deterministically.
        Callers deciding how much a nonce still owes cannot use "whichever row sorted
        first"; an abandoned row would read as nothing owed.
        """
        with self._lock:
            raw = self._conn.execute(
                "SELECT * FROM debit_authorizations "
                "WHERE escrow_channel = ? AND nonce = ? "
                "AND status NOT IN (?, ?) LIMIT 1",
                (escrow_channel, int(nonce), ABANDONED, CONFIRMED),
            ).fetchone()
        return _row(raw) if raw is not None else None

    def superseded_in_window(self, escrow_channel: str, nonce: int) -> list[AuthorizationRow]:
        """The rows a later running total replaced at (escrow channel, nonce)."""
        with self._lock:
            raws = self._conn.execute(
                "SELECT * FROM debit_authorizations WHERE escrow_channel = ? AND nonce = ? "
                "AND status = ? AND last_error = ? ORDER BY amount_units DESC, created_at DESC",
                (escrow_channel, int(nonce), ABANDONED, SUPERSEDED_REASON),
            ).fetchall()
        return [_row(r) for r in raws]

    def revive_superseded(self, escrow_channel: str, nonce: int) -> AuthorizationRow | None:
        """Make the window's previous running total its claim again.

        The one exception to the forward-only state machine, and a narrow one: only a row
        abandoned as SUPERSEDED, only the largest of them (the immediate predecessor — a
        window only grows), and only while nothing else is live at that nonce. Its
        signature was never wrong; it was set aside for one that turned out to cover a call
        the hub did not deliver.
        """
        with self._lock:
            live = self._conn.execute(
                "SELECT 1 FROM debit_authorizations WHERE escrow_channel = ? AND nonce = ? "
                "AND status NOT IN (?, ?) LIMIT 1",
                (escrow_channel, int(nonce), ABANDONED, CONFIRMED),
            ).fetchone()
            if live is not None:
                return None
            raw = self._conn.execute(
                "SELECT * FROM debit_authorizations WHERE escrow_channel = ? AND nonce = ? "
                "AND status = ? AND last_error = ? ORDER BY amount_units DESC, created_at DESC "
                "LIMIT 1",
                (escrow_channel, int(nonce), ABANDONED, SUPERSEDED_REASON),
            ).fetchone()
            if raw is None:
                return None
            self._conn.execute(
                "UPDATE debit_authorizations SET status = ?, last_error = '', resolved_at = '' "
                "WHERE receipt_id = ? AND status = ? AND last_error = ?",
                (PENDING, raw["receipt_id"], ABANDONED, SUPERSEDED_REASON),
            )
            self._conn.commit()
            raw = self._conn.execute(
                "SELECT * FROM debit_authorizations WHERE receipt_id = ?", (raw["receipt_id"],)
            ).fetchone()
        return _row(raw)

    def next_for_channel(self, escrow_channel: str) -> AuthorizationRow | None:
        """The lowest-nonce unresolved authorization for one escrow channel.

        The mirror must submit in nonce order — the contract only accepts the channel's
        CURRENT nonce — so "the next one" is a store concept, not a caller's choice.
        """
        rows = self.unresolved(escrow_channel=escrow_channel, limit=1)
        return rows[0] if rows else None

    def stats(self) -> dict[str, Any]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT status, COUNT(*) AS n, COALESCE(SUM(amount_units), 0) AS units "
                "FROM debit_authorizations GROUP BY status"
            ).fetchall()
        by_status = {r["status"]: {"count": int(r["n"]), "units": int(r["units"])} for r in rows}
        owed = sum(
            v["units"] for k, v in by_status.items() if k not in _TERMINAL
        )
        return {
            "db_path": self.db_path,
            "by_status": by_status,
            "unsubmitted_units": owed,
            "unsubmitted_usd": owed / 1_000_000,
        }
