"""Running verifications: registering a paid call, the workers that claim and run it,
deadlines, appeal sweeps, and waiting on the outcome.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import random
import secrets
import time
from collections.abc import Callable
from typing import Any

from aimarket_hub.channels import UNRESOLVED_SETTLEMENT_STATUSES
from aimarket_hub.db_backend import returning_one

logger = logging.getLogger("aimarket_hub.verified_settlement")


class SettlementSchedulingMixin:
    """Register calls, schedule and run their verification, and report the outcome."""

    # ── Registration (called inline from the invoke handler) ──────────────

    def register(
        self,
        *,
        nonce: str,
        product_id: str,
        capability_id: str,
        channel_id: str,
        provider_id: str,
        price_usd: float,
        intent: str,
        output: Any,
        mode: str,
        receipt: dict[str, Any],
        advisory: bool,
    ) -> dict[str, Any]:
        """Persist a pending settlement and schedule its background verification.

        Returns the pending envelope (already attached to the receipt by the caller).
        """
        env = vs.pending_envelope(nonce, capability_id, mode, advisory=advisory)
        # Mutate the caller's receipt in place so the invoke response and the
        # stored copy both carry the pending envelope from the start.
        receipt["verification"] = env
        try:
            output_json = json.dumps(output, ensure_ascii=False, sort_keys=True, default=str)
        except (TypeError, ValueError):
            output_json = json.dumps(str(output), ensure_ascii=False)
        # Bound the stored row: _compose_input only ever sends the first
        # _MAX_OUTPUT_CHARS to Metis anyway, so a giant provider payload need not
        # bloat the DB or per-task resident memory.
        if len(output_json) > vs._MAX_OUTPUT_CHARS:
            output_json = output_json[:vs._MAX_OUTPUT_CHARS] + "…[truncated]"
        self._db._conn.execute(
            "INSERT INTO verified_settlements "
            "(nonce, product_id, capability_id, channel_id, provider_id, price_usd, "
            " intent, output_json, mode, status, envelope_json, receipt_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?)",
            (
                nonce, product_id, capability_id,
                channel_id if not advisory else "",
                provider_id, price_usd, intent, output_json, mode,
                json.dumps(env, ensure_ascii=False),
                json.dumps(receipt, ensure_ascii=False),
                vs._now_iso(),
            ),
        )
        self._db._conn.commit()
        self._schedule(nonce)
        return env

    def _schedule(self, nonce: str) -> None:
        task = asyncio.create_task(self._run(nonce))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    # ── Lookup / wait ──────────────────────────────────────────────────────

    def lookup(self, nonce: str) -> dict[str, Any] | None:
        row = self._db._conn.execute(
            "SELECT * FROM verified_settlements WHERE nonce = ?", (nonce,)
        ).fetchone()
        if not row:
            return None
        out: dict[str, Any] = {
            "verification": json.loads(row["envelope_json"] or "{}"),
            "receipt": json.loads(row["receipt_json"] or "{}"),
        }
        if row["rejection_json"]:
            out["rejection_receipt"] = json.loads(row["rejection_json"])
        return out

    async def wait_for(self, nonce: str, timeout: float) -> dict[str, Any] | None:
        """Wait (bounded) for the verdict. Returns the resolved lookup dict, or
        None on timeout — the caller then responds with the pending envelope."""
        rec = self.lookup(nonce)
        if rec and rec["verification"].get("status") not in ("", "pending"):
            return rec
        ev = self._events.setdefault(nonce, asyncio.Event())
        try:
            await asyncio.wait_for(ev.wait(), timeout=max(1.0, timeout))
        except asyncio.TimeoutError:
            return None
        return self.lookup(nonce)

    # ── Lifecycle ──────────────────────────────────────────────────────────

    async def reconcile(self) -> int:
        """Re-queue unresolved settlements (startup: restarts never strand holds).

        Pending work is claimed atomically. A verifying row is reclaimed only after
        its worker lease expires; starting another process does not steal live work.

        The appeal statuses are re-queued too, each to the step that owns it: a
        provisional row gets its deadline timer back, an appeal (filed, or claimed by a
        process that died mid-call) goes back to the appeal court, and a row that died in
        'finalizing' replays the outcome already decided for it.
        """
        marks = ",".join("?" for _ in UNRESOLVED_SETTLEMENT_STATUSES)
        rows = self._db._conn.execute(
            f"SELECT nonce, status, appeal_deadline FROM verified_settlements "
            f"WHERE status IN ({marks})",
            UNRESOLVED_SETTLEMENT_STATUSES,
        ).fetchall()
        appeal_rows = 0
        for row in rows:
            status, nonce = row["status"], row["nonce"]
            if status in ("pending", "verifying"):
                self._schedule(nonce)
                continue
            appeal_rows += 1
            if status == vs._PROVISIONAL:
                self._schedule_deadline(nonce, float(row["appeal_deadline"] or 0.0))
            elif status in (vs._APPEALED, vs._APPEAL_VERIFYING):
                self._schedule_appeal(nonce, reclaim_stale=True)
            elif status == vs._FINALIZING:
                try:
                    self._settle_final(nonce)
                except Exception as exc:  # noqa: BLE001 - one bad row must not stop the rest
                    logger.error("verified-settlement %s: replaying final settlement failed: %s",
                                 nonce, exc)
        if rows:
            logger.info("verified-settlement: re-queued %d unresolved verification(s)", len(rows))
        if self._sweeper is None:
            self._sweeper = self._spawn(self._sweep_loop())
        return len(rows)

    def _spawn(self, coro: Any) -> asyncio.Task | None:
        """Schedule background work, or report that there is no loop to run it on.

        Every appeal-side step is also reachable by the sweep and by reconcile, so work
        that cannot be scheduled from a loop-less caller (a CLI, a synchronous test) is
        deferred to them rather than raising after a transition was already committed.
        """
        try:
            task = asyncio.get_running_loop().create_task(coro)
        except RuntimeError:
            coro.close()
            return None
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    def _schedule_deadline(self, nonce: str, deadline: float) -> None:
        key = f"deadline:{nonce}"
        if key in self._inflight:
            return
        self._inflight.add(key)

        async def _at() -> None:
            try:
                delay = deadline - vs._now_s()
                if delay > 0:
                    await asyncio.sleep(delay)
                self._finalize_expired(nonce)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - the sweep retries; say why it has to
                logger.error("verified-settlement %s: closing the appeal window failed: %s",
                             nonce, exc)
            finally:
                self._inflight.discard(key)

        if self._spawn(_at()) is None:
            self._inflight.discard(key)

    def _schedule_appeal(self, nonce: str, *, reclaim_stale: bool = False) -> None:
        key = f"appeal:{nonce}"
        if key in self._inflight:
            return
        self._inflight.add(key)

        async def _go() -> None:
            try:
                await self._run_appeal(nonce, reclaim_stale=reclaim_stale)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - the row stays put for reconcile
                logger.error("verified-settlement %s: hearing the appeal failed: %s", nonce, exc)
            finally:
                self._inflight.discard(key)

        if self._spawn(_go()) is None:
            self._inflight.discard(key)

    async def _sweep_loop(self) -> None:
        """Safety net for the per-row timers: a row made provisional by another worker
        process (or one whose timer died with its process) is still finalized when its
        window closes, and a filed appeal nobody picked up is sent to the court."""
        while True:
            await asyncio.sleep(vs.appeal_sweep_s())
            try:
                self.sweep_appeals()
            except Exception as exc:  # noqa: BLE001 - a bad pass must never kill the loop
                logger.warning("verified-settlement: appeal sweep failed: %s", exc)

    def sweep_appeals(self) -> dict[str, int]:
        """One pass: finalize every provisional row whose window has closed, and queue
        every filed appeal. Idempotent — each step is a conditional transition."""
        now = vs._now_s()

        def each(rows: Any, step: Callable[[str], Any], what: str) -> int:
            # One row that raises must not abort the pass: the rows after it — a stale
            # `verifying` claim to reclaim, a decided outcome to settle — would wait for
            # the next pass, and a row that always raises would stall them forever.
            done = 0
            for row in rows:
                try:
                    done += 1 if step(row["nonce"]) else 0
                except Exception as exc:  # noqa: BLE001
                    logger.error("verified-settlement %s: %s failed in the sweep: %s", row["nonce"], what, exc)
            return done

        expired = self._db._conn.execute(
            "SELECT nonce FROM verified_settlements "
            "WHERE status = ? AND appeal_deadline > 0 AND appeal_deadline <= ?",
            (vs._PROVISIONAL, now),
        ).fetchall()
        finalized = each(expired, self._finalize_expired, "finalizing an expired window")
        waiting = self._db._conn.execute(
            "SELECT nonce FROM verified_settlements WHERE status = ? "
            "OR (status = ? AND lease_until < ?)", (vs._APPEALED, vs._APPEAL_VERIFYING, now),
        ).fetchall()
        each(waiting, lambda nonce: self._schedule_appeal(nonce, reclaim_stale=True) or True, "queueing an appeal")
        stale = self._db._conn.execute(
            "SELECT nonce FROM verified_settlements WHERE status = 'pending' "
            "OR (status = 'verifying' AND lease_until < ?)", (now,),
        ).fetchall()
        each(stale, lambda nonce: self._schedule(nonce) or True, "reclaiming a verification")
        finalizing = self._db._conn.execute(
            "SELECT nonce FROM verified_settlements WHERE status = ?", (vs._FINALIZING,),
        ).fetchall()
        each(finalizing, self._settle_final, "settling a decided outcome")
        return {"finalized": finalized, "appeals_queued": len(waiting)}

    def _transition(self, sql: str, params: tuple) -> bool:
        """Run one conditional UPDATE … RETURNING and report whether THIS call won it.

        RETURNING rather than a row count: on the shared SQLite connection the count is a
        connection-global another thread can overwrite (db_backend.claim_unique). The
        commit comes before the caller acts on the win, so a rollback triggered elsewhere
        on the shared connection cannot undo a claim whose money movement then commits.
        """
        return returning_one(self._db._conn, sql, params, commit=True) is not None

    def _row(self, nonce: str) -> Any:
        return self._db._conn.execute(
            "SELECT * FROM verified_settlements WHERE nonce = ?", (nonce,)
        ).fetchone()

    def _wake(self, nonce: str) -> None:
        ev = self._events.pop(nonce, None)
        if ev:
            ev.set()

    async def shutdown(self) -> None:
        for task in list(self._tasks):
            task.cancel()
        for task in list(self._tasks):
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task

    # ── Worker ─────────────────────────────────────────────────────────────

    async def _run(self, nonce: str) -> None:
        row = self._claim_worker(nonce, "pending", "verifying")
        if not row:
            return
        async with self._worker_heartbeat(row):
            await self._run_claimed(row)

    def _claim_worker(self, nonce: str, pending: str, working: str) -> Any:
        token = secrets.token_hex(16)
        now = vs._now_s()
        if not self._transition(
            "UPDATE verified_settlements SET status = ?, worker_token = ?, lease_until = ? "
            "WHERE nonce = ? AND (status = ? OR (status = ? AND lease_until < ?)) RETURNING nonce",
            (working, token, now + 120, nonce, pending, working, now),
        ):
            return None
        row = self._row(nonce)
        return row if row and row["worker_token"] == token else None

    @contextlib.asynccontextmanager
    async def _worker_heartbeat(self, row: Any):
        async def renew():
            while True:
                await asyncio.sleep(30)
                if not self._transition(
                    "UPDATE verified_settlements SET lease_until = ? "
                    "WHERE nonce = ? AND worker_token = ? AND status = ? RETURNING nonce",
                    (vs._now_s() + 120, row["nonce"], row["worker_token"], row["status"]),
                ):
                    return
        heartbeat = asyncio.create_task(renew())
        try:
            yield
        finally:
            heartbeat.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await heartbeat
            self._transition(
                "UPDATE verified_settlements SET lease_until = 0 "
                "WHERE nonce = ? AND worker_token = ? AND status = ? RETURNING nonce",
                (row["nonce"], row["worker_token"], row["status"]),
            )

    async def _run_claimed(self, row: Any) -> None:
        nonce = row["nonce"]

        started = time.monotonic()
        attempts = int(row["attempts"] or 0)
        engine_attempts = int(row["engine_attempts"] or 0)
        backoff = vs.retry_backoff_s()
        last_env: dict[str, Any] | None = None
        last_judge: Any = None   # the verifier that produced last_env

        while True:
            # Who judges is read per attempt, like every other knob: a route the operator
            # fixes reaches a settlement already waiting on it. An unusable route is
            # retried like an unreachable verifier — the hold stays (buyer-safe: nothing
            # is debited without a verdict) — and is NEVER replaced by the default
            # verifier, which nobody chose for this capability.
            try:
                judge = vs.verifier_route(row["capability_id"])
            except vs.RouteUnavailable as exc:
                vs._warn_once(f"route:{exc}", "verified-settlement: verifier routing refused (%s) — "
                              "routed settlements wait until it is fixed", exc)
                judge, kind, payload, verify_latency_ms = None, "transport", "route_unavailable", 0
            else:
                t0 = time.time()
                # Cap simultaneous calls per verifier across all rows.
                async with self._concurrency_gate(judge.gate):
                    kind, payload = await self._attempt(row, judge)
                verify_latency_ms = int((time.time() - t0) * 1000)
            attempts += 1
            self._persist_progress(nonce, attempts, engine_attempts)

            if kind == "verdict":
                self._resolve_verdict(row, payload, verify_latency_ms, judge=judge)
                return
            if kind == "fatal":
                logger.warning("verified-settlement %s: fatal verify error (%s) — applying policy", nonce, payload)
                self._resolve_policy(row, last_env, judge=judge)
                return
            if kind == "engine":
                last_env, last_judge = payload, judge
                engine_attempts += 1
                self._persist_progress(nonce, attempts, engine_attempts)
                if engine_attempts > vs.engine_retries():
                    logger.warning(
                        "verified-settlement %s: %d engine-error envelope(s) — applying policy",
                        nonce, engine_attempts,
                    )
                    self._resolve_policy(row, last_env, judge=last_judge)
                    return
            # kind in ("transport", "engine"): retry. No overall deadline by default —
            # an unresolved hold is buyer-safe (debit never recorded until a verdict).
            deadline = vs.max_wait_s()
            if deadline > 0 and (time.monotonic() - started) > deadline:
                logger.warning("verified-settlement %s: max wait %.0fs elapsed — applying policy", nonce, deadline)
                self._resolve_policy(row, last_env, judge=last_judge)
                return
            # Jittered backoff de-synchronises a startup herd of re-queued rows so
            # they don't all retry Metis on the same tick.
            await asyncio.sleep(backoff * random.uniform(0.5, 1.5))
            backoff = min(backoff * 2, 300.0)


# Imported after the class on purpose: methods read aimarket_hub.verified_settlement at call time
# (where its settings and test patches live), and either module may load first.
from aimarket_hub import verified_settlement as vs  # noqa: E402
