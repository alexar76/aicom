"""AWR/1 legacy verification (SPEC.md section 12).

AWR/1 documents carry ``Ed25519Signature2018``, a base64 ``proofValue``, and a signature
over a pipe-delimited rendering of ``credentialSubject`` **only**.  Consequences that this
module enforces:

* ``id``, ``type``, ``issuer`` and any ``hubInfo`` are **unsigned** and are never reported
  as attested (section 12, section 13.1).
* Both canonical dialects are tried: **A** renders a JSON integer as ``2340``, **B**
  renders the same integer as ``2340.0``.  The dialects exist because the reference issuer
  was written in a language that distinguishes integers from floats and the reference
  verifier in one that does not.  Failure under both is ``AWR-LEGACY-002``.
* Every AWR/1 document produces the ``AWR-LEGACY-001`` warning.
* The legacy form applied NFC normalization and sorted keys by code point.  Both deviate
  from RFC 8785 and are part of the AWR/1 dialect only.

**There is no issuance path here, by construction.**  Section 12 forbids issuing AWR/1,
so this module exposes rendering (needed to verify) and verification, and nothing that
signs.

The exact byte layout of the "pipe-delimited rendering" is under-specified by section 12;
the reading implemented here is documented in the README and reported as a spec finding.
"""

from __future__ import annotations

import base64
import binascii
import unicodedata
from typing import Any, Dict, List, Optional, Tuple

from .didkey import (
    derive_did_key,
    optional_public_key_from_jwk,
    parse_did_key,
    verify_signature,
)
from .errors import (
    AWR_DOC_008,
    AWR_KEY_001,
    AWR_KEY_003,
    AWR_LEGACY_001,
    AWR_LEGACY_002,
    AWR_LEGACY_004,
    AWR_PROOF_005,
    AwrError,
    Reasons,
)

LEGACY_PROOF_TYPE = "Ed25519Signature2018"
AWR2_PROOF_TYPE = "DataIntegrityProof"

#: Fields that AWR/1 left outside its signature (section 12).
LEGACY_UNSIGNED_FIELDS = ("id", "type", "issuer", "hubInfo")

DIALECT_INTEGER_PRESERVING = "A"
DIALECT_FLOAT_COERCING = "B"
LEGACY_DIALECTS = (DIALECT_INTEGER_PRESERVING, DIALECT_FLOAT_COERCING)

#: Section 12.3, signal 2.  Either context URI is an AWR/2 claim: the VC 2.0 context
#: postdates AWR/1 (which was VC 1.1) and the AWR namespace names this specification.
AWR2_CONTEXT_URIS = (
    "https://www.w3.org/ns/credentials/v2",
    "https://verify.modelmarket.dev/ns/awr/v2",
)

#: Section 12.3, signals 4 and 5.  Envelope and subject members introduced by AWR/2.
#: ``credentialSubject.parents`` is deliberately absent: Appendix D records that AWR/1
#: carried ``parents`` too, as identifier strings, so it is not an AWR/2 claim.
AWR2_ENVELOPE_MEMBERS = ("validFrom", "validUntil")
AWR2_SUBJECT_MEMBERS = ("settlement",)

#: The three outcomes of the section 12.3 gate.
CLASS_AWR2 = "awr2"
CLASS_AWR1 = "awr1"
CLASS_DISAGREE = "disagree"


def _proof_objects(document: Any) -> List[Dict[str, Any]]:
    """Every proof object in *document*, whether ``proof`` is one object or an array.

    Section 12.3: the position of a proof in the array MUST NOT affect classification.
    Reading ``proof[0]`` -- which two of the three implementations did -- let an attacker
    choose the rule set by ordering the array.
    """
    if not isinstance(document, dict):
        return []
    proof = document.get("proof")
    if isinstance(proof, list):
        return [p for p in proof if isinstance(p, dict)]
    if isinstance(proof, dict):
        return [proof]
    return []


def awr2_signals(document: Any) -> List[str]:
    """The section 12.3 AWR/2 signals *document* carries, as human-readable names.

    The list is closed.  A signal one verifier honours and another ignores is a document
    the two disagree about, so nothing may be added here that section 12.3 does not name.
    """
    if not isinstance(document, dict):
        return []
    signals: List[str] = []
    if "awrVersion" in document:
        signals.append("awrVersion")
    context = document.get("@context")
    values = context if isinstance(context, list) else [context]
    for uri in AWR2_CONTEXT_URIS:
        if uri in values:
            signals.append("@context %s" % (uri,))
    for proof in _proof_objects(document):
        if proof.get("type") == AWR2_PROOF_TYPE:
            signals.append("proof.type DataIntegrityProof")
            break
    for member in AWR2_ENVELOPE_MEMBERS:
        if member in document:
            signals.append(member)
    subject = document.get("credentialSubject")
    if isinstance(subject, dict):
        for member in AWR2_SUBJECT_MEMBERS:
            if member in subject:
                signals.append("credentialSubject.%s" % (member,))
    return signals


def has_awr1_proof(document: Any) -> bool:
    """True when any proof object declares the AWR/1 suite (section 12.3)."""
    return any(p.get("type") == LEGACY_PROOF_TYPE for p in _proof_objects(document))


def classify_version(document: Any) -> str:
    """The section 12.3 gate: ``awr2``, ``awr1`` or ``disagree``.

    This runs *before* any verification.  Selecting the legacy path on ``proof.type``
    alone -- the reading every implementation arrived at from the earlier text -- is an
    unauthenticated forgery path: AWR/1 signs neither ``proof.type`` nor ``issuer``, so a
    document carrying ``awrVersion: "2.0.0"`` and a victim's DID could be verified under
    AWR/1 rules against a key the attacker supplied beside it.
    """
    awr1 = has_awr1_proof(document)
    awr2 = bool(awr2_signals(document))
    if awr1 and awr2:
        return CLASS_DISAGREE
    if awr1:
        return CLASS_AWR1
    return CLASS_AWR2


def is_legacy_document(document: Any) -> bool:
    """True when *document* is to be verified under section 12.

    Note this is now narrower than "carries an AWR/1 proof": a document that also makes an
    AWR/2 claim is neither, and its caller must report ``AWR-LEGACY-003``.
    """
    return classify_version(document) == CLASS_AWR1


def _nfc(text: str) -> str:
    return unicodedata.normalize("NFC", text)


#: Section 12.1 defines the AWR/1 rendering only below 10^15.  Beyond it two languages print
#: the same double differently (scientific notation, digit counts), so the legacy form does
#: not exist there and a verifier reports ``AWR-LEGACY-002`` instead of choosing one.
LEGACY_NUMBER_RANGE = 10 ** 15


def _render_scalar(value: Any, dialect: str) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, (int, float)) and abs(value) >= LEGACY_NUMBER_RANGE:
        raise TypeError(
            "number %r is outside the range in which the AWR/1 rendering is defined "
            "(|x| < 10^15, section 12.1)" % (value,)
        )
    if isinstance(value, int):
        if dialect == DIALECT_FLOAT_COERCING:
            return repr(float(value))
        return str(value)
    if isinstance(value, float):
        if value == int(value):
            if dialect == DIALECT_FLOAT_COERCING:
                return repr(float(value))
            return str(int(value))
        # Appendix D records 10-decimal truncation in the legacy dialect.
        return "%.10f" % (value,)
    if isinstance(value, str):
        return _nfc(value)
    raise TypeError("unrenderable legacy scalar of type %s" % type(value).__name__)


def _flatten(value: Any, prefix: str, out: List[Tuple[str, str]], dialect: str) -> None:
    if isinstance(value, dict):
        # AWR/1 sorted keys by code point, which is Python's default string order.
        for key in sorted(value.keys()):
            child = _nfc(key) if prefix == "" else "%s.%s" % (prefix, _nfc(key))
            _flatten(value[key], child, out, dialect)
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            child = "%s.%d" % (prefix, index) if prefix else str(index)
            _flatten(item, child, out, dialect)
        return
    out.append((prefix, _render_scalar(value, dialect)))


def legacy_canonical_form(subject: Any, dialect: str) -> bytes:
    """The AWR/1 pipe-delimited rendering of ``credentialSubject``.

    ``path=value`` entries joined by ``|``, paths flattened with ``.`` (array indices
    included), sorted by code point, strings NFC-normalized, integers rendered per the
    dialect.
    """
    if dialect not in LEGACY_DIALECTS:
        raise ValueError("legacy dialect must be one of %s" % (LEGACY_DIALECTS,))
    if not isinstance(subject, dict):
        raise TypeError("legacy credentialSubject must be an object")
    entries: List[Tuple[str, str]] = []
    _flatten(subject, "", entries, dialect)
    entries.sort(key=lambda item: item[0])
    return "|".join("%s=%s" % (path, value) for path, value in entries).encode("utf-8")


def _decode_legacy_proof_value(value: Any) -> bytes:
    if not isinstance(value, str):
        raise AwrError(
            AWR_PROOF_005,
            "legacy proofValue must be a string, got %s" % type(value).__name__,
        )
    if value.startswith("z"):
        raise AwrError(
            AWR_PROOF_005,
            "an AWR/1 proofValue is base64, not multibase base58btc",
        )
    padded = value + "=" * (-len(value) % 4)
    try:
        signature = base64.b64decode(padded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise AwrError(AWR_PROOF_005, "legacy proofValue is not base64: %s" % (exc,))
    if len(signature) != 64:
        raise AwrError(
            AWR_PROOF_005,
            "legacy proofValue decodes to %d bytes, expected 64" % (len(signature),),
        )
    return signature


def legacy_public_key(document: Dict[str, Any]) -> Optional[bytes]:
    """Find the AWR/1 signing key *carried by the document* (section 12.2).

    AWR/1's ``issuer.id`` was ``did:key:`` plus the first 32 characters of the base64
    public key (Appendix D) and therefore names no key at all, so the key has to come from
    the document's embedded copy: ``issuer.publicKeyJwk``, or ``issuer.publicKeyBase64``.
    A document whose ``issuer.id`` happens to be a real ``did:key`` is also accepted.

    None of these is inside the AWR/1 signature.  A signature checked against a key found
    here establishes only that the file is internally consistent -- section 12.4 -- and
    the caller reports ``AWR-LEGACY-004`` to say so.
    """
    issuer = document.get("issuer")
    if isinstance(issuer, dict):
        from_jwk = optional_public_key_from_jwk(issuer.get("publicKeyJwk"))
        if from_jwk is not None:
            return from_jwk
        encoded = issuer.get("publicKeyBase64")
        if isinstance(encoded, str):
            padded = encoded + "=" * (-len(encoded) % 4)
            try:
                raw = base64.b64decode(padded, validate=True)
            except (binascii.Error, ValueError):
                raw = b""
            if len(raw) == 32:
                return raw
        issuer_id = issuer.get("id")
        if isinstance(issuer_id, str):
            try:
                return parse_did_key(issuer_id)
            except AwrError:
                return None
    return None


def key_named_by_issuer_id(document: Dict[str, Any]) -> Optional[bytes]:
    """The key ``issuer.id`` names, or None when it names none (section 12.4).

    A ``did:key`` bearing a ``#`` fragment -- the section 5.3 ``verificationMethod``
    string -- names the same key as the bare DID, and MUST be read as such: an
    implementation that parsed only the bare form let an attacker keep the victim's DID as
    a literal prefix of ``issuer.id`` while supplying their own ``publicKeyJwk``.
    """
    issuer = document.get("issuer")
    if not isinstance(issuer, dict):
        return None
    issuer_id = issuer.get("id")
    if not isinstance(issuer_id, str) or not issuer_id.startswith("did:key:"):
        return None
    try:
        return parse_did_key(issuer_id.split("#", 1)[0])
    except AwrError:
        return None


class LegacyOutcome(object):
    """What a section 12 verification established, in the terms section 12.4 requires."""

    __slots__ = ("verified", "dialect", "unsigned_fields", "key_source", "verified_key")

    def __init__(
        self,
        verified: bool,
        dialect: Optional[str],
        unsigned_fields: List[str],
        key_source: Optional[str],
        verified_key: Optional[str],
    ) -> None:
        self.verified = verified
        self.dialect = dialect
        self.unsigned_fields = unsigned_fields
        self.key_source = key_source
        self.verified_key = verified_key

    def as_result_member(self) -> Dict[str, Any]:
        """The section 12.4 ``legacy`` member of the section 11.1 result."""
        return {
            "dialect": self.dialect,
            "keySource": self.key_source,
            # A constant, and present *because* it is a constant: AWR/1 can never attest
            # an issuer, and a member that is always false is read while an absent one
            # is not.
            "issuerAttested": False,
            "verifiedKey": self.verified_key,
            "unsignedFields": self.unsigned_fields,
        }


def verify_legacy_document(
    document: Dict[str, Any],
    reasons: Reasons,
    expected_key: Optional[bytes] = None,
) -> LegacyOutcome:
    """Verify an AWR/1 document, in the fixed order of section 12.4.

    *expected_key* is the caller's out-of-band 32-byte Ed25519 public key.  When it is
    given it is the **only** key tried; document-carried key material is neither
    substituted for it nor used as a fallback.  ``AWR-LEGACY-001`` is always added.
    """
    reasons.add(
        AWR_LEGACY_001,
        "verified under the AWR/1 legacy rules (section 12): id, type, issuer and "
        "hubInfo are NOT covered by this signature and MUST NOT be reported as attested",
    )
    unsigned = [f for f in LEGACY_UNSIGNED_FIELDS if f in document]

    def fail(key_source: Optional[str] = None) -> LegacyOutcome:
        return LegacyOutcome(False, None, unsigned, key_source, None)

    subject = document.get("credentialSubject")
    if not isinstance(subject, dict):
        reasons.add(AWR_DOC_008, "credentialSubject must be a single object")
        return fail()

    proof = document.get("proof")
    if isinstance(proof, list):
        proof = next(
            (p for p in proof if isinstance(p, dict) and p.get("type") == LEGACY_PROOF_TYPE),
            None,
        )
    if not isinstance(proof, dict):
        reasons.add(AWR_LEGACY_002, "AWR/1 document has no proof object")
        return fail()

    # Section 12.4 step 3: the caller's key wins outright.
    if expected_key is not None:
        public_key = expected_key
        key_source = "caller"
    else:
        public_key = legacy_public_key(document)
        key_source = "document"
        if public_key is None:
            reasons.add(
                AWR_KEY_001,
                "AWR/1 document carries no usable public key: issuer.publicKeyJwk, "
                "issuer.publicKeyBase64 or a real did:key issuer.id is required, or "
                "an expected key supplied out of band (section 12.4)",
            )
            return fail(key_source)
        reasons.add(
            AWR_LEGACY_004,
            "the AWR/1 signature was checked against key material carried by the "
            "document itself, which the AWR/1 signature does not cover; this shows only "
            "that the file is internally consistent and attests NO issuer identity "
            "(section 12.4) -- supply the expected key out of band to learn who signed",
        )

    # Section 12.4 step 4: two disagreeing statements about the signer are an error.
    named = key_named_by_issuer_id(document)
    if named is not None and named != public_key:
        reasons.add(
            AWR_KEY_003,
            "issuer.id names %s but the AWR/1 signature was to be checked against %s; "
            "AWR/1 signs neither, so there is no way to tell which the issuer meant "
            "(section 12.4)" % (derive_did_key(named), derive_did_key(public_key)),
        )
        return fail(key_source)

    try:
        signature = _decode_legacy_proof_value(proof.get("proofValue"))
    except AwrError as err:
        reasons.add_error_obj(err)
        return fail(key_source)

    for dialect in LEGACY_DIALECTS:
        try:
            message = legacy_canonical_form(subject, dialect)
        except TypeError as exc:
            reasons.add(AWR_LEGACY_002, "legacy rendering failed: %s" % (exc,))
            return fail(key_source)
        if verify_signature(public_key, signature, message):
            return LegacyOutcome(
                True, dialect, unsigned, key_source, derive_did_key(public_key)
            )

    reasons.add(
        AWR_LEGACY_002,
        "signature verified under neither legacy dialect A (integer-preserving) nor "
        "dialect B (float-coercing)",
    )
    return fail(key_source)
