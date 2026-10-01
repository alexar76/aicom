"""Profiles L0 / L1 / L2 (SPEC.md section 10)."""

from __future__ import annotations

import copy

import pytest
from conftest import (
    NOW,
    assert_error,
    assert_warning,
    build_unsecured,
    make_receipt,
    make_verdict,
    sign,
    verdict_subject,
    work_receipt_subject,
)

from awr.documents import document_reference
from awr.verify import verify_document

SETTLEMENT = {
    "scheme": "escrow-evm-v1",
    "chainId": 8453,
    "contract": "0x0000000000000000000000000000000000000000",
    "holdId": "0xabc",
    "amount": {"currency": "USD", "amount": "0.10"},
}

STAKE = {
    "scheme": "stake-evm-v1",
    "chainId": 8453,
    "contract": "0x0000000000000000000000000000000000000001",
    "amount": {"currency": "USD", "amount": "5.00"},
    "slashingPolicy": {
        "id": "urn:example:policy:v2",
        "digestSRI": "sha256-47DEQpj8HBSa+/TImW+5JCeuQeRkm5NMpJWZG3hSuFU=",
    },
}


def staked_verdict(key, receipt, **overrides):
    subject = verdict_subject(receipt, stake=copy.deepcopy(STAKE), **overrides)
    return sign(
        build_unsecured(key, document_type="VerificationVerdict", subject=subject), key
    )


# ---------------------------------------------------------------------------
# L0
# ---------------------------------------------------------------------------


def test_l0_needs_nothing_but_a_keypair(key_a):
    receipt = make_receipt(key_a)
    result = verify_document(receipt, now=NOW, profile="L0")
    assert result["valid"] is True
    assert result["profile"] == "L0"


def test_l0_is_reported_without_a_profile_request(key_a):
    result = verify_document(make_receipt(key_a), now=NOW)
    assert result["profile"] == "L0"


# ---------------------------------------------------------------------------
# L1
# ---------------------------------------------------------------------------


def test_l1_is_satisfied_by_an_independent_verdict(key_a, key_b):
    receipt = make_receipt(key_a)
    verdict = make_verdict(key_b, receipt)
    result = verify_document(receipt, now=NOW, profile="L1", supporting=[verdict])
    assert result["valid"] is True, result
    assert result["profile"] == "L1"


def test_profile_001_no_verdict(key_a):
    receipt = make_receipt(key_a)
    result = verify_document(receipt, now=NOW, profile="L1")
    assert_error(result, "AWR-PROFILE-001")
    assert result["profile"] is None


def test_profile_002_self_verification_is_rejected(key_a):
    """Section 10.2 / 13.3: a verdict signed by the receipt's issuer proves only
    self-consistency, and L1 exists to exclude it structurally."""
    receipt = make_receipt(key_a)
    self_verdict = make_verdict(key_a, receipt)
    assert verify_document(self_verdict, now=NOW)["valid"] is True

    result = verify_document(receipt, now=NOW, profile="L1", supporting=[self_verdict])
    assert_error(result, "AWR-PROFILE-002")
    assert result["profile"] is None


def test_l1_holds_for_a_fail_or_inconclusive_verdict(key_a, key_b):
    for verdict_value in ("fail", "inconclusive"):
        receipt = make_receipt(key_a)
        subject = verdict_subject(receipt, verdict=verdict_value)
        subject.pop("score", None)
        subject.pop("policy", None)
        verdict = sign(
            build_unsecured(key_b, document_type="VerificationVerdict", subject=subject),
            key_b,
        )
        result = verify_document(receipt, now=NOW, profile="L1", supporting=[verdict])
        assert result["profile"] == "L1", (verdict_value, result)


def test_an_invalid_verdict_does_not_satisfy_l1(key_a, key_b):
    receipt = make_receipt(key_a)
    verdict = copy.deepcopy(make_verdict(key_b, receipt))
    verdict["credentialSubject"]["verdict"] = "fail"  # breaks the signature
    result = verify_document(receipt, now=NOW, profile="L1", supporting=[verdict])
    assert_error(result, "AWR-PROFILE-001")


def test_a_verdict_about_another_receipt_does_not_satisfy_l1(key_a, key_b):
    receipt = make_receipt(key_a)
    other = make_receipt(key_a, subject=work_receipt_subject(nonce="01OTHER"))
    verdict = make_verdict(key_b, other)
    result = verify_document(receipt, now=NOW, profile="L1", supporting=[verdict])
    assert_error(result, "AWR-PROFILE-001")


def test_the_verdict_digest_binds_it_to_the_exact_receipt_bytes(key_a, key_b):
    """Section 13.2: a favourable verdict cannot be re-pointed at different work."""
    receipt = make_receipt(key_a, document_id="urn:uuid:target")
    verdict = make_verdict(key_b, receipt)
    substitute = make_receipt(
        key_a, document_id="urn:uuid:target", subject=work_receipt_subject(nonce="01SUB")
    )
    result = verify_document(substitute, now=NOW, profile="L1", supporting=[verdict])
    assert_error(result, "AWR-PROFILE-001")


# ---------------------------------------------------------------------------
# L2
# ---------------------------------------------------------------------------


def test_l2_needs_two_distinct_issuers_and_a_binding(key_a, key_b, key_c):
    receipt = make_receipt(
        key_a, subject=work_receipt_subject(settlement=copy.deepcopy(SETTLEMENT))
    )
    verdicts = [make_verdict(key_b, receipt), make_verdict(key_c, receipt)]
    result = verify_document(receipt, now=NOW, profile="L2", supporting=verdicts)
    assert result["valid"] is True, result
    assert result["profile"] == "L2"
    assert_warning(result, "AWR-L2-001")


def test_profile_003_one_verdict_is_not_enough_for_l2(key_a, key_b):
    receipt = make_receipt(
        key_a, subject=work_receipt_subject(settlement=copy.deepcopy(SETTLEMENT))
    )
    result = verify_document(
        receipt, now=NOW, profile="L2", supporting=[make_verdict(key_b, receipt)]
    )
    assert_error(result, "AWR-PROFILE-003")
    assert "AWR-PROFILE-001" not in [r["code"] for r in result["reasons"]]


def test_profile_003_two_verdicts_from_one_issuer_are_one_issuer(key_a, key_b):
    receipt = make_receipt(
        key_a, subject=work_receipt_subject(settlement=copy.deepcopy(SETTLEMENT))
    )
    verdicts = [
        make_verdict(key_b, receipt, document_id="urn:uuid:verdict-1"),
        make_verdict(
            key_b,
            receipt,
            document_id="urn:uuid:verdict-2",
            subject_overrides={"score": "0.91"},
        ),
    ]
    result = verify_document(receipt, now=NOW, profile="L2", supporting=verdicts)
    assert_error(result, "AWR-PROFILE-003")


def test_profile_003_the_receipt_issuer_never_counts(key_a, key_b):
    receipt = make_receipt(
        key_a, subject=work_receipt_subject(settlement=copy.deepcopy(SETTLEMENT))
    )
    verdicts = [make_verdict(key_a, receipt), make_verdict(key_b, receipt)]
    result = verify_document(receipt, now=NOW, profile="L2", supporting=verdicts)
    assert_error(result, "AWR-PROFILE-003")


def test_profile_004_no_accountability_binding(key_a, key_b, key_c):
    receipt = make_receipt(key_a)
    verdicts = [make_verdict(key_b, receipt), make_verdict(key_c, receipt)]
    result = verify_document(receipt, now=NOW, profile="L2", supporting=verdicts)
    assert_error(result, "AWR-PROFILE-004")
    assert result["profilesEvaluated"]["L1"] == []


def test_l2_binding_may_be_stake_on_every_verdict(key_a, key_b, key_c):
    receipt = make_receipt(key_a)
    verdicts = [staked_verdict(key_b, receipt), staked_verdict(key_c, receipt)]
    result = verify_document(receipt, now=NOW, profile="L2", supporting=verdicts)
    assert result["valid"] is True, result
    assert result["profile"] == "L2"
    assert_warning(result, "AWR-L2-001")


def test_profile_004_stake_on_only_one_verdict_is_not_a_binding(key_a, key_b, key_c):
    receipt = make_receipt(key_a)
    verdicts = [staked_verdict(key_b, receipt), make_verdict(key_c, receipt)]
    assert_error(
        verify_document(receipt, now=NOW, profile="L2", supporting=verdicts),
        "AWR-PROFILE-004",
    )


def test_l2_001_is_a_warning_not_a_verification_of_the_chain(key_a):
    receipt = make_receipt(
        key_a, subject=work_receipt_subject(settlement=copy.deepcopy(SETTLEMENT))
    )
    result = verify_document(receipt, now=NOW)
    assert_warning(result, "AWR-L2-001")
    assert result["valid"] is True
    detail = [w["detail"] for w in result["warnings"] if w["code"] == "AWR-L2-001"][0]
    assert "NOT checked" in detail


def test_a_malformed_settlement_amount_is_reported(key_a):
    bad = copy.deepcopy(SETTLEMENT)
    bad["amount"] = {"currency": "USD", "amount": "ten cents"}
    receipt = make_receipt(key_a, subject=work_receipt_subject(settlement=bad))
    assert_error(verify_document(receipt, now=NOW), "AWR-RCPT-002")


# ---------------------------------------------------------------------------
# section 10.4 -- reporting
# ---------------------------------------------------------------------------


def test_a_profile_is_never_granted_by_self_assertion(key_a):
    """Section 3.3: awrProfile is a hint; a verifier MUST NOT grant a level for it."""
    receipt = make_receipt(key_a, subject=work_receipt_subject(awrProfile="L2"))
    result = verify_document(receipt, now=NOW)
    assert result["valid"] is True
    assert result["profile"] == "L0"


def test_every_evaluated_and_rejected_profile_reports_its_codes(key_a):
    receipt = make_receipt(key_a)
    result = verify_document(receipt, now=NOW)
    evaluated = result["profilesEvaluated"]
    assert [entry["code"] for entry in evaluated["L1"]] == ["AWR-PROFILE-001"]
    assert [entry["code"] for entry in evaluated["L2"]] == [
        "AWR-PROFILE-001",
        "AWR-PROFILE-003",
        "AWR-PROFILE-004",
    ]
    # Not requested, so not errors: the document is still valid at L0.
    assert result["valid"] is True


def test_the_highest_satisfied_profile_is_reported_without_being_requested(key_a, key_b, key_c):
    receipt = make_receipt(
        key_a, subject=work_receipt_subject(settlement=copy.deepcopy(SETTLEMENT))
    )
    one = [make_verdict(key_b, receipt)]
    two = one + [make_verdict(key_c, receipt)]
    assert verify_document(receipt, now=NOW, supporting=one)["profile"] == "L1"
    assert verify_document(receipt, now=NOW, supporting=two)["profile"] == "L2"


def test_profiles_above_l0_are_not_defined_for_a_verdict(key_a, key_b):
    receipt = make_receipt(key_a)
    verdict = make_verdict(key_b, receipt)
    result = verify_document(verdict, now=NOW, profile="L1", supporting=[receipt])
    assert_error(result, "AWR-PROFILE-001")


def test_an_invalid_document_has_no_profile(key_a):
    receipt = copy.deepcopy(make_receipt(key_a))
    receipt["credentialSubject"]["work"]["status"] = "nope"
    result = verify_document(receipt, now=NOW)
    assert result["valid"] is False
    assert result["profile"] is None
