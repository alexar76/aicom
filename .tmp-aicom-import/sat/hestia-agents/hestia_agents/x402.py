"""Turn a hearth's 402 into something a wallet can sign and send.

HESTIA binds a payment to one call: the 402 mints a nonce, and the buyer proves
the payment was made for THAT call by signing an EIP-3009
`transferWithAuthorization` over it. The token contract checks the signature on
chain and emits `AuthorizationUsed(authorizer, nonce)`; the hearth only reads
that log. Nobody has to trust the hearth with a key, and the hearth needs no gas.

A nonce binds a payment to one call, but not to one caller: the moment the
payment is mined, its transaction hash and that log are public, and anyone
watching the chain could present them before the buyer does. So the nonce is a
commitment — sha256 of a secret that never goes on chain (`nonce_for_secret`) —
and a payment is redeemed only with that secret. A tenant hearth mints the
secret and hands it to the buyer in its 402 (`payment_secret`); at the compute
door, which mints no nonce, the buyer makes one up (`mint_secret`). A secret with
fewer than 16 distinct bytes is a pattern anyone could guess, and so no proof of
who paid: the key-less door refuses it, and this client refuses it before a
payment is built over it (`secret_refusal`).

Nothing here touches a private key. It produces:

  * the EIP-712 typed data to hand to `eth_signTypedData_v4` (any wallet), and
  * the calldata to send to the token contract once you have that signature.

Sign and send with whatever already holds your key — a browser wallet, `cast`,
a hardware device. Keeping the key out of this tool is the point.
"""

from __future__ import annotations

import hashlib
import math
import secrets
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


_HEX_DIGITS = frozenset("0123456789abcdefABCDEF")


def _is_hex(text: str) -> bool:
    # Not int(text, 16): that also takes '+', '_' and surrounding whitespace, and
    # whatever it took would be copied into the calldata as it was written.
    return bool(text) and all(c in _HEX_DIGITS for c in text)


def _is_prefixed_hex(value: Any, digits: int) -> bool:
    return (
        isinstance(value, str)
        and value.startswith("0x")
        and len(value) == 2 + digits
        and _is_hex(value[2:])
    )


def is_address(value: Any) -> bool:
    return _is_prefixed_hex(value, 40)


def is_nonce(value: Any) -> bool:
    """A bytes32 as a wallet and the calldata take it: 0x and 64 hex digits."""
    return _is_prefixed_hex(value, 64)


def is_secret(value: Any) -> bool:
    return _is_prefixed_hex(value, 64)


# The hearth's floor (hestia/app.py _compute_gate): its key-less compute door refuses
# a secret with fewer distinct bytes than this. 32 random bytes hold about 30; a
# pattern with fewer (0x00…00, one byte repeated) is one a watcher can precompute,
# and so open the nonce of a payment that is not theirs.
MIN_DISTINCT_BYTES = 16
GUESSABLE = (
    f"is guessable (fewer than {MIN_DISTINCT_BYTES} distinct bytes): anyone could open "
    "its nonce; use 32 random bytes"
)


def is_guessable(secret: Any) -> bool:
    """A well-formed secret the hearth would refuse as guessable."""
    return is_secret(secret) and len(set(bytes.fromhex(secret[2:]))) < MIN_DISTINCT_BYTES


def secret_refusal(secret: Any) -> str:
    """Why a payment secret cannot redeem anything, as the end of a sentence; ''
    when it can.

    Asked wherever a buyer's secret enters, before anything is signed or sent:
    found out afterwards, a payment has already been made that its secret cannot
    redeem."""
    if not is_secret(secret):
        return "is not 0x followed by 64 hex digits"
    if is_guessable(secret):
        return GUESSABLE
    return ""


def mint_secret() -> str:
    """32 random bytes, written as the hearth reads them in X-Payment-Secret.

    A draw the hearth would call guessable is drawn again. The odds of one are
    far below any key's, but a secret this tool makes up must never be one the
    hearth refuses after the buyer has paid under it."""
    while True:
        secret = "0x" + secrets.token_hex(32)
        if not is_guessable(secret):
            return secret


def nonce_for_secret(secret: str) -> str:
    """The EIP-3009 nonce a payment secret commits to: sha256 of its 32 bytes.

    The hearth's rule (hestia.payments.nonce_for_secret); a test asserts the two
    agree, because a nonce derived any other way is a payment nobody can redeem."""
    if not is_secret(secret):
        raise QuoteError("a payment secret is 0x followed by 64 hex digits (32 bytes)")
    return "0x" + hashlib.sha256(bytes.fromhex(secret[2:])).hexdigest()


def opens(secret: Any, nonce: Any) -> bool:
    """True when `secret` is the preimage of `nonce` — what the hearth checks."""
    return is_secret(secret) and is_nonce(nonce) and nonce_for_secret(secret) == nonce.lower()


def whole_number(value: Any) -> int | None:
    """A positive integer written as an int or as decimal digits; None otherwise.

    bool is an int in Python and '1e3' is not a count of base units, so neither
    passes; a float would be one rounding away from a different amount."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        number = value
    elif isinstance(value, str) and value.isascii() and value.isdigit():
        number = int(value)
    else:
        return None
    return number if number > 0 else None


def redeem_by(quote: dict[str, Any]) -> int | None:
    """The last second a bound 402's nonce can be redeemed, or None if it does not say.

    The hearth refuses the nonce once its clock passes `expires_at` (an invoice
    lives payment_invoice_ttl_s, 900 s by default). A deadline signed later than
    that lets the payment be mined when nothing can redeem it any more."""
    expires = quote.get("expires_at")
    if expires is None:
        return None
    if (
        isinstance(expires, bool)
        or not isinstance(expires, (int, float))
        or not math.isfinite(expires)
        or expires <= 0
    ):
        raise QuoteError("402 'expires_at' is not a unix time")
    return int(expires)


def _accept(quote: dict[str, Any]) -> dict[str, Any]:
    accepts = quote.get("accepts") or []
    if not accepts:
        raise QuoteError("402 carried no 'accepts' entry")
    if not isinstance(accepts, list) or not isinstance(accepts[0], dict):
        raise QuoteError("402 'accepts' is not a list of payment options")
    return accepts[0]


def typed_data(
    quote: dict[str, Any],
    *,
    sender: str,
    valid_after: int = 0,
    valid_before: int,
    nonce: str = "",
) -> dict[str, Any]:
    """EIP-712 payload for `eth_signTypedData_v4`.

    The domain comes from the 402 itself (`accepts[0].extra`) rather than being
    guessed: a token's EIP-712 name/version is not derivable from its symbol, and
    guessing wrong yields a signature the contract rejects — which looks like the
    hearth refusing a good payment.

    `nonce`, when given, is signed instead of the one in the 402: the nonce of an
    earlier 402 that was already signed (every 402 mints a new one), or the
    sha256 of a buyer's own secret at a door that mints none.
    """
    if not is_address(sender):
        # quote prints `--from 0xYOURADDRESS` as a template; pasted literally it used to
        # become the first word of the typed data and the calldata, and exit 0.
        raise QuoteError("--from is not an address (0x followed by 40 hex digits)")
    for name, moment in (("valid-after", valid_after), ("valid-before", valid_before)):
        # A negative one used to be written into the calldata as a '-' and exit 0.
        if isinstance(moment, bool) or not isinstance(moment, int) or moment < 0:
            raise QuoteError(f"--{name} is not a unix time (whole seconds, not negative)")
    accept = _accept(quote)
    extra = accept.get("extra") if isinstance(accept.get("extra"), dict) else {}
    if nonce:
        if not is_nonce(nonce):
            raise QuoteError("the payment nonce given is not 32 bytes of 0x-prefixed hex")
    else:
        nonce = quote.get("nonce") or extra.get("nonce")
        if not nonce:
            raise QuoteError("402 carried no payment nonce; this hearth is unbound")
    for field in ("name", "version", "chainId", "verifyingContract"):
        if not extra.get(field):
            raise QuoteError(f"402 'extra' is missing the EIP-712 domain field {field!r}")
    # Everything below is copied into what the wallet signs and into the calldata.
    # A value that is not what its type says comes back as a wallet error at best,
    # and at worst as a transaction the token contract reverts after gas is spent.
    if not is_nonce(nonce):
        raise QuoteError("402 payment nonce is not 32 bytes of 0x-prefixed hex")
    chain_id = whole_number(extra["chainId"])
    if chain_id is None:
        raise QuoteError("402 'extra' chainId is not a positive whole number")
    if not is_address(extra["verifyingContract"]):
        raise QuoteError("402 'extra' verifyingContract is not an address")
    if not is_address(accept.get("payTo")):
        raise QuoteError("402 'accepts' entry names no address to pay (payTo)")
    amount = whole_number(accept.get("maxAmountRequired"))
    if amount is None:
        raise QuoteError(
            "402 'accepts' entry names no amount to pay "
            "(maxAmountRequired, a positive whole number of base units)"
        )
    return {
        "types": EIP712_TYPES,
        "primaryType": "TransferWithAuthorization",
        "domain": {
            "name": extra["name"],
            "version": str(extra["version"]),
            "chainId": chain_id,
            "verifyingContract": extra["verifyingContract"],
        },
        "message": {
            "from": sender,
            "to": accept["payTo"],
            "value": str(amount),
            "validAfter": str(valid_after),
            "validBefore": str(valid_before),
            "nonce": nonce,
        },
    }


def split_signature(signature: str) -> tuple[int, str, str]:
    """65-byte wallet signature → (v, r, s). Accepts v as 0/1 or 27/28.

    Anything else is refused rather than passed on: r and s go into the calldata
    as written, and a v the token cannot recover a signer from makes a
    transaction that is sent, pays gas and reverts."""
    raw = signature[2:] if signature.startswith("0x") else signature
    if len(raw) != 130:
        raise QuoteError("signature must be 65 bytes (132 chars with 0x)")
    for name, part in (("r", raw[0:64]), ("s", raw[64:128]), ("v", raw[128:130])):
        if not _is_hex(part):
            raise QuoteError(f"signature {name} is not hex")
    r = "0x" + raw[0:64]
    s = "0x" + raw[64:128]
    v = int(raw[128:130], 16)
    if v in (0, 1):
        v += 27
    if v not in (27, 28):
        raise QuoteError(f"signature v is {v}: a recovery id is 27 or 28 (or 0 or 1)")
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
