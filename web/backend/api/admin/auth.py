"""
Admin Authentication API
========================
Handles admin login, 2FA setup, and session management.
Supports multi-user accounts (admin_users.json) + legacy admin.json for TOTP metadata.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from web.backend.http.client_ip import client_ip
from pydantic import BaseModel, Field

from web.backend.core.admin_roles import normalize_role, require_admin_with_rbac
from web.backend.services.demo_credentials import sandbox_demo_password_uses_default
from web.backend.services.public_demo_guard import (
    allows_passwordless_admin_login,
    is_public_demo,
    public_demo_status,
    require_not_public_demo,
)
from web.backend.core.security import SecurityManager
from web.backend.middleware.csrf import CSRF_COOKIE, CSRF_HEADER, new_csrf_token
from web.backend.services import admin_users_store as aus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/auth", tags=["admin-auth"])

from core.paths import legacy_admin_path

ADMIN_JSON = legacy_admin_path()

# Browser session cookie carrying the admin JWT. Additive to the Authorization:
# Bearer header (API/SDK clients keep using the header); it lets the SPA avoid
# storing the JWT in localStorage. SameSite=Strict + the double-submit CSRF cookie
# defend mutations. The auth dependency (get_current_admin) reads either cookie or
# the Bearer header.
ADMIN_SESSION_COOKIE = "aif_admin_session"

# Access-token lifetime in seconds (mirrors SecurityManager.jwt_expiry_minutes default).
ACCESS_TOKEN_MAX_AGE = 1800


def _request_is_https(request: Request) -> bool:
    xf = (request.headers.get("x-forwarded-proto") or "").strip().lower()
    if xf.startswith("https"):
        return True
    return request.url.scheme == "https"


def _access_token_cookie_secure(request: Request) -> bool:
    """Secure cookies on HTTPS (or prod) unless overridden (e.g. local HTTP dev)."""
    v = (os.environ.get("AIFACTORY_COOKIE_SECURE") or "").strip().lower()
    if v in ("1", "true", "yes"):
        return True
    if v in ("0", "false", "no"):
        return False
    if (os.environ.get("AIFACTORY_PROD") or "").strip() == "1":
        return True
    return _request_is_https(request)


def _session_token_max_age(request: Request) -> int:
    """Cookie Max-Age aligned to the JWT expiry so the cookie dies with the token."""
    try:
        security: SecurityManager = request.app.state.security_manager
        minutes = int(getattr(security, "jwt_expiry_minutes", 0) or 0)
        if minutes > 0:
            return minutes * 60
    except Exception:
        pass
    return ACCESS_TOKEN_MAX_AGE


def set_admin_session_cookie(request: Request, response: Response, token: str) -> None:
    """Set the HttpOnly browser session cookie holding the admin JWT.

    Contract (shared with the SPA / frontend agent):
      name      ``aif_admin_session``
      value     the admin JWT (same token returned in the JSON body)
      HttpOnly  yes — JS cannot read it (no localStorage token needed)
      SameSite  Strict
      Path      /
      Secure    on HTTPS or when AIFACTORY_PROD=1 (http://localhost dev stays usable)
      Max-Age   aligned to the JWT expiry
    """
    response.set_cookie(
        key=ADMIN_SESSION_COOKIE,
        value=token,
        httponly=True,
        secure=_access_token_cookie_secure(request),
        samesite="strict",
        max_age=_session_token_max_age(request),
        path="/",
    )


def clear_admin_session_cookie(request: Request, response: Response) -> None:
    """Expire the browser session cookie (logout)."""
    cookie_secure = _access_token_cookie_secure(request)
    # Overwrite with an empty, immediately-expiring value, then delete for good measure.
    response.set_cookie(
        key=ADMIN_SESSION_COOKIE,
        value="",
        httponly=True,
        secure=cookie_secure,
        samesite="strict",
        max_age=0,
        path="/",
    )
    response.delete_cookie(
        ADMIN_SESSION_COOKIE,
        path="/",
        httponly=True,
        secure=cookie_secure,
        samesite="strict",
    )


class LoginRequest(BaseModel):
    username: str = Field(default="admin", min_length=1, max_length=64)
    password: str = Field(default="", max_length=256)
    totp_code: Optional[str] = None
    webauthn_credential: Optional[dict] = None


class Setup2FARequest(BaseModel):
    password: str


class Verify2FARequest(BaseModel):
    code: str


class Disable2FARequest(BaseModel):
    password: str


class ChangePasswordRequest(BaseModel):
    old_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=1)


def _load_legacy_admin() -> dict:
    if not ADMIN_JSON.exists():
        return {}
    try:
        with open(ADMIN_JSON, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError, TypeError):
        return {}


def _legacy_totp_applies(login_username: str) -> bool:
    cfg = _load_legacy_admin()
    if not cfg.get("totp_enabled") or not cfg.get("totp_secret"):
        return False
    legacy_user = str(cfg.get("username") or "admin").strip().lower()
    return legacy_user == aus.normalize_username(login_username)


def _public_demo_passwordless_login(username: str, password: str) -> bool:
    """Shared demo: admin may enter without a password (readonly guard still applies).

    Any autofilled password is ignored — demo hosts advertise passwordless entry.
    """
    if not allows_passwordless_admin_login():
        return False
    if aus.normalize_username(username) != "admin":
        return False
    su = aus.get_user_by_username(username)
    if su and not su.get("enabled", True):
        return False
    return True


def _verify_password_for_login(security: SecurityManager, username: str, password: str) -> bool:
    """Match password against admin_users row or legacy admin.json-only install."""
    su = aus.get_user_by_username(username)
    if su:
        if not su.get("enabled", True):
            return False
        return security.verify_password(password, su.get("password_hash") or "")
    cfg = _load_legacy_admin()
    if not cfg.get("password_hash"):
        return False
    legacy_name = str(cfg.get("username") or "admin").strip().lower()
    if legacy_name != aus.normalize_username(username):
        return False
    return security.verify_password(password, cfg["password_hash"])


def _resolve_role_for_login(username: str) -> str:
    su = aus.get_user_by_username(username)
    if su and su.get("enabled", True):
        return str(su.get("role") or "viewer")
    return "super_admin"


def _admin_twofa_flags() -> tuple[bool, bool, bool, str]:
    """(totp_enabled, totp_pending_setup, webauthn_enabled, mfa_method)."""
    from security import webauthn_admin as wa

    cfg = _load_legacy_admin()
    totp_on = bool(cfg.get("totp_enabled") and cfg.get("totp_secret"))
    pending = bool(cfg.get("pending_totp_secret"))
    webauthn_on = wa.webauthn_is_enabled(cfg)
    method = str(cfg.get("mfa_method") or ("webauthn" if webauthn_on else ("totp" if totp_on else "")))
    return totp_on, pending, webauthn_on, method


def _active_mfa_method(login_username: str) -> str:
    """Return ``webauthn``, ``totp``, or empty string."""
    from security import webauthn_admin as wa

    cfg = _load_legacy_admin()
    if wa.webauthn_is_enabled(cfg):
        legacy_user = str(cfg.get("username") or "admin").strip().lower()
        if legacy_user == aus.normalize_username(login_username):
            return "webauthn"
    if _legacy_totp_applies(login_username):
        return "totp"
    return ""


@router.post("/login")
async def admin_login(request: Request, response: Response, login_data: LoginRequest):
    """Authenticate admin user (multi-user store + legacy admin.json)."""
    security: SecurityManager = request.app.state.security_manager
    peer_ip = client_ip(request)

    aus.ensure_legacy_admin_users_file()

    if not aus.list_users_public():
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Admin not configured. Run 'ai-company init' first.",
        )

    if not security.check_login_attempts(peer_ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Please try again later.",
        )

    passwordless = _public_demo_passwordless_login(login_data.username, login_data.password)
    if not passwordless and not _verify_password_for_login(
        security, login_data.username, login_data.password
    ):
        security.record_login_attempt(peer_ip, False, login_data.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    cfg = _load_legacy_admin()
    mfa = "" if passwordless else _active_mfa_method(login_data.username)
    if mfa == "webauthn":
        from security import webauthn_admin as wa

        if not login_data.webauthn_credential:
            security.record_login_attempt(peer_ip, False, login_data.username)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="WebAuthn required",
            )
        try:
            wa.verify_authentication(
                aus.normalize_username(login_data.username),
                login_data.webauthn_credential,
            )
        except ValueError as e:
            security.record_login_attempt(peer_ip, False, login_data.username)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=str(e) or "Invalid passkey",
            ) from e
    elif mfa == "totp":
        secret = cfg.get("totp_secret")
        if not login_data.totp_code:
            security.record_login_attempt(peer_ip, False, login_data.username)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="2FA code required",
            )
        if not secret or not security.verify_totp(secret, login_data.totp_code):
            security.record_login_attempt(peer_ip, False, login_data.username)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid 2FA code",
            )

    role_str = _resolve_role_for_login(login_data.username)
    norm_user = aus.normalize_username(login_data.username)
    token = security.create_access_token(
        norm_user,
        role=normalize_role(role_str).value,
    )
    security.record_login_attempt(peer_ip, True, login_data.username)

    try:
        from web.backend.services.admin_action_log import log_admin_action

        su = aus.get_user_by_username(norm_user)
        log_admin_action(
            actor_username=norm_user,
            actor_user_id=str(su.get("id")) if su else None,
            action="login",
            resource="admin/auth",
            details={"role": normalize_role(role_str).value},
            ip_address=peer_ip,
        )
    except Exception:
        pass

    cookie_secure = _access_token_cookie_secure(request)
    max_age = _session_token_max_age(request)
    csrf = new_csrf_token()
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        secure=cookie_secure,
        samesite="lax",
        max_age=max_age,
        path="/",
    )
    # Additive HttpOnly browser session cookie (SameSite=Strict) so the SPA need
    # not keep the JWT in localStorage. Bearer-header clients are unaffected.
    set_admin_session_cookie(request, response, token)
    response.set_cookie(
        key=CSRF_COOKIE,
        value=csrf,
        httponly=False,
        secure=cookie_secure,
        samesite="strict",
        max_age=max_age,
        path="/",
    )

    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": max_age,
        "role": normalize_role(role_str).value,
        "csrf_token": csrf,
    }


@router.post("/logout")
async def admin_logout(request: Request, response: Response):
    """Logout admin user."""
    try:
        security: SecurityManager = request.app.state.security_manager
        token = request.cookies.get("access_token")
        if not token:
            auth = (request.headers.get("authorization") or "").strip()
            if auth.lower().startswith("bearer "):
                token = auth[7:].strip()
        if token:
            payload = security.decode_token(token)
            if payload and payload.get("admin"):
                from web.backend.services.admin_action_log import log_admin_action_from_request

                log_admin_action_from_request(
                    request,
                    payload,
                    action="logout",
                    resource="admin/auth",
                    details={},
                )
    except Exception:
        pass
    cookie_secure = _access_token_cookie_secure(request)
    response.delete_cookie(
        "access_token",
        path="/",
        httponly=True,
        secure=cookie_secure,
        samesite="lax",
    )
    clear_admin_session_cookie(request, response)
    response.delete_cookie(
        CSRF_COOKIE,
        path="/",
        secure=cookie_secure,
        samesite="strict",
    )
    return {"message": "Logged out successfully"}


@router.get("/me")
async def get_current_admin_info(
    current_admin: dict = Depends(require_admin_with_rbac),
):
    """Get current admin info."""
    totp_enabled, totp_pending, webauthn_enabled, mfa_method = _admin_twofa_flags()
    r = current_admin.get("role")
    username = str(current_admin.get("sub") or "").strip().lower()
    row = aus.get_user_by_username(username) if username else None
    return {
        "username": current_admin.get("sub"),
        "user_id": row.get("id") if row else None,
        "is_admin": current_admin.get("admin", False),
        "role": normalize_role(r).value if r else normalize_role(None).value,
        "totp_enabled": totp_enabled,
        "totp_pending": totp_pending,
        "webauthn_enabled": webauthn_enabled,
        "mfa_method": mfa_method or None,
        "sandbox_demo_password_uses_default": sandbox_demo_password_uses_default(),
        **public_demo_status(),
    }


@router.post("/setup-2fa")
async def setup_2fa(
    request: Request,
    setup_data: Setup2FARequest,
    current_admin: dict = Depends(require_admin_with_rbac),
):
    """Setup 2FA — metadata stored in legacy admin.json."""
    from security import webauthn_admin as wa

    security: SecurityManager = request.app.state.security_manager
    if not ADMIN_JSON.exists():
        raise HTTPException(status_code=500, detail="admin.json missing")

    if wa.webauthn_is_enabled(wa.load_admin_config()):
        raise HTTPException(status_code=400, detail="Remove passkeys before enabling TOTP")

    with open(ADMIN_JSON, "r", encoding="utf-8") as f:
        admin_config = json.load(f)

    if not _verify_password_for_login(security, current_admin["sub"], setup_data.password):
        raise HTTPException(status_code=400, detail="Invalid password")

    secret = security.generate_totp_secret()
    uri = security.get_totp_uri(secret, current_admin["sub"])

    admin_config["pending_totp_secret"] = secret
    with open(ADMIN_JSON, "w", encoding="utf-8") as f:
        json.dump(admin_config, f, indent=2)

    return {
        "secret": secret,
        "uri": uri,
        "message": "Scan the QR code with Google Authenticator, then verify with a code.",
    }


@router.post("/verify-2fa")
async def verify_2fa(
    request: Request,
    verify_data: Verify2FARequest,
    current_admin: dict = Depends(require_admin_with_rbac),
):
    """Verify and enable 2FA."""
    security: SecurityManager = request.app.state.security_manager
    if not ADMIN_JSON.exists():
        raise HTTPException(status_code=500, detail="admin.json missing")

    with open(ADMIN_JSON, "r", encoding="utf-8") as f:
        admin_config = json.load(f)

    pending_secret = admin_config.get("pending_totp_secret")
    if not pending_secret:
        raise HTTPException(status_code=400, detail="No pending 2FA setup")

    if not security.verify_totp(pending_secret, verify_data.code):
        raise HTTPException(status_code=400, detail="Invalid code")

    admin_config["totp_secret"] = pending_secret
    admin_config["totp_enabled"] = True
    admin_config["mfa_method"] = "totp"
    admin_config.pop("pending_totp_secret", None)
    admin_config.pop("webauthn_credentials", None)
    admin_config["webauthn_enabled"] = False
    admin_config.pop("webauthn_pending", None)

    with open(ADMIN_JSON, "w", encoding="utf-8") as f:
        json.dump(admin_config, f, indent=2)

    return {"message": "2FA enabled successfully"}


@router.post("/cancel-2fa-setup")
async def cancel_2fa_setup(
    _admin: dict = Depends(require_admin_with_rbac),
):
    """Discard pending_totp_secret (e.g. user closed setup without verifying)."""
    if not ADMIN_JSON.exists():
        return {"message": "OK"}
    with open(ADMIN_JSON, "r", encoding="utf-8") as f:
        admin_config = json.load(f)
    admin_config.pop("pending_totp_secret", None)
    with open(ADMIN_JSON, "w", encoding="utf-8") as f:
        json.dump(admin_config, f, indent=2)
    return {"message": "2FA setup cancelled"}


@router.post("/disable-2fa")
async def disable_2fa(
    request: Request,
    body: Disable2FARequest,
    _admin: dict = Depends(require_admin_with_rbac),
):
    """Turn off TOTP 2FA after password confirmation."""
    security: SecurityManager = request.app.state.security_manager
    if not ADMIN_JSON.exists():
        raise HTTPException(status_code=400, detail="admin.json missing")

    with open(ADMIN_JSON, "r", encoding="utf-8") as f:
        admin_config = json.load(f)

    if not _verify_password_for_login(security, _admin["sub"], body.password):
        raise HTTPException(status_code=400, detail="Invalid password")

    admin_config.pop("totp_secret", None)
    admin_config["totp_enabled"] = False
    admin_config.pop("pending_totp_secret", None)
    if str(admin_config.get("mfa_method") or "").lower() == "totp":
        admin_config.pop("mfa_method", None)

    with open(ADMIN_JSON, "w", encoding="utf-8") as f:
        json.dump(admin_config, f, indent=2)

    return {"message": "2FA disabled successfully"}


@router.post("/change-password")
async def change_password(
    request: Request,
    body: ChangePasswordRequest,
    current_admin: dict = Depends(require_admin_with_rbac),
):
    """Change password for the logged-in account (store + legacy sync when applicable)."""
    require_not_public_demo("admin password change")
    security: SecurityManager = request.app.state.security_manager

    if len(body.new_password) < 12:
        raise HTTPException(status_code=400, detail="Password must be at least 12 characters")

    uname = current_admin.get("sub") or ""
    if not _verify_password_for_login(security, uname, body.old_password):
        raise HTTPException(status_code=400, detail="Invalid current password")

    new_hash = security.hash_password(body.new_password)
    su = aus.get_user_by_username(uname)
    if su:
        aus.update_user(str(su["id"]), password_hash=new_hash)
    cfg = _load_legacy_admin()
    legacy_name = str(cfg.get("username") or "admin").strip().lower()
    if legacy_name == aus.normalize_username(uname) and ADMIN_JSON.exists():
        cfg["password_hash"] = new_hash
        with open(ADMIN_JSON, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)

    return {"message": "Password changed successfully"}


class WebAuthnLoginOptionsRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)


class WebAuthnRegisterVerifyRequest(BaseModel):
    credential: dict
    label: str = Field(default="Passkey", max_length=64)


class WebAuthnDisableRequest(BaseModel):
    password: str


@router.post("/webauthn/login/options")
async def webauthn_login_options(body: WebAuthnLoginOptionsRequest):
    """Begin WebAuthn authentication (after password verified; second login step)."""
    from security import webauthn_admin as wa

    cfg = wa.load_admin_config()
    if not wa.webauthn_is_enabled(cfg):
        raise HTTPException(status_code=400, detail="WebAuthn 2FA is not enabled")
    try:
        options = wa.authentication_options(aus.normalize_username(body.username))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"publicKey": options}


@router.post("/webauthn/register/options")
async def webauthn_register_options(
    current_admin: dict = Depends(require_admin_with_rbac),
):
    """Begin passkey registration for the logged-in admin."""
    from security import webauthn_admin as wa

    if not wa.webauthn_enabled_globally():
        raise HTTPException(status_code=400, detail="WebAuthn is disabled on this server")
    try:
        options = wa.registration_options(current_admin["sub"])
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"publicKey": options}


@router.post("/webauthn/register/verify")
async def webauthn_register_verify(
    body: WebAuthnRegisterVerifyRequest,
    current_admin: dict = Depends(require_admin_with_rbac),
):
    """Complete passkey registration (disables TOTP when enabled)."""
    from security import webauthn_admin as wa

    try:
        return wa.verify_registration(current_admin["sub"], body.credential, label=body.label)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/webauthn/disable")
async def webauthn_disable(
    body: WebAuthnDisableRequest,
    request: Request,
    current_admin: dict = Depends(require_admin_with_rbac),
):
    """Remove all passkeys after password confirmation."""
    from security import webauthn_admin as wa

    security: SecurityManager = request.app.state.security_manager
    if not _verify_password_for_login(security, current_admin["sub"], body.password):
        raise HTTPException(status_code=400, detail="Invalid password")
    try:
        wa.disable_webauthn(password_ok=True)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"message": "WebAuthn disabled"}
