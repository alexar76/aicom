"""Revocation/storage tests use newly generated disposable identities only."""

from __future__ import annotations

import base64
import hashlib
import importlib
import os
import stat
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_PATHS = (
    "aimarket-hub", "oracles/core", "platon/backend", "oracles/oracles/platon/backend",
    "aimarket-hub/plugins/aimarket-provenance", "awr/reference/python",
)
STORAGE_NAMES = (
    "security.signing_key_storage", "aimarket_hub._signing_key_storage",
    "oracle_core._signing_key_storage", "platon._signing_key_storage",
    "oracle_platon._signing_key_storage", "aimarket_provenance._signing_key_storage",
)
SIGNERS = ("aimarket_hub", "oracle_core", "platon", "oracle_platon")


@pytest.fixture(autouse=True)
def isolated_runtime(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path / "factory"))
    for name in (
        "PLATON_SIGNING_SEED_B64", "ORACLE_SIGNING_SEED_B64", "AIMARKET_SIGNING_KEY_PATH",
        "PLATON_SIGNING_KEY_PATH", "AIMARKET_PQC", "ORACLE_PQC", "PLATON_PQC_ENABLED",
    ):
        monkeypatch.delenv(name, raising=False)
    for relative in PACKAGE_PATHS:
        monkeypatch.syspath_prepend(str(ROOT / relative))


def generated_pair():
    key = Ed25519PrivateKey.generate()
    return key.private_bytes_raw() + key.public_key().public_bytes_raw()


@pytest.mark.parametrize("name", STORAGE_NAMES)
def test_all_standalone_storage_copies_match_canonical_source(name):
    module = importlib.import_module(name)
    assert Path(module.__file__).read_bytes() == (ROOT / "security/signing_key_storage.py").read_bytes()


@pytest.mark.parametrize("name", STORAGE_NAMES)
def test_new_private_identity_is_atomic_across_workers(name, tmp_path):
    module = importlib.import_module(name)
    path = tmp_path / "identity"
    previous = os.umask(0)
    try:
        with ThreadPoolExecutor(max_workers=12) as workers:
            pairs = list(workers.map(lambda _: module.load_or_create_ed25519_keypair(path), range(48)))
    finally:
        os.umask(previous)
    assert len(set(pairs)) == 1
    seed, public = pairs[0]
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert path.read_bytes() == seed + public
    assert list(tmp_path.iterdir()) == [path]
    signature = Ed25519PrivateKey.from_private_bytes(seed).sign(b"payment receipt")
    Ed25519PublicKey.from_public_bytes(public).verify(signature, b"payment receipt")


@pytest.mark.parametrize("name", STORAGE_NAMES)
def test_compromised_identity_refused_without_rotation_or_permissions_change(name, tmp_path, monkeypatch):
    module = importlib.import_module(name)
    raw = generated_pair()
    path = tmp_path / "identity"
    path.write_bytes(raw)
    path.chmod(0o644)
    monkeypatch.setattr(module, "COMPROMISED_PRIVATE_SHA256", frozenset({hashlib.sha256(raw).hexdigest()}))
    with pytest.raises(RuntimeError, match="Compromised Ed25519"):
        module.load_or_create_ed25519_keypair(path)
    assert path.read_bytes() == raw
    assert stat.S_IMODE(path.stat().st_mode) == 0o644
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.parametrize("name", STORAGE_NAMES)
def test_mismatched_private_public_halves_refused_without_replacement(name, tmp_path):
    module = importlib.import_module(name)
    raw = generated_pair()[:32] + generated_pair()[32:]
    path = tmp_path / "identity"
    path.write_bytes(raw)
    with pytest.raises(RuntimeError, match="does not match"):
        module.load_or_create_ed25519_keypair(path)
    assert path.read_bytes() == raw


@pytest.mark.parametrize("name", STORAGE_NAMES)
def test_linked_signing_file_refused_without_touching_target(name, tmp_path):
    module = importlib.import_module(name)
    outside = tmp_path / "outside"
    outside.write_bytes(generated_pair())
    before = outside.read_bytes()
    linked = tmp_path / "identity"
    linked.symlink_to(outside)
    with pytest.raises(RuntimeError):
        module.load_or_create_ed25519_keypair(linked)
    assert outside.read_bytes() == before
    linked.unlink()
    os.link(outside, linked)
    with pytest.raises(RuntimeError, match="hardlinks"):
        module.load_or_create_ed25519_keypair(linked)
    assert outside.read_bytes() == before


def signer_module(name, monkeypatch):
    module = importlib.import_module(name + ".signing")
    if "platon" in name:
        monkeypatch.setattr(module.settings, "pqc_enabled", False)
    return module


def make_signer(name, module, path):
    return module.Signer(path, pqc=False) if name in ("aimarket_hub", "oracle_core") else module.Signer(path)


def verify(name, signer, canonical, value):
    if name == "aimarket_hub":
        return signer.verify(signer.public_key_b64, value, canonical)
    return signer.verify(canonical, value, signer.public_key_b64)


@pytest.mark.parametrize("name", SIGNERS)
def test_real_signers_keep_valid_receipt_bytes_and_reject_tampering(name, tmp_path, monkeypatch):
    module = signer_module(name, monkeypatch)
    signer = make_signer(name, module, tmp_path / "identity")
    canonical = "nonce:receipt-1|price_usd:0.1|timestamp:2026-10-25T00:00:00Z"
    value = signer.sign_canonical(canonical)
    assert verify(name, signer, canonical, value)
    assert not verify(name, signer, canonical.replace("0.1", "9.1"), value)
    assert make_signer(name, module, tmp_path / "identity").public_key_b64 == signer.public_key_b64


@pytest.mark.parametrize("name", SIGNERS)
def test_signer_refuses_compromised_private_file(name, tmp_path, monkeypatch):
    module = signer_module(name, monkeypatch)
    storage = importlib.import_module(name + "._signing_key_storage")
    raw = generated_pair()
    path = tmp_path / "identity"
    path.write_bytes(raw)
    monkeypatch.setattr(storage, "COMPROMISED_PRIVATE_SHA256", frozenset({hashlib.sha256(raw).hexdigest()}))
    with pytest.raises(RuntimeError, match="Compromised Ed25519"):
        make_signer(name, module, path)
    assert path.read_bytes() == raw


@pytest.mark.parametrize("name", SIGNERS)
def test_valid_signature_from_compromised_public_identity_is_refused_even_if_pinned(name, tmp_path, monkeypatch):
    module = signer_module(name, monkeypatch)
    storage = importlib.import_module(name + "._signing_key_storage")
    signer = make_signer(name, module, tmp_path / "identity")
    value = signer.sign_canonical("receipt")
    public = base64.b64decode(signer.public_key_b64)
    assert verify(name, signer, "receipt", value)
    monkeypatch.setattr(storage, "COMPROMISED_PUBLIC_SHA256", frozenset({hashlib.sha256(public).hexdigest()}))
    assert not verify(name, signer, "receipt", value)


@pytest.mark.parametrize("name", ["oracle_core", "platon", "oracle_platon"])
def test_environment_seed_cannot_bypass_compromised_identity_guard(name, tmp_path, monkeypatch):
    module = signer_module(name, monkeypatch)
    storage = importlib.import_module(name + "._signing_key_storage")
    raw = generated_pair()
    monkeypatch.setattr(storage, "COMPROMISED_PRIVATE_SHA256", frozenset({hashlib.sha256(raw).hexdigest()}))
    env_name = "ORACLE_SIGNING_SEED_B64" if name == "oracle_core" else "PLATON_SIGNING_SEED_B64"
    monkeypatch.setenv(env_name, base64.b64encode(raw[:32]).decode())
    with pytest.raises(RuntimeError, match="Compromised Ed25519"):
        make_signer(name, module, tmp_path / "identity")
    assert not (tmp_path / "identity").exists()


def test_provenance_revocation_is_enforced_even_for_a_mathematically_valid_pinned_receipt(tmp_path, monkeypatch):
    from aimarket_hub.signing import Signer
    from aimarket_provenance import _signing_key_storage as storage
    from aimarket_provenance.receipt import ProvenanceReceipt
    from aimarket_provenance.verifier import verify_receipt

    signer = Signer(tmp_path / "identity", pqc=False)
    receipt = ProvenanceReceipt.create(
        model_id="disposable-model@test", provider_hub="https://hub.example",
        input_payload={"question": "test"}, output_payload={"result": "test"}, signer=signer,
    )
    assert verify_receipt(receipt).valid
    public = base64.b64decode(signer.public_key_b64)
    monkeypatch.setattr(storage, "COMPROMISED_PUBLIC_SHA256", frozenset({hashlib.sha256(public).hexdigest()}))
    result = verify_receipt(receipt, trusted_issuer_keys={receipt.issuer_id: signer.public_key_b64})
    assert not result.valid
    assert result.awr["valid"]  # Format validity is distinct from issuer trust.
    assert any("publicly exposed" in error for error in result.errors)


def test_provenance_key_adapter_refuses_compromised_cached_identity(tmp_path, monkeypatch):
    from aimarket_hub.signing import Signer
    from aimarket_provenance import _awr, _signing_key_storage as storage

    signer = Signer(tmp_path / "identity", pqc=False)
    _awr.signing_key_from_signer(signer)
    public = base64.b64decode(signer.public_key_b64)
    monkeypatch.setattr(storage, "COMPROMISED_PUBLIC_SHA256", frozenset({hashlib.sha256(public).hexdigest()}))
    with pytest.raises(_awr.ProvenanceKeyError, match="Compromised"):
        _awr.signing_key_from_signer(signer)


def test_pq_identity_is_private_stable_and_matching(tmp_path):
    from dilithium_py.ml_dsa import ML_DSA_65
    from security.signing_key_storage import load_or_create_mldsa_keypair

    path = tmp_path / "identity_mldsa"
    previous = os.umask(0)
    try:
        pair = load_or_create_mldsa_keypair(path, ML_DSA_65)
    finally:
        os.umask(previous)
    assert pair == load_or_create_mldsa_keypair(path, ML_DSA_65)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    other_public, _ = ML_DSA_65.keygen()
    payload = f"{other_public.hex()}\n{pair[1].hex()}\n"
    path.write_text(payload)
    with pytest.raises(RuntimeError, match="Invalid ML-DSA"):
        load_or_create_mldsa_keypair(path, ML_DSA_65)
    assert path.read_text() == payload


def test_factory_uni_loader_refuses_compromised_restoration_without_touching_file(tmp_path, monkeypatch):
    from core.ed25519_keys import load_or_create_ed25519_keypair
    from security import signing_key_storage

    raw = generated_pair()
    path = tmp_path / "identity"
    path.write_bytes(raw)
    path.chmod(0o644)
    monkeypatch.setattr(signing_key_storage, "COMPROMISED_PRIVATE_SHA256", frozenset({hashlib.sha256(raw).hexdigest()}))
    with pytest.raises(RuntimeError, match="Compromised"):
        load_or_create_ed25519_keypair(path)
    assert path.read_bytes() == raw
    assert stat.S_IMODE(path.stat().st_mode) == 0o644


def test_hub_announces_a_new_pq_identity_and_keeps_existing_identity_quiet(tmp_path, caplog):
    from aimarket_hub.signing import Signer

    path = tmp_path / "identity"
    first = Signer(path, pqc=True)
    assert "NEW post-quantum (ML-DSA-65) signing key generated" in caplog.text
    assert "Back it up together" in caplog.text
    caplog.clear()
    assert Signer(path, pqc=True).pq_public_key_b64 == first.pq_public_key_b64
    assert "NEW post-quantum" not in caplog.text
