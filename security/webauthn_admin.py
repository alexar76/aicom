"""
WebAuthn (passkey) 2FA for admin accounts — alternative to TOTP.

Credentials and flags live in ``data/config/admin.json`` (same as legacy TOTP metadata).
"""

from __future__ import annotations

import base64
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Optional

from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url
from webauthn.helpers.options_to_json import options_to_json
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    UserVerificationRequirement,
)

logger = logging.getLogger(__name__)

ADMIN_JSON = Path("/app/data/config/admin.json")
CHALLENGE_TTL_SEC = 300


def _env_truthy(name: str, default: bool = False) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


def webauthn_enabled_globally() -> bool:
    return _env_truthy("AIFACTORY_WEBAUTHN_ENABLED", True)


def _rp_id() -> str:
    explicit = (os.environ.get("AIFACTORY_WEBAUTHN_RP_ID") or "").strip()
    if explicit:
        return explicit
    site = (os.environ.get("NEXT_PUBLIC_SITE_URL") or os.environ.get("AIFACTORY_PUBLIC_ORIGIN") or "").strip()
    if site:
        from urllib.parse import urlparse

        host = urlparse(site).hostname
        if host:
            return host
    return "localhost"


def _rp_name() -> str:
    return (os.environ.get("AIFACTORY_WEBAUTHN_RP_NAME") or "AI-Factory").strip()


def _origin() -> str:
    explicit = (os.environ.get("AIFACTORY_WEBAUTHN_ORIGIN") or "").strip()
    if explicit:
        return explicit.rstrip("/")
    site = (os.environ.get("NEXT_PUBLIC_SITE_URL") or "").strip().rstrip("/")
    if site:
        return site
    return "http://localhost:9080"


def load_admin_config() -> dict[str, Any]:
    if not ADMIN_JSON.exists():
        return {}
    try:
        with open(ADMIN_JSON, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError, TypeError):
        return {}


def save_admin_config(cfg: dict[str, Any]) -> None:
    ADMIN_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(ADMIN_JSON, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


def list_credentials(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    creds = cfg.get("webauthn_credentials")
    return list(creds) if isinstance(creds, list) else []


def webauthn_is_enabled(cfg: dict[str, Any]) -> bool:
    if not webauthn_enabled_globally():
        return False
    if str(cfg.get("mfa_method") or "").lower() != "webauthn":
        return False
    return len(list_credentials(cfg)) > 0


def totp_is_active(cfg: dict[str, Any]) -> bool:
    return bool(cfg.get("totp_enabled") and cfg.get("totp_secret"))


def _store_challenge(cfg: dict[str, Any], kind: str, challenge: bytes, username: str = "") -> None:
    pending = cfg.setdefault("webauthn_pending", {})
    if not isinstance(pending, dict):
        pending = {}
        cfg["webauthn_pending"] = pending
    pending[kind] = {
        "challenge": bytes_to_base64url(challenge),
        "expires": time.time() + CHALLENGE_TTL_SEC,
        "username": username,
    }


def _pop_challenge(cfg: dict[str, Any], kind: str, username: str = "") -> Optional[bytes]:
    pending = cfg.get("webauthn_pending")
    if not isinstance(pending, dict):
        return None
    row = pending.pop(kind, None)
    save_admin_config(cfg)
    if not isinstance(row, dict):
        return None
    if row.get("expires", 0) < time.time():
        return None
    if username and str(row.get("username") or "") != username:
        return None
    ch = row.get("challenge")
    if not isinstance(ch, str) or not ch:
        return None
    return base64url_to_bytes(ch)


def registration_options(username: str) -> dict[str, Any]:
    cfg = load_admin_config()
    user_id = username.encode("utf-8")
    exclude: list[PublicKeyCredentialDescriptor] = []
    for c in list_credentials(cfg):
        cid = c.get("credential_id")
        if isinstance(cid, str) and cid:
            exclude.append(
                PublicKeyCredentialDescriptor(id=base64url_to_bytes(cid))
            )

    options = generate_registration_options(
        rp_id=_rp_id(),
        rp_name=_rp_name(),
        user_id=user_id,
        user_name=username,
        user_display_name=username,
        exclude_credentials=exclude,
        authenticator_selection=AuthenticatorSelectionCriteria(
            user_verification=UserVerificationRequirement.PREFERRED,
        ),
    )
    _store_challenge(cfg, "register", options.challenge, username)
    save_admin_config(cfg)
    return json.loads(options_to_json(options))


def verify_registration(username: str, credential: dict[str, Any], *, label: str = "") -> dict[str, Any]:
    cfg = load_admin_config()
    expected = _pop_challenge(cfg, "register", username)
    if expected is None:
        raise ValueError("Registration challenge expired or missing")

    verification = verify_registration_response(
        credential=credential,
        expected_challenge=expected,
        expected_rp_id=_rp_id(),
        expected_origin=_origin(),
        require_user_verification=False,
    )

    cred_id = bytes_to_base64url(verification.credential_id)
    creds = list_credentials(cfg)
    if any(c.get("credential_id") == cred_id for c in creds):
        raise ValueError("Credential already registered")

    creds.append(
        {
            "credential_id": cred_id,
            "public_key": bytes_to_base64url(verification.credential_public_key),
            "sign_count": int(verification.sign_count),
            "label": (label or "Passkey").strip()[:64],
            "created_at": time.time(),
        }
    )
    cfg["webauthn_credentials"] = creds
    cfg["mfa_method"] = "webauthn"
    cfg["webauthn_enabled"] = True
    cfg.pop("totp_enabled", None)
    cfg.pop("totp_secret", None)
    cfg.pop("pending_totp_secret", None)
    save_admin_config(cfg)
    return {"credential_id": cred_id, "message": "Passkey registered"}


def authentication_options(username: str) -> dict[str, Any]:
    cfg = load_admin_config()
    allow: list[PublicKeyCredentialDescriptor] = []
    for c in list_credentials(cfg):
        cid = c.get("credential_id")
        if isinstance(cid, str) and cid:
            allow.append(PublicKeyCredentialDescriptor(id=base64url_to_bytes(cid)))

    if not allow:
        raise ValueError("No passkeys registered")

    options = generate_authentication_options(
        rp_id=_rp_id(),
        allow_credentials=allow,
        user_verification=UserVerificationRequirement.PREFERRED,
    )
    _store_challenge(cfg, "login", options.challenge, username)
    save_admin_config(cfg)
    return json.loads(options_to_json(options))


def verify_authentication(username: str, credential: dict[str, Any]) -> None:
    cfg = load_admin_config()
    expected = _pop_challenge(cfg, "login", username)
    if expected is None:
        raise ValueError("Login challenge expired or missing")

    cred_id = credential.get("id") or credential.get("rawId")
    if isinstance(cred_id, str):
        cred_id_b64 = cred_id
    else:
        cred_id_b64 = bytes_to_base64url(cred_id) if cred_id else ""

    stored = None
    for c in list_credentials(cfg):
        if c.get("credential_id") == cred_id_b64:
            stored = c
            break
    if not stored:
        raise ValueError("Unknown passkey")

    verification = verify_authentication_response(
        credential=credential,
        expected_challenge=expected,
        expected_rp_id=_rp_id(),
        expected_origin=_origin(),
        credential_public_key=base64url_to_bytes(stored["public_key"]),
        credential_current_sign_count=int(stored.get("sign_count") or 0),
        require_user_verification=False,
    )

    stored["sign_count"] = int(verification.new_sign_count)
    cfg["webauthn_credentials"] = list_credentials(cfg)
    save_admin_config(cfg)


def disable_webauthn(*, password_ok: bool) -> None:
    if not password_ok:
        raise ValueError("Invalid password")
    cfg = load_admin_config()
    cfg.pop("webauthn_credentials", None)
    cfg["webauthn_enabled"] = False
    if str(cfg.get("mfa_method") or "").lower() == "webauthn":
        cfg.pop("mfa_method", None)
    cfg.pop("webauthn_pending", None)
    save_admin_config(cfg)
