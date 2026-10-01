"""Admin panel user action log API."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from web.backend.core.admin_roles import AdminRole, normalize_role, require_admin_with_rbac
from web.backend.services import admin_users_store as store
from web.backend.services.admin_action_log import query_admin_actions

router = APIRouter(
    prefix="/api/admin/action-log",
    tags=["admin-action-log"],
    dependencies=[Depends(require_admin_with_rbac)],
)


@router.get("/me")
async def my_action_log(
    admin: dict = Depends(require_admin_with_rbac),
    limit: int = Query(100, ge=1, le=500),
    since: Optional[float] = Query(None),
):
    """Current admin user's recent actions."""
    username = str(admin.get("sub") or admin.get("username") or "").strip().lower()
    rows, total = query_admin_actions(username=username, limit=limit, since=since)
    return {"username": username, "entries": rows, "total_matched": total, "limit": limit}


@router.get("/users/{user_id}")
async def user_action_log(
    user_id: str,
    admin: dict = Depends(require_admin_with_rbac),
    limit: int = Query(100, ge=1, le=500),
    since: Optional[float] = Query(None),
):
    """Action log for a specific admin account (super_admin only)."""
    role = normalize_role(admin.get("role"))
    if role != AdminRole.SUPER_ADMIN:
        raise HTTPException(status_code=403, detail="Only super_admin can view other users' action logs")

    user = store.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    username = str(user.get("username") or "").strip().lower()
    rows, total = query_admin_actions(
        username=username,
        user_id=user_id,
        limit=limit,
        since=since,
    )
    return {
        "user_id": user_id,
        "username": username,
        "entries": rows,
        "total_matched": total,
        "limit": limit,
    }
