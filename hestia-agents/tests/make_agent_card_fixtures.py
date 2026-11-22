"""Make agent_card_fixtures.json: an A2A 1.0 card signed four ways, with the JWKS that verifies it.

    uv run --project ../hestia python tests/make_agent_card_fixtures.py

These are fixtures, made here with throwaway keys, not cards found in the wild. The signer is the
`cryptography` library, independent of the agent's own verifier, and the canonical payload is
`json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=False)`, which equals RFC 8785 for a
card with ASCII keys and no fractional numbers. The card is the specification's own example (section
8.4.1) with an empty `capabilities.extensions`, so the a2a-python form (empty values removed)
differs from the card as served:

  es-1  ES256 over the card with empty values removed (a2a-python signing.py) ed-1  EdDSA over the
  card as served rs-1  RS256 (2048-bit) over the card with empty values removed ps-1  PS256 over the
  card with empty values removed

A second copy of the card, `card_dids`, carries the key forms found on signed cards in the wild
(2026-11-21: 183 signed cards among 2,923 served by the MCP registry's remote hosts):

  did:web:example.com#key-1     ES256, its DID document (publicKeyJwk) in `did_document`
  did:key:z6Mk...               EdDSA, the key inside the identifier (self-certifying) es256k-1 with
  jwk embedded    ES256K (secp256k1, RFC 8812) with the key in the protected header b64-1
  EdDSA with RFC 7797 b64:false (the payload signed unencoded),
                                key in `jwks`

ECDSA and PSS signatures are randomised, so a rerun writes different signatures that verify alike.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, ed25519, padding, rsa
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

OUT = Path(__file__).parent / "agent_card_fixtures.json"


def b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def num(value: int, size: int | None = None) -> str:
    size = size or (value.bit_length() + 7) // 8
    return b64url(value.to_bytes(size, "big"))


def b58(raw: bytes) -> str:
    alphabet = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    number, out = int.from_bytes(raw, "big"), ""
    while number:
        number, rem = divmod(number, 58)
        out = alphabet[rem] + out
    return "1" * (len(raw) - len(raw.lstrip(b"\x00"))) + out


def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def clean(value):
    if isinstance(value, dict):
        out = {k: c for k, v in value.items() if (c := clean(v)) is not None}
        return out or None
    if isinstance(value, list):
        out = [c for v in value if (c := clean(v)) is not None]
        return out or None
    if value is None or value == "":
        return None
    return value


CARD = {
    "name": "Example Agent",
    "description": "An example agent that echoes messages.",
    "supportedInterfaces": [
        {
            "url": "https://example.com/a2a/v1",
            "protocolBinding": "JSONRPC",
            "protocolVersion": "1.0",
        }
    ],
    "version": "1.0.0",
    "capabilities": {"streaming": False, "pushNotifications": False, "extensions": []},
    "defaultInputModes": ["text/plain"],
    "defaultOutputModes": ["text/plain"],
    "skills": [
        {"id": "echo", "name": "Echo", "description": "Echoes the input.", "tags": ["echo"]}
    ],
    "securitySchemes": {"bearer": {"httpAuthSecurityScheme": {"scheme": "Bearer"}}},
}


def main() -> None:
    served = canonical(CARD)
    cleaned = canonical(clean(CARD))
    assert served != cleaned
    es = ec.generate_private_key(ec.SECP256R1())
    ed = ed25519.Ed25519PrivateKey.generate()
    rs = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ps = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jku = "https://example.com/.well-known/jwks.json"
    signatures, keys = [], []

    def protected(alg: str, kid: str) -> str:
        return b64url(
            json.dumps(
                {"alg": alg, "typ": "JOSE", "kid": kid, "jku": jku}, separators=(",", ":")
            ).encode()
        )

    def add(alg: str, kid: str, payload: bytes, sign) -> None:
        head = protected(alg, kid)
        signing_input = (head + "." + b64url(payload)).encode()
        signatures.append({"protected": head, "signature": b64url(sign(signing_input))})

    def es256(data: bytes) -> bytes:
        r, s = decode_dss_signature(es.sign(data, ec.ECDSA(hashes.SHA256())))
        return r.to_bytes(32, "big") + s.to_bytes(32, "big")

    add("ES256", "es-1", cleaned, es256)
    add("EdDSA", "ed-1", served, ed.sign)
    add("RS256", "rs-1", cleaned, lambda d: rs.sign(d, padding.PKCS1v15(), hashes.SHA256()))
    add(
        "PS256",
        "ps-1",
        cleaned,
        lambda d: ps.sign(
            d, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=32), hashes.SHA256()
        ),
    )
    numbers = es.public_key().public_numbers()
    keys.append(
        {
            "kty": "EC",
            "crv": "P-256",
            "kid": "es-1",
            "use": "sig",
            "alg": "ES256",
            "x": num(numbers.x, 32),
            "y": num(numbers.y, 32),
        }
    )
    raw = ed.public_key().public_bytes_raw()
    keys.append({"kty": "OKP", "crv": "Ed25519", "kid": "ed-1", "x": b64url(raw)})
    for kid, key, alg in (("rs-1", rs, "RS256"), ("ps-1", ps, "PS256")):
        n = key.public_key().public_numbers()
        keys.append({"kty": "RSA", "kid": kid, "alg": alg, "n": num(n.n), "e": num(n.e)})
    signed = dict(CARD, signatures=signatures)

    # The DID forms, over the card as served.
    dids = []
    web = ec.generate_private_key(ec.SECP256R1())
    head = b64url(
        json.dumps(
            {"alg": "ES256", "typ": "JOSE", "kid": "did:web:example.com#key-1"},
            separators=(",", ":"),
        ).encode()
    )
    r, s_ = decode_dss_signature(
        web.sign((head + "." + b64url(served)).encode(), ec.ECDSA(hashes.SHA256()))
    )
    dids.append(
        {"protected": head, "signature": b64url(r.to_bytes(32, "big") + s_.to_bytes(32, "big"))}
    )
    wn = web.public_key().public_numbers()
    did_document = {
        "@context": ["https://www.w3.org/ns/did/v1"],
        "id": "did:web:example.com",
        "verificationMethod": [
            {
                "id": "did:web:example.com#key-1",
                "type": "JsonWebKey2020",
                "controller": "did:web:example.com",
                "publicKeyJwk": {
                    "kty": "EC",
                    "crv": "P-256",
                    "x": num(wn.x, 32),
                    "y": num(wn.y, 32),
                },
            }
        ],
    }
    dk = ed25519.Ed25519PrivateKey.generate()
    multikey = "z" + b58(b"\xed\x01" + dk.public_key().public_bytes_raw())
    head = b64url(
        json.dumps(
            {"alg": "EdDSA", "typ": "JOSE", "kid": "did:key:" + multikey + "#" + multikey},
            separators=(",", ":"),
        ).encode()
    )
    dids.append(
        {"protected": head, "signature": b64url(dk.sign((head + "." + b64url(served)).encode()))}
    )
    k1 = ec.generate_private_key(ec.SECP256K1())
    kn = k1.public_key().public_numbers()
    head = b64url(
        json.dumps(
            {
                "alg": "ES256K",
                "kid": "es256k-1",
                "jwk": {"kty": "EC", "crv": "secp256k1", "x": num(kn.x, 32), "y": num(kn.y, 32)},
            },
            separators=(",", ":"),
        ).encode()
    )
    r, s_ = decode_dss_signature(
        k1.sign((head + "." + b64url(served)).encode(), ec.ECDSA(hashes.SHA256()))
    )
    dids.append(
        {"protected": head, "signature": b64url(r.to_bytes(32, "big") + s_.to_bytes(32, "big"))}
    )
    b64k = ed25519.Ed25519PrivateKey.generate()
    head = b64url(
        json.dumps(
            {"alg": "EdDSA", "kid": "b64-1", "b64": False, "crit": ["b64"]}, separators=(",", ":")
        ).encode()
    )
    dids.append({"protected": head, "signature": b64url(b64k.sign(head.encode() + b"." + served))})
    keys.append(
        {
            "kty": "OKP",
            "crv": "Ed25519",
            "kid": "b64-1",
            "x": b64url(b64k.public_key().public_bytes_raw()),
        }
    )
    card_dids = dict(CARD, signatures=dids)
    OUT.write_text(
        json.dumps(
            {
                "card": signed,
                "jwks": {"keys": keys},
                "jku": jku,
                "card_dids": card_dids,
                "did_document": did_document,
                "did_key": multikey,
                "payload_served": served.decode(),
                "payload_cleaned": cleaned.decode(),
            },
            indent=1,
        )
        + "\n"
    )
    print("wrote", OUT)


if __name__ == "__main__":
    main()
