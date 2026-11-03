"""C2 — accept a buyer's DebitAuthorization, or refuse the invoke.

The contract will only debit a channel against a signature from its depositor, so this is
where the hub earns the right to be paid: an invoke that runs without a stored, verified
authorization is work the hub can never collect for on chain.

Every check here answers a question the CONTRACT will ask later, and answers it before the
provider does any billable work — so a mismatch costs a 402, not an unpaid delivery:

    signer      == channels[channelId].depositor   (read from the chain, not claimed)
    hub         == this hub's configured address   (the contract binds it into the digest)
    token       == the channel's token
    amount      == the cents the ledger is about to debit, converted exactly
    receiptId   == the ledger's own receipt nonce for this debit
    nonce       == the channel's CURRENT on-chain nonce
    deadline     in the future, and not absurdly far in it

Refusals raise AuthorizationRejected with a message meant for the buyer's client, because
"your authorization is wrong" is only actionable if it says which field.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from aimarket_hub.escrow_bridge import chain, config, escrow_verify, store
from aimarket_hub.escrow_bridge.eip712 import (
    DebitAuthorization,
    Eip712Error,
    addresses_equal,
    normalize_address,
    recover_signer,
)
from aimarket_hub.escrow_bridge.errors import (
    AuthorizationRejected,
    BridgeConfigError,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AcceptedAuthorization:
    """A verified authorization and the on-chain facts it was checked against."""

    row: store.AuthorizationRow
    escrow_channel: chain.EscrowChannel
    signer: str

    def as_dict(self) -> dict[str, object]:
        return {
            "receipt_id": self.row.receipt_id,
            "escrow_channel": self.row.escrow_channel,
            "nonce": self.row.nonce,
            "amount_units": self.row.amount_units,
            "amount_usd": escrow_verify.base_units_to_usd(self.row.amount_units),
            "deadline": self.row.deadline,
            "signer": self.signer,
            "status": self.row.status,
        }


def _same_bytes32(left: object, right: object) -> bool:
    """Compare two 32-byte hex ids, refusing to guess on anything malformed.

    Not ``addresses_equal``: a channelId is 32 bytes, and a helper that silently accepts a
    20-byte value here would treat a truncated id as a match.
    """
    def canon(value: object) -> str | None:
        text = str(value or "").strip().lower()
        if not text.startswith("0x"):
            return None
        body = text[2:]
        if len(body) != 64:
            return None
        try:
            bytes.fromhex(body)
        except ValueError:
            return None
        return body

    a, b = canon(left), canon(right)
    return a is not None and a == b


def _require_hub_address() -> str:
    hub = config.hub_address()
    if not hub:
        raise BridgeConfigError(
            "AIMARKET_ESCROW_HUB_ADDRESS is not set — the contract binds each "
            "authorization to one hub address, so it cannot be guessed"
        )
    try:
        return normalize_address(hub)
    except Eip712Error as exc:
        raise BridgeConfigError(f"AIMARKET_ESCROW_HUB_ADDRESS is not an address: {exc}") from exc


def parse_authorization(payload: object) -> tuple[DebitAuthorization, str]:
    """Turn a client-supplied blob into (authorization, signature). Raises on nonsense.

    Accepts the field names the SDKs already produce for the contract's typed data
    (``channelId``/``receiptId``), and their snake_case spellings, because the Dart, TS and
    Rust helpers spell them differently and a buyer should not have to care.
    """
    if not isinstance(payload, dict):
        raise AuthorizationRejected("payment authorization must be a JSON object")

    def pick(*names: str) -> object:
        for name in names:
            if name in payload and payload[name] not in (None, ""):
                return payload[name]
        raise AuthorizationRejected(f"payment authorization is missing {names[0]}")

    signature = str(pick("signature", "sig")).strip()
    try:
        auth = DebitAuthorization(
            channel_id=str(pick("channelId", "channel_id")).strip(),
            hub=str(pick("hub")).strip(),
            token=str(pick("token")).strip(),
            amount=int(pick("amount")),
            receipt_id=str(pick("receiptId", "receipt_id")).strip(),
            nonce=int(pick("nonce")),
            deadline=int(pick("deadline")),
        )
    except AuthorizationRejected:
        raise
    except (TypeError, ValueError) as exc:
        raise AuthorizationRejected(f"payment authorization has a malformed field: {exc}") from exc
    return auth, signature


def verify_and_store(
    *,
    payload: object,
    ledger_channel_id: str,
    escrow_channel_id: str,
    expected_amount_usd: float,
    expected_receipt_id: str,
    authorizations: store.AuthorizationStore,
    now: float | None = None,
) -> AcceptedAuthorization:
    """Verify one authorization against the chain and the pending debit, then persist it.

    ``expected_amount_usd`` and ``expected_receipt_id`` come from the hub, never from the
    client: they are what the LEDGER is about to record. Checking the signed values against
    them is what stops a buyer from authorising a cent and being served a dollar's work —
    or from authorising a debit the ledger never makes.
    """
    auth, signature = parse_authorization(payload)
    hub = _require_hub_address()
    clock = int(now if now is not None else time.time())

    # Read the chain first: every subsequent comparison is against what the contract says,
    # and an unreadable chain must not fall back to trusting the payload.
    escrow = chain.escrow_address()
    cid = chain.chain_id()
    ch = chain.read_channel(escrow_channel_id, address=escrow)
    if not ch.exists or not ch.is_open:
        raise AuthorizationRejected(
            "the escrow channel backing this payment channel is not open on chain"
        )
    if int(getattr(ch, "closable_at", 0) or 0):
        # AIMarketEscrowV2: the depositor announced an exit. From closableAt on they can
        # take back the whole balance, whatever the hub served — so it serves no more.
        raise AuthorizationRejected(
            "the depositor asked to close this escrow channel; it takes no new calls"
        )
    if ch.expired(now=clock + config.expiry_margin_s()):
        # Status stays Open after expiresAt until someone calls expireChannel, so status
        # alone would let the hub keep serving calls whose debits can never land.
        raise AuthorizationRejected(
            "the escrow channel expires on chain before this debit could be collected"
        )

    if not _same_bytes32(auth.channel_id, escrow_channel_id):
        # The signature covers channelId; a mismatch means the buyer signed for a
        # different channel than the one being debited.
        raise AuthorizationRejected(
            "authorization channelId does not match the escrow channel behind this invoke"
        )
    if not addresses_equal(auth.hub, hub):
        raise AuthorizationRejected(
            "authorization is bound to a different hub address and this hub could never "
            "submit it"
        )
    if not addresses_equal(auth.token, ch.token):
        raise AuthorizationRejected("authorization token does not match the escrow channel")

    # CUMULATIVE, not per call. `debitChannel` signs over the channel's CURRENT `ch.nonce`
    # read from storage and does `ch.nonce += 1` only when a debit lands, so the nonce does
    # not move between on-chain debits: every invoke served in that window signs the SAME
    # nonce and the contract accepts exactly ONE of those signatures.
    #
    # With a per-call amount that made every invoke but one structurally uncollectable, and
    # the bridge's answer was to abandon the earlier row and keep the newest. The
    # production hub's escrow_bridge.db shows what that cost: 86 abandoned authorizations
    # against 27 confirmed, 79 of them reading "replaced by fresh buyer authorization for
    # the same on-chain nonce" — $5.05 delivered and never collected, 76% of everything
    # the rail ever captured, none of it ever even attempted (attempts=0 on all 86).
    #
    # So the authorization at a nonce carries the running total for its window, which is
    # the invariant every payment channel uses. One debit at nonce N then collects the
    # whole window, and superseding the earlier row loses nothing because the later one
    # covers it. A window closes when a debit confirms and the nonce advances.
    live = authorizations.active_at(escrow_channel_id, int(auth.nonce))
    if live is not None and live.status not in (store.PENDING, store.PLANNED):
        # SUBMITTED may still confirm; it may not be superseded, and this invoke must not
        # be asked to carry money that is already on its way to the chain.
        live = None
    if live is not None and str(live.receipt_id).lower() == str(auth.receipt_id).lower():
        # The same receipt arriving twice is a replay of ONE call, not a second one. It
        # owes nothing extra; the replay check below is what answers it.
        live = None
    carried_units = int(live.amount_units) if live is not None else 0
    call_units = escrow_verify.usd_to_base_units(expected_amount_usd)
    expected_units = call_units + carried_units
    cap_usd = config.max_uncollected_usd()
    if carried_units and cap_usd and expected_units > escrow_verify.usd_to_base_units(cap_usd):
        # Until a debit lands, the depositor can settle or refund the channel and take back
        # everything served in this window; the hub stops serving on credit past the cap.
        raise AuthorizationRejected(
            f"escrow channel {escrow_channel_id} already carries {carried_units} uncollected "
            f"base units at nonce {auth.nonce}; serving this call would put "
            f"{expected_units} on credit, over the hub's {cap_usd:.2f} USD limit — retry "
            "once the pending debit lands"
        )
    if int(auth.amount) != expected_units:
        if carried_units:
            raise AuthorizationRejected(
                f"authorization amount {auth.amount} does not match the {expected_units} "
                f"base units this invoke debits: the escrow channel's on-chain nonce "
                f"{auth.nonce} still carries {carried_units} uncollected base units from "
                f"earlier calls, and the contract debits a nonce once, so this signature "
                f"must authorize the running total ({carried_units} + {call_units})"
            )
        raise AuthorizationRejected(
            f"authorization amount {auth.amount} does not match the {expected_units} base "
            "units this invoke debits"
        )
    if auth.amount > ch.balance:
        raise AuthorizationRejected(
            "authorization amount exceeds the escrow channel's remaining on-chain balance"
        )
    if str(auth.receipt_id).lower() != str(expected_receipt_id).lower():
        raise AuthorizationRejected(
            "authorization receiptId does not match this invoke's receipt"
        )
    if int(auth.nonce) != int(ch.nonce):
        # The contract accepts only the channel's CURRENT nonce. A stale nonce is a replay
        # of an older authorization; a future one would sit unsubmittable behind a gap.
        raise AuthorizationRejected(
            f"authorization nonce {auth.nonce} is not the channel's current on-chain "
            f"nonce {ch.nonce}"
        )
    if int(auth.deadline) <= clock:
        raise AuthorizationRejected("authorization deadline has already passed")
    min_ttl = config.min_authorization_ttl_s()
    if int(auth.deadline) - clock < min_ttl:
        # The contract refuses a debit after its deadline; one that expires before the next
        # sweeps can submit it is a call served for nothing.
        raise AuthorizationRejected(
            f"authorization deadline must be at least {min_ttl}s ahead so the hub can "
            "collect it before it expires"
        )
    max_ttl = config.max_authorization_ttl_s()
    if int(auth.deadline) - clock > max_ttl:
        # A deadline is the buyer's cap on how long the hub may hold a claim on their
        # money; an unbounded one turns a single signature into a standing licence.
        raise AuthorizationRejected(
            f"authorization deadline is more than {max_ttl}s in the future"
        )

    signer = recover_signer(auth, signature, chain_id=cid, verifying_contract=escrow)
    if not signer:
        raise AuthorizationRejected("payment authorization signature could not be recovered")
    if not addresses_equal(signer, ch.depositor):
        raise AuthorizationRejected(
            "payment authorization was not signed by the escrow channel's depositor"
        )

    try:
        row = authorizations.record(
            receipt_id=auth.receipt_id,
            ledger_channel=ledger_channel_id,
            escrow_channel=escrow_channel_id,
            chain_id=cid,
            escrow_address=escrow,
            hub=hub,
            token=normalize_address(ch.token),
            depositor=normalize_address(ch.depositor),
            amount_units=int(auth.amount),
            nonce=int(auth.nonce),
            deadline=int(auth.deadline),
            signature=signature,
        )
    except store.StoreError as exc:
        # Same (escrow channel, nonce) may already be pending from a prior invoke that
        # stored the auth then failed later, OR whose receipt was already ledger-spent.
        # Prefer a fresh signature: abandon the orphan row (partial unique index allows
        # a new insert) instead of reusing a receipt the ledger will reject as replay.
        msg = str(exc)
        if "at nonce" in msg and "already stored" in msg:
            # `active_at`, not `get_by_channel_nonce`: the latter returns the newest row of
            # ANY status and ties on created_at, so once a window has an abandoned row in
            # it the third call could read that one, see a terminal status, and refuse a
            # perfectly good cumulative authorization.
            existing = authorizations.active_at(escrow_channel_id, int(auth.nonce))
            # Only ever supersede a claim the incoming authorization provably COVERS. The
            # amount check above already guarantees it — this is the second lock on the
            # door, because the thing on the other side of it is money already earned.
            if (
                existing is not None
                and existing.status in (store.PENDING, store.PLANNED)
                and int(auth.amount) >= int(existing.amount_units)
            ):
                try:
                    authorizations.abandon(existing.receipt_id, store.SUPERSEDED_REASON)
                except store.StoreError:
                    pass
                try:
                    row = authorizations.record(
                        receipt_id=auth.receipt_id,
                        ledger_channel=ledger_channel_id,
                        escrow_channel=escrow_channel_id,
                        chain_id=cid,
                        escrow_address=escrow,
                        hub=hub,
                        token=normalize_address(ch.token),
                        depositor=normalize_address(ch.depositor),
                        amount_units=int(auth.amount),
                        nonce=int(auth.nonce),
                        deadline=int(auth.deadline),
                        signature=signature,
                    )
                except store.StoreError as retry_exc:
                    raise AuthorizationRejected(str(retry_exc)) from retry_exc
                logger.info(
                    "escrow bridge: replaced orphan authorization with %s for escrow "
                    "channel %s nonce %d (%d units)",
                    row.receipt_id[:14],
                    escrow_channel_id[:14],
                    row.nonce,
                    row.amount_units,
                )
                return AcceptedAuthorization(
                    row=row, escrow_channel=ch, signer=normalize_address(signer)
                )
        raise AuthorizationRejected(msg) from exc

    logger.info(
        "escrow bridge: stored authorization %s for escrow channel %s nonce %d (%d units)",
        row.receipt_id[:14], escrow_channel_id[:14], row.nonce, row.amount_units,
    )
    return AcceptedAuthorization(row=row, escrow_channel=ch, signer=normalize_address(signer))


def withdraw(receipt_id: str, authorizations: store.AuthorizationStore, *, reason: str) -> None:
    """A stored call was not served (or not charged): take its authorization back.

    Its row is the running total of its nonce window, so abandoning it alone would leave
    the calls before it with no claim at all; the authorization it replaced becomes the
    window's claim again. Best effort and idempotent.
    """
    row = authorizations.get(receipt_id)
    if row is None or row.status not in (store.PENDING, store.PLANNED):
        return
    authorizations.abandon(receipt_id, str(reason)[:300])
    revived = authorizations.revive_superseded(row.escrow_channel, row.nonce)
    if revived is not None:
        logger.info(
            "escrow bridge: %s withdrawn (%s); %s is the claim of channel %s nonce %d again",
            receipt_id[:14], reason, revived.receipt_id[:14], row.escrow_channel[:14], row.nonce,
        )
