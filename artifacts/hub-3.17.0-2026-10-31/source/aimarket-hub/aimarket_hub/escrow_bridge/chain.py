"""Read-only view of AIMarketEscrow, plus calldata the mirror can simulate.

Nothing in this module signs or sends anything — it only reads and encodes. That split is
deliberate: C1 (funding verification) and the mirror's plan mode need exactly these
capabilities and no more, so the code path that a channel open depends on cannot broadcast
even if the submission policy is misconfigured.

Transport is the hub's existing ``chain_net`` pool (priority-ordered endpoints, failover
on transport errors, JSON-RPC errors surfaced rather than retried), so the bridge inherits
the RPC configuration operators already use instead of introducing a second one.

The ``getChannel`` decoding below was verified against a live deployment on a local anvil:
the struct is nine consecutive 32-byte words in the order declared in
``contracts/evm/src/AIMarketEscrow.sol`` (depositor, hub, token, depositAmount, balance,
usedAmount, expiresAt, nonce, status).
"""

from __future__ import annotations

import contextlib

import logging
import time
from dataclasses import dataclass
from typing import Any

from aimarket_hub.escrow_bridge import config
from aimarket_hub.escrow_bridge.eip712 import (
    DebitAuthorization,
    Eip712Error,
    _keccak,
    normalize_address,
)
from aimarket_hub.escrow_bridge.errors import (
    BridgeConfigError,
    ChainUnavailable,
)

logger = logging.getLogger(__name__)

ESCROW_CONTRACT_NAME = "AIMarketEscrow"
_ZERO_ADDR = "0x" + "00" * 20
_WORD = 32

# ChannelStatus in declaration order — the enum is encoded as its ordinal.
STATUS_OPEN = 0
STATUS_SETTLED = 1
STATUS_REFUNDED = 2
STATUS_EXPIRED = 3
_STATUS_NAMES = {
    STATUS_OPEN: "Open",
    STATUS_SETTLED: "Settled",
    STATUS_REFUNDED: "Refunded",
    STATUS_EXPIRED: "Expired",
}


def selector(signature: str) -> bytes:
    """First 4 bytes of keccak(signature) — computed, never hardcoded.

    A hand-copied selector is exactly how the lottery relayer ended up encoding a
    function that no longer existed; deriving it from the signature string means a
    contract rename breaks loudly at the call site instead of silently on chain.
    """
    return _keccak(signature.encode())[:4]


GET_CHANNEL_SIG = "getChannel(bytes32)"
DEBIT_CHANNEL_SIG = "debitChannel(bytes32,uint256,bytes32,uint256,bytes)"
SETTLE_CHANNEL_SIG = "settleChannel(bytes32)"
AUTHORIZED_HUBS_SIG = "authorizedHubs(address)"
# The contract's replay guard, public: `mapping(bytes32 => bool) public usedReceipts`
# (AIMarketEscrow.sol:128, enforced at :306). Reading it is how the mirror learns that a
# receipt was already collected — including by a debit the hub did not send itself.
USED_RECEIPTS_SIG = "usedReceipts(bytes32)"
# AIMarketEscrowV2 keys its replay flag by (channelId, receiptId); this is its reader.
IS_RECEIPT_USED_SIG = "isReceiptUsed(bytes32,bytes32)"


# ── ABI encoding (only the shapes this module needs) ─────────────────────────


def _word_from_hex(value: str, *, size: int, field: str) -> bytes:
    text = str(value or "").strip()
    if not text.startswith("0x"):
        raise Eip712Error(f"{field} must be 0x-prefixed hex")
    raw = bytes.fromhex(text[2:])
    if len(raw) != size:
        raise Eip712Error(f"{field} must be {size} bytes, got {len(raw)}")
    return raw.rjust(_WORD, b"\x00")


def _uint_word(value: int) -> bytes:
    return int(value).to_bytes(_WORD, "big")


def encode_get_channel(channel_id: str) -> str:
    return "0x" + (
        selector(GET_CHANNEL_SIG) + _word_from_hex(channel_id, size=32, field="channelId")
    ).hex()


def encode_authorized_hubs(hub: str) -> str:
    return "0x" + (
        selector(AUTHORIZED_HUBS_SIG)
        + _word_from_hex(normalize_address(hub), size=20, field="hub")
    ).hex()


def encode_used_receipts(receipt_id: str) -> str:
    return "0x" + (
        selector(USED_RECEIPTS_SIG) + _word_from_hex(receipt_id, size=32, field="receiptId")
    ).hex()


def encode_settle_channel(channel_id: str) -> str:
    return "0x" + (
        selector(SETTLE_CHANNEL_SIG) + _word_from_hex(channel_id, size=32, field="channelId")
    ).hex()


def encode_debit_channel(auth: DebitAuthorization, signature: str) -> str:
    """Calldata for ``debitChannel``. ``signature`` is a dynamic ``bytes`` argument.

    Five head words (four statics plus the offset to the tail), then the byte string as
    length + right-padded content. Written out rather than delegated because getting the
    offset wrong produces calldata a node accepts and the contract misreads.
    """
    sig = str(signature or "").strip()
    if not sig.startswith("0x"):
        raise Eip712Error("signature must be 0x-prefixed hex")
    sig_bytes = bytes.fromhex(sig[2:])
    if not sig_bytes:
        raise Eip712Error("signature is empty")

    head = (
        _word_from_hex(auth.channel_id, size=32, field="channelId")
        + _uint_word(auth.amount)
        + _word_from_hex(auth.receipt_id, size=32, field="receiptId")
        + _uint_word(auth.deadline)
        # Offset counts from the start of the argument block: 5 head words precede the tail.
        + _uint_word(5 * _WORD)
    )
    pad = (-len(sig_bytes)) % _WORD
    tail = _uint_word(len(sig_bytes)) + sig_bytes + b"\x00" * pad
    return "0x" + (selector(DEBIT_CHANNEL_SIG) + head + tail).hex()


def _decode_words(data: str, *, expected: int, what: str) -> list[bytes]:
    raw = bytes.fromhex(data[2:] if data.startswith("0x") else data)
    if len(raw) < expected * _WORD:
        raise ChainUnavailable(
            f"{what} returned {len(raw)} bytes, expected at least {expected * _WORD} — "
            "wrong address, wrong ABI, or a node returning junk"
        )
    return [raw[i * _WORD:(i + 1) * _WORD] for i in range(expected)]


def _addr(word: bytes) -> str:
    return "0x" + word[-20:].hex()


def _uint(word: bytes) -> int:
    return int.from_bytes(word, "big")


# ── the channel as the contract sees it ──────────────────────────────────────


@dataclass(frozen=True)
class EscrowChannel:
    """One ``channels[channelId]`` row, decoded."""

    channel_id: str
    depositor: str
    hub: str
    token: str
    deposit_amount: int
    balance: int
    used_amount: int
    expires_at: int
    nonce: int
    status: int
    #: V2 only: when the depositor's exit request matures (0 = no exit asked, or V1).
    closable_at: int = 0

    @property
    def exists(self) -> bool:
        """A never-opened channel reads back as all zeroes, so the depositor is the probe."""
        return self.depositor != _ZERO_ADDR

    @property
    def is_open(self) -> bool:
        return self.status == STATUS_OPEN

    @property
    def status_name(self) -> str:
        return _STATUS_NAMES.get(self.status, f"Unknown({self.status})")

    @property
    def hub_bound(self) -> bool:
        """The contract binds ``hub`` on the FIRST debit; before that it is the zero address."""
        return self.hub != _ZERO_ADDR

    def expired(self, *, now: float | None = None) -> bool:
        return self.expires_at <= int(now if now is not None else time.time())

    def as_dict(self) -> dict[str, Any]:
        return {
            "channel_id": self.channel_id,
            "depositor": self.depositor,
            "hub": self.hub,
            "token": self.token,
            "deposit_amount": self.deposit_amount,
            "balance": self.balance,
            "used_amount": self.used_amount,
            "expires_at": self.expires_at,
            "nonce": self.nonce,
            "status": self.status,
            "status_name": self.status_name,
        }


# ── resolution + reads ───────────────────────────────────────────────────────


def _network():
    from aimarket_hub import chain_net

    net_id = config.network_id()
    try:
        return chain_net.network(net_id) if net_id else chain_net.active_network()
    except Exception as exc:
        raise BridgeConfigError(f"cannot resolve escrow network {net_id or '(active)'}: {exc}") from exc


def escrow_address() -> str:
    """Configured escrow address, else the one chain_net resolved for this network."""
    override = config.contract_address()
    if override:
        try:
            return normalize_address(override)
        except Eip712Error as exc:
            raise BridgeConfigError(f"AIMARKET_ESCROW_CONTRACT is not an address: {exc}") from exc
    spec = _network()
    addr = (spec.addresses or {}).get(ESCROW_CONTRACT_NAME, "")
    if not addr:
        raise BridgeConfigError(
            f"no {ESCROW_CONTRACT_NAME} address for network {spec.id!r} — set "
            "AIMARKET_ESCROW_CONTRACT"
        )
    return normalize_address(addr)


def _pool():
    from aimarket_hub import chain_net

    net_id = config.network_id()
    try:
        return chain_net.pool_for(net_id or None, timeout=config.rpc_timeout_s())
    except TypeError:
        # Older chain_net signatures do not take a timeout; the pool's own default applies.
        return chain_net.pool_for(net_id or None)
    except Exception as exc:
        raise ChainUnavailable(f"no RPC pool for {net_id or '(active)'}: {exc}") from exc


def chain_id() -> int:
    """The chain id the RPC actually reports — never the one we hoped for.

    The escrow recomputes its EIP-712 domain separator when ``block.chainid`` changes, so
    signing against a configured-but-wrong id yields signatures the contract rejects. A
    mismatch between the RPC and the registry is a configuration error, not something to
    average out.
    """
    try:
        raw = _pool().call("eth_chainId")
    except Exception as exc:
        raise ChainUnavailable(f"eth_chainId failed: {exc}") from exc
    try:
        reported = int(str(raw), 16) if str(raw).startswith("0x") else int(raw)
    except (TypeError, ValueError) as exc:
        raise ChainUnavailable(f"eth_chainId returned {raw!r}") from exc
    expected = getattr(_network(), "chain_id", None)
    if expected and int(expected) != reported:
        raise BridgeConfigError(
            f"RPC reports chainId {reported} but the configured network expects "
            f"{expected} — refusing to sign or verify against the wrong chain"
        )
    return reported


def read_channel(channel_id: str, *, address: str | None = None) -> EscrowChannel:
    """Decode ``getChannel(channelId)``. Raises ChainUnavailable if it cannot be read.

    A channel that was never opened is NOT an error here — it decodes to a zero row whose
    ``exists`` is False, so the caller decides what a missing channel means.
    """
    escrow = normalize_address(address) if address else escrow_address()
    try:
        result = _pool().call(
            "eth_call", [{"to": escrow, "data": encode_get_channel(channel_id)}, "latest"]
        )
    except Exception as exc:
        raise ChainUnavailable(f"getChannel({channel_id[:12]}…) failed: {exc}") from exc
    if not isinstance(result, str) or not result.startswith("0x"):
        raise ChainUnavailable(f"getChannel returned {type(result).__name__}, expected hex")
    # V1 returns 9 words; AIMarketEscrowV2 inserts closableAt before status (10 words).
    # Reading a V2 row with the V1 layout took closableAt for status: a channel the
    # depositor had asked to exit — or one already refunded — decoded as Open.
    raw_len = (len(result) - 2) // 2
    v2 = raw_len >= 10 * _WORD
    words = _decode_words(result, expected=10 if v2 else 9, what="getChannel")
    return EscrowChannel(
        channel_id=channel_id,
        depositor=_addr(words[0]),
        hub=_addr(words[1]),
        token=_addr(words[2]),
        deposit_amount=_uint(words[3]),
        balance=_uint(words[4]),
        used_amount=_uint(words[5]),
        expires_at=_uint(words[6]),
        nonce=_uint(words[7]),
        status=_uint(words[9] if v2 else words[8]),
        closable_at=_uint(words[8]) if v2 else 0,
    )


def encode_is_receipt_used(channel_id: str, receipt_id: str) -> str:
    return "0x" + (
        selector(IS_RECEIPT_USED_SIG)
        + _word_from_hex(channel_id, size=32, field="channelId")
        + _word_from_hex(receipt_id, size=32, field="receiptId")
    ).hex()


def receipt_already_used(receipt_id: str, *, address: str | None = None,
                         channel_id: str | None = None) -> bool:
    """Whether the contract has already collected a debit for ``receipt_id``.

    True means the money is in — by whichever transaction got there first. The hub is not
    necessarily the sender: an operator collecting by hand with the CLI, or from a shell
    with ``cast``, sets the same flag, and then the hub's own store still says the receipt
    is owed. That is not a hypothetical. On 2026-07-29 the production store held three rows
    stuck at ``pending`` with an empty tx hash, two of whose receipt ids had already been
    debited on Base out of band, and because the mirror submits strictly in nonce order the
    first of them blocked every later row on its channel forever.

    Raises ChainUnavailable rather than returning False when the chain cannot be read: a
    read failure must not be mistaken for "not yet collected", which would send a debit the
    contract is guaranteed to reject.
    """
    escrow = normalize_address(address) if address else escrow_address()
    if channel_id:
        # V2 first: there usedReceipts(receiptId) reads a key nobody writes and always says
        # false. A V1 contract has no isReceiptUsed and reverts, which falls through to the
        # global flag below — where a real RPC failure raises as before.
        with contextlib.suppress(Exception):
            v2 = _pool().call("eth_call", [{"to": escrow,
                                            "data": encode_is_receipt_used(channel_id, receipt_id)},
                                           "latest"])
            if isinstance(v2, str) and v2.startswith("0x") and len(v2) >= 66:
                return _uint(_decode_words(v2, expected=1, what="isReceiptUsed")[0]) != 0
    try:
        result = _pool().call(
            "eth_call", [{"to": escrow, "data": encode_used_receipts(receipt_id)}, "latest"]
        )
    except Exception as exc:
        raise ChainUnavailable(f"usedReceipts({receipt_id[:12]}…) failed: {exc}") from exc
    if not isinstance(result, str) or not result.startswith("0x"):
        raise ChainUnavailable(f"usedReceipts returned {type(result).__name__}, expected hex")
    return _uint(_decode_words(result, expected=1, what="usedReceipts")[0]) != 0


def hub_is_authorized(hub: str, *, address: str | None = None) -> bool:
    """Whether the contract would accept debits from ``hub``.

    Checked in plan mode so an unauthorized hub is reported as a configuration problem
    up front, rather than as an opaque ``Unauthorized()`` revert at submission time.
    """
    escrow = normalize_address(address) if address else escrow_address()
    try:
        result = _pool().call(
            "eth_call", [{"to": escrow, "data": encode_authorized_hubs(hub)}, "latest"]
        )
    except Exception as exc:
        raise ChainUnavailable(f"authorizedHubs failed: {exc}") from exc
    words = _decode_words(str(result), expected=1, what="authorizedHubs")
    return _uint(words[0]) == 1


def simulate(*, to: str, data: str, sender: str) -> dict[str, Any]:
    """``eth_call`` a state-changing function to see whether it WOULD succeed.

    This is the whole value of plan mode: the node executes the call against real state
    and returns the revert reason, so an authorization can be proven acceptable (or its
    nonce gap / expired deadline / insufficient balance surfaced) without a transaction
    ever existing. Returns ``{"ok": bool, "error": str, "gas": int|None}`` and never
    raises for a revert — a revert is the answer, not a failure to get one.
    """
    pool = _pool()
    call = {"to": normalize_address(to), "data": data, "from": normalize_address(sender)}
    try:
        pool.call("eth_call", [call, "latest"])
    except Exception as exc:
        return {"ok": False, "error": _revert_reason(exc), "gas": None}
    gas: int | None = None
    try:
        raw = pool.call("eth_estimateGas", [call])
        gas = int(str(raw), 16) if str(raw).startswith("0x") else int(raw)
    except Exception as exc:  # a successful call with an unestimatable gas cost is odd but not fatal
        logger.debug("gas estimate unavailable: %s", exc)
    return {"ok": True, "error": "", "gas": gas}


# The escrow's custom errors. A raw eth_call returns only the 4-byte selector — decoding
# it needs the ABI, which `cast` has and a bare JSON-RPC client does not. Plan mode exists
# to tell an operator WHY the contract would refuse, and "custom error 0x8baa579f" does not
# do that. Selectors are derived from the signatures, so adding an error to the contract
# without adding it here degrades to the raw selector rather than mislabelling it.
_ESCROW_ERROR_SIGNATURES = (
    "ChannelNotFound()",
    "ChannelNotOpen()",
    "ChannelExists()",
    "ChannelNotExpired()",
    "InsufficientBalance(uint256,uint256)",
    "InvalidSignature()",
    "ChannelExpired()",
    "Unauthorized()",
    "DepositOutOfRange()",
    "TokenNotSupported()",
    "ReceiptAlreadyUsed(bytes32)",
    "RefundAfterDebit()",
    "UnsupportedTokenDecimals()",
)


def _error_selectors() -> dict[str, str]:
    table: dict[str, str] = {}
    for signature in _ESCROW_ERROR_SIGNATURES:
        table["0x" + selector(signature).hex()] = signature.split("(", 1)[0]
    return table


_ERROR_NAMES: dict[str, str] | None = None


def decode_revert(text: str) -> str:
    """Annotate a node's revert text with the escrow error name it names, if any."""
    global _ERROR_NAMES
    if _ERROR_NAMES is None:
        try:
            _ERROR_NAMES = _error_selectors()
        except Exception:  # keccak unavailable — the raw text is still useful
            _ERROR_NAMES = {}
    lowered = text.lower()
    for sel, name in _ERROR_NAMES.items():
        if sel in lowered:
            return f"{name} ({text})" if name.lower() not in lowered else text
    return text


def _revert_reason(exc: Exception) -> str:
    """Compact, non-leaky, and named where we can name it.

    Node error payloads can be enormous and can echo request data back; the bridge stores
    this string, so keep it short and strip nothing but the noise.
    """
    text = str(exc).strip().replace("\n", " ")
    if not text:
        return exc.__class__.__name__
    return decode_revert(text)[:300]
