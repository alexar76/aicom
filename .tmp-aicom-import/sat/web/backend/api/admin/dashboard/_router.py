"""Shared admin dashboard FastAPI router."""

from fastapi import APIRouter, Depends

from web.backend.core.admin_roles import require_admin_with_rbac

router = APIRouter(
    prefix="/api/admin",
    tags=["admin-dashboard"],
    dependencies=[Depends(require_admin_with_rbac)],
)
