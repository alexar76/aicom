"""The fixer may read source. It may not read credentials.

The loop guarded writes with real care — a denied-path list, a declared scope map, and both
checked against the model's answer as well as the operator's config. Reads were guarded by a
regular expression that looked for dotted module names, with the whole monorepo bind-mounted
read-only underneath it: `.env`, `data/secrets/*.key`, satellite provider keys.

A bad patch meets a gate. A disclosed key meets nobody — it is in the prompt, the provider's
logs and every transcript downstream before anyone notices. These tests hold the read side to
the standard the write side already had.
"""

from __future__ import annotations

import pytest

from web.backend.services.remediation_fix import (
    audit_visible_credentials,
    path_is_denied,
    path_is_secret,
    read_is_denied,
    redact_secrets,
)


# ── paths that are credentials ────────────────────────────────────────────────────

@pytest.mark.parametrize("rel", [
    ".env",
    ".env.local",
    ".env.production",
    "aimarket-hub/.env",
    "data/secrets/jwt_secret.key",
    "data/secrets/customer_jwt.key",
    "basanos/.aimarket/provider.key",
    "themis/keys/signer.pem",
    "ops/id_rsa",
    "ops/id_ed25519",
    "home/.ssh/known_hosts",
    "deploy/wallet.json",
    "config/credentials.json",
    "ci/.npmrc",
    "ci/.pypirc",
    "certs/server.p12",
])
def test_credential_paths_are_refused(rel):
    assert path_is_secret(rel), f"{rel} should be refused as credential material"
    assert "credential material" in read_is_denied(rel)


@pytest.mark.parametrize("rel", [
    "oracles/core/oracle_core/signing.py",
    "aimarket-hub/aimarket_hub/unpaid_invoke.py",
    "gaia/gaia/attestation.py",
    "momus/canary/canary.py",
    "web/backend/keys.py",            # a module ABOUT keys is not a key
    "docs/secrets-handling.md",       # documentation about secrets is not a secret
])
def test_ordinary_source_is_still_readable(rel):
    assert path_is_secret(rel) == "", f"{rel} should be readable"


def test_a_module_named_keys_is_not_a_key_file():
    # The blunt matcher must not eat the component's own source. `keys.py` is a module.
    assert path_is_secret("aimarket-hub/aimarket_hub/keys.py") == ""
    assert path_is_secret("aimarket-hub/aimarket_hub/signing.key") != ""


# ── paths that are a conflict of interest ─────────────────────────────────────────

@pytest.mark.parametrize("rel", [
    "momus/momus/engine/scanner.py",
    "momus/scripts/deploy.sh",
    "skopos/skopos/remediation/deploy_order.py",
    "treasury/treasury/payer.py",
    "web/backend/services/remediation_fix.py",
])
def test_the_loop_may_not_read_its_own_judges(rel):
    # Already refused for WRITING. Being shown the source of the thing that verifies your
    # patch is a smaller problem than editing it, but it is the same problem.
    assert path_is_denied(rel), "precondition: this is on the write denylist"
    assert "conflict of interest" in read_is_denied(rel)


def test_the_two_refusals_are_reported_distinctly():
    # An operator reading a log needs to know which rule fired: a leaked key and a
    # conflict of interest call for completely different responses.
    assert "credential" in read_is_denied("data/secrets/a.key")
    assert "conflict" in read_is_denied("skopos/skopos/remediation/conductor.py")


# ── content redaction ─────────────────────────────────────────────────────────────

# Concatenated so verify_mirror_secrets does not treat this test as a live leak.
@pytest.mark.parametrize("secret", [
    "-----BEGIN " + "OPENSSH PRIVATE KEY-----",
    "-----BEGIN " + "RSA PRIVATE KEY-----",
    "sk-" + "726e9fAbCdEf0123456789",
    "ghp_" + "abcdefghijklmnopqrstuvwxyz0123",
    "github_pat_" + "11ABCDEFG0123456789abcdef",
    "xoxb-" + "1234567890-abcdefghij",
    "AKIA" + "IOSFODNN7EXAMPLE",
    "0x" + "a1b2c3d4" * 8,
])
def test_key_material_is_redacted_from_content(secret):
    text = f"config = load()\nvalue = '{secret}'\nreturn value\n"
    out, hits = redact_secrets(text)
    assert hits >= 1
    assert secret not in out
    assert "config = load()" in out, "redaction must not eat the surrounding source"


@pytest.mark.parametrize("line", [
    'api_key = "sk_live_0123456789abcdef"',
    "API_KEY: aVeryLongLookingSecretValue123",
    'password = "correct-horse-battery-staple-1"',
    "token= abcdefghijklmnopqrstuvwxyz",
])
def test_assignments_that_look_like_credentials_are_redacted(line):
    out, hits = redact_secrets(line)
    assert hits >= 1, f"expected a redaction in: {line}"


@pytest.mark.parametrize("innocent", [
    "def manifest_canonical(manifest: dict) -> bytes:",
    "# The signature verifies against the operator's public key.",
    "api_key_env = 'OPENROUTER_API_KEY'",      # names the variable, holds no value
    "raise FixRefused('no signing backend available')",
])
def test_ordinary_source_survives_redaction_untouched(innocent):
    out, hits = redact_secrets(innocent)
    assert hits == 0, f"false positive on: {innocent}"
    assert out == innocent


def test_redaction_is_safe_on_empty_input():
    assert redact_secrets("") == ("", 0)
    assert redact_secrets(None) == (None, 0)


def test_a_file_with_two_secrets_loses_both():
    text = "a = '%s'\nb = '%s'\n" % (
        "ghp_" + "abcdefghijklmnopqrstuvwxyz0123",
        "AKIA" + "IOSFODNN7EXAMPLE",
    )
    out, hits = redact_secrets(text)
    assert hits == 2
    assert "ghp_" not in out and "AKIA" not in out


# ── what is still visible must be counted, not assumed ────────────────────────────

def test_the_audit_finds_a_credential_that_no_mask_covers(tmp_path):
    # Masks are a hand-maintained list in a compose file. The next `.env.something` will not
    # be on it — two already were not, and only turned up because someone went looking.
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / ".env.ci").write_text("TOKEN=abc\n")
    (tmp_path / "app" / "main.py").write_text("print('hi')\n")

    found = audit_visible_credentials(str(tmp_path))
    assert found == ["app/.env.ci"]


def test_a_masked_file_reads_as_absent(tmp_path):
    # /dev/null over a path leaves a zero-byte entry, which is not a leak.
    (tmp_path / ".env").write_text("")
    assert audit_visible_credentials(str(tmp_path)) == []


def test_example_files_and_ca_bundles_are_not_credentials(tmp_path):
    (tmp_path / ".env.example").write_text("TOKEN=\n")
    (tmp_path / "cacert.pem").write_text("-----BEGIN CERTIFICATE-----\n")
    assert audit_visible_credentials(str(tmp_path)) == []


def test_dependency_trees_are_not_walked(tmp_path):
    # Full of fixtures and bundles that match on name and are nobody's secret; walking them
    # would bury a real finding in noise and make the count meaningless.
    for noisy in ("node_modules", ".venv", "site-packages", ".git"):
        d = tmp_path / noisy
        d.mkdir()
        (d / "id_rsa").write_text("fixture\n")
    assert audit_visible_credentials(str(tmp_path)) == []


def test_a_clean_tree_reports_nothing(tmp_path):
    (tmp_path / "main.py").write_text("print('hi')\n")
    assert audit_visible_credentials(str(tmp_path)) == []


def test_the_audit_is_bounded(tmp_path):
    for i in range(30):
        (tmp_path / f"k{i}.key").write_text("x")
    assert len(audit_visible_credentials(str(tmp_path), limit=5)) == 5


# ── the guard must not cry wolf at source ─────────────────────────────────────────
#
# A live audit of the container turned up twenty "credentials", nineteen of which were ARGUS
# source and its build output: keystore.ts, wallet.js, wallet.d.ts.map. A guard that refuses
# source is a guard that gets widened until it protects nothing — and it would have refused
# the fixer a legitimate reference file on the way.

@pytest.mark.parametrize("rel", [
    "argus/src/economy/wallet.ts",
    "argus/src/economy/keystore.ts",
    "argus/dist/economy/wallet.js",
    "argus/dist/economy/keystore.d.ts",
    "argus/dist/economy/wallet.js.map",
    "argus/test/keystore.test.ts",
    "web/backend/credentials.py",
    "web/backend/wallet_view.tsx",
])
def test_source_about_wallets_and_keystores_is_readable(rel):
    assert path_is_secret(rel) == "", f"{rel} is source, not a credential"


@pytest.mark.parametrize("rel", [
    "deploy/wallet.json",
    "config/credentials.json",
    "ops/keystore",
    "ci/credentials.txt",
    "env/wallet.enc",
])
def test_the_data_files_themselves_are_still_refused(rel):
    assert path_is_secret(rel), f"{rel} is data, not source"


def test_a_key_basename_is_refused_whatever_follows_it():
    assert path_is_secret("ops/id_rsa")
    assert path_is_secret("ops/id_rsa.bak")
    assert path_is_secret("ops/id_ed25519.pub")


# ── a probe may NAME what a fixer must read, and is still not a principal ─────────

from web.backend.services.remediation_fix import named_reference_sources  # noqa: E402


def test_a_named_file_is_served(tmp_path, monkeypatch):
    import web.backend.services.remediation_fix as mod

    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "signing.py").write_text("def manifest_canonical(m):\n    return ''\n")
    monkeypatch.setattr(mod, "app_root", lambda: str(tmp_path))

    out = named_reference_sources(["pkg/signing.py"], set())
    assert "pkg/signing.py" in out
    assert "manifest_canonical" in out["pkg/signing.py"]


def test_a_probe_naming_a_credential_is_refused_not_obeyed(tmp_path, monkeypatch, caplog):
    # "MOMUS asked for it" is not an entitlement. A probe is not a principal.
    import logging

    import web.backend.services.remediation_fix as mod

    (tmp_path / "data" / "secrets").mkdir(parents=True)
    (tmp_path / "data" / "secrets" / "jwt.key").write_text("supersecret\n")
    monkeypatch.setattr(mod, "app_root", lambda: str(tmp_path))

    with caplog.at_level(logging.WARNING):
        out = named_reference_sources(["data/secrets/jwt.key"], set())

    assert out == {}
    assert "may not have" in caplog.text


def test_a_probe_naming_the_auditors_own_source_is_refused(tmp_path, monkeypatch):
    import web.backend.services.remediation_fix as mod

    (tmp_path / "momus" / "momus").mkdir(parents=True)
    (tmp_path / "momus" / "momus" / "scanner.py").write_text("x = 1\n")
    monkeypatch.setattr(mod, "app_root", lambda: str(tmp_path))

    assert named_reference_sources(["momus/momus/scanner.py"], set()) == {}


def test_a_named_path_cannot_escape_the_application_root(tmp_path, monkeypatch):
    import web.backend.services.remediation_fix as mod

    monkeypatch.setattr(mod, "app_root", lambda: str(tmp_path))
    assert named_reference_sources(["../../etc/passwd"], set()) == {}


def test_a_named_file_that_is_not_in_this_build_is_skipped(tmp_path, monkeypatch):
    import web.backend.services.remediation_fix as mod

    monkeypatch.setattr(mod, "app_root", lambda: str(tmp_path))
    assert named_reference_sources(["pkg/absent.py"], set()) == {}


def test_secrets_inside_a_named_file_are_redacted(tmp_path, monkeypatch):
    import web.backend.services.remediation_fix as mod

    (tmp_path / "cfg.py").write_text(
        "TOKEN = '%s'\n" % ("ghp_" + "abcdefghijklmnopqrstuvwxyz0123")
    )
    monkeypatch.setattr(mod, "app_root", lambda: str(tmp_path))

    out = named_reference_sources(["cfg.py"], set())
    assert "ghp_" not in out["cfg.py"]


def test_a_file_already_in_the_patch_scope_is_not_served_twice(tmp_path, monkeypatch):
    import web.backend.services.remediation_fix as mod

    (tmp_path / "a.py").write_text("x = 1\n")
    monkeypatch.setattr(mod, "app_root", lambda: str(tmp_path))
    assert named_reference_sources(["a.py"], {"a.py"}) == {}


def test_no_names_is_not_an_error(tmp_path, monkeypatch):
    import web.backend.services.remediation_fix as mod

    monkeypatch.setattr(mod, "app_root", lambda: str(tmp_path))
    assert named_reference_sources(None, set()) == {}
    assert named_reference_sources([], set()) == {}
    assert named_reference_sources(["", "  "], set()) == {}
