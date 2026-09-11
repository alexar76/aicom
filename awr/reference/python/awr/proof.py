"""The ``eddsa-jcs-2022`` Data Integrity proof (SPEC.md section 6).

The one thing to get right here is step 6 of section 6.2:

    hashData = SHA-256(canonicalProofConfig) || SHA-256(transformedDocument)

**proof config first.**  The reverse order produces a signature that verifies against no
other implementation, and because both halves are 32 bytes there is nothing structural to
catch the mistake -- which is why ``hashdata`` is a CLI subcommand and why this module
returns the three values separately.
"""

from __future__ import annotations

import copy
from typing import Any, Dict, Optional, Tuple

from .digest import sha256
from .didkey import SigningKey, verify_signature
from .errors import AWR_PROOF_005, AwrError
from .jcs import canonicalize
from .multibase import multibase_decode_base58btc, multibase_encode_base58btc

PROOF_TYPE = "DataIntegrityProof"
CRYPTOSUITE = "eddsa-jcs-2022"
PROOF_PURPOSE = "assertionMethod"

SIGNATURE_LENGTH = 64


def unsecured_document(document: Dict[str, Any]) -> Dict[str, Any]:
    """*D*: the document with ``proof`` removed (section 6.2 step 3)."""
    return {key: value for key, value in document.items() if key != "proof"}


def proof_config(proof: Dict[str, Any], document: Dict[str, Any]) -> Dict[str, Any]:
    """*O*: the proof object without ``proofValue``, carrying the document ``@context``.

    Section 6.2 step 1: the proof options are canonicalized in the same context as the
    document, so the ``@context`` is copied in even when the serialized proof object does
    not carry one -- which is what a pre-2026-08 AWR/2 document looks like.  Section 6.2
    step 9 now requires an issuer to *emit* that same value in the proof, so for a freshly
    issued document this copy is a no-op; it stays because the copy is what makes the
    older documents verify unchanged.
    """
    config = {key: value for key, value in proof.items() if key != "proofValue"}
    if "@context" in document:
        config["@context"] = document["@context"]
    return config


def hash_data(
    unsecured: Dict[str, Any], config: Dict[str, Any]
) -> Tuple[bytes, bytes, bytes]:
    """Return ``(proofConfigHash, transformedDocumentHash, hashData)``."""
    canonical_proof_config = canonicalize(config)
    transformed_document = canonicalize(unsecured)
    proof_config_hash = sha256(canonical_proof_config)
    transformed_document_hash = sha256(transformed_document)
    return (
        proof_config_hash,
        transformed_document_hash,
        proof_config_hash + transformed_document_hash,
    )


def hash_data_for_document(document: Dict[str, Any]) -> Tuple[bytes, bytes, bytes]:
    """``hash_data`` for a document that already carries its ``proof`` object."""
    proof = document.get("proof")
    if isinstance(proof, list):
        if not proof:
            raise ValueError("document carries an empty proof array")
        proof = proof[0]
    if not isinstance(proof, dict):
        raise ValueError("document has no proof object to build proof options from")
    return hash_data(unsecured_document(document), proof_config(proof, document))


def encode_proof_value(signature: bytes) -> str:
    """``z`` + base58btc of the 64-byte signature (section 6.1)."""
    if len(signature) != SIGNATURE_LENGTH:
        raise ValueError(
            "an Ed25519 signature is %d bytes, got %d"
            % (SIGNATURE_LENGTH, len(signature))
        )
    return multibase_encode_base58btc(signature)


def decode_proof_value(value: Any) -> bytes:
    """Decode ``proofValue``.

    base64, hex and unprefixed values are rejected with ``AWR-PROOF-005``, including the
    AWR/1 base64 form -- accepting it in an AWR/2 document would let a legacy proof be
    presented as a current one.
    """
    if not isinstance(value, str):
        raise AwrError(
            AWR_PROOF_005,
            "proofValue must be a string, got %s" % type(value).__name__,
        )
    if not value.startswith("z"):
        raise AwrError(
            AWR_PROOF_005,
            "proofValue must be multibase base58btc with a 'z' prefix; %r is not "
            "(AWR/1 base64 proofValues are not accepted in AWR/2)" % (value[:8] + "...",),
        )
    try:
        signature = multibase_decode_base58btc(value)
    except ValueError as exc:
        raise AwrError(AWR_PROOF_005, "proofValue does not decode: %s" % (exc,))
    if len(signature) != SIGNATURE_LENGTH:
        raise AwrError(
            AWR_PROOF_005,
            "proofValue decodes to %d bytes, expected %d"
            % (len(signature), SIGNATURE_LENGTH),
        )
    return signature


def build_proof_options(
    key: SigningKey,
    created: str,
    *,
    purpose: str = PROOF_PURPOSE,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    proof = {
        "type": PROOF_TYPE,
        "cryptosuite": CRYPTOSUITE,
        "created": created,
        "verificationMethod": key.verification_method,
        "proofPurpose": purpose,
    }
    if extra:
        proof.update(copy.deepcopy(extra))
    return proof


def sign_document(
    document: Dict[str, Any],
    key: SigningKey,
    created: str,
    *,
    purpose: str = PROOF_PURPOSE,
    proof_extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Return a copy of *document* with a valid ``eddsa-jcs-2022`` proof attached.

    This is the low-level primitive: it signs exactly the bytes it is given and performs
    no semantic validation, so it can produce a document that is deliberately invalid
    (which the conformance negative vectors need).  ``awr.documents.issue`` is the
    validating entry point.

    The emitted proof carries ``@context`` (section 6.2 step 9) whenever the document has
    one.  The signature does not depend on it -- ``proof_config`` copies the document's
    value in either way -- but an off-the-shelf ``eddsa-jcs-2022`` verifier rebuilds the
    proof configuration from the *serialized* proof and nothing else, so a proof that does
    not carry it hashes a different configuration and reports "Invalid signature".
    """
    unsecured = unsecured_document(copy.deepcopy(document))
    options = build_proof_options(key, created, purpose=purpose, extra=proof_extra)
    config = proof_config(options, unsecured)
    _, _, message = hash_data(unsecured, config)
    signature = key.sign(message)
    secured = dict(unsecured)
    proof: Dict[str, Any] = {}
    if "@context" in unsecured:
        proof["@context"] = copy.deepcopy(unsecured["@context"])
    proof.update(options)
    proof["proofValue"] = encode_proof_value(signature)
    secured["proof"] = proof
    return secured


def verify_document_signature(
    document: Dict[str, Any], proof: Dict[str, Any], public_key_bytes: bytes
) -> bool:
    """Recompute ``hashData`` per section 6.3 steps 4-5 and check the signature."""
    signature = decode_proof_value(proof.get("proofValue"))
    unsecured = unsecured_document(document)
    config = proof_config(proof, unsecured)
    _, _, message = hash_data(unsecured, config)
    return verify_signature(public_key_bytes, signature, message)
