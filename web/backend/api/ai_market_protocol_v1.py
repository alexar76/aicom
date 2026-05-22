"""
AI Market Protocol v1 API
=========================
Discovery, MCP manifest, HTTP 402 invoke, channels, pipelines.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Header, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from web.backend.services.ai_market_protocol import (
    build_manifest,
    build_well_known,
    close_channel,
    discover_capabilities,
    execute_pipeline,
    get_receipt,
    invoke_capability_v1,
    list_recent_stats,
    open_channel,
    quote_capability_price,
)
from web.backend.services.ai_market_protocol.config import base_public_url

wellknown_router = APIRouter(tags=["ai-market-wellknown"])
capabilities_router = APIRouter(tags=["ai-market-capabilities"])
# No prefix here — mounted under ``/ai-market`` via ``ai_market.router``.
router = APIRouter(tags=["ai-market-v1"])


class DiscoverRequest(BaseModel):
    query: str = Field("", max_length=4000)
    budget_usd: float | None = Field(None, ge=0, le=100_000)
    constraints: dict[str, Any] = Field(default_factory=dict)
    limit: int = Field(8, ge=1, le=32)


class ChannelOpenRequest(BaseModel):
    deposit_usd: float = Field(..., gt=0, le=10_000)
    token: str | None = Field(None, max_length=16)
    chain: str | None = Field(None, max_length=32)
    wallet: str = Field("", max_length=128)
    tx_hash: str = Field("", max_length=128)


class ChannelCloseRequest(BaseModel):
    channel_id: str = Field(..., min_length=8, max_length=64)
    settle_tx_hash: str = Field("", max_length=128)


class PipelineNode(BaseModel):
    id: str = Field("", max_length=64)
    product_id: str = Field(..., min_length=5, max_length=80)
    capability_id: str = Field(..., min_length=2, max_length=80)
    input: dict[str, Any] = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list)
    input_from: str | None = Field(None, max_length=64)


class PipelineRequest(BaseModel):
    nodes: list[PipelineNode] = Field(..., min_length=1, max_length=16)
    channel_id: str | None = Field(None, max_length=64)


class InvokeBody(BaseModel):
    input: dict[str, Any] = Field(default_factory=dict)


def _get_llm_router(request: Request) -> Any:
    return getattr(request.app.state, "llm_router", None)


@wellknown_router.get("/.well-known/ai-market.json")
async def well_known_manifest():
    return build_well_known()


@router.get("/manifest")
async def get_manifest():
    return build_manifest(base_url=base_public_url())


@router.get("/mcp")
async def mcp_tools_list():
    m = build_manifest(base_url=base_public_url())
    tools = []
    for t in m.get("tools") or []:
        tools.append({
            "name": t["name"],
            "description": t.get("description", ""),
            "inputSchema": t.get("input_schema") or {},
        })
    return {"protocol": "mcp", "version": "1.0", "tools": tools}


@router.post("/discover")
async def discover(body: DiscoverRequest, request: Request):
    return await discover_capabilities(
        query=body.query,
        budget_usd=body.budget_usd,
        constraints=body.constraints,
        limit=body.limit,
        llm_router=_get_llm_router(request),
    )


@router.get("/pricing/{product_id}/{capability_id}")
async def pricing(
    product_id: str,
    capability_id: str,
    input_size: int = 0,
):
    return quote_capability_price(
        product_id=product_id,
        capability_id=capability_id,
        input_size=input_size,
    )


@router.post("/pricing/{product_id}/{capability_id}")
async def pricing_post(product_id: str, capability_id: str, body: InvokeBody):
    return quote_capability_price(
        product_id=product_id,
        capability_id=capability_id,
        input_payload=body.input,
    )


@router.post("/channel/open")
async def channel_open(body: ChannelOpenRequest):
    out = open_channel(
        deposit_usd=body.deposit_usd,
        token=body.token,
        chain=body.chain,
        wallet=body.wallet,
        tx_hash=body.tx_hash,
    )
    if out.get("error"):
        return JSONResponse(status_code=400, content=out)
    return out


@router.post("/channel/close")
async def channel_close(body: ChannelCloseRequest):
    out = close_channel(channel_id=body.channel_id, settle_tx_hash=body.settle_tx_hash)
    if out.get("error"):
        return JSONResponse(status_code=400, content=out)
    return out


@router.post("/pipelines")
async def run_pipeline(body: PipelineRequest, request: Request):
    nodes = [n.model_dump() for n in body.nodes]
    return await execute_pipeline(
        nodes=nodes,
        channel_id=body.channel_id,
        base_url=base_public_url(),
        llm_router=_get_llm_router(request),
    )


@router.get("/receipt/{nonce}")
async def receipt(nonce: str):
    r = get_receipt(nonce)
    if not r:
        return JSONResponse(status_code=404, content={"detail": "receipt not found"})
    return r


@router.get("/stats")
async def stats(limit: int = 50):
    return {"events": list_recent_stats(limit=min(limit, 200)), "protocol_version": "v1"}


@capabilities_router.post("/capabilities/{product_id}/{capability_id}/invoke")
async def invoke_capability_root(
    product_id: str,
    capability_id: str,
    body: InvokeBody,
    request: Request,
    x_payment: str | None = Header(default=None, alias="X-Payment"),
    x_payment_channel: str | None = Header(default=None, alias="X-Payment-Channel"),
    x_ai_market_license: str | None = Header(default=None, alias="x-ai-market-license"),
):
    status, payload, headers = await invoke_capability_v1(
        product_id=product_id,
        capability_id=capability_id,
        body_input=body.input,
        base_url=str(request.base_url).rstrip("/"),
        x_payment=x_payment,
        x_payment_channel=x_payment_channel,
        x_ai_market_license=x_ai_market_license,
        llm_router=_get_llm_router(request),
    )
    return JSONResponse(status_code=status, content=payload, headers=headers)


@router.post("/capabilities/{product_id}/{capability_id}/invoke")
async def invoke_capability_prefixed(
    product_id: str,
    capability_id: str,
    body: InvokeBody,
    request: Request,
    x_payment: str | None = Header(default=None, alias="X-Payment"),
    x_payment_channel: str | None = Header(default=None, alias="X-Payment-Channel"),
    x_ai_market_license: str | None = Header(default=None, alias="x-ai-market-license"),
):
    return await invoke_capability_root(
        product_id, capability_id, body, request,
        x_payment, x_payment_channel, x_ai_market_license,
    )
