"""A2A ingress for SKOPOS's remediation conductor.

A small FastAPI app that lets MOMUS delegate a ``remediate`` task to SKOPOS. It can run as a
sidecar next to the Streamlit dashboard, or be mounted into SKOPOS's existing API server. It
advertises an A2A Agent Card so MOMUS (or any peer) can discover the ``remediate`` skill, and it
exposes the job board for the dashboard.

The conductor's work is I/O-bound and may take a while (Factory patch + retests + deploy), so a
posted task starts the job in the background and returns immediately with the job handle; the
peer/dashboard polls ``/remediation/jobs`` for progress.
"""

from __future__ import annotations

import asyncio
import contextlib
import hmac
import os
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from skopos.remediation.conductor import Conductor, RemediationConfig
from skopos.remediation.git_push import valid_finding_id
from skopos.remediation.jobs import JobState
from skopos.remediation.report_push import TERMINAL_STATES


def agent_card(public_url: str, conductor_pubkey: str) -> dict[str, Any]:
    base = public_url.rstrip("/")
    return {
        "protocolVersion": "0.2",
        "name": "SKOPOS",
        "description": "The watcher — conducts remediation: receives a signed finding from MOMUS, "
                       "drives the AI-Factory to patch it, gates the redeploy on a MOMUS re-test, "
                       "and dispatches a signed deploy order to the installed node agent.",
        "url": base,
        "version": "0.1.0",
        "capabilities": {"streaming": False, "pushNotifications": True, "stateTransitionHistory": True},
        "conductorPublicKey": conductor_pubkey,
        "skills": [{
            "id": "remediate",
            "name": "Remediation conductor",
            "description": "Accept a confirmed MOMUS finding and drive fix → re-test → deploy to "
                           "closure, escalating security-core findings to a human.",
            "tags": ["security", "remediation", "orchestration", "ci", "deploy"],
        }],
        "endpoints": {"tasks": f"{base}/a2a/tasks"},
    }


#: Concurrent remediation jobs a single conductor process will hold open.
_MAX_INFLIGHT_JOBS = max(1, int(os.environ.get("SKOPOS_MAX_INFLIGHT_JOBS", "8")))
_inflight: set[asyncio.Task] = set()


def _reap_finished() -> None:
    for task in [t for t in _inflight if t.done()]:
        _inflight.discard(task)
        # Surface a crash instead of losing it to an un-retrieved exception.
        with contextlib.suppress(asyncio.CancelledError, Exception):
            task.result()


def build_app(conductor: Conductor | None = None) -> FastAPI:
    conductor = conductor or Conductor(RemediationConfig.from_env())
    app = FastAPI(title="SKOPOS remediation conductor", version="0.1.0")
    origins = [o.strip() for o in os.environ.get("SKOPOS_A2A_CORS", "*").split(",") if o.strip()] or ["*"]
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["*"], allow_headers=["*"])
    app.state.conductor = conductor

    # ── Peer authentication ────────────────────────────────────────────────────
    # A2A is agent-to-AGENT, not a public inbox. This endpoint can start a Factory patch and end in
    # a signed DeployOrder, so an unauthenticated caller must not be able to open a job. The token is
    # shared with MOMUS (SKOPOS_A2A_TOKEN on both sides); fail-closed outside dry-run.
    a2a_token = os.environ.get("SKOPOS_A2A_TOKEN", "").strip()

    def _require_peer(request: Request) -> None:
        if not a2a_token:
            if not conductor.cfg.dry_run:
                raise HTTPException(
                    status_code=503,
                    detail="SKOPOS_A2A_TOKEN is unset — refusing A2A tasks outside dry-run "
                           "(fail-closed). Configure the same token on MOMUS.")
            return  # dry-run convenience only
        supplied = (request.headers.get("x-a2a-token") or "").strip()
        # Constant-time, like every other secret comparison in this package
        # (app_auth, node_protocol, auth_store, api_server all use compare_digest).
        if not hmac.compare_digest(supplied, a2a_token):
            raise HTTPException(status_code=403, detail="A2A peer token required")

    # ── Reader authentication ─────────────────────────────────────────────────
    # The introspection routes below were written for a service reachable only over loopback.
    # That assumption does not survive contact with Docker: the conductor shares a network with
    # Gitea and its CI runner, and a job container there reaches the conductor's port DIRECTLY at
    # its container address — the `127.0.0.1:9402` publish binds the host side only. Measured, not
    # supposed: a throwaway container on the runner's daemon got 200 from /remediation/jobs and
    # /metrics. Those bodies are the whole self-healing state — findings, components, order ids,
    # host names, breaker posture — handed to whatever a workflow decided to run.
    #
    # Any control token the legitimate callers already hold is accepted; there is no new secret to
    # distribute. When none is configured this stays open, because a conductor with no tokens at
    # all is a dry-run box and refusing its own dashboard would teach nobody anything.
    _reader_tokens = tuple(t for t in (
        os.environ.get("SKOPOS_OPERATOR_TOKEN", "").strip(),
        os.environ.get("SKOPOS_AGENT_TOKEN", "").strip(),
        a2a_token,
    ) if t)

    def _require_reader(request: Request) -> None:
        if not _reader_tokens:
            return
        supplied = ((request.headers.get("x-skopos-operator")
                     or request.headers.get("x-agent-token")
                     or request.headers.get("x-a2a-token")) or "").strip()
        # compare against every accepted token, and never short-circuit on the first mismatch
        ok = False
        for token in _reader_tokens:
            if hmac.compare_digest(supplied, token):
                ok = True
        if not ok:
            raise HTTPException(status_code=403,
                                detail="a control token is required to read remediation state")

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {"status": "ok", "service": "skopos-remediation", "version": "0.1.0",
                "conductor_pubkey": conductor.conductor_pubkey, "dry_run": conductor.cfg.dry_run,
                "a2a_gated": bool(a2a_token) or not conductor.cfg.dry_run,
                "momus_pubkey_configured": bool(conductor.cfg.momus_pubkey)}

    @app.get("/.well-known/agent-card.json")
    async def card() -> dict[str, Any]:
        public = os.environ.get("SKOPOS_PUBLIC_URL", "https://skopos.modelmarket.dev")
        return agent_card(public, conductor.conductor_pubkey)

    @app.post("/a2a/tasks")
    async def a2a_tasks(body: dict, request: Request) -> dict[str, Any]:
        _require_peer(request)
        skill = str((body or {}).get("skill") or "").strip()
        if skill != "remediate":
            conductor.observer.record_inbound(body, state="rejected",
                                              note=f"unsupported skill '{skill}'")
            return {"state": "rejected",
                    "message": f"SKOPOS conductor accepts skill 'remediate', not '{skill}'"}
        ticket = ((body or {}).get("input") or {}).get("ticket") or {}
        if not ticket.get("finding_id"):
            conductor.observer.record_inbound(body, state="rejected", note="missing ticket.finding_id")
            return {"state": "rejected", "message": "missing ticket.finding_id"}
        if not valid_finding_id(ticket.get("finding_id")):
            conductor.observer.record_inbound(
                body, state="rejected", note="unsafe ticket.finding_id")
            raise HTTPException(status_code=400, detail="ticket.finding_id has an unsafe format")
        # Bound the in-flight set. Each accepted ticket spawns a long-running background job
        # (Factory patch + retests + deploy), and nothing counted them: a caller could open
        # jobs faster than they finish until the process ran out of memory or file handles.
        # In dry-run _require_peer above lets an unauthenticated caller in on purpose, so
        # this is the only thing standing between a local caller and unbounded fan-out.
        _reap_finished()
        if len(_inflight) >= _MAX_INFLIGHT_JOBS:
            conductor.observer.record_inbound(
                body, state="rejected",
                note=f"conductor busy: {len(_inflight)} jobs in flight (max {_MAX_INFLIGHT_JOBS})")
            raise HTTPException(
                status_code=429,
                detail=f"conductor is at capacity ({_MAX_INFLIGHT_JOBS} jobs in flight); "
                       "poll /remediation/jobs and retry")
        conductor.observer.record_inbound(body, state="working")
        # Start the (long-running) job in the background; return the handle immediately.
        _inflight.add(asyncio.create_task(conductor.handle_ticket(ticket)))
        return {"state": "working", "finding_id": ticket["finding_id"],
                "message": "remediation job started", "poll": "/remediation/jobs"}

    # ── A2A observability: SKOPOS watching the agents talk ────────────────────
    @app.get("/a2a/events")
    async def a2a_events(request: Request, limit: int = 100, peer: str | None = None,
                         skill: str | None = None) -> dict[str, Any]:
        _require_reader(request)
        return {"events": conductor.observer.recent(limit, peer=peer, skill=skill),
                "stats": conductor.observer.stats()}

    @app.get("/a2a/stats")
    async def a2a_stats(request: Request) -> dict[str, Any]:
        _require_reader(request)
        return conductor.observer.stats()

    # ── Deploy-order pickup for PUSH-ONLY node agents ─────────────────────────
    # The fleet agents have no HTTP server, so they poll here. Authority stays split: the conductor
    # publishes a signed order but cannot execute it; the agent executes but cannot invent one.
    agent_token = os.environ.get("SKOPOS_AGENT_TOKEN", "").strip()

    def _require_agent(request: Request) -> None:
        if not agent_token:
            if not conductor.cfg.dry_run:
                raise HTTPException(status_code=503,
                                    detail="SKOPOS_AGENT_TOKEN is unset — refusing to hand out "
                                           "deploy orders outside dry-run (fail-closed)")
            return
        supplied = (request.headers.get("x-agent-token") or "").strip()
        if not hmac.compare_digest(supplied, agent_token):
            raise HTTPException(status_code=403, detail="agent token required")

    @app.get("/agent/v1/orders")
    async def agent_orders(host: str, request: Request) -> dict[str, Any]:
        """Hand this host its next signed order, ONCE. A claimed order is never re-served, so a
        replayed poll cannot re-run a deploy; an expired one is skipped rather than executed late."""
        _require_agent(request)
        q = conductor.orders.claim_for(host, agent_id=host)
        if q is None:
            return {"order": None, "host": host}
        conductor.observer.record_outbound(
            peer=f"agent:{host}", skill="deploy-order", finding_id=q.finding_id,
            state="completed", summary=f"order {q.order_id} claimed for {q.service}",
            artifacts=["deploy-order"])
        return {"order": q.order, "host": host, "order_id": q.order_id, "service": q.service}

    @app.post("/agent/v1/result")
    async def agent_result(body: dict, request: Request) -> dict[str, Any]:
        """The agent reports what it did — including a REFUSAL, which is the interesting case."""
        _require_agent(request)
        oid = str((body or {}).get("order_id") or "")
        result = (body or {}).get("result") or {}
        ok = conductor.orders.report(oid, result)
        conductor.observer.record_inbound(
            {"skill": "deploy-result", "from_agent": f"agent:{result.get('host', '?')}",
             "input": {"finding_id": oid}},
            state="completed" if ok else "rejected",
            note=("deployed" if result.get("deployed") else
                  f"refused: {str(result.get('reason'))[:80]}" if result.get("refused") else
                  "dry-run"))
        return {"recorded": ok, "order_id": oid}

    @app.get("/agent/v1/queue")
    async def agent_queue(request: Request, limit: int = 20) -> dict[str, Any]:
        """Read-only view of published orders and what the agents did with them."""
        _require_reader(request)
        return {"orders": conductor.orders.all(limit), "stats": conductor.orders.stats()}

    @app.get("/remediation/jobs")
    async def jobs(request: Request) -> dict[str, Any]:
        _require_reader(request)
        return {"jobs": [j.to_dict() for j in conductor.store.all()]}

    @app.get("/remediation/jobs/{finding_id}")
    async def job(finding_id: str, request: Request) -> dict[str, Any]:
        _require_reader(request)
        j = conductor.store.get(finding_id)
        return j.to_dict() if j else {"error": "unknown_job", "finding_id": finding_id}

    @app.get("/api/remediation/stats")
    async def remediation_stats() -> dict[str, Any]:
        """Digest of the remediation loop, in the shape LOGOS reads.

        Deliberately left ungated while its neighbours are not: LOGOS polls this path with no
        header (logos/logos/sources/skopos.py) and this body is counts — how many jobs, how many
        closed, how many escalated. It names no finding, no component, no host and no order, so
        there is nothing here to take. Gating it would buy a number and cost the panel.

        LOGOS has polled this exact path since it shipped (logos/logos/sources/skopos.py);
        nothing served it, so its remediation panel showed a permanent "unreachable" with
        zero counts — and the bare `except Exception` there made a 404 look like a network
        failure. The keys below are the ones that source maps.
        """
        jobs = [j.to_dict() for j in conductor.store.all()]
        by_state: dict[str, int] = {}
        for j in jobs:
            by_state[j.get("state", "unknown")] = by_state.get(j.get("state", "unknown"), 0) + 1
        snap = conductor.health.snapshot()
        return {
            # The keys LOGOS has mapped since it shipped. Do not rename them here — the panel reads
            # these exact names, and a rename would silently zero it again.
            "total": len(jobs),
            "closed": sum(by_state.get(s, 0) for s in TERMINAL_STATES),
            "confirmed_fixed": by_state.get(JobState.DONE.value, 0),
            "escalated": by_state.get(JobState.ESCALATED.value, 0),
            "orders_signed": conductor.orders.stats().get("total", 0),
            "by_state": by_state,
            # Degradation signals, added alongside rather than instead of the above.
            "rolled_back": snap.get("rolled_back", 0),
            "rollback_rate": snap.get("rollback_rate"),
            "win_rate": snap.get("win_rate"),
            "breaker_open": bool(conductor.breaker.state.tripped),
            "needs_attention": snap.get("needs_attention", {}),
        }

    @app.get("/remediation/health")
    async def loop_health(request: Request) -> dict[str, Any]:
        """Everything an operator needs to answer "is this loop still trustworthy?"."""
        _require_reader(request)
        return {"health": conductor.health.snapshot(),
                "breaker": conductor.breaker.status(),
                "dry_run": conductor.cfg.dry_run}

    @app.post("/remediation/breaker/clear")
    async def clear_breaker(request: Request) -> dict[str, Any]:
        """Re-arm a quarantined loop. Operator-only, and deliberately the ONLY way back.

        Nothing in this package calls it: a breaker that could clear itself — on a timer, on a
        restart, on the next apparently-good job — would be defeated by the crash-loop it exists to
        interrupt. Someone has to look first."""
        token = os.environ.get("SKOPOS_OPERATOR_TOKEN", "").strip()
        if not token:
            raise HTTPException(status_code=503,
                                detail="SKOPOS_OPERATOR_TOKEN is unset — refusing to clear the "
                                       "breaker without operator authentication")
        supplied = (request.headers.get("x-skopos-operator") or "").strip()
        if not hmac.compare_digest(supplied, token):
            raise HTTPException(status_code=403, detail="operator token required")
        if not conductor.breaker.state.tripped:
            return {"cleared": False, "reason": "breaker is already closed",
                    "breaker": conductor.breaker.status()}
        was = conductor.breaker.state.reason
        conductor.breaker.clear(by="operator")
        return {"cleared": True, "was_tripped_for": was, "breaker": conductor.breaker.status()}

    @app.get("/metrics")
    async def metrics(request: Request) -> Response:
        """Prometheus exposition — the fleet already scrapes this shape."""
        _require_reader(request)
        snap = conductor.health.snapshot()
        orders = snap.get("orders") or {}
        lines: list[str] = []

        def gauge(name: str, value: Any, help_text: str, labels: str = "") -> None:
            if value is None:
                return          # an absent rate is not zero; omit it rather than lie
            if not labels:
                lines.append(f"# HELP {name} {help_text}")
                lines.append(f"# TYPE {name} gauge")
            lines.append(f"{name}{labels} {value}")

        gauge("skopos_remediation_jobs", snap.get("jobs_in_window", 0), "Jobs in the health window")
        gauge("skopos_remediation_deploys", snap.get("deployed", 0), "Real deploys in the window")
        gauge("skopos_remediation_rollbacks", snap.get("rolled_back", 0), "Rollbacks in the window")
        gauge("skopos_remediation_rollback_rate", snap.get("rollback_rate"),
              "Rollbacks per shipped patch — the primary degradation signal")
        gauge("skopos_remediation_win_rate", snap.get("win_rate"), "DONE over terminal jobs")
        gauge("skopos_remediation_breaker_open", int(bool(conductor.breaker.state.tripped)),
              "1 while the circuit breaker is refusing to sign deploy orders")
        gauge("skopos_remediation_dry_run", int(bool(conductor.cfg.dry_run)),
              "1 while nothing is actually being deployed")
        gauge("skopos_remediation_orders_unclaimed", orders.get("unclaimed", 0),
              "Published orders no agent has picked up")
        gauge("skopos_remediation_time_to_fix_seconds",
              (snap.get("time_to_fix_s") or {}).get("p95", 0), "p95 time from ticket to DONE")
        lines.append("# HELP skopos_remediation_attention Conditions that want a human")
        lines.append("# TYPE skopos_remediation_attention gauge")
        for key, value in (snap.get("needs_attention") or {}).items():
            gauge("skopos_remediation_attention", value, "", labels=f'{{condition="{key}"}}')
        lines.append("# HELP skopos_remediation_jobs_by_state Jobs per state in the window")
        lines.append("# TYPE skopos_remediation_jobs_by_state gauge")
        for state, count in (snap.get("by_state") or {}).items():
            gauge("skopos_remediation_jobs_by_state", count, "", labels=f'{{state="{state}"}}')
        return Response(content="\n".join(lines) + "\n", media_type="text/plain; version=0.0.4")

    return app
