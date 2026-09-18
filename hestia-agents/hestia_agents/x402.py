"""Turn a hearth's 402 into something a wallet can sign and send.

HESTIA binds a payment to one call: the 402 mints a nonce, and the buyer proves
the payment was made for THAT call by signing an EIP-3009
`transferWithAuthorization` over it. The token contract checks the signature on
chain and emits `AuthorizationUsed(authorizer, nonce)`; the hearth only reads
that log. Nobody has to trust the hearth with a key, and the hearth needs no gas.

Nothing here touches a private key. It produces:

  * the EIP-712 typed data to hand to `eth_signTypedData_v4` (any wallet), and
  * the calldata to send to the token contract once you have that signature.

Sign and send with whatever already holds your key — a browser wallet, `cast`,
a hardware device. Keeping the key out of this tool is the point.
"""

from __future__ import annotations

from typing import Any

# keccak256("transferWithAuthorization(address,address,uint256,uint256,uint256,
#           bytes32,uint8,bytes32,bytes32)")[:4]
TRANSFER_WITH_AUTHORIZATION_SELECTOR = "0xe3ee160e"

EIP712_TYPES: dict[str, list[dict[str, str]]] = {
    "EIP712Domain": [
        {"name": "name", "type": "string"},
        {"name": "version", "type": "string"},
        {"name": "chainId", "type": "uint256"},
        {"name": "verifyingContract", "type": "address"},
    ],
    "TransferWithAuthorization": [
        {"name": "from", "type": "address"},
        {"name": "to", "type": "address"},
        {"name": "value", "type": "uint256"},
        {"name": "validAfter", "type": "uint256"},
        {"name": "validBefore", "type": "uint256"},
        {"name": "nonce", "type": "bytes32"},
    ],
}


class QuoteError(ValueError):
    """The 402 did not carry what a payment needs."""


def _accept(quote: dict[str, Any]) -> dict[str, Any]:
    accepts = quote.get("accepts") or []
    if not accepts:
        raise QuoteError("402 carried no 'accepts' entry")
    return accepts[0]


def typed_data(
    quote: dict[str, Any],
    *,
    sender: str,
    valid_after: int = 0,
    valid_before: int,
) -> dict[str, Any]:
    """EIP-712 payload for `eth_signTypedData_v4`.

    The domain comes from the 402 itself (`accepts[0].extra`) rather than being
    guessed: a token's EIP-712 name/version is not derivable from its symbol, and
    guessing wrong yields a signature the contract rejects — which looks like the
    hearth refusing a good payment.
    """
    accept = _accept(quote)
    extra = accept.get("extra") or {}
    nonce = quote.get("nonce") or extra.get("nonce")
    if not nonce:
        raise QuoteError("402 carried no payment nonce; this hearth is unbound")
    for field in ("name", "version", "chainId", "verifyingContract"):
        if not extra.get(field):
            raise QuoteError(f"402 'extra' is missing the EIP-712 domain field {field!r}")
    return {
        "types": EIP712_TYPES,
        "primaryType": "TransferWithAuthorization",
        "domain": {
            "name": extra["name"],
            "version": str(extra["version"]),
            "chainId": int(extra["chainId"]),
            "verifyingContract": extra["verifyingContract"],
        },
        "message": {
            "from": sender,
            "to": accept["payTo"],
            "value": str(accept["maxAmountRequired"]),
            "validAfter": str(valid_after),
            "validBefore": str(valid_before),
            "nonce": nonce,
        },
    }


def split_signature(signature: str) -> tuple[int, str, str]:
    """65-byte wallet signature → (v, r, s). Accepts v as 0/1 or 27/28."""
    raw = signature[2:] if signature.startswith("0x") else signature
    if len(raw) != 130:
        raise QuoteError("signature must be 65 bytes (132 chars with 0x)")
    r = "0x" + raw[0:64]
    s = "0x" + raw[64:128]
    v = int(raw[128:130], 16)
    if v < 27:
        v += 27
    return v, r, s


def _word(value: int | str) -> str:
    if isinstance(value, str):
        hexed = value[2:] if value.startswith("0x") else value
        return hexed.rjust(64, "0").lower()
    return format(value, "064x")


def calldata(
    typed: dict[str, Any], signature: str
) -> str:
    """ABI-encoded `transferWithAuthorization` call for the token contract.

    Every argument is a fixed-size type, so this is the selector followed by
    nine 32-byte words — no dynamic offsets, nothing to get subtly wrong.
    """
    message = typed["message"]
    v, r, s = split_signature(signature)
    words = [
        _word(message["from"]),
        _word(message["to"]),
        _word(int(message["value"])),
        _word(int(message["validAfter"])),
        _word(int(message["validBefore"])),
        _word(message["nonce"]),
        _word(v),
        _word(r),
        _word(s),
    ]
    return TRANSFER_WITH_AUTHORIZATION_SELECTOR + "".join(words)
