"""Appeals: filing one, the bonds both sides hold, hearing and deciding it, and appeal
statistics.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import logging
import random
import time
from typing import TYPE_CHECKING, Any

from aimarket_hub import credits as hub_credits
from aimarket_hub.channels import APPEAL_BOND_PREFIX
from aimarket_hub.channels import channel_secret_error
from aimarket_hub.channels import hold_channel
from aimarket_hub.channels import hold_state

if TYPE_CHECKING:  # annotations only; the classes live in the facade module
    from aimarket_hub.verified_settlement import _Reading

logger = logging.getLogger("aimarket_hub.verified_settlement")


class SettlementAppealsMixin:
    """File, hear and decide appeals; appeal statistics."""

    # ── Appeals: filing ────────────────────────────────────────────────────

    def file_appeal(
        self,
        nonce: str,
        *,
        channel_secret: str = "",
        api_key: str = "",
        statement: str = "",
    ) -> dict[str, Any]:
        """Appeal a provisional verdict. Raises AppealRefused; returns the filed appeal.

        Who: only the party the verdict went against. A PASS is appealed by the buyer,
        authenticated by the channel secret (the credential that authorised the hold); a
        FAIL by the seller, authenticated by the X-API-Key of the publisher's hub credits
        account. A seller paid on-chain through `payout_address` and holding no credits
        account cannot be bonded by this hub, so its appeal is refused rather than taken
        unbonded.

        Order: the bond is held FIRST, then the row is claimed provisional→appealed in one
        conditional statement (still inside the window). Claim-first would leave an
        appealed row with no bond after a crash; bond-first leaves at worst an orphaned
        bond, which the window's finalization (and the hold reaper) hand back. A claim
        that loses — the window closed, or another appeal won — releases the bond here.
        """
        problem = vs.appeal_court_error()
        # With verifier routes the court is checked against whichever verifier ruled on
        # THIS settlement, which needs the row; without them, exactly as it always was.
        if problem and not vs.routes_configured():
            raise vs.AppealRefused(503, "appeals_unavailable", problem)
        if len(statement or "") > vs._MAX_APPEAL_STATEMENT_CHARS:
            raise vs.AppealRefused(400, "statement_too_long",
                                f"the statement is capped at {vs._MAX_APPEAL_STATEMENT_CHARS} characters")
        row = self._row(nonce)
        if not row:
            raise vs.AppealRefused(404, "verification_not_found", "no such verification")
        ruled = self._first_instance(row)
        if ruled is not None:
            problem = vs.appeal_court_error(ruled)
        if problem:
            raise vs.AppealRefused(503, "appeals_unavailable", problem)
        self._refuse_unless_open(row)
        env = json.loads(row["envelope_json"] or "{}")
        terms = dict(env.get("appeal") or {})
        appellant = terms.get("appealable_by") or (
            "buyer" if json.loads(row["verdict_json"] or "{}").get("verdict") == "passed" else "seller"
        )
        bond = float(terms.get("bond_usd") or vs.appeal_bond_usd(float(row["price_usd"] or 0)))
        receipt_id = APPEAL_BOND_PREFIX + nonce
        if appellant == "buyer":
            rail, account = self._hold_buyer_bond(row, receipt_id, bond,
                                                  channel_secret=channel_secret, api_key=api_key)
        else:
            rail, account = self._hold_seller_bond(row, receipt_id, bond,
                                                   channel_secret=channel_secret, api_key=api_key)

        filed = vs._now_s()
        statement = (statement or "").strip()
        terms.update(
            status="filed",
            by=appellant,
            filed_at=vs._iso(filed),
            bond_usd=bond,
            # The public lookup never serves the statement itself (it may carry anything
            # the appellant chose to write); the digest binds which statement was heard.
            statement_sha256=hashlib.sha256(statement.encode()).hexdigest() if statement else None,
            verifier=vs.appeal_verifier_id(),
        )
        env.update(status=vs._APPEALED, appeal=terms, timestamp=vs._now_iso())
        with contextlib.suppress(Exception):
            env["signature"] = self._signer.sign_verification(env)
        receipt = json.loads(row["receipt_json"] or "{}")
        receipt["verification"] = env
        won = self._transition(
            "UPDATE verified_settlements SET status = ?, appeal_by = ?, appeal_rail = ?, "
            "appeal_account = ?, appeal_bond_usd = ?, appeal_statement = ?, "
            "appeal_filed_at = ?, envelope_json = ?, receipt_json = ? "
            "WHERE nonce = ? AND status = ? AND appeal_deadline > ? RETURNING nonce",
            (vs._APPEALED, appellant, rail, account, bond, statement, filed,
             json.dumps(env, ensure_ascii=False), json.dumps(receipt, ensure_ascii=False),
             nonce, vs._PROVISIONAL, filed),
        )
        if not won:
            fresh = self._row(nonce)
            # The bond receipt is one per settlement, so if ANY appeal got recorded (a
            # concurrent request by the same party won the claim — possibly using this very
            # hold) the bond is that appeal's now. Releasing it here would let the recorded
            # appeal run unbonded. Only a bond with no recorded appeal behind it goes back.
            if fresh is not None and not (fresh["appeal_by"] or ""):
                self._settle_bond(nonce, {"rail": rail, "receipt_id": receipt_id,
                                          "action": "release"})
            self._refuse_unless_open(fresh)     # says why (closed / already appealed)
            raise vs.AppealRefused(409, "not_appealable", "the verification changed state; retry")
        logger.info("verified-settlement %s: appeal filed by the %s (bond $%.4f on %s)",
                    nonce, appellant, bond, rail)
        self._schedule_appeal(nonce)
        return {"appeal": terms, "verification": env}

    @staticmethod
    def _first_instance(row: Any) -> Any:
        """The routed verifier that gave this row's first verdict, or None (the default
        verifier, or no verdict yet)."""
        first = json.loads(row["verdict_json"] or "{}")
        if not first.get("verifier_route"):
            return None
        return vs.VerifierRoute(url=str(first.get("verifier_url") or ""),
                                verifier_id=str(first.get("verifier") or ""),
                                match=str(first["verifier_route"]))

    @staticmethod
    def _refuse_unless_open(row: Any) -> None:
        if row is None:
            raise vs.AppealRefused(404, "verification_not_found", "no such verification")
        status = row["status"]
        if status == vs._PROVISIONAL:
            if vs._now_s() >= float(row["appeal_deadline"] or 0):
                raise vs.AppealRefused(409, "appeal_window_closed", "the appeal window has closed")
            return
        if status in (vs._APPEALED, vs._APPEAL_VERIFYING) or (row["appeal_by"] or ""):
            raise vs.AppealRefused(409, "already_appealed", "this verdict has already been appealed")
        if status in ("pending", "verifying"):
            raise vs.AppealRefused(409, "verdict_pending", "there is no verdict to appeal yet")
        if float(row["appeal_deadline"] or 0) > 0:
            raise vs.AppealRefused(409, "appeal_window_closed",
                                "the appeal window has closed and the verdict is final")
        raise vs.AppealRefused(
            409, "not_appealable",
            "only a genuine pass/fail verdict on a paid settlement, inside its appeal window, "
            "can be appealed (indeterminate and advisory verdicts cannot)",
        )

    @staticmethod
    def _hold_buyer_bond(
        row: Any, receipt_id: str, bond: float, *, channel_secret: str, api_key: str,
    ) -> tuple[str, str]:
        channel_id = row["channel_id"]
        if not channel_secret:
            detail = ("a passed verdict is appealed by the BUYER: present the payment "
                      "channel's secret (X-Payment-Channel-Secret)")
            raise vs.AppealRefused(403 if api_key else 401,
                                "wrong_party" if api_key else "unauthorized", detail)
        problem = channel_secret_error(channel_id, channel_secret)
        if problem:
            raise vs.AppealRefused(401, "unauthorized", problem)
        res = hold_channel(channel_id, bond, receipt_id=receipt_id, secret=channel_secret)
        if res.get("error"):
            if "replay" in res["error"] and hold_state(receipt_id) == "held":
                # Our own bond from an attempt that crashed before claiming the row: the
                # same receipt on the same authenticated channel. Use it, do not re-hold.
                return "channel", channel_id
            status = 402 if "insufficient" in res["error"] else 409
            raise vs.AppealRefused(status, "bond_unavailable",
                                f"the ${bond:.4f} appeal bond could not be held: {res['error']}")
        return "channel", channel_id

    @staticmethod
    def _hold_seller_bond(
        row: Any, receipt_id: str, bond: float, *, channel_secret: str, api_key: str,
    ) -> tuple[str, str]:
        publisher = (row["provider_id"] or "").strip()
        if not api_key:
            detail = ("a failed verdict is appealed by the SELLER: present the X-API-Key of "
                      "the publisher's hub credits account")
            raise vs.AppealRefused(403 if channel_secret else 401,
                                "wrong_party" if channel_secret else "unauthorized", detail)
        ledger = hub_credits.ledger() if hub_credits.enabled() else None
        if ledger is None or not publisher or ledger.account(publisher) is None:
            raise vs.AppealRefused(
                409, "seller_appeal_unavailable",
                "a seller's appeal bond is held on the publisher's hub credits account, and "
                f"publisher {publisher or '(unnamed)'} has none on this hub — a seller paid "
                "on-chain through its payout address cannot be bonded here",
            )
        account = ledger.resolve(api_key)
        if not account:
            raise vs.AppealRefused(401, "unauthorized", "unknown or disabled X-API-Key")
        if account != publisher:
            raise vs.AppealRefused(403, "wrong_party",
                                "only the publisher of the delivery may appeal its failure")
        res = ledger.hold(publisher, bond, receipt_id)
        if res.get("error"):
            existing = ledger.hold_status(receipt_id)
            if existing and existing["status"] == "held" and existing["account_id"] == publisher:
                return "credits", publisher     # own bond from a crashed attempt — see buyer
            status = 402 if "insufficient" in res["error"] else 409
            raise vs.AppealRefused(status, "bond_unavailable",
                                f"the ${bond:.4f} appeal bond could not be held: {res['error']}")
        return "credits", publisher

    # ── Appeals: the second verifier ───────────────────────────────────────

    async def _run_appeal(self, nonce: str, *, reclaim_stale: bool = False) -> None:
        """Hear one appeal: claim it, ask the court (blind), decide, settle.

        The same renewable lease protects startup and periodic recovery: neither may
        steal another process's live hearing. A late answer must still own the token
        to decide the outcome.
        """
        row = self._claim_worker(nonce, vs._APPEALED, vs._APPEAL_VERIFYING)
        if not row:
            return
        async with self._worker_heartbeat(row):
            await self._hear_appeal(row)

    async def _hear_appeal(self, row: Any) -> None:
        nonce = row["nonce"]
        filed = float(row["appeal_filed_at"] or 0) or vs._now_s()
        attempts = int(row["appeal_attempts"] or 0)
        engine_attempts = 0
        backoff = vs.retry_backoff_s()
        reading: _Reading | None = None
        cause = ""
        latency_ms = 0
        while True:
            t0 = time.time()
            async with self._concurrency_gate():
                kind, payload = await self._attempt_appeal(row)
            latency_ms = int((time.time() - t0) * 1000)
            attempts += 1
            with contextlib.suppress(Exception):
                self._db._conn.execute(
                    "UPDATE verified_settlements SET appeal_attempts = ? WHERE nonce = ?",
                    (attempts, nonce),
                )
                self._db._conn.commit()
            if kind == "verdict":
                reading = vs._read_verdict(payload, vs.score_threshold(), label=f"{nonce} (appeal)",
                                        audit_bar=vs.audit_threshold())
                cause = reading.cause
                break
            if kind == "fatal":
                cause = f"appeal_{payload}"
                break
            if kind == "engine":
                engine_attempts += 1
                if engine_attempts > vs.engine_retries():
                    cause = "appeal_engine_error"
                    break
            limit = vs.appeal_max_wait_s()
            if limit > 0 and vs._now_s() - filed > limit:
                cause = "appeal_timed_out"
                break
            await asyncio.sleep(backoff * random.uniform(0.5, 1.5))
            backoff = min(backoff * 2, 300.0)

        decision, record = self._decide_appeal(row, reading, cause, latency_ms)
        if self._transition(
            "UPDATE verified_settlements SET status = ?, final_json = ?, appeal_json = ? "
            "WHERE nonce = ? AND status = ? AND worker_token = ? RETURNING nonce",
            (vs._FINALIZING, json.dumps(decision, ensure_ascii=False),
             json.dumps(record, ensure_ascii=False), nonce, vs._APPEAL_VERIFYING, row["worker_token"]),
        ):
            self._settle_final(nonce)

    def _decide_appeal(
        self, row: Any, reading: _Reading | None, cause: str, latency_ms: int,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """(final outcome, research record) for a heard appeal.

        * the court reached a genuine verdict that AGREES with the first → upheld: the
          first verdict stands and the bond is forfeited;
        * a genuine verdict that DISAGREES → overturned: the court's verdict is final and
          the bond is returned;
        * no genuine verdict (split jury, outage, timeout, unreadable) → indeterminate:
          the first verdict stands and the bond is returned — the appellant is not charged
          for a court that could not decide.
        """
        first = json.loads(row["verdict_json"] or "{}")
        first_verdict = first.get("verdict")
        genuine = reading is not None and reading.genuine
        second = ("passed" if reading.passed else "failed") if genuine else "indeterminate"
        if not genuine:
            outcome = "indeterminate"
        elif second == first_verdict:
            outcome = "upheld"
        else:
            outcome = "overturned"

        if outcome == "overturned":
            delivery = reading.delivery
            passed = reading.passed
            final = {
                "verdict": second,
                "performed": True,
                "verified": passed,
                "verify_score": delivery.score,
                "audit_score": reading.audit_score,
                "trace_id": reading.trace_id,
                "reason": None if passed else "verify_failed_on_appeal",
                "delivery": {"fulfils": delivery.fulfils, "score": delivery.score,
                             "reasons": list(delivery.reasons), "source": delivery.source},
                "verify_latency_ms": latency_ms,
                "verifier": vs.appeal_verifier_id(),
            }
        else:
            final = dict(first)
            if first_verdict == "failed":
                # The refund reason names the appeal it survived — `reason` is bound by the
                # rejection receipt's signature, so the receipt references the appeal.
                final["reason"] = f"verify_failed_appeal_{outcome}"

        env = json.loads(row["envelope_json"] or "{}")
        appeal = dict(env.get("appeal") or {})
        appeal.update(
            status="resolved",
            outcome=outcome,
            overturned=outcome == "overturned",
            first_verdict=first_verdict,
            first_score=first.get("verify_score"),
            first_trace_id=first.get("trace_id"),
            first_verifier=first.get("verifier"),
            appeal_verdict=second,
            appeal_score=reading.delivery.score if genuine else None,
            appeal_audit_score=reading.audit_score if reading is not None else None,
            appeal_trace_id=reading.trace_id if reading is not None else None,
            appeal_cause=None if genuine else (cause or "no_verdict"),
            bond="forfeited" if outcome == "upheld" else "returned",
            resolved_at=vs._now_iso(),
        )
        decision = {
            "verdict": final,
            "appeal": appeal,
            "bond": {
                "rail": row["appeal_rail"],
                "account": row["appeal_account"],
                "receipt_id": APPEAL_BOND_PREFIX + row["nonce"],
                "action": "capture" if outcome == "upheld" else "release",
                "amount_usd": float(row["appeal_bond_usd"] or 0),
            },
            "release_orphan_bond": False,
        }
        record = {
            "by": row["appeal_by"],
            "outcome": outcome,
            "first_verdict": first_verdict,
            "appeal_verdict": second,
            # The research signal: did two independent courts agree? None when the second
            # reached no verdict — an outage is not a disagreement.
            "agree": None if outcome == "indeterminate" else outcome == "upheld",
            "appeal_cause": appeal["appeal_cause"],
            "first_verifier": first.get("verifier"),
            "appeal_verifier": vs.appeal_verifier_id(),
            "resolved_at": appeal["resolved_at"],
        }
        logger.info(
            "verified-settlement %s: appeal by the %s %s (first=%s appeal=%s%s)",
            row["nonce"], row["appeal_by"], outcome, first_verdict, second,
            f" cause={appeal['appeal_cause']}" if appeal["appeal_cause"] else "",
        )
        return decision, record

    def appeal_stats(self) -> dict[str, Any]:
        """Durable #1-vs-#2 agreement, from every resolved appeal on this hub."""
        rows = self._db._conn.execute(
            "SELECT appeal_json FROM verified_settlements WHERE appeal_json <> ''"
        ).fetchall()
        counts = {"upheld": 0, "overturned": 0, "indeterminate": 0}
        by_party: dict[str, dict[str, int]] = {}
        for row in rows:
            try:
                rec = json.loads(row["appeal_json"])
            except ValueError:
                continue
            outcome = rec.get("outcome")
            if outcome not in counts:
                continue
            counts[outcome] += 1
            party = by_party.setdefault(str(rec.get("by") or "unknown"),
                                        {"upheld": 0, "overturned": 0, "indeterminate": 0})
            party[outcome] += 1
        judged = counts["upheld"] + counts["overturned"]
        return {
            "appeals": sum(counts.values()),
            **counts,
            "by_party": by_party,
            # Of the appeals the court actually decided, how often it agreed with the
            # first instance. None until there is one — a rate of nothing is not 0 or 1.
            "agreement_rate": round(counts["upheld"] / judged, 4) if judged else None,
        }


# Imported after the class on purpose: methods read aimarket_hub.verified_settlement at call time
# (where its settings and test patches live), and either module may load first.
from aimarket_hub import verified_settlement as vs  # noqa: E402
