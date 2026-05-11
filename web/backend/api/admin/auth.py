"""
Admin Authentication API
========================
Handles admin login, 2FA setup, and session management.
Supports multi-user accounts (admin_users.json) + legacy admin.json for TOTP metadata.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from web.backend.core.admin_roles import normalize_role, require_admin_with_rbac
from web.backend.core.security import SecurityManager
from web.backend.services import admin_users_store as aus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/auth", tags=["admin-auth"])

ADMIN_JSON = Path("/app/data/config/admin.json")


class LoginRequest(BaseModel):
    username: str = Field(default="admin", min_length=1, max_length=64)
    password: str = Field(..., min_length=1)
    totp_code: Optional[str] = None


class Setup2FARequest(BaseModel):
    password: str


class Verify2FARequest(BaseModel):
    code: str


class Disable2FARequest(BaseModel):
    password: str


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


def _admin_twofa_flags() -> tuple[bool, bool]:
    """(totp_enabled, totp_pending_setup)."""
    cfg = _load_legacy_admin()
    enabled = bool(cfg.get("totp_enabled") and cfg.get("totp_secret"))
    pending = bool(cfg.get("pending_totp_secret"))
    return enabled, pending


@router.post("/login")
async def admin_login(request: Request, response: Response, login_data: LoginRequest):
    """Authenticate admin user (multi-user store + legacy admin.json)."""
    security: SecurityManager = request.app.state.security_manager
    client_ip = request.client.host if request.client else "unknown"

    aus.ensure_legacy_admin_users_file()

    if not aus.list_users_public():
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Admin not configured. Run 'ai-company init' first.",
        )

    if not security.check_login_attempts(client_ip):
        security.record_login_attempt(client_ip, False, login_data.username)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Please try again later.",
        )

    if not _verify_password_for_login(security, login_data.username, login_data.password):
        security.record_login_attempt(client_ip, False, login_data.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    cfg = _load_legacy_admin()
    if _legacy_totp_applies(login_data.username):
        secret = cfg.get("totp_secret")
        if not login_data.totp_code:
            security.record_login_attempt(client_ip, False, login_data.username)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="2FA code required",
            )
        if not secret or not security.verify_totp(secret, login_data.totp_code):
            security.record_login_attempt(client_ip, False, login_data.username)
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
    security.record_login_attempt(client_ip, True, login_data.username)

    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=1800,
    )

    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": 1800,
        "role": normalize_role(role_str).value,
    }


@router.post("/logout")
async def admin_logout(response: Response):
    """Logout admin user."""
    response.delete_cookie("access_token")
    return {"message": "Logged out successfully"}


@router.get("/me")
async def get_current_admin_info(
    current_admin: dict = Depends(require_admin_with_rbac),
):
    """Get current admin info."""
    totp_enabled, totp_pending = _admin_twofa_flags()
    r = current_admin.get("role")
    return {
        "username": current_admin.get("sub"),
        "is_admin": current_admin.get("admin", False),
        "role": normalize_role(r).value if r else normalize_role(None).value,
        "totp_enabled": totp_enabled,
        "totp_pending": totp_pending,
    }


@router.post("/setup-2fa")
async def setup_2fa(
    request: Request,
    setup_data: Setup2FARequest,
    current_admin: dict = Depends(require_admin_with_rbac),
):
    """Setup 2FA — metadata stored in legacy admin.json."""
    security: SecurityManager = request.app.state.security_manager
    if not ADMIN_JSON.exists():
        raise HTTPException(status_code=500, detail="admin.json missing")

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
    admin_config.pop("pending_totp_secret", None)

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

    with open(ADMIN_JSON, "w", encoding="utf-8") as f:
        json.dump(admin_config, f, indent=2)

    return {"message": "2FA disabled successfully"}


@router.post("/change-password")
async def change_password(
    request: Request,
    old_password: str,
    new_password: str,
    current_admin: dict = Depends(require_admin_with_rbac),
):
    """Change password for the logged-in account (store + legacy sync when applicable)."""
    security: SecurityManager = request.app.state.security_manager

    if len(new_password) < 12:
        raise HTTPException(status_code=400, detail="Password must be at least 12 characters")

    uname = current_admin.get("sub") or ""
    if not _verify_password_for_login(security, uname, old_password):
        raise HTTPException(status_code=400, detail="Invalid current password")

    new_hash = security.hash_password(new_password)
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
