"""Proof that the adoption counter counts what it claims to count.

Every document here is issued with the AWR reference implementation using freshly
generated Ed25519 keys, so the signatures are real and ``verify_document`` does real work.
The four properties under test are the ones that make the headline number mean
"documents issued by a key we do not control":

1. documents from our own keys do not count;
2. documents from foreign keys do;
3. invalid documents are excluded from the adoption count and reported separately;
4. duplicate document ids count once.

Run with::

    python3 -m pytest awr/adoption/metrics/test_adoption_metric.py -q
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_REFERENCE = os.path.normpath(os.path.join(_HERE, "..", "..", "reference", "python"))

for _path in (_HERE, _REFERENCE):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import adoption_metric as am  # noqa: E402

awr = pytest.importorskip("awr", reason="the AWR reference implementation is required")


# ---------------------------------------------------------------------------
# fixtures: real keys, real signatures
# ---------------------------------------------------------------------------

EMPTY = awr.EMPTY_PAYLOAD_SRI


def make_key():
    return awr.SigningKey.generate()


def receipt(key, *, when="2026-07-15T10:00:00Z", model="claude-sonnet-5@anthropic",
            document_id=None, name=None, status="succeeded"):
    return awr.issue_work_receipt(
        {
            "work": {
                "modelId": model,
                "startedAt": when,
                "completedAt": when,
                "status": status,
            },
            "inputDigest": EMPTY,
            "outputDigest": EMPTY,
        },
        key,
        document_id=document_id,
        valid_from=when,
        created=when,
        issuer_name=name,
    )


def verdict(key, target_receipt, *, when="2026-07-15T11:00:00Z", stake=None):
    subject = {
        "verifiedWork": awr.document_reference(target_receipt),
        "verdict": "pass",
        "method": {"id": "urn:test:method:v1"},
    }
    if stake is not None:
        subject["stake"] = stake
    return awr.issue_verification_verdict(
        subject, key, valid_from=when, created=when
    )


@pytest.fixture
def verifier():
    built = am.build_verifier(require_reference=True)
    assert built.checks_signatures, "these tests must exercise real verification"
    return built


def loaded(*documents, source="memory"):
    """Wrap parsed documents the way the reader would."""
    items = []
    for index, document in enumerate(documents):
        items.append(
            am.LoadedDocument(source, "%s#%d" % (source, index), document)
        )
    return items


def run(verifier, documents, own_keys, **kwargs):
    kwargs.setdefault("now", "2026-07-31T00:00:00Z")
    return am.compute_report(
        loaded(*documents), [], set(own_keys), verifier, **kwargs
    )


def foreign_dids(report):
    return {entry["did"] for entry in report["foreignIssuers"]}


# ---------------------------------------------------------------------------
# 1. our own keys do not count
# ---------------------------------------------------------------------------


def test_documents_from_our_own_keys_do_not_count(verifier):
    ours = make_key()
    docs = [receipt(ours, when="2026-07-0%dT10:00:00Z" % n) for n in range(1, 6)]

    report = run(verifier, docs, {ours.did})

    assert report["headline"]["value"] == 0
    assert report["foreignIssuers"] == []
    assert report["issuers"]["distinctOwn"] == 1
    assert report["issuers"]["distinct"] == 1
    # the documents are perfectly valid; they are simply not adoption
    assert report["context"]["validDocuments"] == 5
    assert report["context"]["ownDocuments"] == 5
    assert report["context"]["foreignDocuments"] == 0
    assert report["invalid"]["count"] == 0


def test_the_same_documents_count_when_the_key_is_not_declared(verifier):
    """The one failure mode of the metric, made visible: an undeclared DID inflates."""
    ours = make_key()
    docs = [receipt(ours)]

    declared = run(verifier, docs, {ours.did})
    forgotten = run(verifier, docs, set())

    assert declared["headline"]["value"] == 0
    assert forgotten["headline"]["value"] == 1
    assert foreign_dids(forgotten) == {ours.did}


def test_own_key_matching_is_by_did_not_by_issuer_name(verifier):
    """issuer.name carries no trust weight (SPEC.md 3.1) and must not classify."""
    stranger = make_key()
    ours = make_key()
    impostor = receipt(stranger, name="example-hub")

    report = run(verifier, [impostor, receipt(ours, name="totally-not-us")], {ours.did})

    assert report["headline"]["value"] == 1
    assert foreign_dids(report) == {stranger.did}
    # the name is reported for recognition only
    assert report["foreignIssuers"][0]["names"] == ["example-hub"]


def test_own_key_matching_is_case_sensitive(verifier):
    ours = make_key()
    report = run(verifier, [receipt(ours)], {ours.did.lower()})
    assert report["headline"]["value"] == 1, (
        "a lowercased did:key must not match: base58btc is case-sensitive, and a "
        "silent match here would hide one of our own keys"
    )


# ---------------------------------------------------------------------------
# 2. foreign keys count, once per issuer
# ---------------------------------------------------------------------------


def test_documents_from_foreign_keys_count(verifier):
    ours = make_key()
    a, b, c = make_key(), make_key(), make_key()
    docs = [receipt(ours), receipt(a), receipt(b), receipt(c)]

    report = run(verifier, docs, {ours.did})

    assert report["headline"]["value"] == 3
    assert foreign_dids(report) == {a.did, b.did, c.did}
    assert report["issuers"]["distinct"] == 4
    assert report["context"]["foreignDocuments"] == 3


def test_one_loud_adopter_is_one_adopter(verifier):
    """Volume is not adoption: 250 receipts from one key is a value of 1."""
    ours = make_key()
    loud = make_key()
    docs = [receipt(loud, document_id="urn:uuid:loud-%04d" % n) for n in range(250)]

    report = run(verifier, docs, {ours.did})

    assert report["headline"]["value"] == 1
    assert report["foreignIssuers"][0]["documents"] == 250
    # and the document count is filed under "not the metric"
    assert "NOT THE METRIC" in report["context"]["note"]


def test_first_and_last_seen_come_from_signed_validfrom(verifier):
    ours = make_key()
    stranger = make_key()
    docs = [
        receipt(stranger, when="2026-07-20T09:00:00Z"),
        receipt(stranger, when="2026-07-02T08:30:00Z"),
        receipt(stranger, when="2026-07-11T23:59:59Z"),
    ]

    report = run(verifier, docs, {ours.did})
    entry = report["foreignIssuers"][0]

    assert entry["documents"] == 3
    assert entry["firstSeen"] == "2026-07-02T08:30:00Z"
    assert entry["lastSeen"] == "2026-07-20T09:00:00Z"
    assert report["instrument"]["timestampField"] == "validFrom"


def test_counts_by_document_type_and_profile(verifier):
    ours = make_key()
    author = make_key()
    juror_one = make_key()
    juror_two = make_key()

    plain = receipt(author, document_id="urn:uuid:plain")
    reviewed = receipt(author, document_id="urn:uuid:reviewed")
    verdict_one = verdict(juror_one, reviewed)
    blame = awr.issue_blame_attestation(
        {
            "chain": awr.document_reference(plain),
            "blamedWork": awr.document_reference(plain),
            "failureClass": "wrong-output",
            "method": {"id": "urn:test:method:blame"},
        },
        juror_two,
        valid_from="2026-07-16T10:00:00Z",
        created="2026-07-16T10:00:00Z",
    )

    report = run(verifier, [plain, reviewed, verdict_one, blame], {ours.did})

    assert report["headline"]["value"] == 3  # author, juror_one, juror_two
    assert report["context"]["byDocumentType"]["foreign"] == {
        "WorkReceipt": 2,
        "VerificationVerdict": 1,
        "BlameAttestation": 1,
    }
    profiles = report["context"]["byProfile"]["foreign"]
    # The reviewed receipt reaches L1: the verdict is in the supporting set and its issuer
    # differs from the receipt's (SPEC.md 10.2). Everything else valid is L0, which is
    # what "valid without a profile" means (SPEC.md 10.4).
    assert profiles == {"L0": 3, "L1": 1}
    # profile has no bearing on the metric: all four issuers of these documents that are
    # not ours are adopters, at whatever level
    assert report["context"]["foreignDocuments"] == 4


def test_profile_l0_is_enough_to_be_an_adopter(verifier):
    """L0 is the adoption floor (SPEC.md 10.1); requiring L1 would measure something else."""
    ours = make_key()
    stranger = make_key()
    report = run(verifier, [receipt(stranger)], {ours.did})
    assert report["headline"]["value"] == 1
    assert report["foreignIssuers"][0]["byProfile"] == {"L0": 1}


# ---------------------------------------------------------------------------
# 3. invalid documents: excluded from adoption, reported separately
# ---------------------------------------------------------------------------


def test_tampered_document_is_excluded_and_reported(verifier):
    ours = make_key()
    stranger = make_key()
    good = receipt(stranger, document_id="urn:uuid:good")

    tampered = copy.deepcopy(receipt(stranger, document_id="urn:uuid:tampered"))
    tampered["credentialSubject"]["work"]["modelId"] = "a-model-nobody-signed-for"

    report = run(verifier, [good, tampered], {ours.did})

    assert report["headline"]["value"] == 1
    assert report["foreignIssuers"][0]["documents"] == 1, "the tampered doc must not count"
    assert report["invalid"]["failedVerification"] == 1
    assert report["invalid"]["byReasonCode"].get("AWR-PROOF-006") == 1
    assert report["invalid"]["byIssuerClass"]["foreign"] == 1
    reported = report["invalid"]["documents"]
    assert len(reported) == 1
    assert reported[0]["id"] == "urn:uuid:tampered"
    assert reported[0]["issuer"] == stranger.did
    assert "AWR-PROOF-006" in reported[0]["errorCodes"]


def test_an_issuer_with_only_invalid_documents_is_not_an_adopter(verifier):
    ours = make_key()
    stranger = make_key()
    broken = copy.deepcopy(receipt(stranger))
    broken["credentialSubject"]["outputDigest"] = "sha256-not-really-a-digest"

    report = run(verifier, [broken], {ours.did})

    assert report["headline"]["value"] == 0
    assert report["foreignIssuers"] == []
    assert report["invalid"]["failedVerification"] == 1
    # not dropped: the lead is still visible, attributed, and diagnosable
    assert report["invalid"]["documents"][0]["issuer"] == stranger.did
    assert report["invalid"]["documents"][0]["errorCodes"]


def test_document_with_a_stripped_proof_is_invalid(verifier):
    ours = make_key()
    stranger = make_key()
    unsigned = copy.deepcopy(receipt(stranger))
    unsigned.pop("proof")

    report = run(verifier, [unsigned], {ours.did})

    assert report["headline"]["value"] == 0
    assert report["invalid"]["failedVerification"] == 1
    assert "AWR-PROOF-001" in report["invalid"]["documents"][0]["errorCodes"]


def test_invalid_documents_are_never_silently_dropped(verifier):
    ours = make_key()
    strangers = [make_key() for _ in range(3)]
    docs = []
    for index, key in enumerate(strangers):
        bad = copy.deepcopy(receipt(key, document_id="urn:uuid:bad-%d" % index))
        bad["credentialSubject"]["work"]["status"] = "not-a-status"
        docs.append(bad)

    report = run(verifier, docs, {ours.did})

    assert report["headline"]["value"] == 0
    assert report["invalid"]["count"] == 3
    assert len(report["invalid"]["documents"]) == 3
    read = report["corpus"]["documentsRead"]
    accounted = (
        report["context"]["validDocuments"]
        + report["invalid"]["count"]
        + report["corpus"]["duplicateIdsCollapsed"]
    )
    assert read == accounted, "every document read must land in exactly one bucket"


def test_valid_awr1_legacy_document_is_not_awr2_adoption(verifier):
    """A valid AWR/1 document is a different format (SPEC.md 12)."""
    stranger_seed = hashlib.sha256(b"legacy-issuer").digest()
    key = awr.SigningKey.from_seed(stranger_seed)
    subject = {
        "work": {"modelId": "legacy-model", "completedAt": "2026-01-01T00:00:00Z"},
    }
    legacy = {
        "@context": ["https://www.w3.org/2018/credentials/v1"],
        "id": "urn:uuid:legacy-1",
        "type": ["VerifiableCredential", "WorkReceipt"],
        "issuer": {"id": key.did},
        "issuanceDate": "2026-01-01T00:00:00Z",
        "awrVersion": "1.0.0",
        "credentialSubject": subject,
        "proof": {
            "type": awr.LEGACY_PROOF_TYPE,
            "created": "2026-01-01T00:00:00Z",
            "proofPurpose": "assertionMethod",
            "verificationMethod": key.verification_method,
            "proofValue": "",
        },
    }
    import base64

    from awr.legacy import DIALECT_INTEGER_PRESERVING, legacy_canonical_form

    # AWR/1 signed a pipe-delimited rendering of credentialSubject only (SPEC.md 12).
    signed = legacy_canonical_form(subject, DIALECT_INTEGER_PRESERVING)
    legacy["proof"]["proofValue"] = base64.b64encode(key.sign(signed)).decode("ascii")

    probe = awr.verify_document(legacy, now="2026-07-31T00:00:00Z")
    if not probe["valid"]:
        pytest.skip(
            "could not construct a valid AWR/1 document with this reference "
            "implementation: %s" % (probe["reasons"],)
        )

    report = run(verifier, [legacy], set())
    assert report["headline"]["value"] == 0
    assert report["invalid"]["validAwr1NotCountedAsAwr2"] == 1

    counted = run(verifier, [legacy], set(), include_legacy=True)
    assert counted["headline"]["value"] == 1
    assert counted["instrument"]["legacyAwr1Counted"] is True


# ---------------------------------------------------------------------------
# 4. duplicate document ids count once
# ---------------------------------------------------------------------------


def test_duplicate_document_id_counts_once(verifier):
    ours = make_key()
    stranger = make_key()
    one = receipt(stranger, document_id="urn:uuid:duplicated")

    report = run(verifier, [one, copy.deepcopy(one), copy.deepcopy(one)], {ours.did})

    assert report["headline"]["value"] == 1
    assert report["corpus"]["documentsRead"] == 3
    assert report["corpus"]["duplicateIdsCollapsed"] == 2
    assert report["context"]["validDocuments"] == 1
    assert report["foreignIssuers"][0]["documents"] == 1
    assert report["idCollisions"] == []


def test_same_id_different_bytes_counts_once_and_is_flagged(verifier):
    ours = make_key()
    first_key = make_key()
    second_key = make_key()
    first = receipt(first_key, document_id="urn:uuid:collision", when="2026-07-01T00:00:00Z")
    second = receipt(second_key, document_id="urn:uuid:collision", when="2026-07-02T00:00:00Z")

    report = run(verifier, [first, second], {ours.did})

    assert report["headline"]["value"] == 1, "one id, one document, one issuer"
    assert foreign_dids(report) == {first_key.did}
    assert len(report["idCollisions"]) == 1
    collision = report["idCollisions"][0]
    assert collision["id"] == "urn:uuid:collision"
    assert collision["first"]["issuer"] == first_key.did
    assert collision["second"]["issuer"] == second_key.did
    assert any("differing bytes" in w for w in report["warnings"])


def test_duplicates_across_two_files_count_once(tmp_path, verifier):
    stranger = make_key()
    document = receipt(stranger, document_id="urn:uuid:shared")
    for name in ("a.json", "b.json"):
        (tmp_path / name).write_text(json.dumps(document), encoding="utf-8")

    documents, errors, paths = am.read_all([str(tmp_path)], verifier)
    assert errors == []
    assert len(paths) == 2
    report = am.compute_report(
        documents, errors, set(), verifier, now="2026-07-31T00:00:00Z"
    )

    assert report["headline"]["value"] == 1
    assert report["corpus"]["documentsRead"] == 2
    assert report["corpus"]["duplicateIdsCollapsed"] == 1


# ---------------------------------------------------------------------------
# the own-keys file
# ---------------------------------------------------------------------------


def test_own_keys_parsing():
    ours = make_key()
    text = "\n".join(
        [
            "# a comment line",
            "",
            "%s   # hub / prod" % (ours.did,),
            "%s#%s" % (ours.did, ours.did.split(":")[-1]),  # verificationMethod form
            "   ",
            "not-a-did",
        ]
    )
    dids, problems = am.parse_own_keys(text)

    assert dids == {ours.did}, "the verificationMethod form must reduce to its DID"
    assert any("not a did:key" in p for p in problems)
    assert any("more than once" in p for p in problems)


def test_missing_own_keys_file_warns_loudly(monkeypatch, tmp_path):
    monkeypatch.delenv(am.OWN_KEYS_ENV_VAR, raising=False)
    monkeypatch.setattr(am, "_HERE", str(tmp_path))
    own_keys, info = am.load_own_keys(None)
    assert own_keys == set()
    assert info["source"] is None
    assert any("INFLATES" in w for w in info["warnings"])


def test_empty_own_keys_file_warns(tmp_path):
    path = tmp_path / "own-keys.txt"
    path.write_text("# nothing declared yet\n", encoding="utf-8")
    own_keys, info = am.load_own_keys(str(path))
    assert own_keys == set()
    assert any("INFLATES" in w for w in info["warnings"])


def test_shipped_example_own_keys_file_declares_no_real_dids():
    path = os.path.join(_HERE, "own-keys.example.txt")
    with open(path, "r", encoding="utf-8") as handle:
        text = handle.read()
    dids, _ = am.parse_own_keys(text)
    assert dids == set(), (
        "own-keys.example.txt must be entirely comments: an example DID that parses "
        "would be copied into own-keys.txt and would deflate the metric"
    )


# ---------------------------------------------------------------------------
# the metric cannot be quietly redefined
# ---------------------------------------------------------------------------


PINNED_DEFINITION = (
    "The number of distinct did:key issuer identifiers that appear in valid AWR/2 "
    "documents and are not listed in this project's own-keys file. A document counts "
    "once per document id; an issuer counts once regardless of how many documents it "
    "issued. Documents that fail verification never count."
)
PINNED_DIGEST = hashlib.sha256(PINNED_DEFINITION.encode("utf-8")).hexdigest()


def test_metric_definition_is_pinned():
    assert am.METRIC_ID == "awr.adoption.distinct-foreign-issuers"
    assert am.METRIC_DEFINITION == PINNED_DEFINITION
    assert am.METRIC_DEFINITION_DIGEST == PINNED_DIGEST, (
        "the metric definition changed. That is allowed, but it must be a deliberate, "
        "reviewed edit to this test -- not a drift."
    )


def test_headline_carries_one_number_and_its_definition(verifier):
    stranger = make_key()
    report = run(verifier, [receipt(stranger)], set())
    head = report["headline"]
    assert head["metric"] == am.METRIC_ID
    assert head["value"] == 1
    assert head["unit"] == "distinct foreign issuer DIDs"
    assert head["definitionDigestSHA256"] == PINNED_DIGEST
    assert head["signaturesVerified"] is True
    # volume must not be reachable from the headline
    assert set(head) == {
        "metric",
        "value",
        "unit",
        "definition",
        "definitionDigestSHA256",
        "signaturesVerified",
    }


def test_report_is_json_serialisable_and_human_renderable(verifier):
    ours = make_key()
    stranger = make_key()
    good = receipt(stranger)
    bad = copy.deepcopy(receipt(stranger))
    bad["credentialSubject"]["work"]["modelId"] = "tampered"
    report = run(verifier, [good, bad], {ours.did})

    blob = json.dumps(report)
    assert json.loads(blob)["headline"]["value"] == 1

    text = am.render_human(report)
    assert "THE NUMBER: 1 distinct foreign issuer DIDs" in text
    assert "NOT THE METRIC" in text
    assert stranger.did in text


# ---------------------------------------------------------------------------
# the degraded path must not look trustworthy
# ---------------------------------------------------------------------------


def test_structural_fallback_marks_itself_untrustworthy():
    stranger = make_key()
    fallback = am.StructuralVerifier()
    document = receipt(stranger)
    document["proof"]["proofValue"] = "z" + "1" * 87  # signature no longer valid

    report = am.compute_report(
        loaded(document), [], set(), fallback, now="2026-07-31T00:00:00Z"
    )

    assert report["headline"]["value"] == 1  # structurally it looks like an adopter
    assert report["headline"]["signaturesVerified"] is False
    assert any("NO SIGNATURES WERE VERIFIED" in w for w in report["warnings"])
    assert "NO SIGNATURES WERE VERIFIED" in am.render_human(report)


def test_reference_verifier_rejects_what_the_fallback_accepts(verifier):
    """The same document: real verification says no, structural says yes."""
    stranger = make_key()
    document = receipt(stranger)
    document["proof"]["proofValue"] = "z" + "1" * 87

    strict = am.compute_report(
        loaded(document), [], set(), verifier, now="2026-07-31T00:00:00Z"
    )
    loose = am.compute_report(
        loaded(document), [], set(), am.StructuralVerifier(), now="2026-07-31T00:00:00Z"
    )

    assert strict["headline"]["value"] == 0
    assert loose["headline"]["value"] == 1


# ---------------------------------------------------------------------------
# reading: bundles, arrays, jsonl, junk
# ---------------------------------------------------------------------------


def test_reads_documents_bundles_arrays_and_jsonl(tmp_path, verifier):
    a, b, c, d = make_key(), make_key(), make_key(), make_key()
    single = receipt(a, document_id="urn:uuid:single")
    bundled = awr.make_bundle([receipt(b, document_id="urn:uuid:bundled")])
    array = [receipt(c, document_id="urn:uuid:arrayed")]
    lines = [receipt(d, document_id="urn:uuid:lined")]

    (tmp_path / "one.awr.json").write_text(json.dumps(single), encoding="utf-8")
    (tmp_path / "bundle.awrb.json").write_text(json.dumps(bundled), encoding="utf-8")
    (tmp_path / "array.json").write_text(json.dumps(array), encoding="utf-8")
    (tmp_path / "batch.jsonl").write_text(
        "\n".join(json.dumps(x) for x in lines) + "\n", encoding="utf-8"
    )

    documents, errors, paths = am.read_all([str(tmp_path)], verifier)
    assert errors == []
    assert len(paths) == 4
    report = am.compute_report(
        documents, errors, set(), verifier, files_scanned=len(paths),
        now="2026-07-31T00:00:00Z",
    )
    assert report["headline"]["value"] == 4
    assert foreign_dids(report) == {a.did, b.did, c.did, d.did}


def test_unparseable_file_is_reported_and_yields_no_adopter(tmp_path, verifier):
    (tmp_path / "junk.json").write_text("{not json at all", encoding="utf-8")
    stranger = make_key()
    (tmp_path / "ok.json").write_text(
        json.dumps(receipt(stranger)), encoding="utf-8"
    )

    documents, errors, paths = am.read_all([str(tmp_path)], verifier)
    report = am.compute_report(
        documents, errors, set(), verifier, files_scanned=len(paths),
        now="2026-07-31T00:00:00Z",
    )

    assert report["headline"]["value"] == 1
    assert report["corpus"]["readErrorCount"] == 1
    assert "junk.json" in report["corpus"]["readErrors"][0]["source"]


def test_duplicate_property_name_rejects_the_file(tmp_path, verifier):
    """Strict section 4 parsing: json.loads would swallow this silently."""
    stranger = make_key()
    blob = json.dumps(receipt(stranger))
    poisoned = blob[:-1] + ',"awrVersion":"2.0.0"}'
    (tmp_path / "dup.json").write_text(poisoned, encoding="utf-8")

    documents, errors, _ = am.read_all([str(tmp_path)], verifier)

    assert documents == []
    assert len(errors) == 1
    assert errors[0]["code"] in ("AWR-CANON-004", "AWR-CANON-005")


def test_missing_input_path_is_reported(verifier):
    documents, errors, paths = am.read_all(["/nonexistent/corpus/path"], verifier)
    assert documents == []
    assert paths == []
    assert errors and "no such file" in errors[0]["error"]


def test_empty_corpus_reports_zero(tmp_path, verifier):
    documents, errors, paths = am.read_all([str(tmp_path)], verifier)
    report = am.compute_report(
        documents, errors, set(), verifier, files_scanned=len(paths),
        now="2026-07-31T00:00:00Z",
    )
    assert report["headline"]["value"] == 0
    assert "Adoption is zero" in am.render_human(report)


# ---------------------------------------------------------------------------
# the CLI
# ---------------------------------------------------------------------------


def test_cli_end_to_end(tmp_path):
    ours = make_key()
    stranger = make_key()
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "ours.json").write_text(json.dumps(receipt(ours)), encoding="utf-8")
    (corpus / "theirs.json").write_text(json.dumps(receipt(stranger)), encoding="utf-8")
    keys = tmp_path / "own-keys.txt"
    keys.write_text("%s  # ours\n" % (ours.did,), encoding="utf-8")

    proc = subprocess.run(
        [
            sys.executable,
            os.path.join(_HERE, "adoption_metric.py"),
            str(corpus),
            "--own-keys",
            str(keys),
            "--format",
            "json",
            "--now",
            "2026-07-31T00:00:00Z",
            "--require-reference",
        ],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    report = json.loads(proc.stdout)
    assert report["headline"]["value"] == 1
    assert report["foreignIssuers"][0]["did"] == stranger.did
    assert report["ownIssuers"][0]["did"] == ours.did


def test_cli_fail_under_exits_one(tmp_path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "ours.json").write_text(
        json.dumps(receipt(make_key())), encoding="utf-8"
    )
    proc = subprocess.run(
        [
            sys.executable,
            os.path.join(_HERE, "adoption_metric.py"),
            str(corpus),
            "--own-keys",
            os.devnull,
            "--format",
            "json",
            "--fail-under",
            "5",
        ],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1
    assert json.loads(proc.stdout)["headline"]["value"] == 1
    assert "below --fail-under 5" in proc.stderr


# ---------------------------------------------------------------------------
# the committed own-keys file: the metric's only integrity control
#
# Critique findings D14/D15. awr/adoption/mcp-trust-label/examples/generate.py IS an AWR/2
# issuer inside this repository, signing from the published seed bytes(range(32)). Before
# own-keys.txt was committed with that DID in it, the metric reported ONE adopter, and the
# adopter was us. These tests exist so that the file's integrity is enforced by a test
# instead of by discipline: delete the entry and the suite fails.
# ---------------------------------------------------------------------------

OWN_KEYS_PATH = os.path.join(_HERE, "own-keys.txt")
EXAMPLES_DIR = os.path.normpath(
    os.path.join(_HERE, "..", "mcp-trust-label", "examples")
)

#: The seed published in examples/generate.py. Derived here, never copied as a string, so
#: that the test fails if the generator's key ever changes.
GENERATOR_SEED = bytes(range(32))


def generator_key():
    return awr.SigningKey.from_seed(GENERATOR_SEED)


def committed_own_keys():
    with open(OWN_KEYS_PATH, "r", encoding="utf-8") as handle:
        return am.parse_own_keys(handle.read())


def demonstration_label(key, *, document_id="urn:uuid:mtl-demo-regression-0001"):
    """The shape the example generator issues: an MTL/1 label as a VerificationVerdict."""
    subject = {
        "verifiedWork": {
            "id": "urn:awr:mtl:1:subject:demo",
            "digestSRI": EMPTY,
        },
        "verdict": "pass",
        "method": {"id": "urn:awr:mtl:1:method:tool-def-pattern-scan"},
        "mcpTrustLabel": {
            "profile": "MTL/1",
            "observedAt": "2026-07-30T09:00:00Z",
            "reproducibility": "deterministic",
            "demonstration": {"isDemonstration": True},
        },
    }
    return awr.issue_verification_verdict(
        subject,
        key,
        document_id=document_id,
        valid_from="2026-07-30T09:15:00Z",
        created="2026-07-30T09:15:00Z",
        issuer_name="mtl-demo-scanner (DEMONSTRATION KEY)",
        extra_types=["MCPTrustLabel"],
        extra_context=["https://verify.modelmarket.dev/ns/awr/mtl/v1"],
    )


def test_own_keys_file_is_committed_and_parses_cleanly():
    """D15: an uncommitted own-keys file makes every quoted number unauditable."""
    assert os.path.isfile(OWN_KEYS_PATH), (
        "own-keys.txt must be committed with content. It holds only public DIDs, and a "
        "metric quoted without the own-keys file it was computed against cannot be audited."
    )
    dids, problems = committed_own_keys()
    assert problems == [], problems
    assert dids, "the committed own-keys file must declare at least one DID"


def test_the_example_generator_did_is_declared_as_ours():
    """D14, first half: the DID is derived by running the code, not copied from prose."""
    dids, _ = committed_own_keys()
    assert generator_key().did in dids, (
        "the MTL example generator signs with the published seed bytes(range(32)); its DID "
        "%s must be declared in own-keys.txt or the metric counts this repository as its "
        "own first adopter" % (generator_key().did,)
    )


def test_a_document_from_the_example_generator_is_not_a_foreign_adopter(verifier):
    """THE REGRESSION. Same bytes, two own-keys files, and the number must differ."""
    label = demonstration_label(generator_key())
    assert awr.verify_document(label, now="2026-07-31T00:00:00Z")["valid"]

    declared, _ = committed_own_keys()
    with_file = run(verifier, [label], declared)

    assert with_file["headline"]["value"] == 0, (
        "a document signed by the example generator's published key must count as zero "
        "adoption once own-keys.txt declares it"
    )
    assert with_file["foreignIssuers"] == []
    assert [entry["did"] for entry in with_file["ownIssuers"]] == [generator_key().did]
    # It is a perfectly valid document. It is simply not evidence of anything.
    assert with_file["context"]["validDocuments"] == 1
    assert with_file["invalid"]["count"] == 0


def test_the_generator_document_is_counted_when_its_did_is_missing(verifier):
    """The other half: if the entry disappears, the metric must go back to reporting 1."""
    label = demonstration_label(generator_key())
    declared, _ = committed_own_keys()
    without = {did for did in declared if did != generator_key().did}

    report = run(verifier, [label], without)

    assert report["headline"]["value"] == 1, (
        "with the generator DID removed from own-keys.txt the metric must count it as a "
        "foreign adopter -- that is the defect this file guards, and a test that passes "
        "either way would guard nothing"
    )
    assert foreign_dids(report) == {generator_key().did}


def test_the_shipped_example_labels_count_as_zero_adoption(verifier):
    """End to end over the real directory, with the real committed own-keys file."""
    if not os.path.isdir(EXAMPLES_DIR):  # pragma: no cover - the examples ship with it
        pytest.skip("the MTL examples directory is not present")
    documents, errors, paths = am.read_all([EXAMPLES_DIR], verifier)
    declared, _ = committed_own_keys()
    report = am.compute_report(
        documents, errors, declared, verifier,
        files_scanned=len(paths), now="2026-07-31T12:00:00Z",
    )

    assert report["headline"]["value"] == 0, (
        "the shipped MTL examples are signed by our own published demonstration key: %s"
        % (report["foreignIssuers"],)
    )
    assert report["context"]["validDocuments"] >= 4
    assert [entry["did"] for entry in report["ownIssuers"]] == [generator_key().did]

    # ...and the same corpus with an empty own-keys file is the bug the critic found.
    inflated = am.compute_report(
        documents, errors, set(), verifier,
        files_scanned=len(paths), now="2026-07-31T12:00:00Z",
    )
    assert inflated["headline"]["value"] == 1
    assert foreign_dids(inflated) == {generator_key().did}


# ---------------------------------------------------------------------------
# the demo corpus: the README transcript, enforced
#
# Critique finding D16. The "what a run looks like" transcript used to be computed over a
# corpus that did not ship, so nobody could check it. demo_corpus.py mints that corpus
# deterministically; these tests assert the exact numbers the README prints, so the
# transcript cannot drift away from the tool.
# ---------------------------------------------------------------------------

import demo_corpus  # noqa: E402


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    directory = tmp_path_factory.mktemp("awr-demo-corpus")
    summary = demo_corpus.write_corpus(str(directory), awr)
    return summary


def demo_own_keys(summary):
    with open(summary["ownKeys"], "r", encoding="utf-8") as handle:
        dids, problems = am.parse_own_keys(handle.read())
    assert problems == [], problems
    return dids


def test_every_demo_corpus_did_is_declared_in_the_real_own_keys_file():
    """The demo seeds are published too, so the demo DIDs are keys we can issue under."""
    declared, _ = committed_own_keys()
    missing = {
        role: did
        for role, did in demo_corpus.demo_dids(awr).items()
        if did not in declared
    }
    assert missing == {}, (
        "every demo-corpus DID must be in own-keys.txt: the seeds are published, so a demo "
        "document that strays into a real corpus must count as zero, not as an adopter"
    )


def test_demo_corpus_is_deterministic(tmp_path):
    """A transcript is only reproducible if the corpus is byte-identical on every run."""
    first = demo_corpus.write_corpus(str(tmp_path / "a"), awr)
    second = demo_corpus.write_corpus(str(tmp_path / "b"), awr)
    for name in first["files"]:
        with open(os.path.join(first["corpus"], name), "rb") as handle:
            left = handle.read()
        with open(os.path.join(second["corpus"], name), "rb") as handle:
            right = handle.read()
        assert left == right, "%s is not reproducible" % (name,)


def test_demo_corpus_reproduces_the_readme_transcript(demo, verifier):
    documents, errors, paths = am.read_all([demo["corpus"]], verifier)
    report = am.compute_report(
        documents, errors, demo_own_keys(demo), verifier,
        files_scanned=len(paths), now="2026-07-31T12:00:00Z",
    )

    # Every number the README prints, asserted here so the two cannot diverge.
    assert report["headline"]["value"] == 3
    assert report["corpus"]["filesScanned"] == 8
    assert report["corpus"]["documentsRead"] == 48
    assert report["corpus"]["duplicateIdsCollapsed"] == 1
    assert report["corpus"]["readErrorCount"] == 1
    assert report["issuers"]["distinct"] == 5
    assert report["issuers"]["distinctOwn"] == 2
    assert report["issuers"]["distinctForeign"] == 3
    assert report["context"]["validDocuments"] == 46
    assert report["context"]["foreignDocuments"] == 43
    assert report["context"]["ownDocuments"] == 3
    assert report["invalid"]["failedVerification"] == 1
    assert report["invalid"]["byReasonCode"] == {"AWR-PROOF-006": 1}
    assert report["invalid"]["byIssuerClass"]["foreign"] == 1

    biggest = report["foreignIssuers"][0]
    assert biggest["documents"] == 41, "one key emitting 41 documents is still one adopter"
    assert biggest["firstSeen"] == "2026-07-01T12:00:00Z"
    assert biggest["lastSeen"] == "2026-07-28T12:00:00Z"
    # Profile changes nothing about whether a document counts (SPEC 10.1: L0 is the floor).
    assert report["context"]["byProfile"]["foreign"] == {"L0": 42, "L2": 1}


def test_demo_corpus_with_an_empty_own_keys_file_reports_five(demo, verifier):
    """The 3-versus-5 line in the README: two undeclared keys of ours, a 67% larger number."""
    documents, errors, paths = am.read_all([demo["corpus"]], verifier)
    report = am.compute_report(
        documents, errors, set(), verifier,
        files_scanned=len(paths), now="2026-07-31T12:00:00Z",
    )
    assert report["headline"]["value"] == 5


def test_demo_corpus_under_the_structural_fallback_reports_four(demo):
    """The 3-versus-4 line: the fallback accepts the document whose signature is broken."""
    structural = am.build_verifier(force_structural=True)
    assert not structural.checks_signatures
    documents, errors, paths = am.read_all([demo["corpus"]], structural)
    report = am.compute_report(
        documents, errors, demo_own_keys(demo), structural,
        files_scanned=len(paths), now="2026-07-31T12:00:00Z",
    )
    assert report["headline"]["value"] == 4
    assert report["headline"]["signaturesVerified"] is False
    assert any("NO SIGNATURES WERE VERIFIED" in w for w in report["warnings"])


def test_forcing_the_fallback_and_requiring_the_reference_is_refused():
    with pytest.raises(SystemExit):
        am.build_verifier(require_reference=True, force_structural=True)


def test_cli_demo_corpus_writes_a_corpus_and_refuses_to_also_measure(tmp_path):
    proc = subprocess.run(
        [
            sys.executable,
            os.path.join(_HERE, "adoption_metric.py"),
            "--demo-corpus",
            str(tmp_path / "demo"),
        ],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert "SYNTHETIC DEMONSTRATION CORPUS" in proc.stderr
    assert os.path.isfile(str(tmp_path / "demo" / "own-keys.txt"))

    both = subprocess.run(
        [
            sys.executable,
            os.path.join(_HERE, "adoption_metric.py"),
            str(tmp_path / "demo" / "corpus"),
            "--demo-corpus",
            str(tmp_path / "demo2"),
        ],
        capture_output=True,
        text=True,
    )
    assert both.returncode == 2
    assert "does not also measure" in both.stderr
