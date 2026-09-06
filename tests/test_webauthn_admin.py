"""WebAuthn admin helpers (options + challenge storage)."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from security import webauthn_admin as wa


@pytest.fixture
def admin_json(tmp_path, monkeypatch):
    path = tmp_path / "config" / "admin.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"username": "admin"}), encoding="utf-8")
    monkeypatch.setattr(wa, "ADMIN_JSON", path)
    monkeypatch.setenv("AIFACTORY_WEBAUTHN_RP_ID", "localhost")
    monkeypatch.setenv("AIFACTORY_WEBAUTHN_ORIGIN", "http://localhost:9080")
    return path


def test_registration_options_returns_public_key(admin_json):
    opts = wa.registration_options("admin")
    assert opts.get("rp", {}).get("id") == "localhost"
    assert "challenge" in opts


def test_webauthn_is_enabled_requires_credentials(admin_json):
    cfg = wa.load_admin_config()
    assert not wa.webauthn_is_enabled(cfg)
    cfg["mfa_method"] = "webauthn"
    cfg["webauthn_credentials"] = [{"credential_id": "abc", "public_key": "pk", "sign_count": 0}]
    assert wa.webauthn_is_enabled(cfg)


def test_disable_webauthn_clears_credentials(admin_json):
    cfg = wa.load_admin_config()
    cfg["mfa_method"] = "webauthn"
    cfg["webauthn_credentials"] = [{"credential_id": "x", "public_key": "y", "sign_count": 0}]
    wa.save_admin_config(cfg)
    wa.disable_webauthn(password_ok=True)
    cfg2 = wa.load_admin_config()
    assert cfg2.get("webauthn_credentials") in (None, [])
    assert not cfg2.get("webauthn_enabled")


def test_verify_registration_stores_credential(admin_json):
    wa.registration_options("admin")
    fake_verification = type(
        "V",
        (),
        {
            "credential_id": b"\x01\x02",
            "credential_public_key": b"\xaa\xbb",
            "sign_count": 0,
        },
    )()
    with patch.object(wa, "verify_registration_response", return_value=fake_verification):
        with patch.object(wa, "_pop_challenge", return_value=b"challenge-bytes"):
            out = wa.verify_registration("admin", {"id": "x", "response": {}})
    assert out.get("credential_id")
    cfg = wa.load_admin_config()
    assert cfg.get("mfa_method") == "webauthn"
    assert len(wa.list_credentials(cfg)) == 1
