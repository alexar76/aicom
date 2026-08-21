#!/usr/bin/env python3
"""Drive every registered AWR/2 implementation through the SPEC.md section 17 CLI.

    awr/conformance/run.py                      # every registered implementation
    awr/conformance/run.py --impl rust          # one of them
    awr/conformance/run.py --markdown           # the matrix as markdown, for README.md
    awr/conformance/run.py --add-impl '{...}'   # a third-party descriptor, not registered

Standard library only, Python 3.9+.  It has to be: an implementer who has just written an
AWR verifier in Go should be able to measure it without installing a Python toolchain
around it.

What this is, and what it is not
--------------------------------
``awr/vectors/check_vectors.py`` holds the *vector set* to its own contract -- it also
regenerates the tree, checks section 11.2 coverage, and reaches into the reference library
for the two properties no CLI can show.  It answers "is the manifest honest?".

This runner answers a different question -- "which implementations conform, vector by
vector?" -- and answers it for **any** implementation, through the section 17 subcommands
and nothing else.  It never imports an implementation, never inspects a source tree, and
never treats the reference as the arbiter: the arbiter is ``awr/vectors/index.json``, which
records for every vector the outcome, the exact reason-code set and the reason the vector
exists.  A disagreement between two implementations is therefore a disagreement with the
manifest, which is a defect in one of them or an ambiguity in the specification -- and the
second case is the one worth finding.

Because the manifest is the arbiter, a conformance level is not divisible: an
implementation either reproduces **every** vector in the manifest or it does not conform.
There is no "conforms except for chains".  See README.md.

Outputs
-------
* a human-readable matrix on stdout (``--markdown`` for the README's table);
* ``results.json`` -- per implementation, per vector: ``pass`` / ``fail`` /
  ``unsupported``, with the failed assertions spelled out;
* ``badge.json`` -- shields.io endpoint format, passed/total.

Exit code: ``0`` when no vector failed for any implementation, ``1`` otherwise.  An
implementation that cannot be driven at all is recorded as ``unsupported`` with the reason
and does **not** turn the run red -- it is an absent measurement, not a failed one, and
deleting the row would hide that distinction.  The one thing that never becomes
``unsupported`` is a vector: a subcommand section 17 requires is a subcommand a conformant
implementation has.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
AWR_ROOT = os.path.abspath(os.path.join(HERE, ".."))
REPO_ROOT = os.path.abspath(os.path.join(AWR_ROOT, ".."))
VECTORS = os.path.join(AWR_ROOT, "vectors")
INDEX = os.path.join(VECTORS, "index.json")
SPEC = os.path.join(AWR_ROOT, "SPEC.md")
CHECK_VECTORS = os.path.join(VECTORS, "check_vectors.py")
REGISTRY_FILE = os.path.join(HERE, "implementations.json")
RESULTS_FILE = os.path.join(HERE, "results.json")
BADGE_FILE = os.path.join(HERE, "badge.json")

#: Section 17 exit codes.
EXIT_OK = 0
EXIT_INVALID = 1
EXIT_USAGE = 2
EXIT_UNIMPLEMENTED = 3

#: Section 17 subcommands.  ``issue`` is the only OPTIONAL one.
SUBCOMMANDS = ("verify", "canonicalize", "digest", "hashdata", "issue")
OPTIONAL_SUBCOMMANDS = ("issue",)

#: Section 11.1: the result members every conforming implementation MUST emit.
RESULT_FLOOR = (
    "valid",
    "awrVersion",
    "documentType",
    "profile",
    "reasons",
    "warnings",
    "chain",
    "verifiedProof",
)

AWR_TYPES = ("WorkReceipt", "VerificationVerdict", "BlameAttestation")

#: Section 11.1 / 6.3: codes that mean step 6 was not performed, so ``verifiedProof`` is
#: null.  Kept here rather than derived, because the set is a normative list in section
#: 11.1 and a runner that inferred it would be guessing at the rule it is checking.
_NO_SIGCHECK_PREFIXES = ("AWR-CANON-", "AWR-KEY-", "AWR-PROOF-")
#: ``AWR-LEGACY-003``/``005`` (section 12.3): the version gate rejected the document, or the
#: caller declined the AWR/1 rules, so it was verified under no rule set and no section 6.1
#: proof was checked -- even where a correct signature over the section 12.1 rendering is
#: present in the file.
_NO_SIGCHECK_CODES = (
    "AWR-DOC-001",
    "AWR-DOC-010",
    "AWR-BUNDLE-001",
    "AWR-BUNDLE-003",
    "AWR-LEGACY-003",
    "AWR-LEGACY-005",
)
_LEGACY_WARNING = "AWR-LEGACY-001"

#: The ``issue`` capability probe signs this subject.  The digests are the manifest's own
#: ``payloads`` entries, so the probe carries no invented hash.
PROBE_SUBJECT = {
    "work": {
        "modelId": "conformance-probe@example",
        "capability": "urn:example:capability:summarise",
        "startedAt": "2026-07-31T10:15:28Z",
        "completedAt": "2026-07-31T10:15:30Z",
        "latencyMs": 2340,
        "status": "succeeded",
    },
    "inputDigest": None,   # filled from index.json payloads.prompt
    "outputDigest": None,  # filled from index.json payloads.summary
    "nonce": "01J9Z8QK4T7YB2N5V6W8XA3C0D",
}

PASS = "pass"
FAIL = "fail"
UNSUPPORTED = "unsupported"


# ---------------------------------------------------------------------------
# section 11.2, from the specification itself
# ---------------------------------------------------------------------------


def load_spec_registry() -> Dict[str, str]:
    """``{code: severity}`` from SPEC.md section 11.2.

    Imported from ``awr/vectors/check_vectors.py`` rather than re-implemented: two parsers
    of the same normative table drift, and the table is the one place the severity of a
    code is defined (section 11.1: a code has exactly one severity).
    """
    spec = importlib.util.spec_from_file_location("awr_check_vectors", CHECK_VECTORS)
    if spec is None or spec.loader is None:  # pragma: no cover -- a broken checkout
        raise SystemExit("conformance: cannot load %s" % (CHECK_VECTORS,))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    registry = module.parse_spec_registry(SPEC)
    if not registry:
        raise SystemExit("conformance: no reason codes parsed out of SPEC.md section 11.2")
    return registry


# ---------------------------------------------------------------------------
# assertions
# ---------------------------------------------------------------------------


class Checks(object):
    """One vector's assertions for one implementation.

    Every assertion is recorded, none raises: a conformance report whose first failure
    hides the next nine is the report that makes independent implementation expensive
    (section 11.1, last bullet).
    """

    def __init__(self) -> None:
        self.count = 0
        self.failures: List[str] = []

    def ok(self, condition: bool, message: str) -> bool:
        self.count += 1
        if not condition:
            self.failures.append(message)
        return bool(condition)

    def eq(self, got: Any, want: Any, what: str) -> bool:
        return self.ok(got == want, "%s\n      expected: %r\n      actual:   %r" % (what, want, got))

    @property
    def outcome(self) -> str:
        return FAIL if self.failures else PASS


# ---------------------------------------------------------------------------
# an implementation under test
# ---------------------------------------------------------------------------


def expand(value: str, table: Dict[str, str]) -> str:
    out = value
    for name, replacement in table.items():
        out = out.replace("${%s}" % (name,), replacement)
    # Anything left of the form ${NAME} comes from the environment; an unset name expands
    # to the empty string, which produces a path that does not exist and therefore a
    # descriptor reported as unresolvable rather than a silent mis-run.
    while "${" in out:
        start = out.index("${")
        end = out.find("}", start)
        if end < 0:
            break
        name = out[start + 2:end]
        out = out[:start] + os.environ.get(name, "") + out[end + 1:]
    return out


def _executable_exists(path: str) -> bool:
    if not path:
        return False
    if os.sep in path or path.startswith("."):
        return os.path.isfile(path) and os.access(path, os.X_OK)
    return shutil.which(path) is not None


class Implementation(object):
    def __init__(self, descriptor: Dict[str, Any]) -> None:
        self.descriptor = descriptor
        self.name = str(descriptor.get("name") or "<unnamed>")
        self.language = str(descriptor.get("language") or "")
        self.crypto_library = str(descriptor.get("cryptoLibrary") or "")
        self.role = str(descriptor.get("role") or "")
        self.notes = str(descriptor.get("notes") or "")
        self.declared_optional = tuple(descriptor.get("optionalSubcommands") or ())
        self.unsupported_reason: Optional[str] = None
        self.command: List[str] = []
        self.runtime_version: Optional[str] = None

        table = {"REPO_ROOT": REPO_ROOT, "AWR_ROOT": AWR_ROOT}
        candidates: List[List[str]] = []
        if descriptor.get("command"):
            candidates.append([expand(str(a), table) for a in descriptor["command"]])
        for candidate in descriptor.get("commandCandidates") or ():
            candidates.append([expand(str(a), table) for a in candidate])
        if not candidates:
            self.unsupported_reason = (
                "the descriptor names neither 'command' nor 'commandCandidates'"
            )
            return

        for candidate in candidates:
            if _executable_exists(candidate[0]):
                self.command = candidate
                break
        if not self.command:
            self.unsupported_reason = "no executable found; tried: %s" % (
                "; ".join(" ".join(c) for c in candidates),
            )
            return

        self.env = dict(os.environ)
        for key, value in (descriptor.get("env") or {}).items():
            self.env[str(key)] = expand(str(value), table)

        version_command = descriptor.get("runtimeVersionCommand")
        if version_command:
            table_with_exe = dict(table)
            table_with_exe["IMPL_EXE"] = self.command[0]
            argv = [expand(str(a), table_with_exe) for a in version_command]
            if _executable_exists(argv[0]):
                code, out, err = _spawn(argv, self.env, VECTORS)
                text = (out.decode("utf-8", "replace") + err).strip()
                if code == 0 and text:
                    self.runtime_version = text.splitlines()[0].strip()

    @property
    def driveable(self) -> bool:
        return self.unsupported_reason is None

    def run(self, args: Sequence[str], timeout: int = 120) -> Tuple[int, bytes, str]:
        return _spawn(self.command + list(args), self.env, VECTORS, timeout)

    def command_string(self) -> str:
        """The resolved command, with the repository root stripped.

        ``results.json`` is committed, so it must not carry the absolute paths of whoever
        ran it: a checkout somewhere else would read as a different command, and the
        machine's directory layout is nobody's business.
        """
        prefix = REPO_ROOT + os.sep
        return " ".join(a[len(prefix):] if a.startswith(prefix) else a for a in self.command)


def _spawn(
    argv: Sequence[str], env: Dict[str, str], cwd: str, timeout: int = 120
) -> Tuple[int, bytes, str]:
    try:
        process = subprocess.Popen(
            list(argv), cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
    except OSError as exc:
        return 127, b"", "cannot execute %s: %s" % (argv[0], exc)
    try:
        out, err = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        out, err = process.communicate()
        return 124, out, (err or b"").decode("utf-8", "replace") + "\n[timed out]"
    return process.returncode, out, (err or b"").decode("utf-8", "replace")


# ---------------------------------------------------------------------------
# per-vector checks: document and bundle
# ---------------------------------------------------------------------------


def _codes(entries: Any) -> List[str]:
    if not isinstance(entries, list):
        return []
    return [e.get("code") for e in entries if isinstance(e, dict) and isinstance(e.get("code"), str)]


def _compare_sets(
    checks: Checks,
    label: str,
    reported: Sequence[str],
    required: Sequence[str],
    allowed_extra: Sequence[str],
) -> None:
    reported_set = set(reported)
    required_set = set(required)
    missing = sorted(required_set - reported_set)
    unexpected = sorted(reported_set - (required_set | set(allowed_extra)))
    checks.ok(
        not missing,
        "%s the manifest requires were NOT reported: %s (reported: %s)"
        % (label, ", ".join(missing), ", ".join(sorted(reported_set)) or "none"),
    )
    checks.ok(
        not unexpected,
        "%s reported that the manifest does not allow: %s (required: %s)"
        % (label, ", ".join(unexpected), ", ".join(sorted(required_set)) or "none"),
    )


def _lenient_document(path: str) -> Optional[Dict[str, Any]]:
    """What ``json`` alone makes of the vector, or ``None``.

    Not a conformant parse and not used as one: its only job is to read back what the
    *document* claims its ``awrVersion`` and ``type`` are, so that a result can be held to
    reporting the document's own values instead of the verifier's (section 11.1).
    """
    try:
        with open(path, "rb") as handle:
            value = json.loads(handle.read().decode("utf-8"))
    except Exception:
        return None
    if not isinstance(value, dict) or isinstance(value.get("documents"), list):
        return None
    return value


def check_result_invariants(entry: Dict[str, Any], result: Dict[str, Any], checks: Checks) -> None:
    """The section 11.1 rules that hold for every result, whatever the vector says.

    They are asserted for every vector rather than recorded per vector because 11.1 states
    them as rules about the *result*: a vector added to the manifest later is held to them
    without anyone remembering to.
    """
    errors = _codes(result.get("reasons"))
    warnings = _codes(result.get("warnings"))
    blocked = (
        any(c.startswith(_NO_SIGCHECK_PREFIXES) for c in errors)
        or any(c in _NO_SIGCHECK_CODES for c in errors)
        or _LEGACY_WARNING in warnings
    )
    no_canonical_form = any(c.startswith("AWR-CANON-") for c in errors)

    verified_proof = result.get("verifiedProof")
    if blocked:
        checks.eq(
            verified_proof,
            None,
            "section 11.1: verifiedProof MUST be null when the result carries a code section "
            "6.3 names as preventing step 6, or when no section 6.1 proof was checked at all "
            "(reported: %s)" % (", ".join(sorted(errors) + sorted(warnings)) or "nothing",),
        )
    else:
        checks.ok(
            isinstance(verified_proof, int)
            and not isinstance(verified_proof, bool)
            and verified_proof >= 0,
            "section 11.1: a section 6.1 proof was checked and verified, so verifiedProof MUST "
            "hold its zero-based index and MUST NOT be null; got %r" % (verified_proof,),
        )

    if no_canonical_form:
        checks.eq(
            (result.get("awrVersion"), result.get("documentType")),
            (None, None),
            "section 11.1: awrVersion and documentType MUST both be null when the document has "
            "no canonical form (%s)" % (", ".join(sorted(errors)),),
        )
    else:
        document = _lenient_document(os.path.join(VECTORS, entry["file"]))
        if document is not None:
            own_version = document.get("awrVersion")
            checks.eq(
                result.get("awrVersion"),
                own_version if isinstance(own_version, str) else None,
                "section 11.1: awrVersion reports the DOCUMENT's awrVersion, never the version "
                "the verifier implements and never an invented value",
            )
            types = document.get("type")
            named = [t for t in AWR_TYPES if t in types] if isinstance(types, list) else []
            checks.eq(
                result.get("documentType"),
                named[0] if len(named) == 1 else None,
                "section 11.1: documentType reports the AWR type the DOCUMENT's `type` array "
                "carries, and null when `type` names more than one",
            )

    chain = result.get("chain")
    if isinstance(chain, dict):
        for member in ("resolved", "unresolved"):
            checks.ok(
                isinstance(chain.get(member), int) and not isinstance(chain.get(member), bool),
                "section 11.1: chain.%s MUST be an integer, got %r" % (member, chain.get(member)),
            )
        if result.get("documentType") in ("VerificationVerdict", "BlameAttestation"):
            checks.eq(
                (chain.get("resolved"), chain.get("unresolved")),
                (0, 0),
                "section 11.1: chain counts section 8.1 `parents` edges only -- a verdict's "
                "verifiedWork and a blame's chain/blamedWork are digest references, not chain "
                "edges",
            )
        document = _lenient_document(os.path.join(VECTORS, entry["file"]))
        if (
            document is not None
            and not entry.get("supporting")
            and result.get("documentType") == "WorkReceipt"
        ):
            subject = document.get("credentialSubject")
            parents = subject.get("parents") if isinstance(subject, dict) else None
            well_formed = 0
            if isinstance(parents, list):
                for ref in parents:
                    if (
                        isinstance(ref, dict)
                        and isinstance(ref.get("digestSRI"), str)
                        and ref["digestSRI"].startswith("sha256-")
                    ):
                        well_formed += 1
            checks.eq(
                (chain.get("resolved") or 0) + (chain.get("unresolved") or 0),
                well_formed,
                "section 11.1: every well-formed `parents` entry is counted exactly once, as "
                "resolved or unresolved, and an entry that is not a well-formed digest reference "
                "(AWR-CHAIN-001/002) is counted in neither",
            )


def verify_args(entry: Dict[str, Any]) -> List[str]:
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
    return args


def check_document_vector(
    entry: Dict[str, Any], impl: Implementation, registry: Dict[str, str], checks: Checks
) -> None:
    args = verify_args(entry)
    code, out, err = impl.run(args)
    if code == EXIT_UNIMPLEMENTED:
        checks.ok(
            False,
            "`verify` exited 3 (unimplemented). Section 17 requires it; only `issue` is "
            "OPTIONAL.\n      stderr: %s" % (err.strip()[:300],),
        )
        return
    expect_valid = entry["expect"] == "valid"
    checks.eq(
        code,
        EXIT_OK if expect_valid else EXIT_INVALID,
        "section 17 exit code for `%s`\n      stderr: %s" % (" ".join(args), err.strip()[:300]),
    )
    try:
        result = json.loads(out.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        checks.ok(False, "stdout is not the section 11.1 result JSON: %s" % (exc,))
        return
    if not checks.ok(isinstance(result, dict), "the section 11.1 result MUST be a JSON object"):
        return

    for member in RESULT_FLOOR:
        checks.ok(member in result, "the section 11.1 result is missing %r" % (member,))

    checks.eq(result.get("valid"), expect_valid, "result.valid")
    errors = _codes(result.get("reasons"))
    warnings = _codes(result.get("warnings"))
    checks.eq(
        result.get("valid"),
        not errors,
        "section 11.1: valid MUST be true if and only if reasons carries no error entry",
    )
    _compare_sets(checks, "error codes", errors, entry["expectedCodes"], entry.get("allowedExtraCodes") or ())
    _compare_sets(
        checks,
        "warning codes",
        warnings,
        entry["expectedWarnings"],
        entry.get("allowedExtraWarnings") or (),
    )

    for reason in result.get("reasons") or ():
        if not isinstance(reason, dict):
            checks.ok(False, "every `reasons` entry MUST be an object, got %r" % (reason,))
            continue
        checks.eq(reason.get("severity"), "error", "severity of reported %s" % (reason.get("code"),))
        checks.eq(
            registry.get(reason.get("code")),
            "error",
            "%s is reported in `reasons`; its SPEC.md 11.2 severity" % (reason.get("code"),),
        )
    for warning in result.get("warnings") or ():
        if not isinstance(warning, dict):
            checks.ok(False, "every `warnings` entry MUST be an object, got %r" % (warning,))
            continue
        checks.eq(warning.get("severity"), "warning", "severity of reported %s" % (warning.get("code"),))
        checks.eq(
            registry.get(warning.get("code")),
            "warning",
            "%s is reported in `warnings`; its SPEC.md 11.2 severity" % (warning.get("code"),),
        )

    if expect_valid and entry.get("profile"):
        checks.eq(result.get("profile"), entry["profile"], "section 10.4: the highest profile satisfied")
    if not expect_valid:
        checks.eq(
            result.get("profile"),
            None,
            "section 10.4: every profile is defined over a valid document, so an invalid one "
            "satisfies none",
        )
    elif result.get("documentType") not in (None, "WorkReceipt"):
        checks.eq(
            result.get("profile"),
            None,
            "section 10.4: a document that is not a WorkReceipt satisfies no profile "
            "(documentType %r)" % (result.get("documentType"),),
        )

    check_result_invariants(entry, result, checks)


# ---------------------------------------------------------------------------
# per-vector checks: canonicalization and proof
# ---------------------------------------------------------------------------


def check_canonicalization_vector(entry: Dict[str, Any], impl: Implementation, checks: Checks) -> None:
    if entry["expect"] == "invalid":
        code, out, err = impl.run(["canonicalize", entry["file"]])
        checks.eq(
            code,
            EXIT_INVALID,
            "section 4.4 / 17: the canonicalizer itself must fail, exit 1\n      stderr: %s"
            % (err.strip()[:300],),
        )
        for expected in entry["expectedCodes"]:
            checks.ok(
                expected in err,
                "section 17: stderr must name %s when no result JSON can be produced "
                "(stderr: %s)" % (expected, err.strip()[:300]),
            )
        checks.eq(out, b"", "a failing `canonicalize` writes nothing to stdout")
        return

    code, out, err = impl.run(["canonicalize", entry["file"]])
    checks.eq(code, EXIT_OK, "`canonicalize` exit code\n      stderr: %s" % (err.strip()[:300],))
    with open(os.path.join(VECTORS, entry["canonicalFile"]), "rb") as handle:
        recorded = handle.read()
    checks.eq(
        out.hex(),
        recorded.hex(),
        "section 4: canonical bytes differ from the recorded %s" % (entry["canonicalFile"],),
    )
    checks.eq(out.hex(), entry["canonicalHex"], "canonical bytes differ from the manifest's canonicalHex")
    checks.eq(len(out), entry["canonicalLength"], "canonical length in bytes")
    checks.ok(
        not out.endswith(b"\n"),
        "section 4.1: the canonical form carries no trailing newline",
    )
    code, out, err = impl.run(["digest", entry["file"]])
    checks.eq(code, EXIT_OK, "`digest` exit code\n      stderr: %s" % (err.strip()[:300],))
    checks.eq(out.decode("utf-8", "replace").strip(), entry["digestSRI"], "`digest` output")


def check_proof_vector(entry: Dict[str, Any], impl: Implementation, checks: Checks) -> None:
    code, out, err = impl.run(["hashdata", entry["securedFile"]])
    checks.eq(code, EXIT_OK, "`hashdata` exit code\n      stderr: %s" % (err.strip()[:300],))
    checks.eq(
        out.decode("utf-8", "replace").strip().splitlines(),
        [entry["proofConfigHash"], entry["transformedDocumentHash"], entry["hashData"]],
        "section 17: `hashdata` prints proofConfigHash, transformedDocumentHash, hashData -- in "
        "the section 6.2 step 6 order, proof config FIRST",
    )

    for cli_file, hex_field, hash_field, label in (
        (entry["unsecuredFile"], "transformedDocumentHex", "transformedDocumentHash", "transformedDocument"),
        (entry["proofConfigFile"], "canonicalProofConfigHex", "proofConfigHash", "canonicalProofConfig"),
    ):
        code, out, err = impl.run(["canonicalize", cli_file])
        checks.eq(code, EXIT_OK, "`canonicalize %s` exit code\n      stderr: %s" % (cli_file, err.strip()[:300]))
        checks.eq(out.hex(), entry[hex_field], "section 6.2: %s bytes" % (label,))
        checks.eq(
            hashlib.sha256(out).hexdigest(),
            entry[hash_field],
            "section 6.2: SHA-256(%s) must equal %s" % (label, hash_field),
        )

    args = ["verify", entry["securedFile"]]
    if entry.get("profile"):
        args += ["--profile", entry["profile"]]
    if entry.get("now"):
        args += ["--now", entry["now"]]
    code, out, err = impl.run(args)
    checks.eq(code, EXIT_OK, "the worked example must verify\n      stderr: %s" % (err.strip()[:300],))
    try:
        result = json.loads(out.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        checks.ok(False, "verify stdout is not the section 11.1 result JSON: %s" % (exc,))
        return
    checks.eq(result.get("valid"), True, "worked example result.valid")
    checks.eq(_codes(result.get("reasons")), [], "worked example reasons")
    checks.eq(result.get("verifiedProof"), 0, "section 11.1: the single proof of section 6.1 has index 0")


# ---------------------------------------------------------------------------
# the OPTIONAL `issue` capability
# ---------------------------------------------------------------------------


def check_issue_capability(
    impl: Implementation, manifest: Dict[str, Any]
) -> Tuple[str, List[str], Optional[str]]:
    """Round-trip the OPTIONAL ``issue`` subcommand: sign, then verify what came out.

    Returns ``(outcome, failures, note)``.  Exit 3 is ``unsupported``, not a failure:
    section 17 makes ``issue`` OPTIONAL for verify-only implementations, and a verifier in
    a browser page holds no private key.

    The key is RFC 8032 section 7.1 TEST 1 -- published in an IETF standard, so this probe
    creates no secret.  Section 17 fixes the interoperable key-file form as a bare
    64-character hex seed on one line, and this is the check that it is accepted.
    """
    checks = Checks()
    key_entry = None
    for candidate in manifest.get("keys") or ():
        if candidate.get("name") == "hub":
            key_entry = candidate
    if key_entry is None:
        return UNSUPPORTED, [], "index.json names no 'hub' key to sign the probe with"

    subject = json.loads(json.dumps(PROBE_SUBJECT))
    payloads = manifest.get("payloads") or {}
    subject["inputDigest"] = payloads["prompt"]["digestSRI"]
    subject["outputDigest"] = payloads["summary"]["digestSRI"]

    workdir = tempfile.mkdtemp(prefix="awr-conformance-issue-")
    try:
        key_path = os.path.join(workdir, "issuer.key")
        with open(key_path, "w", encoding="ascii") as handle:
            handle.write(key_entry["privateKeySeedHex"] + "\n")
        subject_path = os.path.join(workdir, "subject.json")
        with open(subject_path, "w", encoding="utf-8") as handle:
            json.dump(subject, handle, indent=2, sort_keys=True)

        code, out, err = impl.run(
            ["issue", subject_path, "--key", key_path, "--type", "WorkReceipt"]
        )
        if code == EXIT_UNIMPLEMENTED:
            return UNSUPPORTED, [], (err.strip().splitlines() or ["exit 3"])[0][:220]
        checks.eq(code, EXIT_OK, "`issue` exit code\n      stderr: %s" % (err.strip()[:300],))
        try:
            document = json.loads(out.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            checks.ok(False, "section 17: `issue` must print the signed document to stdout: %s" % (exc,))
            return checks.outcome, checks.failures, None

        checks.eq(
            (document or {}).get("awrVersion"),
            "2.0.0",
            "section 3.1: an issued document carries awrVersion 2.0.0",
        )
        checks.eq(
            ((document or {}).get("issuer") or {}).get("id"),
            key_entry["did"],
            "section 5.1: the issued document's issuer.id is the did:key of the key file's seed",
        )
        issued_proof = (document or {}).get("proof")
        if isinstance(issued_proof, list) and issued_proof:
            issued_proof = issued_proof[0]
        if not isinstance(issued_proof, dict):
            issued_proof = {}
        checks.eq(
            issued_proof.get("@context"),
            (document or {}).get("@context"),
            "section 6.2 step 9: the EMITTED proof carries the document's @context. An AWR\n"
            "      verifier injects it either way, so only a check on the serialized proof\n"
            "      catches this; an off-the-shelf eddsa-jcs-2022 verifier rebuilds the proof\n"
            "      configuration from the proof alone and reports a bogus signature failure\n"
            "      when the member is absent",
        )

        issued_path = os.path.join(workdir, "issued.json")
        with open(issued_path, "wb") as handle:
            handle.write(out)
        code, out, err = impl.run(["verify", issued_path, "--profile", "L0"])
        checks.eq(
            code,
            EXIT_OK,
            "the document this implementation issued must verify in it\n      stderr: %s"
            % (err.strip()[:300],),
        )
        try:
            result = json.loads(out.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            checks.ok(False, "verify stdout is not the section 11.1 result JSON: %s" % (exc,))
            return checks.outcome, checks.failures, None
        checks.eq(result.get("valid"), True, "the issued document's result.valid")
        checks.eq(result.get("profile"), "L0", "section 10.1: a freshly issued receipt satisfies L0")
        checks.eq(_codes(result.get("reasons")), [], "the issued document's reasons")
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    return checks.outcome, checks.failures, None


# ---------------------------------------------------------------------------
# running one implementation over the manifest
# ---------------------------------------------------------------------------


def run_implementation(
    impl: Implementation, manifest: Dict[str, Any], registry: Dict[str, str], quiet: bool
) -> Dict[str, Any]:
    vectors_out: Dict[str, Any] = {}
    if not impl.driveable:
        for entry in manifest["vectors"]:
            vectors_out[entry["id"]] = {
                "outcome": UNSUPPORTED,
                "reason": impl.unsupported_reason,
                "assertions": 0,
                "failures": [],
            }
        return {
            "name": impl.name,
            "language": impl.language,
            "cryptoLibrary": impl.crypto_library,
            "role": impl.role,
            "notes": impl.notes,
            "command": None,
            "runtimeVersion": None,
            "driveable": False,
            "unsupportedReason": impl.unsupported_reason,
            "subcommands": dict((name, UNSUPPORTED) for name in SUBCOMMANDS),
            "vectors": vectors_out,
        }

    subcommand_state = dict((name, PASS) for name in SUBCOMMANDS if name not in OPTIONAL_SUBCOMMANDS)
    for entry in manifest["vectors"]:
        checks = Checks()
        kind = entry.get("kind")
        if kind in ("document", "bundle"):
            check_document_vector(entry, impl, registry, checks)
        elif kind == "canonicalization":
            check_canonicalization_vector(entry, impl, checks)
        elif kind == "proof":
            check_proof_vector(entry, impl, checks)
        else:  # pragma: no cover -- phase_manifest in check_vectors.py rejects this
            checks.ok(False, "unknown vector kind %r" % (kind,))
        vectors_out[entry["id"]] = {
            "outcome": checks.outcome,
            "assertions": checks.count,
            "failures": checks.failures,
        }
        if checks.failures:
            if kind == "canonicalization":
                subcommand_state["canonicalize"] = FAIL
                subcommand_state["digest"] = FAIL
            elif kind == "proof":
                subcommand_state["hashdata"] = FAIL
            else:
                subcommand_state["verify"] = FAIL
        if not quiet:
            sys.stderr.write(
                "  %-16s %-50s %s\n" % (impl.name, entry["id"], checks.outcome.upper())
            )

    issue_outcome, issue_failures, issue_note = check_issue_capability(impl, manifest)
    subcommands = dict(subcommand_state)
    subcommands["issue"] = issue_outcome

    return {
        "name": impl.name,
        "language": impl.language,
        "cryptoLibrary": impl.crypto_library,
        "role": impl.role,
        "notes": impl.notes,
        "command": impl.command_string(),
        "runtimeVersion": impl.runtime_version,
        "driveable": True,
        "unsupportedReason": None,
        "subcommands": subcommands,
        "issue": {
            "outcome": issue_outcome,
            "failures": issue_failures,
            "note": issue_note,
            "declaredOptional": "issue" in impl.declared_optional,
        },
        "vectors": vectors_out,
    }


# ---------------------------------------------------------------------------
# reporting
# ---------------------------------------------------------------------------


def group_of(vector_id: str) -> str:
    return vector_id.split("/")[0]


def summarise(manifest: Dict[str, Any], runs: List[Dict[str, Any]]) -> Dict[str, Any]:
    groups: List[str] = []
    for entry in manifest["vectors"]:
        name = group_of(entry["id"])
        if name not in groups:
            groups.append(name)

    per_impl: Dict[str, Any] = {}
    passed = failed = unsupported = 0
    for run in runs:
        counts: Dict[str, Dict[str, int]] = {}
        for group in groups:
            counts[group] = {PASS: 0, FAIL: 0, UNSUPPORTED: 0, "total": 0}
        totals = {PASS: 0, FAIL: 0, UNSUPPORTED: 0, "total": 0}
        for vector_id, outcome in run["vectors"].items():
            group = group_of(vector_id)
            counts[group][outcome["outcome"]] += 1
            counts[group]["total"] += 1
            totals[outcome["outcome"]] += 1
            totals["total"] += 1
        per_impl[run["name"]] = {"groups": counts, "totals": totals}
        passed += totals[PASS]
        failed += totals[FAIL]
        unsupported += totals[UNSUPPORTED]

    measured = passed + failed
    return {
        "groups": groups,
        "perImplementation": per_impl,
        "passed": passed,
        "failed": failed,
        "unsupportedPairs": unsupported,
        "measured": measured,
        "vectorCount": len(manifest["vectors"]),
        "implementationCount": len(runs),
        "conformant": sorted(
            run["name"]
            for run in runs
            if run["driveable"]
            and all(v["outcome"] == PASS for v in run["vectors"].values())
        ),
    }


def _cell(counts: Dict[str, int]) -> str:
    if counts[UNSUPPORTED] == counts["total"] and counts["total"]:
        return "n/a"
    if counts[FAIL]:
        return "%d/%d FAIL" % (counts[PASS], counts["total"])
    return "%d/%d" % (counts[PASS], counts["total"])


def _table(rows: List[List[str]], markdown: bool) -> str:
    widths = [max(len(row[i]) for row in rows) for i in range(len(rows[0]))]
    lines: List[str] = []
    if markdown:
        lines.append("| " + " | ".join(rows[0][i].ljust(widths[i]) for i in range(len(widths))) + " |")
        lines.append("|" + "|".join("-" * (widths[i] + 2) for i in range(len(widths))) + "|")
        for row in rows[1:]:
            lines.append("| " + " | ".join(row[i].ljust(widths[i]) for i in range(len(widths))) + " |")
    else:
        lines.append("  " + "  ".join(rows[0][i].ljust(widths[i]) for i in range(len(widths))))
        lines.append("  " + "  ".join("-" * widths[i] for i in range(len(widths))))
        for row in rows[1:]:
            lines.append("  " + "  ".join(row[i].ljust(widths[i]) for i in range(len(widths))))
    return "\n".join(line.rstrip() for line in lines)


def matrix_text(
    manifest: Dict[str, Any], runs: List[Dict[str, Any]], summary: Dict[str, Any], markdown: bool
) -> str:
    names = [run["name"] for run in runs]
    out: List[str] = []

    header = ["vector group"] + names
    rows = [header]
    for group in summary["groups"]:
        row = ["`%s/`" % group if markdown else group + "/"]
        for name in names:
            row.append(_cell(summary["perImplementation"][name]["groups"][group]))
        rows.append(row)
    total_row = ["**all vectors**" if markdown else "ALL"]
    for name in names:
        total_row.append(_cell(summary["perImplementation"][name]["totals"]))
    rows.append(total_row)
    out.append(_table(rows, markdown))

    out.append("")
    sub_rows = [["section 17 subcommand"] + names]
    for subcommand in SUBCOMMANDS:
        label = "`%s`" % subcommand if markdown else subcommand
        if subcommand in OPTIONAL_SUBCOMMANDS:
            label += " (OPTIONAL)"
        row = [label]
        for run in runs:
            state = run["subcommands"].get(subcommand, UNSUPPORTED)
            row.append({PASS: "yes", FAIL: "FAIL", UNSUPPORTED: "not provided"}[state])
        sub_rows.append(row)
    out.append(_table(sub_rows, markdown))

    out.append("")
    meta_rows = [["implementation", "language", "crypto", "command"]]
    for run in runs:
        meta_rows.append(
            [
                "**%s**" % run["name"] if markdown else run["name"],
                run["language"] or "-",
                run["cryptoLibrary"] or "-",
                ("`%s`" % run["command"]) if run["command"] else "not resolvable: %s" % (run["unsupportedReason"],),
            ]
        )
    out.append(_table(meta_rows, markdown))
    return "\n".join(out)


def failure_report(runs: List[Dict[str, Any]]) -> str:
    lines: List[str] = []
    for run in runs:
        failures = [
            (vector_id, detail)
            for vector_id, detail in sorted(run["vectors"].items())
            if detail["outcome"] == FAIL
        ]
        if not failures and run.get("issue", {}).get("outcome") != FAIL:
            continue
        lines.append("")
        lines.append("%s: %d failing vector(s)" % (run["name"], len(failures)))
        for vector_id, detail in failures:
            lines.append("  FAIL %s" % (vector_id,))
            for message in detail["failures"]:
                lines.append("    - %s" % (message,))
        if run.get("issue", {}).get("outcome") == FAIL:
            lines.append("  FAIL <issue capability>")
            for message in run["issue"]["failures"]:
                lines.append("    - %s" % (message,))
    return "\n".join(lines)


def badge(summary: Dict[str, Any]) -> Dict[str, Any]:
    message = "%d/%d" % (summary["passed"], summary["measured"])
    if summary["unsupportedPairs"]:
        message += " (+%d n/a)" % (summary["unsupportedPairs"],)
    if summary["failed"]:
        colour = "red"
    elif summary["unsupportedPairs"]:
        colour = "yellow"
    else:
        colour = "brightgreen"
    return {
        "schemaVersion": 1,
        "label": "AWR/2 conformance",
        "message": message,
        "color": colour,
        "cacheSeconds": 3600,
    }


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def load_descriptors(args: argparse.Namespace) -> List[Dict[str, Any]]:
    with open(args.registry, "r", encoding="utf-8") as handle:
        registry_file = json.load(handle)
    descriptors = list(registry_file.get("implementations") or [])
    for blob in args.add_impl or ():
        try:
            extra = json.loads(blob)
        except ValueError as exc:
            raise SystemExit("conformance: --add-impl is not JSON: %s" % (exc,))
        if not isinstance(extra, dict):
            raise SystemExit("conformance: --add-impl must be a JSON object")
        descriptors.append(extra)
    if args.impl:
        wanted = set(args.impl)
        descriptors = [d for d in descriptors if d.get("name") in wanted]
        missing = wanted - set(d.get("name") for d in descriptors)
        if missing:
            raise SystemExit("conformance: no such implementation: %s" % (", ".join(sorted(missing)),))
    if not descriptors:
        raise SystemExit("conformance: no implementations to run")
    return descriptors


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Drive AWR/2 implementations through the SPEC.md section 17 CLI and record "
        "a per-vector conformance matrix"
    )
    parser.add_argument("--registry", default=REGISTRY_FILE, help="implementation descriptors (default: %(default)s)")
    parser.add_argument("--impl", action="append", metavar="NAME", help="only this implementation; repeatable")
    parser.add_argument(
        "--add-impl",
        action="append",
        metavar="JSON",
        help="a descriptor as JSON, for an implementation not in the registry; repeatable",
    )
    parser.add_argument("--only", metavar="SUBSTRING", help="only vectors whose id contains this")
    parser.add_argument("--markdown", action="store_true", help="print the matrix as markdown")
    parser.add_argument("--quiet", action="store_true", help="no per-vector progress on stderr")
    parser.add_argument(
        "--no-write",
        action="store_true",
        help="do not write results.json or badge.json (implied by --only, which measures a subset)",
    )
    args = parser.parse_args(list(sys.argv[1:] if argv is None else argv))

    with open(INDEX, "r", encoding="utf-8") as handle:
        manifest = json.load(handle)
    registry = load_spec_registry()

    if args.only:
        manifest = dict(manifest)
        manifest["vectors"] = [v for v in manifest["vectors"] if args.only in v["id"]]
        if not manifest["vectors"]:
            raise SystemExit("conformance: --only %r matched no vector" % (args.only,))

    descriptors = load_descriptors(args)
    implementations = [Implementation(d) for d in descriptors]

    sys.stderr.write(
        "AWR/2 conformance: %d vectors x %d implementation(s)\n"
        % (len(manifest["vectors"]), len(implementations))
    )
    sys.stderr.write("manifest: %s\nspec registry: %d codes\n\n" % (INDEX, len(registry)))

    started = time.time()
    runs = [run_implementation(impl, manifest, registry, args.quiet) for impl in implementations]
    elapsed = time.time() - started
    summary = summarise(manifest, runs)

    text = matrix_text(manifest, runs, summary, args.markdown)
    print(text)
    print("")
    if args.markdown:
        print("Generated by `awr/conformance/run.py`; %d vectors from `awr/vectors/index.json`."
              % (summary["vectorCount"],))
    else:
        print(
            "passed %d / measured %d, %d failed, %d not measured, in %.1fs"
            % (summary["passed"], summary["measured"], summary["failed"], summary["unsupportedPairs"], elapsed)
        )
        if args.only:
            print(
                "passed the %d vector(s) --only selected (NOT a conformance claim, which "
                "covers every vector in the manifest): %s"
                % (len(manifest["vectors"]), ", ".join(summary["conformant"]) or "none")
            )
        else:
            print(
                "conformant implementations (every vector in the manifest): %s"
                % (", ".join(summary["conformant"]) or "none",)
            )

    report = failure_report(runs)
    if report.strip():
        sys.stderr.write(report + "\n")

    partial = bool(args.only)
    if not args.no_write and not partial:
        results = {
            "$comment": [
                "REAL output of awr/conformance/run.py. Do not hand-edit: rerun it.",
                "Per implementation, per vector: pass | fail | unsupported. 'unsupported' means the "
                "measurement could not be taken (the implementation could not be driven, or an "
                "OPTIONAL section 17 subcommand is not provided) -- it never means a vector was "
                "waived, because a claimed conformance level covers every vector in the manifest.",
            ],
            "awrVersion": manifest.get("awrVersion"),
            "spec": "awr/SPEC.md",
            "manifest": "awr/vectors/index.json",
            "runner": "awr/conformance/run.py",
            "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "durationSeconds": round(elapsed, 2),
            "host": {"platform": sys.platform, "python": sys.version.split()[0]},
            "summary": summary,
            "implementations": runs,
        }
        with open(RESULTS_FILE, "w", encoding="utf-8") as handle:
            json.dump(results, handle, indent=2, sort_keys=False)
            handle.write("\n")
        with open(BADGE_FILE, "w", encoding="utf-8") as handle:
            json.dump(badge(summary), handle, indent=2)
            handle.write("\n")
        sys.stderr.write("\nwrote %s\nwrote %s\n" % (RESULTS_FILE, BADGE_FILE))
    elif partial:
        sys.stderr.write("\n--only measures a subset: results.json and badge.json NOT written\n")

    return 1 if summary["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
