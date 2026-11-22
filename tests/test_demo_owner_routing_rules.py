import json
from pathlib import Path

import pyotp
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.persistent_security_store import PersistentSecurityStore
from web.backend.api.admin import auth
from web.backend.api.admin.dashboard import router
from web.backend.core.security import SecurityManager
from web.backend.middleware.api_version import ApiVersionMiddleware
from web.backend.middleware.csrf import csrf_protect_middleware
from web.backend.middleware.public_demo_readonly import public_demo_readonly_middleware
from web.backend.services import admin_users_store as users


def test_only_verified_owner_can_save_demo_routing_rules(tmp_path, monkeypatch):
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("AIFACTORY_DEMO_READONLY", "1")
    monkeypatch.setenv("AIFACTORY_CSRF_PROTECT", "1")
    monkeypatch.delenv("AIFACTORY_SSO_TRUSTED_HEADER", raising=False)
    monkeypatch.setattr(users, "USERS_PATH", tmp_path / "admin_users.json")
    monkeypatch.setattr(auth, "ADMIN_JSON", tmp_path / "admin.json")
    monkeypatch.setattr(users, "LEGACY_ADMIN_PATH", auth.ADMIN_JSON)
    totp_secret = pyotp.random_base32()
    auth.ADMIN_JSON.write_text(json.dumps({
        "username": "admin", "totp_enabled": True, "totp_secret": totp_secret,
    }))
    source = Path(__file__).resolve().parents[1] / "data/config/model_providers.example.yaml"
    config = tmp_path / "model_providers.yaml"
    config.write_bytes(source.read_bytes())
    monkeypatch.setenv("AIFACTORY_MODEL_PROVIDERS", str(config))

    security = SecurityManager(
        secret_key="isolated-owner-routing-regression-key",
        audit_log_path=str(tmp_path / "audit.jsonl"),
    )
    security._rl_store = PersistentSecurityStore(str(tmp_path / "rate-limit.db"))
    password = "local-owner-regression-password"
    password_hash = security.hash_password(password)
    users.create_user(username="admin", password_hash=password_hash, role="super_admin")
    users.create_user(username="other", password_hash=password_hash, role="super_admin")

    app = FastAPI()
    app.state.security_manager = security
    app.include_router(auth.router)
    app.include_router(router)
    app.add_middleware(ApiVersionMiddleware)
    app.middleware("http")(public_demo_readonly_middleware)
    app.middleware("http")(csrf_protect_middleware)

    login = "/api/admin/auth/login"
    url = "/api/admin/providers/routing-rules"
    versioned_url = "/api/v1/admin/providers/routing-rules"
    owner = {"username": "admin", "password": password, "owner_login": True}
    with TestClient(app, client=("127.0.0.1", 1234)) as client:
        bad = client.post(login, json={**owner, "password": "incorrect-owner-password"})
        assert bad.status_code == 401
        guest = client.post(login, json={"username": "admin", "password": "autofilled"})
        assert guest.status_code == 200
        assert security._rl_store.recent_attempt_count("demo-owner:127.0.0.1", 900) == 1
        rules = client.get(url).json()["routing_rules"]
        next(rule for rule in rules if rule["task_type"] == "design_critic")["timeout_sec"] += 1
        body = {"routing_rules": rules}
        headers = {"X-CSRF-Token": client.cookies["csrf_token"]}
        for path in (url, versioned_url):
            assert client.put(path, json=body, headers=headers).status_code == 403

        normal_login = client.post(login, json={"username": "other", "password": password})
        assert normal_login.status_code == 200
        assert security._rl_store.recent_attempt_count("demo-owner:127.0.0.1", 900) == 1
        headers = {"X-CSRF-Token": client.cookies["csrf_token"]}
        assert client.put(url, json=body, headers=headers).status_code == 403
        assert client.post(login, json={**owner, "username": "other"}).status_code == 401
        challenge = client.post(login, json=owner)
        assert challenge.status_code == 401
        assert challenge.json()["detail"] == "2FA code required"
        signed_in = client.post(login, json={**owner, "totp_code": pyotp.TOTP(totp_secret).now()})
        assert signed_in.status_code == 200, signed_in.text
        assert client.put(url, json=body).status_code == 403
        headers = {"X-CSRF-Token": client.cookies["csrf_token"]}
        assert client.put(versioned_url, json=body, headers=headers).status_code == 200
        assert client.get(url).json() == body
        assert yaml.safe_load(config.read_text())["routing_rules"] == rules
        assert client.put("/api/admin/providers/deepseek_api", json={}, headers=headers).status_code == 403

        assert client.post("/api/admin/auth/logout", headers=headers).status_code == 200
        revoked = {"Authorization": f"Bearer {signed_in.json()['access_token']}"}
        assert client.put(url, json=body, headers=revoked).status_code == 403
