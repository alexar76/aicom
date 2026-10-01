"""base58btc, ``did:key`` and key consistency (SPEC.md section 5)."""

from __future__ import annotations

import pytest
from conftest import assert_raises_code, deterministic_key

from awr.didkey import (
    KNOWN_OTHER_KEY_MULTICODECS,
    MULTICODEC_ED25519_PUB,
    SigningKey,
    check_public_key_jwk,
    derive_did_key,
    parse_did_key,
    verification_method_for,
)
from awr.multibase import (
    BITCOIN_ALPHABET,
    b58decode,
    b58encode,
    multibase_encode_base58btc,
)

# ---------------------------------------------------------------------------
# base58btc known answers
# ---------------------------------------------------------------------------


def test_base58btc_known_answer_from_the_multibase_specification():
    """The multibase specification's own example: base58btc("hello world")."""
    assert b58encode(b"hello world") == "StV1DL6CwTryKyV"
    assert multibase_encode_base58btc(b"hello world") == "zStV1DL6CwTryKyV"
    assert b58decode("StV1DL6CwTryKyV") == b"hello world"


def test_base58btc_alphabet_excludes_the_ambiguous_characters():
    assert BITCOIN_ALPHABET.startswith("123456789A")
    for char in "0OIl":
        assert char not in BITCOIN_ALPHABET
    assert len(BITCOIN_ALPHABET) == 58


def test_leading_zero_bytes_become_explicit_ones():
    # base58 is a big-integer encoding and loses leading zeros; each 0x00 byte is encoded
    # as one '1'.  Without this an Ed25519 key starting with 0x00 decodes to 31 bytes.
    assert b58encode(b"\x00") == "1"
    assert b58encode(b"\x00\x00") == "11"
    assert b58encode(b"\x00\x00hello world") == "11StV1DL6CwTryKyV"
    assert b58decode("11StV1DL6CwTryKyV") == b"\x00\x00hello world"
    assert b58decode(b58encode(b"\x00" * 5 + b"\xff")) == b"\x00" * 5 + b"\xff"


def test_base58_round_trips_every_byte_length():
    for length in range(0, 40):
        payload = bytes((i * 7 + length) % 256 for i in range(length))
        assert b58decode(b58encode(payload)) == payload


def test_base58_rejects_characters_outside_the_alphabet():
    for bad in ("0", "O", "I", "l", "hello world!"):
        with pytest.raises(ValueError):
            b58decode(bad)


# ---------------------------------------------------------------------------
# did:key
# ---------------------------------------------------------------------------


def test_did_key_shape_matches_section_5_1():
    key = deterministic_key(1)
    did = key.did
    assert did.startswith("did:key:z6Mk")
    method_specific = did[len("did:key:"):]
    assert len(method_specific) == 48
    assert parse_did_key(did) == key.public_key_bytes


def test_did_key_multicodec_is_the_unsigned_varint_for_ed25519_pub():
    from awr.multibase import multibase_decode_base58btc

    key = deterministic_key(2)
    decoded = multibase_decode_base58btc(key.did[len("did:key:"):])
    assert decoded[:2] == MULTICODEC_ED25519_PUB == b"\xed\x01"
    assert decoded[2:] == key.public_key_bytes
    assert len(decoded) == 34


def test_every_generated_key_yields_a_48_character_z6mk_identifier():
    for tag in range(1, 12):
        did = deterministic_key(tag).did
        assert did.startswith("did:key:z6Mk"), did
        assert len(did) == len("did:key:") + 48, did


def test_verification_method_is_the_did_plus_its_own_fragment():
    key = deterministic_key(3)
    assert verification_method_for(key.did) == "%s#%s" % (
        key.did,
        key.did[len("did:key:"):],
    )
    assert key.verification_method == verification_method_for(key.did)


def test_derive_did_key_rejects_a_wrong_length_key():
    with pytest.raises(ValueError):
        derive_did_key(b"\x01" * 31)


# ---------------------------------------------------------------------------
# negative cases, section 11.2 AWR-KEY-*
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    [
        "https://issuer.example/keys/1",
        "did:web:issuer.example",
        "did:ion:EiC",
        "z6MktwupdmLXVVqTzCw4i46r4uGyosGXRnR3XjN4Zq7oMMsw",
        42,
        None,
    ],
)
def test_non_did_key_issuers_raise_key_001(value):
    assert_raises_code("AWR-KEY-001", lambda: parse_did_key(value))


@pytest.mark.parametrize(
    "msi",
    [
        "6Mkabc",  # missing the multibase 'z'
        "z0OIl",  # characters outside base58btc
        "z" + b58encode(MULTICODEC_ED25519_PUB + b"\x01" * 31),  # 31-byte key
        "z" + b58encode(MULTICODEC_ED25519_PUB + b"\x01" * 33),  # 33-byte key
        "z" + b58encode(b"\x99\x99" + b"\x01" * 32),  # unknown multicodec
        "z" + b58encode(b"\xed"),  # shorter than the multicodec
        "z6MktwupdmLXVVqTzCw4i46r4uGyosGXRnR3XjN4Zq7oMMsw#z6Mk",  # fragment in issuer.id
    ],
)
def test_malformed_did_keys_raise_key_002(msi):
    assert_raises_code("AWR-KEY-002", lambda: parse_did_key("did:key:" + msi))


@pytest.mark.parametrize("multicodec", sorted(KNOWN_OTHER_KEY_MULTICODECS))
def test_other_key_types_raise_key_004(multicodec):
    did = "did:key:" + multibase_encode_base58btc(multicodec + b"\x01" * 32)
    error = assert_raises_code("AWR-KEY-004", lambda: parse_did_key(did))
    assert KNOWN_OTHER_KEY_MULTICODECS[multicodec] in error.detail


def test_matching_public_key_jwk_is_accepted():
    key = deterministic_key(1)
    check_public_key_jwk(key.public_key_jwk(), key.public_key_bytes)


@pytest.mark.parametrize(
    "jwk",
    [
        {"kty": "EC", "crv": "P-256", "x": "AAAA"},
        {"kty": "OKP", "crv": "X25519", "x": "AAAA"},
        {"kty": "OKP", "crv": "Ed25519"},
        {"kty": "OKP", "crv": "Ed25519", "x": 5},
        {"kty": "OKP", "crv": "Ed25519", "x": "!!!not base64!!!"},
        "not an object",
    ],
)
def test_inconsistent_public_key_jwk_raises_key_003(jwk):
    key = deterministic_key(1)
    assert_raises_code(
        "AWR-KEY-003", lambda: check_public_key_jwk(jwk, key.public_key_bytes)
    )


def test_public_key_jwk_naming_another_key_raises_key_003():
    key = deterministic_key(1)
    other = deterministic_key(2)
    assert_raises_code(
        "AWR-KEY-003",
        lambda: check_public_key_jwk(other.public_key_jwk(), key.public_key_bytes),
    )


# ---------------------------------------------------------------------------
# key files (the CLI --key contract)
# ---------------------------------------------------------------------------


def test_key_file_forms_all_load_the_same_key():
    key = deterministic_key(7)
    import json

    from awr.multibase import multibase_encode_base58btc as mb

    forms = [
        json.dumps(key.private_key_jwk()),
        json.dumps({"privateKeySeedHex": key.seed_hex()}),
        json.dumps(
            {"privateKeyMultibase": mb(b"\x80\x26" + bytes.fromhex(key.seed_hex()))}
        ),
        key.seed_hex(),
        "  %s\n" % (key.seed_hex(),),
    ]
    for text in forms:
        assert SigningKey.from_key_file_text(text).did == key.did


def test_key_file_rejects_a_public_only_jwk():
    key = deterministic_key(7)
    import json

    with pytest.raises(ValueError):
        SigningKey.from_key_file_text(json.dumps(key.public_key_jwk()))


def test_key_file_rejects_a_jwk_whose_x_disagrees_with_d():
    key = deterministic_key(7)
    other = deterministic_key(8)
    jwk = key.private_key_jwk()
    jwk["x"] = other.public_key_jwk()["x"]
    import json

    with pytest.raises(ValueError):
        SigningKey.from_key_file_text(json.dumps(jwk))
