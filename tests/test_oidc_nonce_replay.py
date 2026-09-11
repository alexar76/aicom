"""OIDC nonce replay protection (H-3)."""

from __future__ import annotations

import importlib.util
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.persistent_security_store import reset_persistent_security_store_for_tests


def _load_oidc_auth():
    path = Path(__file__).resolve().parents[1] / "web" / "backend" / "core" / "oidc_auth.py"
    spec = importlib.util.spec_from_file_location("oidc_auth_nonce_test", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(autouse=True)
def _reset_store():
    reset_persistent_security_store_for_tests()
    yield
    reset_persistent_security_store_for_tests()


@pytest.fixture
def oidc_env(monkeypatch, tmp_path):
    monkeypatch.setenv("AIFACTORY_SECURITY_STORE_DB", str(tmp_path / "security_store.db"))
    monkeypatch.setenv("AIFACTORY_OIDC_ENABLED", "1")
    monkeypatch.setenv("AIFACTORY_OIDC_ISSUER", "https://issuer.example")
    monkeypatch.setenv("AIFACTORY_OIDC_CLIENT_ID", "client-id")
    monkeypatch.setenv("AIFACTORY_OIDC_REDIRECT_URI", "https://app.example/callback")
    return _load_oidc_auth()


def _mock_discovery_and_jwks(oa):
    discovery = {
        "issuer": "https://issuer.example",
        "jwks_uri": "https://issuer.example/jwks",
    }
    signing_key = MagicMock()
    signing_key.key = "test-key"
    jwks_client = MagicMock()
    jwks_client.get_signing_key_from_jwt.return_value = signing_key
    return (
        patch.object(oa, "_discovery", return_value=discovery),
        patch.object(oa, "PyJWKClient", return_value=jwks_client),
    )


def test_verify_id_token_first_use_ok(oidc_env):
    oa = oidc_env
    nonce = "nonce-first-use"
    claims = {
        "sub": "user-1",
        "nonce": nonce,
        "exp": time.time() + 600,
        "iat": time.time(),
    }
    disc, jwks = _mock_discovery_and_jwks(oa)
    with disc, jwks, patch.object(oa.jwt, "decode", return_value=claims):
        out = oa.verify_id_token("fake.jwt.token", nonce)
    assert out["sub"] == "user-1"


def test_verify_id_token_replay_rejected(oidc_env):
    oa = oidc_env
    nonce = "nonce-replay"
    claims = {
        "sub": "user-1",
        "nonce": nonce,
        "exp": time.time() + 600,
        "iat": time.time(),
    }
    disc, jwks = _mock_discovery_and_jwks(oa)
    with disc, jwks, patch.object(oa.jwt, "decode", return_value=claims):
        oa.verify_id_token("fake.jwt.token", nonce)
        with pytest.raises(ValueError, match="nonce already used"):
            oa.verify_id_token("fake.jwt.token", nonce)


def test_verify_id_token_nonce_mismatch(oidc_env):
    oa = oidc_env
    claims = {
        "sub": "user-1",
        "nonce": "expected",
        "exp": time.time() + 600,
        "iat": time.time(),
    }
    disc, jwks = _mock_discovery_and_jwks(oa)
    with disc, jwks, patch.object(oa.jwt, "decode", return_value=claims):
        with pytest.raises(ValueError, match="mismatched"):
            oa.verify_id_token("fake.jwt.token", "different")
