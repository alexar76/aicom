"""Sandbox preview token validation (reverse-proxy + viewer)."""

from __future__ import annotations

import secrets
from typing import Optional

from fastapi import HTTPException, Request

from web.backend.core.security import get_current_admin, security_scheme


def mint_sandbox_preview_token() -> str:
    return secrets.token_urlsafe(32)


def preview_token_from_request(request: Request, sandbox_id: str) -> Optional[str]:
    header = (request.headers.get("X-Sandbox-Preview-Token") or "").strip()
    if header:
        return header
    query = (request.query_params.get("preview_token") or "").strip()
    if query:
        return query
    cookie = (request.cookies.get(f"aicom_sbx_{sandbox_id}") or "").strip()
    return cookie or None


async def optional_admin(request: Request) -> Optional[dict]:
    """Return admin JWT payload when present; None for anonymous preview-token access."""
    try:
        credentials = await security_scheme(request)
        return await get_current_admin(request, credentials)
    except HTTPException:
        return None


async def require_sandbox_proxy_access(
    sandbox_id: str,
    request: Request,
    *,
    sandbox: dict,
) -> None:
    """Admin JWT or per-sandbox preview token required for backend/compose proxy."""
    if await optional_admin(request) is not None:
        return
    expected = (sandbox.get("preview_token") or "").strip()
    if not expected:
        raise HTTPException(status_code=403, detail="Preview access denied")
    supplied = preview_token_from_request(request, sandbox_id) or ""
    if not secrets.compare_digest(supplied.encode(), expected.encode()):
        raise HTTPException(status_code=403, detail="Invalid or missing preview token")


async def require_sandbox_view_access(
    sandbox_id: str,
    request: Request,
    *,
    sandbox: dict,
) -> None:
    """Viewer page: admin or valid preview_token query/cookie."""
    if await optional_admin(request) is not None:
        return
    expected = (sandbox.get("preview_token") or "").strip()
    if not expected:
        raise HTTPException(status_code=403, detail="Preview access denied")
    supplied = preview_token_from_request(request, sandbox_id) or ""
    if not secrets.compare_digest(supplied.encode(), expected.encode()):
        raise HTTPException(status_code=403, detail="Invalid or missing preview token")


def append_preview_token_query(url: str, token: str) -> str:
    from urllib.parse import quote

    sep = "&" if "?" in url else "?"
    return f"{url}{sep}preview_token={quote(token, safe='')}"


def sanitize_git_remote_line(line: str) -> str:
    """Strip credentials from ``git remote -v`` lines before returning to clients."""
    import re

    return re.sub(r"(https?://)[^@\s]+@", r"\1", line)
