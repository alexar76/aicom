"""Admin funnel analytics dashboard."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from web.backend.core.admin_roles import require_admin_with_rbac
from web.backend.services.funnel_analytics import build_funnel_metrics
from web.backend.services.funnel_store import list_leads

router = APIRouter(
    prefix="/api/admin/funnel",
    tags=["admin-funnel"],
    dependencies=[Depends(require_admin_with_rbac)],
)


@router.get("/dashboard")
async def funnel_dashboard(window_hours: int = Query(168, ge=1, le=720)):
    metrics = build_funnel_metrics(window_hours=window_hours)
    leads = list_leads(limit=100)
    return {"metrics": metrics, "recent_leads": leads[:50]}
