"""One assertion per reason code in the SPEC.md section 11.2 registry.

A reason code with no test is an unimplemented reason code, so this file is organised by
the registry's own sections and the conftest coverage tracker reports the total.
"""

from __future__ import annotations

import copy
import json

import pytest
from conftest import (
    CREATED,
    NOW,
    VALID_FROM,
    assert_error,
    assert_warning,
    build_unsecured,
    default_proof_options,
    make_receipt,
    make_verdict,
    sign,
    sign_with_options,
    sri_of,
    verdict_subject,
    work_receipt_subject,
)

from awr.documents import AWR_CONTEXT, VC_CONTEXT, document_reference
from awr.multibase import b58encode, multibase_encode_base58btc
from awr.proof import encode_proof_value
from awr.verify import verify_document


def error_codes(result):
    return sorted({entry["code"] for entry in result["reasons"]})


def warning_codes(result):
    return sorted({entry["code"] for entry in result["warnings"]})


def receipt_with(key, **subject_overrides):
    """A signed receipt whose subject carries the given (possibly invalid) members."""
    return sign(
        build_unsecured(key, subject=work_receipt_subject(**subject_overrides)), key
    )


def envelope_variant(key, *, overrides=None, drop=()):
    return sign(build_unsecured(key, overrides=overrides, drop=drop), key)


# ---------------------------------------------------------------------------
# AWR-DOC-*
# ---------------------------------------------------------------------------


def test_doc_001_not_a_json_object():
    result = verify_document(b'[{"@context":[]}]', now=NOW)
    assert_error(result, "AWR-DOC-001")
    assert error_codes(result) == ["AWR-DOC-001"]


@pytest.mark.parametrize(
    "overrides,drop",
    [
        (None, ("@context",)),
        ({"@context": "https://www.w3.org/ns/credentials/v2"}, ()),
        ({"@context": []}, ()),
        ({"@context": [AWR_CONTEXT, VC_CONTEXT]}, ()),
        ({"@context": ["https://example.test/other", VC_CONTEXT, AWR_CONTEXT]}, ()),
    ],
)
def test_doc_002_context_missing_or_first_element_wrong(key_a, overrides, drop):
    assert_error(
        verify_document(envelope_variant(key_a, overrides=overrides, drop=drop), now=NOW),
        "AWR-DOC-002",
    )


def test_doc_003_awr_namespace_absent(key_a):
    result = verify_document(
        envelope_variant(key_a, overrides={"@context": [VC_CONTEXT]}), now=NOW
    )
    assert_error(result, "AWR-DOC-003")
    assert error_codes(result) == ["AWR-DOC-003"]


def test_doc_003_additional_contexts_may_follow(key_a):
    document = envelope_variant(
        key_a, overrides={"@context": [VC_CONTEXT, AWR_CONTEXT, "https://example.test/x"]}
    )
    assert verify_document(document, now=NOW)["valid"] is True


@pytest.mark.parametrize(
    "types", [["WorkReceipt"], ["Credential", "WorkReceipt"], "VerifiableCredential"]
)
def test_doc_004_type_missing_verifiable_credential(key_a, types):
    assert_error(
        verify_document(envelope_variant(key_a, overrides={"type": types}), now=NOW),
        "AWR-DOC-004",
    )


@pytest.mark.parametrize(
    "types",
    [
        ["VerifiableCredential"],
        ["VerifiableCredential", "WorkReceipt", "VerificationVerdict"],
        ["VerifiableCredential", "SomethingElse"],
    ],
)
def test_doc_005_zero_or_several_awr_types(key_a, types):
    result = verify_document(
        envelope_variant(key_a, overrides={"type": types}), now=NOW
    )
    assert_error(result, "AWR-DOC-005")
    assert result["documentType"] is None


def test_doc_005_further_types_may_be_present(key_a):
    document = envelope_variant(
        key_a, overrides={"type": ["VerifiableCredential", "WorkReceipt", "HubReceipt"]}
    )
    assert verify_document(document, now=NOW)["valid"] is True


@pytest.mark.parametrize(
    "overrides,drop",
    [
        (None, ("id",)),
        ({"id": "not-a-uri"}, ()),
        ({"id": "/relative/path"}, ()),
        ({"id": 42}, ()),
        ({"id": ""}, ()),
    ],
)
def test_doc_006_id_missing_or_not_absolute(key_a, overrides, drop):
    assert_error(
        verify_document(envelope_variant(key_a, overrides=overrides, drop=drop), now=NOW),
        "AWR-DOC-006",
    )


def test_doc_006_https_id_is_permitted(key_a):
    document = envelope_variant(
        key_a, overrides={"id": "https://receipts.example/2026/07/31/abc"}
    )
    assert verify_document(document, now=NOW)["valid"] is True


@pytest.mark.parametrize(
    "overrides,drop",
    [
        (None, ("validFrom",)),
        ({"validFrom": "2026-07-31 10:15:30Z"}, ()),
        ({"validFrom": "2026-07-31T10:15:30+02:00"}, ()),
        ({"validFrom": "2026-07-31T10:15Z"}, ()),
        ({"validFrom": "2026-13-31T10:15:30Z"}, ()),
        ({"validUntil": VALID_FROM}, ()),
        ({"validUntil": "2026-07-31T10:15:29Z"}, ()),
        ({"validUntil": "whenever"}, ()),
    ],
)
def test_doc_007_valid_from_and_valid_until(key_a, overrides, drop):
    assert_error(
        verify_document(envelope_variant(key_a, overrides=overrides, drop=drop), now=NOW),
        "AWR-DOC-007",
    )


def test_doc_007_sub_second_precision_is_accepted(key_a):
    document = envelope_variant(key_a, overrides={"validFrom": "2026-07-31T10:15:30.250Z"})
    assert verify_document(document, now=NOW)["valid"] is True


@pytest.mark.parametrize(
    "overrides,drop",
    [
        (None, ("credentialSubject",)),
        ({"credentialSubject": [work_receipt_subject()]}, ()),
        ({"credentialSubject": "a string"}, ()),
    ],
)
def test_doc_008_credential_subject_not_a_single_object(key_a, overrides, drop):
    assert_error(
        verify_document(envelope_variant(key_a, overrides=overrides, drop=drop), now=NOW),
        "AWR-DOC-008",
    )


@pytest.mark.parametrize(
    "overrides,drop",
    [
        (None, ("awrVersion",)),
        ({"awrVersion": "2.0"}, ()),
        ({"awrVersion": 2}, ()),
        ({"awrVersion": "3.0.0"}, ()),
        ({"awrVersion": "1.4.2"}, ()),
    ],
)
def test_doc_009_awr_version(key_a, overrides, drop):
    assert_error(
        verify_document(envelope_variant(key_a, overrides=overrides, drop=drop), now=NOW),
        "AWR-DOC-009",
    )


def test_doc_009_a_later_minor_version_is_accepted(key_a):
    document = envelope_variant(key_a, overrides={"awrVersion": "2.4.1"})
    assert verify_document(document, now=NOW)["valid"] is True


@pytest.mark.parametrize(
    "overrides,drop",
    [
        (None, ("issuer",)),
        ({"issuer": "did:key:z6MktwupdmLXVVqTzCw4i46r4uGyosGXRnR3XjN4Zq7oMMsw"}, ()),
        ({"issuer": {"name": "no id here"}}, ()),
        ({"issuer": {"id": ""}}, ()),
        ({"issuer": []}, ()),
    ],
)
def test_doc_010_issuer_missing_or_bare_string(key_a, overrides, drop):
    """A bare-string issuer is legal in VC 2.0 and rejected in AWR/2 (section 3.1)."""
    assert_error(
        verify_document(envelope_variant(key_a, overrides=overrides, drop=drop), now=NOW),
        "AWR-DOC-010",
    )


# ---------------------------------------------------------------------------
# AWR-CANON-* through the verification pipeline
# ---------------------------------------------------------------------------


def test_canon_001_through_the_pipeline(key_a):
    receipt = make_receipt(key_a)
    text = json.dumps(receipt).replace('"latencyMs": 2340', '"latencyMs": 2340.0')
    result = verify_document(text.encode("utf-8"), now=NOW)
    assert_error(result, "AWR-CANON-001")


def test_canon_002_through_the_pipeline(key_a):
    receipt = make_receipt(key_a)
    text = json.dumps(receipt).replace('"latencyMs": 2340', '"latencyMs": 9007199254740992')
    assert_error(verify_document(text.encode("utf-8"), now=NOW), "AWR-CANON-002")


def test_canon_003_through_the_pipeline(key_a):
    receipt = make_receipt(key_a)
    text = json.dumps(receipt).replace('"succeeded"', '"succ\\ud800eded"')
    assert_error(verify_document(text.encode("utf-8"), now=NOW), "AWR-CANON-003")


def test_canon_004_through_the_pipeline(key_a):
    receipt = make_receipt(key_a)
    text = json.dumps(receipt).replace('"awrVersion"', '"id": "urn:uuid:x", "awrVersion"', 1)
    assert_error(verify_document(text.encode("utf-8"), now=NOW), "AWR-CANON-004")


def test_canon_005_through_the_pipeline():
    result = verify_document(b'{"@context": [', now=NOW)
    assert_error(result, "AWR-CANON-005")
    assert error_codes(result) == ["AWR-CANON-005"]


def test_canon_006_is_asserted_in_test_jcs():
    """AWR-CANON-006 is an implementation self-check; see test_jcs.py."""
    from conftest import record_code

    record_code("AWR-CANON-006")


# ---------------------------------------------------------------------------
# AWR-KEY-* through the verification pipeline
# ---------------------------------------------------------------------------


def test_key_001_through_the_pipeline(key_a):
    document = envelope_variant(key_a, overrides={"issuer": {"id": "https://hub.example"}})
    result = verify_document(document, now=NOW)
    assert_error(result, "AWR-KEY-001")


def test_key_002_through_the_pipeline(key_a):
    document = envelope_variant(
        key_a, overrides={"issuer": {"id": "did:key:z" + b58encode(b"\xed\x01" + b"\x02" * 31)}}
    )
    assert_error(verify_document(document, now=NOW), "AWR-KEY-002")


def test_key_003_through_the_pipeline(key_a, key_b):
    document = sign(
        build_unsecured(
            key_a,
            overrides={"issuer": {"id": key_a.did, "publicKeyJwk": key_b.public_key_jwk()}},
        ),
        key_a,
    )
    result = verify_document(document, now=NOW)
    assert_error(result, "AWR-KEY-003")
    # The document MUST be invalidated, not merely flagged (section 5.2).
    assert result["valid"] is False


def test_key_004_through_the_pipeline(key_a):
    x25519 = "did:key:" + multibase_encode_base58btc(b"\xec\x01" + b"\x03" * 32)
    document = envelope_variant(key_a, overrides={"issuer": {"id": x25519}})
    assert_error(verify_document(document, now=NOW), "AWR-KEY-004")


# ---------------------------------------------------------------------------
# AWR-PROOF-*
# ---------------------------------------------------------------------------


def test_proof_001_missing(key_a):
    result = verify_document(build_unsecured(key_a), now=NOW)
    assert_error(result, "AWR-PROOF-001")
    assert error_codes(result) == ["AWR-PROOF-001"]


def test_proof_001_empty_array(key_a):
    document = dict(make_receipt(key_a))
    document["proof"] = []
    assert_error(verify_document(document, now=NOW), "AWR-PROOF-001")


@pytest.mark.parametrize("proof_type", ["Ed25519Signature2020", "JsonWebSignature2020", 7])
def test_proof_002_wrong_type(key_a, proof_type):
    document = sign_with_options(
        build_unsecured(key_a), key_a, default_proof_options(key_a, type=proof_type)
    )
    result = verify_document(document, now=NOW)
    assert_error(result, "AWR-PROOF-002")
    # The signature itself is intact: only the suite label is wrong.
    assert "AWR-PROOF-006" not in error_codes(result)


@pytest.mark.parametrize("suite", ["eddsa-rdfc-2022", "ecdsa-jcs-2019", "eddsa-jcs-2022 "])
def test_proof_003_unsupported_cryptosuite(key_a, suite):
    document = sign_with_options(
        build_unsecured(key_a), key_a, default_proof_options(key_a, cryptosuite=suite)
    )
    result = verify_document(document, now=NOW)
    assert_error(result, "AWR-PROOF-003")
    assert error_codes(result) == ["AWR-PROOF-003"]


@pytest.mark.parametrize("purpose", ["authentication", "keyAgreement", None])
def test_proof_004_wrong_proof_purpose(key_a, purpose):
    options = default_proof_options(key_a, proofPurpose=purpose)
    document = sign_with_options(build_unsecured(key_a), key_a, options)
    assert_error(verify_document(document, now=NOW), "AWR-PROOF-004")


@pytest.mark.parametrize(
    "proof_value",
    [
        "AAAA",  # unprefixed base64
        "z",  # empty body
        "f0011",  # multibase base16
        "z" + b58encode(b"\x01" * 63),  # 63 bytes
        "z" + b58encode(b"\x01" * 65),  # 65 bytes
        "zIl0O",  # not base58btc
        42,
    ],
)
def test_proof_005_bad_proof_value(key_a, proof_value):
    document = copy.deepcopy(make_receipt(key_a))
    document["proof"]["proofValue"] = proof_value
    assert_error(verify_document(document, now=NOW), "AWR-PROOF-005")


def test_proof_005_rejects_the_awr1_base64_form(key_a):
    import base64

    document = copy.deepcopy(make_receipt(key_a))
    signature = b"\x07" * 64
    document["proof"]["proofValue"] = base64.b64encode(signature).decode("ascii")
    result = verify_document(document, now=NOW)
    assert_error(result, "AWR-PROOF-005")
    assert "AWR/1" in [r["detail"] for r in result["reasons"] if r["code"] == "AWR-PROOF-005"][0]


def test_proof_006_signature_failure(key_a, key_b):
    document = copy.deepcopy(make_receipt(key_a))
    document["proof"]["proofValue"] = encode_proof_value(b"\x00" * 64)
    assert_error(verify_document(document, now=NOW), "AWR-PROOF-006")

    # A valid signature made by a different key over the same bytes is also PROOF-006.
    other = sign(build_unsecured(key_a), key_b)
    assert_error(verify_document(other, now=NOW), "AWR-PROOF-007")


@pytest.mark.parametrize(
    "method",
    [
        None,
        "did:key:z6MktwupdmLXVVqTzCw4i46r4uGyosGXRnR3XjN4Zq7oMMsw#z6Mktwupdm",
        "#z6Mk",
    ],
)
def test_proof_007_verification_method_mismatch(key_a, method):
    if method is None:
        method = key_a.did  # the DID without the required fragment
    document = sign_with_options(
        build_unsecured(key_a),
        key_a,
        default_proof_options(key_a, verificationMethod=method),
    )
    result = verify_document(document, now=NOW)
    assert_error(result, "AWR-PROOF-007")


def test_proof_008_proof_context_inconsistent(key_a):
    document = sign_with_options(
        build_unsecured(key_a),
        key_a,
        default_proof_options(key_a, **{"@context": ["https://example.test/other"]}),
    )
    result = verify_document(document, now=NOW)
    assert_error(result, "AWR-PROOF-008")


@pytest.mark.parametrize("created", [None, "2026-07-31 10:15:30", "yesterday", 12345])
def test_proof_009_created_missing_or_malformed(key_a, created):
    document = sign_with_options(
        build_unsecured(key_a), key_a, default_proof_options(key_a, created=created)
    )
    assert_error(verify_document(document, now=NOW), "AWR-PROOF-009")


# ---------------------------------------------------------------------------
# AWR-RCPT-*
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "overrides",
    [
        {"inputDigest": None},
        {"outputDigest": None},
        {"inputDigest": "sha512-" + "A" * 86 + "=="},
        {"outputDigest": "sha256-not-base64!!"},
        {"inputDigest": "47DEQpj8HBSa+/TImW+5JCeuQeRkm5NMpJWZG3hSuFU="},
        {"outputDigest": "sha256-QUJD"},  # too short to be 32 bytes
        {"inputDigest": 1234},
    ],
)
def test_rcpt_001_input_or_output_digest(key_a, overrides):
    subject = work_receipt_subject()
    for name, value in overrides.items():
        if value is None:
            del subject[name]
        else:
            subject[name] = value
    document = sign(build_unsecured(key_a, subject=subject), key_a)
    assert_error(verify_document(document, now=NOW), "AWR-RCPT-001")


def test_rcpt_001_failed_work_may_use_the_empty_payload_digest(key_a):
    from awr.documents import EMPTY_PAYLOAD_SRI

    subject = work_receipt_subject(outputDigest=EMPTY_PAYLOAD_SRI)
    subject["work"]["status"] = "failed"
    document = sign(build_unsecured(key_a, subject=subject), key_a)
    assert verify_document(document, now=NOW)["valid"] is True


@pytest.mark.parametrize(
    "price",
    [
        {"currency": "usd", "amount": "0.15"},
        {"currency": "US", "amount": "0.15"},
        {"currency": "USD", "amount": ".15"},
        {"currency": "USD", "amount": "0,15"},
        {"currency": "USD", "amount": "015"},
        {"currency": "USD"},
        {"amount": "0.15"},
        "0.15 USD",
    ],
)
def test_rcpt_002_price_malformed(key_a, price):
    document = receipt_with(key_a, price=price)
    assert_error(verify_document(document, now=NOW), "AWR-RCPT-002")


@pytest.mark.parametrize(
    "price",
    [
        {"currency": "USD", "amount": "0.15"},
        {"currency": "USD", "amount": "-0.15"},
        {"currency": "USD", "amount": "0"},
        {"currency": "urn:example:credits", "amount": "12"},
    ],
)
def test_rcpt_002_well_formed_prices_are_accepted(key_a, price):
    assert verify_document(receipt_with(key_a, price=price), now=NOW)["valid"] is True


@pytest.mark.parametrize(
    "work",
    [
        {"modelId": "m@v", "status": "succeeded"},  # no completedAt
        {
            "modelId": "m@v",
            "status": "succeeded",
            "startedAt": "2026-07-31T10:15:31Z",
            "completedAt": "2026-07-31T10:15:30Z",
        },
        {"modelId": "m@v", "status": "succeeded", "completedAt": "31 July 2026"},
        {
            "modelId": "m@v",
            "status": "succeeded",
            "completedAt": "2026-07-31T10:15:30Z",
            "startedAt": "nonsense",
        },
    ],
)
def test_rcpt_003_timestamps(key_a, work):
    assert_error(verify_document(receipt_with(key_a, work=work), now=NOW), "AWR-RCPT-003")


def test_rcpt_003_missing_work_object_reports_every_missing_fact(key_a):
    subject = work_receipt_subject()
    del subject["work"]
    document = sign(build_unsecured(key_a, subject=subject), key_a)
    result = verify_document(document, now=NOW)
    assert error_codes(result) == ["AWR-RCPT-003", "AWR-RCPT-005", "AWR-RCPT-006"]


@pytest.mark.parametrize("latency", [-1, "2340", True, 2.5])
def test_rcpt_004_latency(key_a, latency):
    work = dict(work_receipt_subject()["work"])
    work["latencyMs"] = latency
    if isinstance(latency, float):
        # A JSON float never reaches the receipt check: section 4.3 rejects it first.
        from awr.errors import AwrError

        with pytest.raises(AwrError):
            receipt_with(key_a, work=work)
        return
    assert_error(verify_document(receipt_with(key_a, work=work), now=NOW), "AWR-RCPT-004")


@pytest.mark.parametrize("model_id", ["", None, 5, {"name": "m"}])
def test_rcpt_005_model_id(key_a, model_id):
    work = dict(work_receipt_subject()["work"])
    if model_id is None:
        del work["modelId"]
    else:
        work["modelId"] = model_id
    assert_error(verify_document(receipt_with(key_a, work=work), now=NOW), "AWR-RCPT-005")


@pytest.mark.parametrize("status", ["ok", "SUCCEEDED", None, ""])
def test_rcpt_006_status(key_a, status):
    work = dict(work_receipt_subject()["work"])
    if status is None:
        del work["status"]
    else:
        work["status"] = status
    assert_error(verify_document(receipt_with(key_a, work=work), now=NOW), "AWR-RCPT-006")


@pytest.mark.parametrize(
    "status", ["succeeded", "failed", "refused", "timeout", "partial"]
)
def test_rcpt_006_every_enumerated_status_is_accepted(key_a, status):
    work = dict(work_receipt_subject()["work"])
    work["status"] = status
    assert verify_document(receipt_with(key_a, work=work), now=NOW)["valid"] is True


# ---------------------------------------------------------------------------
# AWR-VDCT-*
# ---------------------------------------------------------------------------


def verdict_with(key, receipt=None, **overrides):
    subject = verdict_subject(receipt, **overrides)
    if receipt is None and "verifiedWork" not in overrides:
        subject.pop("verifiedWork", None)
    return sign(
        build_unsecured(key, document_type="VerificationVerdict", subject=subject), key
    )


@pytest.mark.parametrize(
    "verified_work",
    [
        None,
        {"id": "urn:uuid:x"},
        {"digestSRI": "sha256-47DEQpj8HBSa+/TImW+5JCeuQeRkm5NMpJWZG3hSuFU="},
        {"id": "", "digestSRI": "sha256-47DEQpj8HBSa+/TImW+5JCeuQeRkm5NMpJWZG3hSuFU="},
        "urn:uuid:x",
    ],
)
def test_vdct_001_verified_work(key_b, verified_work):
    if verified_work is None:
        document = verdict_with(key_b)
    else:
        document = verdict_with(key_b, verifiedWork=verified_work)
    assert_error(verify_document(document, now=NOW), "AWR-VDCT-001")


@pytest.mark.parametrize("score", ["1.5", "-0.1", "abc", "1.", "0.9.9", 0])
def test_vdct_002_score(key_a, key_b, score):
    receipt = make_receipt(key_a)
    document = verdict_with(key_b, receipt, score=score, policy={})
    assert_error(verify_document(document, now=NOW), "AWR-VDCT-002")


@pytest.mark.parametrize("score", ["0", "1", "1.0", "0.93", "0.000001"])
def test_vdct_002_well_formed_scores_are_accepted(key_a, key_b, score):
    receipt = make_receipt(key_a)
    document = verdict_with(key_b, receipt, score=score, policy={"threshold": "0"})
    assert verify_document(document, now=NOW)["valid"] is True


def test_vdct_002_also_covers_policy_threshold(key_a, key_b):
    receipt = make_receipt(key_a)
    document = verdict_with(key_b, receipt, policy={"threshold": "80%"})
    result = verify_document(document, now=NOW)
    assert_error(result, "AWR-VDCT-002")
    assert "policy.threshold" in [
        r["detail"] for r in result["reasons"] if r["code"] == "AWR-VDCT-002"
    ][0]


@pytest.mark.parametrize(
    "method", [None, {}, {"id": ""}, {"name": "no id"}, "urn:example:method", {"id": 5}]
)
def test_vdct_003_method(key_a, key_b, method):
    receipt = make_receipt(key_a)
    subject = verdict_subject(receipt)
    if method is None:
        del subject["method"]
    else:
        subject["method"] = method
    document = sign(
        build_unsecured(key_b, document_type="VerificationVerdict", subject=subject), key_b
    )
    assert_error(verify_document(document, now=NOW), "AWR-VDCT-003")


@pytest.mark.parametrize("verdict", ["PASS", "passed", None, "", "ok"])
def test_vdct_004_verdict_enumeration(key_a, key_b, verdict):
    receipt = make_receipt(key_a)
    subject = verdict_subject(receipt)
    if verdict is None:
        del subject["verdict"]
    else:
        subject["verdict"] = verdict
    document = sign(
        build_unsecured(key_b, document_type="VerificationVerdict", subject=subject), key_b
    )
    assert_error(verify_document(document, now=NOW), "AWR-VDCT-004")


@pytest.mark.parametrize("verdict", ["pass", "fail", "inconclusive"])
def test_vdct_004_inconclusive_is_not_a_failure(key_a, key_b, verdict):
    receipt = make_receipt(key_a)
    document = verdict_with(key_b, receipt, verdict=verdict, score=None, policy={})
    subject = document["credentialSubject"]
    subject.pop("score", None)
    document = sign(
        build_unsecured(key_b, document_type="VerificationVerdict", subject=subject), key_b
    )
    assert verify_document(document, now=NOW)["valid"] is True


def test_vdct_005_verified_work_digest_does_not_match_the_supplied_receipt(key_a, key_b):
    receipt = make_receipt(key_a, document_id="urn:uuid:the-receipt")
    other = make_receipt(
        key_a,
        document_id="urn:uuid:the-receipt",
        subject=work_receipt_subject(nonce="01J9Z8QK4T7YB2N5V6W8XA3C0Z"),
    )
    verdict = make_verdict(key_b, other)
    # The caller supplies a *different* receipt carrying the same id.
    result = verify_document(verdict, now=NOW, supporting=[receipt])
    assert_error(result, "AWR-VDCT-005")


def test_vdct_006_verdict_inconsistent_with_score_and_threshold(key_a, key_b):
    receipt = make_receipt(key_a)
    document = verdict_with(
        key_b, receipt, verdict="pass", score="0.50", policy={"threshold": "0.80"}
    )
    result = verify_document(document, now=NOW)
    assert_warning(result, "AWR-VDCT-006")
    # A warning, never invalidity: the issuer's verdict is authoritative.
    assert result["valid"] is True


def test_vdct_006_also_fires_when_a_fail_meets_the_threshold(key_a, key_b):
    receipt = make_receipt(key_a)
    document = verdict_with(
        key_b, receipt, verdict="fail", score="0.95", policy={"threshold": "0.80"}
    )
    assert_warning(verify_document(document, now=NOW), "AWR-VDCT-006")


def test_vdct_006_is_silent_for_inconclusive(key_a, key_b):
    receipt = make_receipt(key_a)
    document = verdict_with(
        key_b, receipt, verdict="inconclusive", score="0.50", policy={"threshold": "0.80"}
    )
    result = verify_document(document, now=NOW)
    assert "AWR-VDCT-006" not in warning_codes(result)


def test_vdct_006_uses_decimal_not_binary_float_comparison(key_a, key_b):
    receipt = make_receipt(key_a)
    document = verdict_with(
        key_b, receipt, verdict="pass", score="0.1", policy={"threshold": "0.1"}
    )
    result = verify_document(document, now=NOW)
    assert "AWR-VDCT-006" not in warning_codes(result)


@pytest.mark.parametrize(
    "evidence",
    [
        [{"kind": "trace"}],
        [{"kind": "trace", "digestSRI": None}],
        ["sha256-47DEQpj8HBSa+/TImW+5JCeuQeRkm5NMpJWZG3hSuFU="],
        "a trace",
    ],
)
def test_vdct_007_evidence_without_digest(key_a, key_b, evidence):
    if isinstance(evidence, list) and evidence and isinstance(evidence[0], dict):
        evidence = [{k: v for k, v in evidence[0].items() if v is not None}]
    receipt = make_receipt(key_a)
    document = verdict_with(key_b, receipt, evidence=evidence)
    assert_error(verify_document(document, now=NOW), "AWR-VDCT-007")


# ---------------------------------------------------------------------------
# AWR-BLAME-*
# ---------------------------------------------------------------------------


def blame_with(key, **overrides):
    subject = {
        "chain": {"id": "urn:uuid:terminal", "digestSRI": sri_of(b"terminal")},
        "blamedWork": {"id": "urn:uuid:hop", "digestSRI": sri_of(b"hop")},
        "failureClass": "wrong-output",
        "confidence": "0.90",
        "method": {"id": "urn:example:method:hop-bisect-v1"},
        "evidence": [{"kind": "replay", "digestSRI": sri_of(b"a replay log")}],
    }
    for name, value in overrides.items():
        if value is None:
            subject.pop(name, None)
        else:
            subject[name] = value
    return sign(
        build_unsecured(key, document_type="BlameAttestation", subject=subject), key
    )


def test_blame_001_blamed_work_not_reachable(key_a, key_c):
    terminal = make_receipt(key_a, document_id="urn:uuid:terminal-hop")
    unrelated = make_receipt(key_a, document_id="urn:uuid:unrelated-hop")
    blame = sign(
        build_unsecured(
            key_c,
            document_type="BlameAttestation",
            subject={
                "chain": document_reference(terminal),
                "blamedWork": document_reference(unrelated),
                "failureClass": "wrong-output",
                "method": {"id": "urn:example:method:hop-bisect-v1"},
            },
        ),
        key_c,
    )
    result = verify_document(blame, now=NOW, supporting=[terminal, unrelated])
    assert_error(result, "AWR-BLAME-001")


def test_blame_001_is_silent_when_the_chain_is_not_available(key_a, key_c):
    terminal = make_receipt(key_a)
    unrelated = make_receipt(key_a)
    blame = sign(
        build_unsecured(
            key_c,
            document_type="BlameAttestation",
            subject={
                "chain": document_reference(terminal),
                "blamedWork": document_reference(unrelated),
                "failureClass": "wrong-output",
                "method": {"id": "urn:example:method:hop-bisect-v1"},
            },
        ),
        key_c,
    )
    assert verify_document(blame, now=NOW)["valid"] is True


def test_blame_001_accepts_a_reachable_hop(key_a, key_c):
    parent = make_receipt(key_a)
    terminal = make_receipt(
        key_a, subject=work_receipt_subject(parents=[document_reference(parent)])
    )
    blame = sign(
        build_unsecured(
            key_c,
            document_type="BlameAttestation",
            subject={
                "chain": document_reference(terminal),
                "blamedWork": document_reference(parent),
                "failureClass": "upstream-input",
                "method": {"id": "urn:example:method:hop-bisect-v1"},
            },
        ),
        key_c,
    )
    assert verify_document(blame, now=NOW, supporting=[terminal, parent])["valid"] is True


@pytest.mark.parametrize("failure_class", ["oops", None, "", "WRONG-OUTPUT"])
def test_blame_002_failure_class(key_c, failure_class):
    assert_error(
        verify_document(blame_with(key_c, failureClass=failure_class), now=NOW),
        "AWR-BLAME-002",
    )


@pytest.mark.parametrize(
    "failure_class",
    [
        "wrong-output",
        "malformed-output",
        "unavailable",
        "timeout",
        "policy-violation",
        "upstream-input",
        "cost-overrun",
        "unknown",
    ],
)
def test_blame_002_every_enumerated_class_is_accepted(key_c, failure_class):
    result = verify_document(blame_with(key_c, failureClass=failure_class), now=NOW)
    assert result["valid"] is True, result


@pytest.mark.parametrize(
    "overrides",
    [
        {"chain": None},
        {"blamedWork": None},
        {"chain": {"digestSRI": sri_of(b"x")}},
        {"blamedWork": {"id": "urn:uuid:hop"}},
        {"chain": "urn:uuid:terminal"},
    ],
)
def test_blame_003_chain_or_blamed_work_malformed(key_c, overrides):
    assert_error(verify_document(blame_with(key_c, **overrides), now=NOW), "AWR-BLAME-003")


@pytest.mark.parametrize("confidence", ["2", "-1", "high", "0.9x"])
def test_blame_004_confidence(key_c, confidence):
    assert_error(
        verify_document(blame_with(key_c, confidence=confidence), now=NOW), "AWR-BLAME-004"
    )


def test_blame_may_equal_the_chain_terminal(key_a, key_c):
    terminal = make_receipt(key_a)
    blame = sign(
        build_unsecured(
            key_c,
            document_type="BlameAttestation",
            subject={
                "chain": document_reference(terminal),
                "blamedWork": document_reference(terminal),
                "failureClass": "wrong-output",
                "method": {"id": "urn:example:method:hop-bisect-v1"},
            },
        ),
        key_c,
    )
    assert verify_document(blame, now=NOW, supporting=[terminal])["valid"] is True


# ---------------------------------------------------------------------------
# AWR-ENV-001, AWR-TIME-*
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("member", ["teeAttestation", "zkProof"])
def test_env_001_unverified_attestation_is_a_warning(key_a, member):
    document = receipt_with(key_a, environment={member: {"quote": "opaque", "n": 1}})
    result = verify_document(document, now=NOW)
    assert_warning(result, "AWR-ENV-001")
    # Section 7.3: present-and-unverified must not make the document invalid, and must
    # not make it more trustworthy either.
    assert result["valid"] is True
    assert result["profile"] == "L0"


def test_time_001_valid_from_in_the_future(key_a):
    document = envelope_variant(key_a, overrides={"validFrom": "2026-08-01T00:00:00Z"})
    result = verify_document(document, now=NOW)
    assert_warning(result, "AWR-TIME-001")
    assert result["valid"] is True


def test_time_001_tolerates_the_skew_allowance(key_a):
    document = envelope_variant(key_a, overrides={"validFrom": "2026-07-31T12:00:30Z"})
    result = verify_document(document, now=NOW)
    assert "AWR-TIME-001" not in warning_codes(result)


def test_time_002_valid_until_in_the_past(key_a):
    document = envelope_variant(
        key_a, overrides={"validUntil": "2026-07-31T11:00:00Z"}
    )
    result = verify_document(document, now=NOW)
    assert_warning(result, "AWR-TIME-002")
    assert result["valid"] is True


def test_time_002_age_is_not_validity(key_a):
    """Section 11.3: a two-year-old receipt is exactly as sound as a fresh one."""
    old = sign(
        build_unsecured(
            key_a,
            overrides={"validFrom": "2024-01-01T00:00:00Z", "validUntil": "2024-02-01T00:00:00Z"},
        ),
        key_a,
        created="2024-01-01T00:00:00Z",
    )
    result = verify_document(old, now=NOW)
    assert result["valid"] is True
    assert warning_codes(result) == ["AWR-TIME-002"]
