"""Work chains: edges, limits, cycles (SPEC.md section 8)."""

from __future__ import annotations

import copy
import os

import pytest
from conftest import (
    NOW,
    assert_error,
    assert_warning,
    build_unsecured,
    make_receipt,
    sign,
    sri_of,
    work_receipt_subject,
)

from awr.documents import document_reference
from awr.verify import DEFAULT_MAX_DEPTH, verify_document


def linear_chain(key, length):
    """A chain of *length* receipts, each committing to the previous one's exact bytes."""
    documents = []
    previous = None
    for index in range(length):
        subject = work_receipt_subject(
            inputDigest=sri_of(b"payload-%d" % (index,)),
            outputDigest=sri_of(b"payload-%d" % (index + 1,)),
        )
        if previous is not None:
            subject["parents"] = [dict(document_reference(previous), role="subagent")]
            subject["inputDigest"] = previous["credentialSubject"]["outputDigest"]
        documents.append(make_receipt(key, subject=subject))
        previous = documents[-1]
    return documents


# ---------------------------------------------------------------------------
# section 8.1 -- edges commit to the parent's exact bytes, proof included
# ---------------------------------------------------------------------------


def test_a_resolved_edge_is_reported_as_resolved(key_a):
    parent, child = linear_chain(key_a, 2)
    result = verify_document(child, now=NOW, supporting=[parent])
    assert result["valid"] is True, result
    assert result["chain"] == {"resolved": 1, "unresolved": 0}


def test_the_verifier_reports_which_edges_it_resolved(key_a):
    """Section 8.2: "chain intact" and "chain not checked" must be distinguishable."""
    grandparent, parent, child = linear_chain(key_a, 3)
    result = verify_document(child, now=NOW, supporting=[parent])
    assert result["chain"] == {"resolved": 1, "unresolved": 1}
    resolved = result["chainEdges"]["resolved"]
    unresolved = result["chainEdges"]["unresolved"]
    assert [edge["parentId"] for edge in resolved] == [parent["id"]]
    assert [edge["parentId"] for edge in unresolved] == [grandparent["id"]]
    assert resolved[0]["childId"] == child["id"]
    assert resolved[0]["digestSRI"] == document_reference(parent)["digestSRI"]


def test_an_absent_parent_is_unresolved_and_not_an_error(key_a):
    parent, child = linear_chain(key_a, 2)
    result = verify_document(child, now=NOW)
    assert result["valid"] is True
    assert result["chain"] == {"resolved": 0, "unresolved": 1}


def test_the_edge_covers_the_parents_proof(key_a):
    """Section 8.1: the digest is over the *secured* parent, signature included."""
    parent, child = linear_chain(key_a, 2)
    without_proof = {k: v for k, v in parent.items() if k != "proof"}
    result = verify_document(child, now=NOW, supporting=[without_proof])
    assert result["chain"] == {"resolved": 0, "unresolved": 1}


def test_a_tampered_parent_no_longer_matches_its_edge(key_a):
    parent, child = linear_chain(key_a, 2)
    tampered = copy.deepcopy(parent)
    tampered["credentialSubject"]["work"]["modelId"] = "cheaper-model@vendor"
    result = verify_document(child, now=NOW, supporting=[tampered])
    # Same id, different bytes: reported, not silently resolved.
    assert_error(result, "AWR-CHAIN-003")


def test_a_long_resolved_chain_counts_every_edge(key_a):
    documents = linear_chain(key_a, 8)
    result = verify_document(documents[-1], now=NOW, supporting=documents[:-1])
    assert result["valid"] is True, result
    assert result["chain"] == {"resolved": 7, "unresolved": 0}


# ---------------------------------------------------------------------------
# AWR-CHAIN-001 / 002 -- malformed edges
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "entry", [{"id": "urn:uuid:parent"}, {"role": "retrieval"}, {}, "urn:uuid:parent", 7]
)
def test_chain_001_parents_entry_without_digest(key_a, entry):
    document = sign(
        build_unsecured(key_a, subject=work_receipt_subject(parents=[entry])), key_a
    )
    assert_error(verify_document(document, now=NOW), "AWR-CHAIN-001")


def test_chain_001_parents_not_an_array(key_a):
    document = sign(
        build_unsecured(key_a, subject=work_receipt_subject(parents={"id": "x"})), key_a
    )
    assert_error(verify_document(document, now=NOW), "AWR-CHAIN-001")


@pytest.mark.parametrize(
    "digest_sri",
    [
        "sha512-" + "A" * 86 + "==",
        "md5-" + "A" * 22 + "==",
        "sha256-47DEQpj8HBSa_TImW-5JCeuQeRkm5NMpJWZG3hSuFU=",  # base64url
        "sha256-",
        "47DEQpj8HBSa+/TImW+5JCeuQeRkm5NMpJWZG3hSuFU=",
        12345,
    ],
)
def test_chain_002_digest_reference_format_or_algorithm(key_a, digest_sri):
    """Section 3.2: another algorithm prefix MUST be reported, never ignored."""
    document = sign(
        build_unsecured(
            key_a,
            subject=work_receipt_subject(
                parents=[{"id": "urn:uuid:parent", "digestSRI": digest_sri}]
            ),
        ),
        key_a,
    )
    assert_error(verify_document(document, now=NOW), "AWR-CHAIN-002")


def test_chain_002_role_must_be_a_string(key_a):
    document = sign(
        build_unsecured(
            key_a,
            subject=work_receipt_subject(
                parents=[{"digestSRI": sri_of(b"p"), "role": ["retrieval"]}]
            ),
        ),
        key_a,
    )
    assert_error(verify_document(document, now=NOW), "AWR-CHAIN-002")


# ---------------------------------------------------------------------------
# AWR-CHAIN-003 -- digest mismatch against a supplied parent
# ---------------------------------------------------------------------------


def test_chain_003_supplied_parent_has_a_different_digest(key_a):
    parent = make_receipt(key_a, document_id="urn:uuid:parent-1")
    impostor = make_receipt(
        key_a,
        document_id="urn:uuid:parent-1",
        subject=work_receipt_subject(nonce="01J9Z8QK4T7YB2N5V6W8XA3C0Z"),
    )
    child = sign(
        build_unsecured(
            key_a, subject=work_receipt_subject(parents=[document_reference(impostor)])
        ),
        key_a,
    )
    result = verify_document(child, now=NOW, supporting=[parent])
    assert_error(result, "AWR-CHAIN-003")
    assert result["chain"]["resolved"] == 0


# ---------------------------------------------------------------------------
# AWR-CHAIN-004 -- cycles
# ---------------------------------------------------------------------------


def test_chain_004_identifier_level_cycle(key_a):
    """A digest-level cycle is not constructible (section 8.1), an id-level one is."""
    b = sign(
        build_unsecured(
            key_a,
            document_id="urn:uuid:hop-b",
            subject=work_receipt_subject(
                parents=[{"id": "urn:uuid:hop-a", "digestSRI": sri_of(b"forged-a")}]
            ),
        ),
        key_a,
    )
    a = sign(
        build_unsecured(
            key_a,
            document_id="urn:uuid:hop-a",
            subject=work_receipt_subject(parents=[document_reference(b)]),
        ),
        key_a,
    )
    result = verify_document(a, now=NOW, supporting=[a, b])
    assert_error(result, "AWR-CHAIN-004")
    assert_error(result, "AWR-CHAIN-003")


def test_chain_004_a_diamond_is_not_a_cycle(key_a):
    root = make_receipt(key_a, document_id="urn:uuid:diamond-root")
    left = sign(
        build_unsecured(
            key_a,
            document_id="urn:uuid:diamond-left",
            subject=work_receipt_subject(parents=[document_reference(root)]),
        ),
        key_a,
    )
    right = sign(
        build_unsecured(
            key_a,
            document_id="urn:uuid:diamond-right",
            subject=work_receipt_subject(parents=[document_reference(root)]),
        ),
        key_a,
    )
    top = sign(
        build_unsecured(
            key_a,
            document_id="urn:uuid:diamond-top",
            subject=work_receipt_subject(
                parents=[document_reference(left), document_reference(right)]
            ),
        ),
        key_a,
    )
    result = verify_document(top, now=NOW, supporting=[left, right, root])
    assert "AWR-CHAIN-004" not in [r["code"] for r in result["reasons"]]
    assert result["chain"] == {"resolved": 4, "unresolved": 0}


# ---------------------------------------------------------------------------
# AWR-CHAIN-005 -- depth and node limits
# ---------------------------------------------------------------------------


def test_chain_005_default_depth_limit(key_a):
    documents = linear_chain(key_a, DEFAULT_MAX_DEPTH + 6)
    result = verify_document(documents[-1], now=NOW, supporting=documents[:-1])
    assert_error(result, "AWR-CHAIN-005")
    assert "depth limit of 64" in [
        r["detail"] for r in result["reasons"] if r["code"] == "AWR-CHAIN-005"
    ][0]


def test_chain_005_a_chain_at_the_depth_limit_is_accepted(key_a):
    documents = linear_chain(key_a, DEFAULT_MAX_DEPTH + 1)
    result = verify_document(documents[-1], now=NOW, supporting=documents[:-1])
    assert result["valid"] is True, result
    assert result["chain"]["resolved"] == DEFAULT_MAX_DEPTH


def test_chain_005_node_limit_is_configurable(key_a):
    documents = linear_chain(key_a, 6)
    result = verify_document(
        documents[-1], now=NOW, supporting=documents[:-1], max_nodes=3
    )
    assert_error(result, "AWR-CHAIN-005")
    assert "node limit of 3" in [
        r["detail"] for r in result["reasons"] if r["code"] == "AWR-CHAIN-005"
    ][0]


def test_chain_005_depth_limit_is_configurable(key_a):
    documents = linear_chain(key_a, 6)
    result = verify_document(
        documents[-1], now=NOW, supporting=documents[:-1], max_depth=2
    )
    assert_error(result, "AWR-CHAIN-005")


# ---------------------------------------------------------------------------
# AWR-CHAIN-006 -- one id, two digests
# ---------------------------------------------------------------------------


def test_chain_006_conflicting_digests_for_one_parent_id(key_a):
    document = sign(
        build_unsecured(
            key_a,
            subject=work_receipt_subject(
                parents=[
                    {"id": "urn:uuid:parent-x", "digestSRI": sri_of(b"one")},
                    {"id": "urn:uuid:parent-x", "digestSRI": sri_of(b"two")},
                ]
            ),
        ),
        key_a,
    )
    assert_error(verify_document(document, now=NOW), "AWR-CHAIN-006")


def test_chain_006_across_two_hops(key_a):
    shared = make_receipt(key_a, document_id="urn:uuid:shared-parent")
    other = sign(
        build_unsecured(
            key_a,
            document_id="urn:uuid:middle",
            subject=work_receipt_subject(
                parents=[{"id": "urn:uuid:shared-parent", "digestSRI": sri_of(b"forged")}]
            ),
        ),
        key_a,
    )
    top = sign(
        build_unsecured(
            key_a,
            document_id="urn:uuid:top",
            subject=work_receipt_subject(
                parents=[document_reference(other), document_reference(shared)]
            ),
        ),
        key_a,
    )
    result = verify_document(top, now=NOW, supporting=[other, shared])
    assert_error(result, "AWR-CHAIN-006")


def test_the_same_parent_referenced_twice_identically_is_not_a_conflict(key_a):
    parent = make_receipt(key_a, document_id="urn:uuid:parent-same")
    reference = document_reference(parent)
    document = sign(
        build_unsecured(
            key_a,
            subject=work_receipt_subject(
                parents=[dict(reference, role="input"), dict(reference, role="tool")]
            ),
        ),
        key_a,
    )
    result = verify_document(document, now=NOW, supporting=[parent])
    assert result["valid"] is True, result


# ---------------------------------------------------------------------------
# AWR-CHAIN-007 -- output/input binding is a warning
# ---------------------------------------------------------------------------


def test_chain_007_parent_output_differs_from_child_input(key_a):
    parent = make_receipt(
        key_a, subject=work_receipt_subject(outputDigest=sri_of(b"parent output"))
    )
    child = sign(
        build_unsecured(
            key_a,
            subject=work_receipt_subject(
                inputDigest=sri_of(b"something else"),
                parents=[document_reference(parent)],
            ),
        ),
        key_a,
    )
    result = verify_document(child, now=NOW, supporting=[parent])
    assert_warning(result, "AWR-CHAIN-007")
    # A legitimate hop often transforms its input, so this must not invalidate.
    assert result["valid"] is True


def test_chain_007_is_silent_when_the_digests_agree(key_a):
    parent, child = linear_chain(key_a, 2)
    result = verify_document(child, now=NOW, supporting=[parent])
    assert "AWR-CHAIN-007" not in [w["code"] for w in result["warnings"]]


# ---------------------------------------------------------------------------
# section 8.2 / 13.5 -- no network
# ---------------------------------------------------------------------------


def test_the_package_imports_nothing_that_could_dereference_anything():
    """Section 13.5: a verifier MUST NOT fetch contexts, parents, evidence or schemas."""
    import awr

    package_dir = os.path.dirname(os.path.abspath(awr.__file__))
    forbidden = (
        "import socket",
        "import urllib",
        "import requests",
        "import http.client",
        "from urllib",
        "from http",
        "httpx",
        "aiohttp",
    )
    for name in sorted(os.listdir(package_dir)):
        if not name.endswith(".py"):
            continue
        with open(os.path.join(package_dir, name), "r", encoding="utf-8") as handle:
            source = handle.read()
        for needle in forbidden:
            assert needle not in source, "%s mentions %r" % (name, needle)
