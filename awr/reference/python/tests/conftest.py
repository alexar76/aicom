"""Shared builders and reason-code coverage tracking.

The coverage tracker is the point of ``assert_error`` / ``assert_warning`` /
``assert_raises_code``: every reason code asserted by any test is recorded, and the
terminal summary prints the exercised count against the section 11.2 registry.  A reason
code with no test is an unimplemented reason code, so the number is reported on every run
rather than claimed in prose.
"""

from __future__ import annotations

import base64
import copy
import os
import sys
from typing import Any, Callable, Dict, Iterable, List, Optional

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from awr.digest import sha256, sri_encode  # noqa: E402
from awr.documents import (  # noqa: E402
    AWR_CONTEXT,
    AWR_VERSION,
    VC_CONTEXT,
    document_reference,
)
from awr.errors import REGISTRY, AwrError  # noqa: E402
from awr.didkey import SigningKey  # noqa: E402
from awr.proof import (  # noqa: E402
    build_proof_options,
    encode_proof_value,
    hash_data,
    proof_config,
    sign_document,
    unsecured_document,
)

#: Deterministic clock for every time-dependent assertion (section 17 --now).
NOW = "2026-07-31T12:00:00Z"
VALID_FROM = "2026-07-31T10:15:30Z"
CREATED = "2026-07-31T10:15:30Z"

SEEN_CODES: set = set()


# ---------------------------------------------------------------------------
# keys
# ---------------------------------------------------------------------------


def deterministic_key(tag: int) -> SigningKey:
    return SigningKey.from_seed(bytes([tag]) * 32)


@pytest.fixture(scope="session")
def key_a() -> SigningKey:
    return deterministic_key(1)


@pytest.fixture(scope="session")
def key_b() -> SigningKey:
    return deterministic_key(2)


@pytest.fixture(scope="session")
def key_c() -> SigningKey:
    return deterministic_key(3)


# ---------------------------------------------------------------------------
# payload digests
# ---------------------------------------------------------------------------


def sri_of(payload: bytes) -> str:
    """SRI over application payload bytes (section 3.3: not over an AWR document)."""
    return sri_encode(sha256(payload))


INPUT_SRI = sri_of(b"the prompt payload")
OUTPUT_SRI = sri_of(b"the completion payload")


# ---------------------------------------------------------------------------
# subjects
# ---------------------------------------------------------------------------


def work_receipt_subject(**overrides: Any) -> Dict[str, Any]:
    subject: Dict[str, Any] = {
        "work": {
            "modelId": "claude-sonnet-5@anthropic",
            "capability": "urn:example:capability:summarise",
            "startedAt": "2026-07-31T10:15:28Z",
            "completedAt": "2026-07-31T10:15:30Z",
            "latencyMs": 2340,
            "status": "succeeded",
        },
        "inputDigest": INPUT_SRI,
        "outputDigest": OUTPUT_SRI,
        "nonce": "01J9Z8QK4T7YB2N5V6W8XA3C0D",
    }
    subject.update(copy.deepcopy(overrides))
    return subject


def verdict_subject(receipt: Optional[Dict[str, Any]] = None, **overrides: Any) -> Dict[str, Any]:
    subject: Dict[str, Any] = {
        "verdict": "pass",
        "score": "0.93",
        "method": {
            "id": "urn:example:method:grounded-council-v1",
            "name": "grounded council, 3 jurors",
            "modelIds": ["claude-opus-5@anthropic"],
        },
        "policy": {"threshold": "0.80"},
        "evidence": [{"kind": "trace", "digestSRI": sri_of(b"a trace file")}],
    }
    if receipt is not None:
        subject["verifiedWork"] = document_reference(receipt)
    subject.update(copy.deepcopy(overrides))
    return subject


def blame_subject(
    chain: Optional[Dict[str, Any]] = None,
    blamed: Optional[Dict[str, Any]] = None,
    **overrides: Any
) -> Dict[str, Any]:
    subject: Dict[str, Any] = {
        "failureClass": "wrong-output",
        "confidence": "0.90",
        "method": {"id": "urn:example:method:hop-bisect-v1"},
        "evidence": [{"kind": "replay", "digestSRI": sri_of(b"a replay log")}],
    }
    if chain is not None:
        subject["chain"] = document_reference(chain)
    if blamed is not None:
        subject["blamedWork"] = document_reference(blamed)
    subject.update(copy.deepcopy(overrides))
    return subject


DEFAULT_SUBJECTS: Dict[str, Callable[[], Dict[str, Any]]] = {
    "WorkReceipt": work_receipt_subject,
    "VerificationVerdict": lambda: verdict_subject(
        None, verifiedWork={"id": "urn:uuid:absent", "digestSRI": sri_of(b"absent")}
    ),
    "BlameAttestation": lambda: blame_subject(
        None,
        None,
        chain={"id": "urn:uuid:terminal", "digestSRI": sri_of(b"terminal")},
        blamedWork={"id": "urn:uuid:hop", "digestSRI": sri_of(b"hop")},
    ),
}


# ---------------------------------------------------------------------------
# documents
# ---------------------------------------------------------------------------

_counter = {"n": 0}


def next_id() -> str:
    _counter["n"] += 1
    return "urn:uuid:00000000-0000-4000-8000-%012d" % (_counter["n"],)


def build_unsecured(
    key: SigningKey,
    *,
    document_type: str = "WorkReceipt",
    subject: Optional[Dict[str, Any]] = None,
    document_id: Optional[str] = None,
    overrides: Optional[Dict[str, Any]] = None,
    drop: Iterable[str] = (),
) -> Dict[str, Any]:
    """A complete AWR/2 envelope, ready to be signed or deliberately broken."""
    document: Dict[str, Any] = {
        "@context": [VC_CONTEXT, AWR_CONTEXT],
        "id": document_id or next_id(),
        "type": ["VerifiableCredential", document_type],
        "issuer": {"id": key.did},
        "validFrom": VALID_FROM,
        "awrVersion": AWR_VERSION,
        "credentialSubject": subject
        if subject is not None
        else DEFAULT_SUBJECTS[document_type](),
    }
    if overrides:
        document.update(copy.deepcopy(overrides))
    for name in drop:
        document.pop(name, None)
    return document


def sign(document: Dict[str, Any], key: SigningKey, created: str = CREATED) -> Dict[str, Any]:
    """Sign whatever bytes are given, valid or not (the negative vectors need this)."""
    return sign_document(document, key, created)


def sign_with_options(
    document: Dict[str, Any], key: SigningKey, options: Dict[str, Any]
) -> Dict[str, Any]:
    """Sign with arbitrary proof options, so a proof defect can be tested in isolation.

    Without this, mutating a proof member after signing would also break the signature and
    every proof test would additionally report AWR-PROOF-006.
    """
    unsecured = unsecured_document(copy.deepcopy(document))
    config = proof_config(options, unsecured)
    _, _, message = hash_data(unsecured, config)
    secured = dict(unsecured)
    proof = copy.deepcopy(options)
    proof["proofValue"] = encode_proof_value(key.sign(message))
    secured["proof"] = proof
    return secured


def default_proof_options(key: SigningKey, **changes: Any) -> Dict[str, Any]:
    options = build_proof_options(key, CREATED)
    options.update(copy.deepcopy(changes))
    for name, value in list(options.items()):
        if value is None:
            del options[name]
    return options


def make_receipt(
    key: SigningKey,
    *,
    subject: Optional[Dict[str, Any]] = None,
    document_id: Optional[str] = None,
    overrides: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return sign(
        build_unsecured(
            key,
            document_type="WorkReceipt",
            subject=subject if subject is not None else work_receipt_subject(),
            document_id=document_id,
            overrides=overrides,
        ),
        key,
    )


def make_verdict(
    key: SigningKey,
    receipt: Dict[str, Any],
    *,
    subject_overrides: Optional[Dict[str, Any]] = None,
    document_id: Optional[str] = None,
) -> Dict[str, Any]:
    subject = verdict_subject(receipt, **(subject_overrides or {}))
    return sign(
        build_unsecured(
            key,
            document_type="VerificationVerdict",
            subject=subject,
            document_id=document_id,
        ),
        key,
    )


def make_blame(
    key: SigningKey,
    chain: Dict[str, Any],
    blamed: Dict[str, Any],
    *,
    subject_overrides: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    subject = blame_subject(chain, blamed, **(subject_overrides or {}))
    return sign(
        build_unsecured(key, document_type="BlameAttestation", subject=subject), key
    )


def legacy_document(
    key: SigningKey,
    subject: Dict[str, Any],
    *,
    dialect: str = "A",
    signature: Optional[bytes] = None,
    document_id: str = "urn:uuid:legacy-0001",
) -> Dict[str, Any]:
    """An AWR/1 document, assembled in the test suite rather than by the library.

    Section 12 forbids an implementation from *issuing* AWR/1, so the package exposes no
    way to produce one.  The signature here is computed with a raw Ed25519 signer over the
    legacy canonical form -- a real signature over real bytes, produced outside the AWR
    API on purpose.
    """
    from awr.legacy import legacy_canonical_form

    if signature is None:
        signature = key.sign(legacy_canonical_form(subject, dialect))
    return {
        "@context": ["https://www.w3.org/2018/credentials/v1"],
        "id": document_id,
        "type": ["VerifiableCredential", "WorkReceipt"],
        "issuer": {
            "id": "did:key:" + base64.b64encode(key.public_key_bytes).decode()[:32],
            "publicKeyJwk": key.public_key_jwk(),
        },
        "issuanceDate": VALID_FROM,
        "hubInfo": {"name": "legacy-hub"},
        "credentialSubject": copy.deepcopy(subject),
        "proof": {
            "type": "Ed25519Signature2018",
            "created": CREATED,
            "proofPurpose": "assertionMethod",
            "verificationMethod": "did:key:legacy#key-1",
            "proofValue": base64.b64encode(signature).decode("ascii"),
        },
    }


# ---------------------------------------------------------------------------
# assertions that record coverage
# ---------------------------------------------------------------------------


def _codes(entries: Iterable[Dict[str, str]]) -> List[str]:
    return [entry["code"] for entry in entries]


def assert_error(result: Dict[str, Any], code: str) -> None:
    assert code in REGISTRY, "%s is not in the section 11.2 registry" % (code,)
    SEEN_CODES.add(code)
    assert REGISTRY[code].severity == "error", "%s is a warning, not an error" % (code,)
    codes = _codes(result["reasons"])
    assert code in codes, "expected error %s, got reasons=%s warnings=%s" % (
        code,
        codes,
        _codes(result["warnings"]),
    )
    assert result["valid"] is False, "a document with an error must not be valid"


def assert_warning(result: Dict[str, Any], code: str) -> None:
    assert code in REGISTRY, "%s is not in the section 11.2 registry" % (code,)
    SEEN_CODES.add(code)
    assert REGISTRY[code].severity == "warning", "%s is an error, not a warning" % (code,)
    codes = _codes(result["warnings"])
    assert code in codes, "expected warning %s, got warnings=%s reasons=%s" % (
        code,
        codes,
        _codes(result["reasons"]),
    )
    assert code not in _codes(
        result["reasons"]
    ), "a warning must not appear in reasons (section 11.1)"


def assert_no_error(result: Dict[str, Any], code: str) -> None:
    assert code not in _codes(result["reasons"]), "%s should not have been reported" % (code,)


def assert_raises_code(code: str, function: Callable[[], Any]) -> AwrError:
    assert code in REGISTRY, "%s is not in the section 11.2 registry" % (code,)
    SEEN_CODES.add(code)
    with pytest.raises(AwrError) as info:
        function()
    assert info.value.code == code, "expected %s, raised %s" % (code, info.value.code)
    return info.value


def record_code(code: str) -> None:
    """Record a code exercised through a channel other than the helpers above."""
    assert code in REGISTRY
    SEEN_CODES.add(code)


# ---------------------------------------------------------------------------
# coverage summary
# ---------------------------------------------------------------------------


def pytest_terminal_summary(terminalreporter, exitstatus, config) -> None:  # noqa: ANN001
    registry = set(REGISTRY)
    exercised = SEEN_CODES & registry
    missing = sorted(registry - exercised)
    terminalreporter.write_sep("-", "AWR reason-code coverage")
    terminalreporter.write_line(
        "section 11.2 registry: %d codes; exercised by assertions: %d"
        % (len(registry), len(exercised))
    )
    if missing:
        terminalreporter.write_line("NOT EXERCISED (%d): %s" % (len(missing), ", ".join(missing)))
    else:
        terminalreporter.write_line("every registry code is exercised by at least one test")
