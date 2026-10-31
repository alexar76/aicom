"""The export guard recognizes real key encodings without printing their values."""

from __future__ import annotations

import hashlib
import base64
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import BestAvailableEncryption, Encoding, NoEncryption, PrivateFormat, PublicFormat
import pytest


SCRIPT = Path(__file__).parents[1] / "scripts" / "verify_structured_secrets.py"
_SPEC = importlib.util.spec_from_file_location("structured_secret_guard", SCRIPT)
guard = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = guard
_SPEC.loader.exec_module(guard)


def _pair() -> bytes:
    private = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
    return bytes(range(32)) + private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)


def _git(root: Path, *arguments: str) -> None:
    # A caller/test fixture may poison Git's repository selectors. Never let
    # temporary-repository tests stage the shared workspace by inheritance.
    environment = {
        "PATH": "/usr/bin:/bin", "HOME": str(root), "XDG_CONFIG_HOME": str(root),
        "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_SYSTEM": "/dev/null",
        "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_TERMINAL_PROMPT": "0",
        "GIT_ALLOW_PROTOCOL": "", "LC_ALL": "C",
    }
    subprocess.run(["/usr/bin/git", "-C", str(root), *arguments],
                   env=environment, check=True, capture_output=True)


def _run(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(SCRIPT), str(root)], text=True, capture_output=True)


def test_solana_keypair_is_detected_even_when_ignored_but_already_staged(tmp_path):
    raw = _pair()
    path = tmp_path / "wallet.json"
    path.write_text(json.dumps(list(raw)))
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "add", "wallet.json")
    (tmp_path / ".gitignore").write_text("wallet.json\n")
    result = _run(tmp_path)
    assert result.returncode == 1
    row = json.loads(result.stdout)["structured_secret_findings"][0]
    assert row == {"path": "wallet.json", "kind": "solana-json-keypair", "sha256": hashlib.sha256(raw).hexdigest()}
    assert path.read_text() not in result.stdout + result.stderr


@pytest.mark.parametrize("field", ["private_key", '"privateKey"', "'secret_key'", "signing_seed", "PRIVATE_KEY"])
def test_quoted_lowercase_private_key_fields_are_detected_without_values(tmp_path, field):
    secret = "deadbeef" * 8
    (tmp_path / "settings.toml").write_text(f'{field} = "0x{secret}"\n')
    result = _run(tmp_path)
    assert result.returncode == 1
    assert "hex-private-key-field" in result.stdout
    assert secret not in result.stdout + result.stderr


def test_real_raw_keypair_and_named_private_seed_are_detected(tmp_path):
    (tmp_path / "innocuous_blob").write_bytes(_pair())
    (tmp_path / "private_seed.bin").write_bytes(bytes(range(32)))
    rows = guard.scan(tmp_path)
    assert {(r.path, r.kind) for r in rows} == {
        ("innocuous_blob", "raw-ed25519-keypair"),
        ("private_seed.bin", "named-private-seed"),
    }


def test_binary_and_pem_pkcs8_private_keys_are_detected(tmp_path):
    private = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
    (tmp_path / "document.bin").write_bytes(private.private_bytes(Encoding.DER, PrivateFormat.PKCS8, NoEncryption()))
    (tmp_path / "document.txt").write_bytes(private.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()))
    assert {(r.path, r.kind) for r in guard.scan(tmp_path)} == {
        ("document.bin", "der-private-key"), ("document.txt", "pem-private-key")
    }


def test_encrypted_der_private_key_is_still_private_material(tmp_path):
    private = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
    (tmp_path / "document.bin").write_bytes(private.private_bytes(
        Encoding.DER, PrivateFormat.PKCS8, BestAvailableEncryption(b"synthetic-test-password")
    ))
    assert [(r.path, r.kind) for r in guard.scan(tmp_path)] == [("document.bin", "der-private-key")]


def test_private_host_failure_reports_paths_without_values(tmp_path):
    import os

    target = tmp_path / "deploy/has spaces/settings.txt"
    target.parent.mkdir(parents=True)
    target.write_text("connect=https://private-canary.invalid:9090/sensitive-path\n")
    result = subprocess.run(
        ["bash", str(SCRIPT.with_name("verify_mirror_secrets.sh")), str(tmp_path)],
        env={**os.environ, "MIRROR_FORBIDDEN_HOSTS": "private-canary.invalid"},
        capture_output=True, text=True,
    )
    output = result.stdout + result.stderr
    assert result.returncode != 0
    assert "private server IP/hostname literal" in output
    assert 'file: "deploy/has spaces/settings.txt"' in output
    assert "private-canary.invalid" not in output
    assert "sensitive-path" not in output


def test_mirror_rejects_internal_host_policy_even_with_different_external_policy(tmp_path):
    import os

    target = tmp_path / "scripts/.mirror-forbidden-hosts"
    target.parent.mkdir()
    target.write_text("internal-policy-only.invalid\n")
    result = subprocess.run(
        ["bash", str(SCRIPT.with_name("verify_mirror_secrets.sh")), str(tmp_path)],
        env={**os.environ, "MIRROR_FORBIDDEN_HOSTS": "different-canary.invalid"},
        capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert "internal private-host policy file" in result.stderr
    assert "internal-policy-only.invalid" not in result.stdout + result.stderr


def test_public_key_signature_and_public_hex_vectors_are_allowed(tmp_path):
    public = _pair()[32:]
    private = Ed25519PrivateKey.from_private_bytes(_pair()[:32])
    signature = private.sign(b"public protocol vector")
    (tmp_path / "public.bin").write_bytes(public)
    (tmp_path / "signature.json").write_text(json.dumps(list(signature)))
    (tmp_path / "public.json").write_text(json.dumps({"publicKey": public.hex(), "input_sha256": "ab" * 32}))
    assert guard.scan(tmp_path) == []


def test_embedded_multiline_json_keypair_is_detected_across_chunk_boundary(tmp_path):
    text = " " * (guard._CHUNK_SIZE - 50) + json.dumps({"secretKey": list(_pair())}, indent=2)
    (tmp_path / "nested.json").write_text(text)
    rows = guard.scan(tmp_path)
    assert [(r.path, r.kind) for r in rows] == [("nested.json", "solana-json-keypair")]


def test_valid_64_integer_public_vectors_do_not_become_keys(tmp_path):
    (tmp_path / "vector.json").write_text(json.dumps(list(range(64))))
    (tmp_path / "out_of_range.json").write_text(json.dumps([999] * 64))
    assert guard.scan(tmp_path) == []


def test_test_directory_and_ignore_comment_cannot_exempt_real_key(tmp_path):
    fixtures = tmp_path / "tests" / "fixtures"
    fixtures.mkdir(parents=True)
    (fixtures / "wallet.json").write_text("# gitleaks:allow\n" + json.dumps(list(_pair())))
    assert guard.scan(tmp_path)[0].kind == "solana-json-keypair"


def test_missing_verifier_dependency_fails_closed_without_values(tmp_path, monkeypatch):
    import builtins

    (tmp_path / "wallet.json").write_text(json.dumps(list(_pair())))
    original = builtins.__import__
    def no_crypto(name, *args, **kwargs):
        if name.startswith("cryptography"):
            raise ImportError("not installed")
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", no_crypto)
    assert guard.main([str(tmp_path)]) == 2


def test_git_object_store_is_excluded_but_dotfiles_are_checked(tmp_path):
    dotgit = tmp_path / ".git"
    dotgit.mkdir()
    (dotgit / "old-wallet.json").write_text(json.dumps(list(_pair())))
    (tmp_path / ".wallet.json").write_text(json.dumps(list(_pair())))
    assert [(r.path, r.kind) for r in guard.scan(tmp_path)] == [(".wallet.json", "solana-json-keypair")]


def test_only_exact_known_public_evm_dev_keys_are_exempt(tmp_path):
    # Read the existing public development vector instead of duplicating key
    # literals into another tracked fixture. Never print the value on failure.
    existing_guard = (SCRIPT.parent / "verify_mirror_secrets.sh").read_text()
    block = existing_guard.split("cat <<'ANVIL_KEYS'", 1)[1].split("ANVIL_KEYS", 1)[0]
    known_public = re.findall(r"0x([0-9a-f]{64})", block)[0]
    target = tmp_path / "settings.toml"
    target.write_text(f'private_key = "{known_public}"\n')
    assert guard.scan(tmp_path) == []
    changed = bytes.fromhex(known_public)
    changed = bytes([changed[0] ^ 1]) + changed[1:]
    target.write_text(f'private_key = "{changed.hex()}"\n')
    rows = guard.scan(tmp_path)
    assert len(rows) == 1 and rows[0].kind == "hex-private-key-field"


def test_scan_bytes_supports_historical_blobs_without_touching_path(tmp_path):
    rows = guard.scan_bytes("deleted-history/wallet.json", json.dumps(list(_pair())).encode())
    assert [(r.path, r.kind) for r in rows] == [("deleted-history/wallet.json", "solana-json-keypair")]


def test_staged_secret_is_refused_even_after_worktree_is_clean(tmp_path):
    _git(tmp_path, "init", "-q")
    wallet = tmp_path / "wallet.json"
    wallet.write_text(json.dumps(list(_pair())))
    _git(tmp_path, "add", "wallet.json")
    wallet.write_text('{"public":true}\n')
    (tmp_path / ".gitignore").write_text("wallet.json\n")
    assert guard.scan(tmp_path) == []
    rows = guard.scan_index(tmp_path)
    assert [(r.path, r.kind) for r in rows] == [("wallet.json", "index-solana-json-keypair")]
    result = subprocess.run([sys.executable, str(SCRIPT), "--git-index", str(tmp_path)], text=True, capture_output=True)
    assert result.returncode == 1


def test_index_ignores_executable_repo_config_and_inherited_git_environment(tmp_path, monkeypatch):
    _git(tmp_path, "init", "-q")
    (tmp_path / "safe.txt").write_text("ordinary source\n")
    _git(tmp_path, "add", "safe.txt")
    canary = tmp_path / "should-not-exist"
    script = tmp_path / ".git" / "monitor.sh"
    script.write_text(f'#!/bin/sh\ntouch "{canary}"\n')
    script.chmod(0o700)
    config = tmp_path / ".git" / "config"
    config.write_text(config.read_text() + f'\n[core]\nfsmonitor = "{script}"\n[filter "bad"]\nclean = "{script}"\n[include]\npath = /definitely/missing/config\n')
    (tmp_path / ".gitattributes").write_text("* filter=bad\n")
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "core.fsmonitor")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", str(script))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/definitely/missing/config")
    monkeypatch.setenv("GIT_SSH_COMMAND", str(script))
    assert guard.scan_index(tmp_path) == []
    assert not canary.exists()


def test_index_checks_same_tiny_blob_under_every_name(tmp_path):
    _git(tmp_path, "init", "-q")
    (tmp_path / "public.bin").write_bytes(bytes(range(32)))
    (tmp_path / "private_seed.bin").write_bytes(bytes(range(32)))
    _git(tmp_path, "add", ".")
    assert [(r.path, r.kind) for r in guard.scan_index(tmp_path)] == [("private_seed.bin", "index-named-private-seed")]


def test_index_refuses_git_alternates_without_reading_them(tmp_path):
    _git(tmp_path, "init", "-q")
    (tmp_path / "safe.txt").write_text("safe\n")
    _git(tmp_path, "add", ".")
    (tmp_path / ".git" / "objects" / "info" / "alternates").write_text("/private/untrusted\n")
    with pytest.raises(ValueError, match="alternates"):
        guard.scan_index(tmp_path)


def test_api_token_in_index_is_refused_after_clean_worktree_replacement(tmp_path):
    secret = 'sk-' + ('Ab7Qx9' * 8)
    _git(tmp_path, "init", "-q")
    target = tmp_path / 'configuration.txt'
    target.write_text('API_KEY=' + secret + '\n')
    _git(tmp_path, "add", ".")
    target.write_text('API_KEY=\n')
    assert guard.scan(tmp_path) == []
    rows = guard.scan_index(tmp_path)
    assert [(row.path, row.kind) for row in rows] == [('configuration.txt', 'index-api-token-literal')]
    assert rows[0].sha256 == hashlib.sha256(secret.encode()).hexdigest()


def test_frozen_proof_path_requires_exact_bytes_even_at_original_size(tmp_path):
    rel = next(iter(guard._PROOF_FIXTURE_SHA256))
    target = tmp_path / rel
    target.parent.mkdir(parents=True)
    original = (SCRIPT.parent.parent / 'acex' / rel).read_bytes()
    target.write_bytes(original)
    assert guard.scan(tmp_path) == []
    target.write_bytes(_pair() + b'\x01' * (len(original) - len(_pair())))
    assert [(row.path, row.kind) for row in guard.scan(tmp_path)] == [(rel, 'modified-frozen-proof')]


def test_shell_gate_refuses_ignored_tracked_token_without_values(tmp_path):
    secret = 'sk-' + ('N7zR4k' * 8)
    _git(tmp_path, "init", "-q")
    target = tmp_path / 'ignored.conf'
    target.write_text('API_KEY=' + secret + '\n')
    _git(tmp_path, "add", ".")
    (tmp_path / '.gitignore').write_text('ignored.conf\n')
    import os
    result = subprocess.run(
        ['bash', str(SCRIPT.with_name('verify_mirror_secrets.sh')), str(tmp_path)],
        env={**os.environ, 'MIRROR_FORBIDDEN_HOSTS': 'private-canary.invalid'},
        text=True, capture_output=True,
    )
    assert result.returncode != 0
    assert 'api-token-literal' in result.stdout
    assert secret not in result.stdout + result.stderr


def test_export_gate_cannot_exempt_private_key_by_flow_fixture_name(tmp_path):
    target = tmp_path / 'test' / 'flow-guard.test.ts'
    target.parent.mkdir()
    private = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
    target.write_bytes(private.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()))
    assert [(row.path, row.kind) for row in guard.scan(tmp_path)] == [('test/flow-guard.test.ts', 'pem-private-key')]


def test_literal_prefilters_preserve_api_pattern_case_and_word_boundaries():
    tokens = [
        b"npm_" + b"A7" * 12, b"GHP_" + b"B8" * 12,
        b"sk-ant-" + b"C9_-" * 8, b"sk-or-v1-" + b"D0_" * 10,
        b"GOCSPX-" + b"E1_" * 10, b"aimk_" + b"F2_-" * 8,
        b"12345678:AA" + b"G3_" * 11, b"1234567890:AA" + b"H4_" * 11,
        b"sk-" + b"x" * 20 + b"npm_" + b"y" * 30,
        b"AKIA" + b"A7" * 8, b"AIzaSy" + b"a7_" * 11,
    ]
    data = b"\n".join(prefix + token + b"\n" for token in tokens for prefix in (b"", b"'", b"word", b"_", b"\xff", "é".encode()))
    expected = [m.group(0) for m in guard._API_TOKEN_BYTES.finditer(data)]
    actual = [m.group(0) for m in guard._prefixed_matches(
        guard._API_TOKEN_BYTES, data, data.lower(), guard._API_PREFIXES, telegram=True,
    )]
    assert actual == expected


def test_literal_prefilters_preserve_hex_field_quotes_and_overlap():
    secret = b"a0" * 32
    data = b"\n".join(prefix + field + b' = "0x' + secret + b'"\n'
                      for field in (b"private_key", b'"PRIVATEKEY"', b"'secret-key'", b"signing_seed")
                      for prefix in (b"", b"word", b"_", b"\xff", "é".encode()))
    expected = [m.group("secret") for m in guard._HEX_FIELD_BYTES.finditer(data)]
    actual = [m.group("secret") for m in guard._prefixed_matches(
        guard._HEX_FIELD_BYTES, data, data.lower(), (b"private", b"secret", b"signing"),
    )]
    assert actual == expected


def test_literal_prefilters_preserve_token_field_boundary_semantics():
    data = b"\n".join(prefix + field + b"='" + b"a0" * 32 + b"'\n"
                      for field in (b"ADMIN_TOKEN", b'"api_token"', b"mesh_token", b"OPERATOR_TOKEN")
                      for prefix in (b"", b"word", b"_", b"\xff"))
    expected = [m.group("secret") for m in guard._HEX_TOKEN_BYTES.finditer(data)]
    actual = [m.group("secret") for m in guard._prefixed_matches(
        guard._HEX_TOKEN_BYTES, data, data.lower(),
        (b"admin_token", b"api_token", b"mesh_token", b"operator_token"),
    )]
    assert actual == expected


def test_temporary_git_fixtures_ignore_repository_selector_environment(tmp_path, monkeypatch):
    other = tmp_path / "must-not-be-staged"
    temporary = tmp_path / "fixture"
    other.mkdir()
    temporary.mkdir()
    _git(other, "init", "-q")
    (other / "private.txt").write_text("do not stage this unrelated repository")
    monkeypatch.setenv("GIT_DIR", str(other / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(other))
    monkeypatch.setenv("GIT_INDEX_FILE", str(other / ".git" / "index"))
    _git(temporary, "init", "-q")
    (temporary / "ordinary.txt").write_text("temporary fixture only")
    _git(temporary, "add", ".")
    assert not (other / ".git" / "index").exists()
    assert (temporary / ".git" / "index").exists()


@pytest.mark.parametrize("name", ["session_secret", "dataset_salt", "oracle_vrf_sk", "conductor_key", ".treasury_scanner_ref_key"])
def test_known_runtime_hmac_vrf_and_salt_files_are_private_even_when_printable(name):
    rows = guard.scan_bytes("runtime/" + name, b"x" * 32)
    assert [(r.path, r.kind) for r in rows] == [("runtime/" + name, "named-private-seed")]


def test_fernet_master_key_encoding_is_detected_without_catching_public_keys():
    encoded = base64.urlsafe_b64encode(bytes(range(32)))
    assert guard.scan_bytes("data/secrets/master.key", encoded + b"\n")[0].kind == "named-private-seed"
    assert guard.scan_bytes("public_key.txt", encoded + b"\n") == []


def test_named_mldsa_public_and_private_pair_format_is_detected():
    encoded = b"01" * 1952 + b"\n" + b"02" * 4032 + b"\n"
    assert guard.scan_bytes("data/hub_signing_key_mldsa", encoded)[0].kind == "named-private-seed"
    assert guard.scan_bytes("public-pqc-proof.txt", encoded) == []


def test_named_public_lookalike_and_malformed_encoded_seed_are_not_private():
    assert guard.scan_bytes("public_key", b"x" * 32) == []
    assert guard.scan_bytes("signing_seed.txt", b"ordinary short explanatory text") == []


@pytest.mark.parametrize("prefix,tail", [(b"AKIA", b"A7" * 8), (b"AIzaSy", b"a7_" * 11)], ids=["aws", "google"])
def test_export_google_and_aws_key_grammars_keep_exact_prefix_case(prefix, tail):
    valid = prefix + tail
    assert [r.kind for r in guard.scan_bytes("credentials.txt", valid, export_policy=True)] == ["api-token-literal"]
    assert guard.scan_bytes("public.txt", prefix.lower() + tail, export_policy=True) == []


@pytest.mark.parametrize('relative', [
    'aimarket_hub/_signing_key_storage.py',
    'plugins/aimarket-provenance/aimarket_provenance/_signing_key_storage.py',
    'products/demo/vendor/oracle-core/oracle_core/_signing_key_storage.py',
])
def test_trusted_storage_source_is_content_pinned_at_all_export_roots(tmp_path, relative):
    import os
    trusted = SCRIPT.parents[1] / 'security' / 'signing_key_storage.py'
    target = tmp_path / relative
    target.parent.mkdir(parents=True)
    target.write_bytes(trusted.read_bytes())
    command = ['bash', str(SCRIPT.with_name('verify_mirror_secrets.sh')), str(tmp_path)]
    env = {**os.environ, 'MIRROR_FORBIDDEN_HOSTS': 'private-canary.invalid'}
    assert subprocess.run(command, env=env, capture_output=True).returncode == 0
    target.write_bytes(trusted.read_bytes() + b'\n# changed source\n')
    result = subprocess.run(command, env=env, capture_output=True, text=True)
    assert result.returncode != 0
    assert 'unexpected-signing-storage-module' in result.stdout


def test_index_rejects_changed_storage_source_hidden_by_clean_worktree(tmp_path):
    _git(tmp_path, 'init', '-q')
    target = tmp_path / '_signing_key_storage.py'
    trusted = (SCRIPT.parents[1] / 'security' / 'signing_key_storage.py').read_bytes()
    target.write_bytes(trusted + b'\n# stale or modified implementation\n')
    _git(tmp_path, 'add', '.')
    target.write_bytes(trusted)
    assert guard.scan(tmp_path) == []
    assert [row.kind for row in guard.scan_index(tmp_path)] == ['index-unexpected-signing-storage-module']


@pytest.mark.parametrize('relative,kind', [
    ('z/_signing_key_storage.py', 'index-unexpected-signing-storage-module'),
    (next(iter(guard._PROOF_FIXTURE_SHA256)), 'index-modified-frozen-proof'),
])
def test_large_staged_blob_checks_policy_for_every_path_alias(tmp_path, relative, kind):
    _git(tmp_path, 'init', '-q')
    content = b'# ordinary padding\n' * (guard._CHUNK_SIZE // 10)
    assert len(content) >= guard._CHUNK_SIZE
    (tmp_path / 'a-ordinary.txt').write_bytes(content)
    target = tmp_path / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    _git(tmp_path, 'add', '.')
    rows = guard.scan_index(tmp_path)
    assert [(row.path, row.kind) for row in rows] == [(relative, kind)]
