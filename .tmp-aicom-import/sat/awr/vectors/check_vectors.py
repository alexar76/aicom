#!/usr/bin/env python3
"""Hold every AWR/2 vector to the outcome ``index.json`` claims for it.

    PYTHONPATH=awr/reference/python \
      aimarket-hub/.venv/bin/python awr/vectors/check_vectors.py

The manifest is a **contract**, not documentation: this script is what makes it one.  For
each entry it drives the section 17 CLI and asserts, exactly:

* the exit code section 17 prescribes (``0`` valid, ``1`` invalid, ``2`` usage);
* ``valid`` in the section 11.1 result equals the entry's ``expect``;
* the set of ``reasons`` codes is **exactly** ``expectedCodes`` -- a missing code is a
  failure, and so is an extra one unless the entry lists it in ``allowedExtraCodes``
  because the specification does not settle the question (see ``specFindings``);
* the set of ``warnings`` codes is exactly ``expectedWarnings`` under the same rule;
* the severity of every reported code matches SPEC.md section 11.2;
* for canonicalization vectors, the canonical bytes are byte-identical to the recorded
  ``.canonical`` file *and* to ``canonicalHex``, and ``digest`` prints ``digestSRI``;
* for the proof vector, ``hashdata`` prints the three recorded hex values in the section
  6.2 order, and the recorded signature verifies under the key the ``did:key`` names.

It also checks the properties a per-vector run cannot:

* **coverage** -- every reason code in SPEC.md section 11.2 is either exercised by a
  vector or declared in ``unreachableCodes``/``partiallyCoveredCodes`` with a reason;
* **spec vs reference** -- the section 11.2 table and the reference implementation's
  registry agree on the code set and on every severity;
* **AWR-CANON-006** -- unreachable from any input, so it is proved to fire by pointing the
  reference self-check at a deliberately NFC-applying canonicalizer;
* **test keys** -- every signing seed in the manifest is a published RFC 8032 section 7.1
  test vector, so no secret was created to write a vector;
* **determinism** -- ``generate.py`` is re-run into a temporary tree and diffed against the
  committed one, which fails both on a non-deterministic generator and on a hand-edited
  vector (``--skip-regenerate`` to skip);
* **no orphans** -- every file under ``valid/``, ``invalid/``, ``canonicalization/`` and
  ``proof/`` is referenced by the manifest.  An unreferenced vector has no expected
  outcome and therefore is not part of the contract.

``--impl`` points the CLI phases at another conformant implementation, e.g.
``--impl 'awr/rust/target/release/awr'``.  The phases that use the reference library
directly (AWR-CANON-006, the signature cross-check) are then skipped and said to be.
"""

from __future__ import annotations

import argparse
import base64
import filecmp
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import unicodedata
from typing import Any, Dict, List, Optional, Sequence, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
AWR_ROOT = os.path.abspath(os.path.join(HERE, ".."))
REFERENCE = os.path.join(AWR_ROOT, "reference", "python")
SPEC = os.path.join(AWR_ROOT, "SPEC.md")
INDEX = os.path.join(HERE, "index.json")
VECTOR_DIRS = ("valid", "invalid", "canonicalization", "proof")

#: The Ed25519 test seeds of RFC 8032 section 7.1.  A vector's signing key MUST be one of
#: these: they are published in an IETF standard, so writing the vector set created no
#: secret and leaked none.  A seed outside this set is a failure, not a style question.
RFC8032_SEEDS = {
    "9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60": "TEST 1",
    "4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb": "TEST 2",
    "c5aa8df43f9f837bedb7442f31dcb7b166d38535076f094b85ce3a2e0b4458f7": "TEST 3",
    "f5e5767cf153319517630f226876b86c8160cc583bc013744c6bf255f5cc0ee5": "TEST 1024",
    "833fe62409237b9d62ec77587520911e9a759cec1d19755b7da901b96dca3d42": "TEST SHA(abc)",
}

EXIT_OK = 0
EXIT_INVALID = 1

REQUIRED_ENTRY_FIELDS = (
    "id",
    "file",
    "kind",
    "expect",
    "expectedCodes",
    "expectedWarnings",
    "profile",
    "tags",
    "why",
)


# ---------------------------------------------------------------------------
# reporting
# ---------------------------------------------------------------------------


class Report(object):
    """Failures are collected, never raised: one run must diagnose the whole set."""

    def __init__(self, verbose: bool = False) -> None:
        self.failures: List[str] = []
        self.checks = 0
        self.skipped: List[str] = []
        self.verbose = verbose

    def check(self, condition: bool, where: str, message: str) -> bool:
        self.checks += 1
        if not condition:
            self.failures.append("%s: %s" % (where, message))
        return bool(condition)

    def equal(self, got: Any, want: Any, where: str, what: str) -> bool:
        return self.check(
            got == want, where, "%s\n    expected: %r\n    actual:   %r" % (what, want, got)
        )

    def skip(self, what: str) -> None:
        self.skipped.append(what)

    def note(self, text: str) -> None:
        if self.verbose:
            sys.stderr.write("  %s\n" % (text,))


# ---------------------------------------------------------------------------
# the implementation under test
# ---------------------------------------------------------------------------


class Impl(object):
    def __init__(self, command: Sequence[str], is_reference: bool) -> None:
        self.command = list(command)
        self.is_reference = is_reference
        self.env = dict(os.environ)
        existing = self.env.get("PYTHONPATH")
        self.env["PYTHONPATH"] = (
            REFERENCE if not existing else REFERENCE + os.pathsep + existing
        )

    def run(self, args: Sequence[str]) -> Tuple[int, bytes, str]:
        process = subprocess.Popen(
            self.command + list(args),
            cwd=HERE,
            env=self.env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        out, err = process.communicate()
        return process.returncode, out, err.decode("utf-8", "replace")


def default_impl() -> Impl:
    return Impl([sys.executable, "-m", "awr"], True)


# ---------------------------------------------------------------------------
# SPEC.md section 11.2
# ---------------------------------------------------------------------------

_CODE_ROW = re.compile(r"^\|\s*`(AWR-[A-Z0-9]+-\d+)`\s*\|\s*(.+?)\s*\|\s*$")


def parse_spec_registry(path: str) -> Dict[str, str]:
    """``{code: severity}`` from the section 11.2 tables of SPEC.md.

    Coverage is measured against the *specification*, not against the reference's
    transcription of it: a code the reference forgot would otherwise never be missed.
    """
    registry: Dict[str, str] = {}
    inside = False
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.rstrip("\n")
            if stripped.startswith("### 11.2"):
                inside = True
                continue
            if inside and stripped.startswith("### "):
                break
            if not inside:
                continue
            match = _CODE_ROW.match(stripped)
            if match is None:
                continue
            code, meaning = match.group(1), match.group(2)
            registry[code] = "warning" if "*(warning)*" in meaning else "error"
    return registry


# ---------------------------------------------------------------------------
# phase 1: manifest shape
# ---------------------------------------------------------------------------


def phase_manifest(manifest: Dict[str, Any], report: Report) -> None:
    where = "index.json"
    vectors = manifest.get("vectors")
    if not report.check(isinstance(vectors, list) and bool(vectors), where, "vectors must be a non-empty array"):
        return
    report.equal(manifest.get("vectorCount"), len(vectors), where, "vectorCount")
    report.equal(manifest.get("awrVersion"), "2.0.0", where, "awrVersion")

    seen_ids = set()
    for entry in vectors:
        vid = entry.get("id", "<no id>")
        place = "%s[%s]" % (where, vid)
        for field in REQUIRED_ENTRY_FIELDS:
            report.check(field in entry, place, "missing required manifest field %r" % (field,))
        report.check(vid not in seen_ids, place, "duplicate vector id")
        seen_ids.add(vid)
        report.check(
            isinstance(entry.get("why"), str) and bool(entry.get("why", "").strip()),
            place,
            "a vector with no 'why' does not belong in the set",
        )
        report.check(
            entry.get("kind") in ("document", "bundle", "canonicalization", "proof"),
            place,
            "kind must be document | bundle | canonicalization | proof, got %r" % (entry.get("kind"),),
        )
        report.check(
            entry.get("expect") in ("valid", "invalid"),
            place,
            "expect must be valid | invalid, got %r" % (entry.get("expect"),),
        )
        if entry.get("expect") == "invalid":
            report.check(
                bool(entry.get("expectedCodes")),
                place,
                "an invalid vector must name at least one expected reason code",
            )
        else:
            report.equal(entry.get("expectedCodes"), [], place, "a valid vector must name no error codes")
        report.check(
            entry.get("profile") in (None, "L0", "L1", "L2"),
            place,
            "profile must be null | L0 | L1 | L2, got %r" % (entry.get("profile"),),
        )
        for field in ("file", "canonicalFile", "securedFile", "unsecuredFile", "proofConfigFile"):
            target = entry.get(field)
            if isinstance(target, str):
                report.check(
                    os.path.exists(os.path.join(HERE, target)),
                    place,
                    "%s names a file that does not exist: %s" % (field, target),
                )
        for target in entry.get("supporting") or ():
            report.check(
                os.path.exists(os.path.join(HERE, target)),
                place,
                "supporting names a file that does not exist: %s" % (target,),
            )


def phase_orphans(manifest: Dict[str, Any], report: Report) -> None:
    """Every file in the tree must be referenced: an unreferenced vector has no contract."""
    referenced = set()
    for entry in manifest["vectors"]:
        for field in ("file", "canonicalFile", "securedFile", "unsecuredFile", "proofConfigFile"):
            value = entry.get(field)
            if isinstance(value, str):
                referenced.add(value)
        for value in entry.get("supporting") or ():
            referenced.add(value)
        if entry.get("kind") == "proof":
            # The proof vector's own payload names the intermediate byte files that
            # section 6.2 requires to be recorded separately.
            with open(os.path.join(HERE, entry["file"]), "r", encoding="utf-8") as handle:
                payload = json.load(handle)
            for value in (payload.get("files") or {}).values():
                if isinstance(value, str):
                    referenced.add(value)

    on_disk = set()
    for directory in VECTOR_DIRS:
        root = os.path.join(HERE, directory)
        if not os.path.isdir(root):
            continue
        for name in sorted(os.listdir(root)):
            if not os.path.isfile(os.path.join(root, name)):
                continue
            on_disk.add("%s/%s" % (directory, name))

    for orphan in sorted(on_disk - referenced):
        report.check(False, "index.json", "vector file %s is not referenced by the manifest" % (orphan,))
    for missing in sorted(referenced - on_disk):
        report.check(False, "index.json", "manifest references a file not on disk: %s" % (missing,))


# ---------------------------------------------------------------------------
# phase 2: coverage of section 11.2
# ---------------------------------------------------------------------------


def phase_coverage(manifest: Dict[str, Any], spec_registry: Dict[str, str], report: Report) -> None:
    where = "SPEC.md 11.2 coverage"
    report.check(bool(spec_registry), where, "no reason codes parsed out of SPEC.md section 11.2")

    exercised: Dict[str, List[str]] = {}
    for entry in manifest["vectors"]:
        for code in list(entry["expectedCodes"]) + list(entry["expectedWarnings"]):
            exercised.setdefault(code, []).append(entry["id"])

    declared = dict(manifest.get("unreachableCodes") or {})
    partial = dict(manifest.get("partiallyCoveredCodes") or {})

    for code, severity in sorted(spec_registry.items()):
        if code in exercised:
            continue
        if code in declared:
            report.check(
                bool(str(declared[code]).strip()),
                where,
                "%s is declared unreachable with no reason" % (code,),
            )
            report.note("%s: no vector, declared unreachable" % (code,))
            continue
        report.check(
            False,
            where,
            "%s (%s) is in the registry, is not exercised by any vector, and is not "
            "declared in unreachableCodes" % (code, severity),
        )

    for code in sorted(set(exercised) - set(spec_registry)):
        report.check(
            False,
            where,
            "vectors expect %s, which is not in the SPEC.md section 11.2 registry (%s)"
            % (code, ", ".join(exercised[code])),
        )
    for code in sorted(set(declared) | set(partial)):
        report.check(
            code in spec_registry,
            where,
            "%s is declared unreachable/partial but is not a registry code" % (code,),
        )

    # The manifest's own codeIndex must agree with the vectors it indexes.
    index_map = manifest.get("codeIndex") or {}
    report.equal(
        {code: sorted(ids) for code, ids in sorted(exercised.items())},
        {code: sorted(ids) for code, ids in sorted(index_map.items())},
        where,
        "codeIndex does not match the vectors",
    )


def phase_spec_vs_reference(spec_registry: Dict[str, str], report: Report) -> None:
    """A divergence between SPEC.md 11.2 and the reference registry is a finding."""
    where = "SPEC.md 11.2 vs awr.errors.REGISTRY"
    try:
        from awr.errors import REGISTRY  # noqa: WPS433 -- optional, reference only
    except ImportError:
        report.skip("spec-vs-reference registry comparison (awr not importable)")
        return
    reference = {code: spec.severity for code, spec in REGISTRY.items()}
    for code in sorted(set(spec_registry) - set(reference)):
        report.check(False, where, "%s is in SPEC.md but not in the reference registry" % (code,))
    for code in sorted(set(reference) - set(spec_registry)):
        report.check(False, where, "%s is in the reference registry but not in SPEC.md" % (code,))
    for code in sorted(set(spec_registry) & set(reference)):
        report.equal(reference[code], spec_registry[code], where, "severity of %s" % (code,))


def phase_keys(manifest: Dict[str, Any], report: Report) -> None:
    where = "index.json keys"
    keys = manifest.get("keys") or []
    report.check(bool(keys), where, "the manifest records no signing keys")
    report.check(
        "TEST KEYS" in (manifest.get("keyWarning") or ""),
        where,
        "keyWarning must mark the seeds as test keys without authority",
    )
    for entry in keys:
        seed = entry.get("privateKeySeedHex")
        report.check(
            seed in RFC8032_SEEDS,
            where,
            "key %r uses seed %s, which is not a published RFC 8032 section 7.1 test "
            "vector; a vector set must never carry a freshly created secret"
            % (entry.get("name"), seed),
        )
        if seed in RFC8032_SEEDS:
            report.check(
                RFC8032_SEEDS[seed] in (entry.get("source") or ""),
                where,
                "key %r cites source %r, which does not name RFC 8032 %s"
                % (entry.get("name"), entry.get("source"), RFC8032_SEEDS[seed]),
            )


# ---------------------------------------------------------------------------
# phase 3: per-vector CLI runs
# ---------------------------------------------------------------------------


def _codes(entries: Sequence[Any]) -> List[str]:
    return [e.get("code") for e in entries if isinstance(e, dict)]


#: SPEC.md 11.1: the codes that mean section 6.3 step 6 was not performed, so
#: ``verifiedProof`` MUST be null.  The three families are section 6.3's steps 1-5 plus
#: step 6's own failure; ``AWR-DOC-001``/``AWR-DOC-010`` are the two section 6.3 names
#: alongside them for "no public key can be derived"; ``AWR-BUNDLE-003`` means no subject
#: document was selected, so nothing was checked at all.
_NO_SIGNATURE_CHECK_PREFIXES = ("AWR-CANON-", "AWR-KEY-", "AWR-PROOF-")
#: ``AWR-BUNDLE-001``/``003`` mean no subject document was identified, so nothing was
#: checked.  ``AWR-BUNDLE-001`` has a second cause -- an entry of ``documents`` that is not
#: an object, inside an otherwise supported bundle -- for which a proof *is* checked; no
#: vector exercises that, and a vector that does must split this assertion rather than
#: relax it.
_NO_SIGNATURE_CHECK_CODES = (
    "AWR-DOC-001",
    "AWR-DOC-010",
    "AWR-BUNDLE-001",
    "AWR-BUNDLE-003",
    # Section 12.3: the version gate rejected the document, or the caller declined the
    # AWR/1 rules.  Either way it was verified under no rule set at all, so no section 6.1
    # proof was checked -- even though a signature over the section 12.1 rendering may well
    # be present and correct.
    "AWR-LEGACY-003",
    "AWR-LEGACY-005",
)
#: An AWR/1 document's signature is not a section 6.1 proof (section 12), so no index
#: exists to report.  It arrives as a *warning*, not an error.
_LEGACY_WARNING = "AWR-LEGACY-001"

AWR_TYPES = ("WorkReceipt", "VerificationVerdict", "BlameAttestation")


def _lenient_document(path: str) -> Optional[Dict[str, Any]]:
    """The vector as ``json`` sees it, or ``None``.

    Deliberately permissive: this is not a conformant parse and is used only to read back
    what the *document* says its ``awrVersion`` and ``type`` are, so that the result can be
    held to reporting the document's own values rather than invented ones.
    """
    try:
        with open(path, "rb") as fh:
            value = json.loads(fh.read().decode("utf-8"))
    except Exception:
        return None
    if not isinstance(value, dict):
        return None
    if isinstance(value.get("documents"), list):        # a bundle (section 9)
        return None
    return value


def check_result_invariants(
    entry: Dict[str, Any], result: Dict[str, Any], report: Report
) -> None:
    """The SPEC.md 11.1 rules that hold for *every* result, whatever the vector.

    These are asserted as invariants rather than recorded per vector because 11.1 states
    them as rules about the result, not as facts about a document -- so a vector added
    later is held to them for free.  Every one of them was a live three-way divergence
    that ``index.json`` could not see, because a manifest that pins only ``expectedCodes``
    and ``expectedWarnings`` never looks at the rest of the result:

    * ``verifiedProof`` -- the reference reported ``null`` where the Rust and browser
      builds reported ``0``, for 47 of the 106 vectors; then the reference reported ``0``
      beside ``AWR-PROOF-002`` while the other two reported ``0`` beside ``AWR-KEY-003``.
    * ``awrVersion`` -- the reference reported the document's value, the Rust build its
      own implemented version, and the browser build the invented string ``"1"``.
    * ``documentType`` -- the browser build reported ``"AIProvenanceReceipt"``, a name
      that appears in no document.
    * ``chain`` -- the browser build counted a verdict's ``verifiedWork`` and a blame's
      reachability walk as chain edges, so a standalone verdict claimed one unresolved hop.
    """
    place = entry["id"]
    codes = [c for c in _codes(result.get("reasons") or ()) if isinstance(c, str)]
    warned = [c for c in _codes(result.get("warnings") or ()) if isinstance(c, str)]
    blocked = (
        any(c.startswith(_NO_SIGNATURE_CHECK_PREFIXES) for c in codes)
        or any(c in _NO_SIGNATURE_CHECK_CODES for c in codes)
        or _LEGACY_WARNING in warned
    )
    no_canonical_form = any(c.startswith("AWR-CANON-") for c in codes)

    # ---- verifiedProof is a function of the codes reported (11.1) ----------------
    verified_proof = result.get("verifiedProof")
    if blocked:
        report.equal(
            verified_proof,
            None,
            place,
            "section 11.1: verifiedProof MUST be null when the result carries a code "
            "section 6.3 names as preventing step 6, or when no section 6.1 proof was "
            "checked at all (reported: %s)"
            % (", ".join(sorted(codes) + sorted(warned)) or "nothing",),
        )
    else:
        report.check(
            isinstance(verified_proof, int) and not isinstance(verified_proof, bool)
            and verified_proof >= 0,
            place,
            "section 11.1: a section 6.1 proof was checked and verified, so verifiedProof "
            "MUST hold its zero-based index and MUST NOT be null; got %r" % (verified_proof,),
        )

    # ---- awrVersion and documentType report the DOCUMENT (11.1) -----------------
    if no_canonical_form:
        report.equal(
            (result.get("awrVersion"), result.get("documentType")),
            (None, None),
            place,
            "section 11.1: awrVersion and documentType MUST both be null when the document "
            "has no canonical form (%s)" % (", ".join(sorted(codes)),),
        )
    else:
        document = _lenient_document(os.path.join(HERE, entry["file"]))
        if document is not None:
            own_version = document.get("awrVersion")
            report.equal(
                result.get("awrVersion"),
                own_version if isinstance(own_version, str) else None,
                place,
                "section 11.1: awrVersion reports the DOCUMENT's awrVersion, never the "
                "version the verifier implements and never an invented value",
            )
            types = document.get("type")
            named = (
                [c for c in AWR_TYPES if c in types] if isinstance(types, list) else []
            )
            # Section 11.1: null when `type` names more than one AWR type
            # (``AWR-DOC-005``) -- no single type is the document's, and picking the
            # first would make the answer depend on member order.
            own_type = named[0] if len(named) == 1 else None
            report.equal(
                result.get("documentType"),
                own_type,
                place,
                "section 11.1: documentType reports the AWR type the DOCUMENT's `type` "
                "array carries, never a name the document does not contain, and null when "
                "`type` names more than one",
            )

    # ---- chain counts section 8.1 `parents` edges and nothing else (11.1) -------
    chain = result.get("chain")
    if isinstance(chain, dict):
        for member in ("resolved", "unresolved"):
            report.check(
                isinstance(chain.get(member), int) and not isinstance(chain.get(member), bool),
                place,
                "section 11.1: chain.%s MUST be an integer, got %r" % (member, chain.get(member)),
            )
        if result.get("documentType") in ("VerificationVerdict", "BlameAttestation"):
            report.equal(
                (chain.get("resolved"), chain.get("unresolved")),
                (0, 0),
                place,
                "section 11.1: chain counts section 8.1 `parents` edges only. A verdict's "
                "verifiedWork and a blame's chain/blamedWork are digest references, not "
                "chain edges, and MUST NOT be counted -- their outcome is AWR-VDCT-005 "
                "and AWR-BLAME-001",
            )
        document = _lenient_document(os.path.join(HERE, entry["file"]))
        # Only when nothing was supplied: with ``--parents`` the resolution walks the whole
        # DAG and the counts cover every edge it observed (section 8.2), not just the
        # subject's own.
        if document is not None and not entry.get("supporting") \
                and result.get("documentType") == "WorkReceipt":
            subject = document.get("credentialSubject")
            parents = subject.get("parents") if isinstance(subject, dict) else None
            well_formed = 0
            if isinstance(parents, list):
                for ref in parents:
                    if isinstance(ref, dict) and isinstance(ref.get("digestSRI"), str) \
                            and ref["digestSRI"].startswith("sha256-"):
                        well_formed += 1
            report.equal(
                (chain.get("resolved") or 0) + (chain.get("unresolved") or 0),
                well_formed,
                place,
                "section 11.1: every well-formed `parents` entry is counted exactly once, "
                "as resolved or unresolved, and an entry that is not a well-formed digest "
                "reference (AWR-CHAIN-001/002) is counted in neither",
            )


def _compare_code_sets(
    report: Report,
    place: str,
    label: str,
    reported: Sequence[str],
    required: Sequence[str],
    allowed_extra: Sequence[str],
) -> None:
    reported_set = set(reported)
    required_set = set(required)
    allowed = required_set | set(allowed_extra)
    missing = sorted(required_set - reported_set)
    unexpected = sorted(reported_set - allowed)
    report.check(
        not missing,
        place,
        "%s the manifest requires were NOT reported: %s (reported: %s)"
        % (label, ", ".join(missing), ", ".join(sorted(reported_set)) or "none"),
    )
    report.check(
        not unexpected,
        place,
        "%s reported that the manifest does not allow: %s (required: %s)"
        % (label, ", ".join(unexpected), ", ".join(sorted(required_set)) or "none"),
    )


def check_document_vector(
    entry: Dict[str, Any], impl: Impl, spec_registry: Dict[str, str], report: Report
) -> None:
    place = entry["id"]
    args = ["verify", entry["file"]]
    if entry.get("profile"):
        args += ["--profile", entry["profile"]]
    if entry.get("now"):
        args += ["--now", entry["now"]]
    if entry.get("subjectId"):
        args += ["--subject", entry["subjectId"]]
    if entry.get("maxDepth") is not None:
        args += ["--max-depth", str(entry["maxDepth"])]
    if entry.get("maxNodes") is not None:
        args += ["--max-nodes", str(entry["maxNodes"])]
    if entry.get("supporting"):
        args += ["--parents"] + list(entry["supporting"])

    code, out, err = impl.run(args)
    expect_valid = entry["expect"] == "valid"
    report.equal(
        code,
        EXIT_OK if expect_valid else EXIT_INVALID,
        place,
        "section 17 exit code for `%s`\n    stderr: %s" % (" ".join(args), err.strip()[:400]),
    )
    try:
        result = json.loads(out.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        report.check(False, place, "stdout is not the section 11.1 result JSON: %s" % (exc,))
        return

    for field in (
        "valid",
        "awrVersion",
        "documentType",
        "profile",
        "reasons",
        "warnings",
        "chain",
        "verifiedProof",
    ):
        report.check(field in result, place, "section 11.1 result is missing %r" % (field,))

    report.equal(result.get("valid"), expect_valid, place, "result.valid")
    errors = _codes(result.get("reasons") or ())
    warnings = _codes(result.get("warnings") or ())
    report.equal(
        result.get("valid"),
        not errors,
        place,
        "section 11.1: valid MUST be true iff reasons carries no error entry",
    )
    _compare_code_sets(
        report, place, "error codes", errors, entry["expectedCodes"], entry.get("allowedExtraCodes") or ()
    )
    _compare_code_sets(
        report,
        place,
        "warning codes",
        warnings,
        entry["expectedWarnings"],
        entry.get("allowedExtraWarnings") or (),
    )
    check_result_invariants(entry, result, report)
    for reason in result.get("reasons") or ():
        report.equal(reason.get("severity"), "error", place, "severity of reported %s" % (reason.get("code"),))
        report.equal(
            spec_registry.get(reason.get("code")),
            "error",
            place,
            "%s is reported in reasons; SPEC.md 11.2 severity" % (reason.get("code"),),
        )
    for warning in result.get("warnings") or ():
        report.equal(warning.get("severity"), "warning", place, "severity of reported %s" % (warning.get("code"),))
        report.equal(
            spec_registry.get(warning.get("code")),
            "warning",
            place,
            "%s is reported in warnings; SPEC.md 11.2 severity" % (warning.get("code"),),
        )

    if expect_valid and entry.get("profile"):
        report.equal(
            result.get("profile"),
            entry["profile"],
            place,
            "section 10.4: the highest profile satisfied",
        )
    if not expect_valid:
        # Section 10.4: every profile is defined over a *valid* document, so an invalid one
        # satisfies none -- including when the signature verified and the errors are
        # semantic or chain-level.
        report.equal(result.get("profile"), None, place, "an invalid document satisfies no profile")
    elif result.get("documentType") not in (None, "WorkReceipt"):
        # Section 10.4: the levels are levels of assurance about a unit of work, so a
        # VerificationVerdict or a BlameAttestation satisfies none of them.  ``profile:
        # null`` with ``valid: true`` is the correct answer and does not mean "below L0".
        report.equal(
            result.get("profile"),
            None,
            place,
            "section 10.4: a document that is not a WorkReceipt satisfies no profile "
            "(documentType %r)" % (result.get("documentType"),),
        )


def check_canonicalization_vector(entry: Dict[str, Any], impl: Impl, report: Report) -> None:
    place = entry["id"]
    if entry["expect"] == "invalid":
        code, out, err = impl.run(["canonicalize", entry["file"]])
        report.equal(code, EXIT_INVALID, place, "section 4.4: the canonicalizer itself must fail")
        for expected in entry["expectedCodes"]:
            report.check(
                expected in err,
                place,
                "stderr does not report %s (stderr: %s)" % (expected, err.strip()[:300]),
            )
        report.equal(out, b"", place, "a failing canonicalize must write nothing to stdout")
        return

    code, out, err = impl.run(["canonicalize", entry["file"]])
    report.equal(code, EXIT_OK, place, "canonicalize exit code (stderr: %s)" % (err.strip()[:300],))
    with open(os.path.join(HERE, entry["canonicalFile"]), "rb") as handle:
        recorded = handle.read()
    report.equal(
        out.hex(),
        recorded.hex(),
        place,
        "canonical bytes differ from %s" % (entry["canonicalFile"],),
    )
    report.equal(recorded.hex(), entry["canonicalHex"], place, "canonicalHex differs from the .canonical file")
    report.equal(len(recorded), entry["canonicalLength"], place, "canonicalLength")
    report.check(
        not recorded.endswith(b"\n"),
        place,
        "section 4.1: the canonical form carries no trailing newline",
    )
    expected_sri = "sha256-" + base64.b64encode(hashlib.sha256(recorded).digest()).decode("ascii")
    report.equal(entry["digestSRI"], expected_sri, place, "digestSRI over the recorded canonical bytes")
    code, out, err = impl.run(["digest", entry["file"]])
    report.equal(code, EXIT_OK, place, "digest exit code (stderr: %s)" % (err.strip()[:300],))
    report.equal(out.decode("utf-8").strip(), entry["digestSRI"], place, "`digest` output")


def check_proof_vector(entry: Dict[str, Any], impl: Impl, report: Report) -> None:
    place = entry["id"]
    with open(os.path.join(HERE, entry["file"]), "r", encoding="utf-8") as handle:
        worked = json.load(handle)

    # -- the manifest and the vector payload must agree ---------------------
    for field in ("proofConfigHash", "transformedDocumentHash", "hashData", "proofValue"):
        report.equal(worked.get(field), entry.get(field), place, "%s: manifest vs %s" % (field, entry["file"]))

    # -- section 6.2 step 6: proof config FIRST ----------------------------
    report.equal(
        entry["hashData"],
        entry["proofConfigHash"] + entry["transformedDocumentHash"],
        place,
        "section 6.2 step 6: hashData = proofConfigHash || transformedDocumentHash",
    )
    report.equal(len(bytes.fromhex(entry["hashData"])), 64, place, "hashData length in bytes")

    # -- the CLI's own hashdata output -------------------------------------
    code, out, err = impl.run(["hashdata", entry["securedFile"]])
    report.equal(code, EXIT_OK, place, "hashdata exit code (stderr: %s)" % (err.strip()[:300],))
    lines = out.decode("utf-8").strip().splitlines()
    report.equal(
        lines,
        [entry["proofConfigHash"], entry["transformedDocumentHash"], entry["hashData"]],
        place,
        "`hashdata` must print proofConfigHash, transformedDocumentHash, hashData",
    )

    # -- the two canonical byte strings the hashes are taken over ----------
    for cli_file, hex_field, hash_field, label in (
        (entry["unsecuredFile"], "transformedDocumentHex", "transformedDocumentHash", "transformedDocument"),
        (entry["proofConfigFile"], "canonicalProofConfigHex", "proofConfigHash", "canonicalProofConfig"),
    ):
        code, out, err = impl.run(["canonicalize", cli_file])
        report.equal(code, EXIT_OK, place, "canonicalize %s (stderr: %s)" % (cli_file, err.strip()[:300]))
        report.equal(out.hex(), entry[hex_field], place, "%s bytes" % (label,))
        report.equal(
            hashlib.sha256(out).hexdigest(),
            entry[hash_field],
            place,
            "SHA-256(%s) must equal %s" % (label, hash_field),
        )
        recorded_text = worked.get(label)
        if isinstance(recorded_text, str):
            report.equal(
                recorded_text.encode("utf-8").hex(),
                entry[hex_field],
                place,
                "%s recorded as text vs as hex" % (label,),
            )

    # -- the secured document verifies ------------------------------------
    args = ["verify", entry["securedFile"]]
    if entry.get("profile"):
        args += ["--profile", entry["profile"]]
    if entry.get("now"):
        args += ["--now", entry["now"]]
    code, out, err = impl.run(args)
    report.equal(code, EXIT_OK, place, "the worked example must verify (stderr: %s)" % (err.strip()[:300],))
    try:
        result = json.loads(out.decode("utf-8"))
    except ValueError as exc:
        report.check(False, place, "verify stdout is not JSON: %s" % (exc,))
        return
    report.equal(result.get("valid"), True, place, "worked example result.valid")
    report.equal(_codes(result.get("reasons") or ()), [], place, "worked example reasons")

    # -- the TEST KEY is a published seed and is marked as one -------------
    key = worked.get("key") or {}
    report.check(
        key.get("privateKeySeedHex") in RFC8032_SEEDS,
        place,
        "the worked example's seed is not a published RFC 8032 test vector",
    )
    report.check(
        "TEST KEY" in (key.get("WARNING") or ""),
        place,
        "the worked example key must be marked as a TEST KEY without authority",
    )

    # -- the recorded proofValue is the signature over hashData -----------
    secured_proof_value = (
        (worked.get("securedDocument") or {}).get("proof") or {}
    ).get("proofValue")
    report.equal(secured_proof_value, entry["proofValue"], place, "securedDocument proof.proofValue")
    if not impl.is_reference:
        report.skip("%s: Ed25519 cross-check of the recorded signature" % (place,))
        return
    try:
        from awr.didkey import parse_did_key, verify_signature
        from awr.multibase import multibase_decode_base58btc
    except ImportError:
        report.skip("%s: Ed25519 cross-check (awr not importable)" % (place,))
        return
    signature = multibase_decode_base58btc(entry["proofValue"])
    report.equal(len(signature), 64, place, "section 6.1: proofValue decodes to 64 bytes")
    report.equal(signature.hex(), worked.get("signatureHex"), place, "signatureHex")
    public_key = parse_did_key(key.get("did"))
    report.equal(public_key.hex(), key.get("publicKeyHex"), place, "did:key derives publicKeyHex")
    hash_data_bytes = bytes.fromhex(entry["hashData"])
    report.check(
        verify_signature(public_key, signature, hash_data_bytes),
        place,
        "the recorded proofValue does not verify over hashData under the did:key's key",
    )
    swapped = hash_data_bytes[32:] + hash_data_bytes[:32]
    report.check(
        not verify_signature(public_key, signature, swapped),
        place,
        "the signature also verifies over the REVERSED hashData, so the vector cannot "
        "distinguish the section 6.2 step 6 order",
    )


def phase_vectors(
    manifest: Dict[str, Any], impl: Impl, spec_registry: Dict[str, str], report: Report
) -> None:
    for entry in manifest["vectors"]:
        kind = entry.get("kind")
        if kind in ("document", "bundle"):
            check_document_vector(entry, impl, spec_registry, report)
        elif kind == "canonicalization":
            check_canonicalization_vector(entry, impl, report)
        elif kind == "proof":
            check_proof_vector(entry, impl, report)


# ---------------------------------------------------------------------------
# phase 4: AWR-CANON-006, which no input can trigger
# ---------------------------------------------------------------------------


def _nfc_deep(value: Any) -> Any:
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, list):
        return [_nfc_deep(item) for item in value]
    if isinstance(value, dict):
        return dict((_nfc_deep(k), _nfc_deep(v)) for k, v in value.items())
    return value


def phase_canon_006(manifest: Dict[str, Any], impl: Impl, report: Report) -> None:
    """Prove the code fires, since section 4.1 item 2 makes it a property of the code.

    ``AWR-CANON-006`` reports that the implementation's own canonicalizer is lossy, so no
    document can produce it.  What can is a canonicalizer that applies NFC: the NFC vector
    carries an object with both a precomposed and a decomposed spelling of the same name,
    which normalization collides, losing a member of a signed document.
    """
    where = "AWR-CANON-006"
    if not impl.is_reference:
        report.skip("%s: needs the reference library, not the CLI" % (where,))
        return
    try:
        from awr.errors import AwrError
        from awr.jcs import canonical_self_check, canonicalize, loads
    except ImportError:
        report.skip("%s: awr not importable" % (where,))
        return

    path = None
    for entry in manifest["vectors"]:
        if entry["id"] == "canonicalization/no-nfc-normalization":
            path = os.path.join(HERE, entry["file"])
    if not report.check(path is not None, where, "the no-nfc-normalization vector is missing"):
        return
    with open(path, "rb") as handle:
        value = loads(handle.read())

    report.check(
        len(value) == 7,
        where,
        "the NFC vector must carry both spellings of the colliding name; it has %d members"
        % (len(value),),
    )
    try:
        canonical_self_check(value)
        clean = True
    except AwrError as err:
        clean = False
        report.check(False, where, "the reference canonicalizer failed its own self-check: %s" % (err,))
    report.check(clean, where, "a conformant canonicalizer must pass the self-check on this input")

    def nfc_canonicalizer(inner: Any) -> bytes:
        return canonicalize(_nfc_deep(inner))

    try:
        canonical_self_check(value, canonicalizer=nfc_canonicalizer)
        report.check(
            False,
            where,
            "an NFC-applying canonicalizer passed the self-check: the code cannot fire, so "
            "section 4.1 item 2 is unenforced",
        )
    except AwrError as err:
        report.equal(err.code, "AWR-CANON-006", where, "code raised for an NFC-applying canonicalizer")
        report.note("AWR-CANON-006 fires for an NFC-applying canonicalizer, as declared")


# ---------------------------------------------------------------------------
# phase 5: determinism / tree matches the generator
# ---------------------------------------------------------------------------


def _tree_files(root: str) -> List[str]:
    out: List[str] = []
    for directory, _dirs, names in os.walk(root):
        for name in names:
            full = os.path.join(directory, name)
            out.append(os.path.relpath(full, root))
    return sorted(out)


def _regenerate(target: str) -> Tuple[int, str]:
    """Run generate.py with *target* as its output directory."""
    os.makedirs(target, exist_ok=True)
    shutil.copyfile(os.path.join(HERE, "generate.py"), os.path.join(target, "generate.py"))
    env = dict(os.environ)
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = REFERENCE if not existing else REFERENCE + os.pathsep + existing
    process = subprocess.Popen(
        [sys.executable, "generate.py"],
        cwd=target,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    _out, err = process.communicate()
    os.remove(os.path.join(target, "generate.py"))
    return process.returncode, err.decode("utf-8", "replace")


def _diff_trees(left: str, right: str, ignore: Sequence[str], report: Report, where: str, what: str) -> None:
    left_files = [f for f in _tree_files(left) if f not in ignore]
    right_files = [f for f in _tree_files(right) if f not in ignore]
    report.equal(left_files, right_files, where, "%s: the file lists differ" % (what,))
    for name in sorted(set(left_files) & set(right_files)):
        same = filecmp.cmp(os.path.join(left, name), os.path.join(right, name), shallow=False)
        if not same:
            with open(os.path.join(left, name), "rb") as handle:
                a = handle.read()
            with open(os.path.join(right, name), "rb") as handle:
                b = handle.read()
            offset = next(
                (i for i in range(min(len(a), len(b))) if a[i] != b[i]), min(len(a), len(b))
            )
            report.check(
                False,
                where,
                "%s: %s differs, first at byte %d (%d vs %d bytes)"
                % (what, name, offset, len(a), len(b)),
            )


def phase_determinism(report: Report) -> None:
    where = "generate.py"
    workdir = tempfile.mkdtemp(prefix="awr-vectors-")
    try:
        first = os.path.join(workdir, "run1")
        second = os.path.join(workdir, "run2")
        for target in (first, second):
            code, err = _regenerate(target)
            if not report.equal(code, 0, where, "generate.py exit code\n    stderr: %s" % (err.strip(),)):
                return
        _diff_trees(first, second, (), report, where, "two runs of the generator")
        _diff_trees(
            first,
            HERE,
            ("generate.py", "check_vectors.py", "interop.sh", "README.md"),
            report,
            where,
            "the committed tree vs a fresh generation",
        )
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check every AWR/2 vector against the outcome index.json claims for it"
    )
    parser.add_argument(
        "--impl",
        metavar="COMMAND",
        help="implementation under test (default: the reference `python -m awr`)",
    )
    parser.add_argument("--skip-regenerate", action="store_true", help="skip the determinism phase")
    parser.add_argument("--only", metavar="SUBSTRING", help="only vectors whose id contains this")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(list(sys.argv[1:] if argv is None else argv))

    impl = default_impl() if not args.impl else Impl(shlex.split(args.impl), False)
    report = Report(verbose=args.verbose)

    with open(INDEX, "r", encoding="utf-8") as handle:
        manifest = json.load(handle)
    spec_registry = parse_spec_registry(SPEC)
    # The AWR-CANON-006 phase reads one specific vector, so it always sees the whole
    # manifest: --only narrows what is *run*, not what the suite is allowed to assume.
    full_manifest = manifest

    if args.only:
        manifest = dict(manifest)
        manifest["vectors"] = [v for v in manifest["vectors"] if args.only in v["id"]]
        manifest["vectorCount"] = len(manifest["vectors"])
        sys.stderr.write("filtered to %d vectors\n" % (len(manifest["vectors"]),))

    sys.stderr.write(
        "checking %d vectors against %s\n" % (len(manifest["vectors"]), " ".join(impl.command))
    )
    sys.stderr.write("SPEC.md section 11.2 registry: %d codes\n" % (len(spec_registry),))

    phase_manifest(manifest, report)
    if not args.only:
        phase_orphans(manifest, report)
        phase_coverage(manifest, spec_registry, report)
    phase_spec_vs_reference(spec_registry, report)
    phase_keys(manifest, report)
    phase_vectors(manifest, impl, spec_registry, report)
    phase_canon_006(full_manifest, impl, report)
    if args.skip_regenerate or args.only:
        report.skip("determinism (--skip-regenerate)")
    else:
        phase_determinism(report)

    sys.stderr.write("\n%d assertions\n" % (report.checks,))
    for skipped in report.skipped:
        sys.stderr.write("SKIPPED %s\n" % (skipped,))
    if report.failures:
        sys.stderr.write("\n%d FAILURE(S)\n\n" % (len(report.failures),))
        for failure in report.failures:
            sys.stderr.write("FAIL %s\n" % (failure,))
        return 1
    sys.stderr.write("OK: every vector behaves exactly as index.json claims\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
