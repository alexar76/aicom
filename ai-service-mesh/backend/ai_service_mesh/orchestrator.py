"""Auto-mesh pipeline: discover → verify → escrow → invoke → settle (with agent fallback)."""

from __future__ import annotations

from ai_service_mesh.db import MeshStore
from ai_service_mesh.discovery import DiscoveryMatch, DiscoveryService
from ai_service_mesh.invoke import invoke_direct, invoke_via_hub, preflight_agent, preflight_hub
from ai_service_mesh.models import (
    ActivityKind,
    MeshHopOut,
    TaskOut,
    TaskStatus,
    utc_now_iso,
)
from ai_service_mesh.payments import EscrowLedger


class MeshOrchestrator:
    def __init__(
        self,
        store: MeshStore,
        discovery: DiscoveryService,
        escrow: EscrowLedger,
        hub_url: str,
        *,
        reject_demo_invoke_output: bool = True,
        max_agent_attempts: int = 12,
    ) -> None:
        self._store = store
        self._discovery = discovery
        self._escrow = escrow
        self._hub_url = hub_url.rstrip("/")
        self._reject_demo = reject_demo_invoke_output
        self._max_attempts = max(1, max_agent_attempts)

    async def run_task(self, task: TaskOut, preferred: list[str]) -> TaskOut:
        task.status = TaskStatus.DISCOVERING
        self._store.update_task(task)
        self._store.emit(
            ActivityKind.DISCOVERY,
            "Scanning mesh for capable agents",
            task_id=task.id,
        )

        matches = await self._discovery.discover(task.intent, task.budget_usd, preferred)
        if not matches:
            task.status = TaskStatus.FAILED
            task.error = "No agents matched intent within budget"
            task.completed_at = utc_now_iso()
            self._store.update_task(task)
            self._store.emit(ActivityKind.ERROR, task.error, task_id=task.id)
            return task

        failures: list[str] = []
        candidates = matches[: self._max_attempts]

        for match in candidates:
            task.status = TaskStatus.VERIFYING
            self._store.update_task(task)

            ok_pre, lat_pre, detail_pre = await self._preflight(match)
            task.hops.append(
                MeshHopOut(
                    agent_id=match.agent.id,
                    agent_name=match.agent.name,
                    phase="verify",
                    price_usd=0.0,
                    latency_ms=lat_pre,
                    success=ok_pre,
                    detail=detail_pre,
                )
            )
            self._store.emit(
                ActivityKind.VERIFICATION,
                f"Zero-trust preflight: {match.agent.name} ({detail_pre})",
                task_id=task.id,
                agent_id=match.agent.id,
                payload={"source": match.source, "score": match.score, "ok": ok_pre},
            )
            if not ok_pre:
                failures.append(f"{match.agent.name}: preflight {detail_pre}")
                continue

            task.status = TaskStatus.ESCROWED
            hold = self._escrow.hold(task.id, match.agent.id, match.price_usd)
            self._store.emit(
                ActivityKind.ESCROW,
                f"Escrow hold {hold.amount_usd:.4f} USD ({hold.id})",
                task_id=task.id,
                agent_id=match.agent.id,
                payload={"escrow_id": hold.id},
            )
            task.hops.append(
                MeshHopOut(
                    agent_id=match.agent.id,
                    agent_name=match.agent.name,
                    phase="escrow",
                    price_usd=match.price_usd,
                    latency_ms=0,
                    success=True,
                    detail=hold.id,
                )
            )
            self._store.update_task(task)

            task.status = TaskStatus.INVOKING
            self._store.update_task(task)
            invoke_ok, latency, detail, _raw = await self._invoke_match(match, task.intent)
            task.hops.append(
                MeshHopOut(
                    agent_id=match.agent.id,
                    agent_name=match.agent.name,
                    phase="invoke",
                    price_usd=match.price_usd,
                    latency_ms=latency,
                    success=invoke_ok,
                    detail=detail[:200],
                )
            )
            self._store.emit(
                ActivityKind.INVOKE,
                f"Invocation {'succeeded' if invoke_ok else 'failed'}: {detail[:120]}",
                task_id=task.id,
                agent_id=match.agent.id,
                payload={"latency_ms": latency},
            )

            if invoke_ok:
                self._escrow.release(hold.id)
                task.total_spent_usd = match.price_usd
                task.selected_agent_id = match.agent.id
                task.status = TaskStatus.COMPLETED
                self._store.emit(
                    ActivityKind.SETTLE,
                    f"Settled {match.price_usd:.4f} USD to {match.agent.name}",
                    task_id=task.id,
                    agent_id=match.agent.id,
                )
                task.hops.append(
                    MeshHopOut(
                        agent_id=match.agent.id,
                        agent_name=match.agent.name,
                        phase="settle",
                        price_usd=match.price_usd,
                        latency_ms=0,
                        success=True,
                    )
                )
                task.completed_at = utc_now_iso()
                self._store.update_task(task)
                return task

            self._escrow.refund(hold.id)
            failures.append(f"{match.agent.name}: {detail or 'invoke failed'}")

        task.status = TaskStatus.FAILED
        task.error = failures[-1] if failures else "All agent attempts failed"
        task.completed_at = utc_now_iso()
        self._store.update_task(task)
        self._store.emit(ActivityKind.ERROR, task.error, task_id=task.id)
        return task

    async def _preflight(self, match: DiscoveryMatch) -> tuple[bool, int, str]:
        route_via_hub = match.source == "hub" or bool(
            match.agent.product_id and match.agent.capability_id and self._hub_url
        )
        if route_via_hub:
            if not self._hub_url:
                return False, 0, "hub_url_not_configured"
            return await preflight_hub(self._hub_url)
        return await preflight_agent(match.agent.endpoint_url)

    async def _invoke_match(self, match: DiscoveryMatch, intent: str):
        agent = match.agent
        use_hub = match.source == "hub" or bool(agent.product_id and agent.capability_id)
        if use_hub:
            if not self._hub_url:
                return False, 0, "hub_url_not_configured", {}
            return await invoke_via_hub(
                self._hub_url,
                agent.product_id,
                agent.capability_id,
                intent,
                agent.source_hub or "local",
                reject_demo_output=self._reject_demo,
            )
        return await invoke_direct(agent.endpoint_url, intent)
