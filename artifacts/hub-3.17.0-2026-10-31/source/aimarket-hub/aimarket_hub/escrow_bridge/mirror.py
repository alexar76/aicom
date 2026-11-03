"""C3 — the reconciler that turns stored authorizations into on-chain debits.

This is what actually closes audit finding #9: without it ``usedAmount`` stays 0 forever
and a depositor can reclaim a fully consumed deposit. Everything here is a background /
operator action, never part of a request: an invoke records an authorization and returns,
and the mirror catches up afterwards.

Order is the load-bearing property. The escrow accepts a debit only at the channel's
CURRENT nonce, so authorizations must go out strictly in ascending nonce per channel. A gap
therefore BLOCKS rather than skips — skipping would leave a permanently unsubmittable row
behind, i.e. money the hub can never collect.

Four guards sit in front of every submission, in this order, because each is cheaper than
the next and each can only refuse:

    0. the chain's replay flag      — has this receipt already been collected, by anyone?
    1. the store's queue position   — is this the next nonce for its channel?
    2. the LEDGER                   — did the hub actually debit this receipt, for this much?
    3. the chain                    — would the contract accept it right now? (simulation)

Guard 0 is first for two reasons, both learned the hard way in production on 2026-07-29.
A receipt the operator collected by hand leaves the row unresolved forever, and since
submission is strictly nonce-ordered that one row blocks every later row on its channel —
so it must resolve before the queue guard can refuse it. And it must resolve before the
DEADLINE guard, or a debit that was collected on time gets recorded as money the hub can
never collect, which is the opposite of the truth.

Guard 2 matters more than it looks: the store holds what the BUYER signed, and the ledger
holds what the hub actually charged. Submitting the signed amount without checking would
let a hub bug (or a tampered store) collect more on chain than it billed off chain.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any

from aimarket_hub.escrow_bridge import chain, config, escrow_verify, signer as signer_mod, store
from aimarket_hub.escrow_bridge.eip712 import DebitAuthorization
from aimarket_hub.escrow_bridge.errors import (
    BridgeDisabled,
    SubmissionRefused,
)

logger = logging.getLogger(__name__)

# Outcomes reported per row. "blocked" and "refused" are not failures of the row — they
# describe the state of the world around it — so they never move it in the store.
OUTCOME_PLANNED = "planned"
OUTCOME_SUBMITTED = "submitted"
OUTCOME_CONFIRMED = "confirmed"
OUTCOME_BLOCKED = "blocked"
OUTCOME_REFUSED = "refused"
OUTCOME_REJECTED = "rejected"


@dataclass
class MirrorReport:
    """What one pass did, in a shape an operator can read without a database client."""

    dry_run: bool
    strategy: str
    scanned: int = 0
    outcomes: dict[str, int] = field(default_factory=dict)
    rows: list[dict[str, Any]] = field(default_factory=list)

    def note(self, receipt_id: str, outcome: str, detail: str = "", **extra: Any) -> None:
        self.outcomes[outcome] = self.outcomes.get(outcome, 0) + 1
        self.rows.append(
            {"receipt_id": receipt_id, "outcome": outcome, "detail": detail, **extra}
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "dry_run": self.dry_run,
            "strategy": self.strategy,
            "scanned": self.scanned,
            "outcomes": dict(self.outcomes),
            "rows": self.rows,
        }


def _ledger_debited_cents(receipt_id: str) -> int | None:
    """Cents the CHANNEL LEDGER recorded for this receipt, or None if it has no record.

    Read through the ledger's OWN backend rather than by opening its file. ``ChannelLedger``
    routes via ``db_backend.create_backend(database_url=…, db_path=…)`` and so runs on either
    SQLite or PostgreSQL; this function used to hardcode ``sqlite3.connect`` on
    ``channels._DB_PATH``. On a Postgres hub that read finds no table, returns None, and
    None means "refuse to submit" — so guard 2 would have blocked *every* debit and the
    bridge would have collected nothing at all, silently and forever. Fail-closed, but
    uselessly so, and nothing would have said why.

    Still a private read rather than a new accessor on ``channels``: the bridge is optional
    and must not widen that module's public surface. Any failure returns None, because an
    unverifiable charge is not a charge worth collecting.
    """
    try:
        from aimarket_hub import channels as ch_mod
        from aimarket_hub.db_backend import create_backend

        path = getattr(ch_mod, "_DB_PATH", "")
        url = os.getenv("DATABASE_URL", "").strip()
        if not path and not url:
            return None
        backend = create_backend(database_url=url, db_path=path or None)
        try:
            backend.execute(
                "SELECT amount_cents FROM debited_receipts WHERE receipt_id = ?",
                (receipt_id,),
            )
            row = backend.fetchone()
        finally:
            backend.close()
    except Exception as exc:
        logger.warning("could not read the ledger debit for %s: %s", receipt_id[:14], exc)
        return None
    return int(row["amount_cents"]) if row else None


class Mirror:
    """One pass over the unresolved authorizations."""

    def __init__(
        self,
        *,
        authorizations: store.AuthorizationStore | None = None,
        signer: signer_mod.Signer | None = None,
        require_enabled: bool = True,
    ):
        if require_enabled and not config.enabled():
            raise BridgeDisabled(
                "the escrow bridge is disabled (AIMARKET_ESCROW_BRIDGE_ENABLED=0) — "
                "nothing to mirror"
            )
        self.store = authorizations or store.AuthorizationStore()
        self.signer = signer or signer_mod.build_signer()
        self._dry_run = isinstance(self.signer, signer_mod.PlanOnlySigner)
        # Spend budget for one pass. Reset by run(); see _budget_blocks.
        self._pass_units = 0

    # ── spend bounds ─────────────────────────────────────────────────────────

    def _budget_blocks(self, row: store.AuthorizationRow, *, now: float) -> str | None:
        """Reason this row exceeds a configured spend ceiling, or None to proceed.

        KI-11 asked for a hot wallet with a BOUNDED balance and there was no bound of any
        kind: one pass would submit every unresolved authorization it could reach. A ledger
        bug, a tampered store, or simply a long unattended backlog therefore all had the
        same unlimited blast radius.

        Two ceilings, because one alone does not hold. A per-pass cap is defeated by running
        passes back to back — which is exactly what an unattended timer does — so the daily
        cap is measured from the store's own record of what this hub broadcast, and survives
        a restart. Neither stops an attacker holding the key; both stop the hub from acting
        on a mistake at full speed, which is the failure actually worth bounding.

        Only consulted for real submissions: planning moves nothing.
        """
        per_pass = config.max_usd_per_pass()
        per_day = config.max_usd_per_day()
        row_usd = escrow_verify.base_units_to_usd(row.amount_units)

        if per_pass:
            pass_usd = escrow_verify.base_units_to_usd(self._pass_units + row.amount_units)
            if pass_usd > per_pass:
                # "Nothing further is sent this pass" was wrong: the loop keeps going, and a
                # CHEAPER row further down can still fit under the ceiling. Saying the pass is
                # over when it is not sends an operator looking for a stalled queue that is
                # actually still working. Rows behind this one ON THE SAME CHANNEL are stranded
                # anyway — the nonce guard requires strict order — but other channels proceed.
                return (
                    f"this row would take the pass to ${pass_usd:.4f}, over the "
                    f"${per_pass:.2f} per-pass ceiling "
                    f"(AIMARKET_ESCROW_MAX_USD_PER_PASS). It is skipped; the pass continues "
                    f"with rows that still fit, and this channel resumes next pass"
                )
        if per_day:
            # Wall clock, deliberately NOT the caller's `now`. The store stamps
            # `submitted_at` with real time, so a window measured from an injected clock
            # compares two different scales and silently mis-sizes the budget. `now` stays
            # for the deadline logic, which is denominated in the same units the buyer signed.
            spent_units = self.store.units_collected_since(time.time() - 86_400)
            day_usd = escrow_verify.base_units_to_usd(spent_units + row.amount_units)
            if day_usd > per_day:
                return (
                    f"the last 24h already collected "
                    f"${escrow_verify.base_units_to_usd(spent_units):.4f}; adding "
                    f"${row_usd:.4f} would pass the ${per_day:.2f} daily ceiling "
                    f"(AIMARKET_ESCROW_MAX_USD_PER_DAY)"
                )
        return None

    # ── one row ──────────────────────────────────────────────────────────────

    def _authorization_of(self, row: store.AuthorizationRow) -> DebitAuthorization:
        return DebitAuthorization(
            channel_id=row.escrow_channel, hub=row.hub, token=row.token,
            amount=row.amount_units, receipt_id=row.receipt_id, nonce=row.nonce,
            deadline=row.deadline,
        )

    def _preflight(self, row: store.AuthorizationRow, report: MirrorReport, *, now: float) -> bool:
        """Guards 0, 1 and 2. Returns False (and records why) if the row must not go out."""
        # Guard 0 — already collected? Resolve rather than block. See the module docstring
        # for why this precedes both the queue guard and the deadline guard.
        try:
            already = chain.receipt_already_used(row.receipt_id, address=row.escrow_address,
                                                 channel_id=row.escrow_channel)
        except Exception as exc:  # ChainUnavailable and anything the pool surfaces
            # Cannot read the flag → cannot know. Refuse rather than send a debit that the
            # contract may already have collected; a later pass will retry.
            report.note(
                row.receipt_id, OUTCOME_BLOCKED,
                f"cannot read the contract's replay flag, so cannot tell whether this "
                f"receipt was already collected: {exc}",
                nonce=row.nonce,
            )
            return False
        if already:
            self.store.mark_collected_externally(row.receipt_id)
            report.note(
                row.receipt_id, OUTCOME_CONFIRMED,
                "the contract already counts this receipt as used — collected by a debit "
                "the hub did not send. Resolved; nothing further is owed on it",
                nonce=row.nonce,
                amount_usd=escrow_verify.base_units_to_usd(row.amount_units),
            )
            return False

        nxt = self.store.next_for_channel(row.escrow_channel)
        if nxt is not None and nxt.receipt_id != row.receipt_id:
            report.note(
                row.receipt_id, OUTCOME_BLOCKED,
                f"waiting behind nonce {nxt.nonce}; the contract only accepts the "
                "channel's current nonce",
                nonce=row.nonce,
            )
            return False

        if row.expired(now=now):
            # The signature can never be submitted again, so the money is uncollectable.
            # Recording that plainly is more useful than retrying it forever.
            self.store.abandon(row.receipt_id, "authorization deadline passed before submission")
            report.note(
                row.receipt_id, OUTCOME_REJECTED,
                "deadline passed before submission — this debit can no longer be collected "
                "on chain",
                nonce=row.nonce,
            )
            return False

        recorded = _ledger_debited_cents(row.receipt_id)
        if recorded is not None:
            # A window's authorization is its running total, and the ledger records each
            # call under its own receipt: the calls it replaced back the rest of the total.
            for prior in self.store.superseded_in_window(row.escrow_channel, row.nonce):
                recorded += _ledger_debited_cents(prior.receipt_id) or 0
        if recorded is None:
            report.note(
                row.receipt_id, OUTCOME_BLOCKED,
                "the channel ledger has no debit for this receipt — refusing to collect a "
                "charge the hub cannot show it made",
                nonce=row.nonce,
            )
            return False
        allowed_units = recorded * (10 ** (escrow_verify.TOKEN_DECIMALS - 2))
        if row.amount_units > allowed_units:
            report.note(
                row.receipt_id, OUTCOME_BLOCKED,
                f"authorization is for {row.amount_units} units but the ledger only "
                f"debited {allowed_units} — refusing to over-collect",
                nonce=row.nonce,
            )
            return False
        return True

    def process(self, row: store.AuthorizationRow, report: MirrorReport, *, now: float) -> None:
        """Plan, and submit if the policy allows. Never raises for a normal refusal."""
        if not self._preflight(row, report, now=now):
            return

        auth = self._authorization_of(row)
        data = chain.encode_debit_channel(auth, row.signature)
        sender = self.signer.sender or row.hub
        plan = chain.simulate(to=row.escrow_address, data=data, sender=sender)
        # Recorded whatever the answer: a revert here is the most useful diagnostic the
        # bridge produces, and plan mode exists to collect exactly this.
        self.store.record_plan(row.receipt_id, {**plan, "sender": sender})
        if not plan.get("ok"):
            report.note(
                row.receipt_id, OUTCOME_BLOCKED,
                f"simulation says the contract would reject it: {plan.get('error', '')}",
                nonce=row.nonce,
            )
            return

        if self._dry_run:
            report.note(
                row.receipt_id, OUTCOME_PLANNED,
                "would be accepted; not sent (plan mode)",
                nonce=row.nonce, gas=plan.get("gas"),
                amount_usd=escrow_verify.base_units_to_usd(row.amount_units),
            )
            return

        blocked = self._budget_blocks(row, now=now)
        if blocked is not None:
            report.note(row.receipt_id, OUTCOME_BLOCKED, blocked, nonce=row.nonce,
                        amount_usd=escrow_verify.base_units_to_usd(row.amount_units))
            return

        gas = int(plan.get("gas") or 0)
        tx = signer_mod.UnsignedTx(
            to=row.escrow_address, data=data, chain_id=row.chain_id,
            # A simulated estimate is a floor, not a promise: state can shift between the
            # estimate and inclusion, and an under-funded gas limit reverts the debit.
            gas=int(gas * 1.25) if gas else 250_000,
        )
        try:
            tx_hash = self.signer.submit(tx)
        except SubmissionRefused as exc:
            report.note(row.receipt_id, OUTCOME_REFUSED, str(exc), nonce=row.nonce)
            return
        self.store.mark_submitted(row.receipt_id, tx_hash)
        # Counted only after a successful broadcast: a refused submission spends nothing,
        # and charging it to the budget would throttle the pass for work it never did.
        self._pass_units += row.amount_units
        report.note(
            row.receipt_id, OUTCOME_SUBMITTED, "broadcast; awaiting a receipt",
            nonce=row.nonce, tx_hash=tx_hash,
            amount_usd=escrow_verify.base_units_to_usd(row.amount_units),
        )

    # ── passes ───────────────────────────────────────────────────────────────

    def run(self, *, limit: int = 200, now: float | None = None) -> MirrorReport:
        """Plan (and possibly submit) every unresolved authorization, in nonce order."""
        clock = time.time() if now is None else now
        self._pass_units = 0
        report = MirrorReport(dry_run=self._dry_run, strategy=self.signer.name)
        rows = self.store.unresolved(limit=limit)
        report.scanned = len(rows)
        for row in rows:
            if row.status == store.SUBMITTED:
                # Already broadcast — the confirm pass owns it, and re-submitting would
                # only spend gas to hit the contract's own usedReceipts guard.
                continue
            try:
                self.process(row, report, now=clock)
            except Exception as exc:  # one bad row must not stall the queue
                logger.warning("mirror: %s failed: %s", row.receipt_id[:14], exc)
                report.note(row.receipt_id, OUTCOME_BLOCKED, f"{type(exc).__name__}: {exc}")
        return report

    def confirm(self, *, limit: int = 200) -> MirrorReport:
        """Resolve broadcast rows by READING the chain, never by trusting the signer.

        A signer (or a node) that claims success proves nothing; a receipt does. A reverted
        receipt is left non-terminal on purpose: the usual cause is a nonce the chain moved
        past, and the next pass re-simulates against current state instead of abandoning a
        buyer's still-valid signature.
        """
        report = MirrorReport(dry_run=self._dry_run, strategy=self.signer.name)
        rows = [r for r in self.store.unresolved(limit=limit) if r.status == store.SUBMITTED]
        report.scanned = len(rows)
        for row in rows:
            if not row.tx_hash:
                report.note(row.receipt_id, OUTCOME_BLOCKED, "submitted without a tx hash")
                continue
            try:
                receipt = chain._pool().call("eth_getTransactionReceipt", [row.tx_hash])
            except Exception as exc:
                report.note(row.receipt_id, OUTCOME_BLOCKED, f"receipt unreadable: {exc}")
                continue
            if not receipt:
                report.note(row.receipt_id, OUTCOME_BLOCKED, "not mined yet")
                continue
            status = str((receipt or {}).get("status", "")).lower()
            if status in ("0x1", "1"):
                self.store.mark_confirmed(row.receipt_id, row.tx_hash)
                report.note(
                    row.receipt_id, OUTCOME_CONFIRMED, "the contract recorded the debit",
                    tx_hash=row.tx_hash,
                    amount_usd=escrow_verify.base_units_to_usd(row.amount_units),
                )
            else:
                self.store.record_plan(
                    row.receipt_id,
                    {"ok": False, "error": f"transaction reverted on chain (status {status})"},
                )
                report.note(
                    row.receipt_id, OUTCOME_BLOCKED,
                    "the transaction reverted; it will be re-simulated against current state",
                    tx_hash=row.tx_hash,
                )
        return report

    def status(self) -> dict[str, Any]:
        """Operator snapshot: configuration, queue, and what is still owed on chain."""
        return {
            "config": config.describe(),
            "signer": self.signer.name,
            "dry_run": self._dry_run,
            "store": self.store.stats(),
        }
