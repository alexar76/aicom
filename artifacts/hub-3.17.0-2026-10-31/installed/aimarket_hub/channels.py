"""Pre-funded payment channels for off-chain capability invocation.

Implements channel/open, channel/close from Protocol v1/v2 spec.

Storage: PostgreSQL through ``DATABASE_URL`` in production; SQLite is for dev/test.
Amounts: integer cents internally (no IEEE 754 drift).
Rate limiting: per-wallet caps on open/close (see "Rate limiting" below).
Background sweep: expires stale channels and reaps orphaned holds every 5 min.

Settlement model — this ledger is the ONLY channel state (no on-chain mirror)
    This module does not mirror channel state on-chain and does not hold funds in
    escrow. A deposit is an ordinary on-chain transfer to the PLATFORM SETTLEMENT
    WALLET (on_chain.platform_recipient), verified after the fact; from that moment
    the money is in the operator's custody and every debit, balance and remainder
    below is bookkeeping in this ledger.

    ``AIMarketEscrow.debitChannel`` IS called from this repository now — but only from
    an operator CLI (``python -m aimarket_hub.escrow_bridge.cli submit --yes``), never
    from a code path a request can reach. The HTTP surface is deliberately plan-only:
    ``GET /ai-market/v2/escrow/plan`` is hardcoded to ``PlanOnlySigner``, and there is
    no route that broadcasts. What a paid invoke DOES do is capture and verify the
    depositor's EIP-712 ``DebitAuthorization`` before the provider runs, failing closed
    with 402 — so the hub holds a collectable claim, and collecting it is a separate,
    human-initiated act.

    Consequently this ledger is still the only thing that moves when a channel is
    debited. If an operator ALSO opens a contract channel for the same funds, its
    on-chain ``usedAmount`` stays 0 no matter how much is consumed here, so
    ``refundChannel`` / ``expireChannel`` would return a fully-consumed deposit in
    full. The two rails remain mutually exclusive. Tracked as KI-11 in
    docs/known-issues.md; the honest consequences for refunds are spelled out under
    "Refunds are OBLIGATIONS" below.

Deposit binding (PAYAUTH-003)
    A deposit is verified with the SENDER-returning verifier
    (on_chain.verify_tx_payment_details) and the channel is credited ONLY to the
    wallet that actually paid on-chain. Verifying recipient/amount alone lets anyone
    watching the shared settlement wallet claim someone else's inbound transfer by
    quoting its tx hash first. If the verifier cannot report a sender, the deposit is
    refused (fail closed). A caller that supplies no wallet gets the channel bound to
    the on-chain payer — an on-chain-funded channel is never anonymous.

    Matching the claimed wallet against the on-chain sender is NOT sufficient on its
    own: the payer's address is public — it is printed in the very transaction the
    claimant quotes — so a front-runner simply names the victim's address, the match
    succeeds, and open() hands THEM the channel_secret that authorizes debits (the
    invoke path presents only channel id + secret, no wallet). The claimant must
    therefore PROVE control of the paying wallet with an EIP-191 signature over
    payer_proof_challenge(), recovered via on_chain.recover_channel_open_payer.

    That challenge is the CANONICAL, versioned one defined in
    web/backend/services/ai_market_protocol/on_chain.py and shared byte-for-byte with
    the web v1 channel stack — each side used to have its own incompatible message,
    so one signature could not satisfy both and no SDK could target both doors. The
    preimage binds domain+version, purpose, chain, tx hash, payer and amount; read
    that module's CANONICAL PAYER PROOF block for why each field is in it. Non-EVM
    chains have no implemented proof scheme and are refused rather than credited
    unproven.

Single-use deposits are claimed under a CANONICAL key (PAYAUTH-002)
    An EVM tx hash and a chain name are case-insensitive at the RPC layer, so
    ("Base", "0xABC…") and ("base", "0xabc…") are the same transaction. Claiming them
    verbatim let one real deposit be re-claimed once per capitalisation and fund N
    funded channels; the claim is now keyed on the normalised pair, and the lookup is
    case-insensitive so rows written before this fix still block a replay. Base58
    Solana signatures are case-SIGNIFICANT and are left byte-exact.

Refunds are OBLIGATIONS, not transfers (ACCT-001)
    Deposits are paid to the platform's own settlement wallet, so the unspent
    remainder at close/expiry is already in the operator's custody and NOTHING in this
    module can send value. The remainder is therefore recorded as an explicit,
    queryable payout obligation (`channel_payout_obligations`, migration 017) and the
    settlement dict reports `refund_executed_usd` (always 0.0 here) separately from
    `refund_owed_usd`. Operator payouts happen out-of-band and are attested back with
    mark_obligation_paid().

Rate limiting
    Per-wallet sliding windows held in-process: with N worker processes the effective
    cap is N x the configured value, and wallet-less ("anonymous") opens share ONE
    bounded bucket instead of being exempt. The tracking table is bounded by LRU
    EVICTION, not by refusal — the key is caller-supplied, so refusing when full let
    ~50k junk wallet strings lock every real depositor out of open and close for an
    hour. The flood itself is capped at the HTTP layer, per client IP (api.py), where
    the identity is not attacker-chosen.

Env knobs (read dynamically so they are monkeypatchable, hub convention):
    AIMARKET_CHANNELS_DB_PATH             data/channels.db  ledger database
    AIMARKET_CHANNEL_ALLOW_UNPROVEN_PAYER 0     opt OUT of the payer proof-of-control
                                                requirement above (transition only —
                                                leaves deposit front-running open)
    AIMARKET_CHANNEL_ANON_OPENS_PER_HOUR  200   shared cap for wallet-less opens
    AIMARKET_CHANNEL_ANON_CLOSES_PER_HOUR 600   shared cap for wallet-less closes
    AIMARKET_CHANNEL_HOLD_REAP_AFTER_SECS 86400 release a hold stuck 'held' this long
                                                with no live verification (0 = off)
    AIMARKET_VERIFY_SETTLEMENTS_DB_PATH   —     where verified_settlements lives
                                                (defaults to AIMARKET_DB_PATH /
                                                data/hub.db); the reaper refuses to
                                                release anything it cannot read
"""

from __future__ import annotations

import calendar
import contextlib
import hashlib
import hmac
import json
import logging
import math
import os
import secrets
import sqlite3
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any
from aimarket_hub.paging import page_limit
from aimarket_hub.channel_ledger.storage import LedgerStorageMixin
from aimarket_hub.channel_ledger.sweeps import LedgerSweepsMixin
from aimarket_hub.channel_ledger.opening import LedgerOpeningMixin
from aimarket_hub.channel_ledger.spending import LedgerSpendingMixin


# Payout obligations one read may return.
OBLIGATIONS_PAGE_MAX = 5_000

logger = logging.getLogger(__name__)

# ── Env-driven defaults ──────────────────────────────────────────

_DEFAULT_CHAIN = os.getenv("AIMARKET_PAYMENT_CHAIN", "base")
_DEFAULT_TOKEN = os.getenv("AIMARKET_PAYMENT_TOKEN", "USDC")
_RECIPIENT = os.getenv("AIMARKET_PAYMENT_RECIPIENT", "")
_VERIFY_STUB = os.getenv("AIFACTORY_PAYMENT_VERIFY_STUB", "0") == "1"
_MIN_CONFIRMATIONS = int(os.getenv("AIFACTORY_PAYMENT_MIN_CONFIRMATIONS", "2"))
_DB_PATH = os.getenv("AIMARKET_CHANNELS_DB_PATH", "data/channels.db")

# Rate limits
_MAX_OPENS_PER_WALLET_PER_HOUR = 20
_MAX_CLOSES_PER_WALLET_PER_HOUR = 60
_DEFAULT_ANON_OPENS_PER_HOUR = 200
_DEFAULT_ANON_CLOSES_PER_HOUR = 600
# One shared bucket for every wallet-less caller. Exempting them (the old behaviour)
# made a public hub effectively unlimited: an attacker just omits the wallet field.
_ANON_RATE_KEY = "\x00anonymous"
# Upper bound on tracked buckets. Without it, one request per fresh wallet string
# grows the in-process dicts without limit (memory DoS). Full table => LRU eviction
# (see _check_rate for why refusing instead was an availability DoS).
_MAX_RATE_TRACKED_KEYS = 50_000
_DEFAULT_MAX_CHANNELS = 10_000
_CHANNEL_EXPIRY_SECS = 86400  # 24h
_SWEEP_INTERVAL_SECS = 300     # 5 min

# Orphaned-hold reaper (see module docstring)
_DEFAULT_HOLD_REAP_AFTER_SECS = 86400  # 24h
_HOLD_REAP_SCAN_LIMIT = 500            # bounded work per pass

# Every `verified_settlements` status in which a Pay-on-Verified row still OWNS money: its
# invoke hold and, once an appeal is filed, the appellant's bond. Defined here rather than
# in verified_settlement (which imports this module) because the reaper is the reader that
# must never be missing one. With an appeal window a verdict sits 'provisional' for hours
# with the hold still 'held'; had the reaper kept its old ('pending', 'verifying') list it
# would have released that hold, and the later capture would have spent the same cents twice.
UNRESOLVED_SETTLEMENT_STATUSES: tuple[str, ...] = (
    "pending", "verifying", "provisional", "appealed", "appeal_verifying", "finalizing",
)
# An appeal bond is held under `appeal_<settlement nonce>`, on the buyer's channel.
APPEAL_BOND_PREFIX = "appeal_"

# Cents per USD (no floats for money)
_CENTS_PER_USD = 100


def _validate_recipient() -> None:
    # Only a hub with the chain on can use the recipient. Every other hub printed this on
    # every command, `--help` included — on a credits/x402 hub it describes a rail that is
    # off, and it was the first line a stranger saw from the quickstart (2026-10-12).
    crypto_on = os.environ.get("AIFACTORY_CRYPTO_ENABLED", "0").strip().lower() in (
        "1", "true", "yes", "on")
    if not _RECIPIENT and crypto_on:
        logger.warning(
            "AIMARKET_PAYMENT_RECIPIENT is not set. "
            "Payment channels will work in demo mode but real USDT/USDC "
            "transfers will fail. Set it in .env or environment."
        )


_validate_recipient()


def _is_production_mode() -> bool:
    """Mirror security.prod_startup_guard.is_production_mode with an env fallback.

    The hub also ships as a standalone package where the security module may not
    be importable, so we fall back to the AIFACTORY_PROD env contract used
    elsewhere in the hub (signing.py, capability_nft.py).
    """
    try:
        from security.prod_startup_guard import is_production_mode

        return is_production_mode()
    except Exception:
        return os.environ.get("AIFACTORY_PROD", "").strip() == "1"


def _allow_demo_credit() -> bool:
    """Whether to credit a channel WITHOUT on-chain verification (dev/demo only).

    Read dynamically (not a module constant) so it's monkeypatchable in tests. Fail-closed by
    default: a non-production deploy that hasn't explicitly opted in will REFUSE to credit an
    unverified deposit, so a public hub that simply forgot AIFACTORY_PROD can't hand out free
    channels.
    """
    return os.environ.get("AIMARKET_ALLOW_DEMO_CREDIT", "").strip() == "1"


def payment_readiness() -> dict[str, Any]:
    """Can this hub actually credit a paid channel? Asked out loud, not discovered later.

    A hub in production with no reachable deposit verifier refuses EVERY paid
    ``channel/open`` with "on-chain verification unavailable". That is the correct
    fail-closed behaviour and it is also a total revenue block, and it was invisible:
    modelmarket.dev sat in exactly this state — ``AIFACTORY_PROD=1``, stub off,
    ``verify_tx_payment_details`` unimportable (``No module named 'web'``: the canonical
    verifier lives in the web app, which a standalone hub image does not ship) — with 0
    refusals in 72h of logs, because nobody had tried. Zero refusals read like health.

    So the state is reported next to the money it governs, the way
    ``supply_chain_admission.enforce_readiness`` reports its own.
    """
    prod = _is_production_mode()
    canonical = _shared_on_chain("verify_tx_payment_details") is not None
    native = _native_verifier_ready(_DEFAULT_CHAIN, _DEFAULT_TOKEN)
    crypto = _crypto_enabled()
    blockers: list[str] = []
    if not crypto:
        blockers.append("crypto_disabled")
    if not _RECIPIENT:
        blockers.append("recipient_not_configured")
    if prod and not _VERIFY_STUB and not canonical and native.get("error"):
        blockers.append("deposit_verifier_unusable")
    if prod and not _VERIFY_STUB and not _payer_proof_ready():
        # Proving the deposit is two questions; a hub that can answer only the first
        # still refuses every deposit, one step later.
        blockers.append("payer_proof_unusable")
    # Escrow-only mode with no bridge to route through refuses BOTH doors, by design
    # (see `_escrow_required`). Say so here rather than let it be discovered one
    # refused open at a time: the operator asked for the strongest setting and the
    # honest answer is that this hub currently opens no channels at all.
    escrow_only = _escrow_required()
    bridge_on = False
    if escrow_only:
        try:
            from aimarket_hub.escrow_bridge import config as bridge_config

            bridge_on = bool(bridge_config.enabled())
        except Exception:
            bridge_on = False
        if not bridge_on:
            blockers.append("escrow_required_but_bridge_disabled")
    return {
        "can_credit_channels": not blockers,
        "blockers": blockers,
        "escrow_required": escrow_only,
        "custodial_deposit_reachable": not escrow_only,
        "production_mode": prod,
        "verify_stub": _VERIFY_STUB,
        "deposit_verifier": (
            "canonical" if canonical else ("hub-native" if not native.get("error") else "none")
        ),
        "deposit_verifier_detail": native,
        "recipient_configured": bool(_RECIPIENT),
        "crypto_enabled": crypto,
        "min_confirmations": _MIN_CONFIRMATIONS,
        "payer_proof": "ready" if _payer_proof_ready() else "unusable",
        # The door that has actually carried every channel on this hub so far.
        "escrow_funding": bool(os.getenv("AIMARKET_ESCROW_EVM_ADDRESS")),
    }


def _payer_proof_ready() -> bool:
    """Can this hub both STATE the challenge and evaluate a signature over it?"""
    if _shared_on_chain("recover_channel_open_payer") is not None:
        return True
    try:
        from eth_account import Account  # noqa: F401

        from aimarket_hub.payer_proof import channel_open_proof_message

        return bool(channel_open_proof_message(
            chain="base", tx_hash="0x" + "0" * 64, payer="0x" + "0" * 40, amount_usd=1.0
        ))
    except Exception:
        return False


def _native_verifier_ready(chain: str, token: str) -> dict[str, Any]:
    """Can the hub's own verifier work here — an RPC to ask and a token to look for?"""
    try:
        from aimarket_hub.deposit_verify import STABLECOINS, rpc_urls_for, token_address_for

        name = (token or "").strip().upper()
        urls = rpc_urls_for(chain)
        address = token_address_for(chain, name)
        detail: dict[str, Any] = {
            "chain": chain,
            "token": name,
            "rpc_endpoints": len(urls),
            "token_address": address or "",
        }
        if name not in STABLECOINS:
            detail["error"] = f"{name or 'native coin'} is not a stablecoin — no price oracle"
        elif not urls:
            detail["error"] = f"no RPC endpoint configured for chain {chain!r}"
        elif not address.startswith("0x"):
            detail["error"] = f"no {name} contract address known for chain {chain!r}"
        return detail
    except Exception as exc:  # pragma: no cover - defensive
        return {"error": f"verifier unavailable: {exc}"}


def _warn_if_cannot_take_money() -> None:
    """One loud line at import time, so the condition is in the log before the first sale."""
    readiness = payment_readiness()
    if readiness["can_credit_channels"] or not readiness["production_mode"]:
        return
    if "deposit_verifier_unusable" in readiness["blockers"]:
        logger.error(
            "PAYMENTS BLOCKED: this hub is in production and cannot verify a deposit, so "
            "every deposit-funded channel/open will be refused. Blockers: %s. Detail: %s. "
            "Point AIMARKET_DEPOSIT_RPC_URL at a node for this chain, or configure the "
            "token address (AIMARKET_TOKEN_<SYMBOL>).",
            ", ".join(readiness["blockers"]), readiness.get("deposit_verifier_detail"),
        )
    else:
        logger.warning(
            "Paid channels cannot be credited on this hub — blockers: %s",
            ", ".join(readiness["blockers"]),
        )


def _verify_tx_onchain(
    *, tx_hash: str, amount_usd: float, chain: str, token: str
) -> dict[str, Any]:
    """Verify a deposit tx on-chain before crediting a channel (fail-closed).

    Returns ``{"ok": True, "sender": <payer address or "">}`` only when an on-chain
    verifier confirms the transaction paid the configured recipient the expected
    amount/token with sufficient confirmations. Returns ``{"ok": False, "error": ...}``
    otherwise.

    Uses the SENDER-returning verifier (verify_tx_payment_details) because recipient +
    amount alone do not identify WHO paid: every deposit lands in the same platform
    settlement wallet, so a plain recipient/amount check lets anyone quote a stranger's
    tx hash and have the channel credited to their own wallet (PAYAUTH-003). ``sender``
    is empty when the verifier cannot attribute the payment (e.g. the dev demo-bypass
    path, which has no chain behind it) — callers MUST refuse to credit then.

    If the verifier is not reachable (standalone hub deploy with no chain access) we
    MUST NOT credit in production — we reject with "on-chain verification unavailable"
    so credit is never granted on an unverified tx.
    """
    tx = (tx_hash or "").strip()
    if not tx:
        return {"ok": False, "error": "tx_hash is required for on-chain verification"}

    verify_tx_payment_details = _shared_on_chain("verify_tx_payment_details")
    if verify_tx_payment_details is None:
        # The canonical verifier lives in the web app, which a standalone hub image does
        # not ship — so this branch used to refuse EVERY deposit-funded channel, forever,
        # with no way for the operator to tell that from "nobody has paid yet". The hub
        # verifies the deposit itself instead: same three questions (right recipient,
        # right token, right amount, enough confirmations) asked straight of the chain,
        # and it still returns the PAYER so the caller can bind the channel to it.
        from aimarket_hub.deposit_verify import verify_deposit

        check = verify_deposit(
            tx_hash=tx,
            amount_usd=amount_usd,
            chain=chain,
            token=token,
            recipient=_RECIPIENT,
            min_confirmations=_MIN_CONFIRMATIONS,
        )
        if not check.ok:
            return {"ok": False, "error": check.error}
        logger.info(
            "Deposit %s verified by the hub's own verifier: %s paid %d units of %s "
            "(%d confirmations)",
            tx[:12], check.sender[:10], check.paid_units, token, check.confirmations,
        )
        return {"ok": True, "sender": check.sender}

    try:
        verified, sender = verify_tx_payment_details(
            tx_hash=tx, amount_usd=amount_usd, chain=chain, token=token
        )
    except Exception as exc:
        logger.error("On-chain verification raised for tx %s: %s", tx[:12], exc)
        return {
            "ok": False,
            "error": "on-chain verification unavailable — verifier error, "
            "refusing to credit channel",
        }

    if not verified:
        return {
            "ok": False,
            "error": "on-chain verification failed — transaction does not match "
            "expected recipient/amount/token or has insufficient confirmations",
        }
    return {"ok": True, "sender": str(sender or "").strip()}


# ── Payer proof-of-control (PAYAUTH-003b) ────────────────────────


_ON_CHAIN_MODULE = "web.backend.services.ai_market_protocol.on_chain"
_ON_CHAIN_IMPORT_LOGGED: set[str] = set()


def _shared_on_chain(attr: str) -> Any:
    """One primitive from the CANONICAL on-chain module, or None if unavailable.

    Every cross-package reach into the web stack goes through here so a hub that
    cannot see it degrades identically everywhere (verification, challenge, recovery)
    instead of one call raising ImportError while its neighbour returns an error dict.

    The ``sys.modules`` fallback is not belt-and-braces, it is the whole point: the
    PARENT package's ``__init__`` imports optional web-app dependencies, so on a hub
    where one of those is missing the first ``import …on_chain`` raises even though
    ``on_chain`` itself imported cleanly and is already registered. Without the
    fallback the answer depended on how many times it had been asked — the first
    channel open after boot failed closed and an identical retry succeeded.
    """
    try:
        import web.backend.services.ai_market_protocol.on_chain  # noqa: F401
    except Exception as exc:
        cached = sys.modules.get(_ON_CHAIN_MODULE)
        if cached is None:
            fingerprint = f"missing:{type(exc).__name__}:{exc}"
            if fingerprint not in _ON_CHAIN_IMPORT_LOGGED:
                _ON_CHAIN_IMPORT_LOGGED.add(fingerprint)
                logger.info(
                    "Canonical web on-chain primitives unavailable (%s import failed); "
                    "using standalone Hub-native fallbacks where available: %s",
                    _ON_CHAIN_MODULE, exc,
                )
            return None
        fingerprint = f"cached:{type(exc).__name__}:{exc}"
        if fingerprint not in _ON_CHAIN_IMPORT_LOGGED:
            _ON_CHAIN_IMPORT_LOGGED.add(fingerprint)
            logger.warning(
                "%s imported, but its parent package failed to initialise (%s) — using "
                "the loaded module", _ON_CHAIN_MODULE, exc,
            )
    return getattr(sys.modules.get(_ON_CHAIN_MODULE), attr, None)


def _allow_unproven_payer() -> bool:
    """Whether to credit an on-chain deposit WITHOUT proof the caller controls the payer.

    Default OFF. Matching the caller's claimed wallet against the on-chain sender proves
    nothing, because the sender address is public in the transaction being quoted: a
    front-runner names the victim's own address, the match passes, and open() returns
    the channel_secret to the attacker. This escape hatch exists only so an operator can
    keep the legacy flow alive while the HTTP layer is wired to forward the signature;
    every use is logged.
    """
    return os.environ.get("AIMARKET_CHANNEL_ALLOW_UNPROVEN_PAYER", "").strip() == "1"


def payer_proof_challenge(
    *, payer: str, tx_hash: str, chain: str, deposit_usd: float
) -> str:
    """The exact message the paying wallet must sign to claim a deposit.

    Delegates to the CANONICAL, versioned challenge
    (on_chain.channel_open_proof_message) — the single definition shared with the
    web v1 channel stack, so one signature is valid at both doors and one
    normalisation rule decides whether `0xABC` and `0xabc` are the same deposit.
    The amount is part of the preimage, which is why it is a required argument here.

    Returns "" when the shared primitive is not importable (a standalone hub deploy
    with no `web` package). It is NOT a bare ImportError: every other cross-package
    import in this module degrades to a refusal, and this one used to be the sole
    exception — it raised straight out of the helper. "" means "this deployment
    cannot state or evaluate payer proofs", and it is safe because the matching
    recovery below fails closed for exactly the same reason, so open() refuses every
    on-chain deposit rather than crediting one on an unevaluatable proof.
    """
    build = _shared_on_chain("channel_open_proof_message")
    if build is None:
        # Standalone hub: state the challenge from the byte-identical local copy, so a
        # client is told what to sign instead of being handed "" and a refusal it cannot
        # act on. `payer_proof` mirrors the canonical message and its tests pin them
        # against each other whenever both are importable.
        from aimarket_hub.payer_proof import channel_open_proof_message as _native_message

        return _native_message(
            chain=chain, tx_hash=tx_hash, payer=payer, amount_usd=deposit_usd
        )
    return build(chain=chain, tx_hash=tx_hash, payer=payer, amount_usd=deposit_usd)


def _recover_payer_address(
    *, payer: str, tx_hash: str, chain: str, deposit_usd: float, signature: str
) -> str | None:
    """Address that signed the canonical payer challenge for this deposit, or None.

    None on ANY failure — no signature, malformed signature, or the recovery primitive
    not being importable from this deployment. The caller treats None as "unproven" and
    refuses to credit, so a hub that cannot evaluate the proof never grants one.
    """
    if not (signature or "").strip():
        return None
    recover = _shared_on_chain("recover_channel_open_payer")
    if recover is None:
        # Standalone hub: evaluate the proof ourselves against the byte-identical
        # challenge. Without this the deposit door stayed shut one step later than the
        # verifier — a valid signature over the canonical message was treated as
        # unproven purely because the recovery primitive lived in the web app.
        from aimarket_hub.payer_proof import recover_channel_open_payer as _native_recover

        return _native_recover(
            chain=chain,
            tx_hash=tx_hash,
            payer=payer,
            amount_usd=deposit_usd,
            signature=signature.strip(),
        )
    try:
        return recover(
            chain=chain,
            tx_hash=tx_hash,
            payer=payer,
            amount_usd=deposit_usd,
            signature=signature.strip(),
        )
    except Exception as exc:
        logger.error("Payer proof recovery raised: %s — treating as unproven", exc)
        return None


# ── Helpers ──────────────────────────────────────────────────────

_HEX_DIGITS = frozenset("0123456789abcdefABCDEF")

# Chains whose payout tx ids are 0x + 32 bytes of hex (see _payout_tx_shape_error).
_EVM_PAYOUT_CHAINS = frozenset(
    {"base", "ethereum", "eth", "mainnet", "arbitrum", "optimism", "polygon", "bsc", "avalanche"}
)


def _normalize_chain(chain: str) -> str:
    """Canonical chain id for the single-use deposit claim (chain names are ASCII)."""
    return (chain or "").strip().lower()


def _normalize_tx_hash(tx_hash: str) -> str:
    """Canonical transaction id for the single-use deposit claim.

    EVM hashes are hex and case-insensitive at the JSON-RPC layer, so `0xABC…` and
    `0xabc…` name the SAME transaction. Storing the claim verbatim let one real deposit
    be claimed once per capitalisation and mint a fully funded channel each time.
    Anything that is not 0x-prefixed hex (a base58 Solana signature) is case-SIGNIFICANT
    and must be left byte-exact.
    """
    tx = (tx_hash or "").strip()
    body = tx[2:] if tx[:2].lower() == "0x" else ""
    if body and all(c in _HEX_DIGITS for c in body):
        return "0x" + body.lower()
    return tx


def _claims_fallback_dir(db_path: str) -> str:
    """Stack-local directory used only when no shared registry is configured.

    Derived from the LEDGER'S OWN database path, not the module default: two ledgers
    pointed at different files (a test's tmp db, a second hub instance) must not share
    a claim namespace, or one instance's deposits silently block another's. A
    standalone hub — which has no second door to race with — keeps working, and the
    registry logs a warning whenever it falls back, because a fallback means the doors
    are NOT sharing a record.
    """
    from pathlib import Path

    return str(Path(db_path or _DB_PATH).resolve().parent / "deposit_claims")


# ── the single-use deposit registry, shared by every door that credits a transfer ─────


def _registry_primitives() -> tuple[Any, Any, Any, Any]:
    """(claim, release, claims_dir, claim_key) — the canonical web module's when importable,
    the hub-native fallbacks otherwise. Both key a claim as sha256(chain|tx) in one directory."""
    claim = _shared_on_chain("claim_deposit")
    release = _shared_on_chain("release_deposit_claim")
    claims_dir = _shared_on_chain("deposit_claims_dir")
    claim_key = _shared_on_chain("deposit_claim_key")
    if claim is None or release is None:
        from aimarket_hub import deposit_claims as local

        return local.claim_deposit, local.release_deposit_claim, local.deposit_claims_dir, local.deposit_claim_key
    if claims_dir is None or claim_key is None:
        from aimarket_hub import deposit_claims as local

        claims_dir, claim_key = local.deposit_claims_dir, local.deposit_claim_key
    return claim, release, claims_dir, claim_key


def _hub_channel_stack() -> str:
    return str(_shared_on_chain("DEPOSIT_STACK_HUB") or "aimarket-hub")


def deposit_registry_labels(chain: str, chain_id: int | None = None) -> list[str]:
    """Every registry name one deposit on this chain is claimed under — canonical first.

    A claim keyed on the caller's label alone let one transaction be claimed once per
    label: with ``AIMARKET_DEPOSIT_RPC_URL`` every label is verified against the same node,
    so the same deposit opened a channel as "base" and another as "ethereum". Now a
    transaction is claimed under the chain the verifier reads (``eip155:<chainId>``), under
    its own label (claims written before this change carry only that, and must still
    collide), and under every configured label that names the same chain — the Factory's
    door keys on labels, and must collide too. A non-EVM chain keeps its label alone.
    """
    from aimarket_hub import deposit_verify

    label = _normalize_chain(chain)
    cid = chain_id if chain_id is not None else deposit_verify.registry_chain_id(label)
    if cid is None:
        return [label]
    labels = [f"eip155:{int(cid)}", label]
    try:
        from aimarket_hub import x402
        from aimarket_hub.config import _parse_chains

        configured = [_normalize_chain(c) for c in _parse_chains()] + [_normalize_chain(x402.chain())]
    except Exception:  # noqa: BLE001
        configured = []
    for other in configured:
        if other and other not in labels and deposit_verify.registry_chain_id(other) == int(cid):
            labels.append(other)
    return labels


def _needs_chain_id(chain: str) -> bool:
    """An overridden label is EVM by construction; not knowing its chain must fail closed."""
    label = _normalize_chain(chain)
    return bool((os.environ.get("AIMARKET_DEPOSIT_RPC_URL") or "").strip()
                or (os.environ.get(f"AIMARKET_RPC_{label.upper()}") or "").strip())


def _repair_stale_empty_claim(claims_dir: Any, claim_key: Any, label: str, tx: str,
                              fallback: str, older_than_s: float = 60.0) -> bool:
    """Remove a claim file that exists but was never written — its writer died between
    creating it and writing it, so no door ever credited it. True when one was removed."""
    try:
        d = claims_dir(fallback_dir=fallback)
        if d is None:
            return False
        path = Path(d) / f"{claim_key(label, tx)}.json"
        st = path.stat()
        if time.time() - st.st_mtime < older_than_s:
            return False
        text = path.read_text(encoding="utf-8").strip() if st.st_size else ""
        if text:
            try:
                if isinstance(json.loads(text), dict):
                    return False
            except ValueError:
                pass
        path.unlink()
        logger.error("deposit registry: removed a claim for %s under %s that was never written",
                     tx[:12], label)
        return True
    except FileNotFoundError:
        return True
    except Exception as exc:  # noqa: BLE001
        logger.error("deposit registry: could not inspect a stale claim for %s: %s", tx[:12], exc)
        return False


def claim_deposit_exclusive(
    stack: str, *, chain: str, tx_hash: str, claim_id: str, amount_cents: int,
    chain_id: int | None = None, share_within_stack: bool = False, db_path: str = "",
) -> dict[str, Any]:
    """Claim a transaction for ONE credit, across every door and every name of its chain.

    Takes the claim under each of :func:`deposit_registry_labels`; the first foreign claim
    found undoes every claim THIS call took and is returned (``already_claimed`` with the
    claim that holds it). A claim this caller already holds (same stack and claim id — a
    retry finishing) is kept; ``share_within_stack`` also accepts one by another claim of
    the same door (two top-up authorizations settled in one transaction). Fails closed.
    """
    claim, release, claims_dir, claim_key = _registry_primitives()
    fallback = _claims_fallback_dir(db_path or _ledger._db_path)
    tx = _normalize_tx_hash(tx_hash)
    if chain_id is None and _needs_chain_id(chain):
        from aimarket_hub import deposit_verify

        if deposit_verify.registry_chain_id(chain) is None:
            return {"ok": False, "error": "deposit_registry_unavailable",
                    "detail": "the deposit RPC's chain id could not be read"}
    labels = deposit_registry_labels(chain, chain_id)
    taken: list[str] = []

    def undo() -> None:
        for label in taken:
            with contextlib.suppress(Exception):
                release(chain=label, tx_hash=tx, stack=stack, claim_id=claim_id, fallback_dir=fallback)

    for label in labels:
        try:
            got = claim(chain=label, tx_hash=tx, stack=stack, claim_id=claim_id,
                        amount_cents=amount_cents, fallback_dir=fallback)
            if (not got.get("ok") and got.get("error") == "already_claimed" and not (got.get("claim") or {})
                    and _repair_stale_empty_claim(claims_dir, claim_key, label, tx, fallback)):
                got = claim(chain=label, tx_hash=tx, stack=stack, claim_id=claim_id,
                            amount_cents=amount_cents, fallback_dir=fallback)
        except Exception as exc:  # noqa: BLE001
            logger.error("deposit claim as %s raised for %s: %s", stack, tx[:12], exc)
            undo()
            return {"ok": False, "error": "deposit_registry_unavailable"}
        if got.get("ok"):
            taken.append(label)
            continue
        held = got.get("claim") or {}
        mine = held.get("stack") == stack and (share_within_stack or held.get("claim_id") == claim_id)
        if got.get("error") == "already_claimed" and mine:
            continue
        undo()
        return got
    return {"ok": True, "claim": {"stack": stack, "claim_id": claim_id, "tx_hash": tx, "labels": labels}}


def deposit_claim_holder(
    *, chain: str, tx_hash: str, chain_id: int | None = None, db_path: str = "",
) -> dict[str, Any] | None:
    """The claim that holds this transaction (``{"stack", "claim_id", ...}``), or None — READ ONLY.

    For a door that only needs to know whether another door already credited a deposit (the
    hub's deposit watcher re-examining money it could not attribute). Taking a claim to find
    out, even briefly, could refuse a real credit racing it — the operator's hand credit
    answering 409 because a probe held the transaction for a millisecond.
    """
    _claim, _release, claims_dir, claim_key = _registry_primitives()
    fallback = _claims_fallback_dir(db_path or _ledger._db_path)
    tx = _normalize_tx_hash(tx_hash)
    try:
        labels = deposit_registry_labels(chain, chain_id)
    except Exception:  # noqa: BLE001
        labels = [_normalize_chain(chain)]
    directory = claims_dir(fallback_dir=fallback)
    if directory is None:
        return None
    for label in labels:
        try:
            text = (Path(directory) / f"{claim_key(label, tx)}.json").read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            continue
        if not text:
            continue   # a writer that died before writing: nobody was credited
        try:
            held = json.loads(text)
        except ValueError:
            continue
        if isinstance(held, dict):
            return held
    return None


def release_deposit_exclusive(
    stack: str, *, chain: str, tx_hash: str, claim_id: str, chain_id: int | None = None, db_path: str = "",
) -> None:
    """Hand back every name :func:`claim_deposit_exclusive` took. Best-effort and logged."""
    _claim, release, _dir, _key = _registry_primitives()
    fallback = _claims_fallback_dir(db_path or _ledger._db_path)
    tx = _normalize_tx_hash(tx_hash)
    try:
        labels = deposit_registry_labels(chain, chain_id)
    except Exception:  # noqa: BLE001
        labels = [_normalize_chain(chain)]
    for label in labels:
        try:
            release(chain=label, tx_hash=tx, stack=stack, claim_id=claim_id, fallback_dir=fallback)
        except Exception as exc:  # noqa: BLE001
            logger.error("could not release deposit claim for %s under %s (%s) — the deposit stays "
                         "blocked until an operator clears it", tx[:12], label, exc)


def _claim_deposit_shared(
    *, chain: str, tx_hash: str, channel_id: str, amount_cents: int, db_path: str = ""
) -> dict[str, Any]:
    """Claim a channel deposit in the registry every settlement door consults. Fails closed."""
    return claim_deposit_exclusive(_hub_channel_stack(), chain=chain, tx_hash=tx_hash, claim_id=channel_id,
                                   amount_cents=amount_cents, db_path=db_path)


def claim_deposit_as(
    stack: str, *, chain: str, tx_hash: str, claim_id: str, amount_cents: int,
    chain_id: int | None = None, share_within_stack: bool = False,
) -> dict[str, Any]:
    """Claim ``tx_hash`` under another door's name — a USDC top-up (``aimarket_hub.topup``) or
    an operator crediting an on-chain payment by hand. The same registry and names as the
    channel door, so whichever door claims first keeps the transaction."""
    return claim_deposit_exclusive(stack, chain=chain, tx_hash=tx_hash, claim_id=claim_id,
                                   amount_cents=amount_cents, chain_id=chain_id,
                                   share_within_stack=share_within_stack)


def release_deposit_as(stack: str, *, chain: str, tx_hash: str, claim_id: str, chain_id: int | None = None) -> None:
    release_deposit_exclusive(stack, chain=chain, tx_hash=tx_hash, claim_id=claim_id, chain_id=chain_id)


def _release_deposit_shared(
    *, chain: str, tx_hash: str, channel_id: str, db_path: str = ""
) -> None:
    """Hand a claim back when the channel it was taken for is not created.

    Best-effort by design: a claim left behind blocks one deposit's re-use, which is
    a stuck deposit, not a double credit — so a failure here must never turn into a
    failed open. It is logged so a leak is visible.
    """
    release_deposit_exclusive(_hub_channel_stack(), chain=chain, tx_hash=tx_hash, claim_id=channel_id,
                              db_path=db_path)


def _payout_tx_shape_error(tx: str, chain: str) -> str:
    """Why ``tx`` cannot be a payout transaction id on ``chain`` — "" if it can.

    Not a chain lookup (this module never talks to an RPC) — a SHAPE check, so an
    operator attestation always points at something an auditor can actually resolve.
    Accepting any non-empty string meant "done" cleared a real depositor debt.
    """
    if _normalize_chain(chain) in _EVM_PAYOUT_CHAINS:
        body = tx[2:] if tx[:2].lower() == "0x" else ""
        if len(body) != 64 or not all(c in _HEX_DIGITS for c in body):
            return (
                "payout_tx_hash must be a 0x-prefixed 32-byte hex transaction hash "
                f"on {chain} — refusing to mark a debt paid against an unresolvable id"
            )
        return ""
    # Non-EVM (base58 Solana signatures are 86-88 chars); accept only something long
    # enough to be a real id rather than a word.
    if len(tx) < 32:
        return (
            "payout_tx_hash does not look like a transaction id — refusing to mark a "
            "debt paid against an unresolvable id"
        )
    return ""


def _admin_token() -> str:
    """The operator token, read dynamically so it is monkeypatchable (hub convention)."""
    return os.environ.get("AIMARKET_ADMIN_TOKEN", "").strip()


def _require_operator(operator_token: str, action: str) -> None:
    """Raise PermissionError unless ``operator_token`` is the configured admin token.

    The obligation surface is not merely privileged, it is the operator's LIABILITY
    LEDGER: the readers return depositor wallets, owed amounts and deposit tx hashes,
    and the writer flips a real debt to 'paid'. The HTTP routes gate it, but the
    module-level exports are importable by any in-process plugin, so gating only the
    routes would leave the export as the weak spot. Fail CLOSED: with no admin token
    configured there is nothing to authenticate against, so nobody is authorised.
    """
    expected = _admin_token()
    if not expected:
        raise PermissionError(
            f"{action} is unavailable: AIMARKET_ADMIN_TOKEN is not configured, so the "
            "operator obligation ledger cannot authenticate anyone"
        )
    if not hmac.compare_digest((operator_token or "").strip(), expected):
        raise PermissionError(f"{action} requires the operator (admin) token")


def _env_int(name: str, default: int) -> int:
    """Read a non-negative int env knob, ignoring garbage (keeps the default)."""
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        logger.warning("Ignoring non-integer %s=%r, using %d", name, raw, default)
        return default
    return value if value >= 0 else default


def _anon_opens_per_hour() -> int:
    return _env_int("AIMARKET_CHANNEL_ANON_OPENS_PER_HOUR", _DEFAULT_ANON_OPENS_PER_HOUR)


def _anon_closes_per_hour() -> int:
    return _env_int("AIMARKET_CHANNEL_ANON_CLOSES_PER_HOUR", _DEFAULT_ANON_CLOSES_PER_HOUR)


def _hold_reap_after_secs() -> int:
    return _env_int("AIMARKET_CHANNEL_HOLD_REAP_AFTER_SECS", _DEFAULT_HOLD_REAP_AFTER_SECS)


def _settlements_db_path() -> str:
    """Where `verified_settlements` (the hub index DB) lives.

    The ledger keeps its own database file, so the orphaned-hold reaper has to look
    across at the hub DB to tell an ABANDONED hold from one a live verification still
    owns. Same resolution order the hub itself uses (HubConfig.db_path).
    """
    explicit = os.environ.get("AIMARKET_VERIFY_SETTLEMENTS_DB_PATH", "").strip()
    if explicit:
        return explicit
    return os.environ.get("AIMARKET_DB_PATH", "").strip() or "data/hub.db"


def _is_evm_address(value: str) -> bool:
    # The "0x" prefix carries no checksum information, so an address written "0X…" is
    # the same address. Requiring the exact lowercase prefix made it read as an opaque
    # non-EVM handle: the owner was then denied by _wallet_matches and, on the deposit
    # path, refused as a chain with no proof-of-control scheme.
    s = (value or "").strip()
    if len(s) != 42 or s[:2].lower() != "0x":
        return False
    try:
        int(s[2:], 16)
    except ValueError:
        return False
    return True


def _wallet_matches(a: str, b: str) -> bool:
    """Wallet equality for authorization / deposit binding.

    EVM addresses are case-insensitive — the mixed case of EIP-55 is a checksum, not
    identity — so the lowercase form of an address must not read as a different (or
    unauthorized) wallet. Anything else (base58 Solana ids, opaque handles) compares
    exactly, because case IS significant there.
    """
    a = (a or "").strip()
    b = (b or "").strip()
    if _is_evm_address(a) and _is_evm_address(b):
        return a.lower() == b.lower()
    return a == b


def _dollars_to_cents(usd: float) -> int:
    return round(usd * _CENTS_PER_USD)


def _dollars_to_cents_bill(usd: float) -> int:
    """Cents to DEBIT for a positively-priced invoke.

    Rounds UP to the smallest chargeable unit so a sub-cent price (e.g. a
    $0.004 capability) still bills 1 cent instead of debiting nothing and
    serving the paid invoke for free (BILLING-001). The ``round(.., 6)`` first
    strips binary-float noise (0.35 * 100 == 34.999999999999996) so exact-cent
    prices are not pushed up a whole cent.
    """
    if usd <= 0:
        return 0
    return max(1, math.ceil(round(usd * _CENTS_PER_USD, 6)))


def _cents_to_dollars(cents: int) -> float:
    return cents / _CENTS_PER_USD


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _expiry_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + _CHANNEL_EXPIRY_SECS))


def _hash_secret(secret: str) -> str:
    return hashlib.sha256((secret or "").encode()).hexdigest()


def _parse_ts(value: Any) -> float | None:
    """Epoch seconds for a stored timestamp, or None if unparseable.

    Rows written by this module use ``%Y-%m-%dT%H:%M:%SZ``; rows written by a column
    DEFAULT use SQLite's ``%Y-%m-%d %H:%M:%S``. Both are UTC, and the reaper must be
    able to age EITHER — comparing the two formats as text silently mis-orders them
    (' ' sorts before 'T'), which would age a fresh hold out immediately.
    """
    s = str(value or "").strip()
    if len(s) < 19:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return calendar.timegm(time.strptime(s[:19], fmt))
        except ValueError:
            continue
    return None


# ── SQLite Channel Ledger ────────────────────────────────────────

def _escrow_required() -> bool:
    """True when only escrow-backed funding may open a channel.

    Read through the bridge's own config so there is ONE definition.

    Deliberately NOT `required() and enabled()`. Requiring escrow while the bridge is
    off would then leave the custodial path open — the operator asked for the strongest
    setting and silently got the weakest, which is the failure mode this whole switch
    exists to remove. With `required()` alone, that misconfiguration refuses BOTH paths
    and the hub opens no channels at all: loud, immediate, and impossible to mistake
    for working. `payment_readiness()` reports it at boot so it does not have to be
    discovered one refused open at a time.

    A missing bridge package is the one exception: there is no escrow path to require,
    and failing every open would take a hub off the air rather than make it
    non-custodial.
    """
    try:
        from aimarket_hub.escrow_bridge import config as bridge_config
    except Exception:
        return False
    return bool(bridge_config.required())


class ChannelLedger(LedgerStorageMixin, LedgerSweepsMixin, LedgerOpeningMixin, LedgerSpendingMixin):
    """Payment channel ledger — SQLite or PostgreSQL via DATABASE_URL.

    All amounts stored as integer cents. Public API accepts float USD
    and returns float USD for backward compatibility.
    """

    def __init__(self, db_path: str = "", database_url: str = ""):
        from aimarket_hub.db_backend import create_backend
        from aimarket_hub.migrations import Migrations

        self._db_path = db_path or _DB_PATH
        self._backend = create_backend(
            database_url=database_url,
            db_path=self._db_path,
        )
        self._lock = threading.Lock()
        self._rate_state: dict[str, list[float]] = {}  # wallet -> [open_timestamps]
        self._close_rate: dict[str, list[float]] = {}   # wallet -> [close_timestamps]
        self._max_channels = _DEFAULT_MAX_CHANNELS
        self._sweep_thread: threading.Thread | None = None
        self._running = False
        # The ledger owns a SEPARATE database file, so it applies only the migrations
        # that touch channel-ledger tables. `subsystem=` derives that set from the
        # registered DDL (migrations.channel_ledger_versions) instead of a hand-written
        # target_version: the old `target_version=14` + "incl. ..." comment would have
        # silently skipped every later channels migration the moment one was added.
        Migrations(self._backend).apply(subsystem="channels")
        self._start_sweep()


# ── Global instance ──────────────────────────────────────────────

_ledger = ChannelLedger()

# Master crypto switch (default OFF). Standalone read — same env/contract as the
# rest of the ecosystem. When off, payment channels are disabled entirely and
# capabilities are served free; signing/sandbox/manifests are unaffected.
_CRYPTO_DISABLED = {"error": "payment channels disabled by operator (crypto off — AIFACTORY_CRYPTO_ENABLED=0)"}


def _crypto_enabled() -> bool:
    return os.environ.get("AIFACTORY_CRYPTO_ENABLED", "0").strip().lower() in ("1", "true", "yes", "on")


# Said once, at import, so "this hub cannot take money" is in the log before the first
# customer rather than discovered from a support ticket. Placed after `_crypto_enabled`
# because `payment_readiness` reads it.
_warn_if_cannot_take_money()

def open_channel(
    deposit_usd: float,
    token: str | None = None,
    chain: str | None = None,
    wallet: str = "",
    tx_hash: str = "",
    with_secret: bool = True,
    payer_signature: str = "",
    escrow_channel_id: str = "",
) -> dict[str, Any]:
    """Open a channel from the public/HTTP entry point.

    `payer_signature` must be forwarded by the transport for on-chain deposits — it is
    what stops a front-runner from claiming a stranger's (public) deposit tx and walking
    away with the channel_secret. See ChannelLedger.open / the module docstring.
    """
    if not _crypto_enabled():
        return dict(_CRYPTO_DISABLED)
    # Public/HTTP entry point → secure-by-default: mint a debit secret so the invoke path
    # (X-Payment-Channel) can't be drained with just a leaked channel id.
    return _ledger.open(
        deposit_usd=deposit_usd,
        escrow_channel_id=escrow_channel_id,
        token=token or _DEFAULT_TOKEN,
        chain=chain or _DEFAULT_CHAIN,
        wallet=wallet,
        tx_hash=tx_hash,
        with_secret=with_secret,
        payer_signature=payer_signature,
    )


def close_channel(
    channel_id: str, settle_tx_hash: str = "", wallet: str = "", secret: str = ""
) -> dict[str, Any]:
    if not _crypto_enabled():
        return dict(_CRYPTO_DISABLED)
    return _ledger.close(
        channel_id, settle_tx_hash=settle_tx_hash, wallet=wallet, secret=secret
    )


def debit_channel(
    channel_id: str, amount_usd: float, receipt_id: str = "",
    requester_wallet: str = "", secret: str = "",
) -> dict[str, Any]:
    if not _crypto_enabled():
        return dict(_CRYPTO_DISABLED)
    return _ledger.debit(
        channel_id, amount_usd, receipt_id=receipt_id,
        requester_wallet=requester_wallet, secret=secret,
    )


def refund_channel(
    channel_id: str, amount_usd: float,
    requester_wallet: str = "", secret: str = "",
) -> dict[str, Any]:
    """Reverse a recorded debit (in-ledger only, no funds move).

    Crypto-gated like debit: when the operator has payment channels switched off there
    is no ledger to correct. Authorization is delegated to the primitive (channel secret
    / owner wallet) — the export used to be an unauthenticated, ungated balance writer
    whose only limit was the deposit cap. There is no HTTP route for it: the safety-abort
    path builds its own receipt (safety_gate.refund_channel) and internal callers hold
    the channel secret.
    """
    if not _crypto_enabled():
        return dict(_CRYPTO_DISABLED)
    return _ledger.refund(
        channel_id, amount_usd,
        requester_wallet=requester_wallet, secret=secret,
    )


def hold_channel(
    channel_id: str, amount_usd: float, receipt_id: str,
    requester_wallet: str = "", secret: str = "",
) -> dict[str, Any]:
    """Reserve funds pending a Pay-on-Verified verdict (crypto-gated like debit)."""
    if not _crypto_enabled():
        return dict(_CRYPTO_DISABLED)
    return _ledger.hold(
        channel_id, amount_usd, receipt_id=receipt_id,
        requester_wallet=requester_wallet, secret=secret,
    )


def capture_hold(receipt_id: str) -> dict[str, Any]:
    """Capture a verified hold. NOT crypto-gated: an in-flight hold must resolve
    even if the operator flips the master switch off mid-settlement (mirrors
    refund_channel, which is likewise ungated)."""
    return _ledger.capture_hold(receipt_id)


def release_hold(receipt_id: str) -> dict[str, Any]:
    """Release a failed-verdict hold back to the channel balance (ungated, see capture_hold)."""
    return _ledger.release_hold(receipt_id)


def hold_state(receipt_id: str) -> str:
    """Read-only status of one hold ("" when there is none). Ungated like capture_hold."""
    return _ledger.hold_state(receipt_id)


def channel_secret_error(channel_id: str, secret: str) -> str:
    """"" when `secret` authenticates the channel's owner; see ChannelLedger.secret_error."""
    return _ledger.secret_error(channel_id, secret)


def channel_stats() -> dict[str, Any]:
    return _ledger.stats()


def reap_stale_holds(max_age_secs: float | None = None) -> dict[str, Any]:
    """Release holds abandoned by a crash between the hold and its settlement row.

    Ungated like capture_hold/release_hold: an in-flight hold must be resolvable even if
    the operator flips the master switch off, otherwise the buyer's balance stays frozen.
    """
    return _ledger.reap_stale_holds(max_age_secs)


def channel_obligations(
    status: str = "owed", limit: int = 500, *, operator_token: str = "",
) -> list[dict[str, Any]]:
    """Payout obligations the operator owes depositors — OPERATOR ONLY.

    A closed/expired channel's unspent remainder is recorded here rather than
    transferred (see the module docstring); nothing in this module can pay them.
    Each row carries the depositor's wallet, what they are owed and the deposit tx
    hash, which is a map of who is holding money with the platform — so the export
    demands the operator token and raises PermissionError otherwise.
    """
    _require_operator(operator_token, "listing payout obligations")
    return _ledger.obligations(status=status, limit=limit)


def channel_obligations_total(
    status: str = "owed", *, operator_token: str = "",
) -> dict[str, Any]:
    """Count + USD total of payout obligations — OPERATOR ONLY (see channel_obligations).

    The aggregate alone leaks how much customer money the platform is sitting on, so
    it is gated with the detail view rather than left as the way around it. The
    unauthenticated summary lives on /stats/live, which reports the same total openly
    and on purpose (solvency transparency) without naming any depositor.
    """
    _require_operator(operator_token, "reading the payout obligation total")
    return _ledger.obligations_total(status=status)


def mark_obligation_paid(
    channel_id: str, payout_tx_hash: str, *, operator_token: str = "",
) -> dict[str, Any]:
    """Record an out-of-band operator payout against an obligation (attestation only).

    OPERATOR ONLY, and crypto-gated. This writes off a real debt to a real depositor
    on nothing but the operator's word; before this gate any in-process caller could
    clear the whole liability ledger. The crypto gate is deliberate too: with the
    master switch off the platform is asserting there is no payment rail at all, so
    an on-chain payout hash cannot be honest evidence — flip AIFACTORY_CRYPTO_ENABLED
    back on to settle debts recorded while it was on.
    """
    _require_operator(operator_token, "marking an obligation paid")
    if not _crypto_enabled():
        return dict(_CRYPTO_DISABLED)
    return _ledger.mark_obligation_paid(channel_id, payout_tx_hash)


def wallet_recorded_spend_usd(wallet: str) -> float | None:
    """USD the ledger has actually debited for a wallet, or None if it owns no channels.

    Grounds self-bond slashing in hub-recorded settlement: a claimed overspend can only
    be honoured up to what the hub itself observed, so a forged observed_spend cannot
    drain a bond. Read-only, so it is NOT gated by the crypto master switch.
    """
    return _ledger.recorded_spend_usd(wallet)


def channel_balance(channel_id: str) -> float | None:
    """Current USD balance of an open channel, or None if it is unknown.

    Used for a pre-authorization check before running a billable capability, so a
    depleted channel doesn't get paid upstream work done for free (the debit
    happens only after execution).
    """
    ch = _ledger.get(channel_id)
    if not ch or ch.get("status") != "open":
        return None
    return float(ch.get("balance_usd") or 0.0)


def channel_escrow_binding(channel_id: str) -> str:
    """Escrow channel backing a ledger channel, or "" when it was transfer-funded.

    Read-only, so it is NOT gated by the crypto master switch: the invoke path needs it to
    decide whether a DebitAuthorization is even applicable to this channel.
    """
    return _ledger.escrow_channel_for(channel_id)


def channel_payer(channel_id: str) -> str:
    """The wallet that proved control of this channel's deposit when it was opened, or "".

    That address is the one ``_recover_payer_address`` recovered from the opener's signature
    (or the escrow depositor's, on a proven escrow open). A stub, demo-credit or unproven
    open has none, whatever ``wallet`` it stored. Read-only, so not gated by the crypto
    master switch, like ``channel_escrow_binding``.
    """
    try:
        return _ledger.proven_payer_for((channel_id or "").strip())
    except Exception as exc:  # noqa: BLE001 — a lookup fault means "no payer", not a failed call
        logger.error("channel payer lookup failed: %s", exc)
        return ""
