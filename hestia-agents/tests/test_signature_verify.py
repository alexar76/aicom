"""signature.verify@v1 against RFC 8032, cryptography, the AWR conformance vectors, a live
HISTOR tree head, and the signers the hub and the hearth actually use.

The AWR vectors were generated with Digital Bazaar's eddsa-jcs-2022 implementation; every
AWR/2 document in valid/ must verify, and every invalid/ vector whose defect is in the
signature, the proof, the key or the canonical bytes must not. Vectors that are invalid for
AWR's own rules (chains, enumerations, profiles) carry genuine signatures and are out of
this checker's scope by design.
"""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

import pytest

from hestia_agents.manifests import handler_source

MONOREPO = Path(__file__).resolve().parent.parent.parent
AWR = MONOREPO / "awr" / "vectors"
STH = json.loads((Path(__file__).parent / "histor_sth_2026-10-04.json").read_text())
HISTOR_DID = "did:key:z6Mkw1CVxsPj9utYp7VXWEbuuGM9Ev47itwKu1UfKd5ByxR9"
HUB_DID = "did:key:z6MktwupdmLXVVqTzCw4i46r4uGyosGXRnR3XjN4Zq7oMMsw"  # RFC 8032 TEST 1 key
RFC_SEEDS = {  # RFC 8032 section 7.1: TEST 1, 2, 3
    "9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60": b"",
    "4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb": b"\x72",
    "c5aa8df43f9f837bedb7442f31dcb7b166d38535076f094b85ce3a2e0b4458f7": b"\xaf\x82",
}
L = 2 ** 252 + 27742317777372353535851937790883648493
SIGNATURE_DEFECTS = [
    "hashdata-halves-swapped", "tampered-id", "tampered-issuer-name", "proof-context-mismatch",
    "proof-cryptosuite-unsupported", "proof-purpose-authentication", "proof-stripped",
    "proof-type-not-dataintegrityproof", "proofvalue-base64", "verificationmethod-other-key",
    "didkey-wrong-key-length", "didkey-x25519", "didkey-base64-truncation",
    "number-integer-valued-float", "number-non-integer", "number-integer-2pow53",
    "price-amount-json-float", "string-lone-surrogate", "duplicate-json-keys",
    "proof-array-awr1-then-awr2", "proof-array-awr2-then-awr1", "awr1-issuer-key-disagrees",
]


@pytest.fixture(scope="module")
def ns():
    namespace: dict = {}
    exec(compile(handler_source("signature-verify"), "signature-verify", "exec"), namespace)  # noqa: S102
    return namespace


@pytest.fixture(scope="module")
def handle(ns):
    return ns["handle"]


def awr(name):
    if not AWR.is_dir():
        pytest.skip("awr/ is not beside this package")
    return json.loads((AWR / (name + ".json")).read_text(encoding="utf-8"))


def ed25519():
    serialization = pytest.importorskip("cryptography.hazmat.primitives.serialization")
    keys = pytest.importorskip("cryptography.hazmat.primitives.asymmetric.ed25519")
    return keys.Ed25519PrivateKey, serialization


# ------------------------------------------------------------------ Ed25519 itself


@pytest.mark.parametrize("seed", sorted(RFC_SEEDS))
def test_rfc8032_vectors_match_cryptography(ns, seed) -> None:
    private_cls, serialization = ed25519()
    private = private_cls.from_private_bytes(bytes.fromhex(seed))
    public = private.public_key().public_bytes(serialization.Encoding.Raw,
                                               serialization.PublicFormat.Raw)
    message = RFC_SEEDS[seed]
    assert ns["ed25519_verify"](public, message, private.sign(message)) == (
        True, "signature verifies")
    assert ns["ed25519_verify"](public, message + b"!", private.sign(message))[0] is False


def test_random_keys_both_ways(ns) -> None:
    private_cls, serialization = ed25519()
    for i in range(25):
        private = private_cls.generate()
        public = private.public_key().public_bytes(serialization.Encoding.Raw,
                                                   serialization.PublicFormat.Raw)
        message = bytes(range(i * 9 % 256)) * 3
        signature = private.sign(message)
        assert ns["ed25519_verify"](public, message, signature)[0] is True
        flipped = bytes([signature[0] ^ 1]) + signature[1:]
        assert ns["ed25519_verify"](public, message, flipped)[0] is False


def test_malleated_and_degenerate_inputs_are_refused(ns) -> None:
    private_cls, serialization = ed25519()
    private = private_cls.from_private_bytes(bytes.fromhex(sorted(RFC_SEEDS)[0]))
    public = private.public_key().public_bytes(serialization.Encoding.Raw,
                                               serialization.PublicFormat.Raw)
    signature = private.sign(b"m")
    s = int.from_bytes(signature[32:], "little")
    malleated = signature[:32] + (s + L).to_bytes(32, "little")
    assert ns["ed25519_verify"](public, b"m", malleated) == (
        False, "signature S is not reduced (S >= L)")
    identity = (1).to_bytes(32, "little")
    assert "small order" in ns["ed25519_verify"](identity, b"m", signature)[1]
    not_on_curve = ((2 ** 255 - 19) + 1).to_bytes(32, "little")  # y >= p
    assert ns["ed25519_verify"](not_on_curve, b"m", signature)[0] is False


def test_did_key_round_trip(ns) -> None:
    raw = bytes.fromhex("d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a")
    assert ns["did_key"](raw) == HUB_DID
    assert ns["_key"](HUB_DID + "#" + HUB_DID[8:], "k") == raw


# ------------------------------------------------------------------ AWR / eddsa-jcs-2022


def test_awr_worked_example_hashes_and_key(handle) -> None:
    entry = awr("proof/worked-example")
    out = handle({"document": awr("proof/worked-example-secured"), "public_key": HUB_DID})
    assert out["format"] == "eddsa-jcs-2022" and out["valid"] is True
    assert out["proofConfigHash"] == entry["proofConfigHash"]
    assert out["transformedDocumentHash"] == entry["transformedDocumentHash"]
    assert out["key"] == {
        "hex": "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a",
        "did": HUB_DID, "source": "pinned"}


def test_every_awr2_valid_document_verifies(handle) -> None:
    if not AWR.is_dir():
        pytest.skip("awr/ is not beside this package")
    checked = 0
    for path in sorted((AWR / "valid").glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        documents = data["documents"] if "awrBundle" in data else [data]
        for doc in documents:
            proofs = doc["proof"] if isinstance(doc["proof"], list) else [doc["proof"]]
            if proofs[0].get("type") != "DataIntegrityProof":
                continue  # AWR/1 legacy dialects: not this checker's suite
            assert handle({"document": doc})["valid"] is True, path.name
            checked += 1
    assert checked >= 90


@pytest.mark.parametrize("name", SIGNATURE_DEFECTS)
def test_awr_signature_level_defects_are_invalid(handle, name) -> None:
    out = handle({"document": awr("invalid/" + name), "format": "eddsa-jcs-2022"})
    assert out["valid"] is False, out


def test_a_pinned_key_that_did_not_sign_is_named(handle, ns) -> None:
    verifier_a = ns["did_key"](bytes.fromhex(
        "3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c"))
    out = handle({"document": awr("proof/worked-example-secured"), "public_key": verifier_a})
    assert out["valid"] is False and "different key" in out["reason"]


def test_proof_set_reports_every_proof(handle) -> None:
    out = handle({"document": awr("valid/receipt-proof-array")})
    assert out["valid"] is True and [p["valid"] for p in out["proofs"]] == [False, True]


# ------------------------------------------------------------------ HISTOR, hearth, hub


def test_live_histor_tree_head(handle) -> None:
    out = handle({"document": STH, "public_key": HISTOR_DID})
    assert out["format"] == "histor" and out["valid"] is True
    forged = dict(STH, treeSize=STH["treeSize"] + 1)
    assert handle({"document": forged, "public_key": HISTOR_DID})["valid"] is False
    self_named = handle({"document": STH})
    assert self_named["valid"] is True and self_named["key"]["source"].startswith("document")


def _hestia_signer(tmp_path):
    path = MONOREPO / "hestia"
    if not path.is_dir():
        pytest.skip("hestia/ is not beside this package")
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
    signing = pytest.importorskip("hestia.signing")
    return signing.ProviderSigner(tmp_path / "provider.key", pqc=False)


def test_a_hearth_answer_against_the_input_that_was_sent(handle, tmp_path) -> None:
    signer = _hestia_signer(tmp_path)
    request = {"op": "root", "leaves": ["00"], "note": "é"}
    result = {"root": "abc", "n": 1.5}
    answer = {"ok": True, "result": result, "provider_pubkey": signer.public_key_b64,
              "signature": signer.sign_result(result, capability_id="merkle.proof@v1",
                                              product_id="hestia-agents", input_payload=request)}
    call = {"document": answer, "input": request, "capability_id": "merkle.proof@v1",
            "product_id": "hestia-agents", "public_key": signer.public_key_b64}
    assert handle(call)["valid"] is True
    assert handle(dict(call, input=dict(request, note="e")))["valid"] is False
    assert handle(dict(call, document=dict(answer, result={"root": "abd", "n": 1.5})))[
        "valid"] is False


def test_a_hearth_signed_object(handle, tmp_path) -> None:
    signer = _hestia_signer(tmp_path)
    document = {"hearth": "https://hestia.example", "tenants": [1, 2]}
    document["signature"] = signer.sign_object(document)
    out = handle({"document": document})
    assert out["format"] == "hub-object" and out["valid"] is True


@pytest.mark.parametrize("extra", [{}, {"reason": "verify_failed", "refunded": True}])
def test_hub_receipts_v1_and_v2(handle, tmp_path, extra) -> None:
    hub = MONOREPO / "aimarket-hub"
    if str(hub) not in sys.path:
        sys.path.insert(0, str(hub))
    signing = pytest.importorskip("aimarket_hub.signing")
    signer = signing.Signer(tmp_path / "hub.key", pqc=False)
    receipt = {"nonce": "0xabc", "product_id": "p", "capability_id": "c@v1", "price_usd": 0.0,
               "timestamp": "2026-10-04T12:00:00Z", "success": 1, "latency_ms": 12, **extra}
    receipt["signature"] = signer.sign_receipt(receipt)
    pinned = signer.public_key_b64
    out = handle({"document": receipt, "public_key": pinned})
    assert out["format"] == "hub-receipt" and out["valid"] is True
    assert out["receipt_version"] == (2 if extra else 1)
    # A browser re-serialises 0.0 as 0; the hub still accepts it, so must this.
    assert handle({"document": dict(receipt, price_usd=0), "public_key": pinned})["valid"] is True
    assert handle({"document": dict(receipt, latency_ms=13), "public_key": pinned})[
        "valid"] is False
    if extra:
        assert handle({"document": dict(receipt, reason="other"), "public_key": pinned})[
            "valid"] is False


# ------------------------------------------------------------------ raw and JCS


def test_raw_messages_in_every_encoding(handle) -> None:
    private_cls, serialization = ed25519()
    private = private_cls.generate()
    public = private.public_key().public_bytes(serialization.Encoding.Raw,
                                               serialization.PublicFormat.Raw)
    signature = private.sign("подпись ✓".encode())
    keys = [public.hex(), base64.b64encode(public).decode(),
            base64.urlsafe_b64encode(public).decode().rstrip("=")]
    sigs = [signature.hex(), base64.b64encode(signature).decode(),
            base64.urlsafe_b64encode(signature).decode().rstrip("=")]
    for key in keys:
        for sig in sigs:
            assert handle({"message": "подпись ✓", "signature": sig, "public_key": key})[
                "valid"] is True
    assert handle({"message": "подпись ✓".encode().hex(), "message_encoding": "hex",
                   "signature": sigs[0], "public_key": keys[0]})["valid"] is True


def test_jcs_documents_with_excluded_members(handle) -> None:
    private_cls, serialization = ed25519()
    private = private_cls.generate()
    public = private.public_key().public_bytes(serialization.Encoding.Raw,
                                               serialization.PublicFormat.Raw)
    body = {"b": [1, 2], "a": "é", "\U0001f600": True}
    canonical = '{"a":"é","b":[1,2],"\U0001f600":true}'.encode()
    signature = private.sign(canonical).hex()
    document = dict(body, sig=signature)
    out = handle({"format": "jcs", "document": document, "exclude": ["sig"],
                  "signature": signature, "public_key": public.hex()})
    assert out["valid"] is True and out["signed_bytes_length"] == len(canonical)
    floats = handle({"format": "jcs", "document": {"x": 1.5}, "signature": signature,
                     "public_key": public.hex()})
    assert floats["valid"] is False and "not an integer" in floats["reason"]


@pytest.mark.parametrize(
    ("payload", "match"),
    [
        ({}, "send 'message'"),
        ({"message": "x", "signature": "00" * 64}, "public_key"),
        ({"message": "x", "signature": "00" * 64, "public_key": "00" * 31}, "32"),
        ({"message": "x", "message_encoding": "rot13", "signature": "00" * 64,
          "public_key": "00" * 32}, "message_encoding"),
        ({"format": "pgp", "document": {}}, "format must be"),
        ({"format": "hestia", "document": {"result": 1, "signature": "x"}}, "capability_id"),
    ],
)
def test_bad_requests_say_why(handle, payload, match) -> None:
    with pytest.raises(ValueError, match=match):
        handle(payload)


def test_a_bad_signature_encoding_is_an_answer_not_an_error(handle) -> None:
    out = handle({"message": "x", "signature": "zz", "public_key": "00" * 32})
    assert out == {"format": "raw", "valid": False,
                   "reason": "signature does not decode (hex, base64 or base58btc) to 64 bytes"}
