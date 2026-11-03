"""Settling a verified call: provisional verdicts, the settlement policy, finalizing or
expiring, and moving the hold, the bonds and the escrow authorization.
"""

from __future__ import annotations

import contextlib
import json
import logging
import time
from typing import TYPE_CHECKING, Any

from aimarket_hub import credits as hub_credits
from aimarket_hub.channels import APPEAL_BOND_PREFIX
from aimarket_hub.channels import hold_state
from aimarket_hub.metrics import record_verify_appeal
from aimarket_hub.signing import RECEIPT_SIG_VERSION

if TYPE_CHECKING:  # annotations only; the classes live in the facade module
    from aimarket_hub.verified_settlement import DeliveryVerdict, _Reading

logger = logging.getLogger("aimarket_hub.verified_settlement")


class SettlementFinalizingMixin:
    """Turn a verdict into a settlement: holds, bonds and escrow."""

    # ── Appeals: the provisional verdict ───────────────────────────────────

    @staticmethod
    def _is_paid(row: Any) -> bool:
        return bool(row["channel_id"]) and float(row["price_usd"] or 0) > 0

    def _appealable(self, row: Any, judge: Any = None) -> bool:
        """Only a PAID settlement is appealable: an advisory verdict moved no money, so
        there is nothing a window could protect and no bond rail to take one from. The
        court must be a different service from `judge`, the verifier that ruled."""
        return self._is_paid(row) and vs.appeals_enabled(judge)

    def _make_provisional(self, row: Any, reading: _Reading, verify_latency_ms: int,
                          *, judge: Any = None) -> None:
        """Record the first-instance verdict and open the appeal window. Money stays held.

        The verdict is stored (verdict_json) in the same conditional statement that makes
        the row provisional, so whoever finalizes it later — the deadline timer, the sweep,
        a restarted process — replays exactly this verdict. The envelope is signed at v3
        because it now carries the `appeal` terms: the deadline and the bond are what the
        losing party is told, and they must not be rewritable.
        """
        nonce = row["nonce"]
        passed = reading.passed
        delivery = reading.delivery
        judged_by = vs.verifier_id() if judge is None else judge.verifier_id
        window = vs.appeal_window_s()
        deadline = vs._now_s() + window
        bond = vs.appeal_bond_usd(float(row["price_usd"] or 0))
        first = {
            "verdict": "passed" if passed else "failed",
            "performed": True,
            "verified": passed,
            "verify_score": delivery.score,
            "audit_score": reading.audit_score,
            "trace_id": reading.trace_id,
            "reason": None if passed else "verify_failed",
            "delivery": {
                "fulfils": delivery.fulfils, "score": delivery.score,
                "reasons": list(delivery.reasons), "source": delivery.source,
            },
            "verify_latency_ms": int(verify_latency_ms),
            "verifier": judged_by,
        }
        if judge is not None and judge.routed:
            # A filed appeal must go to a court that is not this verifier; the route may
            # have changed by then, so remember which service ruled.
            first.update(verifier_route=judge.match, verifier_url=judge.url)
        env = json.loads(row["envelope_json"] or "{}")
        env.update(
            status=vs._PROVISIONAL,
            performed=True,
            verified=passed,
            verify_score=round(delivery.score, 4),
            audit_score=round(reading.audit_score, 4),
            delivery_fulfils=delivery.fulfils,
            delivery_reasons=list(delivery.reasons),
            verdict=first["verdict"],
            trace_id=reading.trace_id,
            verifier=judged_by,
            settled=False,
            reason=first["reason"],
            timestamp=vs._now_iso(),
            appeal={
                "status": "open",
                "window_s": window,
                "deadline": vs._iso(deadline),
                # Only the party the verdict went against may appeal it.
                "appealable_by": "buyer" if passed else "seller",
                "bond_usd": bond,
                "verifier": vs.appeal_verifier_id(),
            },
        )
        with contextlib.suppress(Exception):
            env["signature"] = self._signer.sign_verification(env)
        receipt = json.loads(row["receipt_json"] or "{}")
        receipt["verification"] = env
        won = self._transition(
            "UPDATE verified_settlements SET status = ?, envelope_json = ?, receipt_json = ?, "
            "verdict_json = ?, appeal_deadline = ? "
            "WHERE nonce = ? AND status = 'verifying' AND worker_token = ? RETURNING nonce",
            (vs._PROVISIONAL, json.dumps(env, ensure_ascii=False),
             json.dumps(receipt, ensure_ascii=False),
             json.dumps(first, ensure_ascii=False), deadline, nonce, row["worker_token"]),
        )
        # A waiting invoke (wait=true) gets the provisional verdict: it is the verdict,
        # and the buyer needs it — with its deadline — to decide whether to appeal.
        self._wake(nonce)
        if not won:
            logger.info("verified-settlement %s: provisional skipped (already resolved)", nonce)
            return
        logger.info(
            "verified-settlement %s: provisional %s (score=%.4f) — appealable by the %s "
            "until %s", nonce, first["verdict"], delivery.score,
            env["appeal"]["appealable_by"], env["appeal"]["deadline"],
        )
        self._schedule_deadline(nonce, deadline)

    def _finalize_expired(self, nonce: str) -> bool:
        """Close an unappealed window: settle on the first verdict. True iff this call
        won the row (and therefore moved the money)."""
        row = self._row(nonce)
        if not row or row["status"] != vs._PROVISIONAL:
            return False
        now = vs._now_s()
        if now < float(row["appeal_deadline"] or 0):
            return False
        first = json.loads(row["verdict_json"] or "{}")
        if not first.get("verdict"):
            # Cannot happen through this code (the verdict is written with the status);
            # a row that says otherwise is left held and loud rather than guessed at.
            logger.error("verified-settlement %s: provisional row has no stored verdict — "
                         "leaving the hold for operator review", nonce)
            return False
        appeal = dict(json.loads(row["envelope_json"] or "{}").get("appeal") or {})
        appeal.update(status="not_filed", closed_at=vs._iso(now))
        decision = {
            "verdict": first,
            "appeal": appeal,
            "bond": None,
            # A bond whose appeal never got recorded (a crash between taking the bond and
            # claiming the row) is the appellant's money with no appeal behind it.
            "release_orphan_bond": True,
        }
        won = self._transition(
            "UPDATE verified_settlements SET status = ?, final_json = ? "
            "WHERE nonce = ? AND status = ? AND appeal_deadline <= ? RETURNING nonce",
            (vs._FINALIZING, json.dumps(decision, ensure_ascii=False), nonce, vs._PROVISIONAL, now),
        )
        if not won:
            return False
        return self._settle_final(nonce)

    def _resolve_policy(
        self,
        row: Any,
        metis_env: dict[str, Any] | None,
        *,
        cause: str = "metis_error",
        force_refund: bool | None = None,
        judge: Any = None,
    ) -> None:
        """Indeterminate outcome: money moves by operator policy, never by verdict.

        No reputation event and no fault escalation — an unavailable, unverifying or
        self-contradicting verifier is not evidence about the provider. `force_refund`
        overrides the fail-open/fail-closed policy for causes where capturing would be
        wrong under ANY policy (a verifier claiming a pass below the operator bar).
        """
        policy = force_refund is None
        refund = vs.fail_closed() if policy else bool(force_refund)
        reason = (f"{cause}_fail_closed" if refund else f"{cause}_fail_open") if policy else cause
        # One alertable line per indeterminate settlement, with a stable prefix and the
        # cause. Some causes are reachable by ATTACKER-SHAPED CONTENT — most sharply
        # `delivery_verdict_missing`: a delivery echoed into the judge's answer can leave
        # an unterminated JSON string that swallows the real verdict. The default policy
        # is fail-closed, which makes that provider self-harm (nobody gets paid), but an
        # operator running fail-open is CAPTURING on it, so a sustained rate has to be
        # visible in the logs rather than inferable only from the envelope `reason`.
        logger.warning(
            "verified-settlement %s: INDETERMINATE cause=%s policy=%s outcome=%s",
            row["nonce"], cause,
            "forced" if not policy else ("fail_closed" if refund else "fail_open"),
            "refund" if refund else "capture",
        )
        performed, audit_score = vs._audit_signal(metis_env) if metis_env is not None else (False, 0.0)
        trace_id = (metis_env or {}).get("trace_id")
        self._finalize(
            row, verdict="indeterminate",
            # `performed` means "a verifier actually verified something" — an envelope
            # that merely arrived (an engine error, an unscored run) is not that.
            performed=performed,
            verified=False if refund else None,
            # No delivery verdict was usable, so the money-gate score is 0.0 rather
            # than the audit's self-confidence (which says nothing about the delivery).
            verify_score=0.0,
            trace_id=trace_id, reason=reason, force_refund=refund,
            audit_score=audit_score,
            verifier=None if judge is None else judge.verifier_id,
        )

    def _finalize(
        self,
        row: Any,
        *,
        verdict: str,
        performed: bool,
        verified: bool | None,
        verify_score: float,
        trace_id: Any,
        reason: str | None,
        force_refund: bool = False,
        audit_score: float = 0.0,
        delivery: DeliveryVerdict | None = None,
        from_status: str = "verifying",
        appeal: dict[str, Any] | None = None,
        bond: dict[str, Any] | None = None,
        release_orphan_bond: bool = False,
        verifier: str | None = None,
    ) -> bool:
        """Resolve one settlement row. Returns True iff THIS call won the terminal
        transition (and therefore fired the one-shot side-effects); False if the row
        was already resolved by a prior finalize (crash-recovery / double-schedule).

        `from_status` is the state the terminal transition is guarded on: 'verifying' for
        a verdict that settles as it lands (no appeal window — the original path, left
        exactly as it was), 'finalizing' for a decided appeal-path outcome. On the
        'finalizing' path this may be a REPLAY after a crash, so each hold is moved the
        decided way or, if an earlier attempt already moved it that way, left alone
        (`_settle_hold`) — and the appellant's `bond` is resolved with the invoke hold.

        `verifier` names the verifier that ruled on the envelope (None: leave the name the
        envelope already carries). Recorded with the decision, so a replay after a crash
        names the same one.
        """
        nonce = row["nonce"]
        if from_status == "verifying":
            # Persist the decision BEFORE touching either ledger. A stale worker can
            # neither override a provisional verdict nor move its held money.
            decision = {"verdict": {
                "verdict": verdict, "performed": performed, "verified": verified,
                "verify_score": verify_score, "trace_id": trace_id, "reason": reason,
                "force_refund": force_refund, "audit_score": audit_score,
                "delivery": None if delivery is None else {
                    "fulfils": delivery.fulfils, "score": delivery.score,
                    "reasons": list(delivery.reasons), "source": delivery.source,
                },
            }}
            if verifier:
                # Not "verifier": on the appeal path that key names the court that decided.
                decision["verdict"]["judged_by"] = verifier
            if not self._transition(
                "UPDATE verified_settlements SET status = ?, final_json = ? "
                "WHERE nonce = ? AND status = 'verifying' AND worker_token = ? RETURNING nonce",
                (vs._FINALIZING, json.dumps(decision, ensure_ascii=False), nonce, row["worker_token"]),
            ):
                return False
            from_status = vs._FINALIZING
        paid = bool(row["channel_id"]) and float(row["price_usd"] or 0) > 0
        refunding = force_refund or verdict == "failed"

        settled = False
        ledger_note = None
        bond_note = None
        if paid and from_status == vs._FINALIZING:
            settled, ledger_note, captured_now = self._settle_hold(nonce, capture=not refunding)
            if captured_now:
                # Only on the attempt that captured: a replay must not accrue twice.
                self._accrue_acex(row)
            if refunding and ledger_note is None:
                self._withdraw_escrow_authorization(nonce)
        elif paid:
            if refunding:
                res = vs.release_hold(nonce)
                if res.get("error"):
                    ledger_note = f"release_failed:{res['error']}"
                    logger.error("verified-settlement %s: release failed: %s", nonce, res["error"])
                else:
                    self._withdraw_escrow_authorization(nonce)
            else:
                res = vs.capture_hold(nonce)
                if res.get("error"):
                    ledger_note = f"capture_failed:{res['error']}"
                    logger.error("verified-settlement %s: capture failed: %s", nonce, res["error"])
                else:
                    settled = True
                    self._accrue_acex(row)
        else:
            # Advisory: nothing was held; the invoke settled (freely) at response time.
            settled = not refunding
        if from_status == vs._FINALIZING:
            if bond:
                bond_note = self._settle_bond(nonce, bond)
            if release_orphan_bond:
                self._release_orphan_bond(nonce)
        if ledger_note or bond_note:
            # Keep the durable decision for the sweeper. Never sign a refund or a
            # settlement whose corresponding ledger operation failed.
            logger.error("verified-settlement %s: final decision awaits ledger recovery: %s",
                         nonce, ledger_note or bond_note)
            return False

        env = json.loads(row["envelope_json"] or "{}")
        env.update(
            status="refunded" if refunding else "settled",
            performed=performed,
            verified=verified,
            verify_score=round(verify_score, 4),
            audit_score=round(audit_score, 4),
            delivery_fulfils=None if delivery is None else delivery.fulfils,
            delivery_reasons=[] if delivery is None else list(delivery.reasons),
            verdict=verdict,
            trace_id=trace_id,
            settled=settled,
            reason=ledger_note or reason,
            timestamp=vs._now_iso(),
        )
        if verifier:
            # Signed (v2 binds `verifier`): the verdict is attributed to the service that
            # gave it, not to whichever verifier the pending envelope expected.
            env["verifier"] = verifier
        if appeal is not None:
            appeal = dict(appeal)
            if bond_note:
                appeal["bond_ledger_note"] = bond_note
            env["appeal"] = appeal
        with contextlib.suppress(Exception):
            env["signature"] = self._signer.sign_verification(env)

        rejection_json = ""
        rejection: dict[str, Any] | None = None
        if refunding:
            rejection = {
                "type": "verification_rejection",
                "product_id": row["product_id"],
                "capability_id": row["capability_id"],
                "channel_id": row["channel_id"] or None,
                "reason": env["reason"],
                "verify_score": env["verify_score"],
                # The buyer's "why" travels with the refund evidence, so a dispute does
                # not require pulling the verifier trace to learn what failed.
                "delivery_reasons": env["delivery_reasons"],
                "trace_id": trace_id,
                "timestamp": env["timestamp"],
                "refunded": paid and ledger_note is None,
                "nonce": f"vfail_{int(time.time())}_{row['product_id'][:8]}",
            }
            with contextlib.suppress(Exception):
                # v2 canonical: on a rejection every v1 field is a constant (price 0,
                # success 0, latency 0), so v1 authenticated the receipt's identity but
                # not its `reason`, `verify_score` or `delivery_reasons` — the parts a
                # dispute is actually argued from.
                rejection["signature"] = self._signer.sign_receipt(
                    rejection, version=RECEIPT_SIG_VERSION
                )
            rejection_json = json.dumps(rejection, ensure_ascii=False)

        receipt = json.loads(row["receipt_json"] or "{}")
        receipt["verification"] = env

        # Exactly-once gate: the terminal transition is the source of truth. The worker's
        # claim (_run) flips pending→verifying, so only the run that flips verifying→terminal
        # here may fire the one-shot side-effects (escalation, reputation, waiter wakeup).
        # A crash between money-movement above and this UPDATE leaves the row 'verifying';
        # reconcile re-runs it, and this guard makes the re-run — not a phantom double —
        # do the honors, so record_verified_failure can never double-count a fault.
        if from_status == "verifying":
            cur = self._db._conn.execute(
                "UPDATE verified_settlements SET status = ?, envelope_json = ?, "
                "rejection_json = ?, receipt_json = ?, resolved_at = ? "
                "WHERE nonce = ? AND status = 'verifying'",
                (
                    env["status"], json.dumps(env, ensure_ascii=False), rejection_json,
                    json.dumps(receipt, ensure_ascii=False), env["timestamp"], nonce,
                ),
            )
            self._db._conn.commit()
            won = getattr(cur, "rowcount", 0) == 1
        else:
            won = self._transition(
                "UPDATE verified_settlements SET status = ?, envelope_json = ?, "
                "rejection_json = ?, receipt_json = ?, resolved_at = ? "
                "WHERE nonce = ? AND status = ? RETURNING nonce",
                (
                    env["status"], json.dumps(env, ensure_ascii=False), rejection_json,
                    json.dumps(receipt, ensure_ascii=False), env["timestamp"], nonce,
                    from_status,
                ),
            )
        if not won:
            # A prior finalize already resolved this row: do NOT re-move reputation/stake
            # (money was protected by the single-use hold). Still wake any waiter.
            ev = self._events.pop(nonce, None)
            if ev:
                ev.set()
            logger.info("verified-settlement %s: finalize skipped (already resolved)", nonce)
            return False

        # Verify-first escalation — now that we own the terminal transition, so it runs
        # exactly once. Only a genuine verdict "failed" counts (a policy refund /
        # indeterminate verdict is not evidence about the provider); `paid` + the channel
        # (consumer) id gate it further so an advisory verdict never touches stake and one
        # buyer cannot slash alone. Errors are logged, not swallowed, so a wiring/type
        # regression surfaces instead of vanishing.
        if verdict == "failed" and rejection is not None and self._supply_security is not None and (row["provider_id"] or "").strip():
            try:
                self._supply_security.record_verified_failure(
                    publisher_id=row["provider_id"],
                    product_id=row["product_id"],
                    capability_id=row["capability_id"],
                    consumer_id=row["channel_id"] or "",
                    paid=paid,
                    rejection=rejection,
                )
            except Exception as exc:
                logger.warning(
                    "verified-settlement %s: verify-first escalation failed: %s", nonce, exc
                )

        ev = self._events.pop(nonce, None)
        if ev:
            ev.set()
        logger.info(
            "verified-settlement %s: %s (verdict=%s score=%.4f trace=%s verifier=%s)",
            nonce, env["status"], verdict, env["verify_score"] or 0.0, trace_id, env.get("verifier"),
        )
        return True

    @staticmethod
    def _withdraw_escrow_authorization(receipt_id: str) -> None:
        """Take a refunded call's on-chain debit authorization out of the bridge queue.

        On an escrow-backed channel the buyer signs the debit BEFORE the work, and the hub
        stores it for the escrow mirror. A failing verdict releases the hold, so the ledger
        never records that debit and the mirror would refuse to collect it — correctly —
        but would also keep the row pending until its deadline, and the queue is strictly
        nonce-ordered: every later debit on that channel would wait behind money the hub
        has already decided not to take. Abandoning it says so at once. Best effort: a hub
        without the bridge has no such row.
        """
        try:
            from aimarket_hub.escrow_bridge import store as bridge_store

            authorizations = bridge_store.AuthorizationStore(create=False)
        except Exception:
            return
        try:
            from aimarket_hub.escrow_bridge import authorization as bridge_auth

            # withdraw, not abandon: the row is its nonce window's running total, and the
            # calls before this one keep a claim through the authorization it replaced.
            bridge_auth.withdraw(receipt_id, authorizations,
                                 reason="refunded: the delivery failed verification")
        except Exception as exc:
            logger.warning("verified-settlement %s: could not withdraw the escrow authorization: %s",
                           receipt_id, type(exc).__name__)
        finally:
            with contextlib.suppress(Exception):
                authorizations.close()

    # ── Appeals: moving the money once a final outcome is decided ──────────

    @staticmethod
    def _settle_hold(receipt_id: str, *, capture: bool) -> tuple[bool, str | None, bool]:
        """Move one channel hold the decided way. (settled, ledger_note, moved_now).

        capture_hold/release_hold are one-shot, so a replay of a decided outcome finds the
        hold already resolved. That is success when an earlier attempt resolved it THE SAME
        WAY — and a ledger fault to surface when it went the other way (or vanished).
        """
        res = vs.capture_hold(receipt_id) if capture else vs.release_hold(receipt_id)
        if not res.get("error"):
            return capture, None, capture
        wanted = "captured" if capture else "released"
        if hold_state(receipt_id) == wanted:
            return capture, None, False
        verb = "capture" if capture else "release"
        logger.error("verified-settlement %s: %s failed: %s", receipt_id, verb, res["error"])
        return False, f"{verb}_failed:{res['error']}", False

    def _settle_bond(self, nonce: str, bond: dict[str, Any]) -> str | None:
        """Forfeit (capture) or return (release) the appellant's bond. A note on failure.

        A forfeited bond pays for the second verification, so it is captured into the
        OPERATOR's books: on a channel it is a recorded debit like any invoke, on credits
        it is spend. Neither rail pays it to the other party — winning an appeal returns
        the winner's own money, it is not a prize funded by the loser.
        """
        receipt_id = str(bond.get("receipt_id") or APPEAL_BOND_PREFIX + nonce)
        capture = bond.get("action") == "capture"
        if bond.get("rail") == "credits":
            ledger = hub_credits.ledger()
            if ledger is None:
                logger.error("verified-settlement %s: appeal bond on credits but no credits "
                             "ledger is configured — bond left held", nonce)
                return "bond_unresolved:no_credits_ledger"
            res = ledger.capture_hold(receipt_id) if capture else ledger.release_hold(receipt_id)
            wanted = "captured" if capture else "released"
            if res.get("error") or res.get("already") not in (None, wanted):
                detail = res.get("error") or f"already {res.get('already')}"
                logger.error("verified-settlement %s: appeal bond %s failed: %s",
                             nonce, "capture" if capture else "release", detail)
                return f"bond_{'capture' if capture else 'release'}_failed:{detail}"
            return None
        _, note, _ = self._settle_hold(receipt_id, capture=capture)
        return note and f"bond_{note}"

    @staticmethod
    def _release_orphan_bond(nonce: str) -> None:
        """Hand back a bond taken for an appeal that was never recorded (see
        `file_appeal`: the bond is held before the row is claimed). No-op when none."""
        receipt_id = APPEAL_BOND_PREFIX + nonce
        if hold_state(receipt_id) == "held":
            res = vs.release_hold(receipt_id)
            logger.warning("verified-settlement %s: released an orphaned appeal bond (%s)",
                           nonce, res.get("error") or "ok")
        ledger = hub_credits.ledger()
        if ledger is not None:
            status = ledger.hold_status(receipt_id)
            if status and status["status"] == "held":
                res = ledger.release_hold(receipt_id)
                logger.warning("verified-settlement %s: released an orphaned appeal bond on "
                               "credits (%s)", nonce, res.get("error") or "ok")

    def _settle_final(self, nonce: str) -> bool:
        """Execute the outcome decided for a 'finalizing' row. Safe to replay.

        Everything a verdict causes happens here and only here on the appeal path —
        capture or release, the bond, the signed envelope and rejection receipt, the slash
        ladder (inside `_finalize`, on its won terminal transition) and the reputation event
        — because until now none of it was final.
        """
        row = self._row(nonce)
        if not row or row["status"] != vs._FINALIZING:
            return False
        decision = json.loads(row["final_json"] or "{}")
        v = decision.get("verdict") or {}
        if not v.get("verdict"):
            logger.error("verified-settlement %s: finalizing row has no decided outcome — "
                         "leaving it for operator review", nonce)
            return False
        d = v.get("delivery")
        delivery = vs.DeliveryVerdict(
            fulfils=bool(d["fulfils"]), score=float(d["score"]),
            reasons=list(d.get("reasons") or []), source=str(d.get("source") or "answer"),
        ) if isinstance(d, dict) else None
        passed = v["verdict"] == "passed"
        won = self._finalize(
            row, verdict=v["verdict"], performed=bool(v.get("performed", True)),
            verified=v.get("verified"), verify_score=float(v.get("verify_score") or 0.0),
            trace_id=v.get("trace_id"), reason=v.get("reason"),
            audit_score=float(v.get("audit_score") or 0.0), delivery=delivery,
            force_refund=bool(v.get("force_refund")),
            from_status=vs._FINALIZING, appeal=decision.get("appeal"),
            bond=decision.get("bond"),
            release_orphan_bond=bool(decision.get("release_orphan_bond")),
            verifier=v.get("judged_by") or None,
        )
        if won and v["verdict"] in ("passed", "failed"):
            self._emit_reputation(row, passed=passed,
                                  verify_latency_ms=int(v.get("verify_latency_ms") or 0))
            appeal = decision.get("appeal") or {}
            if appeal.get("status") == "resolved":
                record_verify_appeal(str(appeal.get("by") or ""), str(appeal.get("outcome") or ""))
        return won


# Imported after the class on purpose: methods read aimarket_hub.verified_settlement at call time
# (where its settings and test patches live), and either module may load first.
from aimarket_hub import verified_settlement as vs  # noqa: E402
