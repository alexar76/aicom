"""EIP-712 DebitAuthorization — the exact bytes ``AIMarketEscrow.debitChannel`` verifies.

This module is the whole reason the bridge can be trusted to move money: if the digest
computed here differs from the one the contract computes by a single byte, ``ECDSA.recover``
returns a stranger and every submission reverts with ``InvalidSignature()``. So the encoding
is written out explicitly against the Solidity source rather than delegated to a helper
whose defaults might drift:

    contracts/evm/src/AIMarketEscrow.sol
      DEBIT_TYPEHASH = keccak256("DebitAuthorization(bytes32 channelId,address hub,"
                                 "address token,uint256 amount,bytes32 receiptId,"
                                 "uint256 nonce,uint256 deadline)")
      domain         = EIP712Domain(name="AIMarketEscrow", version="1",
                                    chainId=block.chainid, verifyingContract=address(this))
      digest         = keccak256(0x19 0x01 || domainSeparator || structHash)

Every field of DebitAuthorization is a static 32-byte word, so the struct encoding is a
plain concatenation — there is no dynamic-type tail to get wrong. ``tests/
test_escrow_bridge_eip712.py`` cross-checks the result against eth-account's independent
typed-data implementation, so a mistake here cannot hide behind a self-consistent helper.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

DEBIT_TYPE_STRING = (
    "DebitAuthorization(bytes32 channelId,address hub,address token,uint256 amount,"
    "bytes32 receiptId,uint256 nonce,uint256 deadline)"
)
EIP712_DOMAIN_TYPE_STRING = (
    "EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)"
)
ESCROW_DOMAIN_NAME = "AIMarketEscrow"
ESCROW_DOMAIN_VERSION = "1"

_ZERO_ADDRESS = "0x" + "00" * 20
_HEX_RE = re.compile(r"\A0x[0-9a-fA-F]*\Z")
_UINT256_MAX = 2**256 - 1


class Eip712Error(ValueError):
    """The inputs cannot produce a digest the contract would also compute."""


class CryptoUnavailable(RuntimeError):
    """keccak/ECDSA primitives are not installed in this interpreter.

    Raised rather than degraded: a bridge that cannot verify a signature must refuse,
    and the hub's own test venv genuinely lacks eth-account, so this has to be an
    explicit, catchable condition instead of a silent "looks fine".
    """


def _keccak(data: bytes) -> bytes:
    try:
        from eth_utils import keccak
    except Exception as exc:  # pragma: no cover - environment-dependent
        raise CryptoUnavailable(f"keccak unavailable: {exc}") from exc
    return keccak(data)


def crypto_available() -> bool:
    """Whether this interpreter can compute digests and recover signers."""
    try:
        from eth_account import Account  # noqa: F401
        from eth_utils import keccak  # noqa: F401
    except Exception:
        return False
    return True


# ── primitive encoders ───────────────────────────────────────────────────────


def _hex_bytes(value: Any, *, size: int, field: str) -> bytes:
    """Fixed-size hex → bytes, refusing anything that is not exactly ``size`` bytes.

    Padding a short value would silently accept a truncated channel id or receipt id and
    sign a claim against a DIFFERENT deposit than the caller meant.
    """
    if isinstance(value, (bytes, bytearray)):
        raw = bytes(value)
    else:
        text = str(value or "").strip()
        if not _HEX_RE.match(text):
            raise Eip712Error(f"{field} must be 0x-prefixed hex, got {text[:16]!r}")
        body = text[2:]
        if len(body) % 2:
            raise Eip712Error(f"{field} has an odd number of hex digits")
        raw = bytes.fromhex(body)
    if len(raw) != size:
        raise Eip712Error(f"{field} must be exactly {size} bytes, got {len(raw)}")
    return raw


def _address_word(value: Any, *, field: str, allow_zero: bool = False) -> bytes:
    """Left-pad a 20-byte address into a 32-byte word.

    The zero address is refused by default. A signature over a zero ``verifyingContract``
    or a zero ``hub`` is structurally valid and verifiable by NOTHING that exists on
    chain — an invisible dead end that looks like a working authorization until the day
    it has to be submitted.
    """
    raw = _hex_bytes(value, size=20, field=field)
    if not allow_zero and raw == b"\x00" * 20:
        raise Eip712Error(
            f"{field} must not be the zero address — a signature bound to it can never "
            "be verified by a deployed contract"
        )
    return b"\x00" * 12 + raw


def _uint_word(value: Any, *, field: str) -> bytes:
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise Eip712Error(f"{field} must be an integer, got {value!r}") from exc
    if number < 0 or number > _UINT256_MAX:
        raise Eip712Error(f"{field} out of uint256 range: {number}")
    return number.to_bytes(32, "big")


def normalize_address(value: Any) -> str:
    """Lower-cased 0x address, for comparisons and storage (never for hashing)."""
    return "0x" + _hex_bytes(value, size=20, field="address").hex()


def addresses_equal(left: Any, right: Any) -> bool:
    """Case-insensitive address comparison that refuses to guess on malformed input."""
    try:
        return normalize_address(left) == normalize_address(right)
    except Eip712Error:
        return False


# ── the authorization ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class DebitAuthorization:
    """One buyer-signed permission to debit one channel once.

    ``receipt_id`` is the contract's replay key (``usedReceipts``) and ``nonce`` must equal
    the channel's CURRENT on-chain nonce, so an authorization names exactly one debit in
    exactly one order — it cannot be replayed and it cannot jump a gap.
    """

    channel_id: str
    hub: str
    token: str
    amount: int
    receipt_id: str
    nonce: int
    deadline: int

    def as_message(self) -> dict[str, Any]:
        """The message dict in the contract's field order (for eth-account cross-checks)."""
        return {
            "channelId": self.channel_id,
            "hub": self.hub,
            "token": self.token,
            "amount": int(self.amount),
            "receiptId": self.receipt_id,
            "nonce": int(self.nonce),
            "deadline": int(self.deadline),
        }


def domain_separator(*, chain_id: int, verifying_contract: str) -> bytes:
    """keccak256(abi.encode(domainTypeHash, keccak(name), keccak(version), chainId, addr)).

    Mirrors ``AIMarketEscrow._buildDomainSeparator``. The contract recomputes its own
    separator when ``block.chainid`` changes, so a fork does not silently accept
    signatures made for the original chain — which is why chain_id is a required
    argument here and never assumed.
    """
    if int(chain_id) <= 0:
        raise Eip712Error(f"chainId must be positive, got {chain_id}")
    return _keccak(
        _keccak(EIP712_DOMAIN_TYPE_STRING.encode())
        + _keccak(ESCROW_DOMAIN_NAME.encode())
        + _keccak(ESCROW_DOMAIN_VERSION.encode())
        + _uint_word(chain_id, field="chainId")
        + _address_word(verifying_contract, field="verifyingContract")
    )


def struct_hash(auth: DebitAuthorization) -> bytes:
    """keccak256(abi.encode(DEBIT_TYPEHASH, …)) — seven static words, in contract order."""
    return _keccak(
        _keccak(DEBIT_TYPE_STRING.encode())
        + _hex_bytes(auth.channel_id, size=32, field="channelId")
        + _address_word(auth.hub, field="hub")
        + _address_word(auth.token, field="token")
        + _uint_word(auth.amount, field="amount")
        + _hex_bytes(auth.receipt_id, size=32, field="receiptId")
        + _uint_word(auth.nonce, field="nonce")
        + _uint_word(auth.deadline, field="deadline")
    )


def debit_digest(
    auth: DebitAuthorization, *, chain_id: int, verifying_contract: str
) -> bytes:
    """The 32 bytes the depositor signs, identical to ``computeDebitDigest`` on chain."""
    return _keccak(
        b"\x19\x01"
        + domain_separator(chain_id=chain_id, verifying_contract=verifying_contract)
        + struct_hash(auth)
    )


# ── EIP-3009, the signature x402 "exact" payments carry ──────────────────────
#
# A different struct in a different domain from the escrow's DebitAuthorization: the
# verifying contract is the TOKEN, and the domain name/version are the token's own
# (Base mainnet USDC calls itself "USD Coin" version "2"; Base Sepolia USDC calls itself
# "USDC"). Getting either wrong produces a digest the token would never accept, which is
# invisible until a real settlement is rejected — so both are arguments here, never
# assumed.
TRANSFER_AUTHORIZATION_TYPE_STRING = (
    "TransferWithAuthorization(address from,address to,uint256 value,"
    "uint256 validAfter,uint256 validBefore,bytes32 nonce)"
)


def token_domain_separator(
    *, name: str, version: str, chain_id: int, verifying_contract: str
) -> bytes:
    """EIP-712 domain of an EIP-3009 token."""
    if int(chain_id) <= 0:
        raise Eip712Error(f"chainId must be positive, got {chain_id}")
    if not str(name):
        raise Eip712Error("token domain name is required")
    return _keccak(
        _keccak(EIP712_DOMAIN_TYPE_STRING.encode())
        + _keccak(str(name).encode())
        + _keccak(str(version or "").encode())
        + _uint_word(chain_id, field="chainId")
        + _address_word(verifying_contract, field="verifyingContract")
    )


def transfer_authorization_digest(
    *,
    sender: str,
    recipient: str,
    value: int,
    valid_after: int,
    valid_before: int,
    nonce: str,
    token_name: str,
    token_version: str,
    chain_id: int,
    token_address: str,
) -> bytes:
    """The 32 bytes a payer signs to authorize an EIP-3009 transfer."""
    struct = _keccak(
        _keccak(TRANSFER_AUTHORIZATION_TYPE_STRING.encode())
        + _address_word(sender, field="from")
        + _address_word(recipient, field="to")
        + _uint_word(value, field="value")
        + _uint_word(valid_after, field="validAfter")
        + _uint_word(valid_before, field="validBefore")
        + _hex_bytes(nonce, size=32, field="nonce")
    )
    return _keccak(
        b"\x19\x01"
        + token_domain_separator(
            name=token_name, version=token_version,
            chain_id=chain_id, verifying_contract=token_address,
        )
        + struct
    )


def recover_transfer_signer(signature: str, digest: bytes) -> str | None:
    """Who signed this EIP-3009 digest, or None for any malformed proof.

    None rather than an exception for a bad signature — that is a failed payment, not a
    server fault — but a missing crypto stack still raises, so "we cannot check" can never
    be mistaken for "the payer did not sign".
    """
    try:
        from eth_account import Account
    except Exception as exc:  # pragma: no cover - environment-dependent
        raise CryptoUnavailable(f"eth-account unavailable: {exc}") from exc
    sig = str(signature or "").strip()
    if not sig:
        return None
    try:
        return Account._recover_hash(digest, signature=sig)
    except Exception:
        return None


def recover_signer(
    auth: DebitAuthorization,
    signature: str,
    *,
    chain_id: int,
    verifying_contract: str,
) -> str | None:
    """Address that produced ``signature`` over this authorization, or None.

    None — never an exception — for every kind of bad signature (wrong length, bad ``v``,
    non-hex, empty), because a malformed proof is a failed authorization, not a server
    error. A genuinely broken environment (no eth-account) still raises, so it can never
    be mistaken for "the buyer did not sign".
    """
    digest = debit_digest(
        auth, chain_id=chain_id, verifying_contract=verifying_contract
    )
    try:
        from eth_account import Account
    except Exception as exc:  # pragma: no cover - environment-dependent
        raise CryptoUnavailable(f"eth-account unavailable: {exc}") from exc
    sig = str(signature or "").strip()
    if not sig:
        return None
    try:
        # _recover_hash is the documented entry point for a pre-computed EIP-712 digest;
        # recover_message would re-wrap it in the personal-sign prefix, which the
        # contract does NOT apply (it verifies the raw typed-data digest).
        return Account._recover_hash(digest, signature=sig)
    except Exception:
        return None


def signature_matches(
    auth: DebitAuthorization,
    signature: str,
    *,
    expected_signer: str,
    chain_id: int,
    verifying_contract: str,
) -> bool:
    """True iff ``signature`` over this authorization was made by ``expected_signer``."""
    recovered = recover_signer(
        auth, signature, chain_id=chain_id, verifying_contract=verifying_contract
    )
    return bool(recovered) and addresses_equal(recovered, expected_signer)
