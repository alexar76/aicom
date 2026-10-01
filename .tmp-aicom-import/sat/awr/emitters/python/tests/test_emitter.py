"""The emitter must produce documents the reference verifier accepts, and nothing else.

Every assertion here goes through `awr.verify_document` rather than inspecting fields by
hand: the emitter's contract is "the result verifies", not "the dict looks right".
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from awr import SigningKey, verify_document
from awr_emitter import (
    digest_payload,
    emit_receipt,
    generate_key,
    jcs_payload,
    receipt_reference,
)

# RFC 8032 section 7.1 test seed — published, and never to be used for anything real.
SEED = bytes.fromhex("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60")
NOW = "2026-08-01T10:15:30Z"
FIXED = dict(
    document_id="urn:uuid:8f14e45f-ea1c-4f38-9b8a-1c2d3e4f5a6b",
    valid_from=NOW,
    created=NOW,
)


@pytest.fixture()
def key() -> SigningKey:
    return SigningKey.from_seed(SEED)


def assert_valid(document, **kwargs):
    result = verify_document(document, now=NOW, **kwargs)
    assert result["valid"] is True, result["reasons"]
    return result


def test_the_smallest_receipt_verifies(key):
    doc = emit_receipt(key=key, model_id="m@v", input_payload=b"in", output_payload=b"out", **FIXED)
    result = assert_valid(doc)
    assert result["documentType"] == "WorkReceipt"
    assert result["verifiedProof"] == 0


def test_it_omits_every_optional_field_it_was_not_given(key):
    """A receipt should not carry a field the caller never supplied.

    An emitter that helpfully fills in `capability` or a zero `latencyMs` is putting the
    issuer's name on a claim the issuer did not make. `completedAt` is the exception: §3.3
    REQUIRES it, so it is always present and defaults to the document's own moment.
    """
    doc = emit_receipt(key=key, model_id="m@v", input_payload=b"in", output_payload=b"out", **FIXED)
    subject = doc["credentialSubject"]
    assert set(subject) == {"work", "inputDigest", "outputDigest"}
    assert set(subject["work"]) == {"modelId", "status", "completedAt"}
    assert subject["work"]["completedAt"] == NOW
    assert "name" not in doc["issuer"]


def test_the_issuer_is_the_key(key):
    doc = emit_receipt(key=key, model_id="m@v", input_payload=b"", output_payload=b"", **FIXED)
    assert doc["issuer"]["id"] == key.did
    assert doc["proof"]["verificationMethod"].startswith(key.did + "#")


def test_digest_is_over_exactly_the_bytes_given(key):
    """The documented rule, asserted: no normalization, no trailing newline, no BOM."""
    assert digest_payload("hola") == digest_payload(b"hola")
    assert digest_payload("hola") != digest_payload("hola\n")
    # NFC and NFD spellings of the same text are different bytes and must stay different.
    assert digest_payload("é") != digest_payload("é")


def test_jcs_payload_makes_a_json_digest_reproducible(key):
    """Two orderings of the same object must digest the same; that is the whole point."""
    a = jcs_payload({"b": 1, "a": [1, 2]})
    b = jcs_payload({"a": [1, 2], "b": 1})
    assert a == b
    assert digest_payload(a) == digest_payload(b)
    # …and it is genuinely different from a naive json.dumps of the same object.
    assert digest_payload(a) != digest_payload(json.dumps({"b": 1, "a": [1, 2]}))


def test_a_failed_run_still_gets_a_receipt(key):
    """§3.3: an unverifiable failure is the case a dispute most often turns on."""
    doc = emit_receipt(
        key=key, model_id="m@v", input_payload=b"in", output_payload=b"",
        status="failed", **FIXED,
    )
    assert_valid(doc)
    assert doc["credentialSubject"]["work"]["status"] == "failed"


def test_price_must_be_a_decimal_string(key):
    """§4.3 forbids non-integer JSON numbers; the reference rejects it at issue time."""
    with pytest.raises(Exception):
        emit_receipt(
            key=key, model_id="m@v", input_payload=b"i", output_payload=b"o",
            price={"currency": "USD", "amount": 0.15}, **FIXED,
        )
    ok = emit_receipt(
        key=key, model_id="m@v", input_payload=b"i", output_payload=b"o",
        price={"currency": "USD", "amount": "0.15"}, **FIXED,
    )
    assert_valid(ok)


def test_latency_must_be_a_non_negative_integer(key):
    for bad in (-1, 1.5, "2340"):
        with pytest.raises(ValueError):
            emit_receipt(
                key=key, model_id="m@v", input_payload=b"i", output_payload=b"o",
                latency_ms=bad, **FIXED,
            )


def test_an_unknown_status_is_refused(key):
    with pytest.raises(ValueError):
        emit_receipt(
            key=key, model_id="m@v", input_payload=b"i", output_payload=b"o",
            status="mostly-fine", **FIXED,
        )


def test_a_chain_edge_commits_to_the_parent_bytes(key):
    parent = emit_receipt(key=key, model_id="retrieve@v", input_payload=b"q", output_payload=b"docs", **FIXED)
    ref = receipt_reference(parent)
    child = emit_receipt(
        key=key, model_id="answer@v", input_payload=b"docs", output_payload=b"answer",
        parents=[dict(ref, role="retrieval")],
        document_id="urn:uuid:11111111-2222-3333-4444-555555555555",
        valid_from=NOW, created=NOW,
    )
    result = assert_valid(child, supporting=[parent])
    assert result["chain"]["resolved"] == 1

    tampered = json.loads(json.dumps(parent))
    tampered["credentialSubject"]["work"]["modelId"] = "something-else@v"
    broken = verify_document(child, now=NOW, supporting=[tampered])
    assert any(r["code"] == "AWR-CHAIN-003" for r in broken["reasons"]), broken


def test_two_keys_produce_two_issuers():
    a, b = generate_key(), generate_key()
    assert a.did != b.did


def test_the_emitter_reimplements_nothing():
    """Structural: the glue must not grow its own canonicalization or proof.

    This is the failure the whole format exists because of — two copies of a
    canonicalizer that disagree. If a future change adds one here, this fails.
    """
    source = (Path(__file__).resolve().parent.parent / "awr_emitter" / "__init__.py").read_text()
    for forbidden in ("def canonicalize", "sort_keys", "ed25519", "def sign", "b58", "0xed"):
        assert forbidden not in source, "the emitter must delegate, not reimplement: " + forbidden


def test_the_typescript_emitter_agrees_byte_for_byte(key, tmp_path):
    """Cross-language equivalence, run for real rather than asserted.

    Same key, same inputs, same fixed timestamps: the two emitters must produce the same
    bytes. They are independent codebases in different languages, so this is the strongest
    statement available here that the format is implementable rather than merely described.
    """
    ts = Path(__file__).resolve().parents[3] / "emitters" / "typescript"
    if not (ts / "awr-emit.mjs").exists():  # pragma: no cover
        pytest.skip("typescript emitter not present")

    script = """
    import {keyFromSeed, emitReceipt, jcsPayload} from '%s';
    const key = keyFromSeed(Buffer.from('%s','hex'));
    console.log(JSON.stringify(emitReceipt({
      key, modelId:'claude-opus-5@anthropic',
      inputPayload: jcsPayload({prompt:'summarise', n:3}),
      outputPayload:'hola',
      completedAt:'%s', latencyMs:2340,
      documentId:'%s', validFrom:'%s', created:'%s',
    }), null, 1));
    """ % (ts / "awr-emit.mjs", SEED.hex(), NOW, FIXED["document_id"], NOW, NOW)
    proc = subprocess.run(
        [_node(), "--input-type=module", "-e", script], capture_output=True, text=True
    )
    assert proc.returncode == 0, proc.stderr

    mine = emit_receipt(
        key=key, model_id="claude-opus-5@anthropic",
        input_payload=jcs_payload({"prompt": "summarise", "n": 3}),
        output_payload=b"hola",
        completed_at=NOW, latency_ms=2340, **FIXED,
    )
    assert json.dumps(mine, indent=1, ensure_ascii=False) + "\n" == proc.stdout
    assert_valid(json.loads(proc.stdout))


def _node() -> str:
    import shutil

    node = shutil.which("node")
    if node is None:  # pragma: no cover
        pytest.skip("node is not on PATH")
    return node


# ── timestamp derivation (§3.3, and cross-language agreement) ────────────────
#
# The mirror of the three tests at the end of the TypeScript suite. That emitter once answered
# all three timestamp questions from a single `created || validFrom || now`, which made it
# disagree with this one on partial input; these assertions pin the precedence in both languages
# so the next divergence fails a test instead of shipping. A past sentinel stands in for a fixed
# clock: the real clock can never equal it.

PAST = "2020-01-02T03:04:05Z"


def test_valid_from_is_never_derived_from_created(key):
    """A proof timestamp says when the signature was made; it is not a validity start."""
    doc = emit_receipt(
        key=key, model_id="m@1", input_payload=b"in", output_payload=b"out", created=PAST
    )
    assert doc["proof"]["created"] == PAST
    assert doc["validFrom"] != PAST


def test_proof_created_falls_back_to_valid_from(key):
    """The reference signs with ``created or document["validFrom"]`` -- pinned here so the
    TypeScript emitter cannot drift from it. For a freshly issued document validFrom *is* the
    issuance moment, so the two agree without a second clock reading."""
    doc = emit_receipt(
        key=key, model_id="m@1", input_payload=b"in", output_payload=b"out", valid_from=PAST
    )
    assert doc["validFrom"] == PAST
    assert doc["proof"]["created"] == PAST


def test_proof_created_is_never_taken_from_completed_at(key):
    """Work finishing is not the same event as signing."""
    doc = emit_receipt(
        key=key, model_id="m@1", input_payload=b"in", output_payload=b"out", completed_at=PAST
    )
    assert doc["credentialSubject"]["work"]["completedAt"] == PAST
    assert doc["proof"]["created"] != PAST
    assert doc["validFrom"] != PAST


def test_completed_at_precedence_is_completed_created_valid_now(key):
    c, v, d = "2021-01-01T00:00:00Z", "2022-01-01T00:00:00Z", "2023-01-01T00:00:00Z"
    base = dict(key=key, model_id="m", input_payload=b"i", output_payload=b"o")
    assert emit_receipt(completed_at=d, created=c, valid_from=v, **base)["credentialSubject"]["work"]["completedAt"] == d
    assert emit_receipt(created=c, valid_from=v, **base)["credentialSubject"]["work"]["completedAt"] == c
    assert emit_receipt(valid_from=v, **base)["credentialSubject"]["work"]["completedAt"] == v
    assert emit_receipt(**base)["credentialSubject"]["work"]["completedAt"]
