#!/usr/bin/env python3
"""Regenerate every example in this directory with the AWR/2 reference implementation.

DRAFT ON DISK.  Nothing here is sent, published or submitted anywhere.

    THIS SCRIPT IS AN AWR/2 ISSUER, AND ITS PRIVATE KEY IS PUBLIC.
    The seed is ``bytes(range(32))``, three lines of code below, so ANYONE can mint valid
    AWR/2 documents under this issuer's DID
    ``did:key:z6MkehRgf7yJbgaGfYsdoAsKdBPE3dj2CYhowQdcjqSJgvVd``.
    A document signed by that key is therefore evidence of NOTHING: not of adoption, not
    of a scan having been performed, not of anything about any server.  Every label this
    script writes says so inside its own signature (``mcpTrustLabel.demonstration``).
    The DID is declared in ``awr/adoption/metrics/own-keys.txt`` so that the adoption
    metric counts it as zero -- before that entry existed, the metric reported one
    "adopter", and the adopter was this file.

Run from the repository root::

    PYTHONPATH=awr/reference/python:awr/adoption/mcp-trust-label/tools \\
      .venv/bin/python awr/adoption/mcp-trust-label/examples/generate.py

Determinism: the signing key is derived from that fixed published seed and every timestamp
is fixed, so re-running reproduces the examples byte for byte.

The examples are genuinely signed and genuinely verify -- ``awr verify`` reports
``"valid": true`` on each of them.  No signature byte in this directory was written by hand.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, List

from awr import SigningKey, issue_verification_verdict, verify_document
from mtl_subject import build_descriptor, subject_reference, tool_set_digest

HERE = os.path.dirname(os.path.abspath(__file__))

MTL_CONTEXT = "https://verify.modelmarket.dev/ns/awr/mtl/v1"
LABEL_TYPE = "MCPTrustLabel"

# Demonstration key.  THE SEED IS PUBLISHED HERE, so the private key is public and anyone
# can sign under this DID.  Fixed so the examples are reproducible; it confers nothing.
SCANNER_SEED = bytes(range(32))

#: The DID the seed above derives.  Asserted at runtime rather than trusted, and declared
#: in awr/adoption/metrics/own-keys.txt so the adoption metric counts it as zero.
SCANNER_DID = "did:key:z6MkehRgf7yJbgaGfYsdoAsKdBPE3dj2CYhowQdcjqSJgvVd"

#: The name the labels carry.  SPEC §3.1 gives issuer.name no trust weight and PROFILE §9.1
#: forbids displaying it as identity -- it is here so that a human reading the raw JSON, or
#: an adoption report listing issuer names, cannot mistake this key for a real issuer.
ISSUER_NAME = "mtl-demo-scanner (DEMONSTRATION KEY — SEED PUBLISHED, NOT AN ADOPTER)"

#: Carried inside every label, inside the signature, as an ``mcpTrustLabel`` member.
#:
#: PROFILE §6.3 permits unknown members explicitly ("Unknown members MAY be present; a
#: registry MUST ignore them semantically and MUST NOT strip them") and SPEC §3.1/§4.2
#: require a verifier to preserve and canonicalize them, so this block is signed, travels
#: with the document, survives any conformant round-trip, and costs the document nothing:
#: the four labels still verify with ``valid=true``, profile L0, zero reasons and zero
#: warnings.  A registry that ignores it loses nothing; a human who reads the JSON, or any
#: tool that looks for the member, is told the key is worthless before reading further.
DEMONSTRATION = {
    "isDemonstration": True,
    "issuerPrivateKeyIsPublic": True,
    "issuerKeySeed": "bytes(range(32)), published in awr/adoption/mcp-trust-label/examples/generate.py",
    "warning": (
        "DEMONSTRATION DOCUMENT. The private key of this issuer is published, so anyone "
        "can mint documents under this DID and none of them means anything. This label is "
        "a format sample: it is not evidence of adoption, not evidence that any scan was "
        "performed, and not a statement about any real MCP server. The servers named in it "
        "are invented. MUST NOT be displayed as a trust signal or counted as adoption."
    ),
}

# A two-observation timeline: the first observation is what the continuity label later
# compares against.  All four timestamps are in the past so no AWR-TIME-001 warning fires.
FIRST_OBSERVED_AT = "2026-07-24T08:00:00Z"
FIRST_ISSUED_AT = "2026-07-24T08:05:00Z"
OBSERVED_AT = "2026-07-30T09:00:00Z"
ISSUED_AT = "2026-07-30T09:15:00Z"


def scanner_key() -> SigningKey:
    return SigningKey.from_seed(SCANNER_SEED)


# ---------------------------------------------------------------------------
# Fixture tool sets
# ---------------------------------------------------------------------------

#: A server with nothing for the pattern set to match.  Every field here is invented for the
#: example -- "com.example/weather" is not a real published MCP server.
CLEAN_TOOLS: List[Dict[str, Any]] = [
    {
        "name": "get_weather",
        "description": "Return the current weather for a city.",
        "inputSchema": {
            "type": "object",
            "properties": {"city": {"type": "string", "description": "City name."}},
            "required": ["city"],
        },
    },
    {
        "name": "list_cities",
        "description": "List the cities this server can report on.",
        "inputSchema": {"type": "object", "properties": {}},
    },
]

#: A server whose *benign* schema trips the pattern set: an ``api_key`` property and the
#: phrase "instead of".  Reproduced from the shipping ARGUS gate, which scores this tool set
#: 0.40 and, at the default blockAtSeverity="high", blocks it outright.  This is why MTL/1
#: never renders a pattern match as ``fail``.
PATTERN_HIT_TOOLS: List[Dict[str, Any]] = [
    {
        "name": "create_issue",
        "description": "Create a tracker issue. Requires a personal access token with repo scope.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo": {"type": "string"},
                "api_key": {"type": "string", "description": "Token used to authenticate."},
            },
            "required": ["repo", "api_key"],
        },
    },
    {
        "name": "list_files",
        "description": "List files in a directory. Returns names instead of full paths.",
        "inputSchema": {"type": "object", "properties": {"path": {"type": "string"}}},
    },
]


# ---------------------------------------------------------------------------
# The three static findings the ARGUS pattern set produces for PATTERN_HIT_TOOLS.
#
# These are literals: this generator does not execute the gate (it must run with nothing but
# the reference implementation on the path). The claim that they are what the gate actually
# emits is therefore checked elsewhere -- test_examples.py runs
# argus/dist/warden/static-scan.js over exactly these tool definitions with node and
# compares, and skips only if node or that build is absent. ``where`` uses the MTL field
# name ``inputSchema``; the gate's own message says "input schema".
# ---------------------------------------------------------------------------

PATTERN_HIT_FINDINGS = [
    {"code": "TOOL_DEF_SECRET_REQUEST", "severity": "high", "tool": "create_issue", "where": "description"},
    {"code": "TOOL_DEF_SECRET_REQUEST", "severity": "high", "tool": "create_issue", "where": "inputSchema"},
    {"code": "TOOL_DEF_INJECTION", "severity": "low", "tool": "list_files", "where": "description"},
]

#: Digest of the pattern set the scan ran under.  Computed over the extracted pattern table
#: so that two labels are only comparable when they name the same set (PROFILE.md 7.3).
PATTERN_SET_ID = "urn:awr:mtl:1:patternset:argus-warden-static-scan"


def pattern_set_digest() -> str:
    """SRI over the canonical form of the pattern table, as PROFILE.md 7.3 requires.

    The table is transcribed from argus/src/warden/static-scan.ts (22 patterns in four
    groups plus two heuristics).  Only the identity of the set matters for comparability,
    so the digest is taken over ``(group, source, flags, code, severity)`` tuples.
    """
    path = os.path.join(HERE, "pattern-set-argus-warden-static-scan.json")
    with open(path, "rb") as handle:
        table = json.loads(handle.read().decode("utf-8"))
    from awr import canonical_sri

    return canonical_sri(table)


# ---------------------------------------------------------------------------
# Label construction
# ---------------------------------------------------------------------------


def label(
    *,
    document_id: str,
    subject_ref: Dict[str, str],
    verdict: str,
    method_id: str,
    method_name: str,
    detail: Dict[str, Any],
    evidence: List[Dict[str, Any]],
    issued_at: str = ISSUED_AT,
) -> Dict[str, Any]:
    # The demonstration marker goes in every label, inside the signature. It is added here
    # rather than at each call site so that no example can be written without it.
    labelled = dict(detail)
    labelled["demonstration"] = DEMONSTRATION
    subject: Dict[str, Any] = {
        "verifiedWork": subject_ref,
        "verdict": verdict,
        "method": {"id": method_id, "name": method_name},
        "evidence": evidence,
        "mcpTrustLabel": labelled,
    }
    return issue_verification_verdict(
        subject,
        scanner_key(),
        document_id=document_id,
        valid_from=issued_at,
        created=issued_at,
        issuer_name=ISSUER_NAME,
        extra_types=[LABEL_TYPE],
        extra_context=[MTL_CONTEXT],
    )


def write(name: str, document: Dict[str, Any]) -> None:
    path = os.path.join(HERE, name)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(document, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    print("wrote %s" % (name,))


OWN_KEYS = os.path.normpath(os.path.join(HERE, "..", "..", "metrics", "own-keys.txt"))


def check_own_keys_declares_us(did: str) -> None:
    """Warn loudly if the adoption metric would count this demonstration key as an adopter.

    The binding check lives in ``awr/adoption/metrics/test_adoption_metric.py``; this is the
    same check where the issuer can see it. A published seed that is not declared makes the
    adoption number wrong in the flattering direction, which is the one direction nobody
    audits.
    """
    try:
        with open(OWN_KEYS, "r", encoding="utf-8") as handle:
            declared = did in handle.read()
    except OSError as exc:
        print("!! cannot read %s (%s): declare %s there or the adoption metric will count "
              "this demonstration key as an adopter" % (OWN_KEYS, exc, did))
        return
    if declared:
        print("own-keys: declared in %s -> the adoption metric counts this key as zero"
              % (os.path.relpath(OWN_KEYS, os.path.join(HERE, "..", "..", "..", "..")),))
    else:
        print("!! %s DOES NOT declare %s. The adoption metric will count these "
              "demonstration labels as a foreign adopter. Add it." % (OWN_KEYS, did))


def main() -> int:
    key = scanner_key()
    print("=" * 78)
    print("DEMONSTRATION ISSUER — the private key below is PUBLIC (seed bytes(range(32))).")
    print("Anyone can mint documents under this DID; none of them is evidence of anything.")
    print("=" * 78)
    print("issuer DID: %s" % (key.did,))
    if key.did != SCANNER_DID:  # pragma: no cover - would mean the key derivation changed
        print("!! derived DID %s does not match the documented %s" % (key.did, SCANNER_DID))
        return 1
    check_own_keys_declares_us(key.did)
    pattern_digest = pattern_set_digest()
    print("pattern-set digest: %s" % (pattern_digest,))

    written: List[str] = []

    # ---------------- example 1: pass ----------------
    descriptor, tool_sri, hazard = build_descriptor(
        server_name="com.example/weather",
        registry="urn:awr:mtl:1:registry:example",
        tools=CLEAN_TOOLS,
        server_version="1.4.2",
        transport="stdio",
        package="npm:@example/weather-mcp@1.4.2",
    )
    assert hazard is None, hazard
    ref = subject_reference(descriptor)
    print("pass subject:  %s" % (ref["digestSRI"],))
    write("pass-01-subject-descriptor.json", descriptor)
    written.append("pass-01-subject-descriptor.json")

    passing = label(
        document_id="urn:uuid:9f2c1d84-6b3a-4e51-8f07-2a5c9d1e4b60",
        subject_ref=ref,
        verdict="pass",
        method_id="urn:awr:mtl:1:method:tool-def-pattern-scan",
        method_name="MTL/1 tool-definition pattern scan (ARGUS WARDEN static-scan pattern set)",
        detail={
            "profile": "MTL/1",
            "observedAt": OBSERVED_AT,
            "reproducibility": "deterministic",
            "server": {"name": "com.example/weather", "registry": "urn:awr:mtl:1:registry:example"},
            "toolSet": {"count": 2, "digestSRI": tool_sri},
            "patternSet": {"id": PATTERN_SET_ID, "digestSRI": pattern_digest},
            "patternMatches": [],
            "scope": (
                "Pattern match over the tool names, descriptions and JSON schemas this "
                "server advertised at observedAt. No source code was read, no package was "
                "inspected, and no tool was invoked."
            ),
        },
        evidence=[
            {"kind": "mtl-subject-descriptor", "digestSRI": ref["digestSRI"]},
            {"kind": "mtl-tool-set", "digestSRI": tool_sri},
            {"kind": "mtl-pattern-set", "digestSRI": pattern_digest},
        ],
    )
    write("pass-01-pattern-scan.awr.json", passing)
    written.append("pass-01-pattern-scan.awr.json")

    # ---------------- example 2: inconclusive ----------------
    descriptor2, tool_sri2, hazard2 = build_descriptor(
        server_name="com.example/tracker",
        registry="urn:awr:mtl:1:registry:example",
        tools=PATTERN_HIT_TOOLS,
        server_version="0.9.0",
        transport="stdio",
        package="npm:@example/tracker-mcp@0.9.0",
    )
    assert hazard2 is None, hazard2
    ref2 = subject_reference(descriptor2)
    print("incl subject:  %s" % (ref2["digestSRI"],))
    write("inconclusive-01-subject-descriptor.json", descriptor2)
    written.append("inconclusive-01-subject-descriptor.json")

    inconclusive = label(
        document_id="urn:uuid:3d7be015-84c2-4f9a-b1e6-77c0af2d5839",
        subject_ref=ref2,
        verdict="inconclusive",
        method_id="urn:awr:mtl:1:method:tool-def-pattern-scan",
        method_name="MTL/1 tool-definition pattern scan (ARGUS WARDEN static-scan pattern set)",
        detail={
            "profile": "MTL/1",
            "observedAt": OBSERVED_AT,
            "reproducibility": "deterministic",
            "server": {"name": "com.example/tracker", "registry": "urn:awr:mtl:1:registry:example"},
            "toolSet": {"count": 2, "digestSRI": tool_sri2},
            "patternSet": {"id": PATTERN_SET_ID, "digestSRI": pattern_digest},
            "patternMatches": PATTERN_HIT_FINDINGS,
            "scope": (
                "Pattern match over the tool names, descriptions and JSON schemas this "
                "server advertised at observedAt. No source code was read, no package was "
                "inspected, and no tool was invoked."
            ),
            "note": (
                "A pattern match is a reason to read the definition, not a finding of fact. "
                "All three matches here are on benign text: a tool that legitimately takes "
                "an API key, and a description containing the words 'instead of'. MTL/1 "
                "therefore reports inconclusive and never fail for this method."
            ),
        },
        evidence=[
            {"kind": "mtl-subject-descriptor", "digestSRI": ref2["digestSRI"]},
            {"kind": "mtl-tool-set", "digestSRI": tool_sri2},
            {"kind": "mtl-pattern-set", "digestSRI": pattern_digest},
        ],
    )
    write("inconclusive-01-pattern-scan.awr.json", inconclusive)
    written.append("inconclusive-01-pattern-scan.awr.json")

    # ---------------- example 3: observation + continuity over the pass subject ----------
    observation = label(
        document_id="urn:uuid:c41f88a0-52d7-4b16-9e3f-0d6a7c8b2e14",
        subject_ref=ref,
        verdict="pass",
        method_id="urn:awr:mtl:1:method:tool-set-observation",
        method_name="MTL/1 tool-set observation",
        detail={
            "profile": "MTL/1",
            "observedAt": FIRST_OBSERVED_AT,
            "reproducibility": "deterministic",
            "server": {"name": "com.example/weather", "registry": "urn:awr:mtl:1:registry:example"},
            "toolSet": {"count": 2, "digestSRI": tool_sri},
            "scope": (
                "At observedAt this server advertised exactly the 2 tool definitions whose "
                "MTL/1 canonical digest is toolSet.digestSRI. Nothing else is claimed."
            ),
        },
        evidence=[
            {"kind": "mtl-subject-descriptor", "digestSRI": ref["digestSRI"]},
            {"kind": "mtl-tool-set", "digestSRI": tool_sri},
        ],
        issued_at=FIRST_ISSUED_AT,
    )
    write("pass-02-tool-set-observation.awr.json", observation)
    written.append("pass-02-tool-set-observation.awr.json")

    # A continuity label needs a prior label to compare against; the observation above plays
    # that role.  Same subject digest on both sides => no drift.
    from awr import canonical_sri

    prior_sri = canonical_sri(observation)
    continuity = label(
        document_id="urn:uuid:7a05e6c3-19bd-4a72-8c58-b3e91f240dda",
        subject_ref=ref,
        verdict="pass",
        method_id="urn:awr:mtl:1:method:tool-set-continuity",
        method_name="MTL/1 tool-set continuity",
        detail={
            "profile": "MTL/1",
            "observedAt": OBSERVED_AT,
            "reproducibility": "deterministic",
            "server": {"name": "com.example/weather", "registry": "urn:awr:mtl:1:registry:example"},
            "toolSet": {"count": 2, "digestSRI": tool_sri},
            "priorLabel": {
                "id": observation["id"],
                "digestSRI": prior_sri,
                "observedAt": FIRST_OBSERVED_AT,
            },
            "unchangedSince": FIRST_OBSERVED_AT,
            "scope": (
                "The subject digest observed now equals the subject digest of priorLabel. "
                "The advertised tool definitions have not changed between the two "
                "observations. This says nothing about the periods between them."
            ),
        },
        evidence=[
            {"kind": "mtl-subject-descriptor", "digestSRI": ref["digestSRI"]},
            {"kind": "mtl-prior-label", "id": observation["id"], "digestSRI": prior_sri},
        ],
    )
    write("pass-03-tool-set-continuity.awr.json", continuity)
    written.append("pass-03-tool-set-continuity.awr.json")

    # ---------------- verify everything we just wrote ----------------
    print("\n--- verification of every issued document ---")
    ok = True
    for name in written:
        if not name.endswith(".awr.json"):
            continue
        with open(os.path.join(HERE, name), "rb") as handle:
            doc = json.loads(handle.read().decode("utf-8"))
        result = verify_document(doc)
        flag = "OK " if result["valid"] else "BAD"
        ok = ok and bool(result["valid"])
        print(
            "%s %-42s valid=%s profile=%s reasons=%d warnings=%d"
            % (flag, name, result["valid"], result["profile"], len(result["reasons"]), len(result["warnings"]))
        )
        for entry in result["reasons"] + result["warnings"]:
            print("      %s %s: %s" % (entry["severity"], entry["code"], entry["detail"]))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
