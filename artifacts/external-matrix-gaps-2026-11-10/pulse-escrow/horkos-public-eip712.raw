"""Independent EIP-712 verification of the depositor's debit authorization.

"Independent" is the whole value of this module. The hub sends bytes; this rebuilds the
digest the contract will build, and every field the contract reads from *storage* is read
here from chain too — never taken from the request:

    channelId, amount, receiptId, deadline   ← the request's calldata (the contract reads these too)
    hub                                      ← THIS SERVICE'S OWN ADDRESS, never the request
    token, nonce                             ← getChannel(channelId), read from chain

Substituting our own address for ``hub`` is what makes a signature minted for some other
hub unusable here, and it mirrors the contract exactly: ``debitChannel`` binds
``msg.sender`` into the struct hash (AIMarketEscrow.sol:324), so a depositor's signature
for hub A cannot be replayed by hub B.

Both the type hash and the domain separator are computed from their source strings and
then checked against the deployed contract's own ``domainSeparator()`` at boot, so a
mismatch is a startup refusal rather than a run of unusable signatures.
"""

from __future__ import annotations

from eth_account import Account
from eth_utils import keccak

DEBIT_TYPE_STRING = (
    "DebitAuthorization(bytes32 channelId,address hub,address token,uint256 amount,"
    "bytes32 receiptId,uint256 nonce,uint256 deadline)"
)
DOMAIN_TYPE_STRING = (
    "EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)"
)
DOMAIN_NAME = "AIMarketEscrow"
DOMAIN_VERSION = "1"

DEBIT_TYPEHASH = keccak(DEBIT_TYPE_STRING.encode())


def _address_word(address: str) -> bytes:
    raw = bytes.fromhex(address[2:] if address.startswith("0x") else address)
    if len(raw) != 20:
        raise ValueError("address must be 20 bytes")
    return bytes(12) + raw


def domain_separator(chain_id: int, verifying_contract: str) -> bytes:
    """``_buildDomainSeparator`` from AIMarketEscrow.sol, recomputed here."""
    return keccak(
        keccak(DOMAIN_TYPE_STRING.encode())
        + keccak(DOMAIN_NAME.encode())
        + keccak(DOMAIN_VERSION.encode())
        + chain_id.to_bytes(32, "big")
        + _address_word(verifying_contract)
    )


def debit_digest(
    *,
    separator: bytes,
    channel_id: bytes,
    hub: str,
    token: str,
    amount: int,
    receipt_id: bytes,
    nonce: int,
    deadline: int,
) -> bytes:
    """The exact digest ``debitChannel`` recovers against."""
    struct_hash = keccak(
        DEBIT_TYPEHASH
        + channel_id
        + _address_word(hub)
        + _address_word(token)
        + amount.to_bytes(32, "big")
        + receipt_id
        + nonce.to_bytes(32, "big")
        + deadline.to_bytes(32, "big")
    )
    return keccak(b"\x19\x01" + separator + struct_hash)


def recover(digest: bytes, signature: bytes) -> str:
    """Recover the signer of a 65-byte signature over ``digest``.

    Raises on anything unrecoverable; the caller turns that into a refusal. The exception
    is never included in a log line — a signing/recovery error can carry the payload, and
    the payload is the buyer's signature.
    """
    return Account._recover_hash(digest, signature=signature)
