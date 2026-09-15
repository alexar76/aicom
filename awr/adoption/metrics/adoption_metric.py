#!/usr/bin/env python3
"""Measure AWR adoption as exactly one number.

    THE METRIC:  how many AWR documents exist that were issued by a key
                 this project does not control.

Reported as a count of *distinct foreign issuer DIDs*.  Everything else this script
prints -- document totals, per-type counts, per-profile counts -- is context, and is
labelled as context in both outputs so it cannot quietly be promoted to the headline
later.  One enthusiastic adopter emitting a million receipts is one adopter.

Nothing here touches the network: it walks the filesystem, verifies with the AWR
reference implementation (``awr/reference/python``) when that is importable, and prints.
Section 13.5 of the spec forbids a verifier from dereferencing anything, and an adoption
counter that phoned home would be a worse offender than a verifier.

Usage::

    python3 adoption_metric.py CORPUS_DIR [MORE_PATHS ...]
    python3 adoption_metric.py corpus/ --own-keys own-keys.txt --format json

Exit codes: ``0`` report produced, ``1`` ``--fail-under`` threshold not met,
``2`` usage or I/O error.  Invalid documents are data, not an error: they are counted,
reported, and excluded from the metric.

Dependencies: the standard library, plus whatever the AWR reference implementation needs
(``cryptography``, for Ed25519).  Nothing else.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import sys
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

# ---------------------------------------------------------------------------
# the metric, written down once
# ---------------------------------------------------------------------------

METRIC_ID = "awr.adoption.distinct-foreign-issuers"

METRIC_DEFINITION = (
    "The number of distinct did:key issuer identifiers that appear in valid AWR/2 "
    "documents and are not listed in this project's own-keys file. A document counts "
    "once per document id; an issuer counts once regardless of how many documents it "
    "issued. Documents that fail verification never count."
)

REPORT_SCHEMA = "awr-adoption-report/1"

# Any change to METRIC_DEFINITION changes this digest, and the test suite pins it.
# Replacing the metric therefore requires editing a test, which shows up in a diff.
METRIC_DEFINITION_DIGEST = hashlib.sha256(METRIC_DEFINITION.encode("utf-8")).hexdigest()

DEFAULT_OWN_KEYS_FILENAME = "own-keys.txt"
OWN_KEYS_ENV_VAR = "AWR_OWN_KEYS"

DOCUMENT_SUFFIXES = (".json",)
LINES_SUFFIXES = (".jsonl", ".ndjson")
SKIP_DIRECTORY_NAMES = frozenset(
    (".git", ".hg", ".svn", "node_modules", "__pycache__", ".venv", "venv", ".tox")
)

TIMESTAMP_FIELD = "validFrom"

_HERE = os.path.dirname(os.path.abspath(__file__))
# awr/adoption/metrics -> awr/reference/python
_REFERENCE_PYTHON = os.path.normpath(os.path.join(_HERE, "..", "..", "reference", "python"))


# ---------------------------------------------------------------------------
# reference implementation, optional
# ---------------------------------------------------------------------------


def _import_reference() -> Tuple[Optional[Any], Optional[str]]:
    """Import :mod:`awr`, trying the in-repo reference implementation as a fallback.

    Returns ``(module, source)`` or ``(None, reason)``.
    """
    try:
        import awr  # type: ignore

        return awr, getattr(awr, "__file__", "installed")
    except Exception:  # pragma: no cover - depends on the machine
        pass
    if os.path.isdir(_REFERENCE_PYTHON) and _REFERENCE_PYTHON not in sys.path:
        sys.path.insert(0, _REFERENCE_PYTHON)
    try:
        import awr  # type: ignore

        return awr, getattr(awr, "__file__", _REFERENCE_PYTHON)
    except Exception as exc:
        return None, "%s: %s" % (type(exc).__name__, exc)


class ReferenceVerifier(object):
    """Verifies with the AWR reference implementation. Signatures are actually checked."""

    available = True
    checks_signatures = True

    def __init__(self, module: Any, source: str) -> None:
        self._awr = module
        self.source = source
        self.name = "awr reference implementation %s" % (
            getattr(module, "__version__", "?"),
        )

    def parse(self, data: bytes) -> Any:
        """Strict §4 parse: duplicate names and non-integer numbers are rejected."""
        return self._awr.loads(data)

    def parse_error_code(self, exc: BaseException) -> str:
        code = getattr(exc, "code", None)
        return code if isinstance(code, str) else "AWR-CANON-005"

    def is_bundle(self, value: Any) -> bool:
        from awr.verify import is_bundle  # type: ignore

        return is_bundle(value)

    def digest(self, document: Dict[str, Any]) -> Optional[str]:
        try:
            return self._awr.canonical_sri(document)
        except Exception:
            return None

    def prepare(self, documents: Sequence[Dict[str, Any]]) -> Any:
        from awr.verify import SupportingSet  # type: ignore

        return SupportingSet(list(documents))

    def verify(self, payload: Any, supporting: Any, now: Optional[str]) -> Dict[str, Any]:
        return self._awr.verify_document(payload, supporting=supporting, now=now)


class StructuralVerifier(object):
    """Fallback when the reference implementation cannot be imported.

    It checks envelope shape only. It does **not** check a single signature, so the
    number it produces is an upper bound on adoption, not the metric. Both outputs say
    so loudly; do not quote a degraded run.
    """

    available = False
    checks_signatures = False
    name = "structural fallback (NO SIGNATURE VERIFICATION)"
    source = None
    #: True when the operator asked for this mode instead of it being forced on us by a
    #: missing reference implementation. Only changes how the warning reads.
    forced = False

    VC_CONTEXT = "https://www.w3.org/ns/credentials/v2"
    AWR_CONTEXT = "https://verify.modelmarket.dev/ns/awr/v2"
    AWR_TYPES = ("WorkReceipt", "VerificationVerdict", "BlameAttestation")

    def parse(self, data: bytes) -> Any:
        def pairs(items: List[Tuple[str, Any]]) -> Dict[str, Any]:
            seen: Set[str] = set()
            for key, _ in items:
                if key in seen:
                    raise ValueError("duplicate object property name %r" % (key,))
                seen.add(key)
            return dict(items)

        def reject_float(text: str) -> Any:
            raise ValueError("non-integer JSON number %s (spec §4.3)" % (text,))

        return json.loads(data, object_pairs_hook=pairs, parse_float=reject_float)

    def parse_error_code(self, exc: BaseException) -> str:
        return "AWR-CANON-005"

    def is_bundle(self, value: Any) -> bool:
        return isinstance(value, dict) and "awrBundle" in value

    def digest(self, document: Dict[str, Any]) -> Optional[str]:
        try:
            blob = json.dumps(
                document, sort_keys=True, separators=(",", ":"), ensure_ascii=False
            )
        except (TypeError, ValueError):
            return None
        # Not RFC 8785. Used only to notice two different documents sharing one id.
        return "sha256-approx-" + hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def prepare(self, documents: Sequence[Dict[str, Any]]) -> Any:
        return None

    def verify(self, payload: Any, supporting: Any, now: Optional[str]) -> Dict[str, Any]:
        document = payload
        if isinstance(document, (bytes, bytearray, str)):
            try:
                document = self.parse(
                    document if isinstance(document, (bytes, bytearray))
                    else document.encode("utf-8")
                )
            except Exception as exc:
                return _result(False, reasons=[("AWR-CANON-005", str(exc))])
        reasons: List[Tuple[str, str]] = []
        if not isinstance(document, dict):
            return _result(False, reasons=[("AWR-DOC-001", "not a JSON object")])
        context = document.get("@context")
        if not isinstance(context, list) or not context or context[0] != self.VC_CONTEXT:
            reasons.append(("AWR-DOC-002", "@context missing or wrong first element"))
        elif self.AWR_CONTEXT not in context:
            reasons.append(("AWR-DOC-003", "AWR namespace absent from @context"))
        types = document.get("type")
        if not isinstance(types, list) or "VerifiableCredential" not in types:
            reasons.append(("AWR-DOC-004", "type missing VerifiableCredential"))
        found = [t for t in types if t in self.AWR_TYPES] if isinstance(types, list) else []
        if len(found) != 1:
            reasons.append(("AWR-DOC-005", "type does not name exactly one AWR type"))
        doc_id = document.get("id")
        if not isinstance(doc_id, str) or ":" not in doc_id:
            reasons.append(("AWR-DOC-006", "id missing or not an absolute URI"))
        if not isinstance(document.get(TIMESTAMP_FIELD), str):
            reasons.append(("AWR-DOC-007", "validFrom missing"))
        if not isinstance(document.get("credentialSubject"), dict):
            reasons.append(("AWR-DOC-008", "credentialSubject missing or not an object"))
        version = document.get("awrVersion")
        if not isinstance(version, str) or not version.startswith("2."):
            reasons.append(("AWR-DOC-009", "awrVersion missing or not 2.x"))
        issuer = document.get("issuer")
        if not isinstance(issuer, dict) or not isinstance(issuer.get("id"), str):
            reasons.append(("AWR-DOC-010", "issuer missing, not an object, or missing id"))
        if not isinstance(document.get("proof"), (dict, list)):
            reasons.append(("AWR-PROOF-001", "proof missing"))
        return _result(
            not reasons,
            reasons=reasons,
            document_type=found[0] if len(found) == 1 else None,
            awr_version=version if isinstance(version, str) else None,
            profile=None,
        )


def _result(
    valid: bool,
    reasons: Optional[Sequence[Tuple[str, str]]] = None,
    document_type: Optional[str] = None,
    awr_version: Optional[str] = None,
    profile: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "valid": bool(valid),
        "awrVersion": awr_version,
        "documentType": document_type,
        "profile": profile,
        "reasons": [{"code": c, "severity": "error", "detail": d} for c, d in (reasons or ())],
        "warnings": [],
    }


def build_verifier(require_reference: bool = False, force_structural: bool = False) -> Any:
    """Pick a verifier.

    *force_structural* exists so the degraded mode is demonstrable on a machine where the
    reference implementation imports fine: it is the only way to reproduce the "structural
    fallback counts the tampered document" line in README.md. It cannot make a run look
    trustworthy -- ``headline.signaturesVerified`` goes to ``false`` and the report carries
    the do-not-quote warning either way -- and it is refused together with
    ``--require-reference``.
    """
    if force_structural:
        if require_reference:
            raise SystemExit(
                "--no-verify-signatures and --require-reference contradict each other"
            )
        verifier = StructuralVerifier()
        verifier.forced = True
        return verifier
    module, source = _import_reference()
    if module is not None:
        return ReferenceVerifier(module, str(source))
    if require_reference:
        raise SystemExit(
            "the AWR reference implementation could not be imported (%s) and "
            "--require-reference was given" % (source,)
        )
    return StructuralVerifier()


# ---------------------------------------------------------------------------
# own keys
# ---------------------------------------------------------------------------


def parse_own_keys(text: str) -> Tuple[Set[str], List[str]]:
    """Parse an own-keys file: one DID per line, ``#`` comments, blanks ignored.

    A ``did:key:z...#z...`` verification method is accepted and reduced to its DID, so
    that pasting a ``proof.verificationMethod`` does the right thing. Comparison is
    exact and case-sensitive: base58btc is case-sensitive, and lowercasing a DID would
    silently stop excluding one of our own keys.
    """
    dids: Set[str] = set()
    problems: List[str] = []
    for number, raw in enumerate(text.splitlines(), start=1):
        # One split serves both jobs: it drops a trailing ``# comment`` and reduces a
        # ``did:key:z…#z…`` verification method to its DID.
        did = raw.split("#", 1)[0].strip()
        if not did:
            continue
        if not did.startswith("did:key:z"):
            problems.append(
                "line %d: %r is not a did:key (an entry that is not a DID excludes "
                "nothing and inflates the metric)" % (number, did)
            )
            continue
        if did in dids:
            problems.append("line %d: %s is listed more than once" % (number, did))
        dids.add(did)
    return dids, problems


def resolve_own_keys_path(explicit: Optional[str]) -> Optional[str]:
    if explicit:
        return explicit
    from_env = os.environ.get(OWN_KEYS_ENV_VAR)
    if from_env:
        return from_env
    default = os.path.join(_HERE, DEFAULT_OWN_KEYS_FILENAME)
    return default if os.path.isfile(default) else None


def load_own_keys(explicit: Optional[str]) -> Tuple[Set[str], Dict[str, Any]]:
    path = resolve_own_keys_path(explicit)
    info: Dict[str, Any] = {
        "source": path,
        "count": 0,
        "dids": [],
        "problems": [],
        "warnings": [],
    }
    if path is None:
        info["warnings"].append(
            "no own-keys file was found (looked at --own-keys, $%s, and %s). Every "
            "issuer will be counted as foreign, which INFLATES the metric."
            % (OWN_KEYS_ENV_VAR, os.path.join(_HERE, DEFAULT_OWN_KEYS_FILENAME))
        )
        return set(), info
    try:
        with open(path, "r", encoding="utf-8") as handle:
            text = handle.read()
    except OSError as exc:
        raise SystemExit("cannot read own-keys file %s: %s" % (path, exc))
    dids, problems = parse_own_keys(text)
    info["count"] = len(dids)
    info["dids"] = sorted(dids)
    info["problems"] = problems
    if not dids:
        info["warnings"].append(
            "own-keys file %s declares no DIDs. Every issuer will be counted as "
            "foreign, which INFLATES the metric." % (path,)
        )
    return dids, info


# ---------------------------------------------------------------------------
# discovery and reading
# ---------------------------------------------------------------------------


class LoadedDocument(object):
    """One candidate AWR document with where it came from."""

    __slots__ = ("source", "locator", "document", "raw")

    def __init__(
        self,
        source: str,
        locator: str,
        document: Optional[Dict[str, Any]],
        raw: Optional[bytes] = None,
    ) -> None:
        self.source = source
        self.locator = locator
        self.document = document
        self.raw = raw

    @property
    def payload(self) -> Any:
        """What to hand the verifier: the received bytes when we still have them."""
        return self.raw if self.raw is not None else self.document


def discover_paths(inputs: Sequence[str]) -> Tuple[List[str], List[Dict[str, str]]]:
    """Expand directories to candidate files. Explicit file paths are always read."""
    files: List[str] = []
    errors: List[Dict[str, str]] = []
    for entry in inputs:
        if os.path.isfile(entry):
            files.append(entry)
            continue
        if not os.path.isdir(entry):
            errors.append({"source": entry, "error": "no such file or directory"})
            continue
        for root, dirnames, filenames in os.walk(entry):
            dirnames[:] = sorted(
                d for d in dirnames if d not in SKIP_DIRECTORY_NAMES and not d.startswith(".")
            )
            for name in sorted(filenames):
                lowered = name.lower()
                if lowered.endswith(DOCUMENT_SUFFIXES + LINES_SUFFIXES):
                    files.append(os.path.join(root, name))
    seen: Set[str] = set()
    unique: List[str] = []
    for path in files:
        real = os.path.realpath(path)
        if real in seen:
            continue
        seen.add(real)
        unique.append(path)
    return unique, errors


def read_file(path: str, verifier: Any) -> Tuple[List[LoadedDocument], List[Dict[str, str]]]:
    """Read one file into candidate documents.

    A file may hold a single document, a §9 bundle, a JSON array of documents, or one
    JSON document per line (``.jsonl``/``.ndjson``).

    A file whose bytes do not survive the strict §4 parse yields **no** documents and is
    reported as an error, including when the offending property sits inside one document
    of a bundle. That is deliberately conservative: a coarse rejection under-counts,
    and this instrument must never over-count.
    """
    documents: List[LoadedDocument] = []
    errors: List[Dict[str, str]] = []
    try:
        with open(path, "rb") as handle:
            data = handle.read()
    except OSError as exc:
        return [], [{"source": path, "error": "cannot read: %s" % (exc,), "code": None}]

    if path.lower().endswith(LINES_SUFFIXES):
        for number, line in enumerate(data.splitlines(), start=1):
            if not line.strip():
                continue
            locator = "%s:%d" % (path, number)
            try:
                value = verifier.parse(line)
            except Exception as exc:
                errors.append(
                    {
                        "source": locator,
                        "error": "not a strictly parseable AWR document: %s" % (exc,),
                        "code": verifier.parse_error_code(exc),
                    }
                )
                continue
            if isinstance(value, dict):
                documents.append(LoadedDocument(path, locator, value, bytes(line)))
            else:
                errors.append(
                    {"source": locator, "error": "line is not a JSON object", "code": "AWR-DOC-001"}
                )
        return documents, errors

    try:
        value = verifier.parse(data)
    except Exception as exc:
        return [], [
            {
                "source": path,
                "error": "not strictly parseable under spec §4: %s" % (exc,),
                "code": verifier.parse_error_code(exc),
            }
        ]

    if verifier.is_bundle(value):
        inner = value.get("documents")
        if not isinstance(inner, list) or not inner:
            return [], [
                {
                    "source": path,
                    "error": "bundle has no non-empty documents array",
                    "code": "AWR-BUNDLE-001",
                }
            ]
        for index, item in enumerate(inner):
            locator = "%s#documents[%d]" % (path, index)
            if isinstance(item, dict):
                documents.append(LoadedDocument(path, locator, item))
            else:
                errors.append(
                    {"source": locator, "error": "bundle entry is not an object", "code": "AWR-DOC-001"}
                )
        return documents, errors

    if isinstance(value, list):
        for index, item in enumerate(value):
            locator = "%s[%d]" % (path, index)
            if isinstance(item, dict):
                documents.append(LoadedDocument(path, locator, item))
            else:
                errors.append(
                    {"source": locator, "error": "array entry is not an object", "code": "AWR-DOC-001"}
                )
        return documents, errors

    if isinstance(value, dict):
        return [LoadedDocument(path, path, value, data)], errors

    return [], [{"source": path, "error": "top-level JSON is not an object or array", "code": "AWR-DOC-001"}]


def read_all(
    inputs: Sequence[str], verifier: Any
) -> Tuple[List[LoadedDocument], List[Dict[str, str]], List[str]]:
    paths, errors = discover_paths(inputs)
    documents: List[LoadedDocument] = []
    for path in paths:
        found, file_errors = read_file(path, verifier)
        documents.extend(found)
        errors.extend(file_errors)
    return documents, errors, paths


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------


def parse_rfc3339_utc(value: Any) -> Optional[_dt.datetime]:
    """Parse an RFC 3339 UTC timestamp. Returns ``None`` for anything else."""
    if not isinstance(value, str) or not value:
        return None
    text = value.strip()
    if text.endswith("Z") or text.endswith("z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = _dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(_dt.timezone.utc)


def issuer_id_of(document: Any) -> Optional[str]:
    """``issuer.id``, or ``None``.

    A bare-string ``issuer`` is deliberately not resolved. AWR/2 rejects it (§3.1), and
    in an AWR/1 document ``issuer.id`` was a truncated base64 label that names no key at
    all (Appendix D) -- treating it as an identity would attribute adoption to a string.
    """
    if not isinstance(document, dict):
        return None
    issuer = document.get("issuer")
    if isinstance(issuer, dict):
        candidate = issuer.get("id")
        return candidate if isinstance(candidate, str) and candidate else None
    return None


def document_id_of(document: Any) -> Optional[str]:
    if not isinstance(document, dict):
        return None
    candidate = document.get("id")
    return candidate if isinstance(candidate, str) and candidate else None


def error_codes(result: Dict[str, Any]) -> List[str]:
    return [
        entry.get("code")
        for entry in result.get("reasons", ())
        if isinstance(entry, dict) and entry.get("severity", "error") == "error"
    ]


def _bump(table: Dict[str, int], key: str) -> None:
    table[key] = table.get(key, 0) + 1


# ---------------------------------------------------------------------------
# the counter
# ---------------------------------------------------------------------------


def compute_report(
    loaded: Sequence[LoadedDocument],
    read_errors: Sequence[Dict[str, Any]],
    own_keys: Set[str],
    verifier: Any,
    *,
    own_keys_info: Optional[Dict[str, Any]] = None,
    inputs: Optional[Sequence[str]] = None,
    files_scanned: int = 0,
    now: Optional[str] = None,
    include_legacy: bool = False,
    generated_at: Optional[str] = None,
) -> Dict[str, Any]:
    """Count adoption. Pure with respect to the filesystem: it only reads *loaded*."""
    supporting = verifier.prepare([item.document for item in loaded if item.document])

    seen_ids: Dict[str, Dict[str, Any]] = {}
    id_collisions: List[Dict[str, Any]] = []
    duplicate_ids = 0

    valid_documents = 0
    invalid_documents = 0
    legacy_valid = 0
    unattributed_valid = 0

    foreign: Dict[str, Dict[str, Any]] = {}
    own: Dict[str, Dict[str, Any]] = {}
    all_issuers: Set[str] = set()

    by_type_all: Dict[str, int] = {}
    by_type_foreign: Dict[str, int] = {}
    by_profile_all: Dict[str, int] = {}
    by_profile_foreign: Dict[str, int] = {}
    by_version_all: Dict[str, int] = {}

    invalid_records: List[Dict[str, Any]] = []
    invalid_by_code: Dict[str, int] = {}
    invalid_by_class: Dict[str, int] = {"own": 0, "foreign": 0, "unattributable": 0}

    for item in loaded:
        result = verifier.verify(item.payload, supporting, now)
        issuer = issuer_id_of(item.document)
        doc_id = document_id_of(item.document)
        digest = verifier.digest(item.document) if item.document else None
        is_legacy = bool(result.get("legacy"))
        version = result.get("awrVersion")
        doc_type = result.get("documentType") or "unknown"
        profile = result.get("profile") or "none"

        # A document id is a signed, binding statement by the issuer (§3.1), so it is
        # the dedup key. The same id seen twice counts once.
        if doc_id is not None:
            previous = seen_ids.get(doc_id)
            if previous is not None:
                duplicate_ids += 1
                if digest is not None and previous["digest"] is not None and digest != previous["digest"]:
                    id_collisions.append(
                        {
                            "id": doc_id,
                            "first": {
                                "locator": previous["locator"],
                                "issuer": previous["issuer"],
                                "digestSRI": previous["digest"],
                            },
                            "second": {
                                "locator": item.locator,
                                "issuer": issuer,
                                "digestSRI": digest,
                            },
                            "note": (
                                "same id, different bytes: counted once, attributed to "
                                "the first occurrence"
                            ),
                        }
                    )
                continue
            seen_ids[doc_id] = {
                "locator": item.locator,
                "issuer": issuer,
                "digest": digest,
            }

        if not result.get("valid"):
            invalid_documents += 1
            codes = error_codes(result)
            # One increment per document per code: "AWR-PROOF-006=1" reads as "one
            # document failed on this code", not "one error was emitted".
            for code in sorted({c for c in codes if isinstance(c, str)}):
                _bump(invalid_by_code, code)
            if issuer is None:
                invalid_by_class["unattributable"] += 1
            elif issuer in own_keys:
                invalid_by_class["own"] += 1
            else:
                invalid_by_class["foreign"] += 1
            invalid_records.append(
                {
                    "locator": item.locator,
                    "id": doc_id,
                    "issuer": issuer,
                    "documentType": result.get("documentType"),
                    "awrVersion": version,
                    "errorCodes": sorted({c for c in codes if isinstance(c, str)}),
                    "details": [
                        entry.get("detail")
                        for entry in result.get("reasons", ())
                        if isinstance(entry, dict)
                    ],
                }
            )
            continue

        # Valid from here down.
        if is_legacy and not include_legacy:
            legacy_valid += 1
            invalid_records.append(
                {
                    "locator": item.locator,
                    "id": doc_id,
                    "issuer": issuer,
                    "documentType": result.get("documentType"),
                    "awrVersion": version,
                    "errorCodes": ["AWR-ADOPTION-LEGACY"],
                    "details": [
                        "a valid AWR/1 document; not counted as AWR/2 adoption "
                        "(pass --include-legacy to count it)"
                    ],
                }
            )
            _bump(invalid_by_code, "AWR-ADOPTION-LEGACY")
            if issuer is None:
                invalid_by_class["unattributable"] += 1
            elif issuer in own_keys:
                invalid_by_class["own"] += 1
            else:
                invalid_by_class["foreign"] += 1
            continue

        valid_documents += 1
        _bump(by_type_all, doc_type)
        _bump(by_profile_all, profile)
        _bump(by_version_all, version if isinstance(version, str) else "unknown")
        if issuer is not None:
            all_issuers.add(issuer)

        timestamp = item.document.get(TIMESTAMP_FIELD) if item.document else None
        moment = parse_rfc3339_utc(timestamp)

        if issuer is None:
            # A valid document always carries issuer.id (§3.1, AWR-DOC-010), so this is
            # unreachable with the reference implementation. It exists so that a
            # degraded or future verifier cannot let an unattributable document land in
            # the foreign bucket, which is the one direction that would inflate.
            unattributed_valid += 1
            continue
        bucket = own if issuer in own_keys else foreign
        entry = bucket.setdefault(
            issuer,
            {
                "did": issuer,
                "documents": 0,
                "firstSeen": None,
                "lastSeen": None,
                "byDocumentType": {},
                "byProfile": {},
                "sources": [],
                "names": [],
            },
        )
        entry["documents"] += 1
        _bump(entry["byDocumentType"], doc_type)
        _bump(entry["byProfile"], profile)
        if moment is not None:
            iso = moment.strftime("%Y-%m-%dT%H:%M:%SZ")
            if entry["firstSeen"] is None or iso < entry["firstSeen"]:
                entry["firstSeen"] = iso
            if entry["lastSeen"] is None or iso > entry["lastSeen"]:
                entry["lastSeen"] = iso
        elif timestamp is not None:
            entry.setdefault("unparseableTimestamps", 0)
            entry["unparseableTimestamps"] += 1
        if item.source not in entry["sources"]:
            entry["sources"].append(item.source)
        issuer_object = item.document.get("issuer") if item.document else None
        name = issuer_object.get("name") if isinstance(issuer_object, dict) else None
        if isinstance(name, str) and name and name not in entry["names"]:
            # §3.1: issuer.name carries no trust weight. Reported to help a human
            # recognise an adopter, never used for classification.
            entry["names"].append(name)

        if bucket is foreign:
            _bump(by_type_foreign, doc_type)
            _bump(by_profile_foreign, profile)

    for entry in list(foreign.values()) + list(own.values()):
        if len(entry["sources"]) > 20:
            entry["sourcesTruncated"] = len(entry["sources"])
            entry["sources"] = sorted(entry["sources"])[:20]
        else:
            entry["sources"] = sorted(entry["sources"])

    foreign_list = sorted(
        foreign.values(), key=lambda e: (-e["documents"], e["did"])
    )
    own_list = sorted(own.values(), key=lambda e: (-e["documents"], e["did"]))

    warnings: List[str] = []
    if own_keys_info:
        warnings.extend(own_keys_info.get("warnings", ()))
        for problem in own_keys_info.get("problems", ()):
            warnings.append("own-keys file: %s" % (problem,))
    if not verifier.checks_signatures:
        warnings.append(
            "NO SIGNATURES WERE VERIFIED: this run used the structural fallback (%s). "
            "The headline number is an UPPER BOUND, not the metric. Do not quote it."
            % (
                "requested with --no-verify-signatures"
                if getattr(verifier, "forced", False)
                else "the AWR reference implementation could not be imported"
            )
        )
    if id_collisions:
        warnings.append(
            "%d document id(s) appeared with differing bytes; each was counted once and "
            "attributed to its first occurrence" % (len(id_collisions),)
        )
    if unattributed_valid:  # pragma: no cover - unreachable with the reference impl
        warnings.append(
            "%d document(s) passed verification with no issuer.id and were attributed to "
            "no issuer at all" % (unattributed_valid,)
        )

    report: Dict[str, Any] = {
        "report": REPORT_SCHEMA,
        "generatedAt": generated_at
        or _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "headline": {
            "metric": METRIC_ID,
            "value": len(foreign_list),
            "unit": "distinct foreign issuer DIDs",
            "definition": METRIC_DEFINITION,
            "definitionDigestSHA256": METRIC_DEFINITION_DIGEST,
            "signaturesVerified": bool(verifier.checks_signatures),
        },
        "instrument": {
            "verifier": verifier.name,
            "verifierSource": getattr(verifier, "source", None),
            "timestampField": TIMESTAMP_FIELD,
            "network": "none: no request is made by this tool or by verification (§13.5)",
            "legacyAwr1Counted": bool(include_legacy),
        },
        "ownKeys": own_keys_info
        or {"source": None, "count": len(own_keys), "dids": sorted(own_keys)},
        "corpus": {
            "inputs": list(inputs or ()),
            "filesScanned": files_scanned,
            "documentsRead": len(loaded),
            "duplicateIdsCollapsed": duplicate_ids,
            "readErrors": list(read_errors),
            "readErrorCount": len(read_errors),
        },
        "issuers": {
            "distinct": len(all_issuers),
            "distinctOwn": len(own_list),
            "distinctForeign": len(foreign_list),
            "unattributableValidDocuments": unattributed_valid,
        },
        "foreignIssuers": foreign_list,
        "ownIssuers": own_list,
        "context": {
            "note": (
                "NOT THE METRIC. Document counts are volume, not adoption: one "
                "enthusiastic adopter emitting a million receipts is one adopter."
            ),
            "validDocuments": valid_documents,
            "foreignDocuments": sum(e["documents"] for e in foreign_list),
            "ownDocuments": sum(e["documents"] for e in own_list),
            "byDocumentType": {"foreign": by_type_foreign, "all": by_type_all},
            "byProfile": {"foreign": by_profile_foreign, "all": by_profile_all},
            "byAwrVersion": by_version_all,
        },
        "invalid": {
            "note": "excluded from the metric, never dropped",
            "count": invalid_documents + (0 if include_legacy else legacy_valid),
            "failedVerification": invalid_documents,
            "validAwr1NotCountedAsAwr2": 0 if include_legacy else legacy_valid,
            "byIssuerClass": invalid_by_class,
            "byReasonCode": invalid_by_code,
            "documents": invalid_records,
        },
        "idCollisions": id_collisions,
        "warnings": warnings,
    }
    return report


# ---------------------------------------------------------------------------
# rendering
# ---------------------------------------------------------------------------


def _table(rows: Sequence[Tuple[str, Any]], indent: str = "  ") -> str:
    if not rows:
        return ""
    width = max(len(str(label)) for label, _ in rows)
    return "\n".join("%s%-*s  %s" % (indent, width, label, value) for label, value in rows)


def _counts(table: Dict[str, int]) -> str:
    if not table:
        return "-"
    return " ".join(
        "%s=%d" % (key, table[key]) for key in sorted(table, key=lambda k: (-table[k], k))
    )


def render_human(report: Dict[str, Any]) -> str:
    head = report["headline"]
    lines: List[str] = []
    title = "AWR adoption metric — %s" % (head["metric"],)
    lines.append(title)
    lines.append("=" * len(title))
    lines.append("")
    lines.append("THE NUMBER: %d %s" % (head["value"], head["unit"]))
    lines.append("")
    lines.append("  definition: %s" % (head["definition"],))
    lines.append("")

    if not head["signaturesVerified"]:
        lines.append("!" * 72)
        lines.append("! NO SIGNATURES WERE VERIFIED — the number above is an UPPER BOUND,")
        lines.append("! not the metric. Rerun with the AWR reference implementation")
        lines.append("! importable and without --no-verify-signatures.")
        lines.append("!" * 72)
        lines.append("")

    own_keys = report["ownKeys"]
    corpus = report["corpus"]
    issuers = report["issuers"]
    context = report["context"]
    invalid = report["invalid"]

    lines.append("Instrument")
    lines.append(
        _table(
            [
                ("verifier", report["instrument"]["verifier"]),
                ("own-keys file", own_keys.get("source") or "(none found)"),
                ("own DIDs declared", own_keys.get("count", 0)),
                ("timestamp field", report["instrument"]["timestampField"]),
                ("network access", report["instrument"]["network"]),
            ]
        )
    )
    lines.append("")

    lines.append("Corpus")
    lines.append(
        _table(
            [
                ("inputs", ", ".join(corpus["inputs"]) or "-"),
                ("files scanned", corpus["filesScanned"]),
                ("documents read", corpus["documentsRead"]),
                ("duplicate ids collapsed", corpus["duplicateIdsCollapsed"]),
                ("unreadable inputs", corpus["readErrorCount"]),
            ]
        )
    )
    lines.append("")

    lines.append("Issuers")
    lines.append(
        _table(
            [
                ("distinct issuers", issuers["distinct"]),
                ("ours (excluded by DID)", issuers["distinctOwn"]),
                ("FOREIGN (the metric)", issuers["distinctForeign"]),
            ]
        )
    )
    lines.append("")

    lines.append("Foreign issuers")
    if not report["foreignIssuers"]:
        lines.append("  none: no valid AWR document in this corpus was issued by a key")
        lines.append("  outside our own-keys list. Adoption is zero, and saying so is")
        lines.append("  the point of this tool.")
    else:
        for entry in report["foreignIssuers"]:
            names = (" (%s)" % ", ".join(entry["names"])) if entry["names"] else ""
            lines.append("  %s%s" % (entry["did"], names))
            lines.append(
                _table(
                    [
                        ("documents", entry["documents"]),
                        ("first seen", entry["firstSeen"] or "-"),
                        ("last seen", entry["lastSeen"] or "-"),
                        ("by type", _counts(entry["byDocumentType"])),
                        ("by profile", _counts(entry["byProfile"])),
                        (
                            "seen in",
                            ", ".join(entry["sources"][:4])
                            + (" …" if len(entry["sources"]) > 4 else ""),
                        ),
                    ],
                    indent="      ",
                )
            )
    lines.append("")

    lines.append("Our own issuers (excluded)")
    if not report["ownIssuers"]:
        lines.append("  none of our declared DIDs issued a document in this corpus")
    else:
        for entry in report["ownIssuers"]:
            lines.append("  %s  %d documents" % (entry["did"], entry["documents"]))
    lines.append("")

    lines.append("Context — NOT THE METRIC")
    lines.append("  " + context["note"])
    lines.append(
        _table(
            [
                ("valid documents", context["validDocuments"]),
                ("foreign documents", context["foreignDocuments"]),
                ("our documents", context["ownDocuments"]),
                ("type (foreign)", _counts(context["byDocumentType"]["foreign"])),
                ("profile (foreign)", _counts(context["byProfile"]["foreign"])),
                ("type (all valid)", _counts(context["byDocumentType"]["all"])),
                ("profile (all valid)", _counts(context["byProfile"]["all"])),
                ("awrVersion (all valid)", _counts(context["byAwrVersion"])),
            ]
        )
    )
    lines.append("")

    lines.append("Excluded from adoption (%d)" % (invalid["count"],))
    lines.append(
        _table(
            [
                ("failed verification", invalid["failedVerification"]),
                ("valid AWR/1, not AWR/2", invalid["validAwr1NotCountedAsAwr2"]),
                ("by reason code", _counts(invalid["byReasonCode"])),
                ("by issuer class", _counts(invalid["byIssuerClass"])),
            ]
        )
    )
    shown = invalid["documents"][:20]
    for record in shown:
        lines.append(
            "    %s  %s  %s"
            % (
                record["locator"],
                ",".join(record["errorCodes"]) or "-",
                record["issuer"] or "(no issuer)",
            )
        )
    if len(invalid["documents"]) > len(shown):
        lines.append(
            "    … %d more; the full list is in the JSON report"
            % (len(invalid["documents"]) - len(shown),)
        )
    lines.append("")

    if corpus["readErrors"]:
        lines.append("Unreadable inputs (%d)" % (len(corpus["readErrors"]),))
        for record in corpus["readErrors"][:20]:
            lines.append("    %s  %s" % (record["source"], record["error"]))
        lines.append("")

    if report["warnings"]:
        lines.append("Warnings")
        for warning in report["warnings"]:
            lines.append("  - %s" % (warning,))
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="adoption_metric.py",
        description=(
            "Count AWR documents issued by keys this project does not control. "
            "The metric is the number of distinct foreign issuer DIDs."
        ),
        epilog="Exit codes: 0 report produced, 1 --fail-under not met, 2 usage/IO error.",
    )
    parser.add_argument(
        "paths", nargs="*", metavar="PATH", help="directories or files of AWR documents"
    )
    parser.add_argument(
        "--demo-corpus",
        metavar="DIR",
        help=(
            "write the synthetic corpus the README transcript is computed from into DIR "
            "(with its own own-keys.txt) and exit. Deterministic; contains no adoption: "
            "every key comes from a seed published in demo_corpus.py"
        ),
    )
    parser.add_argument(
        "--own-keys",
        metavar="FILE",
        help="newline-delimited list of our own did:key identifiers (default: $%s, "
        "else %s next to this script)" % (OWN_KEYS_ENV_VAR, DEFAULT_OWN_KEYS_FILENAME),
    )
    parser.add_argument(
        "--format",
        choices=("both", "human", "json"),
        default="both",
        help="both (default): human summary to stderr, JSON to stdout",
    )
    parser.add_argument("--json-out", metavar="FILE", help="also write the JSON report here")
    parser.add_argument(
        "--now",
        metavar="RFC3339",
        help="evaluate time-dependent checks at this instant (deterministic runs)",
    )
    parser.add_argument(
        "--include-legacy",
        action="store_true",
        help="count valid AWR/1 documents as adoption (default: report them separately)",
    )
    parser.add_argument(
        "--require-reference",
        action="store_true",
        help="fail instead of falling back to unverified structural counting",
    )
    parser.add_argument(
        "--no-verify-signatures",
        action="store_true",
        help=(
            "force the structural fallback even when the reference implementation is "
            "available: shows what a degraded run counts. The report marks itself "
            "unquotable (signaturesVerified=false). Never use this for a real number"
        ),
    )
    parser.add_argument(
        "--fail-under",
        type=int,
        metavar="N",
        help="exit 1 when the metric is below N",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.demo_corpus:
        if args.paths:
            parser.error("--demo-corpus writes a corpus; it does not also measure one")
        try:
            import demo_corpus  # type: ignore
        except ImportError:  # pragma: no cover - both files ship together
            sys.path.insert(0, _HERE)
            import demo_corpus  # type: ignore
        return demo_corpus.main([args.demo_corpus])

    if not args.paths:
        parser.error("give at least one PATH, or --demo-corpus DIR to mint the demo corpus")

    verifier = build_verifier(
        require_reference=args.require_reference,
        force_structural=args.no_verify_signatures,
    )
    own_keys, own_keys_info = load_own_keys(args.own_keys)
    loaded, read_errors, paths = read_all(args.paths, verifier)

    report = compute_report(
        loaded,
        read_errors,
        own_keys,
        verifier,
        own_keys_info=own_keys_info,
        inputs=args.paths,
        files_scanned=len(paths),
        now=args.now,
        include_legacy=args.include_legacy,
    )

    blob = json.dumps(report, indent=2, sort_keys=False, ensure_ascii=False)
    if args.json_out:
        try:
            with open(args.json_out, "w", encoding="utf-8") as handle:
                handle.write(blob + "\n")
        except OSError as exc:
            sys.stderr.write("cannot write %s: %s\n" % (args.json_out, exc))
            return 2

    if args.format == "human":
        sys.stdout.write(render_human(report) + "\n")
    elif args.format == "json":
        sys.stdout.write(blob + "\n")
    else:
        sys.stderr.write(render_human(report) + "\n")
        sys.stdout.write(blob + "\n")

    if args.fail_under is not None and report["headline"]["value"] < args.fail_under:
        sys.stderr.write(
            "metric %d is below --fail-under %d\n"
            % (report["headline"]["value"], args.fail_under)
        )
        return 1
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except KeyboardInterrupt:  # pragma: no cover
        sys.exit(2)
