"""
Admin API — upload / delete neural UI reference templates (vanilla HTML/CSS/JS shells).
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.paths import data_root as factory_data_root
from web.backend.core.admin_roles import require_admin_with_rbac
from web.backend.core.http_errors import client_error_detail
from web.backend.services.reference_templates import (
    delete_reference_template_dir,
    list_reference_templates_catalog,
    upsert_reference_template_upload,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/admin/reference-templates",
    tags=["admin-reference-templates"],
    dependencies=[Depends(require_admin_with_rbac)],
)


class TemplateFilePayload(BaseModel):
    path: str = Field(..., description="index.html | style.css | app.js")
    content: str = Field("", description="UTF-8 text")


class ReferenceTemplateUpsertPayload(BaseModel):
    template_id: str = Field(..., min_length=1, max_length=64)
    title: Optional[str] = Field(None, max_length=200)
    files: list[TemplateFilePayload] = Field(..., min_length=1)


@router.post("")
async def upsert_reference_template(body: ReferenceTemplateUpsertPayload):
    try:
        tuples = [(f.path, f.content) for f in body.files]
        manifest = upsert_reference_template_upload(
            factory_data_root(),
            body.template_id,
            body.title,
            tuples,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=client_error_detail(e)) from e
    catalog = list_reference_templates_catalog(factory_data_root())
    return {
        "ok": True,
        "template_id": body.template_id.strip(),
        "manifest_template_count": len(manifest.get("templates") or []),
        "catalog": catalog,
    }


@router.delete("/{template_id}")
async def remove_reference_template(template_id: str):
    try:
        ok = delete_reference_template_dir(factory_data_root(), template_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=client_error_detail(e)) from e
    if not ok:
        raise HTTPException(status_code=404, detail="template not found")
    catalog = list_reference_templates_catalog(factory_data_root())
    return {"ok": True, "catalog": catalog}

