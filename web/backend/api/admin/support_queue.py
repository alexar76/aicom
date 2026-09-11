"""
Admin API: business escalations from public support (Director queue JSONL).
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from web.backend.core.admin_roles import require_admin_with_rbac
from web.backend.services.support_pipeline import (
    list_director_escalations,
    mark_escalation_resolved,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/admin/support-queue",
    tags=["admin-support-queue"],
    dependencies=[Depends(require_admin_with_rbac)],
)


class ResolveEscalationBody(BaseModel):
    notes: str = Field(default="", max_length=4000)


@router.get("")
async def list_queue(status: Optional[str] = None, limit: int = 100):
    items = list_director_escalations(limit=min(limit, 500), status=status)
    open_items = list_director_escalations(limit=500, status="open")
    return {"items": items, "open_count": len(open_items)}


@router.post("/{escalation_id}/resolve")
async def resolve_escalation(escalation_id: str, body: ResolveEscalationBody):
    ok = mark_escalation_resolved(escalation_id, notes=body.notes)
    if not ok:
        raise HTTPException(status_code=404, detail="Escalation not found or already resolved")
    logger.info("Escalation %s resolved by admin", escalation_id)
    return {"ok": True, "id": escalation_id}
