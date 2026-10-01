"""Hand-written base58btc and the multibase ``z`` prefix (SPEC.md section 5.1, 6.1).

base58btc is needed in two places -- the ``did:key`` method-specific identifier and
``proof.proofValue`` -- and is implemented here rather than pulled in as a dependency so
that the reference implementation has no dependency beyond ``cryptography``.

The leading-zero rule is the part implementations get wrong: base58 is a big-integer
encoding, which loses leading zero bytes, so each leading 0x00 byte of the input is
encoded as one explicit ``1`` character.  An Ed25519 public key beginning with 0x00 would
otherwise decode to 31 bytes.
"""

from __future__ import annotations

BITCOIN_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_INDEX = {char: value for value, char in enumerate(BITCOIN_ALPHABET)}

MULTIBASE_BASE58BTC = "z"


def b58encode(data: bytes) -> str:
    """Encode *data* with the Bitcoin base58 alphabet."""
    if not isinstance(data, (bytes, bytearray)):
        raise TypeError("b58encode() expects bytes")
    data = bytes(data)
    zeros = 0
    for byte in data:
        if byte != 0:
            break
        zeros += 1
    number = int.from_bytes(data, "big")
    chars = []
    while number > 0:
        number, remainder = divmod(number, 58)
        chars.append(BITCOIN_ALPHABET[remainder])
    chars.reverse()
    return BITCOIN_ALPHABET[0] * zeros + "".join(chars)


def b58decode(text: str) -> bytes:
    """Decode Bitcoin base58 *text*.

    Raises ``ValueError`` on any character outside the alphabet; the caller decides which
    AWR reason code that maps to.
    """
    if not isinstance(text, str):
        raise TypeError("b58decode() expects str")
    zeros = 0
    for char in text:
        if char != BITCOIN_ALPHABET[0]:
            break
        zeros += 1
    number = 0
    for char in text[zeros:]:
        try:
            number = number * 58 + _INDEX[char]
        except KeyError:
            raise ValueError(
                "character %r is not in the base58btc alphabet" % (char,)
            )
    if number == 0:
        body = b""
    else:
        length = (number.bit_length() + 7) // 8
        body = number.to_bytes(length, "big")
    return b"\x00" * zeros + body


def multibase_encode_base58btc(data: bytes) -> str:
    """Return ``z`` followed by base58btc of *data*."""
    return MULTIBASE_BASE58BTC + b58encode(data)


def multibase_decode_base58btc(text: str) -> bytes:
    """Decode a multibase string that MUST use the base58btc (``z``) prefix."""
    if not isinstance(text, str) or not text:
        raise ValueError("multibase value must be a non-empty string")
    prefix, body = text[0], text[1:]
    if prefix != MULTIBASE_BASE58BTC:
        raise ValueError(
            "multibase prefix %r is not base58btc (%r)"
            % (prefix, MULTIBASE_BASE58BTC)
        )
    if not body:
        raise ValueError("multibase value has an empty body")
    return b58decode(body)
