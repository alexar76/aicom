"""The conformance suite must stay honest: positives verify, negatives are rejected.

A conformance runner that passes everything is worse than none, because it is believed. The
tests here check the runner itself — that it exits non-zero when a negative vector is made
to pass, and that the documented canonicals still match the vectors they describe.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PROTO = ROOT / "aimarket-protocol"
RUNNER = PROTO / "conformance" / "run.py"
VECTORS = PROTO / "test-vectors"

pytestmark = pytest.mark.skipif(
    not RUNNER.exists(), reason="protocol repo not present in this checkout"
)


def _has_crypto() -> bool:
    try:
        import cryptography  # noqa: F401
        return True
    except ImportError:
        return False


needs_crypto = pytest.mark.skipif(not _has_crypto(), reason="cryptography>=44 not installed")


@needs_crypto
def test_conformance_suite_passes_on_a_clean_checkout():
    proc = subprocess.run(
        [sys.executable, str(RUNNER)], capture_output=True, text=True, cwd=str(PROTO)
    )
    assert proc.returncode == 0, f"conformance failed:\n{proc.stdout}\n{proc.stderr}"
    assert "FAIL" not in proc.stdout
    # Both halves must actually run — a suite that silently checked nothing would also pass.
    assert "Positive vectors" in proc.stdout and "Negative vectors" in proc.stdout


@needs_crypto
def test_every_negative_vector_is_actually_negative():
    """If a 'negative' vector verifies, the suite is decorative.

    Checked by running the real runner over a copy of the tree in which one negative vector
    has been replaced by a valid positive one. The runner must notice.
    """
    negatives = sorted((VECTORS / "negative").glob("*.json"))
    assert negatives, "no negative vectors — generate them with test-vectors/generate_negative.py"

    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "protocol"
        shutil.copytree(PROTO, copy, ignore=shutil.ignore_patterns(".git", "node_modules"))
        # Smuggle a genuinely valid receipt in under a negative vector's name.
        good = json.loads((VECTORS / "receipt-signed.json").read_text(encoding="utf-8"))
        good["_expect"] = {"result": "reject", "reason": "signature-invalid"}
        (copy / "test-vectors" / "negative" / "receipt-flipped-success.json").write_text(
            json.dumps(good, indent=2), encoding="utf-8"
        )
        proc = subprocess.run(
            [sys.executable, str(copy / "conformance" / "run.py")],
            capture_output=True, text=True, cwd=str(copy),
        )
        assert proc.returncode != 0, (
            "a valid document placed among the negative vectors was accepted — "
            "the suite does not actually test rejection"
        )
        assert "ACCEPTED" in proc.stdout


@needs_crypto
def test_spec_canonical_matches_the_shipped_vector():
    """§7.3.2's formula, applied literally, must verify the manifest vector.

    This is the drift guard for the section: the canonical previously lived only in source,
    and the published documentation drifted to a shape that could not verify anything.
    """
    import base64
    import hashlib

    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    m = json.loads((VECTORS / "manifest-signed.json").read_text(encoding="utf-8"))

    def digest(value):
        return hashlib.sha256(
            json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()

    canonical = (
        f"capabilities_count:{m.get('capabilities_count', 0)}"
        f"|generated_at:{m.get('generated_at', '')}"
        f"|protocol_version:{m.get('protocol_version', 'v1')}"
        f"|tools_hash:{digest(m.get('tools', []))}"
        f"|by_hub_hash:{digest(m.get('by_hub', {}))}"
    )
    Ed25519PublicKey.from_public_bytes(
        base64.b64decode("11qYAYKxCrfVS/7TyWQHOg7hcvPapiMlrwIaaPcHURo=")
    ).verify(base64.b64decode(m["signature"]["value"]), canonical.encode())

    spec = (PROTO / "spec.md").read_text(encoding="utf-8")
    heading = "#### 7.3.2. Manifest canonical (five fields)"
    assert heading in spec
    # Anchor on the HEADING, not the bare string "7.3.2" — cross-references to the section
    # appear earlier in the document and split() would land in one of those instead.
    section = spec.split(heading, 1)[1].split("\n#### ", 1)[0]
    for field in ("tools_hash", "by_hub_hash", "capabilities_count", "generated_at", "protocol_version"):
        assert field in section, f"{field} missing from the specified canonical"

    v2_heading = "#### 7.3.4. Receipt canonical v2"
    assert v2_heading in spec
    v2_section = spec.split(v2_heading, 1)[1].split("\n### ", 1)[0]
    assert "sort_keys" in v2_section and "null" in v2_section, (
        "§7.3.4 must state the sorting and the absent-binds-as-null rule"
    )
    assert "in this order" not in v2_section, (
        "the digest is key-sorted; documenting a fixed order contradicts sort_keys"
    )


def test_vectors_readme_does_not_publish_the_superseded_canonical():
    """The README once taught a three-field canonical that verifies nothing.

    Anyone implementing from it could not succeed, and anyone working around the failure by
    dropping the digests would build a verifier a relay can walk straight through.
    """
    readme = (VECTORS / "README.md").read_text(encoding="utf-8")
    for line in readme.splitlines():
        if "capabilities_count:" in line and "|generated_at:" in line:
            assert "tools_hash" in line and "by_hub_hash" in line, (
                f"README publishes a canonical without the content digests:\n  {line[:120]}"
            )


def _load_runner():
    import importlib.util

    spec = importlib.util.spec_from_file_location("aimarket_conformance_run", RUNNER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_live_check_names_a_bare_string_signature(monkeypatch):
    """mach402.dev, 2026-10-21: the runner's whole answer was "'str' object has no attribute
    'get'". The implementer must read which shape to publish instead."""
    import urllib.error

    run = _load_runner()
    base = "https://peer.example"
    well_known = {"name": "peer", "protocol_versions": ["v1", "v2"],
                  "manifest_url": f"{base}/ai-market/v2/manifest",
                  "signer_public_key": "UGIZ0yVMpsAQBS1sLPq782GBjL5HnJZdI7SVrOQ3Xo4="}
    manifest = {"protocol_version": "v2", "generated_at": "2026-10-21T00:00:00Z", "tools": [],
                "signature": "f9bhOPZYAAMm5OUZR+NLyNZ3GSNKVzY8n5F3+04P"}

    def fetch(url, timeout=15.0):
        if url.endswith("/.well-known/ai-market.json"):
            return 200, well_known
        if url == well_known["manifest_url"]:
            return 200, manifest
        raise urllib.error.HTTPError(url, 404, "Not Found", None, None)

    monkeypatch.setattr(run, "fetch", fetch)
    run.results.clear()
    run.check_live_hub(base)
    failed = {name: detail for ok, name, detail in run.results if not ok}
    assert "not an object (§7.3.1)" in failed["live manifest signature is a §7.3.1 object"]
    assert not any("has no attribute" in detail for detail in failed.values())


def test_signature_examples_are_objects():
    """Two independent implementations copied `"signature": "..."` from the examples and
    published a bare string. Every signature in the protocol is a §7.3.1 object."""
    for doc in (PROTO / "spec.md", ROOT / "docs" / "ai-market-protocol-v1.md"):
        if not doc.exists():
            continue
        for number, line in enumerate(doc.read_text(encoding="utf-8").splitlines(), 1):
            assert '"signature": "' not in line, f"{doc.name}:{number} shows a string signature"
