"""SHA-256 digests and W3C SRI digest references (SPEC.md sections 3.2, 8.1).

An SRI string in AWR/2 is exactly ``sha256-`` followed by *standard, padded* base64
(``+/`` alphabet) of the 32-byte digest.  base64url is not accepted: a digest reference is
inside the signature, so accepting a second spelling of the same value would mean two
documents with different bytes make the same claim.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import re
from typing import Any, Tuple

from .jcs import canonicalize

#: The only digest algorithm defined in AWR/2 (section 3.2).
SRI_ALGORITHM = "sha256"

_SRI_RE = re.compile(r"^([A-Za-z0-9]+)-([A-Za-z0-9+/]+={0,2})$")


def sha256(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


def canonical_bytes(value: Any) -> bytes:
    """The section 4 canonical form of *value*."""
    return canonicalize(value)


def canonical_digest(value: Any) -> bytes:
    """SHA-256 over the section 4 canonical form of *value*."""
    return sha256(canonicalize(value))


def sri_encode(digest: bytes, algorithm: str = SRI_ALGORITHM) -> str:
    """Encode a raw digest as an SRI string."""
    if len(digest) != 32 and algorithm == SRI_ALGORITHM:
        raise ValueError("a sha256 digest is 32 bytes, got %d" % (len(digest),))
    return "%s-%s" % (algorithm, base64.b64encode(digest).decode("ascii"))


def canonical_sri(value: Any) -> str:
    """``sha256-<base64>`` over the canonical form of *value*."""
    return sri_encode(canonical_digest(value))


def parse_sri(text: Any) -> Tuple[str, bytes]:
    """Parse an SRI string, returning ``(algorithm, digest_bytes)``.

    Raises ``ValueError`` with a message distinguishing a malformed string from an
    unsupported algorithm; callers map both to their field's reason code (section 3.2
    mandates ``AWR-CHAIN-002`` for a digest reference).
    """
    if not isinstance(text, str):
        raise ValueError("digest reference must be a string, got %s" % type(text).__name__)
    match = _SRI_RE.match(text)
    if match is None:
        raise ValueError("%r is not a W3C SRI string of the form <alg>-<base64>" % (text,))
    algorithm, payload = match.group(1), match.group(2)
    if algorithm != SRI_ALGORITHM:
        raise ValueError(
            "digest algorithm %r is not supported in AWR/2 (only %r)"
            % (algorithm, SRI_ALGORITHM)
        )
    # Standard base64 with padding: 32 bytes is exactly 44 characters ending in one '='.
    if len(payload) != 44 or not payload.endswith("="):
        raise ValueError(
            "%r is not standard padded base64 of a 32-byte digest" % (payload,)
        )
    try:
        digest = base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("base64 payload does not decode: %s" % (exc,))
    if len(digest) != 32:
        raise ValueError("sha256 digest must be 32 bytes, got %d" % (len(digest),))
    # §3.2: the encoding must be canonical. 32 bytes is not a multiple of 3, so the last
    # base64 character carries four bits that decode to nothing; base64 therefore admits
    # 16 spellings of every digest, and b64decode(validate=True) accepts all of them. A
    # digest reference is used as an identity — AWR-CHAIN-006 compares these strings to
    # catch a parent claimed twice with conflicting digests — so one digest must have
    # exactly one string. Re-encoding is the cheapest exact test.
    if base64.b64encode(digest).decode("ascii") != payload:
        raise ValueError(
            "%r is a non-canonical base64 encoding: the unused trailing bits are not zero "
            "(canonical form is %r)" % (payload, base64.b64encode(digest).decode("ascii"))
        )
    return algorithm, digest


def is_valid_sri(text: Any) -> bool:
    try:
        parse_sri(text)
    except ValueError:
        return False
    return True
