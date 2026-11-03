"""A key is bytes. The alphabet it was written in is not part of its identity.

The spec uses standard base64 and so does this hub, but two of our own implementations —
the factory's AI-Market signer and the UNI bubble — published unpadded base64url. Python's
`base64.b64decode` does not reject `-`/`_`: with the default `validate=False` it *discards*
them and returns different bytes, so a good signature verified as garbage and the peer was
told its signature did not match its key. Found live on 2026-08-31, on our own factory.
"""

from __future__ import annotations

import base64
import pathlib
import tempfile

import pytest

from aimarket_hub.signing import Signer, decode_b64, same_key, signature_shape_problem


@pytest.fixture
def signer() -> Signer:
    return Signer(str(pathlib.Path(tempfile.mkdtemp()) / "key"))


def _urlsafe(standard_b64: str) -> str:
    return base64.urlsafe_b64encode(base64.b64decode(standard_b64)).decode().rstrip("=")


def test_a_urlsafe_signature_verifies(signer):
    canonical = "capabilities_count:1|generated_at:x|protocol_version:v1"
    value = signer.sign_canonical(canonical)
    assert signer.verify(signer.public_key_b64, value, canonical)
    assert signer.verify(_urlsafe(signer.public_key_b64), _urlsafe(value), canonical), (
        "the same key and signature in base64url must verify, not decode to garbage"
    )


def test_a_wrong_signature_still_fails_in_either_alphabet(signer):
    canonical = "capabilities_count:1|generated_at:x|protocol_version:v1"
    value = signer.sign_canonical(canonical)
    assert not signer.verify(signer.public_key_b64, value, canonical + "!")
    assert not signer.verify(_urlsafe(signer.public_key_b64), _urlsafe(value), canonical + "!")


def test_garbage_is_not_a_signature(signer):
    canonical = "anything"
    assert not signer.verify(signer.public_key_b64, "not base64 at all!!", canonical)
    assert not signer.verify("", signer.sign_canonical(canonical), canonical)


def test_decode_reads_both_alphabets_and_refuses_the_rest():
    raw = bytes(range(32))
    assert decode_b64(base64.b64encode(raw).decode()) == raw
    assert decode_b64(base64.urlsafe_b64encode(raw).decode().rstrip("=")) == raw
    assert decode_b64("") is None
    assert decode_b64("nope nope") is None


def test_the_same_key_in_two_alphabets_is_not_a_rotation(signer):
    assert same_key(signer.public_key_b64, _urlsafe(signer.public_key_b64))
    other = Signer(str(pathlib.Path(tempfile.mkdtemp()) / "key2"))
    assert not same_key(signer.public_key_b64, other.public_key_b64)
    assert not same_key(signer.public_key_b64, "")


# ── the shape around the bytes (spec §7.3.1) ────────────────────────────────────
# Both strangers who implemented the protocol themselves (agent-exec.448c.org, mach402.dev,
# October 2026) published the signature as a bare base64 string. Every verifier called
# `.get("value")` on it and raised; the assay died, its dossier froze, doctor printed a
# traceback. A wrong shape must be a refusal with a reason, on every path.


def _manifest(signer: Signer) -> dict:
    manifest = {"protocol_version": "v2", "generated_at": "2026-10-21T00:00:00Z",
                "capabilities_count": 1, "tools": [{"name": "t", "description": "d",
                                                    "input_schema": {"type": "object"}}]}
    manifest["signature"] = signer.sign_manifest(manifest)
    return manifest


def test_a_bare_string_signature_is_refused_not_raised(signer):
    manifest = _manifest(signer)
    assert signer.verify_manifest_signature(manifest, signer.public_key_b64)
    manifest["signature"] = manifest["signature"]["value"]   # the right bytes, the wrong shape
    assert signer.verify_manifest_signature(manifest, signer.public_key_b64) is False
    assert Signer.verify_object_signature({"a": 1, "signature": "abc"}, signer.public_key_b64) is False
    canonical = signer.manifest_canonical(manifest)
    for shape in ("abc", ["abc"], 7, True, {"algorithm": "ed25519"}, {"value": 7}):
        assert Signer.verify_hybrid(signer.public_key_b64, shape, canonical) is False


def test_a_non_string_is_not_base64():
    for value in (None, 7, ["a"], {"value": "a"}, b"AAAA"):
        assert decode_b64(value) is None


def test_the_shape_problem_says_how_to_fix_it():
    said = signature_shape_problem("f9bhOPZYAAMm5OUZR+NLyNZ3GSNKVzY8n5F3+04P")
    assert said.startswith("signature is a string, not an object")
    assert "§7.3.1" in said and '"algorithm": "ed25519"' in said and '"value"' in said
    assert "an array" in signature_shape_problem(["x"])
    assert "a number" in signature_shape_problem(3)
    assert '"value"' in signature_shape_problem({"algorithm": "ed25519"})
    assert signature_shape_problem({"algorithm": "ed25519", "value": "AAAA"}) == ""

