"""AWR/2 reference implementation.

AWR (Agent Work Receipt) defines three signed, self-contained W3C Verifiable Credentials
-- ``WorkReceipt``, ``VerificationVerdict``, ``BlameAttestation`` -- secured with an
``eddsa-jcs-2022`` Data Integrity proof over an RFC 8785 canonicalization and issued by a
``did:key``.  Verification needs no network, no registry and no issuer-specific software.

This package is the reference implementation of ``awr/SPEC.md`` version 2.0.0.  It is pure
standard library apart from ``cryptography`` for Ed25519, and it never opens a socket:
section 13.5 forbids a verifier from dereferencing anything.

Quick start::

    from awr import SigningKey, issue_work_receipt, verify_document

    key = SigningKey.generate()
    receipt = issue_work_receipt({
        "work": {
            "modelId": "claude-sonnet-5@anthropic",
            "completedAt": "2026-07-31T10:15:30Z",
            "status": "succeeded",
        },
        "inputDigest": "sha256-...",
        "outputDigest": "sha256-...",
    }, key)
    result = verify_document(receipt)
    assert result["valid"] and result["profile"] == "L0"

AWR/1 documents (``Ed25519Signature2018``, base64 ``proofValue``, signature over
``credentialSubject`` only) can be *verified* -- see :mod:`awr.legacy` -- and cannot be
issued: section 12 forbids it, so no code path in this package produces one.
"""

from __future__ import annotations

__version__ = "2.0.0"
__spec_version__ = "2.0.0"

from .digest import (  # noqa: E402
    canonical_digest,
    canonical_sri,
    is_valid_sri,
    parse_sri,
    sri_encode,
)
from .didkey import (  # noqa: E402
    SigningKey,
    derive_did_key,
    load_key_file,
    parse_did_key,
    verification_method_for,
)
from .documents import (  # noqa: E402
    AWR_CONTEXT,
    AWR_TYPES,
    AWR_VERSION,
    EMPTY_PAYLOAD_SRI,
    FAILURE_CLASSES,
    TYPE_BLAME_ATTESTATION,
    TYPE_VERIFICATION_VERDICT,
    TYPE_WORK_RECEIPT,
    VC_CONTEXT,
    VERDICTS,
    WORK_STATUSES,
    document_reference,
    issue,
    issue_blame_attestation,
    issue_verification_verdict,
    issue_work_receipt,
)
from .errors import REGISTRY, AwrError, Reasons, severity_of  # noqa: E402
from .jcs import canonical_self_check, canonicalize, loads  # noqa: E402
from .legacy import (  # noqa: E402
    LEGACY_DIALECTS,
    LEGACY_PROOF_TYPE,
    is_legacy_document,
    legacy_canonical_form,
)
from .multibase import b58decode, b58encode  # noqa: E402
from .proof import CRYPTOSUITE, PROOF_TYPE, hash_data, sign_document  # noqa: E402
from .verify import (  # noqa: E402
    DEFAULT_MAX_DEPTH,
    DEFAULT_MAX_NODES,
    make_bundle,
    resolve_chain,
    verify,
    verify_bundle,
    verify_document,
)

__all__ = [
    "AWR_CONTEXT",
    "AWR_TYPES",
    "AWR_VERSION",
    "AwrError",
    "CRYPTOSUITE",
    "DEFAULT_MAX_DEPTH",
    "DEFAULT_MAX_NODES",
    "EMPTY_PAYLOAD_SRI",
    "FAILURE_CLASSES",
    "LEGACY_DIALECTS",
    "LEGACY_PROOF_TYPE",
    "PROOF_TYPE",
    "REGISTRY",
    "Reasons",
    "SigningKey",
    "TYPE_BLAME_ATTESTATION",
    "TYPE_VERIFICATION_VERDICT",
    "TYPE_WORK_RECEIPT",
    "VC_CONTEXT",
    "VERDICTS",
    "WORK_STATUSES",
    "b58decode",
    "b58encode",
    "canonical_digest",
    "canonical_self_check",
    "canonical_sri",
    "canonicalize",
    "derive_did_key",
    "document_reference",
    "hash_data",
    "is_legacy_document",
    "is_valid_sri",
    "issue",
    "issue_blame_attestation",
    "issue_verification_verdict",
    "issue_work_receipt",
    "legacy_canonical_form",
    "load_key_file",
    "loads",
    "make_bundle",
    "parse_did_key",
    "parse_sri",
    "resolve_chain",
    "severity_of",
    "sign_document",
    "sri_encode",
    "verification_method_for",
    "verify",
    "verify_bundle",
    "verify_document",
    "__version__",
]
