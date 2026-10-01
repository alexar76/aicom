"""``did:key`` for Ed25519, and the signing-key handle (SPEC.md section 5).

``did:key:z<base58btc(0xed 0x01 || publicKey)>``.  ``0xed 0x01`` is the unsigned-varint
multicodec identifier for ``ed25519-pub``; the ``z`` is multibase base58btc.  A verifier
derives the key from the DID, so no network lookup and no key selection ever happens.
"""

from __future__ import annotations

import base64
import binascii
import json
import re
from typing import Any, Dict, Optional

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)

from .errors import (
    AWR_KEY_001,
    AWR_KEY_002,
    AWR_KEY_003,
    AWR_KEY_004,
    AwrError,
)
from .multibase import (
    b58decode,
    multibase_decode_base58btc,
    multibase_encode_base58btc,
)

DID_KEY_PREFIX = "did:key:"

#: Unsigned-varint multicodec for ed25519-pub.
MULTICODEC_ED25519_PUB = b"\xed\x01"
#: Unsigned-varint multicodec for ed25519-priv, used by the optional key-file form.
MULTICODEC_ED25519_PRIV = b"\x80\x26"

#: Multicodecs that name a real public key of a type AWR/2 does not support.  Telling
#: these apart from garbage is the difference between AWR-KEY-004 and AWR-KEY-002.
KNOWN_OTHER_KEY_MULTICODECS = {
    b"\xe7\x01": "secp256k1-pub",
    b"\xec\x01": "x25519-pub",
    b"\xea\x01": "bls12_381-g1-pub",
    b"\xeb\x01": "bls12_381-g2-pub",
    b"\x80\x24": "p256-pub",
    b"\x81\x24": "p384-pub",
    b"\x82\x24": "p521-pub",
    b"\x85\x24": "rsa-pub",
}

_DID_KEY_MSI_RE = re.compile(r"^z[1-9A-HJ-NP-Za-km-z]+$")


def derive_did_key(public_key_bytes: bytes) -> str:
    """Derive the ``did:key`` DID of a raw 32-byte Ed25519 public key."""
    if len(public_key_bytes) != 32:
        raise ValueError(
            "an Ed25519 public key is 32 bytes, got %d" % (len(public_key_bytes),)
        )
    return DID_KEY_PREFIX + multibase_encode_base58btc(
        MULTICODEC_ED25519_PUB + bytes(public_key_bytes)
    )


def method_specific_id(did: str) -> str:
    """The part of a ``did:key`` after the method prefix (the ``z...`` multibase string)."""
    if not isinstance(did, str) or not did.startswith(DID_KEY_PREFIX):
        raise AwrError(AWR_KEY_001, "issuer.id %r is not a did:key" % (did,))
    return did[len(DID_KEY_PREFIX):]


def parse_did_key(did: Any) -> bytes:
    """Return the raw 32-byte Ed25519 public key named by *did*.

    Raises ``AWR-KEY-001`` when this is not a ``did:key`` at all, ``AWR-KEY-004`` when it
    is a well-formed ``did:key`` for a key type AWR/2 does not support, and
    ``AWR-KEY-002`` on any other deviation (section 5.1).
    """
    if not isinstance(did, str):
        raise AwrError(
            AWR_KEY_001, "issuer.id must be a string, got %s" % type(did).__name__
        )
    if not did.startswith(DID_KEY_PREFIX):
        raise AwrError(AWR_KEY_001, "issuer.id %r is not a did:key" % (did,))
    msi = did[len(DID_KEY_PREFIX):]
    if "#" in msi or "?" in msi or "/" in msi:
        raise AwrError(
            AWR_KEY_002,
            "did:key %r carries a fragment, path or query; issuer.id must be the bare DID"
            % (did,),
        )
    if not msi.startswith("z"):
        raise AwrError(
            AWR_KEY_002,
            "did:key multibase prefix must be 'z' (base58btc), got %r" % (msi[:1],),
        )
    if _DID_KEY_MSI_RE.match(msi) is None:
        raise AwrError(
            AWR_KEY_002,
            "did:key method-specific id %r is not base58btc" % (msi,),
        )
    try:
        decoded = multibase_decode_base58btc(msi)
    except ValueError as exc:
        raise AwrError(AWR_KEY_002, "did:key is not decodable: %s" % (exc,))
    if len(decoded) < 2:
        raise AwrError(AWR_KEY_002, "did:key payload is shorter than its multicodec")
    multicodec = decoded[:2]
    key_bytes = decoded[2:]
    if multicodec == MULTICODEC_ED25519_PUB:
        if len(key_bytes) != 32:
            raise AwrError(
                AWR_KEY_002,
                "ed25519-pub multicodec with %d key bytes, expected 32"
                % (len(key_bytes),),
            )
        return key_bytes
    other = KNOWN_OTHER_KEY_MULTICODECS.get(multicodec)
    if other is not None:
        raise AwrError(
            AWR_KEY_004,
            "did:key names a %s key; AWR/2 supports only ed25519-pub (0xed 0x01)"
            % (other,),
        )
    raise AwrError(
        AWR_KEY_002,
        "unrecognised multicodec 0x%s in did:key" % (multicodec.hex(),),
    )


def verification_method_for(did: str) -> str:
    """``<did>#<method-specific-id>`` (section 5.3)."""
    return "%s#%s" % (did, method_specific_id(did))


def b64url_decode(text: str) -> bytes:
    """Decode unpadded or padded base64url."""
    if not isinstance(text, str):
        raise ValueError("base64url value must be a string")
    padding = "=" * (-len(text) % 4)
    try:
        return base64.urlsafe_b64decode(text + padding)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("not valid base64url: %s" % (exc,))


def b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def check_public_key_jwk(jwk: Any, public_key_bytes: bytes) -> None:
    """Check an optional ``issuer.publicKeyJwk`` against the ``did:key`` (section 5.2).

    Any disagreement is ``AWR-KEY-003`` and invalidates the document: two statements of
    the signing key inside one signed document is a downgrade surface, not redundancy.
    """
    if not isinstance(jwk, dict):
        raise AwrError(
            AWR_KEY_003,
            "publicKeyJwk must be an object, got %s" % type(jwk).__name__,
        )
    if jwk.get("kty") != "OKP":
        raise AwrError(
            AWR_KEY_003, "publicKeyJwk.kty must be 'OKP', got %r" % (jwk.get("kty"),)
        )
    if jwk.get("crv") != "Ed25519":
        raise AwrError(
            AWR_KEY_003,
            "publicKeyJwk.crv must be 'Ed25519', got %r" % (jwk.get("crv"),),
        )
    x = jwk.get("x")
    if not isinstance(x, str):
        raise AwrError(AWR_KEY_003, "publicKeyJwk.x missing or not a string")
    try:
        decoded = b64url_decode(x)
    except ValueError as exc:
        raise AwrError(AWR_KEY_003, "publicKeyJwk.x does not decode: %s" % (exc,))
    if decoded != public_key_bytes:
        raise AwrError(
            AWR_KEY_003,
            "publicKeyJwk.x names a different key than issuer.id",
        )


def public_key_from_bytes(public_key_bytes: bytes) -> Ed25519PublicKey:
    return Ed25519PublicKey.from_public_bytes(public_key_bytes)


def verify_signature(public_key_bytes: bytes, signature: bytes, message: bytes) -> bool:
    """Pure Ed25519 verification (RFC 8032)."""
    try:
        public_key_from_bytes(public_key_bytes).verify(signature, message)
    except (InvalidSignature, ValueError):
        return False
    return True


class SigningKey:
    """An Ed25519 private key with its AWR identity.

    ``SigningKey`` is the only way to sign in this package, and it is deliberately unable
    to produce an AWR/1 proof (section 12: an implementation MUST NOT issue AWR/1).
    """

    def __init__(self, private_key: Ed25519PrivateKey) -> None:
        self._private = private_key
        self._public_bytes = private_key.public_key().public_bytes(
            Encoding.Raw, PublicFormat.Raw
        )

    # -- construction ---------------------------------------------------------

    @classmethod
    def generate(cls) -> "SigningKey":
        return cls(Ed25519PrivateKey.generate())

    @classmethod
    def from_seed(cls, seed: bytes) -> "SigningKey":
        if len(seed) != 32:
            raise ValueError("an Ed25519 seed is 32 bytes, got %d" % (len(seed),))
        return cls(Ed25519PrivateKey.from_private_bytes(bytes(seed)))

    @classmethod
    def from_jwk(cls, jwk: Dict[str, Any]) -> "SigningKey":
        if not isinstance(jwk, dict):
            raise ValueError("JWK must be an object")
        if jwk.get("kty") != "OKP" or jwk.get("crv") != "Ed25519":
            raise ValueError("key file must be an RFC 8037 OKP/Ed25519 JWK")
        d = jwk.get("d")
        if not isinstance(d, str):
            raise ValueError("JWK is a public key: no 'd' member")
        key = cls.from_seed(b64url_decode(d))
        x = jwk.get("x")
        if isinstance(x, str) and b64url_decode(x) != key.public_key_bytes:
            raise ValueError("JWK 'x' does not match the key derived from 'd'")
        return key

    @classmethod
    def from_key_file_text(cls, text: str) -> "SigningKey":
        """Load a private key from the CLI ``--key`` file.

        Accepted forms (section 17 does not specify one; see README):

        * an RFC 8037 OKP/Ed25519 JWK object with ``d``
        * ``{"privateKeySeedHex": "<64 hex chars>"}``
        * ``{"privateKeyMultibase": "z<base58btc(0x80 0x26 || seed)>"}``
        * a bare 64-hex-character seed on a single line
        """
        stripped = text.strip()
        if stripped.startswith("{"):
            try:
                data = json.loads(stripped)
            except ValueError as exc:
                raise ValueError("key file is not valid JSON: %s" % (exc,))
            if not isinstance(data, dict):
                raise ValueError("key file JSON must be an object")
            if "kty" in data:
                return cls.from_jwk(data)
            for member in ("privateKeySeedHex", "seedHex"):
                if member in data:
                    return cls.from_seed(bytes.fromhex(str(data[member])))
            if "privateKeyMultibase" in data:
                decoded = multibase_decode_base58btc(str(data["privateKeyMultibase"]))
                if decoded[:2] != MULTICODEC_ED25519_PRIV:
                    raise ValueError(
                        "privateKeyMultibase multicodec is not ed25519-priv (0x80 0x26)"
                    )
                return cls.from_seed(decoded[2:])
            raise ValueError(
                "key file object has none of kty / privateKeySeedHex / "
                "privateKeyMultibase"
            )
        if stripped.startswith("z"):
            decoded = b58decode(stripped[1:])
            if decoded[:2] == MULTICODEC_ED25519_PRIV:
                return cls.from_seed(decoded[2:])
            raise ValueError("multibase key file is not an ed25519-priv value")
        try:
            raw = bytes.fromhex(stripped)
        except ValueError:
            raise ValueError(
                "key file is neither JSON, a multibase value, nor a hex seed"
            )
        return cls.from_seed(raw)

    # -- identity -------------------------------------------------------------

    @property
    def public_key_bytes(self) -> bytes:
        return self._public_bytes

    @property
    def did(self) -> str:
        return derive_did_key(self._public_bytes)

    @property
    def verification_method(self) -> str:
        return verification_method_for(self.did)

    def public_key_jwk(self) -> Dict[str, str]:
        return {
            "kty": "OKP",
            "crv": "Ed25519",
            "x": b64url_encode(self._public_bytes),
        }

    def private_key_jwk(self) -> Dict[str, str]:
        seed = self._private.private_bytes(
            Encoding.Raw, PrivateFormat.Raw, NoEncryption()
        )
        jwk = self.public_key_jwk()
        jwk["d"] = b64url_encode(seed)
        return jwk

    def seed_hex(self) -> str:
        return self._private.private_bytes(
            Encoding.Raw, PrivateFormat.Raw, NoEncryption()
        ).hex()

    # -- signing --------------------------------------------------------------

    def sign(self, message: bytes) -> bytes:
        """Pure Ed25519 signature over *message* (RFC 8032), 64 bytes."""
        return self._private.sign(message)


def load_key_file(path: str) -> SigningKey:
    with open(path, "r", encoding="utf-8") as handle:
        return SigningKey.from_key_file_text(handle.read())


def optional_public_key_from_jwk(jwk: Any) -> Optional[bytes]:
    """Best-effort raw key from a JWK, used by the AWR/1 legacy path (section 12)."""
    if not isinstance(jwk, dict):
        return None
    x = jwk.get("x")
    if not isinstance(x, str):
        return None
    try:
        decoded = b64url_decode(x)
    except ValueError:
        return None
    return decoded if len(decoded) == 32 else None
