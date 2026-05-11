"""
Admin panel RBAC
================
Roles (least → most privilege):

- viewer: read-only operational dashboard (pipeline, agents, logs, metrics).
          Cannot open LLM provider secrets, security audit, or platform settings.
- operator: runs the factory — queue products, pipeline actions, discovery triggers.
            Cannot change providers, platform settings, security, methodology admin API,
            or manage admin users.
- admin: full configuration except creating/deleting admin accounts (providers, settings,
         methodology, Director triggers, etc.).
- super_admin: user management (/api/admin/users) + everything else.

Legacy JWTs without a `role` claim are treated as super_admin so existing installs keep working.
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

from fastapi import Depends, HTTPException, Request, status

if TYPE_CHECKING:
    pass

from web.backend.core.security import get_current_admin


class AdminRole(str, Enum):
    VIEWER = "viewer"
    OPERATOR = "operator"
    ADMIN = "admin"
    SUPER_ADMIN = "super_admin"


ROLE_RANK: dict[AdminRole, int] = {
    AdminRole.VIEWER: 1,
    AdminRole.OPERATOR: 2,
    AdminRole.ADMIN: 3,
    AdminRole.SUPER_ADMIN: 4,
}

ROLE_DESCRIPTIONS: dict[AdminRole, str] = {
    AdminRole.VIEWER: "Read-only: dashboards and pipeline status (no secrets).",
    AdminRole.OPERATOR: "Run pipeline & queue products; cannot edit providers or platform settings.",
    AdminRole.ADMIN: "Configure providers, security, settings, methodology — not admin accounts.",
    AdminRole.SUPER_ADMIN: "Full access including creating/removing admin users.",
}


def normalize_role(value: str | None) -> AdminRole:
    if not value:
        return AdminRole.SUPER_ADMIN
    try:
        return AdminRole(str(value).strip().lower())
    except ValueError:
        return AdminRole.SUPER_ADMIN


def rank(role: AdminRole) -> int:
    return ROLE_RANK.get(role, 1)


# GET paths viewers must not access (secrets / privileged config).
VIEWER_BLOCKED_GET_PREFIXES: tuple[str, ...] = (
    "/api/admin/providers",
    "/api/admin/llm-pricing",
    "/api/admin/security",
    "/api/admin/settings",
    "/api/admin/config",
    "/api/admin/methodology",
    "/api/admin/demo-replay",
    "/api/admin/chat/settings",
    "/api/admin/release",
    "/api/admin/reference-templates",
)

# Non-GET requests operators cannot perform (prefix match).
OPERATOR_WRITE_DENIED_PREFIXES: tuple[str, ...] = (
    "/api/admin/users",
    "/api/admin/providers",
    "/api/admin/llm-pricing",
    "/api/admin/security",
    "/api/admin/settings",
    "/api/admin/config/",
    "/api/admin/methodology",
    "/api/admin/demo-replay",
    "/api/admin/chat/settings",
    "/api/admin/release",
    "/api/admin/reference-templates",
    "/api/admin/feedback",
)

# Auth endpoints restricted to admin+ (platform owner actions on legacy admin.json).
ADMIN_ONLY_AUTH_POST_PATHS: frozenset[str] = frozenset(
    {
        "/api/admin/auth/setup-2fa",
        "/api/admin/auth/verify-2fa",
        "/api/admin/auth/disable-2fa",
        "/api/admin/auth/cancel-2fa-setup",
    }
)


def _path_under(path: str, prefix: str) -> bool:
    return path == prefix or path.startswith(prefix + "/")


def check_admin_rbac(request: Request, admin: dict) -> dict:
    """Raise 403 if this admin role may not access the request."""
    role = normalize_role(admin.get("role"))
    method = request.method.upper()
    path = request.url.path

    if path.startswith("/api/admin/users"):
        if role != AdminRole.SUPER_ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Managing admin users requires super_admin role",
            )
        return admin

    if role == AdminRole.VIEWER:
        if method != "GET":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Read-only role cannot modify data",
            )
        for prefix in VIEWER_BLOCKED_GET_PREFIXES:
            if _path_under(path, prefix):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Insufficient permissions for this resource",
                )
        return admin

    if role == AdminRole.OPERATOR:
        if method != "GET" and method != "HEAD":
            for prefix in OPERATOR_WRITE_DENIED_PREFIXES:
                if _path_under(path, prefix):
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Operator role cannot modify this resource",
                    )
            if path in ADMIN_ONLY_AUTH_POST_PATHS:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Admin role required for this action",
                )
        return admin

    if role == AdminRole.ADMIN:
        if path in ADMIN_ONLY_AUTH_POST_PATHS:
            return admin
        return admin

    return admin


async def require_admin_with_rbac(
    request: Request,
    admin: dict = Depends(get_current_admin),
) -> dict:
    return check_admin_rbac(request, admin)
