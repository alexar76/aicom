"""Real asymmetric signatures, secret persistence and concurrent signer regressions."""

from __future__ import annotations

import base64
import builtins
import json
import os
import stat
from concurrent.futures import ThreadPoolExecutor

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from core.ed25519_keys import load_or_create_ed25519_keypair


def test_identity_first_use_is_atomic_across_workers(tmp_path):
    path = tmp_path / "identity.key"
    # All workers must pin exactly the same identity, even at first startup.
    with ThreadPoolExecutor(max_workers=16) as pool:
        pairs = list(pool.map(lambda _: load_or_create_ed25519_keypair(path), range(64)))
    assert len(set(pairs)) == 1
    seed, public = pairs[0]
    assert seed != public
    assert path.read_bytes() == seed + public
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert list(tmp_path.iterdir()) == [path]
    signature = Ed25519PrivateKey.from_private_bytes(seed).sign(b"settlement")
    Ed25519PublicKey.from_public_bytes(public).verify(signature, b"settlement")


@pytest.mark.parametrize("raw", [b"", b"short", b"x" * 64, b"x" * 65])
def test_invalid_existing_identity_never_silently_rotates(tmp_path, raw):
    path = tmp_path / "identity.key"
    path.write_bytes(raw)
    with pytest.raises(RuntimeError, match="Ed25519 identity"):
        load_or_create_ed25519_keypair(path)
    assert path.read_bytes() == raw


def test_legacy_key_keeps_the_existing_identity_and_permissions(tmp_path):
    legacy = tmp_path / "legacy.key"
    pair = load_or_create_ed25519_keypair(legacy)
    os.chmod(legacy, 0o644)
    path = tmp_path / "current.key"
    assert load_or_create_ed25519_keypair(path, legacy_path=legacy) == pair
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(legacy.stat().st_mode) == 0o600


def test_identity_symlink_is_refused_without_touching_target(tmp_path):
    target = tmp_path / "unrelated"
    target.write_bytes(b"unchanged")
    path = tmp_path / "identity.key"
    path.symlink_to(target)
    with pytest.raises(OSError):
        load_or_create_ed25519_keypair(path)
    assert target.read_bytes() == b"unchanged"


@pytest.mark.parametrize("module_name", ["core.uni.signing", "web.backend.services.ai_market_protocol.signing"])
def test_missing_crypto_never_publishes_a_seed_or_returns_an_hmac(tmp_path, monkeypatch, module_name):
    import importlib
    module = importlib.import_module(module_name)
    path = tmp_path / "identity.key"
    monkeypatch.setattr(module, "signing_key_path", lambda: path)
    original = builtins.__import__

    def no_ed25519(name, *args, **kwargs):
        if name == "cryptography.hazmat.primitives.asymmetric.ed25519":
            raise ImportError("simulated missing Ed25519 provider")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_ed25519)
    with pytest.raises(RuntimeError, match="requires cryptography"):
        module.public_key_b64()
    with pytest.raises(RuntimeError, match="requires cryptography"):
        module.sign_payload({"amount_uni": "500"})
    assert not path.exists()


def test_uni_verifies_with_public_crypto_without_signing(tmp_path, monkeypatch):
    from core.uni import signing
    from core.uni.receipts import canonical_receipt_payload, verify_receipt
    monkeypatch.setattr(signing, "signing_key_path", lambda: tmp_path / "uni.key")
    payload = {"id": "rcpt_security", "amount_uni": "500", "kind": "settlement"}
    value = signing.sign_payload(canonical_receipt_payload(payload))
    public = signing.public_key_b64()
    payload["signature"] = {"algorithm": "ed25519", "public_key": public, "value": value}
    Ed25519PublicKey.from_public_bytes(base64.urlsafe_b64decode(public + "==")).verify(
        base64.urlsafe_b64decode(value + "=="),
        json.dumps(canonical_receipt_payload(payload), sort_keys=True, separators=(",", ":")).encode(),
    )

    def signing_is_not_verification(*args):
        raise AssertionError("Verification must never create a signature")

    monkeypatch.setattr(signing, "sign_payload", signing_is_not_verification)
    assert verify_receipt(payload)
    for altered in (
        {**payload, "amount_uni": "501"},
        {**payload, "signature": {**payload["signature"], "algorithm": "hmac-sha256"}},
        {**payload, "signature": {**payload["signature"], "value": "!not-base64"}},
        {**payload, "signature": {**payload["signature"], "public_key": "other"}},
    ):
        assert not verify_receipt(altered)
