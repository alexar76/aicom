#!/usr/bin/env python3
"""Regenerate every AWR/2 test vector and ``index.json`` from the reference implementation.

    PYTHONPATH=awr/reference/python \
      aimarket-hub/.venv/bin/python awr/vectors/generate.py

Run it from anywhere; paths are resolved relative to this file.

**Deterministic by construction.**  There is no wall-clock read and no randomness anywhere
in this file: every timestamp is a literal, every document identifier is derived from a
counter, and every signing key comes from a fixed, *published* test seed.  Ed25519 is
deterministic (RFC 8032), so re-running produces byte-identical files.  ``check_vectors.py``
re-runs the generator into a temporary tree and diffs it, so a non-deterministic edit to this
file is a test failure rather than a surprise in a later diff.

**Every cryptographic value in every file this script writes is computed here.**  No
signature, digest, hash or canonical byte string in ``awr/vectors/`` was typed by hand.  The
two places where a vector's *defect* cannot be produced by the signer -- a non-integer
number and a lone surrogate cannot be canonicalized at all -- are built by signing a
sentinel-carrying variant and then substituting the defect into the emitted text; each such
vector carries a ``note`` in ``index.json`` saying exactly what was signed.

**The signing keys are the Ed25519 test vectors of RFC 8032 section 7.1.**  They are
published in an IETF standard, they confer nothing, and they MUST NOT be used to issue a
real receipt.  See ``README.md``.
"""

from __future__ import annotations

import base64
import copy
import hashlib
import json
import os
import sys
from typing import Any, Dict, List, Optional, Sequence

HERE = os.path.dirname(os.path.abspath(__file__))
REFERENCE = os.path.abspath(os.path.join(HERE, "..", "reference", "python"))
if REFERENCE not in sys.path:
    sys.path.insert(0, REFERENCE)

from awr import (  # noqa: E402
    SigningKey,
    canonical_sri,
    canonicalize,
    document_reference,
    legacy_canonical_form,
    make_bundle,
)
from awr.digest import sri_encode  # noqa: E402
from awr.documents import AWR_CONTEXT, VC_CONTEXT  # noqa: E402
from awr.jcs import loads as strict_loads  # noqa: E402
from awr.multibase import (  # noqa: E402
    multibase_decode_base58btc,
    multibase_encode_base58btc,
)
from awr.proof import (  # noqa: E402
    encode_proof_value,
    hash_data,
    proof_config,
    sign_document,
    unsecured_document,
)

# ---------------------------------------------------------------------------
# fixed inputs
# ---------------------------------------------------------------------------

#: Ed25519 test keys.  Every seed is published in RFC 8032 section 7.1; ``generate.py``
#: asserts that each one derives the public key RFC 8032 records for it, which is also a
#: check on the reference implementation's ``did:key`` derivation.
TEST_KEYS: Sequence[Dict[str, str]] = (
    {
        "name": "hub",
        "role": "issuer of WorkReceipts (issuer.name 'example-hub')",
        "seedHex": "9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60",
        "publicKeyHex": "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a",
        "source": "RFC 8032 section 7.1, TEST 1 secret key",
    },
    {
        "name": "verifierA",
        "role": "issuer of VerificationVerdicts (independent verifier #1)",
        "seedHex": "4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb",
        "publicKeyHex": "3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c",
        "source": "RFC 8032 section 7.1, TEST 2 secret key",
    },
    {
        "name": "verifierB",
        "role": "issuer of VerificationVerdicts (independent verifier #2)",
        "seedHex": "c5aa8df43f9f837bedb7442f31dcb7b166d38535076f094b85ce3a2e0b4458f7",
        "publicKeyHex": "fc51cd8e6218a1a38da47ed00230f0580816ed13ba3303ac5deb911548908025",
        "source": "RFC 8032 section 7.1, TEST 3 secret key",
    },
    {
        "name": "attributor",
        "role": "issuer of BlameAttestations",
        "seedHex": "f5e5767cf153319517630f226876b86c8160cc583bc013744c6bf255f5cc0ee5",
        "publicKeyHex": "278117fc144c72340f67d0f2316e8386ceffbf2b2428c9c51fef7c597f1d426e",
        "source": "RFC 8032 section 7.1, TEST 1024 secret key",
    },
    {
        "name": "upstream",
        "role": "issuer of upstream hops in a multi-hop chain (a second, unrelated hub)",
        "seedHex": "833fe62409237b9d62ec77587520911e9a759cec1d19755b7da901b96dca3d42",
        "publicKeyHex": "ec172b93ad5e563bf4932c70e1245034c35467ef2efd4d64ebf819683467e2bf",
        "source": "RFC 8032 section 7.1, TEST SHA(abc) secret key",
    },
)

KEYS: Dict[str, SigningKey] = {}
for _entry in TEST_KEYS:
    _key = SigningKey.from_seed(bytes.fromhex(_entry["seedHex"]))
    if _key.public_key_bytes.hex() != _entry["publicKeyHex"]:
        raise SystemExit(
            "seed %s does not derive the public key RFC 8032 records for it"
            % (_entry["name"],)
        )
    KEYS[_entry["name"]] = _key
del _entry, _key

HUB = KEYS["hub"]
VERIFIER_A = KEYS["verifierA"]
VERIFIER_B = KEYS["verifierB"]
ATTRIBUTOR = KEYS["attributor"]
UPSTREAM = KEYS["upstream"]

#: The clock every vector is checked at.  ``--now`` makes AWR-TIME-001/002 deterministic
#: (SPEC.md section 17); without it the time warnings depend on when the suite is run.
NOW = "2026-07-31T12:00:00Z"

VALID_FROM = "2026-07-31T10:15:30Z"
STARTED_AT = "2026-07-31T10:15:28Z"
COMPLETED_AT = "2026-07-31T10:15:30Z"
VALID_UNTIL_FUTURE = "2027-07-31T10:15:30Z"
VALID_UNTIL_PAST = "2026-07-31T11:00:00Z"
FUTURE_VALID_FROM = "2027-01-01T00:00:00Z"
LEGACY_CREATED = "2026-01-15T09:00:05Z"
LEGACY_COMPLETED = "2026-01-15T09:00:00Z"

#: Application payload bytes whose digests the receipts carry.  Recording the payloads (not
#: just the digests) is what lets a third party reproduce ``inputDigest``/``outputDigest``;
#: section 3.3 only *recommends* that the issuer document its serialization, and a vector
#: set that did not would be unreproducible.
PAYLOADS: Dict[str, bytes] = {
    "prompt": b'{"prompt":"summarise the attached incident report"}',
    "summary": b'{"summary":"Disk pressure on node 7 backed up the ingest queue."}',
    "retrieved": b'{"chunks":[{"id":"doc-1"},{"id":"doc-2"}]}',
    "tool-call": b'{"tool":"search","query":"node 7 disk"}',
    "empty": b"",
}
SRI = {name: sri_encode(hashlib.sha256(data).digest()) for name, data in PAYLOADS.items()}
EMPTY_SRI = SRI["empty"]

DEPTH_LIMIT = 64  # section 8.2 default

VECTORS: List[Dict[str, Any]] = []
WRITTEN: List[str] = []


# ---------------------------------------------------------------------------
# file helpers
# ---------------------------------------------------------------------------


def _path(relative: str) -> str:
    return os.path.join(HERE, relative)


def write_text(relative: str, text: str) -> None:
    """Write UTF-8 text exactly, with no platform newline translation."""
    target = _path(relative)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "w", encoding="utf-8", newline="") as handle:
        handle.write(text)
    WRITTEN.append(relative)


def write_bytes(relative: str, data: bytes) -> None:
    target = _path(relative)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "wb") as handle:
        handle.write(data)
    WRITTEN.append(relative)


def json_text(value: Any, *, ascii_only: bool = False) -> str:
    return json.dumps(value, indent=2, ensure_ascii=ascii_only, sort_keys=False) + "\n"


def write_json(relative: str, value: Any, *, ascii_only: bool = False) -> None:
    write_text(relative, json_text(value, ascii_only=ascii_only))


# ---------------------------------------------------------------------------
# manifest
# ---------------------------------------------------------------------------


def vector(
    vid: str,
    file: str,
    kind: str,
    expect: str,
    expected_codes: Sequence[str],
    expected_warnings: Sequence[str],
    profile: Optional[str],
    tags: Sequence[str],
    why: str,
    **extra: Any
) -> None:
    """Append one manifest entry.

    ``why`` is mandatory and is not decorative: a vector nobody can name an attack or a
    divergence for does not belong in the set, because it cannot fail informatively.
    """
    if not why or not why.strip():
        raise SystemExit("vector %s has no 'why'" % (vid,))
    if kind not in ("document", "bundle", "canonicalization", "proof"):
        raise SystemExit("vector %s has unknown kind %r" % (vid, kind))
    if expect not in ("valid", "invalid"):
        raise SystemExit("vector %s has unknown expect %r" % (vid, expect))
    if expect == "invalid" and not expected_codes:
        raise SystemExit("vector %s expects invalid but names no code" % (vid,))
    if expect == "valid" and expected_codes:
        raise SystemExit("vector %s expects valid but names error codes" % (vid,))
    entry: Dict[str, Any] = {
        "id": vid,
        "file": file,
        "kind": kind,
        "expect": expect,
        "expectedCodes": list(expected_codes),
        "expectedWarnings": list(expected_warnings),
        "profile": profile,
        "tags": list(tags),
        "why": why,
    }
    entry.update(extra)
    for previous in VECTORS:
        if previous["id"] == vid:
            raise SystemExit("duplicate vector id %r" % (vid,))
    VECTORS.append(entry)


# ---------------------------------------------------------------------------
# document construction
# ---------------------------------------------------------------------------

_COUNTER = {"n": 0}


def next_id() -> str:
    """A deterministic ``urn:uuid:`` identifier.  No randomness: uuid4 would break reruns."""
    _COUNTER["n"] += 1
    return "urn:uuid:%08x-a11c-4f38-9b8a-1c2d3e4f5a6b" % (_COUNTER["n"],)


def envelope(
    subject: Dict[str, Any],
    key: SigningKey,
    *,
    document_type: str = "WorkReceipt",
    document_id: Optional[str] = None,
    issuer_name: Optional[str] = None,
    include_jwk: bool = False,
    issuer: Optional[Any] = None,
    valid_from: str = VALID_FROM,
    valid_until: Optional[str] = None,
    context: Optional[List[Any]] = None,
    types: Optional[List[Any]] = None,
    awr_version: str = "2.0.0",
    top_level: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build an unsecured section 3.1 envelope.

    Every parameter that a negative vector needs to break -- ``@context``, ``type``,
    ``issuer``, ``validFrom``, ``awrVersion`` -- is a parameter here, so the defect is
    present *before* signing and therefore inside the signature.  A vector whose defect were
    introduced after signing would only ever test AWR-PROOF-006.
    """
    if issuer is None:
        issuer_object: Any = {"id": key.did}
        if issuer_name is not None:
            issuer_object["name"] = issuer_name
        if include_jwk:
            issuer_object["publicKeyJwk"] = key.public_key_jwk()
    else:
        issuer_object = issuer
    document: Dict[str, Any] = {
        "@context": [VC_CONTEXT, AWR_CONTEXT] if context is None else context,
        "id": document_id or next_id(),
        "type": ["VerifiableCredential", document_type] if types is None else types,
        "issuer": issuer_object,
        "validFrom": valid_from,
        "awrVersion": awr_version,
        "credentialSubject": copy.deepcopy(subject),
    }
    if valid_until is not None:
        document["validUntil"] = valid_until
    if top_level:
        document.update(copy.deepcopy(top_level))
    return document


def sign(
    document: Dict[str, Any],
    key: SigningKey,
    *,
    created: str = VALID_FROM,
    purpose: str = "assertionMethod",
    proof_extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return sign_document(
        document, key, created, purpose=purpose, proof_extra=proof_extra
    )


def receipt_subject(**extra: Any) -> Dict[str, Any]:
    """The minimal section 3.3 subject: everything else in section 3.3 is OPTIONAL."""
    subject: Dict[str, Any] = {
        "work": {
            "modelId": "claude-sonnet-5@anthropic",
            "completedAt": COMPLETED_AT,
            "status": "succeeded",
        },
        "inputDigest": SRI["prompt"],
        "outputDigest": SRI["summary"],
    }
    subject.update(copy.deepcopy(extra))
    return subject


def work_receipt(key: SigningKey = HUB, **kwargs: Any) -> Dict[str, Any]:
    subject = kwargs.pop("subject", None)
    if subject is None:
        subject = receipt_subject()
    return sign(envelope(subject, key, **kwargs), key)


def verdict_subject(receipt: Dict[str, Any], **extra: Any) -> Dict[str, Any]:
    subject: Dict[str, Any] = {
        "verifiedWork": document_reference(receipt),
        "verdict": "pass",
        "score": "0.93",
        "method": {
            "id": "urn:example:method:grounded-council-v1",
            "name": "grounded council, 3 jurors",
            "modelIds": ["claude-opus-5@anthropic"],
        },
    }
    subject.update(copy.deepcopy(extra))
    return subject


SETTLEMENT = {
    "scheme": "escrow-evm-v1",
    "chainId": 8453,
    "contract": "0x0000000000000000000000000000000000000000",
    "holdId": "0x9f2c1d4e5a6b7c8d9e0f1a2b3c4d5e6f70819293a4b5c6d7e8f90a1b2c3d4e5f",
    "amount": {"currency": "USD", "amount": "0.10"},
}

STAKE = {
    "scheme": "stake-evm-v1",
    "chainId": 8453,
    "contract": "0x0000000000000000000000000000000000000001",
    "amount": {"currency": "USD", "amount": "5.00"},
    "slashingPolicy": {
        "id": "urn:example:policy:v2",
        "digestSRI": SRI["retrieved"],
    },
}


# ---------------------------------------------------------------------------
# valid vectors
# ---------------------------------------------------------------------------


def build_valid() -> Dict[str, Any]:
    built: Dict[str, Any] = {}

    # -- 1. minimal L0 -----------------------------------------------------
    minimal = work_receipt(issuer_name="example-hub")
    write_json("valid/receipt-minimal-l0.json", minimal)
    built["minimal"] = minimal
    vector(
        "valid/receipt-minimal-l0",
        "valid/receipt-minimal-l0.json",
        "document",
        "valid",
        [],
        [],
        "L0",
        ["receipt", "L0", "floor"],
        "The adoption floor: if this does not verify, nothing else in the set can. Every "
        "field present is REQUIRED by section 3.1/3.3 and no OPTIONAL field is, so a "
        "verifier that demands an optional field fails here and only here.",
        now=NOW,
    )

    # -- 2. every optional field -------------------------------------------
    unresolved_parent_id = next_id()
    maximal_subject = receipt_subject(
        work={
            "modelId": "claude-sonnet-5@anthropic",
            "capability": "urn:example:capability:summarise",
            "startedAt": STARTED_AT,
            "completedAt": COMPLETED_AT,
            "latencyMs": 2340,
            "status": "succeeded",
        },
        parents=[
            {
                "id": unresolved_parent_id,
                "digestSRI": SRI["retrieved"],
                "role": "retrieval",
            }
        ],
        price={"currency": "USD", "amount": "0.15"},
        nonce="01J9Z8QK4T7YB2N5V6W8XA3C0D",
        environment={
            "teeAttestation": {
                "platform": "aws-nitro",
                "documentDigestSRI": SRI["tool-call"],
            },
            "zkProof": {"scheme": "groth16", "proofDigestSRI": SRI["retrieved"]},
        },
        settlement=copy.deepcopy(SETTLEMENT),
        awrProfile="L2",
    )
    maximal = work_receipt(
        subject=maximal_subject,
        issuer_name="example-hub",
        include_jwk=True,
        valid_until=VALID_UNTIL_FUTURE,
    )
    write_json("valid/receipt-all-optional-fields.json", maximal)
    built["maximal"] = maximal
    vector(
        "valid/receipt-all-optional-fields",
        "valid/receipt-all-optional-fields.json",
        "document",
        "valid",
        [],
        ["AWR-ENV-001", "AWR-L2-001"],
        "L0",
        [
            "receipt",
            "optional-fields",
            "AWR-ENV-001",
            "AWR-L2-001",
            "self-asserted-profile",
        ],
        "Every OPTIONAL member of sections 3.1/3.3 at once, including publicKeyJwk, an "
        "unresolved parent edge, and awrProfile:\"L2\" on a receipt that satisfies only L0 "
        "-- section 3.3 forbids granting a level because a document claims it, so an "
        "implementation that trusts the hint reports L2 here and fails.",
        now=NOW,
    )

    # -- 3. unknown extension properties at every level ---------------------
    extension_subject = receipt_subject(
        work={
            "modelId": "claude-sonnet-5@anthropic",
            "completedAt": COMPLETED_AT,
            "status": "succeeded",
            "x-vendor-region": "eu-central-1",
        },
        parents=[
            {
                "id": next_id(),
                "digestSRI": SRI["retrieved"],
                "role": "retrieval",
                "x-vendor-edge-note": "cached",
            }
        ],
        **{
            "x-vendor-subject": {
                "nested": {"deeper": ["a", "b", {"deepest": True}]},
                "count": 3,
            }
        }
    )
    extension_doc = envelope(
        extension_subject,
        HUB,
        issuer_name="example-hub",
        top_level={
            "x-vendor-top-level": {"trace": "urn:example:trace:9f2c", "sampled": False},
            "credentialSchema": {
                "id": "https://verify.modelmarket.dev/ns/awr/v2/work-receipt",
                "type": "JsonSchema",
            },
        },
    )
    extension_doc["issuer"]["x-vendor-issuer"] = {"tenant": "acme"}
    extensions = sign(
        extension_doc,
        HUB,
        proof_extra={"x-vendor-proof": {"hsmSlot": 2}},
    )
    write_json("valid/receipt-unknown-extensions.json", extensions)
    built["extensions"] = extensions
    vector(
        "valid/receipt-unknown-extensions",
        "valid/receipt-unknown-extensions.json",
        "document",
        "valid",
        [],
        [],
        "L0",
        ["receipt", "section-3.1", "extension-preservation", "forward-compatibility"],
        "Unknown properties at every level -- top level, inside issuer, inside "
        "credentialSubject, inside work, inside a parents entry, inside proof, and nested "
        "two deep. Section 3.1 requires them ignored semantically, included in "
        "canonicalization and never stripped: an implementation that parses into a typed "
        "struct drops them, computes different bytes and fails AWR-PROOF-006 here.",
        now=NOW,
    )

    # -- 4. non-ASCII and emoji --------------------------------------------
    unicode_subject = receipt_subject(
        work={
            "modelId": "модель-α@供应商 \U0001f680",
            "completedAt": COMPLETED_AT,
            "status": "succeeded",
        },
        **{
            "x-labels": {
                "ru": "Проверка работы",
                "ja": "検証済み ✅",
                "ar": "تحقق من العمل",
                "he": "אימות עבודה",
                "emoji": "\U0001f9ea\U0001f4c4\U0001f510 \U0001f469‍\U0001f52c",
                "flag": "\U0001f1ec\U0001f1e7",
                "math": "∑ ≤ ∞ × ÷",
            }
        }
    )
    unicode_doc = work_receipt(
        subject=unicode_subject,
        issuer_name="Аргус — проверка \U0001f50e",
    )
    write_json("valid/receipt-unicode-strings.json", unicode_doc)
    vector(
        "valid/receipt-unicode-strings",
        "valid/receipt-unicode-strings.json",
        "document",
        "valid",
        [],
        [],
        "L0",
        ["receipt", "section-4.1", "unicode", "emoji", "zwj", "rtl"],
        "Cyrillic, CJK, Arabic, Hebrew, a ZWJ emoji sequence, a regional-indicator flag "
        "pair and mathematical symbols in string values. RFC 8785 section 3.2.2.2 emits all "
        "of them literally as UTF-8; an implementation that escapes non-ASCII as \\uXXXX "
        "(the JSON default in several languages) computes different bytes and fails.",
        now=NOW,
    )

    # -- 5. non-BMP object key (UTF-16 ordering) ---------------------------
    ordering = {
        "b": 2,
        "a": 1,
        "￿": 3,
        "\U0001f600": 4,
        "\U00010000": 5,
        "é": 6,
        "z": 7,
    }
    non_bmp_subject = receipt_subject(**{"x-ordering": copy.deepcopy(ordering)})
    non_bmp_doc = envelope(
        non_bmp_subject,
        HUB,
        issuer_name="example-hub",
        top_level={"\U0001f600-top": "astral key at the document level", "￿-top": 1},
    )
    non_bmp = sign(non_bmp_doc, HUB)
    write_json("valid/receipt-non-bmp-object-keys.json", non_bmp)
    built["non_bmp"] = non_bmp
    utf16_order = ["a", "b", "z", "é", "\U00010000", "\U0001f600", "￿"]
    codepoint_order = ["a", "b", "z", "é", "￿", "\U00010000", "\U0001f600"]
    if utf16_order == codepoint_order:  # pragma: no cover - guards the vector's purpose
        raise SystemExit("the non-BMP key vector no longer distinguishes the two orders")
    vector(
        "valid/receipt-non-bmp-object-keys",
        "valid/receipt-non-bmp-object-keys.json",
        "document",
        "valid",
        [],
        [],
        "L0",
        ["receipt", "section-4.1", "utf-16-ordering", "non-bmp"],
        "Object keys U+1F600 and U+10000 (astral) alongside U+FFFF and ASCII, at two "
        "levels. RFC 8785 section 3.2.3 sorts names as arrays of UTF-16 code units, so an "
        "astral key's leading surrogate (D800..DBFF) sorts BEFORE U+FFFF; code-point "
        "sorting puts it after. This is the only vector where the two orders differ, so an "
        "implementation using its language's default string sort fails here alone.",
        now=NOW,
    )

    # -- 6. decomposed Unicode (no NFC) ------------------------------------
    # Explicit escapes: this is the one vector whose point is destroyed if the source
    # file is ever Unicode-normalised in place.
    decomposed_subject = receipt_subject(
        **{
            "x-normalization": {
                "precomposed": "\u00e9\u00e5\u00f6",
                "decomposed": "e\u0301a\u030ao\u0308",
                "hangulPrecomposed": "\ud55c",
                "hangulDecomposed": "\u1112\u1161\u11ab",
            }
        }
    )
    decomposed = work_receipt(
        subject=decomposed_subject,
        issuer_name="Andre\u0301 Verifica\u0327a\u0303o",
    )
    write_json("valid/receipt-decomposed-unicode.json", decomposed)
    vector(
        "valid/receipt-decomposed-unicode",
        "valid/receipt-decomposed-unicode.json",
        "document",
        "valid",
        [],
        [],
        "L0",
        ["receipt", "section-4.1", "no-nfc", "AWR-CANON-006"],
        "issuer.name and a subject extension carry NFD sequences (U+0065 U+0301, "
        "U+1112 U+1161 U+11AB) next to their NFC equivalents. Section 4.1 item 2 forbids "
        "normalization, so an implementation that applies NFC -- the documented AWR/1 "
        "deviation -- silently rewrites the bytes it signs over and fails AWR-PROOF-006 "
        "on a document its own issuer produced.",
        now=NOW,
    )

    # -- 7. failed status, empty-payload outputDigest ----------------------
    failed = work_receipt(
        subject=receipt_subject(
            work={
                "modelId": "claude-sonnet-5@anthropic",
                "startedAt": STARTED_AT,
                "completedAt": COMPLETED_AT,
                "latencyMs": 2000,
                "status": "failed",
            },
            outputDigest=EMPTY_SRI,
            nonce="01J9Z8QK4T7YB2N5V6W8XA3C0E",
        ),
        issuer_name="example-hub",
    )
    write_json("valid/receipt-failed-empty-output.json", failed)
    vector(
        "valid/receipt-failed-empty-output",
        "valid/receipt-failed-empty-output.json",
        "document",
        "valid",
        [],
        [],
        "L0",
        ["receipt", "section-3.3", "failure-is-first-class", "empty-digest"],
        "status \"failed\" with outputDigest = SRI of the empty byte string, the exact "
        "value section 3.2 shows. Section 3.3 makes a receipt for work that did not succeed "
        "a first-class document, so an implementation that treats a non-succeeded status or "
        "an empty-payload digest as an error rejects the case disputes actually turn on.",
        now=NOW,
    )

    # -- 8. two-hop chain ---------------------------------------------------
    hop_parent = work_receipt(
        subject=receipt_subject(
            work={
                "modelId": "text-embedding-4@example",
                "startedAt": "2026-07-31T10:15:20Z",
                "completedAt": "2026-07-31T10:15:22Z",
                "latencyMs": 1800,
                "status": "succeeded",
            },
            inputDigest=SRI["prompt"],
            outputDigest=SRI["retrieved"],
            nonce="01J9Z8QK4T7YB2N5V6W8XA3B01",
        ),
        key=UPSTREAM,
        issuer_name="example-retrieval",
    )
    hop_child = work_receipt(
        subject=receipt_subject(
            inputDigest=SRI["retrieved"],
            outputDigest=SRI["summary"],
            parents=[dict(document_reference(hop_parent), role="retrieval")],
            nonce="01J9Z8QK4T7YB2N5V6W8XA3B02",
        ),
        issuer_name="example-hub",
    )
    two_hop = make_bundle([hop_child, hop_parent])
    write_json("valid/chain-two-hop.awrb.json", two_hop)
    built["hop_parent"] = hop_parent
    built["hop_child"] = hop_child
    vector(
        "valid/chain-two-hop",
        "valid/chain-two-hop.awrb.json",
        "bundle",
        "valid",
        [],
        [],
        "L0",
        ["bundle", "chain", "section-8", "content-addressed-edge"],
        "A two-hop chain whose edge digests the SECURED parent (section 8.1) and whose "
        "parent outputDigest equals the child inputDigest, so no AWR-CHAIN-007 fires. It "
        "is the positive control for every chain negative: an implementation that digests "
        "the unsecured parent, or digests it non-canonically, fails here and cannot "
        "distinguish itself from a forgery.",
        now=NOW,
    )

    # -- 9. L1 bundle -------------------------------------------------------
    l1_verdict = sign(
        envelope(
            verdict_subject(
                minimal,
                policy={"threshold": "0.80"},
                evidence=[{"kind": "trace", "digestSRI": SRI["tool-call"]}],
            ),
            VERIFIER_A,
            document_type="VerificationVerdict",
            issuer_name="example-verifier-a",
        ),
        VERIFIER_A,
    )
    l1_bundle = make_bundle([minimal, l1_verdict])
    write_json("valid/bundle-l1-verified.awrb.json", l1_bundle)
    built["l1_verdict"] = l1_verdict
    vector(
        "valid/bundle-l1-verified",
        "valid/bundle-l1-verified.awrb.json",
        "bundle",
        "valid",
        [],
        [],
        "L1",
        ["bundle", "profile", "L1", "section-10.2"],
        "A receipt plus one verdict from a different issuer, the whole of L1. The verdict "
        "references the receipt by digest, so an implementation that matches verdict to "
        "receipt by identifier alone still passes here but fails "
        "invalid/verdict-repointed-same-id -- this vector exists so that the pair "
        "localises the defect.",
        now=NOW,
    )

    # -- 10. L2 bundle ------------------------------------------------------
    l2_receipt = work_receipt(
        subject=receipt_subject(
            nonce="01J9Z8QK4T7YB2N5V6W8XA3C11",
            settlement=copy.deepcopy(SETTLEMENT),
        ),
        issuer_name="example-hub",
    )
    l2_verdict_a = sign(
        envelope(
            verdict_subject(
                l2_receipt,
                policy={"threshold": "0.80"},
                stake=copy.deepcopy(STAKE),
            ),
            VERIFIER_A,
            document_type="VerificationVerdict",
            issuer_name="example-verifier-a",
        ),
        VERIFIER_A,
    )
    l2_verdict_b = sign(
        envelope(
            verdict_subject(
                l2_receipt,
                verdict="inconclusive",
                score="0.55",
                policy={"threshold": "0.80"},
                method={"id": "urn:example:method:replay-diff-v2"},
                stake=copy.deepcopy(STAKE),
            ),
            VERIFIER_B,
            document_type="VerificationVerdict",
            issuer_name="example-verifier-b",
        ),
        VERIFIER_B,
    )
    l2_bundle = make_bundle([l2_receipt, l2_verdict_a, l2_verdict_b])
    write_json("valid/bundle-l2-accountable.awrb.json", l2_bundle)
    built["l2_receipt"] = l2_receipt
    built["l2_verdict_a"] = l2_verdict_a
    vector(
        "valid/bundle-l2-accountable",
        "valid/bundle-l2-accountable.awrb.json",
        "bundle",
        "valid",
        [],
        ["AWR-L2-001"],
        "L2",
        ["bundle", "profile", "L2", "section-10.3", "AWR-L2-001"],
        "Two verdicts from distinct issuers plus BOTH accountability bindings (receipt "
        "settlement and stake on each verdict), and the second verdict is "
        "\"inconclusive\": section 3.4 forbids treating that as a failure and section 10.2 "
        "makes it satisfy the level structurally, so an implementation that counts only "
        "\"pass\" verdicts loses L2 here. AWR-L2-001 MUST be reported -- a verifier that "
        "silently implies the escrow was checked on-chain is the failure section 10.3 "
        "names.",
        now=NOW,
    )

    # -- 11. blame attestation over a three-hop chain -----------------------
    hop3 = work_receipt(
        subject=receipt_subject(
            work={
                "modelId": "web-search-1@example",
                "startedAt": "2026-07-31T10:15:10Z",
                "completedAt": "2026-07-31T10:15:12Z",
                "latencyMs": 1500,
                "status": "succeeded",
            },
            inputDigest=SRI["prompt"],
            outputDigest=SRI["tool-call"],
            nonce="01J9Z8QK4T7YB2N5V6W8XA3D01",
        ),
        key=UPSTREAM,
        issuer_name="example-search",
    )
    hop2 = work_receipt(
        subject=receipt_subject(
            work={
                "modelId": "text-embedding-4@example",
                "startedAt": "2026-07-31T10:15:14Z",
                "completedAt": "2026-07-31T10:15:16Z",
                "latencyMs": 1600,
                "status": "succeeded",
            },
            inputDigest=SRI["tool-call"],
            outputDigest=SRI["retrieved"],
            parents=[dict(document_reference(hop3), role="tool")],
            nonce="01J9Z8QK4T7YB2N5V6W8XA3D02",
        ),
        key=UPSTREAM,
        issuer_name="example-retrieval",
    )
    hop1 = work_receipt(
        subject=receipt_subject(
            work={
                "modelId": "claude-sonnet-5@anthropic",
                "startedAt": STARTED_AT,
                "completedAt": COMPLETED_AT,
                "latencyMs": 2340,
                "status": "succeeded",
            },
            inputDigest=SRI["retrieved"],
            outputDigest=SRI["summary"],
            parents=[dict(document_reference(hop2), role="subagent")],
            nonce="01J9Z8QK4T7YB2N5V6W8XA3D03",
        ),
        issuer_name="example-hub",
    )
    chain_bundle = make_bundle([hop1, hop2, hop3])
    write_json("valid/blame-chain-receipts.awrb.json", chain_bundle)
    blame = sign(
        envelope(
            {
                "chain": document_reference(hop1),
                "blamedWork": document_reference(hop3),
                "failureClass": "upstream-input",
                "confidence": "0.90",
                "method": {"id": "urn:example:method:hop-bisect-v1"},
                "evidence": [{"kind": "replay", "digestSRI": SRI["tool-call"]}],
            },
            ATTRIBUTOR,
            document_type="BlameAttestation",
            issuer_name="example-attributor",
        ),
        ATTRIBUTOR,
    )
    write_json("valid/blame-three-hop.json", blame)
    built["hop1"] = hop1
    built["hop2"] = hop2
    built["hop3"] = hop3
    vector(
        "valid/blame-chain-receipts",
        "valid/blame-chain-receipts.awrb.json",
        "bundle",
        "valid",
        [],
        [],
        "L0",
        ["bundle", "chain", "three-hop", "support"],
        "The three-hop chain the blame attestation is about, verified on its own so that a "
        "failure in valid/blame-three-hop can be attributed to the blame document rather "
        "than to the receipts it references.",
        now=NOW,
    )
    vector(
        "valid/blame-three-hop",
        "valid/blame-three-hop.json",
        "document",
        "valid",
        [],
        [],
        None,
        ["blame", "section-3.5", "reachability", "three-hop"],
        "A BlameAttestation whose blamedWork is the deepest of three hops and is reachable "
        "from chain through two parents edges, with failureClass \"upstream-input\" -- the "
        "exoneration case. Section 3.5 requires a verifier that HAS the intermediate "
        "receipts to check reachability, so an implementation that skips the walk passes "
        "this and fails invalid/blame-unreachable-blamedwork.",
        now=NOW,
        supporting=["valid/blame-chain-receipts.awrb.json"],
    )

    # -- 12. verdict warnings ----------------------------------------------
    disagree = sign(
        envelope(
            verdict_subject(
                minimal,
                verdict="pass",
                score="0.50",
                policy={"threshold": "0.80"},
            ),
            VERIFIER_A,
            document_type="VerificationVerdict",
            issuer_name="example-verifier-a",
        ),
        VERIFIER_A,
    )
    write_json("valid/verdict-score-threshold-disagree.json", disagree)
    vector(
        "valid/verdict-score-threshold-disagree",
        "valid/verdict-score-threshold-disagree.json",
        "document",
        "valid",
        [],
        ["AWR-VDCT-006"],
        None,
        ["verdict", "section-3.4", "AWR-VDCT-006", "warning-not-error"],
        "verdict \"pass\" with score 0.50 under threshold 0.80. Section 3.4 keeps the "
        "issuer's stated verdict authoritative while requiring the inconsistency be "
        "reported, so both an implementation that ignores it and one that invalidates the "
        "document fail here -- and comparison MUST be decimal, not binary float.",
        now=NOW,
    )

    # -- 13. chain output/input mismatch warning ----------------------------
    transform_parent = work_receipt(
        subject=receipt_subject(
            inputDigest=SRI["prompt"],
            outputDigest=SRI["retrieved"],
            nonce="01J9Z8QK4T7YB2N5V6W8XA3E01",
        ),
        key=UPSTREAM,
        issuer_name="example-retrieval",
    )
    transform_child = work_receipt(
        subject=receipt_subject(
            inputDigest=SRI["tool-call"],
            outputDigest=SRI["summary"],
            parents=[dict(document_reference(transform_parent), role="retrieval")],
            nonce="01J9Z8QK4T7YB2N5V6W8XA3E02",
        ),
        issuer_name="example-hub",
    )
    write_json(
        "valid/chain-output-input-mismatch.awrb.json",
        make_bundle([transform_child, transform_parent]),
    )
    vector(
        "valid/chain-output-input-mismatch",
        "valid/chain-output-input-mismatch.awrb.json",
        "bundle",
        "valid",
        [],
        ["AWR-CHAIN-007"],
        "L0",
        ["bundle", "chain", "section-8.3", "AWR-CHAIN-007", "warning-not-error"],
        "A resolved edge whose parent outputDigest differs from the child inputDigest. "
        "Section 8.3 makes this a warning because a legitimate hop transforms its input; an "
        "implementation that hard-fails it rejects most real chains, and one that stays "
        "silent hides the case where a chain was re-pointed. This is the one vector that "
        "REQUIRES AWR-CHAIN-007, because section 8.3 makes performing the check a SHOULD: "
        "elsewhere the code is permitted, not demanded (see specFindings).",
        now=NOW,
    )

    # -- 14. time warnings --------------------------------------------------
    future = sign(
        envelope(
            receipt_subject(nonce="01J9Z8QK4T7YB2N5V6W8XA3F01"),
            HUB,
            issuer_name="example-hub",
            valid_from=FUTURE_VALID_FROM,
        ),
        HUB,
        created=FUTURE_VALID_FROM,
    )
    write_json("valid/receipt-validfrom-future.json", future)
    vector(
        "valid/receipt-validfrom-future",
        "valid/receipt-validfrom-future.json",
        "document",
        "valid",
        [],
        ["AWR-TIME-001"],
        "L0",
        ["receipt", "section-11.3", "AWR-TIME-001", "warning-not-error"],
        "validFrom five months after --now. Section 11.3 makes age policy rather than "
        "validity, so this MUST warn and MUST NOT invalidate; the legacy verifier's "
        "hard-fail on age (Appendix D) is what this catches.",
        now=NOW,
    )
    expired = sign(
        envelope(
            receipt_subject(nonce="01J9Z8QK4T7YB2N5V6W8XA3F02"),
            HUB,
            issuer_name="example-hub",
            valid_until=VALID_UNTIL_PAST,
        ),
        HUB,
    )
    write_json("valid/receipt-validuntil-past.json", expired)
    vector(
        "valid/receipt-validuntil-past",
        "valid/receipt-validuntil-past.json",
        "document",
        "valid",
        [],
        ["AWR-TIME-002"],
        "L0",
        ["receipt", "section-11.3", "AWR-TIME-002", "warning-not-error"],
        "validUntil one hour before --now, correctly later than validFrom. A verifier MUST "
        "warn and MUST still report the document valid: an audit is the main reason old "
        "receipts are read (section 11.3).",
        now=NOW,
    )

    # -- 15. proof array ----------------------------------------------------
    array_base = envelope(
        receipt_subject(nonce="01J9Z8QK4T7YB2N5V6W8XA3F03"),
        HUB,
        issuer_name="example-hub",
    )
    good_proof = sign(array_base, HUB)["proof"]
    stale_proof = sign(
        envelope(
            receipt_subject(nonce="a-different-nonce-entirely"),
            HUB,
            issuer_name="example-hub",
            document_id=array_base["id"],
        ),
        HUB,
    )["proof"]
    array_doc = dict(array_base)
    array_doc["proof"] = [stale_proof, good_proof]
    write_json("valid/receipt-proof-array.json", array_doc)
    vector(
        "valid/receipt-proof-array",
        "valid/receipt-proof-array.json",
        "document",
        "valid",
        [],
        [],
        "L0",
        ["receipt", "section-6.1", "proof-array", "spec-ambiguity"],
        "Two proofs, of which the first is a genuine signature over a DIFFERENT document "
        "and the second verifies. Section 6.1 says at least one proof MUST verify while "
        "every proof MUST be reported; this vector fixes the reading that the document is "
        "valid, which section 6.1 and section 11.1 together do not settle (see "
        "specFindings in index.json).",
        now=NOW,
    )

    # -- 16. explicit bundle subject ---------------------------------------
    other_receipt = work_receipt(
        subject=receipt_subject(nonce="01J9Z8QK4T7YB2N5V6W8XA3F04"),
        issuer_name="example-hub",
    )
    write_json(
        "valid/bundle-explicit-subject.awrb.json",
        make_bundle([minimal, other_receipt]),
    )
    vector(
        "valid/bundle-explicit-subject",
        "valid/bundle-explicit-subject.awrb.json",
        "bundle",
        "valid",
        [],
        [],
        "L0",
        ["bundle", "section-9", "explicit-subject"],
        "Two unrelated receipts in one bundle, disambiguated by the caller naming the "
        "subject. Section 9 requires the subject to come from an explicit argument or from "
        "the unreferenced-receipt rule and forbids guessing; the same file without "
        "--subject is invalid/bundle-ambiguous-subject, so the pair proves the "
        "implementation honours the argument instead of picking the first document.",
        now=NOW,
        subjectId=other_receipt["id"],
    )

    # -- 17. depth exactly at the limit ------------------------------------
    at_limit = build_depth_chain(DEPTH_LIMIT + 1)
    write_json("valid/chain-depth-at-limit.awrb.json", make_bundle(at_limit))
    vector(
        "valid/chain-depth-at-limit",
        "valid/chain-depth-at-limit.awrb.json",
        "bundle",
        "valid",
        [],
        [],
        "L0",
        ["bundle", "chain", "section-8.2", "boundary"],
        "A chain of exactly 65 receipts: depths 0..64, the deepest with no parents. "
        "Section 8.2's default maximum depth is 64, so this MUST resolve all 64 edges and "
        "MUST NOT report AWR-CHAIN-005. Paired with "
        "invalid/chain-depth-limit-exceeded it pins the off-by-one that every bounded walk "
        "gets wrong once.",
        now=NOW,
    )

    # -- 18. AWR/1 legacy, one per dialect ---------------------------------
    for dialect, tail in (("A", "integer-preserving"), ("B", "float-coercing")):
        legacy = legacy_document(dialect)
        name = "valid/awr1-legacy-dialect-%s.json" % (dialect.lower(),)
        write_json(name, legacy)
        vector(
            "valid/awr1-legacy-dialect-%s" % (dialect.lower(),),
            name,
            "document",
            "valid",
            [],
            ["AWR-LEGACY-001", "AWR-LEGACY-004"],
            None,
            ["legacy", "awr1", "section-12", "section-12.4", "AWR-LEGACY-004",
             "dialect-" + dialect, tail],
            "An AWR/1 document genuinely signed with the test key over the legacy "
            "pipe-delimited rendering of credentialSubject in dialect %s (%s: latencyMs "
            "2340 renders as %s). Section 12 requires both dialects be tried and either "
            "accepted, AWR-LEGACY-001 reported on every legacy document, and id/type/"
            "issuer/hubInfo never reported as attested -- they are outside this "
            "signature. AWR-LEGACY-004 is reported too (section 12.4): the key came from "
            "the document, which the AWR/1 signature does not cover, so valid: true here "
            "means the subject is signed by the key in legacy.verifiedKey and NOT that any "
            "named party attested anything."
            % (dialect, tail, "2340" if dialect == "A" else "2340.0"),
            now=NOW,
            note="Signed by reaching for a raw Ed25519 signer over "
            "legacy_canonical_form(credentialSubject, %r). Section 12 forbids an "
            "implementation from ISSUING AWR/1, so the reference has no code path that "
            "produces this document; the vector exists only so verifiers can be tested."
            % (dialect,),
        )

    return built


def build_depth_chain(count: int, *, tag: str = "") -> List[Dict[str, Any]]:
    """A linear chain of *count* receipts, deepest first in the returned list."""
    documents: List[Dict[str, Any]] = []
    previous: Optional[Dict[str, Any]] = None
    for index in range(count):
        subject = receipt_subject(
            work={
                "modelId": "chain-hop-%d@example" % (index,),
                "completedAt": COMPLETED_AT,
                "status": "succeeded",
            },
            inputDigest=SRI["retrieved"],
            outputDigest=SRI["retrieved"],
            nonce="chain%s-%04d" % (tag, index),
        )
        if previous is not None:
            subject["parents"] = [dict(document_reference(previous), role="subagent")]
        document = work_receipt(subject=subject, issuer_name="example-hub")
        documents.append(document)
        previous = document
    documents.reverse()  # shallowest (the subject) first, per section 9's SHOULD
    return documents


def legacy_document(dialect: str, *, break_signature: bool = False) -> Dict[str, Any]:
    """An AWR/1 document (section 12), signed over the legacy rendering.

    The ``issuer.id`` reproduces the exact legacy defect Appendix D records: ``did:key:``
    followed by the first 32 characters of the base64 public key, which is not a DID and
    names no key -- which is why the real key has to be embedded as ``publicKeyJwk``.
    """
    subject = {
        "work": {
            "modelId": "legacy-model@vendor",
            "startedAt": "2026-01-15T08:59:58Z",
            "completedAt": LEGACY_COMPLETED,
            "latencyMs": 2340,
            "status": "succeeded",
        },
        "inputDigest": SRI["prompt"],
        "outputDigest": SRI["summary"],
        "price": {"currency": "USD", "amount": "0.15"},
    }
    signed_bytes = legacy_canonical_form(subject, dialect)
    signature = HUB.sign(signed_bytes)
    broken_did = "did:key:" + base64.b64encode(HUB.public_key_bytes).decode("ascii")[:32]
    document: Dict[str, Any] = {
        "@context": ["https://www.w3.org/2018/credentials/v1"],
        "id": "urn:uuid:%08x-1e6a-4c11-8f00-000000000000" % (ord(dialect),),
        "type": ["VerifiableCredential", "WorkReceipt"],
        "issuer": {
            "id": broken_did,
            "name": "legacy-hub",
            "publicKeyJwk": HUB.public_key_jwk(),
        },
        "issuanceDate": LEGACY_CREATED,
        "hubInfo": {"version": "1.4.2", "region": "eu-central-1"},
        "credentialSubject": copy.deepcopy(subject),
        "proof": {
            "type": "Ed25519Signature2018",
            "created": LEGACY_CREATED,
            "verificationMethod": broken_did + "#key-1",
            "proofPurpose": "assertionMethod",
            "proofValue": base64.b64encode(signature).decode("ascii"),
        },
    }
    if break_signature:
        # A field added after signing: outside neither dialect's rendering, so both fail.
        document["credentialSubject"]["nonce"] = "added-after-the-signature"
    return document


# ---------------------------------------------------------------------------
# invalid vectors
# ---------------------------------------------------------------------------

#: Nothing, now, and deliberately named rather than deleted.
#:
#: These vectors used to permit AWR-PROOF-006 alongside the AWR-KEY-* / AWR-DOC-010 code,
#: because section 6.3 ordered key derivation (step 3) before signature verification (step
#: 6) without saying what to report when step 3 makes step 6 impossible, and the registry
#: has no code for "the signature was not checked".  Three implementations split three ways
#: on exactly these six documents.  Section 6.3 now settles it: AWR-PROOF-006 means the
#: signature was checked and did not verify, and when an earlier step prevented the check
#: that step's code is the report and PROOF-006 MUST NOT be added.  The permission is
#: therefore withdrawn -- an implementation that still reports PROOF-006 here fails, which
#: is the point of closing an ambiguity rather than documenting it.
KEY_UNAVAILABLE_EXTRA: List[str] = []

SENTINEL_NON_INTEGER = "@@AWR-NON-INTEGER@@"
SENTINEL_BIG_INTEGER = "@@AWR-BIG-INTEGER@@"
SENTINEL_JSON_NUMBER = "@@AWR-JSON-NUMBER@@"
SENTINEL_SURROGATE = "@@AWR-LONE-SURROGATE@@"


def build_invalid(built: Dict[str, Any]) -> None:
    minimal = built["minimal"]

    def emit(
        name: str,
        document: Any,
        vid_tail: str,
        codes: Sequence[str],
        warnings: Sequence[str],
        tags: Sequence[str],
        why: str,
        *,
        kind: str = "document",
        text: Optional[str] = None,
        ascii_only: bool = False,
        **extra: Any
    ) -> None:
        relative = "invalid/%s" % (name,)
        if text is not None:
            write_text(relative, text)
        else:
            write_json(relative, document, ascii_only=ascii_only)
        vector(
            "invalid/%s" % (vid_tail,),
            relative,
            kind,
            "invalid",
            codes,
            warnings,
            extra.pop("profile", None),
            tags,
            why,
            now=NOW,
            **extra
        )

    # ---- section 3.1 envelope (AWR-DOC-*) --------------------------------

    emit(
        "doc-not-an-object.json",
        [copy.deepcopy(minimal)],
        "doc-not-an-object",
        ["AWR-DOC-001"],
        [],
        ["envelope", "AWR-DOC-001"],
        "A JSON array wrapping an otherwise valid receipt. An AWR document is a JSON "
        "object (section 3.1); an implementation that iterates whatever it is handed "
        "reports the inner document as valid and attributes claims to an issuer that "
        "signed nothing at this level.",
    )
    emit(
        "context-first-not-vc.json",
        sign(
            envelope(
                receipt_subject(),
                HUB,
                issuer_name="example-hub",
                context=[AWR_CONTEXT, VC_CONTEXT],
            ),
            HUB,
        ),
        "context-first-not-vc",
        ["AWR-DOC-002"],
        [],
        ["envelope", "AWR-DOC-002", "section-3.1"],
        "Both required context URIs are present but in the wrong order. Section 3.1 pins "
        "the FIRST element to the VC 2.0 context; an implementation that only tests "
        "membership accepts a document that is not a VC 2.0 credential, and JSON-LD "
        "processors resolve its terms differently.",
    )
    emit(
        "context-missing-awr-namespace.json",
        sign(
            envelope(
                receipt_subject(),
                HUB,
                issuer_name="example-hub",
                context=[VC_CONTEXT, "https://example.org/ns/other/v1"],
            ),
            HUB,
        ),
        "context-missing-awr-namespace",
        ["AWR-DOC-003"],
        [],
        ["envelope", "AWR-DOC-003", "section-3.1"],
        "The AWR namespace is absent from @context, so the document does not claim to be "
        "an AWR credential even though its type says WorkReceipt. Accepting it lets any "
        "VC with a colliding type name be read as a receipt.",
    )
    emit(
        "type-missing-verifiable-credential.json",
        sign(
            envelope(
                receipt_subject(),
                HUB,
                issuer_name="example-hub",
                types=["WorkReceipt"],
            ),
            HUB,
        ),
        "type-missing-verifiable-credential",
        ["AWR-DOC-004"],
        [],
        ["envelope", "AWR-DOC-004", "section-3.1"],
        "type omits VerifiableCredential, so off-the-shelf VC tooling would not treat the "
        "document as a credential at all while an AWR-only verifier would -- exactly the "
        "divergence section 16's \"AWR documents ARE VCs\" claim depends on not existing.",
    )
    emit(
        "type-two-awr-types.json",
        sign(
            envelope(
                receipt_subject(),
                HUB,
                issuer_name="example-hub",
                types=["VerifiableCredential", "WorkReceipt", "VerificationVerdict"],
            ),
            HUB,
        ),
        "type-two-awr-types",
        ["AWR-DOC-005"],
        [],
        ["envelope", "AWR-DOC-005", "section-3.1"],
        "Two AWR types in one document. Section 3.1 requires exactly one, because which "
        "subject schema applies -- and therefore which claims a verifier reports -- would "
        "otherwise depend on the order the implementation happens to check.",
    )
    emit(
        "id-not-absolute-uri.json",
        sign(
            envelope(
                receipt_subject(),
                HUB,
                issuer_name="example-hub",
                document_id="receipt-42",
            ),
            HUB,
        ),
        "id-not-absolute-uri",
        ["AWR-DOC-006"],
        [],
        ["envelope", "AWR-DOC-006", "section-3.1"],
        "A relative identifier. Section 3.1 requires an absolute URI because id is a "
        "binding statement inside the signature and is what chain edges and verdicts "
        "name; a relative id means two documents in different contexts can claim the same "
        "identity.",
    )
    emit(
        "validfrom-offset-not-z.json",
        sign(
            envelope(
                receipt_subject(),
                HUB,
                issuer_name="example-hub",
                valid_from="2026-07-31T12:15:30+02:00",
            ),
            HUB,
            created="2026-07-31T10:15:30Z",
        ),
        "validfrom-offset-not-z",
        ["AWR-DOC-007"],
        [],
        ["envelope", "AWR-DOC-007", "section-3.1", "rfc3339"],
        "validFrom carries a +02:00 offset instead of Z. Section 3.1 requires UTC with a Z, "
        "so that timestamps are comparable as strings as well as instants; a verifier that "
        "accepts any RFC 3339 offset silently admits documents whose ordering depends on "
        "the reader's timezone library.",
    )
    emit(
        "validuntil-not-after-validfrom.json",
        sign(
            envelope(
                receipt_subject(),
                HUB,
                issuer_name="example-hub",
                valid_until=VALID_FROM,
            ),
            HUB,
        ),
        "validuntil-not-after-validfrom",
        ["AWR-DOC-007"],
        ["AWR-TIME-002"],
        ["envelope", "AWR-DOC-007", "section-3.1"],
        "validUntil equal to validFrom, i.e. a document that was never valid. Section 3.1 "
        "requires validUntil to be strictly later. The AWR-TIME-002 warning rides along "
        "because the instant is also in the past, which is a warning and never the reason "
        "for invalidity (section 11.3).",
    )
    subject_array_doc = envelope(receipt_subject(), HUB, issuer_name="example-hub")
    subject_array_doc["credentialSubject"] = [receipt_subject()]
    emit(
        "credentialsubject-array.json",
        sign(subject_array_doc, HUB),
        "credentialsubject-array",
        ["AWR-DOC-008"],
        [],
        ["envelope", "AWR-DOC-008", "section-3.1"],
        "credentialSubject as a one-element array, which VC 2.0 permits and AWR/2 does "
        "not. An implementation that follows VC 2.0 here reads subject fields from "
        "subject[0], and no field of section 3.3 is then where the spec says it is.",
    )
    emit(
        "awrversion-major-1.json",
        sign(
            envelope(
                receipt_subject(),
                HUB,
                issuer_name="example-hub",
                awr_version="1.4.2",
            ),
            HUB,
        ),
        "awrversion-major-1",
        ["AWR-DOC-009"],
        [],
        ["envelope", "AWR-DOC-009", "section-3.1", "version-downgrade"],
        "awrVersion 1.4.2 inside a document otherwise shaped like AWR/2. Section 3.1 "
        "requires rejecting a major version the verifier does not implement; because "
        "awrVersion is inside the signed bytes, an implementation that ignores it lets a "
        "document be re-interpreted under another version's rules by whoever forwards it.",
    )
    emit(
        "issuer-bare-string.json",
        sign(
            envelope(
                receipt_subject(),
                HUB,
                issuer_name="example-hub",
                issuer=HUB.did,
            ),
            HUB,
        ),
        "issuer-bare-string",
        ["AWR-DOC-010"],
        [],
        ["envelope", "AWR-DOC-010", "section-3.1"],
        "A bare-string issuer, legal in VC 2.0 and rejected in AWR/2 so that issuer.name "
        "has exactly one place to live. An implementation that accepts both forms has two "
        "canonical shapes for the same claim and two places a name can hide.",
        allowedExtraCodes=KEY_UNAVAILABLE_EXTRA,
    )

    # ---- section 4 canonicalization (AWR-CANON-*) -------------------------

    non_integer = sign(
        envelope(
            receipt_subject(
                work={
                    "modelId": "claude-sonnet-5@anthropic",
                    "completedAt": COMPLETED_AT,
                    "status": "succeeded",
                    "latencyMs": SENTINEL_NON_INTEGER,
                }
            ),
            HUB,
            issuer_name="example-hub",
        ),
        HUB,
    )
    emit(
        "number-non-integer.json",
        None,
        "number-non-integer",
        ["AWR-CANON-001"],
        [],
        ["canonicalization", "AWR-CANON-001", "section-4.3", "numbers"],
        "work.latencyMs is 2340.5. Section 4.3 forbids non-integer JSON numbers outright "
        "rather than arbitrating them, because implementations disagree on their canonical "
        "form silently -- the signature verifies in one language and fails in another. "
        "Rejection MUST happen at the number, not at the signature.",
        text=json_text(non_integer).replace('"%s"' % SENTINEL_NON_INTEGER, "2340.5"),
        # 2340.5 is also not the non-negative integer section 3.3 requires, so an
        # implementation whose parser can carry the value to the subject validator
        # determines AWR-RCPT-004 as well and section 11.1 tells it to report that.  The
        # reference cannot: parsing aborts at the number.  See specFindings.
        allowedExtraCodes=["AWR-RCPT-004"],
        note="The proof is a genuine signature over the same document with latencyMs = "
        '"%s"; a document containing 2340.5 cannot be canonicalized at all, so no '
        "signature over it can exist. The defect aborts parsing long before the "
        "signature is reached." % (SENTINEL_NON_INTEGER,),
    )

    integral_float = sign(
        envelope(
            receipt_subject(
                work={
                    "modelId": "claude-sonnet-5@anthropic",
                    "completedAt": COMPLETED_AT,
                    "status": "succeeded",
                    "latencyMs": SENTINEL_NON_INTEGER,
                }
            ),
            HUB,
            issuer_name="example-hub",
        ),
        HUB,
    )
    emit(
        "number-integer-valued-float.json",
        None,
        "number-integer-valued-float",
        ["AWR-CANON-001"],
        [],
        ["canonicalization", "AWR-CANON-001", "section-4.3", "numbers", "awr1-dialects"],
        "work.latencyMs is 2340.0 -- the exact divergence that split AWR/1 into two "
        "incompatible dialects (section 12, Appendix D). Section 4.3 forbids the LITERAL, "
        "not the value, so this is AWR-CANON-001 even though 2340.0 denotes a whole "
        "number. An implementation that checks after parsing cannot see it: an IEEE-754 "
        "double parses 2340 and 2340.0 to the same value, so it accepts the document, "
        "canonicalizes it to 2340, and verifies a signature over bytes the issuer never "
        "produced. The browser verifier did exactly that until this vector existed.",
        text=json_text(integral_float).replace('"%s"' % SENTINEL_NON_INTEGER, "2340.0"),
        # As for number-non-integer: 2340.0 is not the integer section 3.3 requires either,
        # so an implementation whose parser carries the value to the subject validator
        # determines AWR-RCPT-004 as well, which section 11.1 permits.  AWR-CANON-001 stays
        # required, so an implementation that reports only the field error still fails.
        allowedExtraCodes=["AWR-RCPT-004"],
        note="The proof is a genuine signature over the same document with latencyMs = "
        '"%s". No conformant issuer can produce 2340.0, so no signature over this text '
        "exists; the point of the vector is that the document is rejected at the number "
        "and never reaches a signature check." % (SENTINEL_NON_INTEGER,),
    )

    big_integer = sign(
        envelope(
            receipt_subject(
                work={
                    "modelId": "claude-sonnet-5@anthropic",
                    "completedAt": COMPLETED_AT,
                    "status": "succeeded",
                    "latencyMs": SENTINEL_BIG_INTEGER,
                }
            ),
            HUB,
            issuer_name="example-hub",
        ),
        HUB,
    )
    emit(
        "number-integer-2pow53.json",
        None,
        "number-integer-2pow53",
        ["AWR-CANON-002"],
        [],
        ["canonicalization", "AWR-CANON-002", "section-4.3", "boundary"],
        "work.latencyMs is 9007199254740992 = 2^53, the first integer outside section "
        "4.3's closed range. 2^53-1 appears in canonicalization/numbers-integer-bounds and "
        "MUST be accepted, so the pair pins the boundary: an implementation whose parser "
        "stores integers as doubles reads this value as 9007199254740992.0 and cannot "
        "notice.",
        text=json_text(big_integer).replace(
            '"%s"' % SENTINEL_BIG_INTEGER, "9007199254740992"
        ),
        # As for number-non-integer: an implementation that carries the value past the
        # parser also determines that latencyMs is not a permitted integer.
        allowedExtraCodes=["AWR-RCPT-004"],
        note="The proof is a genuine signature over the same document with latencyMs = "
        '"%s"; 2^53 cannot be canonicalized under section 4.3, so no signature over it '
        "can exist." % (SENTINEL_BIG_INTEGER,),
    )

    surrogate = sign(
        envelope(
            receipt_subject(nonce=SENTINEL_SURROGATE),
            HUB,
            issuer_name="example-hub",
        ),
        HUB,
    )
    emit(
        "string-lone-surrogate.json",
        None,
        "string-lone-surrogate",
        ["AWR-CANON-003"],
        [],
        ["canonicalization", "AWR-CANON-003", "section-4.1", "unicode"],
        "nonce contains the escape \\ud800, a lone high surrogate that is not valid "
        "Unicode. Section 4.1 item 4 requires the implementation to terminate with an "
        "error and forbids substituting U+FFFD: a replacement character would change the "
        "bytes under the signature while reporting success.",
        text=json_text(surrogate, ascii_only=True).replace(
            SENTINEL_SURROGATE, "lone-\\ud800-surrogate"
        ),
        note="The proof is a genuine signature over the same document with nonce = "
        '"%s". A document containing a lone surrogate has no canonical form, so the '
        "signature cannot be checked at all: section 6.3 requires the AWR-CANON-003 code "
        "and forbids adding AWR-PROOF-006, which would claim a check that never ran. The "
        "reference used to report both and two other implementations reported only one "
        "each; the permission that hid that is withdrawn." % (SENTINEL_SURROGATE,),
    )

    duplicate_text = json_text(minimal)
    marker = '  "awrVersion": "2.0.0",\n'
    if marker not in duplicate_text:  # pragma: no cover
        raise SystemExit("cannot place the duplicate key: envelope layout changed")
    emit(
        "duplicate-json-keys.json",
        None,
        "duplicate-json-keys",
        ["AWR-CANON-004"],
        [],
        ["canonicalization", "AWR-CANON-004", "section-4.1", "parser-decides"],
        "The member \"awrVersion\" appears twice, as \"2.0.0\" and then \"9.9.9\". Section "
        "4.1 item 5 requires rejection because a parser that keeps the last (or the first) "
        "occurrence would decide which bytes were signed -- and the two readings disagree "
        "about which specification the document claims to follow.",
        text=duplicate_text.replace(marker, marker + '  "awrVersion": "9.9.9",\n', 1),
        note="Written as raw text: no JSON serializer can emit a duplicate member, which "
        "is precisely why implementations forget the case exists.",
    )

    malformed_text = json_text(minimal)
    emit(
        "not-well-formed-json.json",
        None,
        "not-well-formed-json",
        ["AWR-CANON-005"],
        [],
        ["canonicalization", "AWR-CANON-005", "trailing-comma"],
        "A trailing comma after the final member. It is the most common way a hand-edited "
        "receipt arrives, several parsers accept it as an extension, and section 4 has no "
        "canonical form for text that is not JSON.",
        text=malformed_text.rstrip("\n")[:-1].rstrip() + ",\n}\n",
        note="Written as raw text: the bytes are valid/receipt-minimal-l0.json with a comma "
        "appended after its final member, so the proof is that document's genuine "
        "signature. No JSON serializer can emit the trailing comma.",
    )

    # ---- section 5 keys (AWR-KEY-*) --------------------------------------

    https_issuer = "https://hub.example/issuers/1"
    emit(
        "issuer-not-did-key.json",
        sign(
            envelope(
                receipt_subject(),
                HUB,
                issuer_name="example-hub",
                issuer={"id": https_issuer, "name": "example-hub"},
            ),
            HUB,
            proof_extra={"verificationMethod": https_issuer + "#key-1"},
        ),
        "issuer-not-did-key",
        ["AWR-KEY-001"],
        [],
        ["keys", "AWR-KEY-001", "section-5.1", "no-network"],
        "An HTTPS issuer identifier. Section 5.1 supports only did:key in AWR/2 because "
        "every other identifier makes verification depend on a network lookup; an "
        "implementation that resolves this URL has abandoned offline verification and "
        "section 13.5.",
        allowedExtraCodes=KEY_UNAVAILABLE_EXTRA,
    )

    truncated_did = (
        "did:key:" + base64.b64encode(VERIFIER_A.public_key_bytes).decode("ascii")[:32]
    )
    emit(
        "didkey-base64-truncation.json",
        sign(
            envelope(
                receipt_subject(),
                VERIFIER_A,
                issuer={"id": truncated_did, "name": "legacy-shaped-issuer"},
            ),
            VERIFIER_A,
            proof_extra={
                "verificationMethod": truncated_did
                + "#"
                + truncated_did[len("did:key:") :]
            },
        ),
        "didkey-base64-truncation",
        ["AWR-KEY-002"],
        [],
        ["keys", "AWR-KEY-002", "section-5.1", "legacy-defect", "appendix-d"],
        "The exact AWR/1 defect Appendix D records: issuer.id is did:key: followed by the "
        "first 32 characters of the base64 public key. It is not multibase, it is not a "
        "DID, and it names no key -- so a verifier cannot derive a public key from it and "
        "MUST NOT fall back to a key embedded elsewhere in the document.",
        allowedExtraCodes=KEY_UNAVAILABLE_EXTRA,
    )

    short_did = "did:key:" + multibase_encode_base58btc(
        b"\xed\x01" + HUB.public_key_bytes[:31]
    )
    emit(
        "didkey-wrong-key-length.json",
        sign(
            envelope(
                receipt_subject(),
                HUB,
                issuer={"id": short_did, "name": "example-hub"},
            ),
            HUB,
            proof_extra={
                "verificationMethod": short_did + "#" + short_did[len("did:key:") :]
            },
        ),
        "didkey-wrong-key-length",
        ["AWR-KEY-002"],
        [],
        ["keys", "AWR-KEY-002", "section-5.1", "length-check"],
        "Well-formed multibase base58btc with the correct ed25519-pub multicodec and only "
        "31 key bytes. Section 5.1 requires the length check as well as the multicodec "
        "check; an implementation that slices the first 32 bytes after the prefix, or that "
        "trusts base58 decoding to produce the right length, derives a key from padding.",
        allowedExtraCodes=KEY_UNAVAILABLE_EXTRA,
    )

    emit(
        "publickeyjwk-different-key.json",
        sign(
            envelope(
                receipt_subject(),
                HUB,
                issuer={
                    "id": HUB.did,
                    "name": "example-hub",
                    "publicKeyJwk": VERIFIER_A.public_key_jwk(),
                },
            ),
            HUB,
        ),
        "publickeyjwk-different-key",
        ["AWR-KEY-003"],
        [],
        ["keys", "AWR-KEY-003", "section-5.2", "downgrade"],
        "issuer.publicKeyJwk names verifierA's key while issuer.id names the hub's, and "
        "the signature is the hub's. Section 5.2 makes the mismatch invalidate the "
        "document: two disagreeing statements of the signing key inside one signed "
        "document is a downgrade surface, and an implementation that prefers the JWK can "
        "be steered to a key of the attacker's choosing.",
    )

    x25519_did = "did:key:" + multibase_encode_base58btc(
        b"\xec\x01" + HUB.public_key_bytes
    )
    emit(
        "didkey-x25519.json",
        sign(
            envelope(
                receipt_subject(),
                HUB,
                issuer={"id": x25519_did, "name": "example-hub"},
            ),
            HUB,
            proof_extra={
                "verificationMethod": x25519_did + "#" + x25519_did[len("did:key:") :]
            },
        ),
        "didkey-x25519",
        ["AWR-KEY-004"],
        [],
        ["keys", "AWR-KEY-004", "section-5.1", "multicodec"],
        "A structurally valid did:key whose multicodec is x25519-pub (0xec 0x01) over the "
        "same 32 bytes. An implementation that ignores the multicodec and takes the "
        "trailing 32 bytes as an Ed25519 key verifies a signature under a key type that "
        "cannot make signatures at all.",
        allowedExtraCodes=KEY_UNAVAILABLE_EXTRA,
    )

    # ---- section 6 proof (AWR-PROOF-*) -----------------------------------

    stripped = {k: v for k, v in copy.deepcopy(minimal).items() if k != "proof"}
    emit(
        "proof-stripped.json",
        stripped,
        "proof-stripped",
        ["AWR-PROOF-001"],
        [],
        ["proof", "AWR-PROOF-001", "section-6.1"],
        "The proof was removed and everything else left intact. An unsecured document is "
        "indistinguishable from a secured one by content alone, so an implementation that "
        "reports validity when there is nothing to check turns section 13.7's "
        "\"attribution\" into decoration.",
    )
    emit(
        "proof-type-not-dataintegrityproof.json",
        sign(
            envelope(receipt_subject(), HUB, issuer_name="example-hub"),
            HUB,
            proof_extra={"type": "Ed25519Signature2020"},
        ),
        "proof-type-not-dataintegrityproof",
        ["AWR-PROOF-002"],
        [],
        ["proof", "AWR-PROOF-002", "section-6.1"],
        "proof.type is Ed25519Signature2020 while the bytes are an eddsa-jcs-2022 "
        "signature that genuinely verifies. Section 6.1 pins the type; an implementation "
        "that dispatches on cryptosuite alone accepts a proof whose containing suite says "
        "the transformation was something else.",
    )
    emit(
        "proof-cryptosuite-unsupported.json",
        sign(
            envelope(receipt_subject(), HUB, issuer_name="example-hub"),
            HUB,
            proof_extra={"cryptosuite": "eddsa-rdfc-2022"},
        ),
        "proof-cryptosuite-unsupported",
        ["AWR-PROOF-003"],
        [],
        ["proof", "AWR-PROOF-003", "section-6.4", "agility"],
        "cryptosuite eddsa-rdfc-2022, a real W3C suite over RDF canonicalization, with an "
        "otherwise valid JCS signature. Section 6.4 requires unknown suites be REJECTED "
        "rather than skipped: an implementation that ignores the field verifies JCS bytes "
        "while the document claims RDF ones, and the two disagree for exactly the "
        "documents an attacker cares about.",
    )
    emit(
        "proof-purpose-authentication.json",
        sign(
            envelope(receipt_subject(), HUB, issuer_name="example-hub"),
            HUB,
            purpose="authentication",
        ),
        "proof-purpose-authentication",
        ["AWR-PROOF-004"],
        [],
        ["proof", "AWR-PROOF-004", "section-6.1", "purpose-confusion"],
        "proofPurpose is authentication, so the signature is a genuine authentication "
        "proof presented as an assertion. Accepting it lets a signature made to prove "
        "control of a key be replayed as a claim about work.",
    )
    base64_doc = copy.deepcopy(minimal)
    signature_bytes = multibase_decode_base58btc(minimal["proof"]["proofValue"])
    base64_doc["proof"] = dict(minimal["proof"])
    base64_doc["proof"]["proofValue"] = base64.b64encode(signature_bytes).decode("ascii")
    emit(
        "proofvalue-base64.json",
        base64_doc,
        "proofvalue-base64",
        ["AWR-PROOF-005"],
        [],
        ["proof", "AWR-PROOF-005", "section-6.1", "legacy-encoding"],
        "The identical 64-byte signature re-encoded as standard base64 instead of "
        "multibase base58btc -- the AWR/1 encoding. Section 6.1 requires rejecting it "
        "explicitly: an implementation that sniffs the encoding accepts a legacy proof as "
        "a current one, and multibase exists so that the encoding is never guessed.",
    )

    tampered_id = copy.deepcopy(minimal)
    tampered_id["id"] = "urn:uuid:deadbeef-a11c-4f38-9b8a-1c2d3e4f5a6b"
    emit(
        "tampered-id.json",
        tampered_id,
        "tampered-id",
        ["AWR-PROOF-006"],
        [],
        ["proof", "AWR-PROOF-006", "section-13.1", "awr1-attack"],
        "valid/receipt-minimal-l0 with only its id rewritten. This is THE attack whole-"
        "document signing closes: in AWR/1 id was outside the signature while parents "
        "referenced ids, so an intermediary could rename a valid receipt and re-point a "
        "chain at it without breaking any signature. An implementation that canonicalizes "
        "only credentialSubject reports this document valid.",
    )
    tampered_issuer = copy.deepcopy(minimal)
    tampered_issuer["issuer"] = dict(tampered_issuer["issuer"])
    tampered_issuer["issuer"]["name"] = "trusted-national-audit-office"
    emit(
        "tampered-issuer-name.json",
        tampered_issuer,
        "tampered-issuer-name",
        ["AWR-PROOF-006"],
        [],
        ["proof", "AWR-PROOF-006", "section-13.1", "issuer-name"],
        "Only issuer.name was rewritten, to something a human would trust. Section 3.1 "
        "gives name no trust weight and section 13.1 puts it inside the signature anyway, "
        "because a name outside the signature is a name any intermediary can choose -- and "
        "it is the field a user interface actually shows.",
    )

    swapped_base = envelope(
        receipt_subject(nonce="01J9Z8QK4T7YB2N5V6W8XA3G01"),
        HUB,
        issuer_name="example-hub",
    )
    swapped_proof_options = {
        "type": "DataIntegrityProof",
        "cryptosuite": "eddsa-jcs-2022",
        "created": VALID_FROM,
        "verificationMethod": HUB.verification_method,
        "proofPurpose": "assertionMethod",
    }
    unsecured = unsecured_document(swapped_base)
    config = proof_config(swapped_proof_options, unsecured)
    proof_config_hash, transformed_hash, correct = hash_data(unsecured, config)
    reversed_hash_data = transformed_hash + proof_config_hash
    if reversed_hash_data == correct:  # pragma: no cover
        raise SystemExit("the two halves are equal; pick a different document")
    swapped = dict(unsecured)
    swapped["proof"] = dict(swapped_proof_options)
    swapped["proof"]["proofValue"] = encode_proof_value(HUB.sign(reversed_hash_data))
    emit(
        "hashdata-halves-swapped.json",
        swapped,
        "hashdata-halves-swapped",
        ["AWR-PROOF-006"],
        [],
        ["proof", "AWR-PROOF-006", "section-6.2", "interop-classic"],
        "A genuine signature over SHA-256(transformedDocument) || "
        "SHA-256(canonicalProofConfig) -- the two halves of hashData in the wrong order. "
        "Section 6.2 step 6 puts the proof config FIRST and calls this the most frequent "
        "Data Integrity interoperability error; both halves are 32 bytes, so nothing "
        "structural catches it and an implementation that got the order wrong verifies "
        "this file and rejects every correct one.",
        note="proofConfigHash = %s, transformedDocumentHash = %s; the signature is over "
        "the concatenation in reverse order. awr/vectors/proof/worked-example.json "
        "records the same three values for a correct signature so a failing "
        "implementation can be localised to one step."
        % (proof_config_hash.hex(), transformed_hash.hex()),
    )

    other_vm = VERIFIER_A.verification_method
    emit(
        "verificationmethod-other-key.json",
        sign(
            envelope(receipt_subject(), HUB, issuer_name="example-hub"),
            HUB,
            proof_extra={"verificationMethod": other_vm},
        ),
        "verificationmethod-other-key",
        ["AWR-PROOF-007"],
        [],
        ["proof", "AWR-PROOF-007", "section-5.3", "key-selection"],
        "verificationMethod names verifierA's key while issuer.id names the hub's, and the "
        "hub's signature verifies. Section 5.3 pins verificationMethod to "
        "<issuer.id>#<method-specific-id> so that a verifier never CHOOSES a key; an "
        "implementation that resolves verificationMethod instead reports a document as "
        "issued by the hub and verified under someone else's key.",
    )
    emit(
        "proof-context-mismatch.json",
        sign(
            envelope(receipt_subject(), HUB, issuer_name="example-hub"),
            HUB,
            proof_extra={"@context": [VC_CONTEXT]},
        ),
        "proof-context-mismatch",
        ["AWR-PROOF-008"],
        [],
        ["proof", "AWR-PROOF-008", "section-6.2"],
        "The serialized proof carries its own @context, missing the AWR namespace, while "
        "section 6.2 step 1 requires the proof options to be canonicalized under the "
        "document's @context. The signature still verifies -- the proof config takes the "
        "document's context -- so only an explicit consistency check catches a proof that "
        "claims a different term set than the document it secures.",
    )
    emit(
        "proof-created-malformed.json",
        sign(
            envelope(receipt_subject(), HUB, issuer_name="example-hub"),
            HUB,
            proof_extra={"created": "31 July 2026 10:15:30 UTC"},
        ),
        "proof-created-malformed",
        ["AWR-PROOF-009"],
        [],
        ["proof", "AWR-PROOF-009", "section-6.1", "rfc3339"],
        "proof.created is a human-readable date, signed as such. Section 6.1 requires an "
        "RFC 3339 UTC date-time; an implementation that never parses created cannot report "
        "when a signature claims to have been made, which is the one temporal fact a "
        "re-signed historical document would have to lie about (section 12).",
    )

    # ---- section 3.3 receipt (AWR-RCPT-*) --------------------------------

    no_output = receipt_subject()
    del no_output["outputDigest"]
    emit(
        "outputdigest-missing.json",
        sign(envelope(no_output, HUB, issuer_name="example-hub"), HUB),
        "outputdigest-missing",
        ["AWR-RCPT-001"],
        [],
        ["receipt", "AWR-RCPT-001", "section-3.3"],
        "outputDigest is absent. Section 3.3 requires it even when status is not "
        "succeeded, because a receipt with no output digest cannot be attached to the "
        "artefact it produced and a dispute has nothing to compare.",
    )
    emit(
        "outputdigest-base64url.json",
        sign(
            envelope(
                receipt_subject(
                    outputDigest=SRI["summary"].replace("+", "-").replace("/", "_")
                ),
                HUB,
                issuer_name="example-hub",
            ),
            HUB,
        ),
        "outputdigest-base64url",
        ["AWR-RCPT-001"],
        [],
        ["receipt", "AWR-RCPT-001", "section-3.2", "sri-alphabet"],
        "The correct digest of the correct payload, encoded base64url instead of the "
        "standard +/ alphabet W3C SRI requires. Accepting a second spelling of the same "
        "value means two documents with different signed bytes make the same claim, and "
        "chain edges stop being comparable by string equality.",
    )
    emit(
        "outputdigest-sha512.json",
        sign(
            envelope(
                receipt_subject(outputDigest="sha512-" + SRI["summary"][len("sha256-") :]),
                HUB,
                issuer_name="example-hub",
            ),
            HUB,
        ),
        "outputdigest-sha512",
        ["AWR-RCPT-001"],
        [],
        ["receipt", "AWR-RCPT-001", "section-3.2", "algorithm", "spec-ambiguity"],
        "A sha512- prefix on a bare SRI field. sha256 is the only algorithm AWR/2 defines, "
        "and a verifier MUST report rather than ignore the reference. Section 3.2 names "
        "AWR-CHAIN-002 for a digest REFERENCE while section 11.2 gives the bare "
        "input/outputDigest fields AWR-RCPT-001; this vector fixes AWR-RCPT-001 for the "
        "bare fields (see specFindings in index.json) and "
        "invalid/parents-digest-sha512 fixes AWR-CHAIN-002 for reference objects.",
    )
    emit(
        "price-amount-json-number.json",
        sign(
            envelope(
                receipt_subject(price={"currency": "USD", "amount": 15}),
                HUB,
                issuer_name="example-hub",
            ),
            HUB,
        ),
        "price-amount-json-number",
        ["AWR-RCPT-002"],
        [],
        ["receipt", "AWR-RCPT-002", "section-4.3", "decimal-string"],
        "price.amount is the JSON number 15, not the string \"15\". Section 3.3 requires a "
        "decimal string and section 4.3 explains why: money that is a JSON number is money "
        "whose canonical form depends on the language. An integer amount is the case that "
        "slips through, because it parses and canonicalizes cleanly -- only the type check "
        "catches it.",
    )
    price_float = sign(
        envelope(
            receipt_subject(price={"currency": "USD", "amount": SENTINEL_JSON_NUMBER}),
            HUB,
            issuer_name="example-hub",
        ),
        HUB,
    )
    emit(
        "price-amount-json-float.json",
        None,
        "price-amount-json-float",
        ["AWR-CANON-001"],
        [],
        ["receipt", "AWR-CANON-001", "section-4.3", "decimal-string"],
        "price.amount is the JSON number 0.15. The interesting part is which code fires: "
        "section 4.3's number restriction rejects the document at the parser, so "
        "AWR-CANON-001 MUST be reported. An implementation that reports only AWR-RCPT-002 "
        "tells its user to fix the price when the problem is the serialization -- and one "
        "that reports neither has a parser that silently decided which bytes were signed. "
        "AWR-RCPT-002 is permitted alongside, because a parser that can carry 0.15 to the "
        "subject validator also determines it (section 11.1).",
        text=json_text(price_float).replace('"%s"' % SENTINEL_JSON_NUMBER, "0.15"),
        allowedExtraCodes=["AWR-RCPT-002"],
        note="The proof is a genuine signature over the same document with amount = "
        '"%s"; 0.15 cannot be canonicalized under section 4.3.' % (SENTINEL_JSON_NUMBER,),
    )
    emit(
        "work-timestamps-inverted.json",
        sign(
            envelope(
                receipt_subject(
                    work={
                        "modelId": "claude-sonnet-5@anthropic",
                        "startedAt": COMPLETED_AT,
                        "completedAt": STARTED_AT,
                        "status": "succeeded",
                    }
                ),
                HUB,
                issuer_name="example-hub",
            ),
            HUB,
        ),
        "work-timestamps-inverted",
        ["AWR-RCPT-003"],
        [],
        ["receipt", "AWR-RCPT-003", "section-3.3"],
        "completedAt two seconds before startedAt. Section 3.3 forbids it explicitly; a "
        "receipt whose work ended before it began is either a clock error or a fabricated "
        "latency, and both matter to a cost or SLA dispute.",
    )
    emit(
        "latencyms-negative.json",
        sign(
            envelope(
                receipt_subject(
                    work={
                        "modelId": "claude-sonnet-5@anthropic",
                        "completedAt": COMPLETED_AT,
                        "status": "succeeded",
                        "latencyMs": -2340,
                    }
                ),
                HUB,
                issuer_name="example-hub",
            ),
            HUB,
        ),
        "latencyms-negative",
        ["AWR-RCPT-004"],
        [],
        ["receipt", "AWR-RCPT-004", "section-3.3"],
        "latencyMs is -2340: a well-formed integer within section 4.3's range that section "
        "3.3 nonetheless forbids. It separates the canonicalization check from the "
        "semantic one -- an implementation that only bounds the magnitude accepts it.",
    )
    emit(
        "modelid-empty.json",
        sign(
            envelope(
                receipt_subject(
                    work={
                        "modelId": "",
                        "completedAt": COMPLETED_AT,
                        "status": "succeeded",
                    }
                ),
                HUB,
                issuer_name="example-hub",
            ),
            HUB,
        ),
        "modelid-empty",
        ["AWR-RCPT-005"],
        [],
        ["receipt", "AWR-RCPT-005", "section-3.3"],
        "work.modelId is the empty string. Section 3.3 requires it present AND non-empty; "
        "\"present\" alone is satisfied by \"\", which is how a receipt ends up naming no "
        "model while a schema validator is content.",
    )
    emit(
        "status-not-in-enumeration.json",
        sign(
            envelope(
                receipt_subject(
                    work={
                        "modelId": "claude-sonnet-5@anthropic",
                        "completedAt": COMPLETED_AT,
                        "status": "ok",
                    }
                ),
                HUB,
                issuer_name="example-hub",
            ),
            HUB,
        ),
        "status-not-in-enumeration",
        ["AWR-RCPT-006"],
        [],
        ["receipt", "AWR-RCPT-006", "section-3.3", "enumeration"],
        "work.status is \"ok\", not one of the five values section 3.3 enumerates. An "
        "open-world reading of status is how \"failed\" quietly becomes \"ok\" across a "
        "gateway, which is the one thing a dispute turns on.",
    )

    # ---- section 3.4 verdict (AWR-VDCT-*) --------------------------------

    def verdict_doc(subject: Dict[str, Any], key: SigningKey = VERIFIER_A) -> Dict[str, Any]:
        return sign(
            envelope(
                subject,
                key,
                document_type="VerificationVerdict",
                issuer_name="example-verifier-a",
            ),
            key,
        )

    emit(
        "verdict-verifiedwork-no-digest.json",
        verdict_doc(
            {
                "verifiedWork": {"id": minimal["id"]},
                "verdict": "pass",
                "method": {"id": "urn:example:method:grounded-council-v1"},
            }
        ),
        "verdict-verifiedwork-no-digest",
        ["AWR-VDCT-001"],
        [],
        ["verdict", "AWR-VDCT-001", "section-3.4", "section-13.2"],
        "verifiedWork names the receipt by identifier only. Section 3.4 requires both id "
        "and digestSRI precisely so a favourable verdict cannot be detached from the work "
        "it judged and attached to different work with the same identifier (section 13.2) "
        "-- and an id-only reference is exactly what AWR/1 used.",
    )
    emit(
        "verdict-score-out-of-range.json",
        verdict_doc(verdict_subject(minimal, score="1.5")),
        "verdict-score-out-of-range",
        ["AWR-VDCT-002"],
        [],
        ["verdict", "AWR-VDCT-002", "section-3.4", "decimal-string"],
        "score is the decimal string \"1.5\", outside the closed unit interval. Comparison "
        "MUST be decimal arithmetic (section 4.3), and the value being a string is not "
        "enough on its own -- an implementation that only checks the type publishes "
        "confidence scores above 1.",
    )
    emit(
        "verdict-method-missing.json",
        verdict_doc(
            {
                "verifiedWork": document_reference(minimal),
                "verdict": "pass",
                "score": "0.93",
                "method": {"name": "grounded council, 3 jurors"},
            }
        ),
        "verdict-method-missing",
        ["AWR-VDCT-003"],
        [],
        ["verdict", "AWR-VDCT-003", "section-3.4", "comparability"],
        "method has a name but no id. Section 3.4 makes two verdicts comparable only if "
        "they name the same method id, so a verdict without one is a score that cannot be "
        "compared to anything -- while looking complete to a reader.",
    )
    emit(
        "verdict-not-in-enumeration.json",
        verdict_doc(verdict_subject(minimal, verdict="passed")),
        "verdict-not-in-enumeration",
        ["AWR-VDCT-004"],
        [],
        ["verdict", "AWR-VDCT-004", "section-3.4", "enumeration"],
        "verdict is \"passed\" rather than \"pass\". A verifier that string-matches "
        "loosely treats \"passed\" as a pass and, by the same tolerance, would treat "
        "\"inconclusive\" as one -- which section 3.4 calls turning verifiers into rubber "
        "stamps.",
    )
    repointed_target = work_receipt(
        subject=receipt_subject(
            nonce="the-receipt-the-verdict-was-NOT-about",
            outputDigest=SRI["tool-call"],
        ),
        issuer_name="example-hub",
        document_id=minimal["id"],
    )
    write_json("invalid/verdict-repointed-other-receipt.json", repointed_target)
    emit(
        "verdict-repointed-same-id.json",
        verdict_doc(verdict_subject(minimal)),
        "verdict-repointed-same-id",
        ["AWR-VDCT-005"],
        [],
        ["verdict", "AWR-VDCT-005", "section-13.2", "reference-substitution"],
        "A verdict that genuinely judged valid/receipt-minimal-l0, supplied alongside a "
        "DIFFERENT receipt carrying the same id and a different outputDigest. Both "
        "documents are individually valid and correctly signed; only the digest in "
        "verifiedWork distinguishes them. An implementation that matches by id reports the "
        "substituted receipt as verified, which is the substitution attack of section "
        "13.2.",
        supporting=["invalid/verdict-repointed-other-receipt.json"],
    )
    emit(
        "verdict-evidence-without-digest.json",
        verdict_doc(
            verdict_subject(
                minimal,
                evidence=[
                    {"kind": "trace", "digestSRI": SRI["tool-call"]},
                    {"kind": "transcript", "uri": "https://example.org/traces/9f2c"},
                ],
            )
        ),
        "verdict-evidence-without-digest",
        ["AWR-VDCT-007"],
        [],
        ["verdict", "AWR-VDCT-007", "section-3.4", "evidence"],
        "The second evidence entry has a URI and no digestSRI. Section 3.4 does not "
        "require the bytes to be available, only that they be non-substitutable; evidence "
        "identified by location alone can be swapped after the fact, and a verifier that "
        "accepts it has recorded a promise rather than a commitment.",
    )

    # ---- section 3.5 blame (AWR-BLAME-*) ---------------------------------

    hop1, hop2, hop3 = built["hop1"], built["hop2"], built["hop3"]

    def blame_doc(subject: Dict[str, Any]) -> Dict[str, Any]:
        return sign(
            envelope(
                subject,
                ATTRIBUTOR,
                document_type="BlameAttestation",
                issuer_name="example-attributor",
            ),
            ATTRIBUTOR,
        )

    unrelated = work_receipt(
        subject=receipt_subject(
            nonce="a-hop-from-a-completely-different-chain",
            outputDigest=SRI["tool-call"],
        ),
        key=UPSTREAM,
        issuer_name="example-other-hub",
    )
    write_json("invalid/blame-unrelated-receipt.json", unrelated)
    write_json(
        "invalid/blame-chain-receipts.awrb.json", make_bundle([hop1, hop2, hop3])
    )
    emit(
        "blame-unreachable-blamedwork.json",
        blame_doc(
            {
                "chain": document_reference(hop1),
                "blamedWork": document_reference(unrelated),
                "failureClass": "wrong-output",
                "confidence": "0.75",
                "method": {"id": "urn:example:method:hop-bisect-v1"},
            }
        ),
        "blame-unreachable-blamedwork",
        ["AWR-BLAME-001"],
        [],
        ["blame", "AWR-BLAME-001", "section-3.5", "reachability"],
        "blamedWork is a valid receipt from another chain entirely, while every hop of the "
        "named chain is supplied so the walk is complete. Section 3.5 requires a verifier "
        "that HAS the intermediate receipts to report this: blame attached to a hop that "
        "was never in the chain is how an accountable party is invented.",
        supporting=[
            "invalid/blame-chain-receipts.awrb.json",
            "invalid/blame-unrelated-receipt.json",
        ],
    )
    emit(
        "blame-failureclass-invalid.json",
        blame_doc(
            {
                "chain": document_reference(hop1),
                "blamedWork": document_reference(hop3),
                "failureClass": "hallucination",
                "method": {"id": "urn:example:method:hop-bisect-v1"},
            }
        ),
        "blame-failureclass-invalid",
        ["AWR-BLAME-002"],
        [],
        ["blame", "AWR-BLAME-002", "section-3.5", "enumeration"],
        "failureClass \"hallucination\" is not in section 3.5's enumeration. The "
        "enumeration is closed because upstream-input is the value that exonerates a hop; "
        "an open vocabulary lets an attributor invent a class that no consumer knows how "
        "to weigh.",
        supporting=["invalid/blame-chain-receipts.awrb.json"],
    )
    emit(
        "blame-chain-missing.json",
        blame_doc(
            {
                "blamedWork": document_reference(hop3),
                "failureClass": "wrong-output",
                "method": {"id": "urn:example:method:hop-bisect-v1"},
            }
        ),
        "blame-chain-missing",
        ["AWR-BLAME-003"],
        [],
        ["blame", "AWR-BLAME-003", "section-3.5"],
        "chain is absent, so the document blames a hop without saying which observable "
        "failure it is answering for. Section 3.5 requires both references; blame with no "
        "chain cannot be checked for reachability and cannot be contested.",
    )
    emit(
        "blame-confidence-out-of-range.json",
        blame_doc(
            {
                "chain": document_reference(hop1),
                "blamedWork": document_reference(hop3),
                "failureClass": "upstream-input",
                "confidence": "1.1",
                "method": {"id": "urn:example:method:hop-bisect-v1"},
            }
        ),
        "blame-confidence-out-of-range",
        ["AWR-BLAME-004"],
        [],
        ["blame", "AWR-BLAME-004", "section-3.5", "decimal-string"],
        "confidence \"1.1\" is outside [0,1]. It carries its own code (AWR-BLAME-004) "
        "rather than the verdict's AWR-VDCT-002, so an implementation that reuses one "
        "decimal check for every field reports the wrong code and sends the reader to the "
        "wrong section.",
        supporting=["invalid/blame-chain-receipts.awrb.json"],
    )

    # ---- section 8 chains (AWR-CHAIN-*) ----------------------------------

    emit(
        "parents-entry-missing-digest.json",
        sign(
            envelope(
                receipt_subject(
                    parents=[{"id": built["hop_parent"]["id"], "role": "retrieval"}]
                ),
                HUB,
                issuer_name="example-hub",
            ),
            HUB,
        ),
        "parents-entry-missing-digest",
        ["AWR-CHAIN-001"],
        [],
        ["chain", "AWR-CHAIN-001", "section-8.1", "awr1-defect"],
        "A parents entry that names its parent by id and carries no digest -- AWR/1's edge "
        "format exactly (Appendix D). Section 8.1 makes an edge a commitment to the "
        "parent's exact bytes; without one the chain can be re-pointed while every "
        "signature still verifies.",
    )
    emit(
        "parents-digest-sha512.json",
        sign(
            envelope(
                receipt_subject(
                    parents=[
                        {
                            "id": built["hop_parent"]["id"],
                            "digestSRI": "sha512-"
                            + canonical_sri(built["hop_parent"])[len("sha256-") :],
                            "role": "retrieval",
                        }
                    ]
                ),
                HUB,
                issuer_name="example-hub",
            ),
            HUB,
        ),
        "parents-digest-sha512",
        ["AWR-CHAIN-002"],
        [],
        ["chain", "AWR-CHAIN-002", "section-3.2", "algorithm"],
        "A parents entry whose digestSRI claims sha512. Section 3.2 requires a verifier "
        "encountering another prefix to REPORT AWR-CHAIN-002 rather than ignore the "
        "reference -- silently skipping an edge it cannot check is how a chain reports as "
        "intact when a hop was never verified.",
    )
    stripped_parent = {
        k: v for k, v in copy.deepcopy(built["hop_parent"]).items() if k != "proof"
    }
    write_json("invalid/chain-parent-proof-stripped-parent.json", stripped_parent)
    emit(
        "chain-parent-proof-stripped.json",
        copy.deepcopy(built["hop_child"]),
        "chain-parent-proof-stripped",
        ["AWR-CHAIN-003"],
        [],
        ["chain", "AWR-CHAIN-003", "section-8.1", "secured-parent"],
        "The child of valid/chain-two-hop, supplied with a parent whose proof was removed "
        "and nothing else changed. Section 8.1 digests the SECURED parent, signature "
        "included, so an implementation that digests the unsecured parent -- a natural "
        "mistake, since verification strips proof anyway -- accepts an unsigned parent as "
        "a chain hop.",
        supporting=["invalid/chain-parent-proof-stripped-parent.json"],
    )
    substituted_parent = work_receipt(
        subject=receipt_subject(
            inputDigest=SRI["prompt"],
            outputDigest=SRI["retrieved"],
            nonce="substituted-parent-same-id",
        ),
        key=UPSTREAM,
        issuer_name="example-retrieval",
        document_id=built["hop_parent"]["id"],
    )
    write_json("invalid/chain-parent-substituted-parent.json", substituted_parent)
    emit(
        "chain-parent-digest-mismatch.json",
        copy.deepcopy(built["hop_child"]),
        "chain-parent-digest-mismatch",
        ["AWR-CHAIN-003"],
        [],
        ["chain", "AWR-CHAIN-003", "section-8.2", "substitution"],
        "The same child, supplied with a validly signed parent that has the right id and "
        "different content. Section 8.2 requires recomputing the parent's digest and "
        "reporting the mismatch; a verifier that looks parents up by id and then trusts "
        "the signature it finds has verified a different chain than the one the child "
        "committed to.",
        supporting=["invalid/chain-parent-substituted-parent.json"],
    )

    self_loop = sign(
        envelope(
            receipt_subject(
                parents=[{"id": "urn:uuid:cycle-self", "digestSRI": SRI["retrieved"]}],
                nonce="self-referential-hop",
            ),
            HUB,
            issuer_name="example-hub",
            document_id="urn:uuid:cycle-self",
        ),
        HUB,
    )
    write_json("invalid/chain-cycle-self-copy.awrb.json", make_bundle([self_loop]))
    emit(
        "chain-cycle-self.json",
        self_loop,
        "chain-cycle-self",
        ["AWR-CHAIN-003", "AWR-CHAIN-004"],
        [],
        ["chain", "AWR-CHAIN-004", "AWR-CHAIN-003", "section-8.2", "dos"],
        "A receipt that names itself as its own parent, supplied to the walk as a chain "
        "document. Section 8.2 requires cycle detection because chain resolution is "
        "attacker-influenced work and an unbounded walk is a denial of service. "
        "AWR-CHAIN-003 rides along and cannot be avoided: an edge digest that matched its "
        "own document would be a SHA-256 fixed point, so any constructible cycle also "
        "carries a digest mismatch (see specFindings in index.json).",
        supporting=["invalid/chain-cycle-self-copy.awrb.json"],
    )

    cycle_c = sign(
        envelope(
            receipt_subject(
                parents=[{"id": "urn:uuid:cycle-b", "digestSRI": SRI["tool-call"]}],
                nonce="cycle-hop-c",
            ),
            UPSTREAM,
            issuer_name="example-other-hub",
            document_id="urn:uuid:cycle-c",
        ),
        UPSTREAM,
    )
    cycle_b = sign(
        envelope(
            receipt_subject(
                parents=[dict(document_reference(cycle_c), role="subagent")],
                nonce="cycle-hop-b",
            ),
            UPSTREAM,
            issuer_name="example-other-hub",
            document_id="urn:uuid:cycle-b",
        ),
        UPSTREAM,
    )
    cycle_a = sign(
        envelope(
            receipt_subject(
                parents=[dict(document_reference(cycle_b), role="subagent")],
                nonce="cycle-hop-a",
            ),
            HUB,
            issuer_name="example-hub",
            document_id="urn:uuid:cycle-a",
        ),
        HUB,
    )
    write_json(
        "invalid/chain-cycle-three-node-support.awrb.json",
        make_bundle([cycle_b, cycle_c]),
    )
    emit(
        "chain-cycle-three-node.json",
        cycle_a,
        "chain-cycle-three-node",
        ["AWR-CHAIN-003", "AWR-CHAIN-004", "AWR-CHAIN-006"],
        [],
        ["chain", "AWR-CHAIN-004", "AWR-CHAIN-006", "section-8.2", "dos"],
        "A -> B -> C -> B: a three-node walk whose cycle is not a self-loop, so a resolver "
        "that only guards against the trivial case still recurses forever. All three codes "
        "are structurally forced -- B is referenced once with its true digest by A and once "
        "with a false one by C, which is simultaneously a cycle (AWR-CHAIN-004), a digest "
        "mismatch (AWR-CHAIN-003) and one id with conflicting digests (AWR-CHAIN-006).",
        supporting=["invalid/chain-cycle-three-node-support.awrb.json"],
        # A->B and B->C resolve by digest, and every hop here carries the same
        # inputDigest/outputDigest pair, so a verifier that performs the section 8.3
        # input/output check reports AWR-CHAIN-007 on both edges.  Section 8.3 makes that
        # check a SHOULD while making the report a MUST, so the warning can be neither
        # required nor forbidden here; see specFindings.
        allowedExtraWarnings=["AWR-CHAIN-007"],
    )

    over_limit = build_depth_chain(DEPTH_LIMIT + 2, tag="x")
    write_json("invalid/chain-depth-limit-exceeded.awrb.json", make_bundle(over_limit))
    vector(
        "invalid/chain-depth-limit-exceeded",
        "invalid/chain-depth-limit-exceeded.awrb.json",
        "bundle",
        "invalid",
        ["AWR-CHAIN-005"],
        [],
        None,
        ["chain", "AWR-CHAIN-005", "section-8.2", "dos", "boundary"],
        "A chain of 66 receipts, depths 0..65, one hop past section 8.2's default maximum "
        "depth of 64. The limits are mandatory, not advisory: an implementation with no "
        "bound resolves the whole chain and reports it valid, and the same code path is "
        "what an attacker points at a 10^6-hop bundle. Paired with "
        "valid/chain-depth-at-limit, which MUST NOT report this code.",
        now=NOW,
    )
    # The node-count half of AWR-CHAIN-005.  The default is 1024 nodes, which would need a
    # 1025-document bundle; section 17 now defines --max-nodes, so the same code path is
    # exercised with a four-hop chain and a limit of two.  The chain is short enough that
    # the depth limit is untouched, so a failure here is the node counter and nothing else.
    node_chain = build_depth_chain(4, tag="nodes")
    write_json("invalid/chain-node-limit-exceeded.awrb.json", make_bundle(node_chain))
    vector(
        "invalid/chain-node-limit-exceeded",
        "invalid/chain-node-limit-exceeded.awrb.json",
        "bundle",
        "invalid",
        ["AWR-CHAIN-005"],
        [],
        None,
        ["chain", "AWR-CHAIN-005", "section-8.2", "dos", "node-limit"],
        "Four receipts in a chain, verified with --max-nodes 2. AWR-CHAIN-005 covers two "
        "independent bounds and an implementation can easily enforce the depth one and "
        "forget the node one -- a wide chain (one receipt with 10^6 parents) has depth 1 "
        "and is exactly as effective a denial of service. Section 8.2 makes both limits "
        "mandatory and configurable, and section 17 defines the flag, so both halves of "
        "the code are now reachable.",
        now=NOW,
        maxNodes=2,
    )
    emit(
        "parents-conflicting-digests.json",
        sign(
            envelope(
                receipt_subject(
                    parents=[
                        {
                            "id": built["hop_parent"]["id"],
                            "digestSRI": canonical_sri(built["hop_parent"]),
                            "role": "retrieval",
                        },
                        {
                            "id": built["hop_parent"]["id"],
                            "digestSRI": SRI["tool-call"],
                            "role": "tool",
                        },
                    ]
                ),
                HUB,
                issuer_name="example-hub",
            ),
            HUB,
        ),
        "parents-conflicting-digests",
        ["AWR-CHAIN-006"],
        [],
        ["chain", "AWR-CHAIN-006", "section-8.2"],
        "One receipt names the same parent id twice with two different digests. Section "
        "8.2 calls this a direct statement that one of the two is forged, and it is "
        "detectable with no other document present -- an implementation that only compares "
        "digests it can resolve misses it entirely.",
    )

    # ---- section 9 bundles (AWR-BUNDLE-*) --------------------------------

    bad_version = make_bundle([minimal])
    bad_version["awrBundle"] = "1.0"
    write_json("invalid/bundle-version-unsupported.awrb.json", bad_version)
    vector(
        "invalid/bundle-version-unsupported",
        "invalid/bundle-version-unsupported.awrb.json",
        "bundle",
        "invalid",
        ["AWR-BUNDLE-001"],
        [],
        None,
        ["bundle", "AWR-BUNDLE-001", "section-9"],
        "awrBundle is \"1.0\". The container version is the one thing a bundle asserts, "
        "and an implementation that ignores it will read a future container's members "
        "under this version's rules.",
        now=NOW,
    )
    duplicate_verdict_a = sign(
        envelope(
            verdict_subject(minimal),
            VERIFIER_A,
            document_type="VerificationVerdict",
            document_id="urn:uuid:00000fff-a11c-4f38-9b8a-1c2d3e4f5a6b",
            issuer_name="example-verifier-a",
        ),
        VERIFIER_A,
    )
    duplicate_verdict_b = sign(
        envelope(
            verdict_subject(minimal, verdict="fail", score="0.10"),
            VERIFIER_A,
            document_type="VerificationVerdict",
            document_id="urn:uuid:00000fff-a11c-4f38-9b8a-1c2d3e4f5a6b",
            issuer_name="example-verifier-a",
        ),
        VERIFIER_A,
    )
    write_json(
        "invalid/bundle-duplicate-id-differing.awrb.json",
        make_bundle([minimal, duplicate_verdict_a, duplicate_verdict_b]),
    )
    vector(
        "invalid/bundle-duplicate-id-differing",
        "invalid/bundle-duplicate-id-differing.awrb.json",
        "bundle",
        "invalid",
        ["AWR-BUNDLE-002"],
        [],
        None,
        ["bundle", "AWR-BUNDLE-002", "section-9", "verdict-shopping"],
        "Two validly signed verdicts about the same receipt, from the same issuer, with "
        "the same id and opposite verdicts (pass 0.93 / fail 0.10). Both verify "
        "individually; only the bundle-level duplicate check catches that a consumer's "
        "answer now depends on which one it happens to index.",
        now=NOW,
    )
    write_json(
        "invalid/bundle-ambiguous-subject.awrb.json",
        make_bundle([minimal, built["l2_receipt"]]),
    )
    vector(
        "invalid/bundle-ambiguous-subject",
        "invalid/bundle-ambiguous-subject.awrb.json",
        "bundle",
        "invalid",
        ["AWR-BUNDLE-003"],
        [],
        None,
        ["bundle", "AWR-BUNDLE-003", "section-9", "no-guessing"],
        "Two unrelated receipts, neither referenced as a parent, and no subject argument. "
        "Section 9 forbids resolving the ambiguity by guessing -- an implementation that "
        "takes documents[0] answers a question the caller did not ask, and "
        "valid/bundle-explicit-subject is the same bytes with the argument supplied.",
        now=NOW,
    )

    # ---- section 10 profiles (AWR-PROFILE-*) -----------------------------

    vector(
        "invalid/profile-l1-no-verdict",
        "valid/receipt-minimal-l0.json",
        "document",
        "invalid",
        ["AWR-PROFILE-001"],
        [],
        "L1",
        ["profile", "AWR-PROFILE-001", "section-10.2"],
        "The minimal receipt checked at L1 with no verdict supplied. The same bytes are "
        "valid at L0, which is the point: a profile is checked on request and never "
        "granted by self-assertion, so an implementation that reports one boolean cannot "
        "distinguish \"valid\" from \"verified\".",
        now=NOW,
    )
    self_verdict = sign(
        envelope(
            verdict_subject(minimal, method={"id": "urn:example:method:self-check-v1"}),
            HUB,
            document_type="VerificationVerdict",
            issuer_name="example-hub",
        ),
        HUB,
    )
    write_json(
        "invalid/profile-l1-self-issued-verdict.awrb.json",
        make_bundle([minimal, self_verdict]),
    )
    vector(
        "invalid/profile-l1-self-issued-verdict",
        "invalid/profile-l1-self-issued-verdict.awrb.json",
        "bundle",
        "invalid",
        ["AWR-PROFILE-002"],
        [],
        "L1",
        ["profile", "AWR-PROFILE-002", "section-10.2", "section-13.3", "self-verification"],
        "A perfectly valid verdict signed by the receipt's OWN issuer. Nothing "
        "cryptographic is wrong with it; section 10.2 excludes it structurally because "
        "\"verified\" that means \"verified by itself\" is worse than no claim (section "
        "13.3). This is the vector a verifier that only checks signatures cannot fail.",
        now=NOW,
    )
    single_issuer_two_verdicts_a = sign(
        envelope(
            verdict_subject(built["l2_receipt"], stake=copy.deepcopy(STAKE)),
            VERIFIER_A,
            document_type="VerificationVerdict",
            issuer_name="example-verifier-a",
        ),
        VERIFIER_A,
    )
    single_issuer_two_verdicts_b = sign(
        envelope(
            verdict_subject(
                built["l2_receipt"],
                score="0.88",
                method={"id": "urn:example:method:replay-diff-v2"},
                stake=copy.deepcopy(STAKE),
            ),
            VERIFIER_A,
            document_type="VerificationVerdict",
            issuer_name="example-verifier-a",
        ),
        VERIFIER_A,
    )
    write_json(
        "invalid/profile-l2-single-issuer.awrb.json",
        make_bundle(
            [
                built["l2_receipt"],
                single_issuer_two_verdicts_a,
                single_issuer_two_verdicts_b,
            ]
        ),
    )
    vector(
        "invalid/profile-l2-single-issuer",
        "invalid/profile-l2-single-issuer.awrb.json",
        "bundle",
        "invalid",
        ["AWR-PROFILE-003"],
        ["AWR-L2-001"],
        "L2",
        ["profile", "AWR-PROFILE-003", "section-10.3", "distinct-issuers"],
        "TWO valid verdicts, both independent of the receipt's issuer, both staked, both "
        "with different methods -- and both signed by the same key. Section 10.3 counts "
        "distinct issuer.id values, not verdicts; an implementation that counts documents "
        "grants L2 to one verifier who submitted twice.",
        now=NOW,
    )
    no_binding_receipt = work_receipt(
        subject=receipt_subject(nonce="01J9Z8QK4T7YB2N5V6W8XA3H01"),
        issuer_name="example-hub",
    )
    binding_verdict_a = sign(
        envelope(
            verdict_subject(no_binding_receipt),
            VERIFIER_A,
            document_type="VerificationVerdict",
            issuer_name="example-verifier-a",
        ),
        VERIFIER_A,
    )
    binding_verdict_b = sign(
        envelope(
            verdict_subject(
                no_binding_receipt, method={"id": "urn:example:method:replay-diff-v2"}
            ),
            VERIFIER_B,
            document_type="VerificationVerdict",
            issuer_name="example-verifier-b",
        ),
        VERIFIER_B,
    )
    write_json(
        "invalid/profile-l2-no-binding.awrb.json",
        make_bundle([no_binding_receipt, binding_verdict_a, binding_verdict_b]),
    )
    vector(
        "invalid/profile-l2-no-binding",
        "invalid/profile-l2-no-binding.awrb.json",
        "bundle",
        "invalid",
        ["AWR-PROFILE-004"],
        [],
        "L2",
        ["profile", "AWR-PROFILE-004", "section-10.3", "accountability"],
        "L1 satisfied twice over -- two verdicts from two distinct independent issuers -- "
        "and no settlement on the receipt and no stake on either verdict. Section 10.3 "
        "requires the accountability binding as well as the second opinion, so an "
        "implementation that reads L2 as \"two verdicts\" reports it here. Note the "
        "absence of AWR-L2-001: there is no binding to warn about.",
        now=NOW,
    )

    # ---- section 12 legacy (AWR-LEGACY-*) --------------------------------

    write_json("invalid/awr1-both-dialects-fail.json", legacy_document("A", break_signature=True))
    vector(
        "invalid/awr1-both-dialects-fail",
        "invalid/awr1-both-dialects-fail.json",
        "document",
        "invalid",
        ["AWR-LEGACY-002"],
        ["AWR-LEGACY-001", "AWR-LEGACY-004"],
        None,
        ["legacy", "awr1", "AWR-LEGACY-002", "AWR-LEGACY-004", "section-12"],
        "An AWR/1 document with a genuine dialect-A signature and one member added to "
        "credentialSubject afterwards, so the rendering matches under neither dialect. "
        "Section 12 requires BOTH dialects be tried before failing: an implementation that "
        "tries one reports AWR-LEGACY-002 on half of the real legacy corpus, and one that "
        "tries neither reports this tampered document as verified. AWR-LEGACY-001 is still "
        "reported, because the document is still AWR/1.",
        now=NOW,
    )


# ---------------------------------------------------------------------------
# section 12.3 version gate and section 12.4 issuer rules
# ---------------------------------------------------------------------------

#: The attacker in the vectors below.  ``verifierA``'s seed is reused as "a key the
#: attacker holds and the victim does not"; the victim is ``hub``, whose DID is public
#: information.  That is the whole point of the downgrade forgery: it needs nothing secret.
ATTACKER = VERIFIER_A

#: The AWR/1 identifier form Appendix D records: ``did:key:`` + the first 32 characters of
#: the base64 public key.  It is not a DID and names no recoverable key, which is why
#: section 12.2 has to look elsewhere -- and why an attacker who puts one here is
#: cross-checked against nothing.
AWR1_STYLE_ID = "did:key:" + base64.b64encode(HUB.public_key_bytes).decode("ascii")[:32]

GATE_SUBJECT = {
    "work": {
        "modelId": "victim-flagship@v3",
        "startedAt": "2026-07-31T11:59:58Z",
        "completedAt": "2026-07-31T12:00:00Z",
        "latencyMs": 2340,
        "status": "succeeded",
    },
    "inputDigest": SRI["prompt"],
    "outputDigest": SRI["summary"],
    "price": {"currency": "USD", "amount": "999.00"},
}


def legacy_proof_over(subject: Dict[str, Any], key: SigningKey) -> Dict[str, Any]:
    """An AWR/1 proof over the section 12.1 rendering of *subject*, signed with *key*.

    Section 12 forbids an implementation from ISSUING AWR/1, so there is no issuance path
    to reach for: the signature is produced here by handing the legacy rendering to a raw
    Ed25519 signer.
    """
    return {
        "type": "Ed25519Signature2018",
        "created": "2026-07-31T12:00:05Z",
        # The section 5.3 form over the VICTIM's DID: what a reader sees.
        "verificationMethod": HUB.verification_method,
        "proofPurpose": "assertionMethod",
        "proofValue": base64.b64encode(
            key.sign(legacy_canonical_form(subject, "A"))
        ).decode("ascii"),
    }


def gate_document(
    issuer: Dict[str, Any],
    *,
    signals: Sequence[str] = (),
    key: SigningKey = None,
    doc_id: str = "urn:uuid:00000fed-1e6a-4c11-8f00-000000000001",
) -> Dict[str, Any]:
    """An AWR/1-proofed document carrying the named section 12.3 AWR/2 signals.

    *signals* is drawn from {"awrVersion", "context", "validFrom", "settlement"}.
    """
    subject = copy.deepcopy(GATE_SUBJECT)
    if "settlement" in signals:
        subject["settlement"] = {"chain": "eip155:8453", "txHash": "0x" + "ab" * 32}
    document: Dict[str, Any] = {}
    if "context" in signals:
        document["@context"] = [VC_CONTEXT, AWR_CONTEXT]
    else:
        document["@context"] = ["https://www.w3.org/2018/credentials/v1"]
    document["id"] = doc_id
    document["type"] = ["VerifiableCredential", "WorkReceipt"]
    document["issuer"] = issuer
    if "validFrom" in signals:
        document["validFrom"] = "2026-07-31T12:00:05Z"
    else:
        document["issuanceDate"] = "2026-07-31T12:00:05Z"
    if "awrVersion" in signals:
        document["awrVersion"] = "2.0.0"
    document["credentialSubject"] = subject
    document["proof"] = legacy_proof_over(subject, key or ATTACKER)
    return document


def build_legacy_gate(built: Dict[str, Any]) -> None:
    """Vectors for the section 12.3 gate and the section 12.4 unsigned-issuer rules.

    Every one of these was reported ``valid: true`` by at least two of the three
    implementations before the gate existed, and the first four were reported valid by all
    three -- with ``documentType: WorkReceipt``, ``awrVersion: 2.0.0`` and exit code 0,
    unchanged under ``--profile L0``.
    """
    attacker_jwk = ATTACKER.public_key_jwk()

    # -- 1. THE downgrade forgery -----------------------------------------
    document = gate_document(
        {"id": HUB.did, "name": "example-hub", "publicKeyJwk": attacker_jwk},
        signals=("awrVersion", "context"),
    )
    write_json("invalid/awr1-downgrade-awrversion.json", document)
    vector(
        "invalid/awr1-downgrade-awrversion",
        "invalid/awr1-downgrade-awrversion.json",
        "document",
        "invalid",
        ["AWR-LEGACY-003"],
        [],
        None,
        ["legacy", "awr1", "AWR-LEGACY-003", "section-12.3", "downgrade", "forgery",
         "authentication-bypass"],
        "THE downgrade forgery. The document presents itself as AWR/2 -- awrVersion 2.0.0 "
        "and the AWR/2 @context -- and carries an Ed25519Signature2018 proof over the "
        "section 12.1 rendering signed with a key the ATTACKER holds, while naming the "
        "victim's real did:key in issuer.id. Every implementation that selected the legacy "
        "path on proof.type alone reported this valid: true, documentType WorkReceipt, "
        "awrVersion 2.0.0, exit 0, even under --profile L0, because AWR/1 signs neither "
        "proof.type nor issuer and the key was taken from the document's own unsigned "
        "issuer object. Section 12.3 makes the AWR/2 signal win over the unsigned proof "
        "suite: the signals disagree, so the document is verified under NEITHER rule set "
        "and there is no fallback to the other. The signature is genuine under the "
        "attacker's key, so any implementation that reaches the signature check reports "
        "this valid -- the classification is the whole defence.",
        now=NOW,
        note="Signed by handing legacy_canonical_form(credentialSubject, 'A') to a raw "
        "Ed25519 signer with the verifierA seed. Section 12 forbids ISSUING AWR/1, so no "
        "implementation has a code path that produces this document.",
    )

    # -- 2. the @context signal alone -------------------------------------
    write_json(
        "invalid/awr1-downgrade-context-only.json",
        gate_document(
            {"id": HUB.did, "name": "example-hub", "publicKeyJwk": attacker_jwk},
            signals=("context",),
        ),
    )
    vector(
        "invalid/awr1-downgrade-context-only",
        "invalid/awr1-downgrade-context-only.json",
        "document",
        "invalid",
        ["AWR-LEGACY-003"],
        [],
        None,
        ["legacy", "awr1", "AWR-LEGACY-003", "section-12.3", "downgrade",
         "context-signal"],
        "The same forgery with awrVersion removed, so the only AWR/2 signal is the "
        "@context (section 12.3 signal 2). An implementation that gates on awrVersion "
        "alone -- the obvious reading of section 3.1, which is the member that says a "
        "document cannot be re-interpreted under another version's rules -- lets this "
        "through, and the attacker deletes one member to get there. The section 12.3 "
        "signal list is closed so that every signal in it is load-bearing.",
        now=NOW,
    )

    # -- 3. the validFrom signal alone ------------------------------------
    write_json(
        "invalid/awr1-downgrade-validfrom.json",
        gate_document(
            {"id": AWR1_STYLE_ID, "name": "example-hub", "publicKeyJwk": attacker_jwk},
            signals=("validFrom",),
        ),
    )
    vector(
        "invalid/awr1-downgrade-validfrom",
        "invalid/awr1-downgrade-validfrom.json",
        "document",
        "invalid",
        ["AWR-LEGACY-003"],
        [],
        None,
        ["legacy", "awr1", "AWR-LEGACY-003", "section-12.3", "downgrade",
         "validfrom-signal"],
        "An AWR/1 proof on a document carrying validFrom (section 12.3 signal 4): AWR/1 "
        "was VC 1.1 and used issuanceDate, so validFrom is an AWR/2 claim made with "
        "neither awrVersion nor the AWR/2 @context present. issuer.id here is the Appendix "
        "D identifier form, which names no key, so the section 12.4 cross-check has "
        "nothing to compare and the version gate is the only thing that rejects this.",
        now=NOW,
    )

    # -- 4. the settlement signal alone -----------------------------------
    write_json(
        "invalid/awr1-downgrade-settlement.json",
        gate_document(
            {"id": AWR1_STYLE_ID, "name": "example-hub", "publicKeyJwk": attacker_jwk},
            signals=("settlement",),
        ),
    )
    vector(
        "invalid/awr1-downgrade-settlement",
        "invalid/awr1-downgrade-settlement.json",
        "document",
        "invalid",
        ["AWR-LEGACY-003"],
        [],
        None,
        ["legacy", "awr1", "AWR-LEGACY-003", "section-12.3", "downgrade",
         "settlement-signal", "section-10.3"],
        "An AWR/1 proof on a document whose credentialSubject carries settlement (section "
        "12.3 signal 5) -- an L2 accountability binding (section 10.3) AWR/1 had no notion "
        "of. Without the gate this is a legacy receipt claiming a payment binding while "
        "being verifiable against a key its own unsigned issuer object supplies. Note "
        "credentialSubject.parents is deliberately NOT a signal: Appendix D records that "
        "AWR/1 carried parents too, as identifier strings, so treating it as an AWR/2 "
        "claim would reject part of the honest legacy corpus.",
        now=NOW,
    )

    # -- 5/6. a proof array mixing the two suites, in both orders ---------
    genuine = copy.deepcopy(built["minimal"])
    awr2_proof = copy.deepcopy(genuine["proof"])
    legacy_extra = legacy_proof_over(genuine["credentialSubject"], ATTACKER)
    for name, order, tail in (
        ("invalid/proof-array-awr2-then-awr1", "awr2-first",
         "with an AWR/1 proof appended at index 1"),
        ("invalid/proof-array-awr1-then-awr2", "awr1-first",
         "with an AWR/1 proof inserted at index 0"),
    ):
        document = copy.deepcopy(genuine)
        document["proof"] = (
            [awr2_proof, legacy_extra] if order == "awr2-first" else [legacy_extra, awr2_proof]
        )
        write_json(name + ".json", document)
        vector(
            name,
            name + ".json",
            "document",
            "invalid",
            ["AWR-LEGACY-003"],
            [],
            None,
            ["legacy", "awr1", "AWR-LEGACY-003", "section-12.3", "proof-array", order,
             "interop"],
            "A genuinely signed AWR/2 WorkReceipt " + tail + ", signed with a key the "
            "attacker holds over the section 12.1 rendering of the same subject. This is "
            "the divergence that made one set of bytes mean three things: two "
            "implementations classified from proof[0] and one from any element of the "
            "array, so the sender chose the rule set by ordering it -- and with the legacy "
            "proof first, all three took the legacy path and never checked the genuine "
            "AWR/2 signature at all. Section 12.3 makes position irrelevant: an AWR/1 "
            "proof anywhere in a document that signals AWR/2 is AWR-LEGACY-003, in both "
            "orders, and the document is verified under neither rule set.",
            now=NOW,
            note="The AWR/2 proof is the reference issuer's over the hub key and still "
            "verifies on its own; the file differs from valid/receipt-minimal-l0 only by "
            "the added AWR/1 proof.",
        )

    # -- 7. pure AWR/1: issuer.id and the embedded JWK name different keys
    write_json(
        "invalid/awr1-issuer-key-disagrees.json",
        gate_document({"id": HUB.did, "name": "example-hub", "publicKeyJwk": attacker_jwk}),
    )
    vector(
        "invalid/awr1-issuer-key-disagrees",
        "invalid/awr1-issuer-key-disagrees.json",
        "document",
        "invalid",
        ["AWR-KEY-003"],
        ["AWR-LEGACY-001", "AWR-LEGACY-004"],
        None,
        ["legacy", "awr1", "AWR-KEY-003", "AWR-LEGACY-004", "section-12.4", "forgery",
         "unsigned-issuer"],
        "The same forgery with every AWR/2 signal removed: a pure AWR/1 document, which "
        "the section 12.3 gate cannot help with, naming the victim's real did:key in "
        "issuer.id while carrying the attacker's publicKeyJwk beside it. Two of the three "
        "implementations took the JWK and never compared it with issuer.id at all, and "
        "reported valid: true. Section 12.4 makes the disagreement an error: the document "
        "states two different signers, AWR/1 signs neither, and there is no way to tell "
        "which one the issuer meant.",
        now=NOW,
    )

    # -- 8. pure AWR/1: issuer.id is the section 5.3 verificationMethod ---
    write_json(
        "invalid/awr1-issuer-did-fragment-disagrees.json",
        gate_document(
            {
                "id": HUB.verification_method,
                "name": "example-hub",
                "publicKeyJwk": attacker_jwk,
            }
        ),
    )
    vector(
        "invalid/awr1-issuer-did-fragment-disagrees",
        "invalid/awr1-issuer-did-fragment-disagrees.json",
        "document",
        "invalid",
        ["AWR-KEY-003"],
        ["AWR-LEGACY-001", "AWR-LEGACY-004"],
        None,
        ["legacy", "awr1", "AWR-KEY-003", "AWR-LEGACY-004", "section-12.4", "section-5.3",
         "did-fragment", "forgery"],
        "issuer.id is the section 5.3 verificationMethod form, did:key:z6Mk...#z6Mk..., "
        "which carries the victim's DID as a literal prefix -- so a reader sees the "
        "victim's identifier -- while the embedded publicKeyJwk is the attacker's. The one "
        "implementation that DID cross-check the JWK against issuer.id lost the check "
        "here, because the fragment form does not parse as a bare did:key, and reported "
        "valid: true. Section 12.4 requires the portion before the fragment to be read as "
        "naming the key.",
        now=NOW,
    )

    # -- 9. the control: two key statements that agree -------------------
    write_json(
        "valid/awr1-legacy-issuer-did-agrees.json",
        gate_document(
            {"id": HUB.did, "name": "legacy-hub", "publicKeyJwk": HUB.public_key_jwk()},
            key=HUB,
            doc_id="urn:uuid:00000fed-1e6a-4c11-8f00-000000000009",
        ),
    )
    vector(
        "valid/awr1-legacy-issuer-did-agrees",
        "valid/awr1-legacy-issuer-did-agrees.json",
        "document",
        "valid",
        [],
        ["AWR-LEGACY-001", "AWR-LEGACY-004"],
        None,
        ["legacy", "awr1", "AWR-LEGACY-001", "AWR-LEGACY-004", "section-12.4",
         "unsigned-issuer", "control"],
        "The control for AWR-KEY-003: a genuine AWR/1 document whose issuer.id did:key and "
        "whose embedded publicKeyJwk name the same key, and whose signature verifies under "
        "it. Section 12.4's cross-check must not reject this -- an implementation that "
        "fails it rejects the honest corpus the annex exists to keep readable. "
        "AWR-LEGACY-004 is still reported, because the key came from the document and "
        "therefore attests no issuer: the result names a KEY (legacy.verifiedKey), never "
        "an issuer, and legacy.issuerAttested is false.",
        now=NOW,
        note="Signed with the hub seed over legacy_canonical_form(credentialSubject, 'A').",
    )


# ---------------------------------------------------------------------------
# canonicalization vectors
# ---------------------------------------------------------------------------


def canonicalization_vector(
    name: str,
    value: Any,
    tags: Sequence[str],
    why: str,
    *,
    ascii_only: bool = False,
    text: Optional[str] = None,
) -> None:
    """Write an input file, its exact canonical bytes, and the manifest entry."""
    input_file = "canonicalization/%s.json" % (name,)
    canonical_file = "canonicalization/%s.canonical" % (name,)
    if text is not None:
        write_text(input_file, text)
        value = strict_loads(text)
    else:
        write_json(input_file, value, ascii_only=ascii_only)
    canonical = canonicalize(value)
    write_bytes(canonical_file, canonical)
    vector(
        "canonicalization/%s" % (name,),
        input_file,
        "canonicalization",
        "valid",
        [],
        [],
        None,
        list(tags),
        why,
        canonicalFile=canonical_file,
        canonicalHex=canonical.hex(),
        canonicalLength=len(canonical),
        digestSRI=sri_encode(hashlib.sha256(canonical).digest()),
    )


def canonicalization_negative(
    name: str, text: str, codes: Sequence[str], tags: Sequence[str], why: str
) -> None:
    input_file = "canonicalization/%s.json" % (name,)
    write_text(input_file, text)
    vector(
        "canonicalization/%s" % (name,),
        input_file,
        "canonicalization",
        "invalid",
        codes,
        [],
        None,
        list(tags),
        why,
    )


def build_canonicalization(built: Dict[str, Any]) -> None:
    canonicalization_vector(
        "key-order-ascii",
        {
            "é": "e-acute",
            "Z": 1,
            "a": 2,
            "A": 3,
            "z": 4,
            "10": 5,
            "2": 6,
            "": "empty name",
            "_": 7,
            "~": 8,
        },
        ["section-4.1", "key-order", "ascii"],
        "Property names sorted as unsigned UTF-16 code units: the empty name first, then "
        "digits, uppercase, underscore, lowercase, tilde, then U+00E9. It catches a "
        "canonicalizer that sorts case-insensitively or with a locale collation -- both "
        "produce plausible-looking output and a different signature.",
    )
    canonicalization_vector(
        "key-order-non-bmp",
        {
            "b": 2,
            "a": 1,
            "￿": 3,
            "\U0001f600": 4,
            "\U00010000": 5,
            "é": 6,
            "": 7,
            "nested": {"\U0001f9ea": 1, "￿": 2, "b": 3},
        },
        ["section-4.1", "key-order", "non-bmp", "utf-16"],
        "The divergence RFC 8785 section 3.2.3 exists to pin: U+10000 and U+1F600 begin "
        "with surrogates D800 and D83D, which sort BELOW U+E000 and U+FFFF as UTF-16 code "
        "units and ABOVE them as code points. Any implementation using its language's "
        "default string comparison produces the code-point order and a different digest "
        "for this exact input.",
    )
    canonicalization_vector(
        "escapes-all-forms",
        {
            "two-char": "\b\t\n\f\r\"\\",
            "c0-controls": "".join(
                chr(c) for c in range(0x20) if c not in (0x08, 0x09, 0x0A, 0x0C, 0x0D)
            ),
            "not-escaped": "/ \u007f \u0080 \u009f \u00a0 ' < > &",
            "mixed": "line1\nline2\ttabbed \"quoted\" back\\slash",
        },
        ["section-4.1", "escaping"],
        "Every escape form at once: the seven two-character escapes, the remaining C0 "
        "controls as LOWERCASE \\u00xx, and the characters implementations escape without "
        "being asked -- forward slash, U+007F, U+0080..U+009F, U+00A0, apostrophe, "
        "angle brackets and ampersand. Uppercase hex or an HTML-safe escaper changes the "
        "bytes without changing the meaning, which is the whole failure mode.",
        ascii_only=True,
    )
    # Built with explicit escapes: an editor or a filesystem that normalises this source
    # file would otherwise silently destroy the only vector that tests for normalisation.
    nfc_keys = {
        "nfc-string": "\u00e9\u00c5\u00f6\u01e0",
        "nfd-string": "e\u0301A\u030ao\u0308G\u0304\u0307",
        "hangul-nfc": "\ud55c\uae00",
        "hangul-nfd": "\u1112\u1161\u11ab\u1100\u1173\u11af",
        "nfkc-bait": "\ufb01 \u2460 \uff21",
        "e\u0301-key": "a DECOMPOSED object name",
        "\u00e9-key": "a PRECOMPOSED object name -- NFC would collide it with the previous one",
    }
    if len(nfc_keys) != 7:  # pragma: no cover - the source was normalised
        raise SystemExit("the NFC vector lost a key: this source file was normalised")
    canonicalization_vector(
        "no-nfc-normalization",
        nfc_keys,
        ["section-4.1", "no-nfc", "AWR-CANON-006", "unicode"],
        "THE vector for the legacy NFC deviation (Appendix D). Strings and object NAMES in "
        "both NFC and NFD, plus NFKC bait (U+FB01, U+2460, U+FF21). Section 4.1 item 2 "
        "requires string data preserved as-is, so the canonical bytes here contain both "
        "sequences unchanged and both names separately -- an implementation that "
        "normalizes either COLLIDES the two names, which is a lossy transformation of a "
        "signed document and is what AWR-CANON-006 reports.",
    )
    canonicalization_vector(
        "empty-containers",
        {
            "emptyObject": {},
            "emptyArray": [],
            "arrayOfEmpty": [{}, [], [[]], [{}]],
            "objectOfEmpty": {"a": {}, "b": [], "c": {"d": {}}},
            "emptyString": "",
            "nullValue": None,
        },
        ["section-4.1", "empty-containers", "structure"],
        "Empty objects, empty arrays, nested empties, the empty string and null. RFC 8785 "
        "emits {} and [] with no whitespace and keeps them; a canonicalizer that prunes "
        "empty members -- a common \"cleanup\" in serializers -- changes the signed bytes "
        "of any document that carries one.",
    )
    canonicalization_vector(
        "nesting-mixed",
        {
            "level1": {
                "array": [
                    1,
                    "two",
                    True,
                    None,
                    {"z": 1, "a": [{"deep": [[[{"deepest": "value"}]]]}]},
                ],
                "object": {"c": {"b": {"a": {"": "empty key at depth 4"}}}},
            },
            "arrayOfObjects": [{"b": 1, "a": 2}, {"a": 3, "b": 4}],
        },
        ["section-4.1", "nesting", "array-order"],
        "Arrays inside objects inside arrays, five levels deep, with keys out of order at "
        "every level and an empty key at depth four. Array order is DATA and must not be "
        "sorted; object order is not. An implementation that sorts recursively without "
        "distinguishing the two passes the flat vectors and fails this one.",
    )
    canonicalization_vector(
        "numbers-integer-bounds",
        {
            "zero": 0,
            "negativeZeroLiteral": 0,
            "one": 1,
            "minusOne": -1,
            "maxSafe": 9007199254740991,
            "minSafe": -9007199254740991,
            "smallish": 2340,
            "arrayOfIntegers": [0, -1, 1, 9007199254740991],
        },
        ["section-4.3", "numbers", "boundary"],
        "The integers section 4.3 permits, at both ends of the range. 2^53-1 MUST "
        "canonicalize as 9007199254740991; an implementation whose numbers are doubles "
        "emits 9007199254740992 or 9.007199254740991e15 and its signature disagrees with "
        "everyone else's. invalid/number-integer-2pow53 is the same boundary one step out.",
    )
    canonicalization_vector(
        "literals-and-strings",
        {
            "true": True,
            "false": False,
            "null": None,
            "arrayOfLiterals": [True, False, None],
            "stringTrue": "true",
            "stringNull": "null",
            "unicode-literal": "\u0430\u0431\u0432 \u4e2d\u6587 \U0001f600 \u2028\u2029",
        },
        ["section-4.1", "literals", "unicode"],
        "Literals next to strings that spell them, and U+2028/U+2029 -- which JavaScript "
        "serializers escape because they break JS string literals, and which RFC 8785 "
        "emits literally. A JS-derived canonicalizer produces \\u2028 here and a different "
        "digest for every document containing a line separator.",
    )

    unsecured = unsecured_document(built["minimal"])
    write_json("proof/worked-example-unsecured.json", unsecured)
    canonical = canonicalize(unsecured)
    write_bytes("canonicalization/worked-example-document.canonical", canonical)
    vector(
        "canonicalization/worked-example-document",
        "proof/worked-example-unsecured.json",
        "canonicalization",
        "valid",
        [],
        [],
        None,
        ["section-4", "section-6.2", "worked-example", "cross-check"],
        "The transformedDocument of Appendix A: the unsecured form of "
        "valid/receipt-minimal-l0. These are the exact bytes whose SHA-256 is the second "
        "half of hashData, so an implementation that matches every other canonicalization "
        "vector and still fails the signature has its defect in the proof steps rather "
        "than in the canonicalizer -- which is what section 6.2 asks the vectors to "
        "localise.",
        canonicalFile="canonicalization/worked-example-document.canonical",
        canonicalHex=canonical.hex(),
        canonicalLength=len(canonical),
        digestSRI=sri_encode(hashlib.sha256(canonical).digest()),
    )

    # -- negatives (section 4.4) -------------------------------------------
    canonicalization_negative(
        "neg-duplicate-key",
        '{\n  "a": 1,\n  "b": {"x": 1, "x": 2},\n  "c": 3\n}\n',
        ["AWR-CANON-004"],
        ["section-4.1", "AWR-CANON-004", "negative"],
        "A duplicate name in a nested object. Section 4.4 requires the canonicalizer "
        "itself to fail with the recorded code, not the document validator: by the time a "
        "document has been parsed last-wins, the choice of which bytes were signed has "
        "already been made silently.",
    )
    canonicalization_negative(
        "neg-lone-surrogate",
        '{\n  "text": "lone-\\ud800-surrogate"\n}\n',
        ["AWR-CANON-003"],
        ["section-4.1", "AWR-CANON-003", "negative", "unicode"],
        "A lone high surrogate as a \\u escape -- well-formed JSON text that denotes no "
        "Unicode string. Section 4.1 item 4 requires termination with an error; the "
        "tempting behaviour, substituting U+FFFD, produces canonical bytes for input that "
        "has no canonical form.",
    )
    canonicalization_negative(
        "neg-non-integer-number",
        '{\n  "latencyMs": 2340.5\n}\n',
        ["AWR-CANON-001"],
        ["section-4.3", "AWR-CANON-001", "negative", "numbers"],
        "A non-integer number reaching the canonicalizer directly. RFC 8785 specifies "
        "these precisely and implementations still disagree, so section 4.3 removes the "
        "class instead of arbitrating it -- including for the CLI's canonicalize "
        "subcommand, which is where a caller would otherwise get bytes AWR forbids.",
    )
    canonicalization_negative(
        "neg-integer-valued-float",
        '{\n  "latencyMs": 2340.0,\n  "alsoForbidden": 2.34e3\n}\n',
        ["AWR-CANON-001"],
        ["section-4.3", "AWR-CANON-001", "negative", "numbers", "awr1-dialects"],
        "2340.0 and 2.34e3 both denote the whole number 2340, and section 4.3 forbids the "
        "literal rather than the value, so both are AWR-CANON-001. This is the vector a "
        "canonicalizer that checks the parsed value instead of the received text fails: it "
        "emits 2340 for input AWR forbids, which is how the same document acquires two "
        "canonical forms and how AWR/1 acquired two dialects (section 12).",
    )
    canonicalization_negative(
        "neg-integer-out-of-range",
        '{\n  "big": 9007199254740992\n}\n',
        ["AWR-CANON-002"],
        ["section-4.3", "AWR-CANON-002", "negative", "boundary"],
        "2^53 exactly. It is a JSON integer, it is not representable exactly as a double, "
        "and section 4.3 excludes it. An implementation whose parser is double-backed "
        "cannot even detect the case, which is why the limit is stated rather than "
        "inferred.",
    )
    canonicalization_negative(
        "neg-not-json",
        '{\n  "a": 1,\n  "b": [1, 2,],\n}\n',
        ["AWR-CANON-005"],
        ["section-4", "AWR-CANON-005", "negative"],
        "Trailing commas in an array and an object: accepted by JSON5, by several "
        "hand-rolled parsers and by many editors' auto-formatters. Section 4 defines a "
        "canonical form for JSON, and text that is not JSON has none.",
    )


# ---------------------------------------------------------------------------
# the worked example (Appendix A)
# ---------------------------------------------------------------------------


def build_proof_vector(built: Dict[str, Any]) -> None:
    secured = copy.deepcopy(built["minimal"])
    unsecured = unsecured_document(secured)
    proof = secured["proof"]
    options = {k: v for k, v in proof.items() if k != "proofValue"}
    config = proof_config(options, unsecured)
    canonical_proof_config = canonicalize(config)
    transformed_document = canonicalize(unsecured)
    proof_config_hash, transformed_document_hash, hash_data_bytes = hash_data(
        unsecured, config
    )
    signature = HUB.sign(hash_data_bytes)
    proof_value = encode_proof_value(signature)
    if proof_value != proof["proofValue"]:  # pragma: no cover
        raise SystemExit("re-signing the worked example did not reproduce its proofValue")

    write_json("proof/worked-example-secured.json", secured)
    write_json("proof/worked-example-proof-config.json", config)
    write_bytes("proof/worked-example-proof-config.canonical", canonical_proof_config)
    write_bytes("proof/worked-example-transformed-document.canonical", transformed_document)

    worked = {
        "$comment": [
            "SPEC.md Appendix A, generated by awr/vectors/generate.py.  Every value below "
            "was computed by running the reference implementation; none was transcribed.",
            "Reproduce with:  awr hashdata proof/worked-example-secured.json  and  "
            "awr canonicalize proof/worked-example-unsecured.json",
        ],
        "spec": {
            "document": "awr/SPEC.md",
            "version": "2.0.0",
            "sections": ["4", "5.1", "5.3", "6.1", "6.2", "Appendix A"],
        },
        "key": {
            "WARNING": "TEST KEY -- PUBLISHED, PUBLIC, AND WITHOUT ANY AUTHORITY. This "
            "seed is the Ed25519 TEST 1 secret key of RFC 8032 section 7.1, chosen "
            "precisely because it is already published in an IETF standard, so no secret "
            "was created to write this vector. It MUST NOT be used to issue a real AWR "
            "document, and a verifier MUST NOT treat this DID as trustworthy.",
            "source": "RFC 8032 section 7.1, TEST 1 secret key",
            "privateKeySeedHex": TEST_KEYS[0]["seedHex"],
            "publicKeyHex": TEST_KEYS[0]["publicKeyHex"],
            "publicKeyJwk": HUB.public_key_jwk(),
            "did": HUB.did,
            "verificationMethod": HUB.verification_method,
            "didKeyDerivation": {
                "multicodecHex": "ed01",
                "multibasePrefix": "z",
                "multicodecAndKeyHex": "ed01" + TEST_KEYS[0]["publicKeyHex"],
                "methodSpecificIdLength": len(HUB.did) - len("did:key:"),
            },
        },
        "payloads": {
            "$comment": "The application bytes whose digests the receipt carries. Section "
            "3.3 leaves the payload serialization to the issuer; recording the bytes is "
            "what makes inputDigest and outputDigest reproducible by a third party.",
            "input": {
                "utf8": PAYLOADS["prompt"].decode("utf-8"),
                "hex": PAYLOADS["prompt"].hex(),
                "digestSRI": SRI["prompt"],
            },
            "output": {
                "utf8": PAYLOADS["summary"].decode("utf-8"),
                "hex": PAYLOADS["summary"].hex(),
                "digestSRI": SRI["summary"],
            },
        },
        "unsecuredDocument": unsecured,
        "proofOptions": config,
        "canonicalProofConfig": canonical_proof_config.decode("utf-8"),
        "canonicalProofConfigHex": canonical_proof_config.hex(),
        "canonicalProofConfigLength": len(canonical_proof_config),
        "transformedDocument": transformed_document.decode("utf-8"),
        "transformedDocumentHex": transformed_document.hex(),
        "transformedDocumentLength": len(transformed_document),
        "proofConfigHash": proof_config_hash.hex(),
        "transformedDocumentHash": transformed_document_hash.hex(),
        "hashData": hash_data_bytes.hex(),
        "hashDataOrder": "hashData = proofConfigHash || transformedDocumentHash -- proof "
        "config FIRST (section 6.2 step 6). Both halves are 32 bytes, so the reversed "
        "concatenation is indistinguishable by length; "
        "invalid/hashdata-halves-swapped.json is a genuine signature over it.",
        "signatureHex": signature.hex(),
        "proofValue": proof_value,
        "securedDocument": secured,
        "securedDocumentDigestSRI": canonical_sri(secured),
        "files": {
            "securedDocument": "proof/worked-example-secured.json",
            "unsecuredDocument": "proof/worked-example-unsecured.json",
            "proofConfig": "proof/worked-example-proof-config.json",
            "canonicalProofConfig": "proof/worked-example-proof-config.canonical",
            "transformedDocument": "proof/worked-example-transformed-document.canonical",
        },
    }
    write_json("proof/worked-example.json", worked)
    vector(
        "proof/worked-example",
        "proof/worked-example.json",
        "proof",
        "valid",
        [],
        [],
        "L0",
        ["section-6.2", "appendix-a", "worked-example", "hash-order"],
        "Appendix A end to end: document, TEST key, canonicalProofConfig, "
        "transformedDocument, the two hashes, hashData and proofValue, each as text and as "
        "hex. Section 6.2 records them SEPARATELY so that a failing implementation is "
        "localised to one step instead of being told only that a signature did not "
        "verify.",
        now=NOW,
        securedFile="proof/worked-example-secured.json",
        unsecuredFile="proof/worked-example-unsecured.json",
        proofConfigFile="proof/worked-example-proof-config.json",
        proofConfigHash=proof_config_hash.hex(),
        transformedDocumentHash=transformed_document_hash.hex(),
        hashData=hash_data_bytes.hex(),
        proofValue=proof_value,
        transformedDocumentHex=transformed_document.hex(),
        canonicalProofConfigHex=canonical_proof_config.hex(),
    )


# ---------------------------------------------------------------------------
# index.json
# ---------------------------------------------------------------------------

SPEC_FINDINGS = [
    {
        "section": "11.2 AWR-CANON-006",
        "issue": "No document can trigger it. The registry calls it an implementation "
        "self-check failure and section 4.1 item 2 names it for a canonicalizer that "
        "applies NFC, which is a property of the implementation, not of any input.",
        "closedBy": "canonicalization/no-nfc-normalization and "
        "valid/receipt-decomposed-unicode: a normalizing implementation produces canonical "
        "bytes different from the recorded ones and fails a signature its own issuer made. "
        "check_vectors.py additionally points the reference self-check at a deliberately "
        "NFC-applying canonicalizer and asserts the code fires.",
    },
    {
        "section": "8.2 AWR-CHAIN-004 / AWR-CHAIN-003",
        "issue": "A cycle in digests is not constructible -- an edge commits to the "
        "parent's exact bytes (8.1), so a digest cycle would be a SHA-256 fixed point. "
        "AWR-CHAIN-004 is therefore only reachable for a resolver that also locates "
        "parents by id, and any such cycle necessarily carries a digest mismatch as well.",
        "closedBy": "invalid/chain-cycle-self and invalid/chain-cycle-three-node both list "
        "AWR-CHAIN-003 alongside AWR-CHAIN-004; the three-node vector also lists "
        "AWR-CHAIN-006, which is likewise structurally forced.",
    },
    {
        "section": "8.3 AWR-CHAIN-007",
        "issue": "\"A verifier SHOULD check this when both receipts are available and MUST "
        "report AWR-CHAIN-007 when they differ\" splits the obligation: performing the "
        "check is a SHOULD, reporting its outcome a MUST. An implementation that never "
        "binds outputDigest to inputDigest is therefore conformant and never emits the "
        "code, so no vector can require it of every implementation -- while a vector also "
        "cannot forbid it, because an implementation that does check is equally conformant.",
        "closedBy": "valid/chain-output-input-mismatch requires the warning: it exists for "
        "exactly this check, so an implementation is held to the SHOULD there. Everywhere "
        "the mismatch is incidental to the vector's purpose -- invalid/chain-cycle-three-"
        "node, whose hops all carry the same input/output pair -- the code is listed in "
        "allowedExtraWarnings instead. Section 8.3 should promote the check to a MUST or "
        "state that the report is conditional on having performed it.",
    },
    {
        "section": "3.2 vs 11.2",
        "issue": "3.2 says a verifier encountering a digest algorithm other than sha256 "
        "MUST report AWR-CHAIN-002, but inputDigest and outputDigest are bare SRI strings "
        "rather than reference objects and 11.2 gives them AWR-RCPT-001.",
        "closedBy": "invalid/outputdigest-sha512 fixes AWR-RCPT-001 for the bare fields; "
        "invalid/parents-digest-sha512 fixes AWR-CHAIN-002 for reference objects.",
    },
    {
        "section": "6.1 vs 11.1",
        "issue": "\"At least one proof MUST verify and every proof present MUST be either "
        "valid or reported\" cannot coexist with \"valid iff reasons has no error entry\" "
        "if a failing proof's AWR-PROOF-006 lands in reasons.",
        "closedBy": "valid/receipt-proof-array fixes the reading that one verifying proof "
        "makes the document valid and that the failing proof is reported outside reasons.",
    },
    {
        "section": "11.2 AWR-TIME-001",
        "issue": "\"beyond the caller's skew allowance\" names no default and section 17 "
        "exposes no flag for it, so two conformant CLIs can disagree about whether the "
        "warning appears for identical input.",
        "closedBy": "valid/receipt-validfrom-future puts validFrom five months ahead of "
        "--now, which is beyond any plausible skew allowance; no vector exercises the "
        "boundary, because the specification does not define one.",
    },
    {
        "section": "10.1 / 11.1",
        "issue": "L0 is defined as \"a single valid WorkReceipt\", but 11.1 says \"valid "
        "without a profile means L0 only\" -- which leaves the reported profile of a valid "
        "VerificationVerdict or BlameAttestation undefined. The reference reported \"L0\" "
        "and the two other implementations reported null.",
        "closedBy": "SETTLED IN THE SPEC. Section 10.4 now states that the profile of a "
        "document which is not a WorkReceipt is null: the levels are levels of assurance "
        "about a unit of work, and profile: null with valid: true does not mean \"below "
        "L0\". The reference was changed to match the other two. check_vectors.py asserts "
        "it for every valid non-receipt vector.",
    },
    {
        "section": "6.3 / 11.2, no code for \"signature not checked\"",
        "issue": "The registry has AWR-PROOF-006 for \"Ed25519 signature verification "
        "failed\" and no code for \"the signature could not be checked\". Whenever an "
        "earlier step of 6.3 makes the check impossible -- no derivable key (step 3), or a "
        "document that cannot be canonicalized (step 5) -- 11.1's \"report all errors it "
        "can determine\" and the registry's wording pull in opposite directions. Two "
        "implementations written from this text disagreed on exactly these six documents.",
        "closedBy": "SETTLED IN THE SPEC. Section 6.3 now states that AWR-PROOF-006 means "
        "the signature was checked and did not verify, that the code of the step which "
        "prevented the check is the report, and that PROOF-006 MUST NOT be added on top -- "
        "with a fail-closed rule so that skipping step 6 can never produce valid: true. The "
        "registry needs no new code: the preventing step already has a more specific one. "
        "The allowedExtraCodes permission is withdrawn from all six vectors "
        "(invalid/string-lone-surrogate, invalid/issuer-bare-string, "
        "invalid/issuer-not-did-key, invalid/didkey-base64-truncation, "
        "invalid/didkey-wrong-key-length, invalid/didkey-x25519), so the code set is now "
        "exact and all three implementations were changed to match: the reference dropped "
        "PROOF-006 on the lone-surrogate document, and the Rust and browser builds dropped "
        "it on the five key documents.",
    },
    {
        "section": "4.3 vs 11.1",
        "issue": "Section 4.3 says a verifier MUST reject a document containing a "
        "forbidden number with AWR-CANON-001/002, which for a strict parser aborts before "
        "any field is seen. Section 11.1 says a verifier MUST report all errors it can "
        "determine -- and an implementation whose parser can carry 2340.5 or 0.15 to the "
        "subject validator determines the field-level error too. Whether the extra code is "
        "required, permitted or forbidden is not stated.",
        "closedBy": "invalid/number-non-integer and invalid/number-integer-2pow53 permit "
        "AWR-RCPT-004; invalid/price-amount-json-float permits AWR-RCPT-002. The "
        "canonicalization code is required in all three, so an implementation that reports "
        "only the field error still fails.",
    },
    {
        "section": "10.4 / 11.1, profile of an invalid document",
        "issue": "Nothing says what `profile` holds when `valid` is false. 10.4 requires "
        "reporting \"the highest profile satisfied\"; 10.1 defines L0 as \"a single valid "
        "WorkReceipt\", which an invalid receipt is not; and 11.1's example shows "
        "valid: false with profile: null. It is implied, never stated, and a second "
        "implementation reported \"L0\" (and once \"L1\") for 14 documents it had itself "
        "just declared invalid -- a caller reading profile alone would see an assurance "
        "level on a document that failed verification.",
        "closedBy": "SETTLED IN THE SPEC. Section 10.4 now states outright that the profile "
        "of an invalid document is null, including when the signature verified and the only "
        "errors are semantic or chain-level -- which was the case the Rust build got wrong "
        "for all 14. check_vectors.py asserts it for every invalid vector.",
    },
    {
        "section": "8.2, whether a digest-mismatched parent is traversed",
        "issue": "Section 8.2 requires cycle detection (AWR-CHAIN-004) but never says how a "
        "resolver locates a parent. Every constructible cycle passes through an edge whose "
        "digest does not match, because an edge commits to the parent's exact bytes (8.1) "
        "and a matching cycle would be a SHA-256 fixed point. So a resolver that refuses "
        "to walk through a parent whose digest failed -- defensible, arguably safer, since "
        "the child never committed to those bytes -- never constructs a cycle and "
        "AWR-CHAIN-004 becomes dead code. A second implementation did exactly this and "
        "reported only AWR-CHAIN-003 on both cycle vectors.",
        "closedBy": "SETTLED IN THE SPEC. Section 8.2 now has a \"Locating a parent\" "
        "paragraph: resolution is by digest first; when no supplied document carries the "
        "committed digest but one carries the edge's id, the verifier MUST report "
        "AWR-CHAIN-003, MUST count the edge unresolved, and MUST still traverse that "
        "document for cycle, AWR-CHAIN-006 and limit detection -- because otherwise "
        "AWR-CHAIN-004 is unreachable. Cycle detection keys on document id. The Rust and "
        "browser builds were changed accordingly and both now report AWR-CHAIN-003 and "
        "AWR-CHAIN-004 on the two cycle vectors, as the reference always did.",
    },
    {
        "section": "12",
        "issue": "The AWR/1 pipe-delimited rendering is not defined: no separator, no rule "
        "for nesting or arrays, no escaping, no rendering for null or booleans. Two blind "
        "implementations cannot agree, so AWR/1 verification is not independently "
        "implementable from the spec text.",
        "closedBy": "SETTLED IN THE SPEC. Section 12.1 now writes the layout out as a "
        "grammar -- leaves as path=leaf entries joined by |, dotted paths with array "
        "indices, empty containers contributing no entry, entries sorted by whole path in "
        "code-point order, NFC strings unquoted, null as `null`, ten fractional digits for "
        "non-integer numbers with trailing zeros kept, and the rendering undefined (hence "
        "AWR-LEGACY-002) outside |x| < 10^15. Section 12.2 fixes where the key comes from "
        "and that a bad proofValue is AWR-PROOF-005 while AWR-KEY-001 covers \"no usable "
        "key\". The browser verifier implemented an entirely different rendering "
        "(key:value pairs, JSON-quoted nested blobs, Python-style True/None) and therefore "
        "verified neither AWR/1 vector; it now agrees byte-for-byte with the other two.",
    },
    {
        "section": "17",
        "issue": "The CLI contract has no flag for the section 8.2 depth and node limits, "
        "so a depth-limit vector can only exercise the DEFAULT of 64, and the node limit "
        "of 1024 cannot be exercised without a 1025-document bundle.",
        "closedBy": "SETTLED IN THE SPEC. Section 17 now defines --max-depth and "
        "--max-nodes, so both halves of AWR-CHAIN-005 are reachable: "
        "invalid/chain-depth-limit-exceeded breaches the default depth with 66 receipts, "
        "and invalid/chain-node-limit-exceeded breaches a node limit of 2 with a four-hop "
        "chain. partiallyCoveredCodes is now empty.",
    },
    {
        "section": "9 / 17",
        "issue": "Section 9 requires the subject of a bundle to be identified \"by "
        "explicit caller argument\", and section 17's CLI defines no such argument; it "
        "offers only --parents, which is also the only channel for the verdicts L1/L2 "
        "need.",
        "closedBy": "SETTLED IN THE SPEC. Section 17 now names the flag --subject <id> "
        "normatively, precisely because a harness that has to guess it cannot drive two "
        "implementations from one manifest. Entries carry \"supporting\" (--parents) and "
        "\"subjectId\" (--subject); all three implementations spell it the same way.",
    },
    {
        "section": "4.3, literal or value",
        "issue": "\"Non-integer JSON numbers MUST NOT appear\" did not say whether the "
        "restriction is on the literal or on the value it denotes, so `2340.0` was "
        "undecided. It matters more than any other case in this list: an implementation "
        "that checks the parsed value cannot see it at all, because an IEEE-754 double "
        "parses 2340 and 2340.0 to the same number. The browser verifier accepted `2340.0` "
        "and canonicalized it to `2340` -- reproducing, in AWR/2, the exact defect that "
        "split AWR/1 into two dialects (Appendix D).",
        "closedBy": "SETTLED IN THE SPEC. Section 4.3 now states that the restriction is on "
        "the literal, that a fraction or exponent part is forbidden whatever it denotes, and "
        "that the check MUST be lexical and applied to the received bytes rather than "
        "delegated to a numeric type. Two new vectors hold every implementation to it: "
        "invalid/number-integer-valued-float (2340.0 in a signed receipt) and "
        "canonicalization/neg-integer-valued-float (2340.0 and 2.34e3 straight into the "
        "canonicalizer). The browser verifier now enforces §4.3 in its pre-parse scanner, "
        "which is the only place in JavaScript where it can be enforced.",
    },
    {
        "section": "11.1 / 11.2, one severity per code",
        "issue": "11.1 gave each reason entry a severity and 11.2 gave each code one, but "
        "nothing said the two must agree. The browser verifier used that gap to report "
        "error-severity codes at warning severity -- AWR-PROFILE-001 on every receipt "
        "verified without --profile, AWR-PROOF-006 to say which proof of an array verified, "
        "AWR-BUNDLE-002 for a bundled document that was itself invalid, AWR-CHAIN-001 for "
        "AWR/1 parent strings. Every one of those is defensible as information and destroys "
        "comparability: `valid` stops being a function of the codes reported, and a caller "
        "cannot tell a downgraded error from a real warning.",
        "closedBy": "SETTLED IN THE SPEC. Section 11.1 now states that every code has "
        "exactly one severity, the one 11.2 gives it, and that a code MUST NOT appear on the "
        "other side. Section 6.1 says which proof verified goes in the `verifiedProof` "
        "member of the result, not in a reason code, and 10.4 gates AWR-PROFILE-* on the "
        "caller having requested a profile while explicitly keeping AWR-L2-001 ungated. "
        "check_vectors.py already cross-checked every reported code's severity against "
        "SPEC.md 11.2, which is what caught all four.",
    },
    {
        "section": "5.1, AWR-KEY-002 vs AWR-KEY-004",
        "issue": "5.1 said a verifier MUST report AWR-KEY-002 \"on any deviation\" from "
        "ed25519-pub, while 11.2 also registers AWR-KEY-004 \"unsupported key type\" -- so "
        "a well-formed did:key for an x25519 key had two codes and no rule. The browser "
        "verifier reported AWR-KEY-002 where the other two reported AWR-KEY-004.",
        "closedBy": "SETTLED IN THE SPEC. Section 5.1 now separates them: a recognised "
        "multicodec that is not ed25519-pub is AWR-KEY-004 (a version problem), while a bad "
        "multibase, an undecodable payload, an unrecognised multicodec or a key length other "
        "than 32 bytes is AWR-KEY-002 (a corruption problem), and a document MUST NOT be "
        "reported as both. invalid/didkey-x25519 and invalid/didkey-wrong-key-length pin the "
        "two sides.",
    },
    # ---------------------------------------------------------------------------------
    # Found by comparing the WHOLE section 11.1 result across the three implementations
    # rather than only the code sets this manifest pins.  Every entry below was invisible
    # to check_vectors.py until it began asserting the result invariants: all 106 vectors
    # passed in all three builds while the three disagreed on 75 results.
    # ---------------------------------------------------------------------------------
    {
        "section": "11.1, verifiedProof in the single-proof case",
        "issue": "\"verifiedProof is OPTIONAL and holds the zero-based index of the proof "
        "that verified. It is REQUIRED when the document carried an array of proofs and one "
        "of them verified\" left the single-proof case free, so the reference reported null "
        "and the Rust and browser builds reported 0 for the same valid document -- 47 of the "
        "106 vectors. A caller could not read the member without knowing which "
        "implementation produced the result.",
        "closedBy": "SETTLED IN THE SPEC. Section 11.1 now makes verifiedProof REQUIRED "
        "whenever 6.3 step 6 was performed and succeeded, whether proof was one object or an "
        "array, and states the equivalence in both directions: null when the result carries "
        "any AWR-CANON-*, AWR-KEY-* or AWR-PROOF-* code, AWR-DOC-001, AWR-DOC-010, "
        "AWR-LEGACY-001, or a bundle code meaning no subject was identified; the index "
        "otherwise. All three builds were wrong in one direction or the other -- the "
        "reference reported 0 beside AWR-PROOF-002/004, the other two beside AWR-KEY-003 -- "
        "and each now derives the member from the codes reported instead of trusting the "
        "call site. check_vectors.py asserts the equivalence on every vector.",
    },
    {
        "section": "11.1, what `chain` counts",
        "issue": "The result carries chain.resolved/unresolved and nothing said what an "
        "\"edge\" is there. Section 8.1 defines a chain edge as a `parents` entry, but a "
        "verdict's verifiedWork and a blame's chain/blamedWork are digest references too, "
        "and the browser verifier counted them: a standalone VerificationVerdict reported "
        "one unresolved hop on a document that names no hop, which is the opposite of the "
        "\"chain intact\" vs \"chain not checked\" distinction 8.2 gives the member.",
        "closedBy": "SETTLED IN THE SPEC. Section 11.1 now states that chain counts 8.1 "
        "`parents` edges and nothing else, that verifiedWork and chain/blamedWork MUST NOT "
        "be counted -- their outcome is AWR-VDCT-005 and AWR-BLAME-001 -- and that an entry "
        "which is not a well-formed digest reference (AWR-CHAIN-001/002) is counted in "
        "neither total, since it never entered resolution. The browser build was changed on "
        "both points; a sha512 parents edge used to count as one unresolved edge.",
    },
    {
        "section": "11.1, awrVersion and documentType",
        "issue": "Nothing said whether awrVersion reports the DOCUMENT's version or the one "
        "the verifier implements, and all three answered differently for an AWR/1 document, "
        "which carries no awrVersion at all: the reference null, the Rust build its own "
        "\"2.0.0\", the browser build the invented string \"1\" -- with documentType "
        "\"AIProvenanceReceipt\", a name that appears in no document. A verifier printing "
        "its own version there answers \"2.0.0\" for a document that is not an AWR/2 "
        "document, which is the one question the member exists to answer.",
        "closedBy": "SETTLED IN THE SPEC. Section 11.1 now states that both members report "
        "what the document carries and null when it carries nothing, that a verifier MUST "
        "NOT substitute a value the document does not contain, that documentType is null "
        "when `type` names more than one AWR type (AWR-DOC-005), and that both are null "
        "whenever any AWR-CANON-* code is reported -- a document with no canonical form has "
        "no confirmed content, and leaving the two free made them a property of the parser's "
        "architecture rather than of the document: a strict lexical parser rejects 2340.0 "
        "before it sees `type` while a parser that carries the literal to the subject "
        "validator reads both, and the reverse holds for a lone surrogate. That is five "
        "documents on which three conformant verifiers answered three different things.",
    },
    {
        "section": "9, a bundle whose awrBundle version is unsupported",
        "issue": "Section 9 required awrBundle to be \"2.0\" and said every claim inside a "
        "bundle is verified individually, without saying whether a verifier may process the "
        "contents of a container version it does not support. Two implementations verified "
        "the receipt inside an awrBundle: \"1.0\" container and reported its documentType "
        "and verifiedProof; the third refused. All three reported AWR-BUNDLE-001, so no code "
        "set revealed the disagreement.",
        "closedBy": "SETTLED IN THE SPEC. Section 9 now fails closed: a verifier that finds "
        "an unsupported awrBundle MUST report AWR-BUNDLE-001 and MUST NOT process "
        "`documents`, reporting documentType: null and verifiedProof: null. awrBundle is the "
        "only statement of the container's schema, so reaching into an unknown version to "
        "pull out things merely assumed to be documents is the verifier deciding for itself "
        "which bytes to read, which 4.2 and 13.5 forbid elsewhere -- and it is the same gate "
        "3.1 puts on awrVersion (AWR-DOC-009). The reference and the Rust build were changed "
        "to match invalid/bundle-version-unsupported.",
    },
    {
        "section": "11.1, additional result members",
        "issue": "\"MUST be a JSON object with at least\" plainly permits extra top-level "
        "members, but said nothing about `chain`, and the three builds put their extra "
        "reporting in different places: the reference a top-level chainEdges, the browser "
        "build depth/edges/nodes inside `chain`. Whether the inner object was closed was "
        "undecided, so a harness comparing results could not tell a permitted extra from a "
        "divergence.",
        "closedBy": "SETTLED IN THE SPEC. Section 11.1 now states that additional members "
        "MAY appear both at the top level and inside `chain`, that a consumer MUST ignore "
        "the ones it does not know, and that an additional member MUST NOT carry a reason "
        "code -- whose only homes are `reasons` and `warnings`, at the severity 11.2 gives "
        "it. No implementation changed; the comparison did.",
    },
    {
        "section": "11.1, documentType is not a signal about the signature",
        "issue": "Once verifiedProof was tied to \"no subject document was identified\", it "
        "was tempting to read documentType: null as that signal. It is not: a document "
        "naming two AWR types (AWR-DOC-005) has no determinable type while its proof "
        "verifies perfectly well.",
        "closedBy": "SETTLED IN THE SPEC. Section 11.1 says outright that the two MUST NOT "
        "be conflated and gives the case: documentType: null with verifiedProof: 0 is the "
        "correct result for invalid/type-two-awr-types.",
    },
]

UNREACHABLE_CODES = {
    "AWR-LEGACY-005": "Not reachable from any document: it reports that the CALLER "
    "declined section 12 (--no-legacy), which is a property of the invocation and not of "
    "the bytes, while every field of a vector entry describes a document. All three "
    "implementations cover it in their own tests, and it is reachable from the section 17 "
    "CLI as `verify valid/awr1-legacy-dialect-a.json --no-legacy`.",
    "AWR-CANON-006": "Not reachable from any input: it reports that the implementation's "
    "own canonicalizer is lossy (section 4.1 item 2, section 4.4). The NFC vectors are "
    "what make a lossy implementation fail; check_vectors.py proves the code fires by "
    "pointing the reference self-check at an NFC-applying canonicalizer.",
}

#: Empty.  Both halves of AWR-CHAIN-005 are now covered: the depth limit at its default of
#: 64 by invalid/chain-depth-limit-exceeded, and the node-count limit by
#: invalid/chain-node-limit-exceeded, which section 17's --max-nodes made reachable without
#: a 1025-document bundle.
PARTIALLY_COVERED_CODES: Dict[str, str] = {}


def build_index() -> Dict[str, Any]:
    codes_seen: Dict[str, List[str]] = {}
    for entry in VECTORS:
        for code in list(entry["expectedCodes"]) + list(entry["expectedWarnings"]):
            codes_seen.setdefault(code, []).append(entry["id"])
    return {
        "$comment": [
            "AWR/2 test vectors as a CONTRACT: every vector carries its expected outcome, "
            "the reason codes that MUST be reported, and a 'why' naming the attack or the "
            "divergence it exists to catch.",
            "A vector is only added together with its expected outcome. See README.md.",
            "Generated by awr/vectors/generate.py -- do not hand-edit either this file or "
            "any vector; regenerate.",
        ],
        "awrVersion": "2.0.0",
        "spec": "awr/SPEC.md",
        "generator": "awr/vectors/generate.py",
        "checker": "awr/vectors/check_vectors.py",
        "vectorCount": len(VECTORS),
        "determinism": {
            "clock": "Every entry carries \"now\"; pass it as the CLI's --now so that "
            "AWR-TIME-001/002 are deterministic (section 17).",
            "randomness": "None. Identifiers come from a counter, timestamps are "
            "literals, and Ed25519 is deterministic (RFC 8032), so regenerating produces "
            "byte-identical files.",
        },
        "keys": [
            {
                "name": entry["name"],
                "role": entry["role"],
                "source": entry["source"],
                "privateKeySeedHex": entry["seedHex"],
                "publicKeyHex": entry["publicKeyHex"],
                "did": KEYS[entry["name"]].did,
                "verificationMethod": KEYS[entry["name"]].verification_method,
            }
            for entry in TEST_KEYS
        ],
        "keyWarning": "TEST KEYS. Every seed above is a published Ed25519 test vector from "
        "RFC 8032 section 7.1; nothing here is secret and nothing here confers authority. "
        "They MUST NOT be used to issue a real AWR document, and a verifier MUST NOT treat "
        "these DIDs as trustworthy.",
        "payloads": {
            name: {
                "utf8": data.decode("utf-8"),
                "hex": data.hex(),
                "digestSRI": SRI[name],
            }
            for name, data in sorted(PAYLOADS.items())
        },
        "fields": {
            "id": "Stable vector identifier; also the path without its extension.",
            "file": "Path relative to awr/vectors/.",
            "kind": "document | bundle | canonicalization | proof.",
            "expect": "valid | invalid -- the value of \"valid\" in the section 11.1 "
            "result (for canonicalization vectors: whether the canonicalizer succeeds).",
            "expectedCodes": "Reason codes of severity error that MUST be reported. The "
            "set is exact: reporting a code that is not listed is a failure unless it is "
            "in allowedExtraCodes.",
            "expectedWarnings": "Reason codes of severity warning that MUST be reported, "
            "compared as a set (section 11.1 does not forbid repeating a code with "
            "different detail).",
            "profile": "The profile the vector is meant to be checked at, passed as "
            "--profile. null means check without a profile argument and assert nothing "
            "about the reported profile.",
            "tags": "Free-form labels: the section, the code, the attack class.",
            "why": "Mandatory. The attack or the divergence the vector exists to catch. A "
            "vector with no why does not belong in the set.",
            "now": "RFC 3339 UTC instant to pass as --now.",
            "maxNodes": "Chain node-count limit to pass as --max-nodes (section 17), "
            "overriding the section 8.2 default of 1024.",
            "maxDepth": "Chain depth limit to pass as --max-depth (section 17), overriding "
            "the section 8.2 default of 64.",
            "supporting": "Files to pass as --parents: chain parents, verdicts, the "
            "receipts a BlameAttestation refers to. Each is a document or a bundle.",
            "subjectId": "Bundle subject identifier, for the explicit-argument branch of "
            "section 9.",
            "allowedExtraCodes": "Error codes an implementation MAY additionally report "
            "because the specification does not settle the question; see specFindings.",
            "allowedExtraWarnings": "As allowedExtraCodes, for warnings.",
            "note": "How the file was built when it could not be produced by signing "
            "alone -- the defect, and what was actually signed.",
            "canonicalFile": "Canonicalization vectors: the file holding the exact "
            "expected canonical bytes (no trailing newline).",
            "canonicalHex": "The same bytes as hex, so a mismatch is diagnosable "
            "byte-for-byte from the manifest alone.",
            "canonicalLength": "Length in bytes of the canonical form.",
            "digestSRI": "sha256-<base64> over the canonical bytes, i.e. what `awr digest` "
            "must print.",
            "securedFile / unsecuredFile / proofConfigFile": "Proof vectors: the three "
            "documents the section 17 CLI is run against.",
            "proofConfigHash / transformedDocumentHash / hashData / proofValue": "Proof "
            "vectors: the expected output of `awr hashdata`, in order, plus the signature.",
        },
        "specFindings": SPEC_FINDINGS,
        "unreachableCodes": UNREACHABLE_CODES,
        "partiallyCoveredCodes": PARTIALLY_COVERED_CODES,
        "codeIndex": {code: sorted(ids) for code, ids in sorted(codes_seen.items())},
        "vectors": VECTORS,
    }


def main() -> int:
    built = build_valid()
    build_invalid(built)
    build_canonicalization(built)
    build_proof_vector(built)
    # Last, so that it cannot shift any other vector's counter-derived identifier.
    build_legacy_gate(built)
    write_json("index.json", build_index())
    sys.stderr.write(
        "wrote %d files and %d manifest entries covering %d reason codes\n"
        % (
            len(WRITTEN),
            len(VECTORS),
            len(
                {
                    code
                    for entry in VECTORS
                    for code in entry["expectedCodes"] + entry["expectedWarnings"]
                }
            ),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
