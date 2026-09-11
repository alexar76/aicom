from __future__ import annotations

from fastapi import APIRouter, Depends

from web.backend.core.admin_roles import require_admin_with_rbac
from web.backend.services.release_cockpit import evaluate_release_cockpit, execute_release_protocol

router = APIRouter(prefix="/api/admin/release", tags=["admin-release"], dependencies=[Depends(require_admin_with_rbac)])


@router.get("/cockpit/{product_id}")
async def release_cockpit(product_id: str):
    return evaluate_release_cockpit(product_id)


@router.post("/protocol/{product_id}/execute")
async def release_protocol_execute(product_id: str):
    return execute_release_protocol(product_id)

