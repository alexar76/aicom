"""``eddsa-jcs-2022`` signing and verification (SPEC.md section 6)."""

from __future__ import annotations

import copy

import pytest
from conftest import (
    CREATED,
    NOW,
    VALID_FROM,
    assert_error,
    blame_subject,
    build_unsecured,
    make_blame,
    make_receipt,
    make_verdict,
    sign,
    verdict_subject,
    work_receipt_subject,
)

from awr.digest import sha256
from awr.documents import (
    document_reference,
    issue_blame_attestation,
    issue_verification_verdict,
    issue_work_receipt,
)
from awr.jcs import canonicalize
from awr.multibase import multibase_decode_base58btc
from awr.proof import (
    CRYPTOSUITE,
    PROOF_PURPOSE,
    PROOF_TYPE,
    encode_proof_value,
    hash_data,
    hash_data_for_document,
    proof_config,
    unsecured_document,
)
from awr.verify import verify_document


# ---------------------------------------------------------------------------
# hashData composition -- section 6.2 step 6
# ---------------------------------------------------------------------------


def test_hash_data_is_proof_config_hash_then_document_hash(key_a):
    receipt = make_receipt(key_a)
    proof_config_hash, transformed_hash, hash_data_bytes = hash_data_for_document(receipt)

    assert len(proof_config_hash) == 32
    assert len(transformed_hash) == 32
    assert len(hash_data_bytes) == 64
    assert hash_data_bytes == proof_config_hash + transformed_hash
    # The reverse order is the most frequent Data Integrity interop error.
    assert hash_data_bytes != transformed_hash + proof_config_hash


def test_the_two_halves_are_sha256_of_the_two_canonical_forms(key_a):
    receipt = make_receipt(key_a)
    unsecured = unsecured_document(receipt)
    config = proof_config(receipt["proof"], unsecured)

    proof_config_hash, transformed_hash, _ = hash_data(unsecured, config)
    assert proof_config_hash == sha256(canonicalize(config))
    assert transformed_hash == sha256(canonicalize(unsecured))
    assert b'"proofValue"' not in canonicalize(config)
    assert b'"proof"' not in canonicalize(unsecured)


def test_proof_config_carries_the_document_context(key_a):
    receipt = make_receipt(key_a)
    config = proof_config(receipt["proof"], receipt)
    assert config["@context"] == receipt["@context"]
    assert "proofValue" not in config


def test_reversed_hash_data_does_not_verify(key_a):
    """A signature over transformedDocumentHash || proofConfigHash must be rejected."""
    unsecured = build_unsecured(key_a)
    from awr.proof import build_proof_options

    options = build_proof_options(key_a, CREATED)
    config = proof_config(options, unsecured)
    proof_config_hash, transformed_hash, _ = hash_data(unsecured, config)
    wrong_order_signature = key_a.sign(transformed_hash + proof_config_hash)

    document = dict(unsecured)
    proof = dict(options)
    proof["proofValue"] = encode_proof_value(wrong_order_signature)
    document["proof"] = proof

    assert_error(verify_document(document, now=NOW), "AWR-PROOF-006")


# ---------------------------------------------------------------------------
# proof object shape -- section 6.1
# ---------------------------------------------------------------------------


def test_proof_object_members(key_a):
    receipt = make_receipt(key_a)
    proof = receipt["proof"]
    assert proof["type"] == PROOF_TYPE == "DataIntegrityProof"
    assert proof["cryptosuite"] == CRYPTOSUITE == "eddsa-jcs-2022"
    assert proof["proofPurpose"] == PROOF_PURPOSE == "assertionMethod"
    assert proof["created"] == CREATED
    assert proof["verificationMethod"] == key_a.verification_method
    assert proof["proofValue"].startswith("z")
    assert len(multibase_decode_base58btc(proof["proofValue"])) == 64


# ---------------------------------------------------------------------------
# round trips for all three document types
# ---------------------------------------------------------------------------


def test_work_receipt_round_trip(key_a):
    receipt = issue_work_receipt(
        work_receipt_subject(), key_a, valid_from=VALID_FROM, created=CREATED
    )
    result = verify_document(receipt, now=NOW)
    assert result["valid"] is True, result
    assert result["reasons"] == []
    assert result["documentType"] == "WorkReceipt"
    assert result["awrVersion"] == "2.0.0"
    assert result["profile"] == "L0"
    assert result["chain"] == {"resolved": 0, "unresolved": 0}


def test_verification_verdict_round_trip(key_a, key_b):
    receipt = make_receipt(key_a)
    verdict = issue_verification_verdict(
        verdict_subject(receipt), key_b, valid_from=VALID_FROM, created=CREATED
    )
    result = verify_document(verdict, now=NOW, supporting=[receipt])
    assert result["valid"] is True, result
    assert result["documentType"] == "VerificationVerdict"


def test_blame_attestation_round_trip(key_a, key_c):
    parent = make_receipt(key_a)
    terminal = make_receipt(
        key_a, subject=work_receipt_subject(parents=[document_reference(parent)])
    )
    blame = issue_blame_attestation(
        blame_subject(terminal, parent), key_c, valid_from=VALID_FROM, created=CREATED
    )
    result = verify_document(blame, now=NOW, supporting=[terminal, parent])
    assert result["valid"] is True, result
    assert result["documentType"] == "BlameAttestation"


def test_round_trip_is_stable_across_a_json_serialization(key_a):
    import json

    receipt = make_receipt(key_a)
    as_bytes = json.dumps(receipt).encode("utf-8")
    assert verify_document(as_bytes, now=NOW)["valid"] is True
    # ... and across a re-ordered, re-indented serialization of the same members.
    shuffled = json.dumps(
        {k: receipt[k] for k in sorted(receipt, reverse=True)}, indent=4
    ).encode("utf-8")
    assert verify_document(shuffled, now=NOW)["valid"] is True


# ---------------------------------------------------------------------------
# signature coverage -- section 13.1
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path,value",
    [
        (("id",), "urn:uuid:renamed-by-an-intermediary"),
        (("issuer", "name"), "someone-else"),
        (("type",), ["VerifiableCredential", "WorkReceipt", "ExtraType"]),
        (("validFrom",), "2020-01-01T00:00:00Z"),
        (("awrVersion",), "2.0.1"),
        (("credentialSubject", "nonce"), "01J9Z8QK4T7YB2N5V6W8XA3C0E"),
        (("credentialSubject", "work", "latencyMs"), 2341),
    ],
)
def test_every_top_level_field_is_inside_the_signature(key_a, path, value):
    receipt = make_receipt(key_a, overrides={"issuer": {"id": key_a.did, "name": "hub"}})
    tampered = copy.deepcopy(receipt)
    target = tampered
    for step in path[:-1]:
        target = target[step]
    target[path[-1]] = value
    assert_error(verify_document(tampered, now=NOW), "AWR-PROOF-006")


def test_unknown_properties_are_covered_and_must_not_be_stripped(key_a):
    receipt = sign(
        build_unsecured(key_a, overrides={"vendorExtension": {"anything": [1, 2, 3]}}),
        key_a,
    )
    assert verify_document(receipt, now=NOW)["valid"] is True

    stripped = copy.deepcopy(receipt)
    del stripped["vendorExtension"]
    assert_error(verify_document(stripped, now=NOW), "AWR-PROOF-006")


def test_unknown_properties_inside_the_proof_are_covered(key_a):
    from conftest import default_proof_options, sign_with_options

    unsecured = build_unsecured(key_a)
    options = default_proof_options(key_a, domain="example.test")
    document = sign_with_options(unsecured, key_a, options)
    assert verify_document(document, now=NOW)["valid"] is True

    tampered = copy.deepcopy(document)
    tampered["proof"]["domain"] = "attacker.test"
    assert_error(verify_document(tampered, now=NOW), "AWR-PROOF-006")


def test_a_proof_array_verifies_when_one_proof_is_valid(key_a):
    """Section 6.1: an array MAY be present; one proof MUST verify and all are reported."""
    receipt = make_receipt(key_a)
    good = receipt["proof"]
    bad = copy.deepcopy(good)
    bad["proofValue"] = encode_proof_value(b"\x00" * 64)
    document = dict(receipt)
    document["proof"] = [bad, good]

    result = verify_document(document, now=NOW)
    assert result["valid"] is True, result
    assert result["verifiedProof"] == 1
    assert result["proofs"][0]["verified"] is False
    assert "AWR-PROOF-006" in [r["code"] for r in result["proofs"][0]["reasons"]]
    assert result["proofs"][1]["verified"] is True


def test_a_proof_array_with_no_valid_proof_is_invalid(key_a):
    receipt = make_receipt(key_a)
    bad = copy.deepcopy(receipt["proof"])
    bad["proofValue"] = encode_proof_value(b"\x00" * 64)
    document = dict(receipt)
    document["proof"] = [bad]
    assert_error(verify_document(document, now=NOW), "AWR-PROOF-006")


# ---------------------------------------------------------------------------
# issuance refuses to emit what it would reject
# ---------------------------------------------------------------------------


def test_issue_refuses_an_invalid_subject(key_a):
    from awr.documents import IssuanceError

    with pytest.raises(IssuanceError) as info:
        issue_work_receipt(
            work_receipt_subject(work={"modelId": "", "status": "nope"}),
            key_a,
            valid_from=VALID_FROM,
        )
    assert "AWR-RCPT" in str(info.value)


def test_issue_rejects_an_unknown_document_type(key_a):
    from awr.documents import issue

    with pytest.raises(ValueError):
        issue(work_receipt_subject(), key_a, document_type="LegacyWorkReceipt")


def test_issue_is_deterministic_for_a_fixed_id_and_clock(key_a):
    first = issue_work_receipt(
        work_receipt_subject(),
        key_a,
        document_id="urn:uuid:fixed",
        valid_from=VALID_FROM,
        created=CREATED,
    )
    second = issue_work_receipt(
        work_receipt_subject(),
        key_a,
        document_id="urn:uuid:fixed",
        valid_from=VALID_FROM,
        created=CREATED,
    )
    assert canonicalize(first) == canonicalize(second)
    assert first["proof"]["proofValue"] == second["proof"]["proofValue"]


def test_issue_can_embed_a_consistent_public_key_jwk(key_a):
    receipt = issue_work_receipt(
        work_receipt_subject(),
        key_a,
        valid_from=VALID_FROM,
        created=CREATED,
        include_public_key_jwk=True,
    )
    assert receipt["issuer"]["publicKeyJwk"]["crv"] == "Ed25519"
    assert verify_document(receipt, now=NOW)["valid"] is True


def test_verdict_and_blame_round_trips_use_digest_references(key_a, key_b):
    receipt = make_receipt(key_a)
    verdict = make_verdict(key_b, receipt)
    reference = verdict["credentialSubject"]["verifiedWork"]
    assert reference["id"] == receipt["id"]
    assert reference["digestSRI"] == document_reference(receipt)["digestSRI"]

    blame = make_blame(key_b, receipt, receipt)
    assert blame["credentialSubject"]["chain"]["digestSRI"] == reference["digestSRI"]
