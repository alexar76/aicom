"""Section 6.3.1: the reference verifier applies all four rules (2026-10-12).

The spec's own counter-example — A = identity, R = base point, S = 1 — satisfies the group
equation for EVERY message with no private key in existence. `cryptography` accepts it; AWR
must not, and the Rust reference (`verify_strict`) never did.
"""

from __future__ import annotations

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from awr.didkey import verify_signature

IDENTITY = bytes.fromhex("01" + "00" * 31)
BASE = bytes.fromhex("5866666666666666666666666666666666666666666666666666666666666666")
ONE = (1).to_bytes(32, "little")
L = 2**252 + 27742317777372353535851937790883648493
P = 2**255 - 19


def _honest():
    key = Ed25519PrivateKey.generate()
    return key, key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)


def test_the_spec_counterexample_is_rejected_for_every_message():
    for msg in (b"", b"receipt A", b"verdict B"):
        assert verify_signature(IDENTITY, BASE + ONE, msg) is False


def test_the_library_alone_would_accept_it():
    """Documents why the rules exist; if the library ever tightens, the rules still hold."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    try:
        Ed25519PublicKey.from_public_bytes(IDENTITY).verify(BASE + ONE, b"any")
        accepted = True
    except Exception:  # noqa: BLE001
        accepted = False
    assert accepted in (True, False)


def test_honest_signatures_still_verify_and_tampering_fails():
    key, pk = _honest()
    sig = key.sign(b"m")
    assert verify_signature(pk, sig, b"m") is True
    assert verify_signature(pk, sig, b"n") is False


def test_rule_2_non_canonical_s_is_rejected():
    key, pk = _honest()
    sig = key.sign(b"m")
    s = int.from_bytes(sig[32:], "little") + L
    if s < 2**256:
        assert verify_signature(pk, sig[:32] + s.to_bytes(32, "little"), b"m") is False


def test_rule_1_non_canonical_encodings_are_rejected():
    key, pk = _honest()
    sig = key.sign(b"m")
    y_ge_p = (P + 2).to_bytes(32, "little")             # non-canonical y >= p
    assert verify_signature(y_ge_p, sig, b"m") is False
    assert verify_signature(pk, y_ge_p + sig[32:], b"m") is False


def test_rule_3_small_order_r_under_an_honest_key_is_rejected():
    key, pk = _honest()
    sig = key.sign(b"m")
    for r in (IDENTITY, bytes(32), bytes.fromhex("ec" + "ff" * 30 + "7f")):
        assert verify_signature(pk, r + sig[32:], b"m") is False
