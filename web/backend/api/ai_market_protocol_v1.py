"""
AI Market Protocol v1 API
=========================
Discovery, MCP manifest, HTTP 402 invoke, channels, pipelines.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
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
from web.backend.core.admin_roles import AdminRole, normalize_role, require_admin_with_rbac
from web.backend.services.ai_market_protocol.channels import (
    list_outstanding_refunds,
    list_unfulfilled_payments,
    mark_refund_settled,
)
from web.backend.services.ai_market_protocol.config import base_public_url
from web.backend.services.ai_market_protocol.rate_limits import enforce_discover_limit, enforce_invoke_limits
from web.backend.services.customer_auth import require_customer

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
    # EIP-191 proof that the caller controls the wallet that paid the deposit.
    # channels.open_channel refuses without it whenever on_chain.require_payer_proof()
    # is on (production), so a transport that cannot carry it makes every production
    # channel open fail with `deposit_proof_required`.
    signature: str = Field("", max_length=256)


class ChannelCloseRequest(BaseModel):
    channel_id: str = Field(..., min_length=8, max_length=64)
    settle_tx_hash: str = Field("", max_length=128)


class RefundSettledRequest(BaseModel):
    """Operator attestation that an outstanding refund obligation was paid."""
    channel_id: str = Field(..., min_length=8, max_length=64)
    settle_tx_hash: str = Field(..., min_length=8, max_length=128)


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
    channel_secret: str | None = Field(None, max_length=128)


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
    enforce_discover_limit(request)
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
async def channel_open(body: ChannelOpenRequest, customer: dict = Depends(require_customer)):
    out = open_channel(
        deposit_usd=body.deposit_usd,
        token=body.token,
        chain=body.chain,
        wallet=body.wallet,
        tx_hash=body.tx_hash,
        customer_id=str(customer.get("sub") or ""),
        customer_email=str(customer.get("email") or ""),
        signature=body.signature,
    )
    if out.get("error"):
        return JSONResponse(status_code=400, content=out)
    return out


@router.post("/channel/close")
async def channel_close(body: ChannelCloseRequest, customer: dict = Depends(require_customer)):
    out = close_channel(
        channel_id=body.channel_id,
        settle_tx_hash=body.settle_tx_hash,
        customer_id=str(customer.get("sub") or ""),
    )
    if out.get("error"):
        return JSONResponse(status_code=400, content=out)
    return out


# ── Operator liability surface ───────────────────────────────────────────────
#
# Closing a channel (and consuming a one-off payment whose delivery then failed)
# records a DEBT to the customer rather than moving funds — nothing in this package
# can send value. The services recorded those debts but nothing exposed them, so an
# operator could neither see who was owed what nor write a payout off after making
# it. These routes are that surface, and they are admin-gated because a row names a
# customer, their email, their wallet and their balance.


def _require_liability_admin(admin: dict = Depends(require_admin_with_rbac)) -> dict:
    """Admin+ for the liability ledger — a viewer must not read customer wallets.

    ``require_admin_with_rbac`` alone would admit a read-only VIEWER on GET, because
    its blocked-prefix list is scoped to ``/api/admin/*`` and these routes live under
    ``/ai-market``. Operator-and-below are excluded on purpose: this is finance data,
    not operational dashboarding.
    """
    if normalize_role(admin.get("role")) not in (AdminRole.ADMIN, AdminRole.SUPER_ADMIN):
        raise HTTPException(
            status_code=403, detail="admin role required for the liability ledger"
        )
    return admin


@router.get("/admin/refunds/outstanding")
async def outstanding_refunds(admin: dict = Depends(_require_liability_admin)):
    """Channel remainders and consumed-but-undelivered payments still owed."""
    refunds = list_outstanding_refunds()
    unfulfilled = list_unfulfilled_payments()
    return {
        "outstanding_refunds": refunds,
        "outstanding_refunds_usd": round(sum(float(r.get("owed_usd") or 0) for r in refunds), 4),
        "unfulfilled_payments": unfulfilled,
        "unfulfilled_payments_usd": round(
            sum(float(p.get("amount_usd") or 0) for p in unfulfilled), 4
        ),
        "note": (
            "Recorded debts. This service never moves funds: pay out-of-band, then "
            "POST /ai-market/admin/refunds/settled with the payout transaction."
        ),
        "protocol_version": "v1",
    }


@router.post("/admin/refunds/settled")
async def settle_refund(
    body: RefundSettledRequest, admin: dict = Depends(_require_liability_admin)
):
    """Clear a refund obligation with a VERIFIED outbound payout transaction.

    ``mark_refund_settled`` re-verifies the hash in the direction the money actually
    travels (an allowed payout wallet → the recorded depositor) before clearing
    anything, so this route cannot write a debt off on the operator's word alone.
    """
    out = mark_refund_settled(
        channel_id=body.channel_id,
        settle_tx_hash=body.settle_tx_hash,
        operator_id=str(admin.get("sub") or admin.get("username") or ""),
    )
    if not out.get("ok"):
        return JSONResponse(status_code=400, content={**out, "protocol_version": "v1"})
    return {**out, "protocol_version": "v1"}


@router.post("/pipelines")
async def run_pipeline(body: PipelineRequest, request: Request, authorization: str | None = Header(default=None)):
    nodes = [n.model_dump() for n in body.nodes]
    return await execute_pipeline(
        nodes=nodes,
        channel_id=body.channel_id,
        channel_secret=body.channel_secret,
        base_url=base_public_url(),
        authorization=authorization,
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
    x_payment_channel_secret: str | None = Header(default=None, alias="X-Payment-Channel-Secret"),
    x_ai_market_license: str | None = Header(default=None, alias="x-ai-market-license"),
    authorization: str | None = Header(default=None),
):
    enforce_invoke_limits(request, authorization)
    status, payload, headers = await invoke_capability_v1(
        product_id=product_id,
        capability_id=capability_id,
        body_input=body.input,
        base_url=str(request.base_url).rstrip("/"),
        x_payment=x_payment,
        x_payment_channel=x_payment_channel,
        x_payment_channel_secret=x_payment_channel_secret,
        x_ai_market_license=x_ai_market_license,
        authorization=authorization,
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
    x_payment_channel_secret: str | None = Header(default=None, alias="X-Payment-Channel-Secret"),
    x_ai_market_license: str | None = Header(default=None, alias="x-ai-market-license"),
    authorization: str | None = Header(default=None),
):
    return await invoke_capability_root(
        product_id=product_id,
        capability_id=capability_id,
        body=body,
        request=request,
        x_payment=x_payment,
        x_payment_channel=x_payment_channel,
        x_payment_channel_secret=x_payment_channel_secret,
        x_ai_market_license=x_ai_market_license,
        authorization=authorization,
    )
