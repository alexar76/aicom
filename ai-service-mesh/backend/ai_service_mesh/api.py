"""FastAPI application — AI Service Mesh control plane."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from ai_service_mesh.config import Settings, get_settings
from ai_service_mesh.db import MeshStore
from ai_service_mesh.discovery import DiscoveryService
from ai_service_mesh.models import (
    AgentRegisterRequest,
    AgentOut,
    ActivityEventOut,
    MeshStatsOut,
    TaskCreateRequest,
    TaskOut,
)
from ai_service_mesh.orchestrator import MeshOrchestrator
from ai_service_mesh.payments import EscrowLedger
from ai_service_mesh.security import (
    RateLimiter,
    assert_production_tokens,
    client_ip,
    require_bearer,
    url_is_safe_async,
)
from ai_service_mesh.verification import verify_agent_registration

logger = logging.getLogger(__name__)


def create_app(settings: Optional[Settings] = None) -> FastAPI:
    settings = settings or get_settings()
    store = MeshStore(settings.data_dir, database_url=settings.database_url)
    discovery = DiscoveryService(
        store,
        settings.hub_url,
        skip_demo_capabilities=settings.skip_demo_capabilities,
    )
    escrow = EscrowLedger(store)
    assert_production_tokens(
        settings.env,
        settings.api_token,
        settings.admin_token,
        allow_insecure_tokens=settings.allow_insecure_tokens,
    )
    orchestrator = MeshOrchestrator(
        store,
        discovery,
        escrow,
        settings.hub_url,
        reject_demo_invoke_output=settings.reject_demo_invoke_output,
        max_agent_attempts=settings.max_agent_attempts,
    )
    limiter = RateLimiter(settings.rate_limit)

    cors_origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        logger.info("Mesh database backend: %s", store.backend_type)
        if settings.hub_url:
            logger.info("Federated discovery via AIMarket hub: %s", settings.hub_url)
        else:
            logger.warning("MESH_HUB_URL unset — only locally registered agents are discoverable")

        async def _stale_task_sweep() -> None:
            while True:
                try:
                    n = store.fail_stale_tasks(settings.task_stale_seconds)
                    if n:
                        logger.warning("Dead-lettered %s stale task(s)", n)
                except Exception:
                    logger.exception("Stale task sweep failed")
                await asyncio.sleep(60)

        sweep_task = asyncio.create_task(_stale_task_sweep())
        try:
            yield
        finally:
            sweep_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await sweep_task

    app = FastAPI(
        title="AI Service Mesh",
        description='Airbnb for AI agents — discover, verify, pay, invoke.',
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"],
    )

    def _rate(request: Request) -> None:
        limiter.check(client_ip(request))

    def _require_api(authorization: str, *, write: bool = False) -> None:
        if not settings.api_token:
            if not write:
                return
            raise HTTPException(status_code=503, detail="MESH_API_TOKEN not configured")
        require_bearer(
            authorization,
            settings.api_token,
            disabled_detail="MESH_API_TOKEN not configured",
        )

    def _require_admin(authorization: str) -> None:
        require_bearer(
            authorization,
            settings.admin_token,
            disabled_detail="MESH_ADMIN_TOKEN not configured",
        )

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response

    @app.get("/health")
    async def health() -> dict:
        return {
            "status": "ok",
            "service": "ai-service-mesh",
            "version": "0.1.0",
            "database": store.backend_type,
        }

    @app.get("/v1/stats", response_model=MeshStatsOut)
    async def stats(request: Request) -> MeshStatsOut:
        _rate(request)
        return store.stats()

    @app.get("/v1/agents", response_model=list[AgentOut])
    async def list_agents(
        request: Request,
        verified_only: bool = Query(default=False),
    ) -> list[AgentOut]:
        _rate(request)
        return store.list_agents(verified_only=verified_only)

    @app.get("/v1/agents/{agent_id}", response_model=AgentOut)
    async def get_agent(request: Request, agent_id: str) -> AgentOut:
        _rate(request)
        agent = store.get_agent(agent_id)
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")
        return agent

    @app.post("/v1/agents", response_model=AgentOut, status_code=201)
    async def register_agent(
        request: Request,
        body: AgentRegisterRequest,
        authorization: str = Header(default=""),
    ) -> AgentOut:
        _rate(request)
        _require_admin(authorization)
        if not await url_is_safe_async(
            body.endpoint_url, allow_localhost=settings.allow_localhost_agents
        ):
            raise HTTPException(status_code=400, detail="endpoint_url failed SSRF safety check")
        agent = store.register_agent(
            body.name,
            body.endpoint_url,
            body.public_key_pem,
            body.capabilities,
            body.attestation,
            product_id=body.product_id,
            capability_id=body.capability_id,
            source_hub=body.source_hub,
        )
        result = verify_agent_registration(
            name=body.name,
            endpoint_url=body.endpoint_url,
            public_key_pem=body.public_key_pem,
            capabilities=body.capabilities,
            attestation=body.attestation,
            allow_localhost=settings.allow_localhost_agents,
        )
        if result.ok:
            return store.verify_agent(agent.id, result.trust_score) or agent
        return agent

    @app.get("/v1/tasks", response_model=list[TaskOut])
    async def list_tasks(request: Request, limit: int = Query(default=50, le=200)) -> list[TaskOut]:
        _rate(request)
        return store.list_tasks(limit=limit)

    @app.get("/v1/tasks/{task_id}", response_model=TaskOut)
    async def get_task(request: Request, task_id: str) -> TaskOut:
        _rate(request)
        task = store.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        return task

    @app.post("/v1/tasks", response_model=TaskOut, status_code=201)
    async def create_task(
        request: Request,
        body: TaskCreateRequest,
        authorization: str = Header(default=""),
    ) -> TaskOut:
        _rate(request)
        _require_api(authorization, write=True)
        task = store.create_task(body.intent, body.budget_usd, body.consumer_agent_id)
        task = await orchestrator.run_task(task, body.preferred_capabilities)
        return task

    @app.get("/v1/activity", response_model=list[ActivityEventOut])
    async def activity(
        request: Request,
        limit: int = Query(default=100, le=500),
        since_id: Optional[str] = None,
    ) -> list[ActivityEventOut]:
        _rate(request)
        return store.list_activity(limit=limit, since_id=since_id)

    @app.get("/v1/activity/stream")
    async def activity_stream(request: Request) -> StreamingResponse:
        _rate(request)

        async def gen():
            last_id: Optional[str] = None
            while True:
                if await request.is_disconnected():
                    break
                events = store.list_activity(limit=50, since_id=last_id)
                for ev in events:
                    last_id = ev.id
                    yield f"data: {ev.model_dump_json()}\n\n"
                await asyncio.sleep(2)

        return StreamingResponse(gen(), media_type="text/event-stream")

    app.state.store = store
    app.state.settings = settings
    return app
