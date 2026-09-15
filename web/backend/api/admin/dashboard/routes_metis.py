"""Metis ecosystem status for admin dashboard."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import Depends

from web.backend.core.admin_roles import require_admin_with_rbac
from web.backend.services.metis_status import build_metis_admin_status
from .helpers import _load_pipeline_products_for_metrics
from ._router import router


@router.get("/metis/status")
async def get_metis_status(_admin: dict = Depends(require_admin_with_rbac)) -> dict[str, Any]:
    """Metis deployment, factory gate config, and per-product gate usage."""
    _ = _admin
    products = await asyncio.to_thread(_load_pipeline_products_for_metrics)
    return await asyncio.to_thread(build_metis_admin_status, products=products)
