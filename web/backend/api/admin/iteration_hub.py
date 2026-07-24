"""Iteration hub: user templates, pattern library, iteration canvas, AI prefill, Web Push."""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from web.backend.core.admin_roles import require_admin_with_rbac
from web.backend.services import idea_prefill_llm
from web.backend.services import product_iteration_canvas
from web.backend.services import user_iteration_templates
from web.backend.services import user_pattern_library
from web.backend.services import web_push_service

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/admin/iteration-hub",
    tags=["iteration-hub"],
    dependencies=[Depends(require_admin_with_rbac)],
)


class UserTemplateUpsert(BaseModel):
    id: Optional[str] = None
    name: str = Field("", max_length=400)
    delivery_profile: str = Field("infer", max_length=64)
    production_mode: bool = False
    instructions: str = Field("", max_length=32000)


class PatternUpsert(BaseModel):
    id: Optional[str] = None
    name: str = Field("", max_length=400)
    tags: list[str] = Field(default_factory=list)
    document: dict[str, Any] = Field(default_factory=dict)


class IterationCanvasPut(BaseModel):
    version: int = 1
    nodes: list[Any]
    edges: list[Any]


class PrefillBody(BaseModel):
    idea: str = Field("", max_length=16000)
    consent: bool = False


class WebPushSubscribeBody(BaseModel):
    endpoint: str
    keys: dict[str, str]
    userAgent: Optional[str] = None


class WebPushTestBody(BaseModel):
    title: str = "AI Factory"
    body: str = "Test notification"
    url: str = "/admin"


@router.get("/user-templates")
async def list_user_templates():
    return {"templates": user_iteration_templates.list_templates()}


@router.post("/user-templates")
async def upsert_user_template(body: UserTemplateUpsert):
    rec = user_iteration_templates.upsert_template(
        template_id=body.id,
        name=body.name,
        delivery_profile=body.delivery_profile,
        production_mode=body.production_mode,
        instructions=body.instructions,
    )
    return {"template": rec}


@router.delete("/user-templates/{template_id}")
async def delete_user_template(template_id: str):
    ok = user_iteration_templates.delete_template(template_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Template not found")
    return {"ok": True}


@router.get("/patterns")
async def list_patterns():
    return {"patterns": user_pattern_library.list_patterns()}


@router.post("/patterns")
async def upsert_pattern(body: PatternUpsert):
    rec = user_pattern_library.upsert_pattern(
        pattern_id=body.id,
        name=body.name,
        tags=body.tags,
        document=body.document,
    )
    return {"pattern": rec}


@router.delete("/patterns/{pattern_id}")
async def delete_pattern(pattern_id: str):
    ok = user_pattern_library.delete_pattern(pattern_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Pattern not found")
    return {"ok": True}


@router.get("/products/{product_id}/iteration-canvas")
async def get_iteration_canvas(product_id: str):
    return product_iteration_canvas.get_canvas(product_id)


@router.put("/products/{product_id}/iteration-canvas")
async def put_iteration_canvas(product_id: str, body: IterationCanvasPut):
    try:
        doc = product_iteration_canvas.put_canvas(
            product_id,
            {"version": body.version, "nodes": body.nodes, "edges": body.edges},
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return doc


@router.post("/prefill-from-idea")
async def prefill_from_idea(body: PrefillBody, request: Request):
    if not body.consent:
        raise HTTPException(status_code=400, detail="consent must be true to call the LLM")
    router_llm = getattr(request.app.state, "llm_router", None)
    result = await idea_prefill_llm.prefill_from_idea(body.idea, router_llm)
    return result


@router.get("/web-push/vapid-public")
async def web_push_vapid_public():
    try:
        key = web_push_service.vapid_public_key()
    except Exception as e:
        logger.warning("web_push vapid: %s", e)
        raise HTTPException(status_code=503, detail="Could not prepare VAPID keys") from e
    return {"publicKey": key}


@router.post("/web-push/subscribe")
async def web_push_subscribe(body: WebPushSubscribeBody):
    try:
        row = web_push_service.add_subscription(
            {
                "endpoint": body.endpoint,
                "keys": body.keys,
                "userAgent": body.userAgent or "",
            }
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True, "subscription": row}


@router.get("/web-push/subscriptions")
async def web_push_list_subs():
    return {"subscriptions": web_push_service.list_subscriptions()}


@router.post("/web-push/test")
async def web_push_test(body: WebPushTestBody):
    return web_push_service.broadcast_payload(title=body.title, body=body.body, url=body.url)
