"""Public-key revocation and private storage, with disposable generated material."""
from __future__ import annotations

import base64
import hashlib
import importlib
import os
import secrets
import stat
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parents[1]
STORAGE_NAMES = (
    "security.signing_key_storage", "aimarket_hub._signing_key_storage",
    "oracle_core._signing_key_storage", "platon._signing_key_storage",
    "oracle_platon._signing_key_storage", "aimarket_provenance._signing_key_storage",
    "sortes._signing_key_storage",
)


@pytest.fixture(autouse=True)
def isolated_runtime(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    for relative in (
        "aimarket-hub", "oracles/core", "oracles/oracles/sortes", "platon/backend",
        "oracles/oracles/platon/backend", "aimarket-hub/plugins/aimarket-provenance",
    ):
        monkeypatch.syspath_prepend(str(ROOT / relative))
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path / "factory"))
    monkeypatch.setenv("AIMARKET_DATASET_SALT_PATH", str(tmp_path / "import-salt"))
    monkeypatch.setenv("SORTES_VRF_SK_PATH", str(tmp_path / "vrf-key"))
    monkeypatch.delenv("AIMARKET_DATASET_SALT", raising=False)
    monkeypatch.delenv("SORTES_VRF_SK", raising=False)


@pytest.mark.parametrize("name", STORAGE_NAMES)
def test_all_standalone_helpers_revoke_new_public_uni_and_vrf_identities(name):
    module = importlib.import_module(name)
    assert Path(module.__file__).read_bytes() == (ROOT / "security/signing_key_storage.py").read_bytes()
    assert {
        "7623f31052756773e34f692b6f90a3cbe93d51d9666edb68473b0f56bfb1945b",
        "02c2c8322c51829a26b04b45e864a5df842e1efc1bf6abf361d6002b9aeca448",
        "dc7ea68d59012eb84f09d6982c06263a6b563d511ba34054b88656c9d4fcd555",
    } <= module.COMPROMISED_PRIVATE_SHA256
    assert {
        "59e06ad12bdfe6c691668b63f4a7c5a20f62c5c3b7ff9564d3601abf6b2df304",
        "933590d1e764af4a81c2350d2c8d88d39c6a0107ee707c006007a2520aa02024",
    } <= module.COMPROMISED_PUBLIC_SHA256


def test_independent_sortes_supports_old_core_without_private_helper_or_crypto_packages(tmp_path):
    # Simulate the smallest previously allowed oracle-core public interface.
    # -I -S ensures neither this checkout nor installed dependencies fill its gaps.
    old_core = tmp_path / "legacy" / "oracle_core"
    old_core.mkdir(parents=True)
    (old_core / "__init__.py").write_text(
        "class Capability:\n"
        "    def __init__(self, **values): self.__dict__.update(values)\n"
        "class OracleSpec(Capability): pass\n"
    )
    result = subprocess.run([
        sys.executable, "-I", "-S", "-c",
        "import sys, secrets; "
        "sys.path[:0] = sys.argv[1:3]; "
        "import oracle_core; "
        "assert not hasattr(oracle_core, '_signing_key_storage'); "
        "from sortes import vrf; "
        "seed = secrets.token_bytes(32); public = vrf.sk_to_pk(seed); "
        "proof = vrf.prove(seed, b'independent import'); "
        "assert vrf.verify(public, b'independent import', proof) is not None; "
        "assert vrf.verify(public, b'changed', proof) is None; "
        "from sortes import capabilities; "
        "draw = capabilities._draw({'alpha': 'independent import'}); "
        "assert capabilities._verify(draw)['valid']; "
        "assert 'oracle_core._signing_key_storage' not in sys.modules; "
        "assert 'cryptography' not in sys.modules",
        str(old_core.parent), str(ROOT / "oracles/oracles/sortes"),
    ], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr


def test_uni_receipt_signing_and_trust_pin_refuse_compromised_identity(monkeypatch, tmp_path):
    from core.uni import receipts, signing
    from security import signing_key_storage as storage
    key = Ed25519PrivateKey.generate()
    public = key.public_key().public_bytes_raw()
    raw = key.private_bytes_raw() + public
    path = tmp_path / "uni-key"
    path.write_bytes(raw)
    monkeypatch.setattr(signing, "signing_key_path", lambda: path)
    payload = {"kind": "grant", "amount_uni": "42", "receipt_id": "disposable-receipt"}
    signature = signing.sign_payload(receipts.canonical_receipt_payload(payload))
    payload["signature"] = {"algorithm": "ed25519", "public_key": signing.public_key_b64(), "value": signature}
    assert receipts.verify_receipt(payload)
    assert not receipts.verify_receipt(dict(payload, amount_uni="43"))
    monkeypatch.setattr(storage, "COMPROMISED_PUBLIC_SHA256", frozenset({hashlib.sha256(public).hexdigest()}))
    # Even a mathematically valid signature under an explicitly matching trust pin is revoked.
    monkeypatch.setattr(signing, "public_key_b64", lambda: base64.urlsafe_b64encode(public).decode().rstrip("="))
    assert not receipts.verify_receipt(payload)
    with pytest.raises(RuntimeError, match="Compromised"):
        signing.sign_payload({"amount_uni": "42"})
    assert path.read_bytes() == raw


def test_uni_legacy_restoration_is_rejected_without_publishing_replacement(monkeypatch, tmp_path):
    from core.ed25519_keys import load_or_create_ed25519_keypair
    from security import signing_key_storage as storage
    key = Ed25519PrivateKey.generate()
    raw = key.private_bytes_raw() + key.public_key().public_bytes_raw()
    legacy = tmp_path / "legacy"
    legacy.write_bytes(raw)
    legacy.chmod(0o644)
    monkeypatch.setattr(storage, "COMPROMISED_PRIVATE_SHA256", frozenset({hashlib.sha256(raw).hexdigest()}))
    with pytest.raises(RuntimeError, match="Compromised"):
        load_or_create_ed25519_keypair(tmp_path / "new", legacy_path=legacy)
    assert legacy.read_bytes() == raw and stat.S_IMODE(legacy.stat().st_mode) == 0o644
    assert not (tmp_path / "new").exists()


def test_uni_hardlinked_identity_is_refused_before_changing_the_external_inode(tmp_path):
    from core.ed25519_keys import load_or_create_ed25519_keypair
    key = Ed25519PrivateKey.generate()
    raw = key.private_bytes_raw() + key.public_key().public_bytes_raw()
    external, path = tmp_path / "external", tmp_path / "uni-key"
    external.write_bytes(raw)
    external.chmod(0o644)
    os.link(external, path)
    with pytest.raises(RuntimeError, match="hardlinks"):
        load_or_create_ed25519_keypair(path)
    assert external.read_bytes() == raw and stat.S_IMODE(external.stat().st_mode) == 0o644


def test_uni_fifo_identity_is_refused_without_waiting_for_a_writer(tmp_path):
    path = tmp_path / "uni-fifo"
    os.mkfifo(path)
    result = subprocess.run([
        sys.executable, "-c",
        "from pathlib import Path; import sys; from core.ed25519_keys import load_or_create_ed25519_keypair; "
        "load_or_create_ed25519_keypair(Path(sys.argv[1]))", str(path),
    ], env=dict(os.environ, PYTHONPATH=str(ROOT)), capture_output=True, text=True, timeout=5)
    assert result.returncode != 0 and "regular file" in result.stderr
    assert stat.S_ISFIFO(path.lstat().st_mode)


@pytest.mark.parametrize("source", ["file", "env", "cached_prover"])
def test_vrf_compromised_seed_is_refused_without_rotation(source, monkeypatch, tmp_path):
    from sortes import capabilities, vrf
    from sortes import _signing_key_storage as storage
    seed = secrets.token_bytes(32)
    path = tmp_path / "vrf-key"
    if source == "file":
        path.write_text(seed.hex())
        path.chmod(0o644)
    elif source == "env":
        monkeypatch.setenv("SORTES_VRF_SK", seed.hex())
    else:
        monkeypatch.setattr(capabilities, "_SK", seed)
        monkeypatch.setattr(capabilities, "_PK", vrf.sk_to_pk(seed))
    monkeypatch.setattr(storage, "COMPROMISED_PRIVATE_SHA256", frozenset({hashlib.sha256(seed).hexdigest()}))
    with pytest.raises(RuntimeError, match="Compromised"):
        capabilities._draw({"alpha": "disposable challenge"}) if source == "cached_prover" else capabilities._load_or_create_sk()
    if source == "file":
        assert path.read_text() == seed.hex() and stat.S_IMODE(path.stat().st_mode) == 0o644


def test_vrf_real_proof_and_offline_verifier_reject_revoked_public_key(monkeypatch):
    from sortes import capabilities, vrf
    from sortes import _signing_key_storage as storage
    seed = secrets.token_bytes(32)
    public = vrf.sk_to_pk(seed)
    proof = vrf.prove(seed, b"draw challenge")
    assert vrf.verify(public, b"draw challenge", proof) is not None
    assert vrf.verify(public, b"tampered challenge", proof) is None
    monkeypatch.setattr(storage, "COMPROMISED_PUBLIC_SHA256", frozenset({hashlib.sha256(public).hexdigest()}))
    assert vrf.verify(public, b"draw challenge", proof) is None
    assert not capabilities._verify({"public_key": public.hex(), "pi": proof.hex(), "alpha": "draw challenge"})["valid"]


def salt_module(monkeypatch, tmp_path):
    from aimarket_hub import dataset_exporter
    monkeypatch.setattr(dataset_exporter, "_SALT_FILE", tmp_path / "salt")
    return dataset_exporter


@pytest.mark.parametrize("source", ["file", "env"])
def test_published_dataset_salt_requires_explicit_recovery(source, monkeypatch, tmp_path):
    module = salt_module(monkeypatch, tmp_path)
    salt = ("disposable-salt-" + secrets.token_hex(16)).encode()
    monkeypatch.setattr(module, "COMPROMISED_SALT_SHA256", frozenset({hashlib.sha256(salt).hexdigest()}))
    if source == "env":
        monkeypatch.setenv("AIMARKET_DATASET_SALT", salt.decode())
    else:
        module._SALT_FILE.write_bytes(salt)
        module._SALT_FILE.chmod(0o644)
    with pytest.raises(RuntimeError, match="publicly exposed"):
        module._load_or_create_salt()
    if source == "file":
        assert module._SALT_FILE.read_bytes() == salt
        assert stat.S_IMODE(module._SALT_FILE.stat().st_mode) == 0o644
    else:
        assert not module._SALT_FILE.exists()


@pytest.mark.parametrize("kind", ["vrf", "salt"])
def test_first_write_is_complete_private_and_stable_under_concurrent_restart(kind, monkeypatch, tmp_path):
    if kind == "vrf":
        from sortes.capabilities import _load_or_create_sk as load
        # Import creates its initial identity; exercise a separate empty destination.
        path = tmp_path / "concurrent-vrf-key"
        monkeypatch.setenv("SORTES_VRF_SK_PATH", str(path))
    else:
        module = salt_module(monkeypatch, tmp_path)
        load, path = module._load_or_create_salt, module._SALT_FILE
    old_umask = os.umask(0)
    try:
        with ThreadPoolExecutor(max_workers=8) as executor:
            values = list(executor.map(lambda _: load(), range(24)))
    finally:
        os.umask(old_umask)
    assert len(set(values)) == 1 and len(values[0]) == 32
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert (bytes.fromhex(path.read_text()) if kind == "vrf" else path.read_bytes()) == values[0]
    assert load() == values[0]
    if kind == "salt":
        monkeypatch.setattr(module, "_SALT", values[0])
        anonymized = module._anonymize_id("same-product")
        assert module._anonymize_id("other-product") != module._anonymize_id("same-product")
        monkeypatch.setenv("AIMARKET_DATASET_SALT_PATH", str(path))
        assert importlib.reload(module)._anonymize_id("same-product") == anonymized


@pytest.mark.parametrize("kind", ["vrf", "salt"])
@pytest.mark.parametrize("unsafe", ["symlink", "hardlink", "empty"])
def test_unsafe_or_malformed_private_files_are_never_replaced(kind, unsafe, monkeypatch, tmp_path):
    if kind == "vrf":
        from sortes.capabilities import _load_or_create_sk as load
        path, content = tmp_path / "unsafe-vrf", secrets.token_bytes(32).hex().encode()
        monkeypatch.setenv("SORTES_VRF_SK_PATH", str(path))
    else:
        module = salt_module(monkeypatch, tmp_path)
        load, path, content = module._load_or_create_salt, module._SALT_FILE, secrets.token_bytes(32)
    target = tmp_path / "outside"
    target.write_bytes(content)
    target.chmod(0o644)
    if unsafe == "symlink":
        path.symlink_to(target)
    elif unsafe == "hardlink":
        os.link(target, path)
    else:
        path.touch()
    with pytest.raises(RuntimeError):
        load()
    assert target.read_bytes() == content and stat.S_IMODE(target.stat().st_mode) == 0o644
    if unsafe == "empty":
        assert path.read_bytes() == b""
