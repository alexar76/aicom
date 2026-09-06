"""Pre-funded payment channels (off-chain ledger, on-chain settle)."""

from __future__ import annotations

import fcntl
import hashlib
import hmac
import json
import logging
import math
import os
import secrets
import threading
import time
import uuid
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

from core.uni.config import uni_enabled
from core.uni.pricing import uni_to_usd, usd_to_uni
from web.backend.services.ai_market_protocol.config import demo_payment_bypass, pilot_tuple
from web.backend.services.ai_market_protocol.on_chain import (
    BIND_SENDER,
    DEPOSIT_STACK_WEB_V1,
    canonical_proof_payer,
    channel_open_proof_message,
    claim_deposit,
    is_demo_tx,
    is_evm_chain,
    normalize_tx_hash,
    recover_channel_open_payer,
    release_deposit_claim,
    require_payer_proof,
    verify_refund_transfer,
    verify_tx_transfer,
)
from web.backend.services.ai_market_protocol.paths import channels_path
from web.backend.services.ai_market_protocol.signing import sign_payload
from web.backend.services.commerce import CommerceService

if TYPE_CHECKING:
    from pathlib import Path

_commerce = CommerceService()

logger = logging.getLogger(__name__)

# In-process serialization of the channel store. Combined with an OS file lock
# (flock) below, this makes load→modify→save atomic across threads AND processes
# (FastAPI runs sync handlers in a threadpool; deployments run multiple workers).
# Without it two concurrent deduct_channel() calls double-spend a channel balance.
_STORE_LOCK = threading.RLock()

# flock() is per open-file-description, so a nested channel_store_lock() in the
# same thread would deadlock against its own outer lock (the RLock lets the
# thread through, then the second open()+LOCK_EX blocks forever). Track depth and
# only take the OS lock at the outermost level.
_LOCK_DEPTH = threading.local()

# All channel arithmetic goes through integer cents. Floats accumulate drift over
# a long ledger (0.35 * 100 == 34.999999999999996), which is how a channel ends
# up a fraction of a cent away from deposit == balance + spent.
_CENTS_PER_USD = 100

def deposit_proof_challenge(
    *, chain: str, tx_hash: str, payer: str, deposit_usd: float
) -> str:
    """The exact text a depositor signs to claim a channel deposit here.

    Thin re-export of the CANONICAL challenge (on_chain.channel_open_proof_message)
    so this package and aimarket-hub cannot drift into two incompatible schemes
    again — one signature is valid at both doors. Exposed by name because clients
    and tests need to build the message without reaching into on_chain directly.
    """
    return channel_open_proof_message(
        chain=chain, tx_hash=tx_hash, payer=payer, amount_usd=deposit_usd
    )


def _hash_secret(secret: str) -> str:
    return hashlib.sha256((secret or "").encode()).hexdigest()


def _to_cents(usd: Any) -> int:
    try:
        value = float(usd or 0)
    except (TypeError, ValueError):
        return 0
    if not math.isfinite(value):
        return 0
    return int(round(value * _CENTS_PER_USD))


def _bill_cents(usd: float) -> int:
    """Cents to DEBIT for a positively-priced call.

    Rounds UP so a sub-cent price (a $0.004 capability) still bills 1 cent rather
    than debiting nothing and serving a paid invoke for free. ``round(.., 6)``
    first strips binary-float noise so exact-cent prices are not pushed up a cent.
    """
    if usd <= 0:
        return 0
    return max(1, math.ceil(round(float(usd) * _CENTS_PER_USD, 6)))


def _from_cents(cents: int) -> float:
    return round(cents / _CENTS_PER_USD, 4)


@contextmanager
def channel_store_lock():
    """Hold an exclusive process- and cross-process lock on the channel store.

    Wrap every read-modify-write sequence in this so balance checks and writes
    are atomic. Network/on-chain verification should happen *outside* the lock.
    Re-entrant: a nested use inside the same thread reuses the held OS lock.
    """
    depth = getattr(_LOCK_DEPTH, "value", 0)
    if depth:
        _LOCK_DEPTH.value = depth + 1
        try:
            yield
        finally:
            _LOCK_DEPTH.value = depth
        return

    p = channels_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    lock_path = p.parent / (p.name + ".lock")
    with _STORE_LOCK:
        with open(lock_path, "a+") as lock_f:
            fcntl.flock(lock_f, fcntl.LOCK_EX)
            _LOCK_DEPTH.value = 1
            try:
                yield
            finally:
                _LOCK_DEPTH.value = 0
                fcntl.flock(lock_f, fcntl.LOCK_UN)


def _load_json_store(p: Path, label: str) -> dict[str, Any]:
    if not p.exists():
        return {}
    raw = p.read_text(encoding="utf-8")
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        # Never silently return {} for a corrupt-but-present store: a subsequent
        # save would wipe every channel (and every real balance). Abort instead.
        logger.error("%s store at %s is corrupt: %s", label, p, e)
        raise RuntimeError(f"{label} store is corrupt; refusing to overwrite") from e
    return data if isinstance(data, dict) else {}


def _save_json_store(p: Path, data: dict[str, Any]) -> None:
    # Atomic write: a crash mid-write can't truncate/corrupt the live store.
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.parent / (p.name + f".tmp-{os.getpid()}-{threading.get_ident()}")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, p)


def _load_channels() -> dict[str, Any]:
    return _load_json_store(channels_path(), "channel")


def _save_channels(data: dict[str, Any]) -> None:
    _save_json_store(channels_path(), data)


# ── Single-use registry for one-off on-chain payments ────────────────────────
# Channel deposits are de-duplicated through the channel records themselves, but
# the pay-per-call invoke path had no record at all: one $0.40 transfer could pay
# for unlimited invokes, and a mempool watcher could replay a stranger's hash.
# This registry gives those payments the same one-hash-one-payment guarantee, in
# the same lock order as the channel store (so no second lock, no deadlock).

def payment_tx_path() -> Path:
    return channels_path().parent / "payment_txs.json"


def _load_tx_claims() -> dict[str, Any]:
    return _load_json_store(payment_tx_path(), "payment-tx")


def payment_tx_claim(tx_hash: str) -> dict[str, Any] | None:
    """The existing claim on ``tx_hash``, if this hash was already spent."""
    return _load_tx_claims().get((tx_hash or "").strip())


def claim_payment_tx(
    *,
    tx_hash: str,
    chain: str,
    token: str,
    amount_usd: float,
    purpose: str,
    sender: str = "",
    claimant: str = "",
) -> dict[str, Any]:
    """Atomically mark ``tx_hash`` as spent, or refuse because it already is.

    Fails closed on reuse: the caller must not deliver value when ``ok`` is False.
    Dev placeholder hashes are not registered (they intentionally have no chain
    behind them and are reused freely in local flows).
    """
    tx = (tx_hash or "").strip()
    if not tx:
        return {"ok": False, "error": "tx_hash_required"}
    if is_demo_tx(tx):
        return {"ok": True, "demo": True, "claim": None}
    with channel_store_lock():
        claims = _load_tx_claims()
        existing = claims.get(tx)
        if existing:
            return {"ok": False, "error": "tx_hash_already_used", "claim": existing}
        if _tx_hash_already_used(tx):
            return {"ok": False, "error": "tx_hash_already_used"}
        claim = {
            "tx_hash": tx,
            "chain": (chain or "").strip().lower(),
            "token": (token or "").strip().upper(),
            "amount_usd": round(float(amount_usd or 0), 4),
            "purpose": purpose,
            "sender": (sender or "").strip(),
            "claimant": (claimant or "").strip(),
            "claimed_at": time.time(),
        }
        claims[tx] = claim
        _save_json_store(payment_tx_path(), claims)
        return {"ok": True, "claim": claim}


def mark_payment_tx_unfulfilled(*, tx_hash: str, reason: str) -> dict[str, Any]:
    """Flag a consumed one-off payment whose delivery failed.

    The transfer has to stay consumed (otherwise the same hash buys unlimited
    retries), so a failed execution leaves the platform holding money it did not
    earn. Record that as an explicit obligation rather than letting the claim look
    like a fulfilled sale — paying it back is an operator action, this code never
    moves funds.
    """
    tx = (tx_hash or "").strip()
    if not tx or is_demo_tx(tx):
        return {"ok": False, "error": "no_claim"}
    with channel_store_lock():
        claims = _load_tx_claims()
        claim = claims.get(tx)
        if not claim:
            return {"ok": False, "error": "no_claim"}
        claim["fulfilled"] = False
        claim["obligation_reason"] = reason
        claim["obligation_recorded_at"] = time.time()
        claims[tx] = claim
        _save_json_store(payment_tx_path(), claims)
    logger.warning(
        "on-chain payment %s (%s USD) delivered nothing (%s) — refund obligation to %s",
        tx[:14],
        claim.get("amount_usd"),
        reason,
        claim.get("sender") or "an unknown wallet",
    )
    return {"ok": True, "claim": claim}


def list_unfulfilled_payments() -> list[dict[str, Any]]:
    """One-off on-chain payments that were consumed without delivering value."""
    out = [c for c in _load_tx_claims().values() if c.get("fulfilled") is False]
    out.sort(key=lambda c: c.get("obligation_recorded_at") or 0)
    return out


def _tx_hash_already_used(tx_clean: str) -> bool:
    if not tx_clean or is_demo_tx(tx_clean):
        return False
    if _commerce.get_order_by_tx_hash(tx_clean):
        return True
    if tx_clean in _load_tx_claims():
        return True
    for ch in _load_channels().values():
        if ch.get("open_tx_hash") == tx_clean:
            return True
        if ch.get("settle_tx_hash") == tx_clean:
            return True
    return False


def open_channel(
    *,
    deposit_usd: float,
    token: str | None = None,
    chain: str | None = None,
    wallet: str = "",
    tx_hash: str = "",
    customer_id: str = "",
    customer_email: str = "",
    signature: str = "",
) -> dict[str, Any]:
    """Open a pre-funded channel against a verified on-chain deposit.

    The credited channel is bound to the wallet that ACTUALLY paid: the deposit is
    verified with ``BIND_SENDER``, the on-chain sender becomes the channel's
    ``deposit_wallet`` (and therefore the refund destination), and a caller-declared
    ``wallet`` must match it. ``signature`` is an EIP-191 proof over the CANONICAL
    channel-open challenge (:func:`deposit_proof_challenge`, shared byte-for-byte
    with aimarket-hub) binding the paying wallet to this tx and amount — required
    whenever :func:`require_payer_proof` says so (production), because without it
    a mempool watcher can still submit a stranger's hash and get the balance. The
    refusal carries the exact `challenge` text so a client never has to guess it.
    """
    from core.crypto_config import crypto_enabled

    # Payment channels are an external-crypto feature (on-chain funded deposits).
    # With crypto OFF (default) they are disabled — invokes settle via UNI instead.
    if not crypto_enabled():
        return {"error": "crypto_disabled", "detail": "payment channels disabled (AIFACTORY_CRYPTO_ENABLED=0) — invokes settle via UNI"}
    cfg = pilot_tuple()
    token = (token or cfg["token"]).upper()
    chain = (chain or cfg["chain"]).lower()
    if not math.isfinite(deposit_usd) or deposit_usd <= 0 or deposit_usd > 10_000:
        return {"error": "invalid_deposit", "detail": "deposit must be in (0, 10000]"}
    if _to_cents(deposit_usd) < 1:
        # The ledger is integer cents, so a $0.004 deposit would be credited as a
        # $0.00 channel — a real transfer swallowed for nothing. Refuse BEFORE the
        # tx is verified/consumed so the payer's hash stays unspent.
        return {"error": "invalid_deposit", "detail": "deposit must be at least 0.01"}
    if not customer_id or not customer_email:
        return {"error": "customer_required", "detail": "customer authentication required"}

    tx_clean = ""
    deposit_wallet = (wallet or "").strip()
    deposit_wallet_verified = False
    if demo_payment_bypass():
        tx_clean = (tx_hash or "").strip() or ""
        if not tx_clean:
            ch_id_preview = f"ch_{uuid.uuid4().hex[:12]}"
            tx_clean = f"demo-{ch_id_preview}"
    else:
        if not (tx_hash or "").strip():
            return {"error": "tx_hash_required", "detail": "deposit transaction hash required"}
        tx_clean = normalize_tx_hash(tx_hash, chain=chain)
        if _tx_hash_already_used(tx_clean):
            return {"error": "tx_hash_already_used", "detail": "transaction hash already used"}
        verified = verify_tx_transfer(
            tx_hash=tx_clean,
            amount_usd=deposit_usd,
            chain=chain,
            token=token,
            expect_sender=BIND_SENDER,
        )
        if not verified["verified"]:
            return {
                "error": "tx_not_verified",
                "detail": f"on-chain deposit not verified ({verified['error']})",
            }
        sender = str(verified["from"] or "")
        declared = (wallet or "").strip()
        if declared and declared.lower() != sender.lower():
            return {
                "error": "wallet_mismatch",
                "detail": "declared wallet is not the on-chain sender of this deposit",
            }
        deposit_wallet = sender
        if signature.strip():
            if not is_evm_chain(chain):
                return {
                    "error": "deposit_proof_unsupported_chain",
                    "detail": f"payer proof is only implemented for EVM chains, not {chain}",
                }
            recovered = recover_channel_open_payer(
                chain=chain,
                tx_hash=tx_clean,
                payer=sender,
                amount_usd=deposit_usd,
                signature=signature.strip(),
            )
            if not recovered or canonical_proof_payer(recovered) != canonical_proof_payer(sender):
                return {
                    "error": "deposit_proof_invalid",
                    "detail": "signature does not prove control of the paying wallet",
                }
            deposit_wallet_verified = True
        if require_payer_proof() and not deposit_wallet_verified:
            # Recipient+amount alone cannot say WHOSE deposit this is; refuse to
            # credit rather than let the first submitter claim someone else's money.
            return {
                "error": "deposit_proof_required",
                "detail": (
                    "deposit must include a signature proving control of the paying "
                    "wallet — sign the canonical challenge "
                    "(deposit_proof_challenge / on_chain.channel_open_proof_message) "
                    "with the wallet that paid and resend it as `signature`"
                ),
                "challenge": deposit_proof_challenge(
                    chain=chain, tx_hash=tx_clean, payer=sender, deposit_usd=deposit_usd
                ),
            }

    ch_id = f"ch_{uuid.uuid4().hex[:12]}"
    now = time.time()
    channel_secret = secrets.token_urlsafe(24)
    deposit_cents = _to_cents(deposit_usd)
    channel = {
        "channel_id": ch_id,
        "deposit_usd": _from_cents(deposit_cents),
        "balance_usd": _from_cents(deposit_cents),
        "spent_usd": 0.0,
        "token": token,
        "chain": chain,
        "wallet": deposit_wallet,
        "deposit_wallet": deposit_wallet,
        "deposit_wallet_verified": deposit_wallet_verified,
        "open_tx_hash": tx_clean or f"demo-{ch_id}",
        "customer_id": customer_id,
        "customer_email": customer_email,
        "status": "open",
        "created_at": now,
        "expires_at": now + 3600 * 24,
        "ledger": [],
        "secret_hash": _hash_secret(channel_secret),
    }
    # CROSS-STACK single-use. _tx_hash_already_used only sees THIS package's ledger;
    # aimarket-hub's channel door keeps its own consumed_deposits table. One real
    # transfer plus one signature therefore bought a funded channel at each door until
    # both started writing the shared registry — $5 paid, $10 credited. Claimed here,
    # outside the store lock (the claim is its own atomic O_EXCL create and must not be
    # held across file I/O), and released below if the channel is not actually created.
    claimed = False
    if tx_clean and not is_demo_tx(tx_clean):
        claim = claim_deposit(
            chain=chain, tx_hash=tx_clean, stack=DEPOSIT_STACK_WEB_V1,
            claim_id=ch_id, amount_cents=int(round(deposit_usd * 100)),
        )
        if not claim.get("ok"):
            if claim.get("error") == "deposit_registry_unavailable":
                return {
                    "error": "deposit_registry_unavailable",
                    "detail": (
                        "shared deposit registry unavailable — refusing to credit a "
                        "channel that cannot be made exclusive across settlement doors "
                        "(set AIMARKET_DEPOSIT_CLAIMS_DIR)"
                    ),
                }
            return {
                "error": "tx_hash_already_used",
                "detail": "transaction hash already used to fund a channel",
            }
        claimed = True

    def _unclaim() -> None:
        if claimed:
            release_deposit_claim(
                chain=chain, tx_hash=tx_clean, stack=DEPOSIT_STACK_WEB_V1, claim_id=ch_id,
            )

    with channel_store_lock():
        # Re-check the deposit tx hash inside the lock to close the TOCTOU where two
        # concurrent opens reuse one on-chain deposit (and to avoid clobbering a
        # channel another worker just inserted).
        if tx_clean and not is_demo_tx(tx_clean) and _tx_hash_already_used(tx_clean):
            _unclaim()
            return {"error": "tx_hash_already_used", "detail": "transaction hash already used"}
        data = _load_channels()
        data[ch_id] = channel

        if uni_enabled():
            from web.backend.services.uni_bridge import record_channel_open

            uni_out = record_channel_open(
                customer_id=customer_id,
                channel_id=ch_id,
                deposit_usd=deposit_usd,
                tx_hash=tx_clean or f"demo-{ch_id}",
                chain=chain,
                token=token,
            )
            if uni_out and uni_out.get("error"):
                data.pop(ch_id, None)
                _save_channels(data)
                # The channel never came into existence, so the deposit must stay
                # spendable — otherwise a UNI hiccup silently burns a real payment.
                _unclaim()
                return {"error": "uni_hold_failed", "detail": uni_out.get("error")}
            channel["uni"] = uni_out
            channel["balance_uni"] = uni_out.get("amount_uni") if uni_out else usd_to_uni(deposit_usd)

        _save_channels(data)

    channel["signature"] = sign_payload(
        {"channel_id": ch_id, "deposit_usd": channel["deposit_usd"], "created_at": now}
    )
    return {"channel": channel, "channel_secret": channel_secret, "protocol_version": "v1"}


def get_channel(channel_id: str) -> dict[str, Any] | None:
    return _load_channels().get(channel_id)


def deduct_channel(
    channel_id: str,
    amount_usd: float,
    *,
    ref: str,
    secret: str = "",
) -> dict[str, Any]:
    """Debit a channel for one call. Returns ``billed_usd`` — what was charged.

    ``billed_usd`` can exceed ``amount_usd`` by at most a cent (sub-cent prices
    round up so they cannot be served for free); callers must bill/receipt the
    returned amount, not the quote, so the receipt matches the ledger.
    """
    # Whole balance check→debit→persist runs under the store lock so concurrent
    # invokes on the same channel cannot double-spend (see C1/H3).
    with channel_store_lock():
        data = _load_channels()
        ch = data.get(channel_id)
        if not ch or ch.get("status") != "open":
            return {"ok": False, "error": "channel_not_open"}

        stored_hash = str(ch.get("secret_hash") or "")
        if stored_hash and not hmac.compare_digest(stored_hash, _hash_secret(secret)):
            return {"ok": False, "error": "invalid_channel_secret"}

        expires_at = float(ch.get("expires_at") or 0)
        if expires_at and time.time() > expires_at:
            # A lapsed channel must not keep spending the customer's deposit; the
            # remainder is theirs to close out. (Status stays "open" so close still
            # works — expiry blocks debits, not settlement.)
            return {"ok": False, "error": "channel_expired"}

        if not math.isfinite(amount_usd) or amount_usd < 0:
            # A negative "debit" used to CREDIT the channel — an uncapped mint.
            return {"ok": False, "error": "invalid_amount"}

        bill_cents = _bill_cents(amount_usd)
        if bill_cents == 0:
            # Genuinely free capability: nothing to debit, nothing to log.
            return {"ok": True, "channel": ch, "billed_usd": 0.0}

        if uni_enabled() and ch.get("uni"):
            from web.backend.services.uni_bridge import record_channel_spend

            spend = record_channel_spend(
                channel_id=channel_id, price_usd=_from_cents(bill_cents), ref=ref
            )
            if spend and spend.get("duplicate"):
                return {"ok": False, "error": "duplicate_spend"}
            if not spend or spend.get("error"):
                return {"ok": False, "error": spend.get("error", "insufficient_balance") if spend else "uni_unavailable"}
            remaining_uni = float(spend.get("remaining_uni") or 0)
            ch["balance_usd"] = round(uni_to_usd(remaining_uni), 4)
            ch["balance_uni"] = remaining_uni
        else:
            bal_cents = _to_cents(ch.get("balance_usd"))
            if bill_cents > bal_cents:
                return {"ok": False, "error": "insufficient_balance"}
            ch["balance_usd"] = _from_cents(bal_cents - bill_cents)

        ch["spent_usd"] = _from_cents(_to_cents(ch.get("spent_usd")) + bill_cents)
        ch.setdefault("ledger", []).append(
            {
                "time": time.time(),
                "amount_usd": _from_cents(bill_cents),
                "ref": ref,
                "type": "debit",
            }
        )
        data[channel_id] = ch
        _save_channels(data)
        return {"ok": True, "channel": ch, "billed_usd": _from_cents(bill_cents)}


def refund_channel(
    channel_id: str,
    amount_usd: float,
    *,
    ref: str,
    debit_ref: str,
) -> dict[str, Any]:
    """Reverse a debit this channel already paid, back into its own balance.

    Caller contract — this is a SERVER-SIDE reversal primitive, not a customer
    endpoint. No channel secret is required because no value leaves the channel,
    so the abuse to defend against is inflation, and it is defended structurally:

    * only an ``open`` channel can be credited (a closed one is settled; crediting
      it would mint balance after the settlement receipt was signed);
    * ``debit_ref`` is MANDATORY and must name a real debit in this channel's
      ledger. The deposit cap alone is not enough: it bounds the balance but not
      the number of reversals, so N anonymous calls could hand back N debits'
      worth of spend one call at a time until ``spent_usd`` reached zero. Naming
      the debit makes the reversal both capped at that debit's amount and
      idempotent, so a retry cannot pay out twice;
    * the credit is additionally hard-capped at ``deposit - balance`` (i.e. at what
      was really spent), so no sequence of calls can lift a channel above its
      deposit — the old version raised the balance by an arbitrary amount with no
      cap at all.
    """
    with channel_store_lock():
        data = _load_channels()
        ch = data.get(channel_id)
        if not ch:
            return {"ok": False, "error": "channel_not_found"}
        if ch.get("status") != "open":
            return {"ok": False, "error": "channel_not_open"}
        if not math.isfinite(amount_usd) or amount_usd <= 0:
            return {"ok": False, "error": "invalid_amount"}
        if not (debit_ref or "").strip():
            # An unnamed reversal is unauditable and repeatable — refuse it.
            return {"ok": False, "error": "debit_ref_required"}

        ledger = ch.setdefault("ledger", [])
        want_cents = _to_cents(amount_usd)
        debit = next(
            (e for e in ledger if e.get("type") == "debit" and e.get("ref") == debit_ref),
            None,
        )
        if debit is None:
            return {"ok": False, "error": "unknown_debit"}
        if any(
            e.get("reverses") == debit_ref
            for e in ledger
            if e.get("type") in ("credit", "credit_owed")
        ):
            return {"ok": False, "error": "already_refunded"}
        want_cents = min(want_cents, _to_cents(debit.get("amount_usd")))

        deposit_cents = _to_cents(ch.get("deposit_usd"))
        bal_cents = _to_cents(ch.get("balance_usd"))
        max_cents = deposit_cents - bal_cents
        if max_cents <= 0:
            return {"ok": False, "error": "refund_exceeds_deposit"}
        granted = min(want_cents, max_cents)
        if granted <= 0:
            return {"ok": False, "error": "invalid_amount"}

        now = time.time()
        if uni_enabled() and ch.get("uni"):
            # The spend left the UNI hold and this bridge has no un-spend
            # primitive, so crediting the local mirror would invent balance the
            # UNI ledger does not have. Record the debt honestly instead of
            # lying about the balance.
            ledger.append(
                {
                    "time": now,
                    "amount_usd": _from_cents(granted),
                    "ref": ref,
                    "type": "credit_owed",
                    "reverses": debit_ref,
                    "reason": "uni_refund_unavailable",
                }
            )
            ch["refund_owed_usd"] = _from_cents(
                _to_cents(ch.get("refund_owed_usd")) + granted
            )
            data[channel_id] = ch
            _save_channels(data)
            logger.error(
                "UNI-backed channel %s owes %s USD back to %s (no UNI reversal primitive)",
                channel_id,
                _from_cents(granted),
                ch.get("customer_id") or "?",
            )
            return {
                "ok": False,
                "error": "uni_refund_unavailable",
                "owed_usd": _from_cents(granted),
                "channel": ch,
            }

        ch["balance_usd"] = _from_cents(bal_cents + granted)
        ch["spent_usd"] = _from_cents(max(0, _to_cents(ch.get("spent_usd")) - granted))
        ledger.append(
            {
                "time": now,
                "amount_usd": _from_cents(granted),
                "ref": ref,
                "type": "credit",
                "reverses": debit_ref,
            }
        )
        data[channel_id] = ch
        _save_channels(data)
        return {"ok": True, "credited_usd": _from_cents(granted), "channel": ch}


def _refund_destination(ch: dict[str, Any]) -> str:
    """Wallet a channel remainder is owed to (the verified depositor)."""
    return str(ch.get("deposit_wallet") or ch.get("wallet") or "").strip()


def close_channel(
    *,
    channel_id: str,
    settle_tx_hash: str = "",
    customer_id: str = "",
) -> dict[str, Any]:
    """Settle and close a channel; the remainder goes back to the depositor.

    ``settle_tx_hash`` is OPTIONAL and, when given, is verified in the direction
    the money actually travels — the platform paying the depositor's wallet. The
    previous version verified it as a payment *to the platform's* settlement
    wallet of the amount the platform owed the customer, which no honest
    transaction can satisfy, so every channel with a non-zero balance was
    unclosable. Closing now always settles the ledger: with a verified proof the
    refund is recorded ``paid``, otherwise it is recorded as an explicit
    outstanding obligation (``owed``) that :func:`list_outstanding_refunds`
    reports and :func:`mark_refund_settled` clears once the operator has paid it.
    This function never moves funds.
    """
    snapshot = _load_channels().get(channel_id)
    if not snapshot:
        return {"error": "channel_not_found"}
    if snapshot.get("status") != "open":
        return {"error": "channel_already_closed"}
    owner = str(snapshot.get("customer_id") or "")
    if owner and customer_id and owner != customer_id:
        return {"error": "forbidden", "detail": "channel belongs to another customer"}
    if owner and not customer_id:
        return {"error": "customer_required", "detail": "customer authentication required"}

    refund = float(snapshot.get("balance_usd") or 0)
    chain = str(snapshot.get("chain") or pilot_tuple()["chain"]).lower()
    token = str(snapshot.get("token") or pilot_tuple()["token"]).upper()
    destination = _refund_destination(snapshot)

    # On-chain settlement verification (network I/O) runs OUTSIDE the store lock.
    settle_clean = (settle_tx_hash or "").strip()
    proof_kind = ""
    proof_amount = 0.0
    if demo_payment_bypass():
        # Dev/demo: the deposit was demo money too, so a demo settlement hash
        # closes the loop symmetrically. Nothing on any chain is asserted here.
        settle_clean = settle_clean or f"demo-settle-{channel_id}"
        if refund > 1e-9:
            proof_kind = "demo"
            proof_amount = refund
    elif settle_clean and refund > 1e-9:
        settle_clean = normalize_tx_hash(settle_clean, chain=chain)
        if _tx_hash_already_used(settle_clean):
            return {"error": "tx_hash_already_used", "detail": "settlement transaction hash already used"}
        verified = verify_refund_transfer(
            tx_hash=settle_clean,
            amount_usd=refund,
            chain=chain,
            token=token,
            destination=destination,
        )
        if not verified["verified"]:
            # A rejected proof is reported instead of being silently downgraded to
            # "owed"; closing without a hash always works, so this never blocks.
            return {
                "error": "settle_tx_not_verified",
                "detail": f"settlement to {destination or 'unknown wallet'} not verified ({verified['error']})",
            }
        proof_kind = "on_chain"
        proof_amount = refund
    else:
        # No proof supplied, or nothing owed: keep an unverifiable hash out of the
        # record so it can never be mistaken for settlement evidence later.
        settle_clean = settle_clean if (settle_clean and refund > 1e-9) else ""

    # Re-load + re-check status under the lock so a concurrent close can't settle twice.
    with channel_store_lock():
        data = _load_channels()
        ch = data.get(channel_id)
        if not ch:
            return {"error": "channel_not_found"}
        if ch.get("status") != "open":
            return {"error": "channel_already_closed"}
        if settle_clean and not is_demo_tx(settle_clean) and _tx_hash_already_used(settle_clean):
            return {"error": "tx_hash_already_used", "detail": "settlement transaction hash already used"}

        refund = float(ch.get("balance_usd") or 0)
        used = float(ch.get("spent_usd") or 0)

        if uni_enabled() and ch.get("uni"):
            from web.backend.services.uni_bridge import record_channel_release

            released = record_channel_release(channel_id)
            if released and not released.get("error"):
                refund = uni_to_usd(float(released.get("refund_uni") or 0))
                ch["balance_usd"] = round(refund, 4)

        refund_cents = _to_cents(refund)
        paid_cents = min(_to_cents(proof_amount), refund_cents) if proof_kind else 0
        owed_cents = max(0, refund_cents - paid_cents)
        if refund_cents <= 0:
            refund_status = "none"
        elif owed_cents <= 0:
            refund_status = "paid"
        else:
            # Partially-proved settlement (the balance moved between verification
            # and the lock) is still an obligation for the difference.
            refund_status = "owed"

        now = time.time()
        ch["status"] = "closed"
        ch["closed_at"] = now
        ch["refund_usd"] = _from_cents(refund_cents)
        ch["settle_tx_hash"] = settle_clean
        ch["refund_status"] = refund_status
        ch["refund_destination"] = destination
        ch["refund_paid_usd"] = _from_cents(paid_cents)
        ch["refund_owed_usd"] = _from_cents(
            _to_cents(ch.get("refund_owed_usd")) + owed_cents
        )
        ch["refund_proof"] = proof_kind
        if refund_cents > 0:
            ch.setdefault("ledger", []).append(
                {
                    "time": now,
                    "amount_usd": _from_cents(refund_cents),
                    "ref": f"close:{channel_id}",
                    "type": "refund_settled" if refund_status == "paid" else "refund_obligation",
                    "settle_tx_hash": settle_clean,
                    "destination": destination,
                    "proof": proof_kind,
                }
            )
        data[channel_id] = ch
        _save_channels(data)

    if refund_status == "owed":
        logger.warning(
            "channel %s closed owing %s %s to %s (customer %s) — outstanding refund obligation",
            channel_id,
            ch["refund_owed_usd"],
            token,
            destination or "an unknown wallet",
            ch.get("customer_email") or ch.get("customer_id") or "?",
        )

    receipt = {
        "channel_id": channel_id,
        "used_usd": round(used, 4),
        "refund_usd": _from_cents(refund_cents),
        "settle_tx_hash": ch["settle_tx_hash"],
        "refund_status": refund_status,
        "refund_paid_usd": ch["refund_paid_usd"],
        "refund_owed_usd": _from_cents(owed_cents),
        "refund_destination": destination,
        "refund_proof": proof_kind,
    }
    if refund_status == "owed" and not destination:
        # Honest about WHY it cannot be paid: legacy channels (and demo opens)
        # carry no verified depositor wallet, so the operator must collect one.
        receipt["refund_destination_unknown"] = True
    receipt["signature"] = sign_payload(receipt)
    return {"channel": ch, "settlement": receipt, "protocol_version": "v1"}


def list_outstanding_refunds() -> list[dict[str, Any]]:
    """Channel remainders the platform still owes — operator/accounting view.

    Closing a channel never moves funds, so every remainder without verified
    settlement proof is a liability that must stay visible until it is paid.
    """
    out: list[dict[str, Any]] = []
    for ch in _load_channels().values():
        owed = _to_cents(ch.get("refund_owed_usd"))
        if owed <= 0:
            continue
        out.append(
            {
                "channel_id": ch.get("channel_id"),
                "customer_id": ch.get("customer_id", ""),
                "customer_email": ch.get("customer_email", ""),
                "destination": _refund_destination(ch),
                "chain": ch.get("chain", ""),
                "token": ch.get("token", ""),
                "owed_usd": _from_cents(owed),
                "status": ch.get("status", ""),
                "closed_at": ch.get("closed_at"),
            }
        )
    out.sort(key=lambda r: (r.get("closed_at") or 0))
    return out


def mark_refund_settled(
    *, channel_id: str, settle_tx_hash: str, operator_id: str = ""
) -> dict[str, Any]:
    """Record proof that an outstanding refund obligation was paid out-of-band.

    This only records evidence — it never sends funds. The transaction must be
    verified in the outbound direction (an allowed payout wallet → the recorded
    depositor wallet, for at least the owed amount); anything unverifiable leaves
    the obligation standing.
    """
    snapshot = _load_channels().get(channel_id)
    if not snapshot:
        return {"ok": False, "error": "channel_not_found"}
    owed = _from_cents(_to_cents(snapshot.get("refund_owed_usd")))
    if owed <= 0:
        return {"ok": False, "error": "no_outstanding_refund"}
    destination = _refund_destination(snapshot)
    if not destination:
        return {"ok": False, "error": "refund_destination_unknown"}
    tx = (settle_tx_hash or "").strip()
    if not tx:
        return {"ok": False, "error": "settle_tx_hash_required"}

    chain = str(snapshot.get("chain") or pilot_tuple()["chain"]).lower()
    token = str(snapshot.get("token") or pilot_tuple()["token"]).upper()
    tx_clean = normalize_tx_hash(tx, chain=chain)
    if _tx_hash_already_used(tx_clean):
        return {"ok": False, "error": "tx_hash_already_used"}
    verified = verify_refund_transfer(
        tx_hash=tx_clean,
        amount_usd=owed,
        chain=chain,
        token=token,
        destination=destination,
    )
    if not verified["verified"]:
        return {"ok": False, "error": "settle_tx_not_verified", "detail": verified["error"]}

    with channel_store_lock():
        data = _load_channels()
        ch = data.get(channel_id)
        if not ch:
            return {"ok": False, "error": "channel_not_found"}
        still_owed = _to_cents(ch.get("refund_owed_usd"))
        if still_owed <= 0:
            return {"ok": False, "error": "no_outstanding_refund"}
        if _to_cents(owed) < still_owed:
            # The debt grew after verification — the proof no longer covers it.
            return {"ok": False, "error": "settlement_amount_stale"}
        if not is_demo_tx(tx_clean) and _tx_hash_already_used(tx_clean):
            return {"ok": False, "error": "tx_hash_already_used"}
        now = time.time()
        ch["refund_owed_usd"] = 0.0
        ch["refund_paid_usd"] = _from_cents(
            _to_cents(ch.get("refund_paid_usd")) + still_owed
        )
        ch["refund_status"] = "paid"
        ch["refund_proof"] = "on_chain"
        ch["settle_tx_hash"] = tx_clean
        ch.setdefault("ledger", []).append(
            {
                "time": now,
                "amount_usd": _from_cents(still_owed),
                "ref": f"refund_settled:{channel_id}",
                "type": "refund_settled",
                "settle_tx_hash": tx_clean,
                "destination": destination,
                "operator_id": operator_id,
                "proof": "on_chain",
            }
        )
        data[channel_id] = ch
        _save_channels(data)
    return {
        "ok": True,
        "channel_id": channel_id,
        "settled_usd": _from_cents(still_owed),
        "settle_tx_hash": tx_clean,
        "destination": destination,
    }
