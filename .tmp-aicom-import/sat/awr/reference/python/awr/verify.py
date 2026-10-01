"""The AWR/2 verification pipeline (SPEC.md sections 6.3, 8, 9, 10, 11).

Two properties of this module are normative requirements rather than style:

* **All errors, not the first** (section 11.1).  Every check appends to a
  :class:`awr.errors.Reasons` accumulator; nothing short-circuits except where a later
  check is impossible (unparseable bytes, a document that is not an object).
* **No network, ever** (section 13.5).  Chain resolution, verdict lookup and profile
  evaluation operate exclusively over documents the caller supplied.  There is no import
  of any HTTP client in this package.
"""

from __future__ import annotations

import copy
import datetime as _dt
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .digest import canonical_sri, is_valid_sri
from .didkey import verification_method_for
from .documents import (
    TYPE_BLAME_ATTESTATION,
    TYPE_VERIFICATION_VERDICT,
    TYPE_WORK_RECEIPT,
    ReceiptFacts,
    check_envelope,
    check_issuer_key,
    coerce_now,
    document_type_of,
    parse_rfc3339_utc,
    validate_subject,
)
from .errors import (
    AWR_BLAME_001,
    AWR_BUNDLE_001,
    AWR_BUNDLE_002,
    AWR_BUNDLE_003,
    AWR_CANON_001,
    AWR_CANON_002,
    AWR_CHAIN_003,
    AWR_CHAIN_004,
    AWR_CHAIN_005,
    AWR_CHAIN_006,
    AWR_CHAIN_007,
    AWR_DOC_001,
    AWR_L2_001,
    AWR_LEGACY_003,
    AWR_LEGACY_005,
    AWR_PROFILE_001,
    AWR_PROFILE_002,
    AWR_PROFILE_003,
    AWR_PROFILE_004,
    AWR_PROOF_001,
    AWR_PROOF_002,
    AWR_PROOF_003,
    AWR_PROOF_004,
    AWR_PROOF_006,
    AWR_PROOF_007,
    AWR_PROOF_008,
    AWR_PROOF_009,
    AWR_TIME_001,
    AWR_TIME_002,
    AWR_VDCT_005,
    AwrError,
    Reasons,
)
from .jcs import canonical_self_check, loads
from .legacy import (
    CLASS_AWR1,
    CLASS_DISAGREE,
    awr2_signals,
    classify_version,
    is_legacy_document,
    verify_legacy_document,
)
from .proof import (
    CRYPTOSUITE,
    PROOF_PURPOSE,
    PROOF_TYPE,
    decode_proof_value,
    verify_document_signature,
)

#: Section 8.2 defaults.  Both are configurable and both are mandatory: chain resolution
#: is attacker-influenced work.
DEFAULT_MAX_DEPTH = 64
DEFAULT_MAX_NODES = 1024

#: Section 11.2 AWR-TIME-001 says "beyond the caller's skew allowance" without naming a
#: default; this implementation's default allowance is 60 seconds (see README finding).
DEFAULT_SKEW_SECONDS = 60

BUNDLE_VERSION = "2.0"

PROFILES = ("L0", "L1", "L2")


class SupportingSet(object):
    """Documents the caller supplied, indexed by canonical digest and by ``id``."""

    def __init__(self, documents: Optional[Sequence[Any]] = None) -> None:
        self.documents: List[Dict[str, Any]] = []
        self.by_digest: Dict[str, Dict[str, Any]] = {}
        self.by_id: Dict[str, Dict[str, Any]] = {}
        for document in documents or ():
            self.add(document)

    def add(self, document: Any) -> None:
        if not isinstance(document, dict):
            return
        self.documents.append(document)
        try:
            sri = canonical_sri(document)
        except AwrError:
            sri = None
        if sri is not None and sri not in self.by_digest:
            self.by_digest[sri] = document
        doc_id = document.get("id")
        if isinstance(doc_id, str) and doc_id and doc_id not in self.by_id:
            self.by_id[doc_id] = document

    def __len__(self) -> int:
        return len(self.documents)


# ---------------------------------------------------------------------------
# parsing
# ---------------------------------------------------------------------------


def _parse_input(data: Any, reasons: Reasons) -> Tuple[Any, bool]:
    """Return ``(value, is_legacy)`` or ``(None, False)`` when parsing failed.

    Section 4.3's number restriction applies to documents signed under AWR/2.  An AWR/1
    document predates it, so when the strict parse fails *only* on a number the bytes are
    re-parsed leniently and, if what comes out is an AWR/1 document, verification
    continues on the legacy path.  See the README finding on section 4.3's scope.
    """
    if isinstance(data, (dict, list)):
        return data, is_legacy_document(data)
    try:
        return loads(data), False
    except AwrError as err:
        if err.code in (AWR_CANON_001, AWR_CANON_002):
            try:
                lenient = loads(data, allow_non_integer_numbers=True)
            except AwrError:
                lenient = None
            if is_legacy_document(lenient):
                return lenient, True
        reasons.add_error_obj(err)
        return None, False


# ---------------------------------------------------------------------------
# proof
# ---------------------------------------------------------------------------


def _check_single_proof(
    document: Dict[str, Any],
    proof: Any,
    issuer_id: Optional[str],
    public_key: Optional[bytes],
    reasons: Reasons,
) -> bool:
    """Check one proof object (sections 5.3, 6.1, 6.3).  Returns True if it verified."""
    if not isinstance(proof, dict):
        reasons.add(AWR_PROOF_001, "proof must be an object")
        return False

    if proof.get("type") != PROOF_TYPE:
        reasons.add(
            AWR_PROOF_002,
            "proof.type must be %r, got %r" % (PROOF_TYPE, proof.get("type")),
        )
    if proof.get("cryptosuite") != CRYPTOSUITE:
        reasons.add(
            AWR_PROOF_003,
            "cryptosuite must be %r, got %r (unknown suites are rejected, not skipped, "
            "section 6.4)" % (CRYPTOSUITE, proof.get("cryptosuite")),
        )
    if proof.get("proofPurpose") != PROOF_PURPOSE:
        reasons.add(
            AWR_PROOF_004,
            "proofPurpose must be %r, got %r"
            % (PROOF_PURPOSE, proof.get("proofPurpose")),
        )
    if parse_rfc3339_utc(proof.get("created")) is None:
        reasons.add(
            AWR_PROOF_009,
            "proof.created must be an RFC 3339 UTC date-time, got %r"
            % (proof.get("created"),),
        )
    if issuer_id is not None:
        try:
            expected = verification_method_for(issuer_id)
        except AwrError:
            expected = None
        if expected is not None and proof.get("verificationMethod") != expected:
            reasons.add(
                AWR_PROOF_007,
                "verificationMethod must be %r, got %r"
                % (expected, proof.get("verificationMethod")),
            )
    if "@context" in proof and proof.get("@context") != document.get("@context"):
        reasons.add(
            AWR_PROOF_008,
            "proof.@context differs from the document @context",
        )

    signature_ok = False
    try:
        decode_proof_value(proof.get("proofValue"))
        decoded = True
    except AwrError as err:
        reasons.add_error_obj(err)
        decoded = False
    if decoded and public_key is not None:
        try:
            signature_ok = verify_document_signature(document, proof, public_key)
        except AwrError as err:
            reasons.add_error_obj(err)
            signature_ok = False
        if not signature_ok:
            reasons.add(
                AWR_PROOF_006,
                "Ed25519 verification of hashData = SHA-256(canonicalProofConfig) || "
                "SHA-256(transformedDocument) failed (note the order, section 6.2 step 6)",
            )
    return signature_ok


def _check_proofs(
    document: Dict[str, Any],
    issuer_id: Optional[str],
    public_key: Optional[bytes],
    reasons: Reasons,
) -> Tuple[bool, Optional[int], List[Dict[str, Any]]]:
    """Check ``proof``, which may be a single object or an array (section 6.1).

    Returns ``(any_verified, verified_index, per_proof_reports)``.  For an array, a proof
    that failed is *reported* in the per-proof list; its reasons are promoted to the
    document's errors only when no proof verified, since section 6.1 makes one valid proof
    sufficient while still requiring every proof to be reported.
    """
    if "proof" not in document:
        reasons.add(AWR_PROOF_001, "proof is missing")
        return False, None, []

    proof = document.get("proof")
    if not isinstance(proof, list):
        verified = _check_single_proof(document, proof, issuer_id, public_key, reasons)
        return verified, 0 if verified else None, []

    if not proof:
        reasons.add(AWR_PROOF_001, "proof array is empty")
        return False, None, []

    reports: List[Dict[str, Any]] = []
    verified_index: Optional[int] = None
    per_proof: List[Reasons] = []
    for index, candidate in enumerate(proof):
        local = Reasons()
        ok = _check_single_proof(document, candidate, issuer_id, public_key, local)
        per_proof.append(local)
        reports.append(
            {
                "index": index,
                "verified": ok,
                "reasons": local.errors,
                "warnings": local.warnings,
            }
        )
        if ok and verified_index is None:
            verified_index = index
    if verified_index is None:
        for local in per_proof:
            reasons.extend(local)
    return verified_index is not None, verified_index, reports


# ---------------------------------------------------------------------------
# chain
# ---------------------------------------------------------------------------


def _parents_of(document: Any) -> List[Dict[str, Any]]:
    if not isinstance(document, dict):
        return []
    subject = document.get("credentialSubject")
    if not isinstance(subject, dict):
        return []
    parents = subject.get("parents")
    if not isinstance(parents, list):
        return []
    return [entry for entry in parents if isinstance(entry, dict)]


def _digest_field(document: Any, field: str) -> Optional[str]:
    if not isinstance(document, dict):
        return None
    subject = document.get("credentialSubject")
    if not isinstance(subject, dict):
        return None
    value = subject.get(field)
    return value if isinstance(value, str) else None


def resolve_chain(
    receipt: Dict[str, Any],
    supporting: SupportingSet,
    reasons: Reasons,
    *,
    max_depth: int = DEFAULT_MAX_DEPTH,
    max_nodes: int = DEFAULT_MAX_NODES,
) -> Dict[str, Any]:
    """Walk ``parents`` edges over the supplied documents (section 8).

    Returns ``resolved``/``unresolved`` counts plus ``resolvedEdges``/``unresolvedEdges``,
    which identify each edge: section 8.2 requires a verifier to report *which* edges it
    resolved so that a caller can tell "chain intact" from "chain not checked".

    Cycle detection keys on document ``id``.  A cycle in the *digests* is not
    constructible -- an edge commits to the parent's exact bytes (section 8.1), so a
    digest-level cycle would be a SHA-256 fixed point -- but two documents can name each
    other by identifier, which is what an attacker controls and what section 8.2 requires
    a resolver to survive.  See the README finding on section 8.2.
    """
    stats: Dict[str, Any] = {
        "resolved": 0,
        "unresolved": 0,
        "resolvedEdges": [],
        "unresolvedEdges": [],
    }
    id_digests: Dict[str, set] = {}
    id_sources: Dict[str, set] = {}
    state = {"nodes": 1, "stopped": False}

    def note_conflict(child_id: Optional[str], parent_id: str, sri: str) -> None:
        id_digests.setdefault(parent_id, set()).add(sri)
        id_sources.setdefault(parent_id, set()).add(child_id or "")

    def walk(document: Dict[str, Any], depth: int, path: Tuple[str, ...]) -> None:
        if state["stopped"]:
            return
        child_id = document.get("id") if isinstance(document.get("id"), str) else None
        for entry in _parents_of(document):
            sri = entry.get("digestSRI")
            if not is_valid_sri(sri):
                # Already reported by the subject validator as AWR-CHAIN-001/002.
                continue
            parent_id = entry.get("id") if isinstance(entry.get("id"), str) else None
            if parent_id:
                note_conflict(child_id, parent_id, sri)

            parent = supporting.by_digest.get(sri)
            edge_resolved = parent is not None
            if parent is None and parent_id is not None:
                candidate = supporting.by_id.get(parent_id)
                if candidate is not None:
                    try:
                        candidate_sri = canonical_sri(candidate)
                    except AwrError:
                        candidate_sri = None
                    if candidate_sri != sri:
                        reasons.add(
                            AWR_CHAIN_003,
                            "parent %s is available but its canonical digest %s does not "
                            "match the edge digest %s"
                            % (parent_id, candidate_sri, sri),
                        )
                    parent = candidate

            edge = {
                "childId": child_id,
                "parentId": parent_id,
                "digestSRI": sri,
            }
            if edge_resolved:
                stats["resolved"] += 1
                stats["resolvedEdges"].append(edge)
                parent_output = _digest_field(parent, "outputDigest")
                child_input = _digest_field(document, "inputDigest")
                if (
                    parent_output is not None
                    and child_input is not None
                    and parent_output != child_input
                ):
                    reasons.add(
                        AWR_CHAIN_007,
                        "parent %s outputDigest != child %s inputDigest; a legitimate hop "
                        "often transforms its input, so this is a warning"
                        % (parent.get("id"), child_id),
                    )
            else:
                stats["unresolved"] += 1
                stats["unresolvedEdges"].append(edge)

            if parent is None:
                continue

            parent_key = parent.get("id") if isinstance(parent.get("id"), str) else sri
            if parent_key in path:
                reasons.add(
                    AWR_CHAIN_004,
                    "cycle detected: %s is already on the resolution path %s"
                    % (parent_key, " -> ".join(path)),
                )
                continue
            if depth + 1 > max_depth:
                reasons.add(
                    AWR_CHAIN_005,
                    "chain resolution depth limit of %d exceeded" % (max_depth,),
                )
                state["stopped"] = True
                return
            state["nodes"] += 1
            if state["nodes"] > max_nodes:
                reasons.add(
                    AWR_CHAIN_005,
                    "chain resolution node limit of %d exceeded" % (max_nodes,),
                )
                state["stopped"] = True
                return
            walk(parent, depth + 1, path + (parent_key,))
            if state["stopped"]:
                return

    root_key = receipt.get("id") if isinstance(receipt.get("id"), str) else ""
    walk(receipt, 0, (root_key,))

    for parent_id, digests in id_digests.items():
        if len(digests) > 1 and len(id_sources.get(parent_id, set())) > 1:
            reasons.add(
                AWR_CHAIN_006,
                "parent id %s is referenced with %d conflicting digests across the chain; "
                "one of them is forged" % (parent_id, len(digests)),
            )
    return stats


def _reachable_receipt_digests(
    start: Dict[str, Any], supporting: SupportingSet, max_nodes: int
) -> Tuple[set, int]:
    """Digests reachable from *start* through ``parents``, plus the unresolved edge count."""
    seen = set()
    unresolved = 0
    try:
        seen.add(canonical_sri(start))
    except AwrError:
        pass
    stack = [start]
    while stack and len(seen) <= max_nodes:
        current = stack.pop()
        for entry in _parents_of(current):
            sri = entry.get("digestSRI")
            if not is_valid_sri(sri):
                continue
            parent = supporting.by_digest.get(sri)
            if parent is None:
                unresolved += 1
                continue
            if sri in seen:
                continue
            seen.add(sri)
            stack.append(parent)
    return seen, unresolved


# ---------------------------------------------------------------------------
# profiles
# ---------------------------------------------------------------------------


def _has_stake_binding(document: Any) -> bool:
    if not isinstance(document, dict):
        return False
    subject = document.get("credentialSubject")
    if not isinstance(subject, dict):
        return False
    stake = subject.get("stake")
    return (
        isinstance(stake, dict)
        and isinstance(stake.get("scheme"), str)
        and bool(stake.get("scheme"))
    )


def _issuer_id_of(document: Any) -> Optional[str]:
    if not isinstance(document, dict):
        return None
    issuer = document.get("issuer")
    if not isinstance(issuer, dict):
        return None
    value = issuer.get("id")
    return value if isinstance(value, str) else None


def _matching_verdicts(
    receipt_sri: Optional[str],
    supporting: SupportingSet,
    now: _dt.datetime,
    skew_seconds: int,
) -> List[Tuple[Dict[str, Any], Dict[str, Any]]]:
    """Valid verdicts in *supporting* whose ``verifiedWork`` digests the receipt."""
    found: List[Tuple[Dict[str, Any], Dict[str, Any]]] = []
    if receipt_sri is None:
        return found
    for document in supporting.documents:
        if document_type_of(document) != TYPE_VERIFICATION_VERDICT:
            continue
        subject = document.get("credentialSubject")
        if not isinstance(subject, dict):
            continue
        reference = subject.get("verifiedWork")
        if not isinstance(reference, dict) or reference.get("digestSRI") != receipt_sri:
            continue
        result = verify_document(
            document,
            now=now,
            skew_seconds=skew_seconds,
            _recursion=1,
        )
        if result["valid"]:
            found.append((document, result))
    return found


def evaluate_profiles(
    document_type: Optional[str],
    receipt_sri: Optional[str],
    receipt_issuer: Optional[str],
    receipt_facts: Optional[ReceiptFacts],
    supporting: SupportingSet,
    now: _dt.datetime,
    skew_seconds: int,
    base_valid: bool,
    warnings: Optional[Reasons] = None,
) -> Tuple[Optional[str], Dict[str, List[Dict[str, str]]]]:
    """Evaluate L1 and L2 (section 10) without mutating the document's own reasons.

    Returns ``(highest_satisfied, {profile: [reason, ...]})``.  A profile is never granted
    because a document claims it (section 3.3), and the shortfall reasons are only
    promoted to errors when the caller asked for that profile.
    """
    evaluated: Dict[str, List[Dict[str, str]]] = {}
    l1 = Reasons()
    l2 = Reasons()

    if document_type != TYPE_WORK_RECEIPT:
        detail = (
            "profiles L1/L2 are defined over a WorkReceipt; this document is a %s"
            % (document_type,)
        )
        l1.add(AWR_PROFILE_001, detail)
        l2.add(AWR_PROFILE_001, detail)
        evaluated["L1"] = l1.errors
        evaluated["L2"] = l2.errors
        # Section 10.4: the profile of a document that is not a WorkReceipt is null.  The
        # levels are levels of assurance *about a unit of work*; a VerificationVerdict or a
        # BlameAttestation is valid on its own terms and is not a receipt, so it satisfies
        # none of them.  ``profile: null`` with ``valid: true`` does not mean "below L0".
        # This module used to report "L0" here and two other implementations reported null,
        # which is the divergence 10.4 now settles.
        return None, evaluated

    verdicts = _matching_verdicts(receipt_sri, supporting, now, skew_seconds)
    independent = [
        (doc, res)
        for doc, res in verdicts
        if _issuer_id_of(doc) is not None and _issuer_id_of(doc) != receipt_issuer
    ]
    if not verdicts:
        l1.add(
            AWR_PROFILE_001,
            "no valid VerificationVerdict for this receipt was supplied",
        )
    elif not independent:
        l1.add(
            AWR_PROFILE_002,
            "the only verdict(s) supplied were issued by the receipt's own issuer %s; "
            "self-verification is exactly what L1 exists to exclude" % (receipt_issuer,),
        )
    evaluated["L1"] = list(l1.errors)

    l2.extend(l1)
    distinct = sorted({_issuer_id_of(doc) for doc, _ in independent})
    if len(distinct) < 2:
        l2.add(
            AWR_PROFILE_003,
            "L2 needs verdicts from two distinct issuers, neither the receipt's; found %d"
            % (len(distinct),),
        )
    has_settlement = bool(receipt_facts and receipt_facts.has_settlement_binding)
    all_staked = bool(independent) and all(
        _has_stake_binding(doc) for doc, _ in independent
    )
    if not (has_settlement or all_staked):
        l2.add(
            AWR_PROFILE_004,
            "L2 needs an accountability binding: receipt.settlement, or stake on every "
            "counted verdict",
        )
    elif all_staked and not has_settlement and warnings is not None:
        # The settlement case emits AWR-L2-001 from the receipt's own subject check; a
        # stake binding lives in the verdicts, so say it here (section 10.3).
        warnings.add(
            AWR_L2_001,
            "every counted verdict carries a stake binding; on-chain existence was NOT "
            "checked (section 10.3)",
        )
    evaluated["L2"] = list(l2.errors)

    highest = None
    if base_valid:
        highest = "L0"
        if not evaluated["L1"]:
            highest = "L1"
            if not evaluated["L2"]:
                highest = "L2"
    return highest, evaluated


# ---------------------------------------------------------------------------
# the pipeline
# ---------------------------------------------------------------------------


#: Section 11.1: ``verifiedProof`` is non-null if and only if the result reports no code
#: from these three families.  They are exactly the conditions section 6.3 lists as making
#: step 6 impossible (steps 1-5) plus step 6's own failure, ``AWR-PROOF-006``: no canonical
#: form, no authoritative public key -- ``AWR-KEY-003`` included, since two disagreeing
#: statements of the signing key leave none authoritative (section 5.2) -- or a proof
#: configuration that is not the one AWR/2 defines.
_NO_SIGNATURE_CHECK_PREFIXES = ("AWR-CANON-", "AWR-KEY-", "AWR-PROOF-")


def _enforce_result_invariants(result: Dict[str, Any]) -> None:
    """Hold the derived members of section 11.1 to the rules the section states.

    Both are *functions of the codes reported*, so they are derived here rather than at
    each call site:

    * ``verifiedProof`` is nulled when an ``AWR-CANON-*``/``AWR-KEY-*``/``AWR-PROOF-*``
      code is reported.  Deriving it made this module stop reporting
      ``verifiedProof: 0`` beside ``AWR-PROOF-002``/``AWR-PROOF-004`` -- asserting that
      proof 0 verified, for a proof configuration AWR/2 does not accept.

      Section 11.1 also requires null for ``AWR-DOC-001``, ``AWR-DOC-010``,
      ``AWR-LEGACY-001`` and for a bundle whose version is unsupported or whose subject
      is ambiguous.  Those need no clause here: on every one of those paths no proof is
      ever checked, so ``_empty_result``'s ``None`` stands.  This function is the
      *correction*, not the whole rule; ``check_vectors.py`` asserts the full
      equivalence, in both directions, on all 106 vectors.
    * ``awrVersion`` and ``documentType`` are null whenever any ``AWR-CANON-*`` code is
      reported: a document with no canonical form has no confirmed content, and leaving
      the two free made them a property of the parser's architecture rather than of the
      document -- this module read them off the lone-surrogate document, which the Rust
      build's parser rejects before it sees ``type``, and could not read them off the
      ``2340.0`` document, which the Rust build does reach.
    """
    codes = [entry.get("code", "") for entry in result.get("reasons") or ()]
    if any(code.startswith(_NO_SIGNATURE_CHECK_PREFIXES) for code in codes):
        result["verifiedProof"] = None
    if any(code.startswith("AWR-CANON-") for code in codes):
        result["awrVersion"] = None
        result["documentType"] = None


def _empty_result() -> Dict[str, Any]:
    return {
        "valid": False,
        "awrVersion": None,
        "documentType": None,
        "profile": None,
        "reasons": [],
        "warnings": [],
        "chain": {"resolved": 0, "unresolved": 0},
        # Section 11.1: present on every result, ``null`` until a proof verifies.
        "verifiedProof": None,
    }


def verify_document(
    document: Any,
    *,
    profile: Optional[str] = None,
    supporting: Optional[Sequence[Any]] = None,
    now: Any = None,
    skew_seconds: int = DEFAULT_SKEW_SECONDS,
    max_depth: int = DEFAULT_MAX_DEPTH,
    max_nodes: int = DEFAULT_MAX_NODES,
    expected_key: Optional[bytes] = None,
    no_legacy: bool = False,
    _recursion: int = 0,
) -> Dict[str, Any]:
    """Verify one AWR document and return the section 11.1 result object.

    *document* may be ``bytes``/``str`` (the received bytes) or an already-parsed object.
    *supporting* carries the documents the caller supplied for chain resolution and
    profile evaluation; nothing is ever fetched.

    *expected_key* is the caller's out-of-band 32-byte Ed25519 public key.  Section 12.4
    requires it of every implementation that verifies AWR/1, because an AWR/1 signature
    checked against a key the document carries attests no identity.  *no_legacy* declines
    section 12 entirely (``AWR-LEGACY-005``); section 12 support is OPTIONAL.
    """
    if profile is not None and profile not in PROFILES:
        raise ValueError("profile must be one of %s, got %r" % (PROFILES, profile))

    reasons = Reasons()
    result = _empty_result()
    moment = coerce_now(now)

    parsed, legacy = _parse_input(document, reasons)
    if parsed is None:
        result["reasons"] = reasons.errors
        result["warnings"] = reasons.warnings
        return result
    if not isinstance(parsed, dict):
        reasons.add(
            AWR_DOC_001, "an AWR document is a JSON object, got %s" % type(parsed).__name__
        )
        result["reasons"] = reasons.errors
        result["warnings"] = reasons.warnings
        return result

    doc: Dict[str, Any] = parsed
    support = supporting if isinstance(supporting, SupportingSet) else SupportingSet(supporting)

    # Section 12.3: the version gate runs before any verification, and before the AWR/2
    # envelope checks.  Selecting the rule set on `proof.type` alone was an
    # unauthenticated forgery path -- AWR/1 signs neither `proof.type` nor `issuer`.
    version_class = classify_version(doc)
    if version_class == CLASS_DISAGREE:
        reasons.add(
            AWR_LEGACY_003,
            "version signals disagree: the document carries an AWR/1 proof suite (section 12) "
            "and the AWR/2 signal(s) %s. AWR/1 does not sign proof.type or issuer, "
            "so honouring the proof suite here would let the sender choose which rules "
            "apply to a document that claims to be AWR/2 (section 12.3); it is verified "
            "under neither, and there is no fallback to the other rule set"
            % (", ".join(awr2_signals(doc)),),
        )
        result["awrVersion"] = (
            doc.get("awrVersion") if isinstance(doc.get("awrVersion"), str) else None
        )
        result["documentType"] = document_type_of(doc)
        result["reasons"] = reasons.errors
        result["warnings"] = reasons.warnings
        _enforce_result_invariants(result)
        return result
    if legacy or version_class == CLASS_AWR1:
        if no_legacy:
            reasons.add(
                AWR_LEGACY_005,
                "the document is an AWR/1 legacy document (section 12) and this verifier "
                "was asked not to apply the AWR/1 rules; section 12 support is OPTIONAL",
            )
            result["awrVersion"] = None
            result["documentType"] = document_type_of(doc)
            result["reasons"] = reasons.errors
            result["warnings"] = reasons.warnings
            return result
        return _verify_legacy(doc, reasons, result, expected_key)

    # Section 4.1/4.2 self-check before anything depends on the canonical bytes.
    try:
        canonical_self_check(doc)
        canonicalizable = True
    except AwrError as err:
        reasons.add_error_obj(err)
        canonicalizable = False

    envelope = check_envelope(doc, reasons)
    result["awrVersion"] = envelope.awr_version
    result["documentType"] = envelope.document_type

    public_key = check_issuer_key(doc, envelope.issuer_id, reasons)

    proof_reports: List[Dict[str, Any]] = []
    if canonicalizable:
        # A failed signature is already reported as AWR-PROOF-006 inside _check_proofs;
        # `verified_index` only exists to say *which* proof of an array verified (6.1).
        _, verified_index, proof_reports = _check_proofs(
            doc, envelope.issuer_id, public_key, reasons
        )
        # Section 11.1: ``verifiedProof`` is REQUIRED whenever section 6.3 step 6 was
        # performed and succeeded, whether ``proof`` was one object or an array -- ``0``
        # for a single proof.  Gating it on ``proof_reports`` (non-empty only for an
        # array) is what made this module report ``null`` where the Rust and browser
        # builds reported ``0``, for 47 of the 106 vectors.
        result["verifiedProof"] = verified_index
    # Section 6.3: ``AWR-PROOF-006`` means the signature was checked and did not verify.
    # When the document has no canonical form there is nothing to check it over, and the
    # ``AWR-CANON-*`` code already reported is the honest and more specific report; adding
    # PROOF-006 on top is what made this module disagree with two other implementations on
    # the lone-surrogate document.  The document stays invalid either way: a
    # canonicalization failure is an error.
    elif not reasons.has_errors():
        # Fail closed.  Unreachable in practice -- ``canonicalizable`` is only false after
        # a canonicalization error was recorded -- but a valid result must never be
        # reported for a signature that was not checked.
        reasons.add(
            AWR_PROOF_006,
            "the signature was not checked and no reason was recorded; refusing to "
            "report this document as valid",
        )
    if proof_reports:
        result["proofs"] = proof_reports

    facts = validate_subject(envelope.document_type, doc.get("credentialSubject"), reasons)

    # Time warnings are never validity (section 11.3).
    if envelope.valid_from is not None:
        if envelope.valid_from > moment + _dt.timedelta(seconds=skew_seconds):
            reasons.add(
                AWR_TIME_001,
                "validFrom %s is in the future beyond the %d-second skew allowance"
                % (doc.get("validFrom"), skew_seconds),
            )
    if envelope.valid_until is not None and envelope.valid_until < moment:
        reasons.add(
            AWR_TIME_002,
            "validUntil %s is in the past; age is policy, not validity (section 11.3)"
            % (doc.get("validUntil"),),
        )

    self_sri: Optional[str] = None
    if canonicalizable:
        try:
            self_sri = canonical_sri(doc)
        except AwrError:
            self_sri = None
        result["documentDigestSRI"] = self_sri

    if envelope.document_type == TYPE_WORK_RECEIPT:
        chain = resolve_chain(
            doc, support, reasons, max_depth=max_depth, max_nodes=max_nodes
        )
        result["chain"] = {
            "resolved": chain["resolved"],
            "unresolved": chain["unresolved"],
        }
        # Section 8.2: report *which* edges resolved, beyond the section 11.1 counts.
        result["chainEdges"] = {
            "resolved": chain["resolvedEdges"],
            "unresolved": chain["unresolvedEdges"],
        }
    elif envelope.document_type == TYPE_VERIFICATION_VERDICT:
        _cross_check_verdict(doc, support, reasons)
    elif envelope.document_type == TYPE_BLAME_ATTESTATION:
        _cross_check_blame(doc, support, reasons, max_nodes)

    base_valid = not reasons.has_errors()

    if _recursion == 0:
        highest, evaluated = evaluate_profiles(
            envelope.document_type,
            self_sri,
            envelope.issuer_id,
            facts if isinstance(facts, ReceiptFacts) else None,
            support,
            moment,
            skew_seconds,
            base_valid,
            warnings=reasons,
        )
        result["profilesEvaluated"] = evaluated
        if profile in ("L1", "L2"):
            for entry in evaluated.get(profile, []):
                reasons.add(entry["code"], entry["detail"])
        result["profile"] = highest if not reasons.has_errors() else None
    else:
        result["profile"] = "L0" if base_valid else None

    result["valid"] = not reasons.has_errors()
    result["reasons"] = reasons.errors
    result["warnings"] = reasons.warnings
    if result["profile"] is not None and not result["valid"]:
        result["profile"] = None
    _enforce_result_invariants(result)
    return result


def _cross_check_verdict(
    document: Dict[str, Any], supporting: SupportingSet, reasons: Reasons
) -> None:
    """AWR-VDCT-005: the referenced receipt was supplied and does not match."""
    subject = document.get("credentialSubject")
    if not isinstance(subject, dict):
        return
    reference = subject.get("verifiedWork")
    if not isinstance(reference, dict):
        return
    sri = reference.get("digestSRI")
    ref_id = reference.get("id")
    if not isinstance(sri, str) or not isinstance(ref_id, str):
        return
    if sri in supporting.by_digest:
        return
    candidate = supporting.by_id.get(ref_id)
    if candidate is None:
        return
    try:
        candidate_sri = canonical_sri(candidate)
    except AwrError:
        return
    if candidate_sri != sri:
        reasons.add(
            AWR_VDCT_005,
            "verifiedWork.digestSRI %s does not match the supplied receipt %s whose "
            "canonical digest is %s" % (sri, ref_id, candidate_sri),
        )


def _cross_check_blame(
    document: Dict[str, Any],
    supporting: SupportingSet,
    reasons: Reasons,
    max_nodes: int,
) -> None:
    """AWR-BLAME-001: blamedWork must be reachable from chain when receipts are available."""
    subject = document.get("credentialSubject")
    if not isinstance(subject, dict):
        return
    chain_ref = subject.get("chain")
    blamed_ref = subject.get("blamedWork")
    if not isinstance(chain_ref, dict) or not isinstance(blamed_ref, dict):
        return
    chain_sri = chain_ref.get("digestSRI")
    blamed_sri = blamed_ref.get("digestSRI")
    if not is_valid_sri(chain_sri) or not is_valid_sri(blamed_sri):
        return
    terminal = supporting.by_digest.get(chain_sri)
    if terminal is None:
        # The chain's terminal receipt was not supplied: nothing is knowable, and
        # section 8.2 forbids fetching it.
        return
    reachable, unresolved = _reachable_receipt_digests(terminal, supporting, max_nodes)
    if blamed_sri in reachable:
        return
    if unresolved:
        # Some hop is missing, so unreachability is not a statement about the document.
        return
    reasons.add(
        AWR_BLAME_001,
        "blamedWork %s is not reachable from chain %s through the %d supplied receipts"
        % (blamed_sri, chain_sri, len(reachable)),
    )


def _verify_legacy(
    document: Dict[str, Any],
    reasons: Reasons,
    result: Dict[str, Any],
    expected_key: Optional[bytes] = None,
) -> Dict[str, Any]:
    """AWR/1 verification (section 12)."""
    outcome = verify_legacy_document(document, reasons, expected_key)
    # Section 12.3 guarantees a document reaching here carries no `awrVersion` -- that is
    # an AWR/2 signal and would have been AWR-LEGACY-003 -- so this is always null.  It is
    # read off the document rather than hard-coded because section 11.1 says the member
    # reports what the document carries.
    version = document.get("awrVersion")
    result["awrVersion"] = version if isinstance(version, str) else None
    # `type` is unsigned in AWR/1, so documentType is reported as a parse of untrusted
    # bytes, not as an attested fact -- see result["legacy"]["unsignedFields"].
    result["documentType"] = document_type_of(document)
    # Section 12.4: an AWR/1 result names a KEY, never an issuer.
    result["legacy"] = outcome.as_result_member()
    result["legacyDialect"] = outcome.dialect
    result["unsignedFields"] = outcome.unsigned_fields
    result["valid"] = outcome.verified and not reasons.has_errors()
    result["profile"] = None
    result["reasons"] = reasons.errors
    result["warnings"] = reasons.warnings
    _enforce_result_invariants(result)
    return result


# ---------------------------------------------------------------------------
# bundles
# ---------------------------------------------------------------------------


def is_bundle(value: Any) -> bool:
    return isinstance(value, dict) and "awrBundle" in value


def _bundle_documents(bundle: Dict[str, Any], reasons: Reasons) -> List[Dict[str, Any]]:
    if bundle.get("awrBundle") != BUNDLE_VERSION:
        # Section 9: fail closed.  ``awrBundle`` is the only statement of the container's
        # schema, so nothing inside an unsupported version may be processed -- reaching in
        # to pull out things merely *assumed* to be documents is the verifier deciding for
        # itself which bytes to read.  Same gate as section 3.1's ``awrVersion``
        # (``AWR-DOC-009``).  This module used to verify the enclosed receipt and report its
        # documentType and verifiedProof for an ``awrBundle: "1.0"`` container.
        reasons.add(
            AWR_BUNDLE_001,
            "awrBundle must be %r, got %r; nothing inside an unsupported bundle version is "
            "processed (section 9)" % (BUNDLE_VERSION, bundle.get("awrBundle")),
        )
        return []
    documents = bundle.get("documents")
    if not isinstance(documents, list) or not documents:
        reasons.add(AWR_BUNDLE_001, "documents must be a non-empty array")
        return []
    by_id: Dict[str, str] = {}
    out: List[Dict[str, Any]] = []
    for entry in documents:
        if not isinstance(entry, dict):
            reasons.add(AWR_BUNDLE_001, "every bundle document must be a JSON object")
            continue
        out.append(entry)
        doc_id = entry.get("id")
        if isinstance(doc_id, str) and doc_id:
            try:
                sri = canonical_sri(entry)
            except AwrError:
                continue
            previous = by_id.get(doc_id)
            if previous is not None and previous != sri:
                reasons.add(
                    AWR_BUNDLE_002,
                    "document id %s appears twice with differing content" % (doc_id,),
                )
            by_id[doc_id] = sri
    return out


def _choose_subject(
    documents: Sequence[Dict[str, Any]], reasons: Reasons
) -> Optional[Dict[str, Any]]:
    """The single WorkReceipt not referenced as anyone's parent (section 9)."""
    referenced_digests = set()
    referenced_ids = set()
    for document in documents:
        for entry in _parents_of(document):
            sri = entry.get("digestSRI")
            if isinstance(sri, str):
                referenced_digests.add(sri)
            parent_id = entry.get("id")
            if isinstance(parent_id, str):
                referenced_ids.add(parent_id)
    candidates = []
    for document in documents:
        if document_type_of(document) != TYPE_WORK_RECEIPT:
            continue
        try:
            sri = canonical_sri(document)
        except AwrError:
            sri = None
        doc_id = document.get("id")
        if sri is not None and sri in referenced_digests:
            continue
        if isinstance(doc_id, str) and doc_id in referenced_ids:
            continue
        candidates.append(document)
    if len(candidates) == 1:
        return candidates[0]
    reasons.add(
        AWR_BUNDLE_003,
        "the subject document is ambiguous: %d WorkReceipts are not referenced as a "
        "parent; pass the subject id explicitly rather than guessing" % (len(candidates),),
    )
    return None


def verify_bundle(
    bundle: Any,
    *,
    subject_id: Optional[str] = None,
    profile: Optional[str] = None,
    supporting: Optional[Sequence[Any]] = None,
    now: Any = None,
    skew_seconds: int = DEFAULT_SKEW_SECONDS,
    max_depth: int = DEFAULT_MAX_DEPTH,
    max_nodes: int = DEFAULT_MAX_NODES,
    expected_key: Optional[bytes] = None,
    no_legacy: bool = False,
) -> Dict[str, Any]:
    """Verify the subject document of a bundle (section 9).

    A bundle is a transport container, is not signed and carries no claims: every document
    inside it is verified individually, and the bundle's own defects are reported as
    ``AWR-BUNDLE-*`` on the subject's result.
    """
    reasons = Reasons()
    result = _empty_result()

    parsed, _ = _parse_input(bundle, reasons)
    if parsed is None:
        result["reasons"] = reasons.errors
        result["warnings"] = reasons.warnings
        return result
    if not isinstance(parsed, dict):
        reasons.add(AWR_BUNDLE_001, "a bundle is a JSON object")
        result["reasons"] = reasons.errors
        result["warnings"] = reasons.warnings
        return result

    documents = _bundle_documents(parsed, reasons)
    extra = list(supporting or ())
    if not documents:
        result["reasons"] = reasons.errors
        result["warnings"] = reasons.warnings
        return result

    # §9: subject selection runs ONLY when a profile is requested. Without one a bundle is a
    # transport container and nothing more — every document in it is verified individually
    # and the result is the conjunction. This is why a bundle holding a single
    # VerificationVerdict is valid here and AWR-BUNDLE-003 at any profile; the old text
    # described selection without saying when it applied, and three implementations of it
    # produced three different answers for that bundle.
    if profile is None and subject_id is None:
        merged = Reasons()
        merged.extend(reasons)
        first_verified_proof: Optional[int] = None
        for index, document in enumerate(documents):
            support = SupportingSet(
                [d for d in documents if d is not document] + list(extra)
            )
            inner = verify_document(
                document,
                profile=None,
                supporting=support,
                now=now,
                skew_seconds=skew_seconds,
                max_depth=max_depth,
                max_nodes=max_nodes,
                expected_key=expected_key,
                no_legacy=no_legacy,
            )
            for entry in list(inner["reasons"]) + list(inner["warnings"]):
                # The detail is NOT prefixed with the document index. Reasons dedup on
                # (code, detail), and two documents failing the same way for the same
                # stated reason are one fact about the bundle, not two — prefixing made
                # `AWR-CHAIN-005` appear twice for a bundle whose every document breached
                # the same limit. Details that need to name a document already carry its
                # id.
                merged.add(entry["code"], entry["detail"])
            if index == 0:
                first_verified_proof = inner.get("verifiedProof")
        result["reasons"] = merged.errors
        result["warnings"] = merged.warnings
        result["valid"] = not merged.errors
        # §11.1 requires verifiedProof to name the proof that was checked. A container has
        # no subject, so it reports the value from documents[0] — deterministic, and the
        # only reading that stays true for the single-document bundle, which is the common
        # case. Callers needing per-document detail verify the documents themselves.
        if first_verified_proof is not None:
            result["verifiedProof"] = first_verified_proof
        return result

    subject: Optional[Dict[str, Any]] = None
    if subject_id is not None:
        for document in documents:
            if document.get("id") == subject_id:
                subject = document
                break
        if subject is None:
            reasons.add(
                AWR_BUNDLE_003,
                "no document in the bundle has id %r" % (subject_id,),
            )
    else:
        subject = _choose_subject(documents, reasons)

    if subject is None:
        result["reasons"] = reasons.errors
        result["warnings"] = reasons.warnings
        return result

    support = SupportingSet(
        [d for d in documents if d is not subject] + [d for d in extra]
    )
    inner = verify_document(
        subject,
        profile=profile,
        supporting=support,
        now=now,
        skew_seconds=skew_seconds,
        max_depth=max_depth,
        max_nodes=max_nodes,
        expected_key=expected_key,
        no_legacy=no_legacy,
    )
    merged = Reasons()
    merged.extend(reasons)
    for entry in inner["reasons"]:
        merged.add(entry["code"], entry["detail"])
    for entry in inner["warnings"]:
        merged.add(entry["code"], entry["detail"])
    inner["reasons"] = merged.errors
    inner["warnings"] = merged.warnings
    inner["valid"] = not merged.has_errors()
    if not inner["valid"]:
        inner["profile"] = None
    inner["bundleDocuments"] = len(documents)
    inner["subjectId"] = subject.get("id")
    return inner


def verify(
    data: Any,
    *,
    profile: Optional[str] = None,
    supporting: Optional[Sequence[Any]] = None,
    subject_id: Optional[str] = None,
    now: Any = None,
    skew_seconds: int = DEFAULT_SKEW_SECONDS,
    max_depth: int = DEFAULT_MAX_DEPTH,
    max_nodes: int = DEFAULT_MAX_NODES,
    expected_key: Optional[bytes] = None,
    no_legacy: bool = False,
) -> Dict[str, Any]:
    """Verify a document or a bundle, dispatching on the ``awrBundle`` member."""
    reasons = Reasons()
    parsed, _ = _parse_input(data, reasons)
    if parsed is None:
        result = _empty_result()
        result["reasons"] = reasons.errors
        result["warnings"] = reasons.warnings
        return result
    if is_bundle(parsed):
        return verify_bundle(
            parsed,
            subject_id=subject_id,
            profile=profile,
            supporting=supporting,
            now=now,
            skew_seconds=skew_seconds,
            max_depth=max_depth,
            max_nodes=max_nodes,
            expected_key=expected_key,
            no_legacy=no_legacy,
        )
    return verify_document(
        parsed,
        profile=profile,
        supporting=supporting,
        now=now,
        skew_seconds=skew_seconds,
        max_depth=max_depth,
        max_nodes=max_nodes,
        expected_key=expected_key,
        no_legacy=no_legacy,
    )


def make_bundle(documents: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Build a section 9 bundle.  It is not signed and carries no claims of its own."""
    if not documents:
        raise ValueError("a bundle's documents array must be non-empty")
    return {"awrBundle": BUNDLE_VERSION, "documents": [copy.deepcopy(d) for d in documents]}
