"""Agent doors: MCP at /ai-market/mcp and the apex, and the A2A facade."""

from __future__ import annotations

import os
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, FastAPI

from aimarket_hub import mandates
from aimarket_hub.access_policy import capability_is_publicly_offerable
from aimarket_hub.config import HubConfig
from aimarket_hub.database import HubDatabase
from aimarket_hub.fulfillment import capability_is_fulfillable
from aimarket_hub.mandates import MandateStore
from aimarket_hub.settle import InvoiceStore


def register(
    *,
    _api_key_account: Callable[..., Any],
    _check_invoke_rate: Callable[..., Any],
    _mcp_caller: Callable[..., Any],
    app: FastAPI,
    config: HubConfig,
    db: HubDatabase,
    hub_invoices: InvoiceStore,
    hub_mandates: MandateStore,
    search: Callable[..., Awaitable[Any]],
    wellknown_router: APIRouter,
) -> None:
    """Attach the MCP and A2A routers to ``app``."""
    # api.py's module-level helpers; imported here because api.py imports this module.
    from aimarket_hub.api import (
        _catalogue_route,
    )

    # MCP at /ai-market/mcp (advertised in well-known) — not under /v2.
    from aimarket_hub.mcp_gateway import attach_mcp_discovery_routes, attach_mcp_routes

    def _mcp_route_ok(capability: Any) -> bool:
        # The same predicate as the buyer-facing catalogue snapshot: a direct MCP tool is
        # listed only while its capability is fulfillable, public and on a sellable route.
        return (
            capability_is_fulfillable(capability)
            and capability_is_publicly_offerable(capability)
            and _catalogue_route(db, config, capability).sellable
        )

    mcp_router = APIRouter(prefix="/ai-market", tags=["mcp"])
    attach_mcp_routes(
        mcp_router, db=db, hub_url=config.hub_url, client_address=_mcp_caller,
        search=search, route_ok=_mcp_route_ok,
    )
    app.include_router(mcp_router)

    # The same gateway at the apex /mcp, because that is the URL a human pastes into an
    # MCP client and the one an MCP-registry listing can carry. /ai-market/mcp stays for
    # peers that read `mcp_endpoint` out of the well-known manifest.
    apex_mcp_router = APIRouter(tags=["mcp"])
    attach_mcp_routes(
        apex_mcp_router, db=db, hub_url=config.hub_url, client_address=_mcp_caller,
        search=search, route_ok=_mcp_route_ok,
    )
    app.include_router(apex_mcp_router)

    # A2A 1.0: marketplace discovery, and paid execution as Tasks (docs/a2a.md). Pass the
    # existing public search handler rather than duplicating its fulfillment, route-freshness
    # and supply-security policy in an adapter.
    from aimarket_hub import a2a as a2a_facade
    from aimarket_hub import a2a_push
    from aimarket_hub.a2a_tasks import A2ATaskStore

    a2a_bridge: a2a_facade.InvokeBridge | None = None
    if a2a_facade.invoke_enabled():
        # The invoke bridge posts to /ai-market/v2/invoke THROUGH THIS APP, not to the Python
        # handler: _x402_middleware mints the invoice nonce every x402 payment must be bound to,
        # and prepare → _invoke_core → finish, the rate limiter and the invoke metrics must be
        # the ones every other buyer meets. In-process (ASGITransport), unlike the MCP gateway's
        # loopback, so no port is guessed and nothing leaves the process; `client` is the real
        # caller, so the per-IP limiter and the trial ledger see each A2A buyer on their own.
        _parts = urlparse(config.hub_url or "")
        _a2a_base = (
            f"{_parts.scheme}://{_parts.netloc}" if _parts.scheme and _parts.netloc else "http://hub.internal"
        )

        async def _a2a_invoke(raw: bytes, headers: dict[str, str], caller: str):
            transport = httpx.ASGITransport(
                app=app, client=(caller or "127.0.0.1", 0), raise_app_exceptions=False,
            )
            # No timeout: the call runs in this process to completion either way (a
            # Pay-on-Verified invoke may legitimately hold for 300 s), and abandoning it half
            # way would only lose the answer, not stop the charge.
            async with httpx.AsyncClient(transport=transport, base_url=_a2a_base, timeout=None) as client:
                response = await client.post(
                    "/ai-market/v2/invoke", content=raw,
                    headers={"Content-Type": "application/json", **headers},
                )
            try:
                answer: Any = response.json()
            except ValueError:
                answer = {"success": False, "error": "invalid_response", "detail": response.text[:500]}
            return response.status_code, response.headers, answer

        def _a2a_verify_mandate(digest: str, proof: str, method: str, path: str, body: bytes) -> bool:
            try:
                leaf = hub_mandates.get(digest)
                if leaf is None:
                    return False
                hub_mandates.verify_request(leaf=leaf, proof_header=proof, method=method, path=path, body=body)
            except mandates.MandateError:
                return False
            return True

        def _a2a_is_priced(product_id: str, capability_id: str, source_hub: str) -> bool:
            """Whether a capability costs anything; unknown counts as priced (the MCP rule:
            erring the other way would send an unpaid invoke at something that is not free)."""
            origins = (source_hub, "local") if source_hub and source_hub != "local" else ("local",)
            for origin in origins:
                try:
                    cap = db.get_capability(product_id, capability_id, origin)
                except Exception:  # noqa: BLE001
                    return True
                if cap is not None:
                    try:
                        return float(cap.price_per_call_usd or 0) > 0
                    except (TypeError, ValueError):
                        return True
            return True

        def _env_seconds(name: str, default: int) -> int:
            try:
                return int(os.environ.get(name, "") or default)
            except ValueError:
                return default

        a2a_tasks_store = A2ATaskStore(
            db._conn,
            interrupted_ttl_s=_env_seconds("AIMARKET_A2A_TASK_TTL_S", 900),
            retention_s=_env_seconds("AIMARKET_A2A_TASK_RETENTION_S", 7 * 86_400),
        )

        def _a2a_recover(row: dict[str, Any]) -> dict[str, Any]:
            """What an abandoned task's call cost, from the receipts its ChargeJournal named.

            A hold still held belongs to a process that is gone (the recovery took the task's
            lease first): it is released, with its mandate reservation — and an owner approval
            it used goes back with it. A captured hold or a recorded debit is a charge. An
            allowance (its children settle it) or a hold a verifier still owns cannot be judged
            here: "unknown"."""
            from aimarket_hub import credits as credits_mod
            from aimarket_hub.channels import UNRESOLVED_SETTLEMENT_STATUSES

            ledger = credits_mod.CreditsLedger(db._conn)
            charges = a2a_tasks_store.charges(row["task_id"])
            charged: list[str] = []
            unknown = False
            marks = ",".join("?" for _ in UNRESOLVED_SETTLEMENT_STATUSES)
            for charge in charges:
                receipt, kind = str(charge["receipt_id"]), str(charge["kind"])
                if kind == "allowance":
                    unknown = True
                    continue
                if kind == "debit":
                    if db._conn.execute("SELECT 1 FROM credit_ledger WHERE receipt_id = ? LIMIT 1",
                                        (receipt,)).fetchone():
                        charged.append(receipt)
                    continue
                hold = db._conn.execute("SELECT status FROM credit_holds WHERE receipt_id = ?", (receipt,)).fetchone()
                if hold is None:
                    continue   # named, never taken
                status = str(dict(hold)["status"])
                if status == "held" and db._conn.execute(
                        f"SELECT 1 FROM verified_settlements WHERE nonce = ? AND status IN ({marks})",
                        (receipt, *UNRESOLVED_SETTLEMENT_STATUSES)).fetchone():
                    unknown = True   # a verifier owns it and settles it on its own
                    continue
                if status == "held":
                    result = ledger.release_hold(receipt)
                    status = "captured" if result.get("already") == "captured" else "released"
                if status == "captured":
                    charged.append(receipt)
                    hub_mandates.capture(receipt)
                else:
                    hub_mandates.settle(receipt, 0)
            if charged:
                outcome = "charged"
            elif unknown:
                outcome = "unknown"
            else:
                outcome = "released" if charges else "none"
            return {"outcome": outcome, "receipts": charged}

        a2a_bridge = a2a_facade.InvokeBridge(
            invoke=_a2a_invoke,
            tasks=a2a_tasks_store,
            recover=_a2a_recover,
            approval_lookup=lambda approval_id: (
                mandates.approval_public(row, base_url=hub_mandates.hub_origin)
                if (row := hub_mandates.approval(approval_id)) is not None else None),
            client_address=_mcp_caller,
            resolve_account=_api_key_account,
            verify_mandate=_a2a_verify_mandate,
            is_priced=_a2a_is_priced,
            allow_request=lambda caller: _check_invoke_rate("a2a:" + caller),
            payment_secret=hub_invoices.secret_for,
            # On by default (AIMARKET_A2A_PUSH_ENABLED=0 turns it off): webhooks are the
            # caller's own https URLs, held to the outbound SSRF rules (a2a_push.py).
            push=a2a_push.PushDispatcher(a2a_push.PushStore(db._conn)) if a2a_push.enabled() else None,
        )
        # An owner's answer to an approval moves the task waiting on it (mandates.md §5.6).
        hub_mandates.decision_listeners.append(a2a_facade.approval_listener(a2a_bridge))

    a2a_router = APIRouter(tags=["a2a"])
    # The task sweep, run on the hub's timer too (api.py lifespan): after a restart the tasks
    # the dead process was running must be recovered whether or not anyone calls /a2a.
    app.state.a2a_sweep = a2a_facade.attach_a2a_routes(
        a2a_router,
        hub_name=config.hub_name,
        hub_url=config.hub_url,
        hub_version=config.hub_version,
        search=search,
        bridge=a2a_bridge,
    )
    app.include_router(a2a_router)

    attach_mcp_discovery_routes(wellknown_router)
