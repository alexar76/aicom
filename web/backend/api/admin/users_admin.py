"""Admin user CRUD — super_admin only (enforced also by RBAC)."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from web.backend.core.admin_roles import AdminRole, ROLE_DESCRIPTIONS, require_admin_with_rbac
from web.backend.core.security import SecurityManager
from web.backend.services import admin_users_store as store
from web.backend.services.public_demo_guard import require_not_public_demo
from web.backend.core.http_errors import client_error_detail

router = APIRouter(
    prefix="/api/admin/users",
    tags=["admin-users"],
    dependencies=[Depends(require_admin_with_rbac)],
)

# Stable order for UI (declare static routes before /{user_id} handlers).
_ROLE_ORDER: tuple[AdminRole, ...] = (
    AdminRole.VIEWER,
    AdminRole.OPERATOR,
    AdminRole.ADMIN,
    AdminRole.SUPER_ADMIN,
)


class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    password: str = Field(..., min_length=12, max_length=256)
    role: AdminRole


class UserUpdate(BaseModel):
    role: Optional[AdminRole] = None
    enabled: Optional[bool] = None


class UserPasswordReset(BaseModel):
    new_password: str = Field(..., min_length=12, max_length=256)


@router.get("/roles/meta")
async def roles_meta(_admin: dict = Depends(require_admin_with_rbac)):
    """Role ids and English descriptions for the admin Users UI (super_admin only)."""
    _ = _admin
    return {
        "roles": [
            {
                "id": r.value,
                "label": r.value.replace("_", " ").title(),
                "description": ROLE_DESCRIPTIONS[r],
            }
            for r in _ROLE_ORDER
        ]
    }


@router.get("")
async def list_users(_admin: dict = Depends(require_admin_with_rbac)):
    _ = _admin
    return {"users": store.list_users_public()}


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_user(request: Request, body: UserCreate, admin: dict = Depends(require_admin_with_rbac)):
    require_not_public_demo("admin user management")
    security: SecurityManager = request.app.state.security_manager
    try:
        store.validate_username(body.username)
        row = store.create_user(
            username=body.username,
            password_hash=security.hash_password(body.password),
            role=body.role.value,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=client_error_detail(e)) from e
    pub = {k: v for k, v in row.items() if k != "password_hash"}
    try:
        from web.backend.services.admin_action_log import log_admin_action_from_request

        log_admin_action_from_request(
            request,
            admin,
            action="user_created",
            resource=f"admin/users/{pub.get('id')}",
            details={"username": pub.get("username"), "role": pub.get("role")},
        )
    except Exception:
        pass
    return pub


@router.patch("/{user_id}")
async def patch_user(
    user_id: str,
    request: Request,
    body: UserUpdate,
    admin: dict = Depends(require_admin_with_rbac),
):
    require_not_public_demo("admin user management")
    try:
        kw: dict = {}
        if body.role is not None:
            kw["role"] = body.role.value
        if body.enabled is not None:
            kw["enabled"] = body.enabled
        if not kw:
            raise HTTPException(status_code=400, detail="No fields to update")
        store.update_user(user_id, **kw)
    except LookupError:
        raise HTTPException(status_code=404, detail="User not found") from None
    except ValueError as e:
        raise HTTPException(status_code=400, detail=client_error_detail(e)) from e
    u = store.get_user_by_id(user_id)
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    try:
        from web.backend.services.admin_action_log import log_admin_action_from_request

        log_admin_action_from_request(
            request,
            admin,
            action="user_updated",
            resource=f"admin/users/{user_id}",
            details={"fields": list(kw.keys())},
        )
    except Exception:
        pass
    return {k: v for k, v in u.items() if k != "password_hash"}


@router.post("/{user_id}/password")
async def reset_user_password(
    request: Request,
    user_id: str,
    body: UserPasswordReset,
    admin: dict = Depends(require_admin_with_rbac),
):
    """Super-admin sets a new password for another admin panel user."""
    require_not_public_demo("admin user management")
    security: SecurityManager = request.app.state.security_manager
    try:
        store.update_user(user_id, password_hash=security.hash_password(body.new_password))
    except LookupError:
        raise HTTPException(status_code=404, detail="User not found") from None
    except ValueError as e:
        raise HTTPException(status_code=400, detail=client_error_detail(e)) from e
    u = store.get_user_by_id(user_id)
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    try:
        from web.backend.services.admin_action_log import log_admin_action_from_request

        log_admin_action_from_request(
            request,
            admin,
            action="user_password_reset",
            resource=f"admin/users/{user_id}",
            details={"username": u.get("username")},
        )
    except Exception:
        pass
    return {"ok": True, "username": u.get("username")}


@router.delete("/{user_id}")
async def remove_user(user_id: str, request: Request, admin: dict = Depends(require_admin_with_rbac)):
    require_not_public_demo("admin user management")
    try:
        store.delete_user(user_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="User not found") from None
    except ValueError as e:
        raise HTTPException(status_code=400, detail=client_error_detail(e)) from e
    try:
        from web.backend.services.admin_action_log import log_admin_action_from_request

        log_admin_action_from_request(
            request,
            admin,
            action="user_deleted",
            resource=f"admin/users/{user_id}",
            details={},
        )
    except Exception:
        pass
    return {"ok": True}
