"""Tests over the shipped MTL/1 examples: honesty markers, spec conformance, drift.

What these assert, and why each one exists:

1. **The demonstration marker is in every label, inside the signature, and costs nothing.**
   The generator's private key is public (seed ``bytes(range(32))``), so the documents must
   say so themselves. PROFILE §6.3 permits unknown ``mcpTrustLabel`` members explicitly, so
   the marker is conformant -- and these tests prove it by re-verifying every shipped label
   and requiring ``valid``, profile ``L0``, zero reasons and zero warnings.
2. **The generator's DID is declared in the adoption metric's own-keys file.** It is an
   AWR/2 issuer in this repository; undeclared, it counts as an adopter, and the adopter is
   us. (The binding check is in ``awr/adoption/metrics/test_adoption_metric.py`` too; this
   one fails next to the issuer that causes it.)
3. **The subject digest is stable.** ``sha256-nNR6…`` is quoted in ``PROFILE.md`` §4.5,
   ``examples/README.md`` and ``registry-integration.md``. Anything that changes it makes
   three documents wrong at once.
4. **The transcribed pattern set has not drifted from the code it was transcribed from.**
   PROFILE §7.3 makes the pattern-set digest the thing that makes a scan label falsifiable;
   a digest over a hand copy binds to the copy, so the copy needs a test.
5. **The hardcoded pattern-scan findings are what the gate actually emits.** The generator
   cannot execute the gate (it runs with only the reference implementation on the path), so
   this test runs ``argus/dist/warden/static-scan.js`` with node and compares. It skips,
   loudly, when node or that build is absent -- a skip is honest, an unchecked literal is not.

Run with::

    PYTHONPATH=awr/reference/python:awr/adoption/mcp-trust-label/tools \\
      python3 -m pytest awr/adoption/mcp-trust-label/examples/test_examples.py -q
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.normpath(os.path.join(_HERE, "..", "..", "..", ".."))
_REFERENCE = os.path.join(_REPO, "awr", "reference", "python")
_TOOLS = os.path.normpath(os.path.join(_HERE, "..", "tools"))

for _path in (_HERE, _TOOLS, _REFERENCE):
    if _path not in sys.path:
        sys.path.insert(0, _path)

awr = pytest.importorskip("awr", reason="the AWR reference implementation is required")
pytest.importorskip("mtl_subject", reason="mtl_subject.py must be importable")

import generate  # noqa: E402

OWN_KEYS = os.path.join(_REPO, "awr", "adoption", "metrics", "own-keys.txt")
PATTERN_SET = os.path.join(_HERE, "pattern-set-argus-warden-static-scan.json")
STATIC_SCAN_TS = os.path.join(_REPO, "argus", "src", "warden", "static-scan.ts")
STATIC_SCAN_JS = os.path.join(_REPO, "argus", "dist", "warden", "static-scan.js")

LABELS = (
    "pass-01-pattern-scan.awr.json",
    "inconclusive-01-pattern-scan.awr.json",
    "pass-02-tool-set-observation.awr.json",
    "pass-03-tool-set-continuity.awr.json",
)

#: Quoted in PROFILE.md §4.5, examples/README.md and registry-integration.md.
PASS_SUBJECT_DIGEST = "sha256-nNR6utZJHl/EpVoffkzaYj4kA7LbJOig5Yz91lk6k1s="

NOW = "2026-07-31T12:00:00Z"


def load(name):
    with open(os.path.join(_HERE, name), "rb") as handle:
        return awr.loads(handle.read())


# ---------------------------------------------------------------------------
# 1. the demonstration marker, and that it costs the document nothing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", LABELS)
def test_every_label_verifies_with_the_demonstration_marker_present(name):
    result = awr.verify_document(load(name), now=NOW)
    assert result["valid"], result["reasons"]
    assert result["profile"] == "L0"
    assert result["reasons"] == []
    assert result["warnings"] == [], (
        "an unknown mcpTrustLabel member is permitted by PROFILE 6.3 and must not cost the "
        "document a single warning: %s" % (result["warnings"],)
    )


@pytest.mark.parametrize("name", LABELS)
def test_every_label_says_it_is_a_demonstration_inside_its_signature(name):
    document = load(name)
    marker = document["credentialSubject"]["mcpTrustLabel"]["demonstration"]
    assert marker["isDemonstration"] is True
    assert marker["issuerPrivateKeyIsPublic"] is True
    assert "bytes(range(32))" in marker["issuerKeySeed"]
    assert "not evidence of adoption" in marker["warning"]
    # The marker is inside credentialSubject, so it is inside the signature: flipping it
    # invalidates the document rather than editing a comment.
    tampered = json.loads(json.dumps(document))
    tampered["credentialSubject"]["mcpTrustLabel"]["demonstration"]["isDemonstration"] = False
    assert not awr.verify_document(tampered, now=NOW)["valid"]


@pytest.mark.parametrize("name", LABELS)
def test_the_issuer_name_cannot_be_mistaken_for_a_real_issuer(name):
    issuer = load(name)["issuer"]
    assert issuer["id"] == generate.SCANNER_DID
    assert "DEMONSTRATION KEY" in issuer["name"]
    assert "SEED PUBLISHED" in issuer["name"]


def test_the_documented_did_is_the_one_the_published_seed_derives():
    assert awr.SigningKey.from_seed(generate.SCANNER_SEED).did == generate.SCANNER_DID
    assert generate.SCANNER_SEED == bytes(range(32))


# ---------------------------------------------------------------------------
# 2. the adoption metric must not count us
# ---------------------------------------------------------------------------


def test_the_generator_did_is_declared_in_the_adoption_own_keys_file():
    assert os.path.isfile(OWN_KEYS), (
        "awr/adoption/metrics/own-keys.txt must be committed: this generator issues AWR/2 "
        "documents, and an undeclared issuer DID is counted as an adopter"
    )
    with open(OWN_KEYS, "r", encoding="utf-8") as handle:
        text = handle.read()
    declared = [
        line.split("#", 1)[0].strip()
        for line in text.splitlines()
        if line.split("#", 1)[0].strip()
    ]
    assert generate.SCANNER_DID in declared


# ---------------------------------------------------------------------------
# 3. the digest three documents quote
# ---------------------------------------------------------------------------


def test_the_pass_subject_digest_is_the_value_the_documents_quote():
    descriptor = load("pass-01-subject-descriptor.json")
    assert awr.canonical_sri(descriptor) == PASS_SUBJECT_DIGEST
    label = load("pass-01-pattern-scan.awr.json")
    assert label["credentialSubject"]["verifiedWork"]["digestSRI"] == PASS_SUBJECT_DIGEST


def test_the_pattern_set_digest_in_the_labels_matches_the_shipped_table():
    with open(PATTERN_SET, "rb") as handle:
        table = json.loads(handle.read().decode("utf-8"))
    expected = awr.canonical_sri(table)
    for name in ("pass-01-pattern-scan.awr.json", "inconclusive-01-pattern-scan.awr.json"):
        detail = load(name)["credentialSubject"]["mcpTrustLabel"]
        assert detail["patternSet"]["digestSRI"] == expected


# ---------------------------------------------------------------------------
# 4. drift: the transcription against the code it was transcribed from
# ---------------------------------------------------------------------------

_GROUP_NAMES = {
    "INJECTION_PATTERNS": "injection",
    "EXFIL_PATTERNS": "exfil",
    "SECRET_PATTERNS": "secret",
    "URL_SCHEME_PATTERNS": "url-scheme",
}


def _read_regex_literal(text, start):
    """Return ``(source, flags, end)`` for the JS regex literal beginning at ``text[start]``.

    Hand-rolled because a naive split on ``/`` breaks on ``https?:\\/\\//i`` and on ``/`` inside
    a character class -- exactly the two shapes this pattern table is full of.
    """
    assert text[start] == "/"
    index = start + 1
    in_class = False
    escaped = False
    while index < len(text):
        char = text[index]
        if escaped:
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == "[":
            in_class = True
        elif char == "]":
            in_class = False
        elif char == "/" and not in_class:
            break
        index += 1
    source = text[start + 1:index]
    flags_end = index + 1
    while flags_end < len(text) and text[flags_end].isalpha():
        flags_end += 1
    return source, text[index + 1:flags_end], flags_end


def extract_patterns_from_typescript(text):
    """Every ``{ re: /…/f, code: "…", severity: "…" }`` entry, with its group const name."""
    found = []
    for const_name, group in _GROUP_NAMES.items():
        match = re.search(
            r"const\s+%s\s*:\s*SignaturePattern\[\]\s*=\s*\[" % (const_name,), text
        )
        assert match, "%s not found in %s" % (const_name, STATIC_SCAN_TS)
        cursor = match.end()
        depth = 1
        block_start = cursor
        while cursor < len(text) and depth:
            if text[cursor] == "[":
                depth += 1
            elif text[cursor] == "]":
                depth -= 1
            cursor += 1
        block = text[block_start:cursor - 1]
        position = 0
        while True:
            entry = block.find("re:", position)
            if entry == -1:
                break
            slash = block.index("/", entry)
            source, flags, end = _read_regex_literal(block, slash)
            tail = block[end:block.index("}", end)]
            code = re.search(r'code:\s*"([^"]+)"', tail)
            severity = re.search(r'severity:\s*"([^"]+)"', tail)
            assert code and severity, tail
            found.append(
                {
                    "group": group,
                    "source": source,
                    "flags": flags,
                    "code": code.group(1),
                    "severity": severity.group(1),
                }
            )
            position = end
    return found


def test_the_transcribed_pattern_table_has_not_drifted_from_the_gate():
    if not os.path.isfile(STATIC_SCAN_TS):  # pragma: no cover - ARGUS ships in this repo
        pytest.skip("argus/src/warden/static-scan.ts is not present")
    with open(STATIC_SCAN_TS, "r", encoding="utf-8") as handle:
        source_text = handle.read()
    with open(PATTERN_SET, "r", encoding="utf-8") as handle:
        table = json.load(handle)

    from_code = extract_patterns_from_typescript(source_text)
    transcribed = [
        {k: entry[k] for k in ("group", "source", "flags", "code", "severity")}
        for entry in table["patterns"]
    ]

    assert len(from_code) == 22, "the gate no longer has 22 patterns: %d" % (len(from_code),)
    assert from_code == transcribed, (
        "pattern-set-argus-warden-static-scan.json is a hand transcription of "
        "argus/src/warden/static-scan.ts and has drifted from it. PROFILE 7.3 makes the "
        "pattern-set digest the thing that makes a scan label falsifiable, so a stale copy "
        "means every label naming this set names a set that was never run."
    )

    # The two heuristics are separate consts in the gate, not part of the arrays above.
    heuristics = {entry["code"]: entry["source"] for entry in table["heuristics"]}
    base64_source, _, _ = _read_regex_literal(
        source_text, source_text.index("/", source_text.index("const BASE64_BLOB"))
    )
    assert heuristics["TOOL_DEF_BASE64_BLOB"] == base64_source
    hidden = re.search(r'HIDDEN_UNICODE\s*=\s*new RegExp\("([^"]+)"\)', source_text)
    assert hidden, "HIDDEN_UNICODE not found"
    # Built from a JS *string* literal, so the pattern the engine compiles is the literal
    # with its backslash escapes collapsed. The table records the compiled source, the same
    # thing it records for every regex-literal entry.
    assert heuristics["TOOL_DEF_HIDDEN_UNICODE"] == hidden.group(1).replace("\\\\", "\\")
    assert table["scannedFields"] == ["description", "inputSchema"]


# ---------------------------------------------------------------------------
# 5. the hardcoded findings, checked by running the gate
# ---------------------------------------------------------------------------


def test_the_hardcoded_pattern_matches_are_what_the_gate_emits(tmp_path):
    node = shutil.which("node")
    if node is None:  # pragma: no cover - depends on the machine
        pytest.skip("node is not available, so the ARGUS gate cannot be executed here")
    if not os.path.isfile(STATIC_SCAN_JS):  # pragma: no cover - needs a built argus
        pytest.skip("argus/dist/warden/static-scan.js is not built")

    script = tmp_path / "run-gate.mjs"
    script.write_text(
        'import { StaticScanGate } from %s;\n'
        "const tools = JSON.parse(process.argv[2]);\n"
        "const result = await new StaticScanGate().evaluate({ tools });\n"
        "console.log(JSON.stringify(result));\n" % (json.dumps(STATIC_SCAN_JS),),
        encoding="utf-8",
    )
    proc = subprocess.run(
        [node, str(script), json.dumps(generate.PATTERN_HIT_TOOLS)],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)

    def triples(entries):
        return sorted((e["code"], e["severity"], e["tool"]) for e in entries)

    assert triples(result["findings"]) == triples(generate.PATTERN_HIT_FINDINGS), (
        "generate.py hardcodes the pattern matches it writes into the inconclusive label; "
        "the gate now emits something else: %s" % (result["findings"],)
    )
    # The 0.40 score and the "blocked at the default threshold" claim in examples/README.md
    # and PROFILE 8: same run, same numbers.
    assert result["score"] == pytest.approx(0.40)

    label = load("inconclusive-01-pattern-scan.awr.json")
    detail = label["credentialSubject"]["mcpTrustLabel"]
    assert detail["patternMatches"] == generate.PATTERN_HIT_FINDINGS
    assert label["credentialSubject"]["verdict"] == "inconclusive", (
        "PROFILE 7.3 forbids fail for this method: three matches on benign text are why"
    )
