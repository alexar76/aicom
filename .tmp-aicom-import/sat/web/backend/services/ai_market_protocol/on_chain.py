"""On-chain payment verification helpers for AI Market Protocol.

Read this before adding a call site — confusing the two levels of API below has
already produced the same money bug three times.

* :func:`verify_tx_transfer` is the safe default. The caller MUST say what it
  expects about the *payer* (``expect_sender``) and MAY name a ``recipient``
  other than the platform settlement wallet, which is what makes it possible to
  verify an OUTBOUND refund to a customer instead of only inbound payments.
  It returns the on-chain sender so a credit can be bound to the wallet that
  actually paid.
* :func:`verify_tx_payment` is LEGACY: recipient is always the platform wallet
  and the payer is not checked at all. It only answers "did *somebody* pay the
  platform?" — never enough to credit anybody, because whoever submits the hash
  first can claim a stranger's inbound transfer. It is kept because callers
  outside this package (aimarket-hub) still use it; do not add new call sites.

This module also owns the two definitions that MUST be identical in both channel
stacks: the canonical payer-proof challenge (one signature, both doors) and the
shared single-use deposit registry (one deposit, one channel, system-wide). Both
blocks below explain why they live here rather than in either stack.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from web.backend.services.ai_market_protocol.config import demo_payment_bypass

if TYPE_CHECKING:
    from collections.abc import Iterable

logger = logging.getLogger(__name__)


def _payment_api() -> Any:
    """The RPC-facing payment module, imported on demand.

    Deliberately NOT a module-level import: ``web.backend.api.payment`` drags in the
    whole web application stack (passlib, the hub bridge, …), which made this module
    unimportable from a standalone aimarket-hub deployment. The canonical payer-proof
    challenge below lives here precisely so both stacks share one definition, so it
    must be importable without a web app behind it — otherwise the hub silently
    degrades to "cannot evaluate payer proofs" and refuses every real channel open.
    """
    from web.backend.api import payment as payment_api

    return payment_api


# ``expect_sender`` sentinels — see verify_tx_transfer.
#
# These are deliberately NOT strings. Call sites pass request-supplied data here
# (invoke.py forwards the client's ``X-Payment.from``), and a magic-string
# sentinel is a value the attacker can simply type: sending ``from:
# "<any-sender>"`` would have turned the mandatory payer expectation back into
# "any payer" and bypassed the sender_unresolved refusal. As objects they are
# unforgeable over the wire — an attacker-supplied lookalike string falls through
# to the address branch and fails closed as sender_mismatch.
class _SenderExpectation:
    __slots__ = ("_name",)

    def __init__(self, name: str) -> None:
        self._name = name

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return self._name


ANY_SENDER = _SenderExpectation("<any-sender>")
"""Explicit opt-out: the payer is irrelevant. Never valid when crediting value."""

BIND_SENDER = _SenderExpectation("<bind-sender>")
"""The payer is unknown up front but the caller WILL bind its credit to the
returned ``from`` address; verification fails closed when no sender can be
established (an unbound credit is exactly the hole this closes)."""

_TRUTHY = ("1", "true", "yes", "on")

# EVM chain prefixes we can verify an EIP-191 payer proof for. Non-EVM chains
# (solana) use a different signing scheme that is not implemented here, so a
# required proof on those chains must fail closed rather than be skipped.
_EVM_CHAIN_PREFIXES = ("base", "eth", "arb", "opt", "polygon", "bsc", "avax")


def normalize_tx_hash(tx_hash: str, *, chain: str) -> str:
    tx = (tx_hash or "").strip()
    if chain == "solana":
        return tx
    return tx if tx.startswith("0x") else f"0x{tx}"


def is_demo_tx(tx_hash: str) -> bool:
    """Whether this hash is a dev placeholder with no chain behind it."""
    return (tx_hash or "").strip().startswith(("demo-", "0xdemo"))


def is_evm_chain(chain: str) -> bool:
    c = (chain or "").strip().lower()
    return bool(c) and c.startswith(_EVM_CHAIN_PREFIXES)


def platform_recipient(chain: str) -> str:
    """Settlement wallet the platform expects INBOUND payments at.

    Empty when that chain has no wallet configured (the module defaults are
    ``""`` until ``load_wallets()`` runs, and an EVM-only deployment has no
    Solana address at all). Callers must treat "" as "cannot verify", never as
    "no constraint".
    """
    try:
        return (_payment_api()._get_address_for_chain(chain) or "").strip()
    except Exception as exc:
        # Wallet config that cannot be read is a refusal, not a crash.
        logger.warning("no settlement wallet resolvable for chain %s: %s", chain, exc)
        return ""


def refund_payer_wallets(chain: str) -> tuple[str, ...]:
    """Wallets a refund/settlement payout is allowed to originate FROM.

    Defaults to the platform settlement wallet (refunds normally go back out of
    the wallet the deposit landed in). Operators who pay refunds from a separate
    hot wallet list it in ``AIFACTORY_AI_MARKET_REFUND_WALLETS`` (comma
    separated); an unknown payer must not be accepted as proof that the platform
    paid, otherwise any inbound transfer to the customer could be used to mark a
    refund obligation settled that the platform never funded.
    """
    wallets: list[str] = []
    settlement = platform_recipient(chain)
    if settlement:
        wallets.append(settlement)
    extra = os.environ.get("AIFACTORY_AI_MARKET_REFUND_WALLETS", "")
    for part in extra.split(","):
        addr = part.strip()
        if addr and addr.lower() not in {w.lower() for w in wallets}:
            wallets.append(addr)
    return tuple(wallets)


def require_payer_proof() -> bool:
    """Whether a claimed payer must PROVE control of the paying wallet.

    Matching only recipient+amount lets a mempool watcher submit a stranger's
    transaction hash and have the value credited to themselves. An EIP-191
    signature over a tx-bound challenge is the only thing that closes that, so it
    is required in production. Outside production the bind-to-sender path (which
    at least fixes the refund destination and records who really paid) is
    allowed, because the HTTP surface cannot carry a signature yet.
    ``AIFACTORY_AI_MARKET_ALLOW_UNPROVEN_PAYER=1`` is the operator's explicit,
    logged opt-out; ``AIFACTORY_AI_MARKET_REQUIRE_PAYER_PROOF=1`` forces it on.
    """
    if os.environ.get("AIFACTORY_AI_MARKET_REQUIRE_PAYER_PROOF", "").strip().lower() in _TRUTHY:
        return True
    if os.environ.get("AIFACTORY_AI_MARKET_ALLOW_UNPROVEN_PAYER", "").strip().lower() in _TRUTHY:
        logger.warning(
            "AIFACTORY_AI_MARKET_ALLOW_UNPROVEN_PAYER=1 — crediting on-chain payments "
            "without proof that the caller controls the paying wallet"
        )
        return False
    return _is_production_env()


def _is_production_env() -> bool:
    """Production marker, mirroring config._is_production_env + prod_startup_guard."""
    try:
        from security.prod_startup_guard import is_production_mode

        if is_production_mode():
            return True
    except Exception:
        pass
    if os.environ.get("AIFACTORY_ENV", "").strip().lower() in ("production", "prod", "live"):
        return True
    return any(
        os.environ.get(key, "").strip().lower() in _TRUTHY
        for key in ("AIFACTORY_PROD", "AIFACTORY_PRODUCTION")
    )


def payer_proof_message(*, purpose: str, subject: str, tx_hash: str, chain: str) -> str:
    """EIP-191 challenge binding one claimant (``subject``) to one payment tx.

    LEGACY, kept for the one-off invoke payment proof (``invoke.py``), which binds a
    single transfer to a single call and needs no amount field beyond the price the
    verifier already checked. Channel opens use :func:`channel_open_proof_message`
    — see the CANONICAL PAYER PROOF block below for why they had to diverge from
    this shape and then be re-unified.
    """
    return f"AIMarket {purpose}\nsubject:{subject}\ntx:{tx_hash}\nchain:{chain}"


def recover_payer(
    *, purpose: str, subject: str, tx_hash: str, chain: str, signature: str
) -> str | None:
    """Recover the address that signed the LEGACY payer-proof challenge, or None."""
    if not (signature or "").strip():
        return None
    try:
        from eth_account import Account
        from eth_account.messages import encode_defunct

        message = payer_proof_message(
            purpose=purpose, subject=subject, tx_hash=tx_hash, chain=chain
        )
        return Account.recover_message(encode_defunct(text=message), signature=signature)
    except Exception:
        # A malformed signature is a failed proof, not a server error.
        return None


# ── CANONICAL PAYER PROOF (channel opens) ────────────────────────────────────
#
# ONE message, defined here and imported by every implementation, because the two
# channel stacks independently invented incompatible challenges for the same
# concept: aimarket-hub signed `purpose="channel-open", subject=<payer>` with its
# own tx normalisation, while this package signed `purpose="channel deposit",
# subject=<customer_id>` with another. A signature valid for one was invalid for
# the other, so no SDK could target both, and the two normalisations disagreed on
# whether `0xABC` and `0xabc` were the same deposit.
#
# Preimage fields, and why each one is in it:
#   line 1  domain + version   Domain separation. A signature collected for any
#                              other AIMarket challenge (UNI top-up, invoke
#                              payment) must never validate here, and the version
#                              lets the preimage change without silently accepting
#                              both shapes.
#   purpose                    Scopes the proof to the operation. Today only
#                              "channel-open"; the slot exists so the next
#                              value-granting operation cannot reuse this one's
#                              signatures.
#   chain                      The SAME tx hash can exist on several EVM chains
#                              (identical calldata replayed). Without it a proof
#                              for a $1 deposit on a cheap testnet-like chain
#                              would authorise the identically-hashed mainnet tx.
#   tx                         Binds the proof to exactly one deposit, so it
#                              cannot be reused for the payer's next transfer.
#   payer                      Binds the proof to the wallet the credit is granted
#                              to. Recovery must return THIS address; a signature
#                              that recovers to anyone else proves control of the
#                              wrong key.
#   amount_cents               Binds the proof to the credited amount, in the
#                              ledger's own integer unit (both stacks bill in
#                              cents, so signing floats would let "5.0" and "5.00"
#                              disagree). Stops a proof gathered for a small
#                              deposit being presented against a larger claim if a
#                              verifier is ever relaxed about the amount.
#
# NOT in the preimage: the platform account (customer_id) the channel is opened
# under. It was in this package's old challenge, but keeping it makes the message
# unproducible by the hub, which has no accounts — that is precisely the drift
# being removed. The residual is narrow and bounded: a leaked signature lets
# another account SPEND the deposit, but never redirects it, because the refund
# destination is `deposit_wallet` — the verified on-chain payer — and a deposit tx
# funds exactly one channel.

PAYER_PROOF_DOMAIN = "AIMarket-Payer-Proof"
PAYER_PROOF_VERSION = 1
PAYER_PROOF_CHANNEL_OPEN = "channel-open"

_HEX_DIGITS = frozenset("0123456789abcdefABCDEF")


def canonical_proof_chain(chain: str) -> str:
    """Canonical chain id for a payer proof (chain names are ASCII, case-free)."""
    return (chain or "").strip().lower()


def canonical_proof_tx_hash(tx_hash: str) -> str:
    """Canonical transaction id for a payer proof.

    EVM hashes are hex and case-insensitive at the JSON-RPC layer, so ``0xABC…``
    and ``0xabc…`` name the SAME transaction and must produce the SAME challenge —
    otherwise a client that signs the checksummed rendering of its own hash is
    refused. Anything that is not hex (a base58 Solana signature) is
    case-SIGNIFICANT and is left byte-exact.

    The ``0x`` prefix is normalised in as well, not just lowercased. Only one of the
    two stacks strips/adds it before building the challenge (this package runs
    :func:`normalize_tx_hash` first, aimarket-hub passes the raw request value), so
    treating a bare hex hash as opaque made the two produce DIFFERENT preimages for
    the same deposit — the exact drift this canonical message exists to remove.
    """
    tx = (tx_hash or "").strip()
    body = tx[2:] if tx[:2].lower() == "0x" else tx
    if body and all(c in _HEX_DIGITS for c in body):
        return "0x" + body.lower()
    return tx


def canonical_proof_payer(payer: str) -> str:
    """Canonical payer address for a payer proof.

    EIP-55 mixed case is a checksum, not identity, so an EVM address is lowercased.
    Non-EVM handles keep their case (base58 is case-significant).
    """
    addr = (payer or "").strip()
    if len(addr) == 42 and addr[:2].lower() == "0x":
        body = addr[2:]
        if all(c in _HEX_DIGITS for c in body):
            return "0x" + body.lower()
    return addr


def canonical_proof_amount_cents(amount_usd: Any) -> int:
    """Deposit amount as the integer cents both ledgers actually bill in.

    Returns -1 for an unusable amount so the challenge is still deterministic and
    a proof over it can never match a real deposit (both ledgers refuse a
    non-finite / non-positive deposit long before this point).
    """
    try:
        value = float(amount_usd)
    except (TypeError, ValueError):
        return -1
    if value != value or value in (float("inf"), float("-inf")):
        return -1
    return int(round(value * 100))


def channel_open_proof_message(
    *, chain: str, tx_hash: str, payer: str, amount_usd: Any
) -> str:
    """The exact EIP-191 text the PAYING wallet signs to claim a channel deposit.

    Personal-sign (EIP-191) on purpose: every ordinary wallet can produce it with
    no typed-data support, which is what makes this usable from an SDK, a browser
    extension and a hardware wallet alike.
    """
    return (
        f"{PAYER_PROOF_DOMAIN}/v{PAYER_PROOF_VERSION}\n"
        f"purpose:{PAYER_PROOF_CHANNEL_OPEN}\n"
        f"chain:{canonical_proof_chain(chain)}\n"
        f"tx:{canonical_proof_tx_hash(tx_hash)}\n"
        f"payer:{canonical_proof_payer(payer)}\n"
        f"amount_cents:{canonical_proof_amount_cents(amount_usd)}"
    )


def recover_channel_open_payer(
    *, chain: str, tx_hash: str, payer: str, amount_usd: Any, signature: str
) -> str | None:
    """Address that signed the canonical channel-open challenge, or None.

    None on ANY failure — no signature, malformed signature, eth_account missing.
    Callers treat None as "unproven" and refuse to credit, so a deployment that
    cannot evaluate the proof never grants one.
    """
    if not (signature or "").strip():
        return None
    try:
        from eth_account import Account
        from eth_account.messages import encode_defunct

        message = channel_open_proof_message(
            chain=chain, tx_hash=tx_hash, payer=payer, amount_usd=amount_usd
        )
        return Account.recover_message(
            encode_defunct(text=message), signature=signature.strip()
        )
    except Exception:
        # A malformed signature is a failed proof, not a server error.
        return None


# ── SHARED SINGLE-USE DEPOSIT REGISTRY (cross-stack) ─────────────────────────
#
# The invariant: ONE on-chain deposit funds AT MOST ONE payment channel in the
# WHOLE system.
#
# Two channel doors credit balance against the same kind of deposit — aimarket-hub
# (`consumed_deposits`, SQLite) and this package (`channels.json` + `payment_txs
# .json`). Each enforced single-use over its OWN store only, so one real transfer
# plus one signature bought a funded channel at each door: $5 paid, $10 credited.
#
# Why not an audience/stack tag in the signed preimage
#     It does not close this. The attacker is the PAYER: they hold the key, so they
#     simply sign one message per audience and present each at its own door. A tag
#     would also re-split the "one signature, both doors" property the canonical
#     challenge above exists to provide, for no security gain. Rejected.
#
# Why a shared consumption record
#     The only thing that can make a claim exclusive across two independent ledgers
#     is a record both of them consult and write BEFORE crediting. That is this
#     registry: one file per deposit, named by the canonical (chain, tx) key, created
#     with O_CREAT|O_EXCL — the create either wins or raises FileExistsError, which is
#     atomic across threads AND processes on POSIX (and across the two stacks, which
#     are separate processes). No lock file, no read-modify-write window.
#
# Where it lives, and the operator's obligation
#     ``AIMARKET_DEPOSIT_CLAIMS_DIR`` when set, else
#     ``$AIFACTORY_DATA_ROOT/state/ai_market/deposit_claims`` (same root this
#     package already keeps ``channels.json`` under, so for the web stack the
#     registry is exactly as available as its own ledger).
#     The two stacks are deployed as SEPARATE services with SEPARATE volumes
#     (docker-compose.core.yml gives the hub its own ``hub_data``), so a filesystem
#     registry is only genuinely shared when the operator makes it so: mount one
#     path into both containers and point ``AIMARKET_DEPOSIT_CLAIMS_DIR`` at it.
#     ``deposit_registry_status()`` reports what a running process actually resolved,
#     and callers log a WARNING whenever they had to fall back to a stack-local
#     directory, so "the doors are not sharing a registry" is visible rather than
#     silent. A caller that can reach NO usable directory gets
#     ``deposit_registry_unavailable`` and must refuse to credit (fail closed).

DEPOSIT_CLAIMS_DIR_ENV = "AIMARKET_DEPOSIT_CLAIMS_DIR"
DEPOSIT_STACK_HUB = "aimarket-hub"
DEPOSIT_STACK_WEB_V1 = "web-ai-market-v1"

_DEFAULT_DATA_ROOT = "/app/data"   # mirrors core.paths.data_root() without importing it
_SHARED_CLAIMS_SUBPATH = ("state", "ai_market", "deposit_claims")

# Directories already probed, and the ones we have warned about (warn once each, not
# once per deposit — this runs on every funded open).
_claims_dir_lock = threading.Lock()
_warned_fallback_dirs: set[str] = set()


def _shared_claims_dir_default() -> Path:
    root = os.environ.get("AIFACTORY_DATA_ROOT", "").strip() or _DEFAULT_DATA_ROOT
    return Path(root).joinpath(*_SHARED_CLAIMS_SUBPATH)


def _usable_dir(path: Path) -> Path | None:
    """``path`` as a writable directory, or None. Never raises."""
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None
    return path if os.access(path, os.W_OK | os.X_OK) else None


def deposit_claims_dir(*, fallback_dir: str | Path | None = None) -> Path | None:
    """Directory holding the shared single-use deposit claims, or None.

    ``fallback_dir`` is a STACK-LOCAL last resort for a deployment where the shared
    root is not writable (a standalone hub whose only writable state is its ledger
    directory). Using it still enforces single-use within that stack — it just cannot
    see the other door — so it is logged once, loudly. An explicitly configured
    ``AIMARKET_DEPOSIT_CLAIMS_DIR`` is never silently replaced by the fallback: if the
    operator named a directory and it is unusable, that is a refusal, not a downgrade.
    """
    configured = os.environ.get(DEPOSIT_CLAIMS_DIR_ENV, "").strip()
    if configured:
        got = _usable_dir(Path(configured))
        if got is None:
            logger.error(
                "%s=%s is not a writable directory — refusing to credit deposits "
                "that cannot be claimed", DEPOSIT_CLAIMS_DIR_ENV, configured,
            )
        return got

    shared = _usable_dir(_shared_claims_dir_default())
    if shared is not None:
        return shared

    if fallback_dir is None:
        logger.error(
            "shared deposit registry unusable at %s and no local fallback offered — "
            "set %s to a directory both channel stacks can write",
            _shared_claims_dir_default(), DEPOSIT_CLAIMS_DIR_ENV,
        )
        return None

    local = _usable_dir(Path(fallback_dir))
    if local is None:
        return None
    key = str(local)
    with _claims_dir_lock:
        first = key not in _warned_fallback_dirs
        _warned_fallback_dirs.add(key)
    if first:
        logger.warning(
            "shared deposit registry unusable at %s — falling back to %s. Deposit "
            "single-use is enforced for THIS stack only; set %s to a directory shared "
            "with the other channel stack to make it system-wide",
            _shared_claims_dir_default(), local, DEPOSIT_CLAIMS_DIR_ENV,
        )
    return local


def deposit_registry_status(*, fallback_dir: str | Path | None = None) -> dict[str, Any]:
    """What this process resolved for the shared registry (diagnostics/tests)."""
    resolved = deposit_claims_dir(fallback_dir=fallback_dir)
    shared = _shared_claims_dir_default()
    configured = os.environ.get(DEPOSIT_CLAIMS_DIR_ENV, "").strip()
    return {
        "available": resolved is not None,
        "dir": str(resolved) if resolved else "",
        "configured": bool(configured),
        "shared": bool(resolved) and (bool(configured) or str(resolved) == str(shared)),
    }


def deposit_claim_key(chain: str, tx_hash: str) -> str:
    """Canonical, collision-free file name for one deposit's claim.

    Hashed rather than used verbatim because a tx id is attacker-supplied and goes
    into a path: base58 ids are not path-safe, and no ``../`` can survive a sha256.
    The canonicalisation is the SAME one the payer proof uses, so `0xABC` / `0xabc`
    (and `Base` / `base`) are one deposit here too.
    """
    canonical = f"{canonical_proof_chain(chain)}|{canonical_proof_tx_hash(tx_hash)}"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _read_claim(path: Path) -> dict[str, Any] | None:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # A crash between create and write leaves an empty file. The deposit is still
        # claimed (the name is what makes it exclusive) — we just cannot say by whom.
        return None
    return data if isinstance(data, dict) else None


def deposit_claim(
    chain: str, tx_hash: str, *, fallback_dir: str | Path | None = None
) -> dict[str, Any] | None:
    """The existing claim on this deposit, or None if it is unclaimed/unreadable."""
    d = deposit_claims_dir(fallback_dir=fallback_dir)
    if d is None:
        return None
    return _read_claim(d / f"{deposit_claim_key(chain, tx_hash)}.json")


def claim_deposit(
    *,
    chain: str,
    tx_hash: str,
    stack: str,
    claim_id: str,
    amount_cents: int = 0,
    fallback_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Claim a deposit for exactly one channel, system-wide. Fails closed.

    Returns ``{"ok": True, "claim": {...}, "dir": ...}`` for the single winner, and
    ``{"ok": False, "error": "already_claimed"|"deposit_registry_unavailable", ...}``
    for everybody else. The caller MUST NOT credit anything unless ``ok`` is True, and
    must :func:`release_deposit_claim` if it then fails to create the channel.

    Demo/placeholder hashes are NOT claimed — they name no transaction, so they carry
    nothing to replay and are reused freely in local flows. The caller decides that
    (via :func:`is_demo_tx`); a demo hash reaching here would be claimed like any
    other and would break the dev loop, so callers check first.
    """
    d = deposit_claims_dir(fallback_dir=fallback_dir)
    if d is None:
        return {"ok": False, "error": "deposit_registry_unavailable"}
    path = d / f"{deposit_claim_key(chain, tx_hash)}.json"
    record = {
        "chain": canonical_proof_chain(chain),
        "tx_hash": canonical_proof_tx_hash(tx_hash),
        "stack": stack,
        "claim_id": claim_id,
        "amount_cents": int(amount_cents or 0),
        "claimed_at": time.time(),
    }
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        return {"ok": False, "error": "already_claimed", "claim": _read_claim(path)}
    except OSError as exc:
        logger.error("deposit claim registry write failed at %s: %s", path, exc)
        return {"ok": False, "error": "deposit_registry_unavailable"}
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(record, fh, sort_keys=True)
            fh.flush()
            os.fsync(fh.fileno())
    except OSError as exc:
        # The name already reserves the deposit; a body we could not write would make
        # the claim unattributable and unreleasable, so drop it and refuse.
        logger.error("deposit claim registry write failed at %s: %s", path, exc)
        try:
            path.unlink()
        except OSError:
            pass
        return {"ok": False, "error": "deposit_registry_unavailable"}
    return {"ok": True, "claim": record, "dir": str(d)}


def release_deposit_claim(
    *,
    chain: str,
    tx_hash: str,
    stack: str,
    claim_id: str,
    fallback_dir: str | Path | None = None,
) -> bool:
    """Give a claim back when the channel it was taken for was never created.

    ONLY the holder can release: the stored ``stack``/``claim_id`` must match, so a
    loser of the race can never free the winner's claim and re-fund the deposit. An
    unattributable claim (empty/corrupt body) is never released either — leaving a
    deposit unusable is recoverable by the operator, crediting it twice is not.
    """
    d = deposit_claims_dir(fallback_dir=fallback_dir)
    if d is None:
        return False
    path = d / f"{deposit_claim_key(chain, tx_hash)}.json"
    held = _read_claim(path)
    if not held or held.get("stack") != stack or held.get("claim_id") != claim_id:
        return False
    try:
        path.unlink()
    except OSError:
        return False
    return True


def _expected_senders(
    expect_sender: _SenderExpectation | str | Iterable[str],
) -> tuple[Any, frozenset[str]]:
    """Normalize ``expect_sender`` into (mode, lowercased address set)."""
    if isinstance(expect_sender, _SenderExpectation):
        return expect_sender, frozenset()
    if isinstance(expect_sender, str):
        candidates: list[str] = [expect_sender]
    else:
        candidates = list(expect_sender or [])
    cleaned = frozenset(a.strip().lower() for a in candidates if (a or "").strip())
    if not cleaned:
        # Fail closed on a programming error rather than silently degrading to
        # "any sender" — that degradation is the bug this parameter exists for.
        raise ValueError(
            "expect_sender must be ANY_SENDER, BIND_SENDER, or at least one address"
        )
    return "addresses", cleaned


def _result(
    *,
    verified: bool,
    sender: str | None = None,
    to: str = "",
    amount: float | None = None,
    demo: bool = False,
    error: str = "",
) -> dict[str, Any]:
    return {
        "verified": verified,
        "from": sender,
        "to": to,
        "amount": amount,
        "demo": demo,
        "error": error,
    }


def verify_tx_transfer(
    *,
    tx_hash: str,
    amount_usd: float,
    chain: str,
    token: str,
    expect_sender: _SenderExpectation | str | Iterable[str],
    recipient: str | None = None,
) -> dict[str, Any]:
    """Verify that ``tx_hash`` transferred ``amount_usd`` of ``token`` to ``recipient``.

    ``recipient`` defaults to the platform settlement wallet (inbound payment);
    pass a customer wallet to verify an OUTBOUND refund/settlement instead.

    ``expect_sender`` is mandatory and must be one of:
      * :data:`BIND_SENDER` — require a resolvable payer and return it, so the
        caller can bind the credit to the wallet that actually paid;
      * one or more addresses — require the payer to be one of them;
      * :data:`ANY_SENDER` — explicitly do not care (never for credits).

    The two sentinels are objects, not strings, so request data forwarded into
    this parameter can never impersonate them: a caller-supplied
    ``"<any-sender>"`` is treated as an address and fails as ``sender_mismatch``.

    Returns ``{"verified", "from", "to", "amount", "demo", "error"}``. ``demo`` is
    True only for dev placeholder hashes, where there is no chain and therefore
    no sender: a caller that must bind a credit checks that flag instead of
    treating ``from is None`` as success.
    """
    from core.crypto_config import crypto_enabled

    mode, senders = _expected_senders(expect_sender)
    tx = (tx_hash or "").strip()
    chain = (chain or "").strip().lower()
    token = (token or "").strip().upper()

    # Crypto OFF (default): there is no external chain to verify against — never
    # contact an RPC. Callers must not rely on on-chain payment when crypto is off
    # (the invoke path settles via UNI instead); a verification request here fails.
    if not crypto_enabled():
        return _result(verified=False, error="crypto_disabled")

    if demo_payment_bypass() and is_demo_tx(tx):
        return _result(
            verified=True, to=(recipient or "").strip(), amount=amount_usd, demo=True
        )

    to = (recipient or "").strip() or platform_recipient(chain)
    if not to:
        return _result(verified=False, error="recipient_not_configured")

    try:
        if chain == "solana":
            raw = _payment_api()._verify_solana_transaction(
                tx_hash=tx,
                expected_recipient=to,
                expected_amount=amount_usd,
                expected_token=token,
            )
        else:
            raw = _payment_api()._verify_evm_transaction(
                chain=chain,
                tx_hash=tx,
                expected_recipient=to,
                expected_amount=amount_usd,
                expected_token=token,
            )
    except Exception as exc:
        # A malformed address/hash or an RPC blow-up must never read as "verified";
        # log it and refuse (money gates fail closed on ambiguity).
        logger.warning("on-chain verification raised for %s on %s: %s", tx[:14], chain, exc)
        return _result(verified=False, to=to, error="verifier_error")

    if not raw.get("verified"):
        return _result(verified=False, to=to, error=str(raw.get("error") or "not_verified"))

    sender = (str(raw.get("from") or "")).strip() or None
    amount = raw.get("amount")
    if mode == BIND_SENDER and not sender:
        # A verified transfer whose payer the chain would not tell us cannot be
        # bound to anybody — refuse instead of crediting an unbound deposit.
        return _result(verified=False, to=to, amount=amount, error="sender_unresolved")
    if mode == "addresses":
        if not sender:
            return _result(verified=False, to=to, amount=amount, error="sender_unresolved")
        if sender.lower() not in senders:
            return _result(verified=False, sender=sender, to=to, amount=amount, error="sender_mismatch")

    return _result(verified=True, sender=sender, to=to, amount=amount)


def verify_refund_transfer(
    *, tx_hash: str, amount_usd: float, chain: str, token: str, destination: str
) -> dict[str, Any]:
    """Verify an OUTBOUND settlement: the platform paid ``destination``.

    This is the direction a channel refund actually travels. Verifying it with
    the inbound helper (recipient = platform wallet) demands that the customer
    prove they paid the platform the money the platform owes *them*, which no
    honest transaction can ever satisfy.
    """
    dest = (destination or "").strip()
    if not dest:
        return _result(verified=False, error="refund_destination_unknown")
    payers = refund_payer_wallets(chain)
    if not payers:
        # No wallet is configured for this chain, so "did the PLATFORM pay this?"
        # has no answer. verify_tx_transfer rejects an empty expectation with a
        # ValueError (a programming-error guard); here the empty tuple is a
        # runtime config state reachable from a customer-facing close, so it must
        # be an ordinary refusal — a 500 would put the channel back in the
        # unclosable state finding #8b was raised about.
        logger.warning(
            "cannot verify a %s refund payout: no settlement/refund wallet configured "
            "(set AIFACTORY_AI_MARKET_REFUND_WALLETS or the chain's settlement wallet)",
            chain,
        )
        return _result(verified=False, to=dest, error="refund_payout_wallet_unconfigured")
    return verify_tx_transfer(
        tx_hash=tx_hash,
        amount_usd=amount_usd,
        chain=chain,
        token=token,
        expect_sender=payers,
        recipient=dest,
    )


def verify_tx_payment(*, tx_hash: str, amount_usd: float, chain: str, token: str) -> bool:
    """LEGACY: "did somebody pay the platform?" — UNSAFE for crediting value.

    The payer is not checked, so the answer cannot tell you *whose* payment it
    was: any caller who learns the hash can claim it. Use
    :func:`verify_tx_transfer` with ``expect_sender=BIND_SENDER`` (and bind the
    credit to the returned address) for anything that grants balance, and
    :func:`verify_refund_transfer` for outbound settlements. Retained only for
    the aimarket-hub callers that import it by name.
    """
    out = verify_tx_transfer(
        tx_hash=tx_hash,
        amount_usd=amount_usd,
        chain=chain,
        token=token,
        expect_sender=ANY_SENDER,
    )
    return bool(out["verified"])


def verify_tx_payment_details(
    *, tx_hash: str, amount_usd: float, chain: str, token: str
) -> tuple[bool, str | None]:
    """Like :func:`verify_tx_payment` but also returns the on-chain SENDER address.

    Callers that credit value to an account (UNI top-up) must bind the credited
    account to the wallet that actually paid — verifying only recipient/amount
    lets anyone claim any inbound transfer to the shared settlement wallet.
    Returns ``(verified, from_address)``; ``from_address`` is ``None`` in the
    demo-bypass path (no real chain) so callers fail closed on the real path.
    """
    out = verify_tx_transfer(
        tx_hash=tx_hash,
        amount_usd=amount_usd,
        chain=chain,
        token=token,
        expect_sender=ANY_SENDER,
    )
    if not out["verified"]:
        return False, None
    return True, out["from"]
