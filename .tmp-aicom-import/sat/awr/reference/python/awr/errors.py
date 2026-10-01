"""Reason-code registry and the single exception type of the AWR reference implementation.

The registry is a transcription of AWR/2 SPEC.md section 11.2.  Codes are stable:
a code is never re-used for a different meaning (section 11.1).
"""

from __future__ import annotations

from typing import Dict, List, NamedTuple, Optional

SEVERITY_ERROR = "error"
SEVERITY_WARNING = "warning"


class ReasonSpec(NamedTuple):
    code: str
    severity: str
    meaning: str


# (code, severity, meaning) -- severity "warning" only where SPEC.md 11.2 marks it so.
_TABLE = (
    # Document
    ("AWR-DOC-001", SEVERITY_ERROR, "Not a JSON object"),
    ("AWR-DOC-002", SEVERITY_ERROR,
     "@context missing, not an array, or first element is not the VC 2.0 context"),
    ("AWR-DOC-003", SEVERITY_ERROR, "AWR namespace URI absent from @context"),
    ("AWR-DOC-004", SEVERITY_ERROR, "type missing VerifiableCredential"),
    ("AWR-DOC-005", SEVERITY_ERROR, "No AWR document type, or more than one, in type"),
    ("AWR-DOC-006", SEVERITY_ERROR, "id missing or not an absolute URI"),
    ("AWR-DOC-007", SEVERITY_ERROR,
     "validFrom missing or malformed; or validUntil not later than validFrom"),
    ("AWR-DOC-008", SEVERITY_ERROR, "credentialSubject missing or not a single object"),
    ("AWR-DOC-009", SEVERITY_ERROR,
     "awrVersion missing, malformed, or major version not implemented"),
    ("AWR-DOC-010", SEVERITY_ERROR, "issuer missing, not an object, or missing id"),
    # Canonicalization
    ("AWR-CANON-001", SEVERITY_ERROR, "Non-integer JSON number present"),
    ("AWR-CANON-002", SEVERITY_ERROR, "Integer outside +/-(2^53-1)"),
    ("AWR-CANON-003", SEVERITY_ERROR, "Invalid Unicode (lone surrogate) in string data"),
    ("AWR-CANON-004", SEVERITY_ERROR, "Duplicate object property name"),
    ("AWR-CANON-005", SEVERITY_ERROR, "Input is not well-formed JSON"),
    ("AWR-CANON-006", SEVERITY_ERROR,
     "Canonical form mismatch -- implementation self-check failed"),
    # Keys
    ("AWR-KEY-001", SEVERITY_ERROR, "issuer.id is not a did:key"),
    ("AWR-KEY-002", SEVERITY_ERROR,
     "did:key malformed: bad multibase, multicodec, or key length"),
    ("AWR-KEY-003", SEVERITY_ERROR, "publicKeyJwk inconsistent with did:key"),
    ("AWR-KEY-004", SEVERITY_ERROR, "Unsupported key type"),
    # Proof
    ("AWR-PROOF-001", SEVERITY_ERROR, "proof missing"),
    ("AWR-PROOF-002", SEVERITY_ERROR, "proof.type is not DataIntegrityProof"),
    ("AWR-PROOF-003", SEVERITY_ERROR, "Unsupported cryptosuite"),
    ("AWR-PROOF-004", SEVERITY_ERROR, "proofPurpose is not assertionMethod"),
    ("AWR-PROOF-005", SEVERITY_ERROR, "proofValue not multibase base58btc of 64 bytes"),
    ("AWR-PROOF-006", SEVERITY_ERROR, "Ed25519 signature verification failed"),
    ("AWR-PROOF-007", SEVERITY_ERROR, "verificationMethod does not match issuer.id"),
    ("AWR-PROOF-008", SEVERITY_ERROR, "proof.@context inconsistent with document @context"),
    ("AWR-PROOF-009", SEVERITY_ERROR, "proof.created missing or malformed"),
    # Receipt
    ("AWR-RCPT-001", SEVERITY_ERROR,
     "inputDigest or outputDigest missing or not a valid SRI string"),
    ("AWR-RCPT-002", SEVERITY_ERROR, "price malformed (currency or decimal-string amount)"),
    ("AWR-RCPT-003", SEVERITY_ERROR, "work timestamps missing or inconsistent"),
    ("AWR-RCPT-004", SEVERITY_ERROR, "work.latencyMs negative or not an integer"),
    ("AWR-RCPT-005", SEVERITY_ERROR, "work.modelId missing or empty"),
    ("AWR-RCPT-006", SEVERITY_ERROR, "work.status missing or not in the enumeration"),
    # Verdict
    ("AWR-VDCT-001", SEVERITY_ERROR, "verifiedWork missing, or missing id/digestSRI"),
    ("AWR-VDCT-002", SEVERITY_ERROR, "score not a decimal string in [0,1]"),
    ("AWR-VDCT-003", SEVERITY_ERROR, "method missing or method.id empty"),
    ("AWR-VDCT-004", SEVERITY_ERROR, "verdict not in the enumeration"),
    ("AWR-VDCT-005", SEVERITY_ERROR,
     "verifiedWork.digestSRI does not match the supplied receipt"),
    ("AWR-VDCT-006", SEVERITY_WARNING, "verdict inconsistent with score/threshold"),
    ("AWR-VDCT-007", SEVERITY_ERROR, "evidence entry without digestSRI"),
    # Blame
    ("AWR-BLAME-001", SEVERITY_ERROR,
     "blamedWork not reachable from chain through available receipts"),
    ("AWR-BLAME-002", SEVERITY_ERROR, "failureClass not in the enumeration"),
    ("AWR-BLAME-003", SEVERITY_ERROR, "chain or blamedWork missing or malformed"),
    ("AWR-BLAME-004", SEVERITY_ERROR, "confidence not a decimal string in [0,1]"),
    # Chain
    ("AWR-CHAIN-001", SEVERITY_ERROR, "parents entry missing digestSRI"),
    ("AWR-CHAIN-002", SEVERITY_ERROR, "Digest reference format or algorithm invalid"),
    ("AWR-CHAIN-003", SEVERITY_ERROR, "Parent digest mismatch against the supplied parent"),
    ("AWR-CHAIN-004", SEVERITY_ERROR, "Cycle detected"),
    ("AWR-CHAIN-005", SEVERITY_ERROR, "Depth or node limit exceeded"),
    ("AWR-CHAIN-006", SEVERITY_ERROR, "Same parent id with conflicting digests"),
    ("AWR-CHAIN-007", SEVERITY_WARNING, "Parent outputDigest != child inputDigest"),
    # Bundle
    ("AWR-BUNDLE-001", SEVERITY_ERROR,
     "awrBundle missing or unsupported, or documents empty"),
    ("AWR-BUNDLE-002", SEVERITY_ERROR, "Duplicate document id with differing content"),
    ("AWR-BUNDLE-003", SEVERITY_ERROR, "Subject document ambiguous"),
    # Profile
    ("AWR-PROFILE-001", SEVERITY_ERROR, "L1: no valid verdict for the receipt"),
    ("AWR-PROFILE-002", SEVERITY_ERROR, "L1: verdict issuer equals receipt issuer"),
    ("AWR-PROFILE-003", SEVERITY_ERROR, "L2: fewer than two distinct verdict issuers"),
    ("AWR-PROFILE-004", SEVERITY_ERROR, "L2: no settlement or stake binding present"),
    ("AWR-L2-001", SEVERITY_WARNING,
     "Accountability binding present but not checked on-chain"),
    # Environment, time, legacy
    ("AWR-ENV-001", SEVERITY_WARNING, "Attestation present and not verified"),
    ("AWR-TIME-001", SEVERITY_WARNING,
     "validFrom in the future beyond the caller's skew allowance"),
    ("AWR-TIME-002", SEVERITY_WARNING, "validUntil in the past"),
    ("AWR-LEGACY-001", SEVERITY_WARNING,
     "Document verified under the AWR/1 legacy rules (section 12)"),
    ("AWR-LEGACY-002", SEVERITY_ERROR,
     "AWR/1 document whose two legacy canonical dialects both failed"),
    ("AWR-LEGACY-003", SEVERITY_ERROR,
     "Version signals disagree: the document carries both an AWR/2 signal and an AWR/1 "
     "proof suite, and is verified under neither (section 12.3)"),
    ("AWR-LEGACY-004", SEVERITY_WARNING,
     "The AWR/1 signature was checked against key material carried by the document, "
     "which the AWR/1 signature does not cover; no issuer identity is attested "
     "(section 12.4)"),
    ("AWR-LEGACY-005", SEVERITY_ERROR,
     "AWR/1 verification declined: section 12 support is OPTIONAL and this verifier was "
     "asked not to apply it (section 12.3)"),
)

REGISTRY: Dict[str, ReasonSpec] = {}
for _code, _sev, _meaning in _TABLE:
    REGISTRY[_code] = ReasonSpec(_code, _sev, _meaning)
del _code, _sev, _meaning

# Convenience constants so that callers never spell a code as a bare literal.
for _spec in REGISTRY.values():
    globals()[_spec.code.replace("-", "_")] = _spec.code
del _spec

# Explicit names for static readers / linters.
AWR_DOC_001 = "AWR-DOC-001"
AWR_DOC_002 = "AWR-DOC-002"
AWR_DOC_003 = "AWR-DOC-003"
AWR_DOC_004 = "AWR-DOC-004"
AWR_DOC_005 = "AWR-DOC-005"
AWR_DOC_006 = "AWR-DOC-006"
AWR_DOC_007 = "AWR-DOC-007"
AWR_DOC_008 = "AWR-DOC-008"
AWR_DOC_009 = "AWR-DOC-009"
AWR_DOC_010 = "AWR-DOC-010"
AWR_CANON_001 = "AWR-CANON-001"
AWR_CANON_002 = "AWR-CANON-002"
AWR_CANON_003 = "AWR-CANON-003"
AWR_CANON_004 = "AWR-CANON-004"
AWR_CANON_005 = "AWR-CANON-005"
AWR_CANON_006 = "AWR-CANON-006"
AWR_KEY_001 = "AWR-KEY-001"
AWR_KEY_002 = "AWR-KEY-002"
AWR_KEY_003 = "AWR-KEY-003"
AWR_KEY_004 = "AWR-KEY-004"
AWR_PROOF_001 = "AWR-PROOF-001"
AWR_PROOF_002 = "AWR-PROOF-002"
AWR_PROOF_003 = "AWR-PROOF-003"
AWR_PROOF_004 = "AWR-PROOF-004"
AWR_PROOF_005 = "AWR-PROOF-005"
AWR_PROOF_006 = "AWR-PROOF-006"
AWR_PROOF_007 = "AWR-PROOF-007"
AWR_PROOF_008 = "AWR-PROOF-008"
AWR_PROOF_009 = "AWR-PROOF-009"
AWR_RCPT_001 = "AWR-RCPT-001"
AWR_RCPT_002 = "AWR-RCPT-002"
AWR_RCPT_003 = "AWR-RCPT-003"
AWR_RCPT_004 = "AWR-RCPT-004"
AWR_RCPT_005 = "AWR-RCPT-005"
AWR_RCPT_006 = "AWR-RCPT-006"
AWR_VDCT_001 = "AWR-VDCT-001"
AWR_VDCT_002 = "AWR-VDCT-002"
AWR_VDCT_003 = "AWR-VDCT-003"
AWR_VDCT_004 = "AWR-VDCT-004"
AWR_VDCT_005 = "AWR-VDCT-005"
AWR_VDCT_006 = "AWR-VDCT-006"
AWR_VDCT_007 = "AWR-VDCT-007"
AWR_BLAME_001 = "AWR-BLAME-001"
AWR_BLAME_002 = "AWR-BLAME-002"
AWR_BLAME_003 = "AWR-BLAME-003"
AWR_BLAME_004 = "AWR-BLAME-004"
AWR_CHAIN_001 = "AWR-CHAIN-001"
AWR_CHAIN_002 = "AWR-CHAIN-002"
AWR_CHAIN_003 = "AWR-CHAIN-003"
AWR_CHAIN_004 = "AWR-CHAIN-004"
AWR_CHAIN_005 = "AWR-CHAIN-005"
AWR_CHAIN_006 = "AWR-CHAIN-006"
AWR_CHAIN_007 = "AWR-CHAIN-007"
AWR_BUNDLE_001 = "AWR-BUNDLE-001"
AWR_BUNDLE_002 = "AWR-BUNDLE-002"
AWR_BUNDLE_003 = "AWR-BUNDLE-003"
AWR_PROFILE_001 = "AWR-PROFILE-001"
AWR_PROFILE_002 = "AWR-PROFILE-002"
AWR_PROFILE_003 = "AWR-PROFILE-003"
AWR_PROFILE_004 = "AWR-PROFILE-004"
AWR_L2_001 = "AWR-L2-001"
AWR_ENV_001 = "AWR-ENV-001"
AWR_TIME_001 = "AWR-TIME-001"
AWR_TIME_002 = "AWR-TIME-002"
AWR_LEGACY_001 = "AWR-LEGACY-001"
AWR_LEGACY_002 = "AWR-LEGACY-002"
AWR_LEGACY_003 = "AWR-LEGACY-003"
AWR_LEGACY_004 = "AWR-LEGACY-004"
AWR_LEGACY_005 = "AWR-LEGACY-005"


def severity_of(code: str) -> str:
    spec = REGISTRY.get(code)
    if spec is None:
        raise KeyError("unknown AWR reason code: %r" % (code,))
    return spec.severity


class AwrError(Exception):
    """An AWR failure carrying a registry reason code.

    Raised by the low-level primitives (canonicalization, did:key, digests).  The
    verification pipeline catches these and turns them into result entries, because
    section 11.1 requires *all* determinable errors to be reported, not the first.
    """

    def __init__(self, code: str, detail: str = "") -> None:
        spec = REGISTRY.get(code)
        if spec is None:
            raise KeyError("unknown AWR reason code: %r" % (code,))
        self.code = code
        self.detail = detail or spec.meaning
        self.severity = spec.severity
        super().__init__("%s: %s" % (self.code, self.detail))

    def as_reason(self) -> Dict[str, str]:
        return {"code": self.code, "severity": self.severity, "detail": self.detail}


class Reasons:
    """Accumulator that routes registry entries to `reasons` or `warnings`."""

    def __init__(self) -> None:
        self.errors: List[Dict[str, str]] = []
        self.warnings: List[Dict[str, str]] = []

    def add(self, code: str, detail: Optional[str] = None) -> None:
        spec = REGISTRY.get(code)
        if spec is None:
            raise KeyError("unknown AWR reason code: %r" % (code,))
        entry = {
            "code": code,
            "severity": spec.severity,
            "detail": detail if detail else spec.meaning,
        }
        target = self.warnings if spec.severity == SEVERITY_WARNING else self.errors
        if entry not in target:
            target.append(entry)

    def add_error_obj(self, err: AwrError) -> None:
        self.add(err.code, err.detail)

    def extend(self, other: "Reasons") -> None:
        for entry in other.errors:
            if entry not in self.errors:
                self.errors.append(entry)
        for entry in other.warnings:
            if entry not in self.warnings:
                self.warnings.append(entry)

    def has_errors(self) -> bool:
        return bool(self.errors)

    def codes(self) -> List[str]:
        return [e["code"] for e in self.errors] + [w["code"] for w in self.warnings]
