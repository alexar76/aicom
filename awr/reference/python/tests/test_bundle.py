"""Bundles (SPEC.md section 9)."""

from __future__ import annotations

import copy

import pytest
from conftest import (
    NOW,
    assert_error,
    build_unsecured,
    make_receipt,
    make_verdict,
    sign,
    work_receipt_subject,
)

from awr.documents import document_reference
from awr.verify import make_bundle, verify, verify_bundle


def test_a_bundle_is_a_transport_container_and_is_not_signed(key_a, key_b):
    receipt = make_receipt(key_a)
    verdict = make_verdict(key_b, receipt)
    bundle = make_bundle([receipt, verdict])
    assert bundle["awrBundle"] == "2.0"
    assert "proof" not in bundle
    result = verify_bundle(bundle, now=NOW, profile="L1")
    assert result["valid"] is True, result
    assert result["profile"] == "L1"
    assert result["subjectId"] == receipt["id"]
    assert result["bundleDocuments"] == 2


def test_verify_dispatches_on_the_awr_bundle_member(key_a, key_b):
    receipt = make_receipt(key_a)
    verdict = make_verdict(key_b, receipt)
    import json

    payload = json.dumps(make_bundle([receipt, verdict])).encode("utf-8")
    result = verify(payload, now=NOW, profile="L1")
    assert result["valid"] is True, result
    assert result["profile"] == "L1"


def test_bundle_order_does_not_matter(key_a, key_b):
    receipt = make_receipt(key_a)
    verdict = make_verdict(key_b, receipt)
    first = verify_bundle(make_bundle([receipt, verdict]), now=NOW, profile="L1")
    second = verify_bundle(make_bundle([verdict, receipt]), now=NOW, profile="L1")
    assert first["valid"] and second["valid"]
    assert first["subjectId"] == second["subjectId"] == receipt["id"]


@pytest.mark.parametrize(
    "bundle",
    [
        {"documents": []},
        {"awrBundle": "1.0", "documents": []},
        {"awrBundle": "2.0", "documents": []},
        {"awrBundle": "2.0"},
        {"awrBundle": "2.0", "documents": {}},
        {"awrBundle": 2.0},
    ],
)
def test_bundle_001_version_or_documents(bundle):
    assert_error(verify_bundle(bundle, now=NOW), "AWR-BUNDLE-001")


def test_a_bundle_carrying_a_non_integer_number_is_rejected_at_parse_time():
    """The bundle itself is not signed, but its bytes still go through the parser."""
    assert_error(
        verify_bundle(b'{"awrBundle": 2.0, "documents": []}', now=NOW), "AWR-CANON-001"
    )


def test_bundle_001_an_unsupported_version_is_reported(key_a):
    bundle = make_bundle([make_receipt(key_a)])
    bundle["awrBundle"] = "3.0"
    assert_error(verify_bundle(bundle, now=NOW), "AWR-BUNDLE-001")


def test_bundle_001_a_non_object_document(key_a):
    bundle = make_bundle([make_receipt(key_a)])
    bundle["documents"].append("not a document")
    assert_error(verify_bundle(bundle, now=NOW), "AWR-BUNDLE-001")


def test_bundle_002_duplicate_id_with_differing_content(key_a):
    receipt = make_receipt(key_a, document_id="urn:uuid:same-id")
    impostor = make_receipt(
        key_a, document_id="urn:uuid:same-id", subject=work_receipt_subject(nonce="01X")
    )
    bundle = make_bundle([receipt, impostor])
    assert_error(verify_bundle(bundle, now=NOW), "AWR-BUNDLE-002")


def test_bundle_002_duplicate_id_with_identical_content_is_not_an_error(key_a):
    receipt = make_receipt(key_a, document_id="urn:uuid:same-id")
    bundle = make_bundle([receipt, copy.deepcopy(receipt)])
    result = verify_bundle(bundle, now=NOW, subject_id="urn:uuid:same-id")
    assert "AWR-BUNDLE-002" not in [r["code"] for r in result["reasons"]]


def test_bundle_003_two_unreferenced_receipts_are_ambiguous(key_a):
    """§9: ambiguity is a profile-time fault, not a container-time one.

    Two receipts neither of which is anyone's parent is a perfectly good transport
    container — there is simply no answer to "which one is the subject", and that question
    is only asked when a profile is being evaluated.
    """
    first = make_receipt(key_a)
    second = make_receipt(key_a, subject=work_receipt_subject(nonce="01SECOND"))
    bundle = make_bundle([first, second])

    no_profile = verify_bundle(bundle, now=NOW)
    assert no_profile["valid"] is True, no_profile

    assert_error(verify_bundle(bundle, now=NOW, profile="L0"), "AWR-BUNDLE-003")


def test_bundle_003_an_explicit_subject_resolves_the_ambiguity(key_a):
    first = make_receipt(key_a)
    second = make_receipt(key_a, subject=work_receipt_subject(nonce="01SECOND"))
    result = verify_bundle(
        make_bundle([first, second]), now=NOW, subject_id=second["id"]
    )
    assert result["valid"] is True, result
    assert result["subjectId"] == second["id"]


def test_bundle_003_no_receipt_at_all_is_ambiguous(key_a, key_b):
    """A lone verdict is a valid container and an impossible profile subject.

    This is the case three independent implementations answered three different ways
    before §9 said when subject selection runs: valid, AWR-BUNDLE-003, AWR-BUNDLE-003.
    """
    receipt = make_receipt(key_a)
    verdict = make_verdict(key_b, receipt)
    bundle = make_bundle([verdict])

    assert verify_bundle(bundle, now=NOW)["valid"] is True
    assert_error(verify_bundle(bundle, now=NOW, profile="L0"), "AWR-BUNDLE-003")


def test_bundle_003_an_unknown_explicit_subject_is_reported(key_a):
    bundle = make_bundle([make_receipt(key_a)])
    assert_error(
        verify_bundle(bundle, now=NOW, subject_id="urn:uuid:absent"), "AWR-BUNDLE-003"
    )


def test_the_subject_is_the_receipt_no_one_calls_a_parent(key_a, key_b):
    parent = make_receipt(key_a)
    child = sign(
        build_unsecured(
            key_a, subject=work_receipt_subject(parents=[document_reference(parent)])
        ),
        key_a,
    )
    verdict = make_verdict(key_b, child)
    result = verify_bundle(make_bundle([parent, child, verdict]), now=NOW, profile="L1")
    assert result["valid"] is True, result
    assert result["subjectId"] == child["id"]
    assert result["chain"] == {"resolved": 1, "unresolved": 0}
    assert result["profile"] == "L1"


def test_bundle_defects_and_document_defects_are_reported_together(key_a):
    """Section 11.1: a bundle-level defect does not hide the defects inside it.

    The container version is supported here, so the walk proceeds; the bundle defect is
    an entry of ``documents`` that is not a JSON object (``AWR-BUNDLE-001``).
    """
    receipt = copy.deepcopy(make_receipt(key_a))
    receipt["credentialSubject"]["work"]["status"] = "nope"  # also breaks the signature
    bundle = make_bundle([receipt])
    bundle["documents"].append("not an object")
    result = verify_bundle(bundle, now=NOW)
    codes = [entry["code"] for entry in result["reasons"]]
    assert "AWR-BUNDLE-001" in codes
    assert "AWR-RCPT-006" in codes
    assert "AWR-PROOF-006" in codes


def test_an_unsupported_bundle_version_stops_before_the_documents(key_a):
    """Section 9: fail closed on a container version this implementation does not know.

    ``awrBundle`` is the only statement of the container's schema, so nothing inside may
    be processed -- reaching in to pull out things merely *assumed* to be documents is
    the verifier deciding for itself which bytes to read.  Two of the three AWR/2
    implementations verified the enclosed receipt anyway and reported its
    ``documentType`` and ``verifiedProof``; all three reported ``AWR-BUNDLE-001``, so no
    code set revealed the disagreement.
    """
    receipt = copy.deepcopy(make_receipt(key_a))
    receipt["credentialSubject"]["work"]["status"] = "nope"  # also breaks the signature
    bundle = make_bundle([receipt])
    bundle["awrBundle"] = "9.9"
    result = verify_bundle(bundle, now=NOW)
    assert [entry["code"] for entry in result["reasons"]] == ["AWR-BUNDLE-001"]
    assert result["valid"] is False
    # Section 11.1: nothing was read out of the container, so nothing is reported about it.
    assert result["documentType"] is None
    assert result["verifiedProof"] is None
    assert result["profile"] is None


def test_every_claim_in_a_bundle_is_verified_individually(key_a, key_b):
    """A bundle carries no claims: a broken verdict inside it cannot lend validity."""
    receipt = make_receipt(key_a)
    verdict = copy.deepcopy(make_verdict(key_b, receipt))
    verdict["credentialSubject"]["score"] = "0.99"  # breaks the verdict's signature
    result = verify_bundle(make_bundle([receipt, verdict]), now=NOW, profile="L1")
    assert_error(result, "AWR-PROFILE-001")


def test_make_bundle_rejects_an_empty_document_list():
    with pytest.raises(ValueError):
        make_bundle([])
