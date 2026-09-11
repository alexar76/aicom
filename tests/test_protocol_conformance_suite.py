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
