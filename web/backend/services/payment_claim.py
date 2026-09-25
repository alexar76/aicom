"""Bind a public chain transaction to the authenticated checkout customer."""
from __future__ import annotations

import json
import re
from typing import Callable, Optional

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from eth_abi import decode as abi_decode
from eth_account import Account
from eth_account.messages import encode_defunct
from eth_utils import keccak

from core.public_site_url import resolve_public_site_url

# The doors that turn an inbound transfer into something of value. Each one takes the
# same single-use claim (ai_market_protocol.channels.claim_transfer) under its own name,
# so a transfer spent at one door is refused at every other.
DOOR_CHECKOUT = "web-checkout"
DOOR_PILOT = "web-pilot-settlement"
DOOR_INVOKE = "web-invoke"
DOOR_UNI_TOPUP = "web-uni-topup"

_EVM_TX = re.compile(r"(?:0[xX])?([0-9a-fA-F]{64})")


def canonical_tx_hash(value: str) -> str:
    """The one key every door stores and compares a transfer under.

    An EVM hash is case-insensitive and web3 adds a missing 0x itself, so ``0xABC…``,
    ``0xabc…`` and a bare ``abc…`` all fetch the same transaction. They must be one
    key, or each spelling can be spent again. Anything else (a base58 Solana
    signature) is case-sensitive and is kept byte for byte.
    """
    value = (value or "").strip()
    match = _EVM_TX.fullmatch(value)
    if match:
        return "0x" + match.group(1).lower()
    return value


def checkout_tx_hash(chain: str, value: str) -> str:
    value = value.strip()
    if chain == "solana":
        if not re.fullmatch(r"[1-9A-HJ-NP-Za-km-z]{64,88}", value):
            raise ValueError("Invalid Solana transaction signature")
        return value
    if not _EVM_TX.fullmatch(value):
        raise ValueError("Invalid EVM transaction hash")
    return canonical_tx_hash(value)


def claim_message(payment: dict, tx_hash: str) -> str:
    """The server constructs the entire signed message from its immutable quote.

    The opening lines are for the person signing: which site asks, and which
    transfer they claim for which order. A genuine message shown on another site
    still says where it belongs, so a "verify your purchase" page elsewhere is
    visibly not the place to sign it. The site is in the signed JSON as well, so a
    signature made for one deployment does not validate on another. A quote pins
    the site it was issued under (``payment["site"]``) so a config change between
    fetching and confirming cannot invalidate an honest signature.
    """
    site = payment.get("site") or resolve_public_site_url()
    transaction = checkout_tx_hash(payment["chain"], tx_hash)
    return (
        f"{site} asks you to confirm that you paid for order {payment['payment_id']}.\n"
        f"Sign only on {site}, and only if you sent transaction {transaction}.\n\n"
        "AI Factory checkout ownership v2\n" + json.dumps({
            "site": site,
            "payment_id": payment["payment_id"], "customer_id": payment["customer_id"],
            "product_id": payment["product_id"], "chain": payment["chain"],
            "currency": payment["currency"], "amount": str(payment["amount"]),
            "recipient": payment["wallet_address"], "transaction": transaction,
        }, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    )


def _base58_decode(value: str) -> bytes:
    alphabet = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    number = 0
    for char in value:
        number = number * 58 + alphabet.index(char)
    return b"\0" * (len(value) - len(value.lstrip("1"))) + number.to_bytes(
        (number.bit_length() + 7) // 8, "big")


# ERC-6492: a smart wallet that signs before it is first deployed appends this marker
# to abi.encode(factory, factoryCalldata, innerSignature).
_ERC6492_SUFFIX = bytes.fromhex("6492" * 16)

# (payer, EIP-191 digest, signature bytes) -> did that contract wallet accept it?
ContractSignatureCheck = Callable[[str, bytes, bytes], bool]


def _eip191_digest(message: str) -> bytes:
    data = message.encode("utf-8")
    return keccak(b"\x19Ethereum Signed Message:\n" + str(len(data)).encode() + data)


def _erc1271_signature(signature: str) -> bytes:
    """The bytes a contract wallet's isValidSignature should be asked about.

    A 6492 wrapper is unwrapped rather than refused: the wallet has already sent the
    payment on chain, so it is deployed, and its own isValidSignature judges the
    inner signature.
    """
    raw = bytes.fromhex(signature.strip().removeprefix("0x"))
    if len(raw) > 32 and raw.endswith(_ERC6492_SUFFIX):
        _factory, _calldata, inner = abi_decode(["address", "bytes", "bytes"], raw[:-32])
        return bytes(inner)
    return raw


def verify_claim(payment: dict, tx_hash: str, signature: str, payer: str, *,
                 contract_check: Optional[ContractSignatureCheck] = None) -> bool:
    """Whether ``signature`` proves the on-chain ``payer`` claims this transfer here.

    An ordinary wallet signs with its key (EIP-191, recovered locally). A smart
    contract wallet has no key to recover; ``contract_check`` asks the wallet itself
    (EIP-1271 isValidSignature), which is how Coinbase Smart Wallet and Safe buyers,
    common on Base, can claim what they paid.
    """
    try:
        message = claim_message(payment, tx_hash)
        if payment["chain"] == "solana":
            raw = bytes.fromhex(signature.removeprefix("0x"))
            if len(raw) != 64:
                return False
            Ed25519PublicKey.from_public_bytes(_base58_decode(payer)).verify(raw, message.encode())
            return True
        try:
            recovered = Account.recover_message(encode_defunct(text=message), signature=signature)
            if recovered.lower() == payer.lower():
                return True
        except Exception:
            pass  # not a plain 65-byte key signature; a contract wallet may still accept it
        if contract_check is None:
            return False
        return bool(contract_check(payer, _eip191_digest(message), _erc1271_signature(signature)))
    except (ValueError, TypeError, KeyError):
        return False
    except Exception:
        # Includes InvalidSignature and malformed crypto encodings. Never fall back
        # to accepting a tx hash without a valid proof.
        return False
