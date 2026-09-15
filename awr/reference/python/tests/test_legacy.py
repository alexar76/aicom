"""AWR/1 legacy verification (SPEC.md section 12).

Legacy documents are assembled by the test suite from raw Ed25519 signatures over the
legacy canonical form, because the package deliberately exposes no way to issue one.
"""

from __future__ import annotations

import base64
import copy
import json
import os

import pytest
from conftest import (
    CREATED,
    NOW,
    assert_error,
    assert_warning,
    legacy_document,
    make_receipt,
    sri_of,
)

from awr.legacy import (
    DIALECT_FLOAT_COERCING,
    DIALECT_INTEGER_PRESERVING,
    LEGACY_PROOF_TYPE,
    is_legacy_document,
    legacy_canonical_form,
)
from awr.verify import verify_document

LEGACY_SUBJECT = {
    "modelId": "gpt-legacy@vendor",
    "latencyMs": 2340,
    "status": "succeeded",
    "inputHash": sri_of(b"legacy input"),
    "outputHash": sri_of(b"legacy output"),
    "priceUsd": "0.15",
    "note": "café",
}


# ---------------------------------------------------------------------------
# the two dialects
# ---------------------------------------------------------------------------


def test_the_two_dialects_differ_exactly_on_integer_rendering():
    a = legacy_canonical_form(LEGACY_SUBJECT, DIALECT_INTEGER_PRESERVING)
    b = legacy_canonical_form(LEGACY_SUBJECT, DIALECT_FLOAT_COERCING)
    assert a != b
    assert b"latencyMs=2340|" in a
    assert b"latencyMs=2340.0|" in b
    assert a.replace(b"latencyMs=2340|", b"latencyMs=2340.0|") == b


def test_the_legacy_form_is_pipe_delimited_and_sorted_by_code_point():
    rendered = legacy_canonical_form(LEGACY_SUBJECT, DIALECT_INTEGER_PRESERVING).decode()
    fields = rendered.split("|")
    names = [field.split("=", 1)[0] for field in fields]
    assert names == sorted(names)
    assert names == [
        "inputHash",
        "latencyMs",
        "modelId",
        "note",
        "outputHash",
        "priceUsd",
        "status",
    ]


def test_the_legacy_form_applies_nfc_unlike_awr2():
    decomposed = {"note": "café"}
    composed = {"note": "café"}
    assert legacy_canonical_form(decomposed, "A") == legacy_canonical_form(composed, "A")
    # AWR/2 must not do this (section 4.1 item 2).
    from awr.jcs import canonicalize

    assert canonicalize(decomposed) != canonicalize(composed)


def test_nested_objects_and_arrays_are_flattened():
    subject = {"a": {"b": 1}, "c": [10, 20], "d": True, "e": None}
    rendered = legacy_canonical_form(subject, DIALECT_INTEGER_PRESERVING).decode()
    assert rendered == "a.b=1|c.0=10|c.1=20|d=true|e=null"


def test_legacy_rendering_rejects_an_unknown_dialect():
    with pytest.raises(ValueError):
        legacy_canonical_form(LEGACY_SUBJECT, "C")


# ---------------------------------------------------------------------------
# verification under both dialects
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("dialect", [DIALECT_INTEGER_PRESERVING, DIALECT_FLOAT_COERCING])
def test_legacy_001_a_document_signed_under_either_dialect_verifies(key_a, dialect):
    document = legacy_document(key_a, LEGACY_SUBJECT, dialect=dialect)
    assert is_legacy_document(document) is True
    result = verify_document(document, now=NOW)
    assert result["valid"] is True, result
    assert_warning(result, "AWR-LEGACY-001")
    # Section 12.4: the result names a KEY, never an issuer.
    assert result["legacy"]["dialect"] == dialect
    assert result["legacy"]["keySource"] == "document"
    assert result["legacy"]["issuerAttested"] is False
    assert result["legacy"]["verifiedKey"] == key_a.did
    assert result["legacyDialect"] == dialect


def test_legacy_002_neither_dialect_verifies(key_a):
    document = legacy_document(key_a, LEGACY_SUBJECT, signature=b"\x00" * 64)
    result = verify_document(document, now=NOW)
    assert_error(result, "AWR-LEGACY-002")
    assert_warning(result, "AWR-LEGACY-001")


def test_legacy_002_a_signature_over_tampered_content_fails(key_a):
    document = legacy_document(key_a, LEGACY_SUBJECT)
    document["credentialSubject"]["priceUsd"] = "9.99"
    assert_error(verify_document(document, now=NOW), "AWR-LEGACY-002")


def test_legacy_001_is_reported_on_every_legacy_document(key_a):
    good = legacy_document(key_a, LEGACY_SUBJECT)
    bad = legacy_document(key_a, LEGACY_SUBJECT, signature=b"\x01" * 64)
    for document in (good, bad):
        assert_warning(verify_document(document, now=NOW), "AWR-LEGACY-001")


# ---------------------------------------------------------------------------
# section 12.3: the version gate
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "mutate,label",
    [
        (lambda d: d.update({"awrVersion": "2.0.0"}), "awrVersion"),
        (lambda d: d.update({"@context": [
            "https://www.w3.org/ns/credentials/v2",
            "https://verify.modelmarket.dev/ns/awr/v2",
        ]}), "context"),
        (lambda d: d.update({"validFrom": "2026-07-31T12:00:05Z"}), "validFrom"),
        (lambda d: d["credentialSubject"].update({"settlement": {"chain": "eip155:8453"}}),
         "settlement"),
        (lambda d: d.update({"proof": [d["proof"], {"type": "DataIntegrityProof"}]}),
         "a DataIntegrityProof beside the AWR/1 proof"),
    ],
)
def test_legacy_003_an_awr2_signal_beside_an_awr1_proof_is_rejected(key_a, mutate, label):
    """Section 12.3: the whole downgrade forgery, one AWR/2 signal at a time.

    The signature over the section 12.1 rendering is genuine in every one of these -- the
    attacker made it with their own key.  What must reject the document is the
    classification, before any signature is checked.
    """
    document = legacy_document(key_a, LEGACY_SUBJECT)
    mutate(document)
    assert is_legacy_document(document) is False
    result = verify_document(document, now=NOW)
    assert result["valid"] is False, label
    assert_error(result, "AWR-LEGACY-003")
    # No fallback to either rule set: the document was verified under neither, so no
    # section 6.1 proof was checked and AWR-LEGACY-001 is NOT reported (section 11.1).
    assert result["verifiedProof"] is None
    assert [w["code"] for w in result["warnings"]] == []


def test_legacy_003_does_not_depend_on_the_position_in_a_proof_array(key_a):
    """Section 12.3: an AWR/1 proof anywhere is the signal; ordering must not matter."""
    base = legacy_document(key_a, LEGACY_SUBJECT)
    awr1 = base["proof"]
    awr2 = {"type": "DataIntegrityProof", "cryptosuite": "eddsa-jcs-2022"}
    for order in ([awr1, awr2], [awr2, awr1]):
        document = copy.deepcopy(base)
        document["proof"] = order
        assert_error(verify_document(document, now=NOW), "AWR-LEGACY-003")


def test_the_legacy_path_is_never_selected_by_a_content_heuristic(key_a):
    """Section 12.3: no heuristic over credentialSubject may route to section 12.

    LEGACY_SUBJECT carries the AWR/1-era inputHash/outputHash members, which one verifier
    used as a heuristic.  With no AWR/1 proof present the document is AWR/2 and reports
    AWR/2 codes, never AWR-LEGACY-001.
    """
    document = legacy_document(key_a, LEGACY_SUBJECT)
    del document["proof"]
    assert is_legacy_document(document) is False
    result = verify_document(document, now=NOW)
    assert "AWR-LEGACY-001" not in [w["code"] for w in result["warnings"]]
    assert_error(result, "AWR-PROOF-001")


def test_legacy_005_the_caller_can_decline_section_12(key_a):
    """Section 12.3: support for AWR/1 is OPTIONAL, so declining it must be possible."""
    document = legacy_document(key_a, LEGACY_SUBJECT)
    result = verify_document(document, now=NOW, no_legacy=True)
    assert result["valid"] is False
    assert_error(result, "AWR-LEGACY-005")
    assert [w["code"] for w in result["warnings"]] == []


# ---------------------------------------------------------------------------
# section 12.4: the unsigned issuer
# ---------------------------------------------------------------------------


def test_legacy_004_a_key_taken_from_the_document_attests_no_issuer(key_a):
    document = legacy_document(key_a, LEGACY_SUBJECT)
    result = verify_document(document, now=NOW)
    assert result["valid"] is True
    assert_warning(result, "AWR-LEGACY-004")
    assert result["legacy"]["keySource"] == "document"
    assert result["legacy"]["issuerAttested"] is False


def test_an_expected_key_supplied_out_of_band_is_the_only_key_tried(key_a, key_b):
    document = legacy_document(key_a, LEGACY_SUBJECT)

    anchored = verify_document(document, now=NOW, expected_key=key_a.public_key_bytes)
    assert anchored["valid"] is True
    assert anchored["legacy"]["keySource"] == "caller"
    assert anchored["legacy"]["verifiedKey"] == key_a.did
    # Section 12.4: with a caller key there is nothing unanchored to warn about.
    assert "AWR-LEGACY-004" not in [w["code"] for w in anchored["warnings"]]

    # The document still carries key_a's publicKeyJwk. It MUST NOT be used as a fallback
    # when the caller's key fails -- that would hand the choice of key back to the sender.
    wrong = verify_document(document, now=NOW, expected_key=key_b.public_key_bytes)
    assert wrong["valid"] is False
    assert_error(wrong, "AWR-LEGACY-002")


def test_key_003_issuer_id_and_the_embedded_key_must_not_disagree(key_a, key_b):
    """Section 12.4: the forgery that survives the version gate.

    issuer.id names the victim; the embedded publicKeyJwk is the attacker's, and the
    signature is the attacker's too, so it verifies. Two statements about the signer, and
    AWR/1 signs neither.
    """
    document = legacy_document(key_b, LEGACY_SUBJECT)
    document["issuer"]["id"] = key_a.did
    result = verify_document(document, now=NOW)
    assert result["valid"] is False
    assert_error(result, "AWR-KEY-003")
    assert result["legacy"]["verifiedKey"] is None


def test_key_003_reads_the_did_through_a_verificationmethod_fragment(key_a, key_b):
    """Section 12.4/5.3: `did:key:z6Mk...#z6Mk...` names the same key as the bare DID.

    The victim's DID is a literal prefix of this issuer.id, so a reader sees the victim --
    and an implementation that parses only the bare form loses the cross-check entirely.
    """
    document = legacy_document(key_b, LEGACY_SUBJECT)
    document["issuer"]["id"] = key_a.verification_method
    assert_error(verify_document(document, now=NOW), "AWR-KEY-003")


def test_agreeing_key_statements_are_not_rejected(key_a):
    """The control: an honest AWR/1 document must survive the section 12.4 cross-check."""
    document = legacy_document(key_a, LEGACY_SUBJECT)
    document["issuer"]["id"] = key_a.did
    result = verify_document(document, now=NOW)
    assert result["valid"] is True, result
    assert_warning(result, "AWR-LEGACY-004")


def test_the_legacy_unsigned_fields_are_reported_as_unsigned(key_a):
    """Section 12 / 13.1: id, type, issuer and hubInfo are outside the AWR/1 signature."""
    document = legacy_document(key_a, LEGACY_SUBJECT)
    result = verify_document(document, now=NOW)
    assert set(result["unsignedFields"]) == {"id", "type", "issuer", "hubInfo"}

    # Renaming the receipt and re-pointing its type does not break an AWR/1 signature --
    # which is exactly why AWR/2 signs the whole document.
    renamed = copy.deepcopy(document)
    renamed["id"] = "urn:uuid:renamed-by-an-intermediary"
    renamed["hubInfo"] = {"name": "someone-else"}
    still_valid = verify_document(renamed, now=NOW)
    assert still_valid["valid"] is True
    assert still_valid["unsignedFields"] == result["unsignedFields"]


def test_a_legacy_document_with_non_integer_numbers_is_still_verifiable(key_a):
    """Section 4.3's number restriction is an AWR/2 signing rule; AWR/1 predates it."""
    subject = {"modelId": "m@v", "latencyMs": 2340, "score": 0.93}
    document = legacy_document(key_a, subject, dialect=DIALECT_INTEGER_PRESERVING)
    payload = json.dumps(document).encode("utf-8")
    assert b"0.93" in payload
    result = verify_document(payload, now=NOW)
    assert result["valid"] is True, result
    assert result["legacy"]["dialect"] == DIALECT_INTEGER_PRESERVING


def test_an_awr2_document_with_a_non_integer_number_is_still_rejected(key_a):
    receipt = make_receipt(key_a)
    payload = json.dumps(receipt).replace('"latencyMs": 2340', '"latencyMs": 0.5')
    assert_error(verify_document(payload.encode("utf-8"), now=NOW), "AWR-CANON-001")


def test_a_legacy_proof_value_must_be_base64_not_multibase(key_a):
    document = legacy_document(key_a, LEGACY_SUBJECT)
    document["proof"]["proofValue"] = "z" + document["proof"]["proofValue"]
    assert_error(verify_document(document, now=NOW), "AWR-PROOF-005")


def test_a_legacy_document_without_a_usable_key_is_reported(key_a):
    document = legacy_document(key_a, LEGACY_SUBJECT)
    del document["issuer"]["publicKeyJwk"]
    assert_error(verify_document(document, now=NOW), "AWR-KEY-001")


def test_a_legacy_document_may_carry_the_key_as_base64(key_a):
    document = legacy_document(key_a, LEGACY_SUBJECT)
    del document["issuer"]["publicKeyJwk"]
    document["issuer"]["publicKeyBase64"] = base64.b64encode(
        key_a.public_key_bytes
    ).decode("ascii")
    assert verify_document(document, now=NOW)["valid"] is True


def test_a_legacy_document_is_not_checked_against_awr2_envelope_rules(key_a):
    """The AWR/1 envelope has no awrVersion and no AWR/2 @context; those are not errors."""
    document = legacy_document(key_a, LEGACY_SUBJECT)
    assert "awrVersion" not in document
    result = verify_document(document, now=NOW)
    codes = [entry["code"] for entry in result["reasons"]]
    assert codes == []
    assert result["awrVersion"] is None


# ---------------------------------------------------------------------------
# legacy issuance is impossible
# ---------------------------------------------------------------------------


def test_the_package_exposes_no_legacy_issuer():
    import awr
    import awr.legacy

    assert not [
        name
        for name in dir(awr.legacy)
        if name.startswith("issue") or name.startswith("make_legacy")
    ]
    assert not [name for name in dir(awr) if "legacy" in name.lower() and "issue" in name.lower()]


def test_only_the_legacy_module_mentions_the_legacy_suite():
    import awr

    package_dir = os.path.dirname(os.path.abspath(awr.__file__))
    mentions = {}
    for name in sorted(os.listdir(package_dir)):
        if not name.endswith(".py"):
            continue
        with open(os.path.join(package_dir, name), "r", encoding="utf-8") as handle:
            source = handle.read()
        if LEGACY_PROOF_TYPE in source:
            mentions[name] = source
    # legacy.py defines the constant; __init__.py names it only in its module docstring.
    assert sorted(mentions) == ["__init__.py", "legacy.py"]
    init_source = mentions["__init__.py"]
    assert init_source.index(LEGACY_PROOF_TYPE) < init_source.index('__version__')
    assert 'LEGACY_PROOF_TYPE = "%s"' % (LEGACY_PROOF_TYPE,) in mentions["legacy.py"]


def test_issue_cannot_be_talked_into_emitting_a_legacy_proof(key_a):
    from awr.documents import issue
    from conftest import work_receipt_subject

    with pytest.raises(ValueError):
        issue(
            work_receipt_subject(),
            key_a,
            extra_properties={
                "proof": {"type": LEGACY_PROOF_TYPE, "proofValue": "AAAA"}
            },
        )


def test_every_issued_document_uses_the_awr2_suite(key_a):
    from awr.documents import (
        issue_blame_attestation,
        issue_verification_verdict,
        issue_work_receipt,
    )
    from conftest import blame_subject, verdict_subject, work_receipt_subject

    receipt = issue_work_receipt(work_receipt_subject(), key_a, created=CREATED)
    verdict = issue_verification_verdict(verdict_subject(receipt), key_a, created=CREATED)
    blame = issue_blame_attestation(
        blame_subject(receipt, receipt), key_a, created=CREATED
    )
    for document in (receipt, verdict, blame):
        assert document["proof"]["type"] == "DataIntegrityProof"
        assert document["proof"]["cryptosuite"] == "eddsa-jcs-2022"
        assert document["proof"]["proofValue"].startswith("z")
        assert is_legacy_document(document) is False
