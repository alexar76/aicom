"""Document model: envelope and subject validation, and issuance (SPEC.md sections 3, 10).

Validation functions take a :class:`awr.errors.Reasons` accumulator and never stop at the
first problem, because section 11.1 requires a verifier to report every error it can
determine -- diagnosing an interoperability failure one error per run is what makes
independent implementation expensive.
"""

from __future__ import annotations

import copy
import datetime as _dt
import re
import uuid
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple

from .digest import canonical_sri, parse_sri
from .didkey import SigningKey, check_public_key_jwk, parse_did_key
from .errors import (
    AWR_BLAME_002,
    AWR_BLAME_003,
    AWR_BLAME_004,
    AWR_CHAIN_001,
    AWR_CHAIN_002,
    AWR_CHAIN_006,
    AWR_DOC_002,
    AWR_DOC_003,
    AWR_DOC_004,
    AWR_DOC_005,
    AWR_DOC_006,
    AWR_DOC_007,
    AWR_DOC_008,
    AWR_DOC_009,
    AWR_DOC_010,
    AWR_ENV_001,
    AWR_L2_001,
    AWR_RCPT_001,
    AWR_RCPT_002,
    AWR_RCPT_003,
    AWR_RCPT_004,
    AWR_RCPT_005,
    AWR_RCPT_006,
    AWR_VDCT_001,
    AWR_VDCT_002,
    AWR_VDCT_003,
    AWR_VDCT_004,
    AWR_VDCT_006,
    AWR_VDCT_007,
    AwrError,
    Reasons,
)
from .proof import sign_document, verify_document_signature

VC_CONTEXT = "https://www.w3.org/ns/credentials/v2"
AWR_CONTEXT = "https://verify.modelmarket.dev/ns/awr/v2"
AWR_VERSION = "2.0.0"
AWR_MAJOR_VERSION = 2

TYPE_WORK_RECEIPT = "WorkReceipt"
TYPE_VERIFICATION_VERDICT = "VerificationVerdict"
TYPE_BLAME_ATTESTATION = "BlameAttestation"
AWR_TYPES = (TYPE_WORK_RECEIPT, TYPE_VERIFICATION_VERDICT, TYPE_BLAME_ATTESTATION)

WORK_STATUSES = ("succeeded", "failed", "refused", "timeout", "partial")
VERDICTS = ("pass", "fail", "inconclusive")
FAILURE_CLASSES = (
    "wrong-output",
    "malformed-output",
    "unavailable",
    "timeout",
    "policy-violation",
    "upstream-input",
    "cost-overrun",
    "unknown",
)

_RFC3339_RE = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(\.\d+)?Z$"
)
_ABSOLUTE_URI_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]*:[^\s]+$")
_AMOUNT_RE = re.compile(r"^-?(0|[1-9][0-9]*)(\.[0-9]+)?$")
_UNIT_INTERVAL_RE = re.compile(r"^(0(\.[0-9]+)?|1(\.0+)?)$")
_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")
_VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")

#: The digest of the empty byte string, as an SRI value.  Section 3.3 permits it as the
#: outputDigest of a receipt whose work did not succeed.
EMPTY_PAYLOAD_SRI = "sha256-47DEQpj8HBSa+/TImW+5JCeuQeRkm5NMpJWZG3hSuFU="


# ---------------------------------------------------------------------------
# scalar helpers
# ---------------------------------------------------------------------------


def parse_rfc3339_utc(value: Any) -> Optional[_dt.datetime]:
    """Parse an RFC 3339 UTC ``date-time`` with a literal ``Z`` and second precision.

    Returns ``None`` when *value* is not such a string.  Offsets other than ``Z`` are
    refused: section 3.1 requires UTC so that two documents' timestamps are comparable as
    strings as well as instants.
    """
    if not isinstance(value, str):
        return None
    match = _RFC3339_RE.match(value)
    if match is None:
        return None
    year, month, day, hour, minute, second = (int(match.group(i)) for i in range(1, 7))
    fraction = match.group(7)
    microsecond = 0
    if fraction:
        digits = (fraction[1:] + "000000")[:6]
        microsecond = int(digits)
    try:
        return _dt.datetime(
            year,
            month,
            day,
            hour,
            minute,
            second,
            microsecond,
            tzinfo=_dt.timezone.utc,
        )
    except ValueError:
        return None


def is_absolute_uri(value: Any) -> bool:
    return isinstance(value, str) and _ABSOLUTE_URI_RE.match(value) is not None


def is_decimal_amount(value: Any) -> bool:
    return isinstance(value, str) and _AMOUNT_RE.match(value) is not None


def is_unit_interval_decimal(value: Any) -> bool:
    """Decimal string in the closed unit interval, compared as decimal (section 4.3)."""
    if not isinstance(value, str) or _UNIT_INTERVAL_RE.match(value) is None:
        return False
    try:
        number = Decimal(value)
    except InvalidOperation:
        return False
    return Decimal(0) <= number <= Decimal(1)


def is_plain_integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def now_utc() -> _dt.datetime:
    return _dt.datetime.now(tz=_dt.timezone.utc)


def format_rfc3339_utc(moment: _dt.datetime) -> str:
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=_dt.timezone.utc)
    moment = moment.astimezone(_dt.timezone.utc)
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def coerce_now(value: Any) -> _dt.datetime:
    """Accept ``None`` (current time), a ``datetime`` or an RFC 3339 UTC string."""
    if value is None:
        return now_utc()
    if isinstance(value, _dt.datetime):
        return value if value.tzinfo else value.replace(tzinfo=_dt.timezone.utc)
    parsed = parse_rfc3339_utc(value)
    if parsed is None:
        raise ValueError("--now must be an RFC 3339 UTC date-time, got %r" % (value,))
    return parsed


# ---------------------------------------------------------------------------
# envelope
# ---------------------------------------------------------------------------


class Envelope(object):
    """Facts extracted from the common envelope during validation."""

    def __init__(self) -> None:
        self.document_type: Optional[str] = None
        self.issuer_id: Optional[str] = None
        self.awr_version: Optional[str] = None
        self.valid_from: Optional[_dt.datetime] = None
        self.valid_until: Optional[_dt.datetime] = None


def check_envelope(document: Dict[str, Any], reasons: Reasons) -> Envelope:
    """Check section 3.1 and return what the rest of the pipeline needs."""
    envelope = Envelope()

    context = document.get("@context")
    if not isinstance(context, list) or not context or context[0] != VC_CONTEXT:
        reasons.add(
            AWR_DOC_002,
            "@context must be an array whose first element is %r" % (VC_CONTEXT,),
        )
    if not isinstance(context, list) or AWR_CONTEXT not in context:
        reasons.add(
            AWR_DOC_003, "@context must contain the AWR namespace %r" % (AWR_CONTEXT,)
        )

    if not is_absolute_uri(document.get("id")):
        reasons.add(
            AWR_DOC_006,
            "id must be present and an absolute URI, got %r" % (document.get("id"),),
        )

    types = document.get("type")
    if not isinstance(types, list) or "VerifiableCredential" not in types:
        reasons.add(AWR_DOC_004, "type must be an array containing VerifiableCredential")
    # §3.1: `type` is a set. A repeated member is what makes a reader that takes the first
    # match and a reader that counts matches disagree about the same bytes, so it is
    # rejected outright rather than de-duplicated.
    if isinstance(types, list):
        seen = set()
        duplicates = []
        for entry in types:
            key = entry if isinstance(entry, str) else repr(entry)
            if key in seen and key not in duplicates:
                duplicates.append(key)
            seen.add(key)
        if duplicates:
            reasons.add(
                AWR_DOC_005,
                "type is a set and must not repeat a value; repeated: %s"
                % ", ".join(repr(d) for d in duplicates),
            )

    awr_types = (
        [t for t in types if t in AWR_TYPES] if isinstance(types, list) else []
    )
    if len(set(awr_types)) != 1:
        reasons.add(
            AWR_DOC_005,
            "type must contain exactly one of %s, found %s"
            % (", ".join(AWR_TYPES), awr_types or "none"),
        )
    else:
        envelope.document_type = awr_types[0]

    issuer = document.get("issuer")
    if not isinstance(issuer, dict):
        reasons.add(
            AWR_DOC_010,
            "issuer must be an object with an id; a bare-string issuer is rejected in "
            "AWR/2 (section 3.1)",
        )
    elif not isinstance(issuer.get("id"), str) or not issuer.get("id"):
        reasons.add(AWR_DOC_010, "issuer.id must be a non-empty string")
    else:
        envelope.issuer_id = issuer["id"]

    valid_from = parse_rfc3339_utc(document.get("validFrom"))
    if valid_from is None:
        reasons.add(
            AWR_DOC_007,
            "validFrom must be an RFC 3339 UTC date-time ending in Z, got %r"
            % (document.get("validFrom"),),
        )
    envelope.valid_from = valid_from
    if "validUntil" in document:
        valid_until = parse_rfc3339_utc(document.get("validUntil"))
        if valid_until is None:
            reasons.add(
                AWR_DOC_007,
                "validUntil must be an RFC 3339 UTC date-time ending in Z, got %r"
                % (document.get("validUntil"),),
            )
        elif valid_from is not None and valid_until <= valid_from:
            reasons.add(
                AWR_DOC_007, "validUntil must be later than validFrom"
            )
        envelope.valid_until = valid_until

    version = document.get("awrVersion")
    envelope.awr_version = version if isinstance(version, str) else None
    match = _VERSION_RE.match(version) if isinstance(version, str) else None
    if match is None:
        reasons.add(
            AWR_DOC_009,
            "awrVersion must be a semantic version string, got %r" % (version,),
        )
    elif int(match.group(1)) != AWR_MAJOR_VERSION:
        reasons.add(
            AWR_DOC_009,
            "awrVersion major %s is not implemented by this verifier (AWR/%d)"
            % (match.group(1), AWR_MAJOR_VERSION),
        )

    subject = document.get("credentialSubject")
    if not isinstance(subject, dict):
        reasons.add(
            AWR_DOC_008,
            "credentialSubject must be a single object, got %s"
            % (type(subject).__name__,),
        )

    return envelope


def check_issuer_key(
    document: Dict[str, Any], issuer_id: Optional[str], reasons: Reasons
) -> Optional[bytes]:
    """Derive the public key from ``issuer.id`` and cross-check ``publicKeyJwk``."""
    if issuer_id is None:
        return None
    try:
        public_key = parse_did_key(issuer_id)
    except AwrError as err:
        reasons.add_error_obj(err)
        return None
    issuer = document.get("issuer")
    if isinstance(issuer, dict) and "publicKeyJwk" in issuer:
        try:
            check_public_key_jwk(issuer["publicKeyJwk"], public_key)
        except AwrError as err:
            reasons.add_error_obj(err)
            return None
    return public_key


# ---------------------------------------------------------------------------
# digest references
# ---------------------------------------------------------------------------


def validate_digest_reference(
    reference: Any,
    reasons: Reasons,
    where: str,
    *,
    require_id: bool,
    missing_code: str,
    format_code: str = AWR_CHAIN_002,
) -> Optional[str]:
    """Validate a section 3.2 digest reference; return its ``digestSRI`` when usable."""
    if not isinstance(reference, dict):
        reasons.add(
            missing_code,
            "%s must be a digest reference object, got %s"
            % (where, type(reference).__name__),
        )
        return None
    sri = reference.get("digestSRI")
    if sri is None:
        reasons.add(missing_code, "%s is missing digestSRI" % (where,))
        return None
    try:
        parse_sri(sri)
    except ValueError as exc:
        reasons.add(format_code, "%s: %s" % (where, exc))
        return None
    if require_id:
        ref_id = reference.get("id")
        if not isinstance(ref_id, str) or not ref_id:
            reasons.add(missing_code, "%s is missing id" % (where,))
            return None
    return sri


# ---------------------------------------------------------------------------
# subjects
# ---------------------------------------------------------------------------


class ReceiptFacts(object):
    def __init__(self) -> None:
        self.parents: List[Dict[str, Any]] = []
        self.input_digest: Optional[str] = None
        self.output_digest: Optional[str] = None
        self.has_settlement_binding = False


def _check_amount_object(value: Any, reasons: Reasons, where: str, code: str) -> None:
    if not isinstance(value, dict):
        reasons.add(code, "%s must be an object" % (where,))
        return
    currency = value.get("currency")
    if not isinstance(currency, str) or not (
        _CURRENCY_RE.match(currency) or currency.startswith("urn:")
    ):
        reasons.add(
            code,
            "%s.currency must be an ISO 4217 alphabetic code or a urn: URI, got %r"
            % (where, currency),
        )
    if not is_decimal_amount(value.get("amount")):
        reasons.add(
            code,
            "%s.amount must be a decimal string matching "
            "^-?(0|[1-9][0-9]*)(\\.[0-9]+)?$, got %r (a JSON number is not permitted, "
            "section 4.3)" % (where, value.get("amount")),
        )


def validate_work_receipt(subject: Dict[str, Any], reasons: Reasons) -> ReceiptFacts:
    facts = ReceiptFacts()

    work = subject.get("work")
    if not isinstance(work, dict):
        reasons.add(AWR_RCPT_003, "credentialSubject.work must be an object")
        reasons.add(AWR_RCPT_005, "work.modelId is missing (no work object)")
        reasons.add(AWR_RCPT_006, "work.status is missing (no work object)")
    else:
        model_id = work.get("modelId")
        if not isinstance(model_id, str) or not model_id:
            reasons.add(
                AWR_RCPT_005, "work.modelId must be a non-empty string, got %r" % (model_id,)
            )
        status = work.get("status")
        if status not in WORK_STATUSES:
            reasons.add(
                AWR_RCPT_006,
                "work.status must be one of %s, got %r"
                % (", ".join(WORK_STATUSES), status),
            )
        completed = parse_rfc3339_utc(work.get("completedAt"))
        if completed is None:
            reasons.add(
                AWR_RCPT_003,
                "work.completedAt must be an RFC 3339 UTC date-time, got %r"
                % (work.get("completedAt"),),
            )
        if "startedAt" in work:
            started = parse_rfc3339_utc(work.get("startedAt"))
            if started is None:
                reasons.add(
                    AWR_RCPT_003,
                    "work.startedAt must be an RFC 3339 UTC date-time, got %r"
                    % (work.get("startedAt"),),
                )
            elif completed is not None and completed < started:
                reasons.add(
                    AWR_RCPT_003,
                    "work.completedAt %s is earlier than work.startedAt %s"
                    % (work.get("completedAt"), work.get("startedAt")),
                )
        if "latencyMs" in work:
            latency = work.get("latencyMs")
            if not is_plain_integer(latency) or latency < 0:
                reasons.add(
                    AWR_RCPT_004,
                    "work.latencyMs must be a non-negative integer, got %r" % (latency,),
                )

    for field in ("inputDigest", "outputDigest"):
        value = subject.get(field)
        if value is None:
            reasons.add(AWR_RCPT_001, "%s is missing" % (field,))
            continue
        try:
            parse_sri(value)
        except ValueError as exc:
            reasons.add(AWR_RCPT_001, "%s: %s" % (field, exc))
            continue
        if field == "inputDigest":
            facts.input_digest = value
        else:
            facts.output_digest = value

    if "parents" in subject:
        parents = subject.get("parents")
        if not isinstance(parents, list):
            reasons.add(AWR_CHAIN_001, "parents must be an array of digest references")
        else:
            by_id: Dict[str, set] = {}
            for index, entry in enumerate(parents):
                where = "parents[%d]" % (index,)
                sri = validate_digest_reference(
                    entry,
                    reasons,
                    where,
                    require_id=False,
                    missing_code=AWR_CHAIN_001,
                )
                if sri is None:
                    continue
                entry_id = entry.get("id")
                if isinstance(entry_id, str) and entry_id:
                    by_id.setdefault(entry_id, set()).add(sri)
                role = entry.get("role")
                if role is not None and not isinstance(role, str):
                    reasons.add(
                        AWR_CHAIN_002, "%s.role must be a string when present" % (where,)
                    )
                    continue
                facts.parents.append(entry)
            for entry_id, digests in by_id.items():
                if len(digests) > 1:
                    reasons.add(
                        AWR_CHAIN_006,
                        "parent id %s appears with %d conflicting digests"
                        % (entry_id, len(digests)),
                    )

    if "price" in subject:
        _check_amount_object(subject.get("price"), reasons, "price", AWR_RCPT_002)

    environment = subject.get("environment")
    if isinstance(environment, dict):
        for member in ("teeAttestation", "zkProof"):
            if member in environment:
                reasons.add(
                    AWR_ENV_001,
                    "environment.%s is present and was not verified; AWR/2 treats it as "
                    "an opaque object (section 7.3)" % (member,),
                )

    settlement = subject.get("settlement")
    if settlement is not None:
        if (
            isinstance(settlement, dict)
            and isinstance(settlement.get("scheme"), str)
            and settlement.get("scheme")
        ):
            facts.has_settlement_binding = True
            if "amount" in settlement:
                _check_amount_object(
                    settlement.get("amount"), reasons, "settlement.amount", AWR_RCPT_002
                )
            reasons.add(
                AWR_L2_001,
                "settlement binding %r is present, well-formed and signed; on-chain "
                "existence was NOT checked (section 10.3)" % (settlement.get("scheme"),),
            )

    return facts


class VerdictFacts(object):
    def __init__(self) -> None:
        self.verified_work_digest: Optional[str] = None
        self.verified_work_id: Optional[str] = None
        self.has_stake_binding = False


def validate_verification_verdict(
    subject: Dict[str, Any], reasons: Reasons
) -> VerdictFacts:
    facts = VerdictFacts()

    if "verifiedWork" not in subject:
        reasons.add(AWR_VDCT_001, "verifiedWork is missing")
    else:
        digest = validate_digest_reference(
            subject.get("verifiedWork"),
            reasons,
            "verifiedWork",
            require_id=True,
            missing_code=AWR_VDCT_001,
        )
        facts.verified_work_digest = digest
        reference = subject.get("verifiedWork")
        if isinstance(reference, dict) and isinstance(reference.get("id"), str):
            facts.verified_work_id = reference["id"]

    verdict = subject.get("verdict")
    if verdict not in VERDICTS:
        reasons.add(
            AWR_VDCT_004,
            "verdict must be one of %s, got %r" % (", ".join(VERDICTS), verdict),
        )

    score = subject.get("score")
    if score is not None and not is_unit_interval_decimal(score):
        reasons.add(
            AWR_VDCT_002,
            "score must be a decimal string in [0,1] (never a JSON number), got %r"
            % (score,),
        )

    method = subject.get("method")
    if not isinstance(method, dict) or not (
        isinstance(method.get("id"), str) and method.get("id")
    ):
        reasons.add(
            AWR_VDCT_003, "method must be an object with a non-empty id"
        )
    elif "modelIds" in method:
        model_ids = method.get("modelIds")
        if not isinstance(model_ids, list) or not all(
            isinstance(item, str) for item in model_ids
        ):
            reasons.add(AWR_VDCT_003, "method.modelIds must be an array of strings")

    threshold = None
    policy = subject.get("policy")
    if isinstance(policy, dict) and "threshold" in policy:
        threshold = policy.get("threshold")
        if not is_unit_interval_decimal(threshold):
            # Section 3.4 constrains policy.threshold but registers no code of its own;
            # AWR-VDCT-002 is the registry's decimal-string-in-[0,1] code.  See README.
            reasons.add(
                AWR_VDCT_002,
                "policy.threshold must be a decimal string in [0,1], got %r"
                % (threshold,),
            )
            threshold = None

    if (
        verdict in ("pass", "fail")
        and is_unit_interval_decimal(score)
        and is_unit_interval_decimal(threshold)
    ):
        meets = Decimal(score) >= Decimal(threshold)
        if (verdict == "pass") != meets:
            reasons.add(
                AWR_VDCT_006,
                "verdict %r disagrees with score %s against threshold %s; the issuer's "
                "verdict is authoritative but the inconsistency is evidence"
                % (verdict, score, threshold),
            )

    if "evidence" in subject:
        evidence = subject.get("evidence")
        if not isinstance(evidence, list):
            reasons.add(AWR_VDCT_007, "evidence must be an array")
        else:
            for index, entry in enumerate(evidence):
                validate_digest_reference(
                    entry,
                    reasons,
                    "evidence[%d]" % (index,),
                    require_id=False,
                    missing_code=AWR_VDCT_007,
                )

    stake = subject.get("stake")
    if stake is not None:
        if (
            isinstance(stake, dict)
            and isinstance(stake.get("scheme"), str)
            and stake.get("scheme")
        ):
            facts.has_stake_binding = True
            if "amount" in stake:
                _check_amount_object(
                    stake.get("amount"), reasons, "stake.amount", AWR_VDCT_002
                )
            if "slashingPolicy" in stake:
                validate_digest_reference(
                    stake.get("slashingPolicy"),
                    reasons,
                    "stake.slashingPolicy",
                    require_id=False,
                    missing_code=AWR_VDCT_007,
                )
            reasons.add(
                AWR_L2_001,
                "stake binding %r is present, well-formed and signed; on-chain existence "
                "was NOT checked (section 10.3)" % (stake.get("scheme"),),
            )

    return facts


class BlameFacts(object):
    def __init__(self) -> None:
        self.chain_digest: Optional[str] = None
        self.chain_id: Optional[str] = None
        self.blamed_digest: Optional[str] = None
        self.blamed_id: Optional[str] = None


def validate_blame_attestation(
    subject: Dict[str, Any], reasons: Reasons
) -> BlameFacts:
    facts = BlameFacts()

    for field in ("chain", "blamedWork"):
        if field not in subject:
            reasons.add(AWR_BLAME_003, "%s is missing" % (field,))
            continue
        digest = validate_digest_reference(
            subject.get(field),
            reasons,
            field,
            require_id=True,
            missing_code=AWR_BLAME_003,
        )
        reference = subject.get(field)
        ref_id = reference.get("id") if isinstance(reference, dict) else None
        if field == "chain":
            facts.chain_digest = digest
            facts.chain_id = ref_id if isinstance(ref_id, str) else None
        else:
            facts.blamed_digest = digest
            facts.blamed_id = ref_id if isinstance(ref_id, str) else None

    failure_class = subject.get("failureClass")
    if failure_class not in FAILURE_CLASSES:
        reasons.add(
            AWR_BLAME_002,
            "failureClass must be one of %s, got %r"
            % (", ".join(FAILURE_CLASSES), failure_class),
        )

    confidence = subject.get("confidence")
    if confidence is not None and not is_unit_interval_decimal(confidence):
        reasons.add(
            AWR_BLAME_004,
            "confidence must be a decimal string in [0,1], got %r" % (confidence,),
        )

    method = subject.get("method")
    if not isinstance(method, dict) or not (
        isinstance(method.get("id"), str) and method.get("id")
    ):
        # Section 3.5 requires method with a non-empty id but registers no AWR-BLAME code
        # for it; AWR-VDCT-003 is the registry's "method missing or method.id empty".
        reasons.add(
            AWR_VDCT_003,
            "method must be an object with a non-empty id (BlameAttestation)",
        )

    if "evidence" in subject:
        evidence = subject.get("evidence")
        if not isinstance(evidence, list):
            reasons.add(AWR_VDCT_007, "evidence must be an array")
        else:
            for index, entry in enumerate(evidence):
                validate_digest_reference(
                    entry,
                    reasons,
                    "evidence[%d]" % (index,),
                    require_id=False,
                    missing_code=AWR_VDCT_007,
                )

    return facts


def validate_subject(
    document_type: Optional[str], subject: Any, reasons: Reasons
) -> Optional[Any]:
    """Dispatch to the type-specific subject validator (sections 3.3-3.5)."""
    if document_type is None or not isinstance(subject, dict):
        return None
    if document_type == TYPE_WORK_RECEIPT:
        return validate_work_receipt(subject, reasons)
    if document_type == TYPE_VERIFICATION_VERDICT:
        return validate_verification_verdict(subject, reasons)
    if document_type == TYPE_BLAME_ATTESTATION:
        return validate_blame_attestation(subject, reasons)
    return None


# ---------------------------------------------------------------------------
# issuance
# ---------------------------------------------------------------------------


def document_reference(document: Dict[str, Any]) -> Dict[str, str]:
    """A section 3.2 digest reference to *document* (a secured AWR document)."""
    reference = {"digestSRI": canonical_sri(document)}
    doc_id = document.get("id")
    if isinstance(doc_id, str) and doc_id:
        reference["id"] = doc_id
    return reference


class IssuanceError(AwrError):
    """Raised when the reference issuer would emit a document it would itself reject."""


def issue(
    subject: Dict[str, Any],
    key: SigningKey,
    *,
    document_type: str = TYPE_WORK_RECEIPT,
    document_id: Optional[str] = None,
    valid_from: Optional[str] = None,
    valid_until: Optional[str] = None,
    created: Optional[str] = None,
    issuer_name: Optional[str] = None,
    include_public_key_jwk: bool = False,
    extra_context: Optional[List[str]] = None,
    extra_types: Optional[List[str]] = None,
    extra_properties: Optional[Dict[str, Any]] = None,
    now: Any = None,
    validate: bool = True,
) -> Dict[str, Any]:
    """Issue a signed AWR/2 document.

    There is no parameter, and no other function in this package, that produces an AWR/1
    proof: section 12 requires an implementation never to issue one, so the capability is
    absent rather than guarded.
    """
    if document_type not in AWR_TYPES:
        raise ValueError(
            "document_type must be one of %s, got %r"
            % (", ".join(AWR_TYPES), document_type)
        )
    if not isinstance(subject, dict):
        raise ValueError("credentialSubject must be an object")

    moment = format_rfc3339_utc(coerce_now(now))
    context: List[str] = [VC_CONTEXT, AWR_CONTEXT]
    if extra_context:
        context.extend(extra_context)
    types: List[str] = ["VerifiableCredential", document_type]
    if extra_types:
        types.extend(extra_types)

    issuer: Dict[str, Any] = {"id": key.did}
    if issuer_name:
        issuer["name"] = issuer_name
    if include_public_key_jwk:
        issuer["publicKeyJwk"] = key.public_key_jwk()

    document: Dict[str, Any] = {
        "@context": context,
        "id": document_id or ("urn:uuid:%s" % (uuid.uuid4(),)),
        "type": types,
        "issuer": issuer,
        "validFrom": valid_from or moment,
        "awrVersion": AWR_VERSION,
        "credentialSubject": copy.deepcopy(subject),
    }
    if valid_until:
        document["validUntil"] = valid_until
    if extra_properties:
        for name, value in extra_properties.items():
            if name in ("proof",):
                raise ValueError("extra_properties must not contain %r" % (name,))
            document[name] = copy.deepcopy(value)

    secured = sign_document(document, key, created or document["validFrom"])

    if validate:
        reasons = Reasons()
        envelope = check_envelope(secured, reasons)
        public_key = check_issuer_key(secured, envelope.issuer_id, reasons)
        validate_subject(envelope.document_type, secured.get("credentialSubject"), reasons)
        if public_key is None or not verify_document_signature(
            secured, secured["proof"], public_key
        ):
            reasons.add(
                "AWR-PROOF-006", "the issuer's own signature did not verify"
            )
        if reasons.has_errors():
            raise IssuanceError(
                reasons.errors[0]["code"],
                "refusing to issue a document this implementation would reject: %s"
                % ("; ".join(
                    "%s %s" % (e["code"], e["detail"]) for e in reasons.errors
                ),),
            )
    return secured


def issue_work_receipt(subject: Dict[str, Any], key: SigningKey, **kwargs: Any) -> Dict[str, Any]:
    kwargs["document_type"] = TYPE_WORK_RECEIPT
    return issue(subject, key, **kwargs)


def issue_verification_verdict(
    subject: Dict[str, Any], key: SigningKey, **kwargs: Any
) -> Dict[str, Any]:
    kwargs["document_type"] = TYPE_VERIFICATION_VERDICT
    return issue(subject, key, **kwargs)


def issue_blame_attestation(
    subject: Dict[str, Any], key: SigningKey, **kwargs: Any
) -> Dict[str, Any]:
    kwargs["document_type"] = TYPE_BLAME_ATTESTATION
    return issue(subject, key, **kwargs)


def document_type_of(document: Any) -> Optional[str]:
    """The AWR type of *document*, or ``None`` when it does not name exactly one."""
    if not isinstance(document, dict):
        return None
    types = document.get("type")
    if not isinstance(types, list):
        return None
    found = [t for t in types if t in AWR_TYPES]
    return found[0] if len(found) == 1 else None


def envelope_summary(document: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    """``(documentType, issuerId)`` without emitting reasons -- for reporting only."""
    issuer = document.get("issuer") if isinstance(document, dict) else None
    issuer_id = issuer.get("id") if isinstance(issuer, dict) else None
    return document_type_of(document), issuer_id if isinstance(issuer_id, str) else None
