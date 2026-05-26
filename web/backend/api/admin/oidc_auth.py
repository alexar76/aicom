"""OIDC / SSO admin authentication routes."""

from __future__ import annotations

import logging
import os

from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse

from web.backend.core.admin_roles import normalize_role
from web.backend.core.oidc_auth import (
    OIDC_NONCE_COOKIE,
    OIDC_STATE_COOKIE,
    build_authorize_url,
    claims_to_username,
    exchange_code,
    map_groups_to_role,
    new_oidc_state,
    oidc_enabled,
    safe_post_login_url,
    verify_id_token,
)
from web.backend.core.security import SecurityManager
from web.backend.http.client_ip import client_ip
from web.backend.middleware.csrf import CSRF_COOKIE, CSRF_HEADER, new_csrf_token
from web.backend.services import admin_users_store as aus
from web.backend.api.admin.auth import (
    _access_token_cookie_secure,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/auth", tags=["admin-auth-oidc"])


def _issue_session(
    request: Request,
    response: Response,
    username: str,
    role: str,
) -> None:
    security: SecurityManager = request.app.state.security_manager
    token = security.create_access_token(username, role=normalize_role(role).value)
    cookie_secure = _access_token_cookie_secure(request)
    csrf = new_csrf_token()
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        secure=cookie_secure,
        samesite="lax",
        max_age=1800,
        path="/",
    )
    response.set_cookie(
        key=CSRF_COOKIE,
        value=csrf,
        httponly=False,
        secure=cookie_secure,
        samesite="strict",
        max_age=1800,
        path="/",
    )


def _sync_oidc_user(username: str, role: str) -> dict:
    """Provision or refresh OIDC user; skip role overwrite when account is disabled."""
    aus.ensure_legacy_admin_users_file()
    normalized = normalize_role(role).value
    existing = aus.get_user_by_username(username)
    if existing:
        if existing.get("enabled", True) is False:
            return existing
        if str(existing.get("role")) != normalized:
            aus.update_user(str(existing["id"]), role=normalized)
        return existing
    created = aus.create_user(
        username=username,
        password_hash="!",  # OIDC-only — password login disabled (empty hash fails verify)
        role=normalized,
    )
    return created or aus.get_user_by_username(username) or {}


@router.get("/oidc/status")
async def oidc_status():
    return {
        "enabled": oidc_enabled(),
        "issuer": (os.environ.get("AIFACTORY_OIDC_ISSUER") or "").strip() or None,
    }


@router.get("/oidc/login")
async def oidc_login():
    if not oidc_enabled():
        raise HTTPException(status_code=404, detail="OIDC not enabled")
    state, nonce = new_oidc_state()
    url = build_authorize_url(state, nonce)
    resp = RedirectResponse(url=url, status_code=302)
    resp.set_cookie(OIDC_STATE_COOKIE, state, httponly=True, samesite="lax", max_age=600, path="/")
    resp.set_cookie(OIDC_NONCE_COOKIE, nonce, httponly=True, samesite="lax", max_age=600, path="/")
    return resp


@router.get("/oidc/callback")
async def oidc_callback(request: Request, code: str = "", state: str = ""):
    if not oidc_enabled():
        raise HTTPException(status_code=404, detail="OIDC not enabled")
    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code")

    expected_state = request.cookies.get(OIDC_STATE_COOKIE, "")
    nonce = request.cookies.get(OIDC_NONCE_COOKIE, "")
    if not expected_state or state != expected_state:
        raise HTTPException(status_code=400, detail="Invalid OIDC state")

    try:
        tokens = exchange_code(code)
        id_token = tokens.get("id_token")
        if not id_token:
            raise ValueError("token response missing id_token")
        claims = verify_id_token(id_token, nonce)
    except Exception as exc:
        logger.warning("OIDC callback failed: %s", exc)
        raise HTTPException(status_code=401, detail="OIDC authentication failed") from exc

    username = claims_to_username(claims)
    groups = claims.get("groups") or claims.get("roles") or []
    if isinstance(groups, str):
        groups = [groups]
    role = map_groups_to_role([str(g) for g in groups]) if groups else (
        os.environ.get("AIFACTORY_OIDC_DEFAULT_ROLE") or "viewer"
    )
    row = _sync_oidc_user(username, role)
    if not row.get("enabled", True):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")

    session_role = str(row.get("role") or role)
    resp = RedirectResponse(url=safe_post_login_url(os.environ.get("AIFACTORY_OIDC_POST_LOGIN_URL")), status_code=302)
    _issue_session(request, resp, username, session_role)
    resp.delete_cookie(OIDC_STATE_COOKIE, path="/")
    resp.delete_cookie(OIDC_NONCE_COOKIE, path="/")
    security: SecurityManager = request.app.state.security_manager
    security.record_login_attempt(client_ip(request), True, username)
    return resp
