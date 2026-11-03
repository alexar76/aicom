"""Ed25519 against the RFC 8032 vectors, and strict verification (KI-6 self-check, 2026-10-12).

OpenSSL (`cryptography`) accepts, under the identity public key, R = identity, S = 0 for every
message; an all-zero key is forgeable after a few tries. No secret exists for these keys, so a peer,
provider or issuer announcing one would be impersonable by anybody. `Signer.verify` (every hub
signature path, hybrid included) refuses small-order keys and small-order R, as libsodium does.
"""

from __future__ import annotations

import base64

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from aimarket_hub.signing import Signer, has_small_order
from aimarket_hub.supply_chain_admission import _decode_public_key

b64 = lambda b: base64.b64encode(b).decode()  # noqa: E731

RFC8032 = [  # RFC 8032 §7.1 TEST 1 and TEST 2
    ("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60",
     "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a", "",
     "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b"),
    ("4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb",
     "3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c", "r",
     "92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00"),
]
SMALL_ORDER_POINTS = [bytes.fromhex(h) for h in (
    "0000000000000000000000000000000000000000000000000000000000000000",
    "0000000000000000000000000000000000000000000000000000000000000080",
    "0100000000000000000000000000000000000000000000000000000000000000",
    "26e8958fc2b227b045c3f489f2ef98f0d5dfac05d3c63339b13802886d53fc05",
    "26e8958fc2b227b045c3f489f2ef98f0d5dfac05d3c63339b13802886d53fc85",
    "c7176a703d4dd84fba3c0b760d10670f2a2053fa2c39ccc64ec7fd7792ac037a",
    "c7176a703d4dd84fba3c0b760d10670f2a2053fa2c39ccc64ec7fd7792ac03fa",
    "ecffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff7f",
)]
IDENTITY = bytes.fromhex("01" + "00" * 31)


@pytest.mark.parametrize("sk,pk,msg,sig", RFC8032)
def test_rfc8032_vectors(sk, pk, msg, sig):
    key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(sk))
    raw = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    assert raw.hex() == pk and key.sign(msg.encode()).hex() == sig
    assert Signer.verify(b64(bytes.fromhex(pk)), b64(bytes.fromhex(sig)), msg) is True
    assert Signer.verify(b64(bytes.fromhex(pk)), b64(bytes.fromhex(sig)), msg + "x") is False


def test_small_order_points_are_recognised():
    assert all(has_small_order(p) for p in SMALL_ORDER_POINTS)
    raw = Ed25519PrivateKey.generate().public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    assert has_small_order(raw) is False


def test_the_identity_key_forgery_is_refused_on_every_hub_path():
    forged = b64(IDENTITY + bytes(32))
    for msg in ("receipt: price_usd 0", "manifest of somebody else"):
        assert Signer.verify(b64(IDENTITY), forged, msg) is False
        assert Signer.verify_hybrid(b64(IDENTITY), {"value": forged}, msg) is False


def test_a_small_order_r_is_refused_under_an_honest_key():
    key = Ed25519PrivateKey.generate()
    pk = b64(key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw))
    sig = key.sign(b"m")
    assert Signer.verify(pk, b64(sig), "m") is True
    for r in SMALL_ORDER_POINTS:
        assert Signer.verify(pk, b64(r + sig[32:]), "m") is False


def test_a_placeholder_auditor_key_is_refused():
    for p in (bytes(32), IDENTITY):
        with pytest.raises(ValueError, match="small-order"):
            _decode_public_key(b64(p))
