"""timestamp.verify@v1 against three real RFC 3161 tokens.

`timestamp_fixtures.json` holds the replies of three public TSAs on 2026-11-21 21:33 UTC to one
request (openssl ts -query -sha256 -cert, nonce 0xE3A994942B24580D) for the SHA-256 of the text in
`data`: Sigstore's TSA (ECDSA P-384, root from sigstore/root-signing), DigiCert (RSA 4096, chain to
DigiCert Trusted Root G4, cross-signed copy in the token) and FreeTSA (ECDSA P-384 leaf under an RSA
4096 root, signingCertificate v1 with SHA-1). `openssl ts -verify` accepted each of them.
"""
# ruff: noqa: E501 — recorded values

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

import pytest
from replay import load

from hestia_agents.manifests import AGENTS, deploy_body

F = json.loads((Path(__file__).parent / "timestamp_fixtures.json").read_text(encoding="utf-8"))
SLUG = "timestamp"
IMPRINT = "12bfb127ea5522cb6393c88ebab2abf0214332b9dacba1fadb21f456e657c03f"


def run(payload):
    handle, asked, ns = load(SLUG, {})
    out = handle(payload)
    assert asked == []  # the agent reaches no host
    return out, ns


@pytest.mark.parametrize(
    "tsa, root, policy, chain_length",
    [
        ("sigstore", "Sigstore TSA", "1.3.6.1.4.1.57264.2", 2),
        ("digicert", "DigiCert Trusted Root G4", "2.16.840.1.114412.7.1", 3),
        ("freetsa", "Free TSA Root CA", "1.2.3.4.1", 2),
    ],
)
def test_each_tsa_token_verifies_to_its_pinned_root(tsa, root, policy, chain_length) -> None:
    out, _ = run({"token": F[tsa], "data": F["data"]})
    assert out["verdict"] == "verified" and out["imprint_matches"] is True
    assert all(c["ok"] for c in out["checks"]) and [c["check"] for c in out["checks"]] == [
        "content_type",
        "message_digest",
        "signer_certificate",
        "signing_certificate",
        "signature",
        "time_stamping_key_usage",
        "signer_valid_at_gen_time",
    ] + ["chain_valid_at_gen_time"] * (chain_length - 1)
    assert out["trusted_root"].startswith(root) and len(out["chain"]) == chain_length
    tst = out["tst_info"]
    assert (
        tst["policy"] == policy and tst["imprint"] == IMPRINT and tst["hash_algorithm"] == "sha256"
    )
    assert tst["nonce"] == "00e3a994942b24580d" and tst["gen_time"].startswith("2026-11-21T21:33:1")


def test_the_hash_or_the_bytes_check_the_same_imprint() -> None:
    assert run({"token": F["sigstore"], "hash": IMPRINT})[0]["imprint_matches"] is True
    b64 = base64.b64encode(F["data"].encode()).decode()
    assert run({"token": F["sigstore"], "data_base64": b64})[0]["imprint_matches"] is True


def test_other_data_is_an_imprint_mismatch_of_a_good_token() -> None:
    out, _ = run({"token": F["digicert"], "data": F["data"] + "."})
    assert out["verdict"] == "imprint_mismatch" and all(c["ok"] for c in out["checks"])


def test_the_bare_token_inside_a_response_reads_the_same() -> None:
    out, ns = run({"token": F["freetsa"]})
    status, token = ns["unwrap"](base64.b64decode(F["freetsa"]))
    assert status == "granted"
    bare, _ = run({"token": base64.b64encode(token).decode()})
    assert bare["verdict"] == out["verdict"] == "verified" and "imprint_matches" not in bare
    assert bare["tst_info"] == out["tst_info"]


def flip(token_b64, needle_hex, delta=1):
    raw = bytearray(base64.b64decode(token_b64))
    at = raw.find(bytes.fromhex(needle_hex))
    assert at >= 0
    raw[at + len(bytes.fromhex(needle_hex)) - 1] ^= delta
    return base64.b64encode(bytes(raw)).decode()


def test_a_changed_imprint_inside_the_token_breaks_its_digest() -> None:
    out, _ = run({"token": flip(F["sigstore"], IMPRINT[:16]), "data": F["data"]})
    assert out["verdict"] == "invalid"
    assert [c["check"] for c in out["checks"] if not c["ok"]] == ["message_digest"]


def test_a_changed_signature_fails_the_signature_check() -> None:
    raw = bytearray(base64.b64decode(F["digicert"]))
    raw[-10] ^= 1  # the RSA signature is the token's last field
    out, _ = run({"token": base64.b64encode(bytes(raw)).decode(), "data": F["data"]})
    assert out["verdict"] == "invalid" and [c["check"] for c in out["checks"] if not c["ok"]] == [
        "signature"
    ]


def test_a_root_that_is_not_pinned_is_untrusted_until_named() -> None:
    handle, _, ns = load(SLUG, {})
    ns["TRUSTED_ROOTS"] = {
        k: v for k, v in ns["TRUSTED_ROOTS"].items() if not k.startswith("Free TSA")
    }
    out = handle({"token": F["freetsa"], "data": F["data"]})
    assert out["verdict"] == "verified_untrusted" and "trusted_root" not in out
    spki = out["untrusted_root"]["spki_sha256"]
    assert spki == "52c54ba340885605314daa1857c8763b94087d05c636092938d4e2d1818e99b5"
    out = handle({"token": F["freetsa"], "data": F["data"], "trusted_spki": [spki]})
    assert out["verdict"] == "verified" and out["trusted_root"].startswith("your trusted_spki")


def test_a_rejected_request_is_invalid_with_the_status() -> None:
    rejection = bytes.fromhex("3005" + "3003020102")  # TimeStampResp { status { rejection } }
    out, _ = run({"token": base64.b64encode(rejection).decode()})
    assert out["verdict"] == "invalid" and "rejection" in out["detail"]


def test_the_pinned_roots_are_the_published_ones() -> None:
    _, ns = run({"token": F["sigstore"]})
    by_name = {r["pinned_as"].split(" (")[0]: r for r in ns["_roots"]()}
    assert (
        hashlib.sha256(by_name["DigiCert Trusted Root G4"]["der"])
        .hexdigest()
        .upper()
        .startswith("552F7BDCF1A7AF9E")
    )
    assert (
        hashlib.sha256(by_name["Free TSA Root CA"]["der"])
        .hexdigest()
        .upper()
        .startswith("A6379E7CECC05FAA")
    )
    assert by_name["Sigstore TSA"]["subject_text"] == "O=sigstore.dev, CN=sigstore-tsa-selfsigned"


def test_generalized_time_with_fractions_and_oid_text() -> None:
    _, ns = run({"token": F["sigstore"]})
    seconds, fraction = ns["_time"](0x18, b"20261121213314.125Z")
    assert ns["_iso"](seconds, fraction) == "2026-11-21T21:33:14.125Z"
    assert ns["_oid_text"](bytes.fromhex("2b0601040183bf3002")) == "1.3.6.1.4.1.57264.2"
    with pytest.raises(ValueError):
        ns["_time"](0x18, b"20261121213314+0100")


@pytest.mark.parametrize(
    "payload, message",
    [
        ({}, "token must be base64"),
        ({"token": "!!"}, "not base64"),
        ({"token": "AAAA", "data": "x", "hash": "00"}, "at most one"),
        ({"token": "AAAA", "trusted_spki": ["xx"]}, "trusted_spki"),
    ],
)
def test_bad_input_is_refused(payload, message) -> None:
    handle, _, _ = load(SLUG, {})
    with pytest.raises(ValueError, match=message):
        handle(payload)


def test_manifest_has_no_egress_and_is_free() -> None:
    body = deploy_body(SLUG)
    assert "egress_hosts" not in body and AGENTS[SLUG]["price_per_call_usd"] == 0
