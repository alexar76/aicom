"""
Pipeline Worker
===============
Background process that monitors the pipeline state machine and executes tasks
via real AI agent classes. Each task is processed by the appropriate agent
(PMAgent, ArchitectAgent, DeveloperAgent, etc.) which produce meaningful output.

This is NOT a mock/simulation. Agents use the LLM router with a rule-based
fallback when LLM models are unavailable.
"""

import asyncio
import contextlib
import hashlib
import json
import logging
import os
import signal
import sys
import time
import uuid
from pathlib import Path
from typing import Optional

from core.paths import data_root, model_providers_path, pipeline_db_path, pipeline_json_path
from core.logging_utils import log_suppressed
from core.throughput_limits import (
    effective_batch_pipeline_active_limit,
    effective_batch_pipeline_max_start_per_cycle,
    effective_task_executor_concurrency,
)
from agents.product_profile import post_devops_human_gate_required
from orchestrator.pipeline_flow import PIPELINE_AGENT_FLOW
from orchestrator.pipeline_worker_persistence import PipelineStatePersistence
from orchestrator.pipeline_worker_sidecars import PipelineWorkerSidecarMixin
from orchestrator.worker_components import PeerReviewEngine, QualityManager, TaskOrchestrator
from orchestrator.runtime_guards import RuntimeGuards
from orchestrator.task_executor import PipelineTaskExecutor
from orchestrator.worker_utils import delivery_profile_from_product_dict, env_truthy

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("pipeline-worker")

class PipelineWorker(PipelineWorkerSidecarMixin):
    """
    Background worker that:
    1. Monitors the pipeline state file for new products
    2. Creates initial tasks for new products
    3. Processes pending tasks via real AI agent classes
    4. Updates task status and advances pipeline states
    5. Persists agent output to the filesystem
    """

    def __init__(self):
        self.state_file = pipeline_json_path()
        from core.pipeline_database import pipeline_uses_sql_store

        self.use_sql_store = pipeline_uses_sql_store()
        self.use_sqlite = self.use_sql_store  # legacy flag name in logs/health
        self._running = False
        self._agents = {}  # agent_type -> agent instance
        self._llm_router = None
        self._wake_event = asyncio.Event()
        self._watch_stop = asyncio.Event()
        self._watch_task: Optional[asyncio.Task] = None
        self._last_mtime = 0
        self._last_content_hash = ""
        self._last_policy_audit_mono = 0.0
        self._last_cycle_at = 0.0
        self._last_successful_cycle_at = 0.0
        self._started_at = time.time()
        self._shutdown_reason = ""
        self._has_active_pipeline_work = False
        self.data_root = data_root()
        self._guards = RuntimeGuards(str(self.data_root))
        self._persistence = PipelineStatePersistence(
            state_file=self.state_file,
            use_sql_store=self.use_sql_store,
        )
        self._health_server = None
        self.task_orchestrator = TaskOrchestrator(self._get_priority)
        self.quality_manager = QualityManager(self._get_priority)
        self.peer_review_engine = PeerReviewEngine(self._get_priority)
        self._task_executor = PipelineTaskExecutor()

    def _audit_agent_handoff(
        self,
        *,
        product_id: str,
        from_agent: str,
        from_state: str,
        next_task: dict,
        task_id: str = "",
        reason: str = "sequential",
        success: bool = True,
        blocked: bool = False,
        output_data: dict | None = None,
        extra: dict | None = None,
    ) -> None:
        """Tamper-evident audit when the pipeline queues the next agent."""
        try:
            from security.agent_handoff_audit import log_handoff_from_task

            log_handoff_from_task(
                product_id=product_id,
                from_agent=from_agent,
                from_state=from_state,
                next_task=next_task,
                task_id=task_id,
                reason=reason,
                success=success,
                blocked=blocked,
                output_data=output_data,
                extra=extra,
            )
        except Exception:
            logger.debug("Agent handoff audit skipped", exc_info=False)

    def _request_shutdown(self, reason: str = "signal") -> None:
        if not self._shutdown_reason:
            self._shutdown_reason = reason
        self.stop()

    def _install_signal_handlers(self) -> None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            with contextlib.suppress(NotImplementedError):
                loop.add_signal_handler(sig, self._request_shutdown, sig.name)

    def health_snapshot(self) -> dict:
        return {
            "ok": True,
            "running": self._running,
            "started_at": self._started_at,
            "uptime_sec": max(0.0, time.time() - self._started_at),
            "last_cycle_at": self._last_cycle_at,
            "last_successful_cycle_at": self._last_successful_cycle_at,
            "shutdown_reason": self._shutdown_reason or None,
        }

    def readiness_snapshot(self) -> dict:
        sql_ready = (not self.use_sql_store) or (self._persistence._async_store is not None)
        agents_ready = len(self._agents) > 0
        ready = sql_ready and (agents_ready or not self._running)
        from core.pipeline_database import pipeline_db_backend

        return {
            "ready": ready,
            "running": self._running,
            "sqlite_ready": sql_ready,
            "sql_store_ready": sql_ready,
            "agents_ready": agents_ready,
            "use_sqlite": self.use_sql_store,
            "pipeline_db_backend": pipeline_db_backend(),
        }

    async def _start_health_server(self) -> None:
        try:
            port = int(os.environ.get("AIFACTORY_WORKER_HEALTH_PORT", "8091"))
        except ValueError:
            port = 8091
        if port <= 0:
            return
        host = os.environ.get("AIFACTORY_WORKER_HEALTH_HOST", "127.0.0.1")

        async def _handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            try:
                raw = await reader.readline()
                req = raw.decode("utf-8", errors="ignore").strip()
                parts = req.split()
                path = parts[1] if len(parts) >= 2 else "/"
                if path in ("/health", "/healthz"):
                    status = "200 OK"
                    body = json.dumps(self.health_snapshot()).encode("utf-8")
                elif path in ("/ready", "/readyz"):
                    ready = self.readiness_snapshot()
                    status = "200 OK" if ready.get("ready") else "503 Service Unavailable"
                    body = json.dumps(ready).encode("utf-8")
                elif path in ("/wake", "/wake/"):
                    self.signal_new_work()
                    status = "204 No Content"
                    body = b""
                else:
                    status = "404 Not Found"
                    body = b'{"error":"not_found"}'
                writer.write(
                    (
                        f"HTTP/1.1 {status}\r\n"
                        "Content-Type: application/json\r\n"
                        f"Content-Length: {len(body)}\r\n"
                        "Connection: close\r\n\r\n"
                    ).encode("utf-8")
                    + body
                )
                await writer.drain()
            finally:
                writer.close()
                with contextlib.suppress(Exception):
                    await writer.wait_closed()

        self._health_server = await asyncio.start_server(_handler, host=host, port=port)
        logger.info("Pipeline worker health server started at http://%s:%s", host, port)

    async def _close_resources(self) -> None:
        if self._health_server is not None:
            self._health_server.close()
            await self._health_server.wait_closed()
            self._health_server = None
        await self._persistence.close()

    async def _load_state_async(self) -> dict | None:
        return await self._persistence.load_async()

    async def _save_state_async(
        self,
        state: dict,
        *,
        sql_full_save: bool = False,
        dirty_product_ids: set[str] | None = None,
        dirty_task_ids: set[str] | None = None,
    ) -> bool:
        payload = dict(state)
        if sql_full_save:
            payload["_sql_full_save"] = True
        if dirty_product_ids:
            payload["_dirty_product_ids"] = list(dirty_product_ids)
        if dirty_task_ids:
            payload["_dirty_task_ids"] = list(dirty_task_ids)
        return await self._persistence.save_async(payload)

    async def _init_agents(self):
        """Initialize all agent instances with the LLM router."""
        if self._agents:
            return

        # Initialize LLM router with provider config path
        from llm import LLMRouter
        self._llm_router = LLMRouter(str(model_providers_path()))
        await self._llm_router.start_health_checks(interval_sec=60)
        logger.info("LLM Router initialized for pipeline worker (circuit breaker + health checks)")

        # Import all agent classes
        try:
            from agents.pm import PMAgent
            from agents.architect import ArchitectAgent
            from agents.dev import DeveloperAgent
            from agents.hardening import HardeningAgent
            from agents.qa import QAAgent
            from agents.design_critic import DesignCriticAgent
            from agents.security import SecurityAgent
            from agents.devops import DevOpsAgent
            from agents.marketing import MarketingAgent
            from agents.sales import SalesAgent
            from agents.evolution_analyst import EvolutionAnalystAgent
            from agents.analyst import MarketResearchAgent
            from agents.methodologist import MethodologyAgent

            self._agents = {
                "pm": PMAgent(self._llm_router),
                "architect": ArchitectAgent(self._llm_router),
                "design_critic": DesignCriticAgent(self._llm_router),
                "methodologist": MethodologyAgent(self._llm_router),
                "developer": DeveloperAgent(self._llm_router),
                "hardening": HardeningAgent(self._llm_router),
                "qa": QAAgent(self._llm_router),
                "security": SecurityAgent(self._llm_router),
                "devops": DevOpsAgent(self._llm_router),
                "marketing": MarketingAgent(self._llm_router),
                "sales": SalesAgent(self._llm_router),
                "evolution_analyst": EvolutionAnalystAgent(self._llm_router),
                "analyst": MarketResearchAgent(self._llm_router),
            }
            logger.info(f"Initialized {len(self._agents)} agents")
        except Exception as e:
            logger.error(f"Failed to initialize agents: {e}")
            raise

    async def run(self):
        """Main worker loop — event-driven mode using mtime checks + wake signal."""
        self._running = True
        self._install_signal_handlers()
        await self._start_health_server()
        logger.info("Pipeline Worker started (event-driven mode)")

        # Initialize agents on first run
        try:
            await self._init_agents()
        except Exception as e:
            logger.error(f"Agent initialization failed: {e}")
            logger.warning("Continuing with task orchestration only")

        self._last_policy_audit_mono = time.monotonic()
        self._watch_stop.clear()
        self._watch_task = asyncio.create_task(
            self._run_state_watch(),
            name="pipeline-state-watch",
        )
        await asyncio.sleep(2)
        try:
            if os.environ.get("AIFACTORY_POLICY_AUDIT_ON_START", "1").strip().lower() in (
                "1",
                "true",
                "yes",
            ):
                await self._run_policy_audit_once("startup")
        except Exception as e:
            logger.error(f"Startup policy audit failed: {e}")
        self._last_policy_audit_mono = time.monotonic()

        last_mtime = 0
        last_sqlite_mtime = 0.0
        last_content_hash = ""
        first_run = True
        woke = False

        try:
            while self._running:
                try:
                    self._last_cycle_at = time.time()
                    current_mtime = 0
                    if self.state_file.exists():
                        current_mtime = os.path.getmtime(self.state_file)

                    current_sqlite_mtime = 0.0
                    if self.use_sql_store:
                        from core.pipeline_state_writer import sqlite_store_mtime

                        current_sqlite_mtime = sqlite_store_mtime()

                    # Run a cycle when: first start, worker wake (/wake or signal_new_work),
                    # pipeline.json changed, or SQLite store touched (API enqueue without JSON mirror).
                    json_tick = first_run or current_mtime != last_mtime
                    sqlite_tick = self.use_sql_store and (
                        first_run or current_sqlite_mtime != last_sqlite_mtime
                    )
                    if woke or json_tick or sqlite_tick or self._has_active_pipeline_work:
                        first_run = False
                        last_mtime = current_mtime
                        last_sqlite_mtime = current_sqlite_mtime

                        if self.use_sqlite:
                            content_changed = True
                        else:
                            content_changed = True
                            if current_mtime > 0:
                                content_hash = self._compute_content_hash()
                                if content_hash == last_content_hash:
                                    content_changed = False
                                else:
                                    last_content_hash = content_hash

                        if content_changed:
                            await self._process_cycle()
                    self._last_successful_cycle_at = time.time()
                except Exception as e:
                    logger.error(f"Processing cycle error: {e}")

                # Event-driven idle: wake on /wake or signal_new_work(); else adaptive poll timeout.
                woke = await self._wait_next_cycle(
                    self._poll_interval_sec(self._has_active_pipeline_work)
                )

                current_mtime = 0
                try:
                    interval = float(os.environ.get("AIFACTORY_POLICY_AUDIT_INTERVAL_SEC", "900"))
                except ValueError:
                    interval = 900.0
                if interval > 0:
                    now_m = time.monotonic()
                    if now_m - self._last_policy_audit_mono >= interval:
                        self._last_policy_audit_mono = now_m
                        try:
                            await self._run_policy_audit_once("periodic")
                        except Exception as e:
                            logger.error(f"Periodic policy audit failed: {e}")
        finally:
            self._watch_stop.set()
            if self._watch_task is not None:
                self._watch_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await self._watch_task
            await self._close_resources()

    async def _run_policy_audit_once(self, reason: str) -> None:
        """Re-check terminal products against current marketplace/demo rules; enqueue fixes."""
        from web.backend.services.policy_audit import apply_policy_audit, sync_sqlite_from_pipeline_json
        from web.backend.services.feedback_guardrail import apply_feedback_guardrail

        state = await self._load_state_async()
        if not state:
            logger.warning("Policy audit: cannot read/recover pipeline state")
            return

        products = state.get("products", {})
        task_queue = state.get("task_queue", [])
        now = time.time()
        changed = apply_policy_audit(products, task_queue, now)
        if apply_feedback_guardrail(products, task_queue, now):
            changed = True
        if not changed:
            return

        state["products"] = products
        state["task_queue"] = task_queue
        if not await self._save_state_async(state, sql_full_save=True):
            return
        if not self.use_sqlite:
            try:
                sync_sqlite_from_pipeline_json()
            except Exception:
                logger.exception("Policy audit: SQLite sync failed")

        logger.info("Policy audit (%s): pipeline state updated", reason)
        self.signal_new_work()

    def _poll_interval_sec(self, has_active_work: bool) -> float:
        env_key = (
            "AIFACTORY_PIPELINE_ACTIVE_POLL_SEC"
            if has_active_work
            else "AIFACTORY_PIPELINE_IDLE_POLL_SEC"
        )
        default = "0.25" if has_active_work else "2.0"
        try:
            return max(0.05, float(os.environ.get(env_key, default)))
        except ValueError:
            return 0.25 if has_active_work else 2.0

    async def _wait_next_cycle(self, poll_sec: float) -> bool:
        """Block until ``signal_new_work()`` or idle poll timeout. Returns True when woken."""
        woke = False
        try:
            await asyncio.wait_for(self._wake_event.wait(), timeout=poll_sec)
            woke = True
        except asyncio.TimeoutError as _suppressed_exc:
            log_suppressed(logger, "non-fatal (pipeline_worker.py)", exc_info=_suppressed_exc)
        self._wake_event.clear()
        return woke

    async def _process_cycle(self):
        """One processing cycle: check for new products and pending tasks."""
        state = await self._load_state_async()
        if not state:
            self._has_active_pipeline_work = False
            return

        products = state.get("products", {})
        task_queue = state.get("task_queue", [])
        self._has_active_pipeline_work = any(
            t.get("status") in ("pending", "running") for t in task_queue
        )
        changed = False
        now = time.time()
        dirty_products: set[str] = set()
        dirty_tasks: set[str] = set()
        sql_full_save = False

        # Phase 0: Recover stranded PM quality-gate failures from previous runs.
        # This handles cases where products are left in FAILED with no active PM task.
        if self.task_orchestrator.archive_superseded_failed_tasks(products, task_queue, now):
            changed = True
            sql_full_save = True

        if self.task_orchestrator.recover_false_failed_products(products, task_queue, now):
            changed = True
            sql_full_save = True

        if self.task_orchestrator.recover_stranded_pm_quality_failures(products, task_queue, now):
            changed = True
            sql_full_save = True

        # Phase 0b: Reset tasks stuck in `running` (blocked sync calls, killed worker mid-flight).
        if self.task_orchestrator.recover_stale_running_tasks(task_queue, now):
            changed = True
            sql_full_save = True

        # Phase 0.1: Drain batch idea queue with controlled concurrency.
        try:
            from orchestrator.batch_pipeline import drain_batch_queue_into_state

            max_to_start = effective_batch_pipeline_max_start_per_cycle()
            active_limit = effective_batch_pipeline_active_limit()
            batch_res = drain_batch_queue_into_state(
                state={"products": products, "task_queue": task_queue},
                max_to_start=max(1, max_to_start),
                active_limit=max(1, active_limit),
            )
            if int(batch_res.get("started", 0)) > 0:
                changed = True
                sql_full_save = True
        except Exception as e:
            logger.warning("Batch queue drain skipped: %s", e)

        # Phase 1: Create initial tasks for products in IDEA_RECEIVED with no tasks
        if self.task_orchestrator.create_initial_tasks(products, task_queue, now):
            changed = True
            sql_full_save = True

        # Phase 2: Process pending tasks (start them)
        if self.task_orchestrator.start_pending_tasks(products, task_queue, now):
            changed = True
            sql_full_save = True

        # Checkpoint: Phase 3 may await many agents for a long time; without an early save,
        # bootstrap tasks from Phase 1–2 never reach SQLite until all runners finish (starvation).
        if changed:
            state["products"] = products
            state["task_queue"] = task_queue
            await self._save_state_async(state, sql_full_save=True)
            self._has_active_pipeline_work = any(
                t.get("status") in ("pending", "running") for t in task_queue
            )

        # Phase 3: Process running tasks via real agents (bounded concurrency)
        running_tasks = [task for task in task_queue if task.get("status") == "running"]
        exec_concurrency = effective_task_executor_concurrency()
        if running_tasks:
            sem = asyncio.Semaphore(exec_concurrency)

            async def _run_one(t: dict):
                async with sem:
                    await self._process_task(
                        t, products, task_queue, dirty_products=dirty_products, dirty_tasks=dirty_tasks
                    )

            await asyncio.gather(*(_run_one(t) for t in running_tasks))
            changed = True

        # Phase 4: Retry failed tasks (up to max_retries with exponential backoff)
        if self.task_orchestrator.retry_failed_tasks(products, task_queue, now):
            changed = True
            sql_full_save = True

        # Phase 4b: Dedupe active tasks; cancel regressive re-queues (PM on DEV_FIXING, etc.)
        if self.task_orchestrator.enforce_queue_hygiene(products, task_queue, now):
            changed = True
            sql_full_save = True

        # Phase 4c: Idle mid-pipeline products with no active task → enqueue next sequential step
        for pid, product in list(products.items()):
            st = str(product.get("state") or "").upper()
            if st in ("COMPLETED", "FAILED", "CANCELLED", "IDEA_RECEIVED"):
                continue
            has_active = any(
                t.get("product_id") == pid
                and str(t.get("status") or "").lower() in ("pending", "running")
                for t in task_queue
            )
            if has_active:
                continue
            next_task = self._create_next_task(product)
            if not next_task:
                continue
            from orchestrator.task_queue_hygiene import append_product_task

            if append_product_task(task_queue, next_task, products, get_priority=self._get_priority):
                changed = True
                sql_full_save = True
                dirty_products.add(pid)
                tid = next_task.get("id")
                if tid:
                    dirty_tasks.add(str(tid))
                logger.info(
                    "Healed idle product %s at %s: queued %s -> %s",
                    pid,
                    st,
                    next_task.get("agent_type"),
                    next_task.get("state"),
                )

        # Phase 5: Periodic market monitoring for COMPLETED products (interval from env; 0 = off)
        if self.task_orchestrator.enqueue_market_monitoring(products, task_queue, now):
            changed = True
            sql_full_save = True
        if self.task_orchestrator.enqueue_refactor_sprint(products, task_queue, now):
            changed = True
            sql_full_save = True

        # Phase 6: Ensure COMPLETED products are truly storefront-ready.
        # Reopen hidden/non-eligible products for developer remediation.
        if self._enforce_marketplace_readiness(products, task_queue, now):
            changed = True
            sql_full_save = True

        # Phase 6b: Heal product.state when JSON sync or partial writes left IDEA_RECEIVED.
        try:
            from orchestrator.pipeline_state_sync import reconcile_all_products_from_tasks

            if reconcile_all_products_from_tasks(products, task_queue):
                changed = True
                sql_full_save = True
        except Exception as exc:
            logger.debug("product state reconcile skipped: %s", exc)

        # Save if changed
        if changed:
            state["products"] = products
            state["task_queue"] = task_queue
            await self._save_state_async(
                state,
                sql_full_save=sql_full_save,
                dirty_product_ids=dirty_products if not sql_full_save else None,
                dirty_task_ids=dirty_tasks if not sql_full_save else None,
            )

        self._has_active_pipeline_work = any(
            t.get("status") in ("pending", "running") for t in task_queue
        )

    def _load_spec(self, product_id: str) -> dict:
        """Load inner specification dict (PM `specification` object) for agents."""
        return self._guards.load_spec(product_id)

    def _load_arch(self, product_id: str) -> dict:
        """Load inner architecture dict for agents."""
        return self._guards.load_arch(product_id)

    def _release_critic(self, product_id: str, product: dict) -> tuple[bool, list[str]]:
        """Final production-only critic pass before COMPLETED."""
        return self._guards.release_critic(product_id, product)

    def _architecture_gate(
        self, product_id: str, *, delivery_profile: str | None = None
    ) -> tuple[bool, list[str]]:
        """Gatekeeper check that must pass before developer/hardening starts."""
        return self._guards.architecture_gate(product_id, delivery_profile=delivery_profile)

    def _apply_watermark_policy(self, product_id: str, product: dict) -> None:
        """
        Viral loop policy:
        - free/unknown plan => watermark ON
        - maker/studio/enterprise => watermark OFF
        """
        md = product.get("metadata") if isinstance(product.get("metadata"), dict) else {}
        owner_plan = str((md or {}).get("owner_plan") or "free").strip().lower()
        policy = str((md or {}).get("watermark_policy") or "").strip().lower()
        if policy not in ("on", "off"):
            policy = "on" if owner_plan in ("", "free") else "off"
        if policy != "on":
            return
        code_dir = self.data_root / "code" / product_id
        if not code_dir.exists():
            return
        badge_html = (
            '<div class="aifactory-badge" style="margin-top:24px;padding:8px 12px;font:12px/1.4 system-ui;opacity:.85;">'
            'Made with <a href="https://aifactory.dev" target="_blank" rel="noopener noreferrer">AI-Factory</a>'
            "</div>"
        )
        for html_file in code_dir.rglob("*.html"):
            try:
                content = html_file.read_text(encoding="utf-8")
                if "aifactory-badge" in content:
                    continue
                if "</body>" in content.lower():
                    lower = content.lower()
                    idx = lower.rfind("</body>")
                    content = content[:idx] + badge_html + content[idx:]
                else:
                    content = content + badge_html
                html_file.write_text(content, encoding="utf-8")
            except OSError as exc:
                logger.warning("Watermark inject failed for %s: %s", html_file, exc)

    async def _process_task(
        self,
        task: dict,
        products: dict,
        task_queue: list,
        *,
        dirty_products: set[str] | None = None,
        dirty_tasks: set[str] | None = None,
    ):
        """Delegate to :class:`orchestrator.task_executor.PipelineTaskExecutor`."""
        await self._task_executor.process_task(
            self,
            task,
            products,
            task_queue,
            dirty_products=dirty_products,
            dirty_tasks=dirty_tasks,
        )

    def _latest_bug_context(self, product: dict) -> str:
        """Compact bug summary for developer/QA fix tasks (from product.last_bug_context)."""
        lb = product.get("last_bug_context")
        if not isinstance(lb, dict) or not lb:
            return ""
        try:
            return json.dumps(lb, ensure_ascii=False, default=str)[:8000]
        except (TypeError, ValueError):
            return str(lb)[:8000]

    def _create_next_task(self, product: dict) -> Optional[dict]:
        """Create the next task based on current product state."""
        from core.delivery_profile import MARKETING_LANDING

        current_state = product.get("state", "")
        if current_state == "TELEMETRY_COLLECTING" and delivery_profile_from_product_dict(product) == MARKETING_LANDING:
            return {
                "id": f"task-{uuid.uuid4().hex[:12]}",
                "product_id": product["id"],
                "agent_type": "__complete__",
                "state": "COMPLETED",
                "status": "pending",
                "retry_count": 0,
                "max_retries": 3,
                "input_data": {
                    "product_id": product["id"],
                    "idea": product.get("idea", ""),
                    "landing_fast_path": True,
                },
                "created_at": time.time(),
                "priority": self._get_priority("__complete__"),
            }

        next_info = PIPELINE_AGENT_FLOW.get(current_state)
        if not next_info:
            return None

        agent_type, next_state = next_info
        if current_state == "SECURITY_SCANNED" and agent_type == "devops":
            if post_devops_human_gate_required(product):
                next_state = "HUMAN_REVIEW_PENDING"
            else:
                next_state = "SALES_ACTIVE"
        task = {
            "id": f"task-{uuid.uuid4().hex[:12]}",
            "product_id": product["id"],
            "agent_type": agent_type,
            "state": next_state,
            "status": "pending",
            "retry_count": 0,
            "max_retries": 3,
            "input_data": {
                "product_id": product["id"],
                "idea": product.get("idea", ""),
            },
            "created_at": time.time(),
            "priority": self._get_priority(agent_type),
        }
        if current_state == "BUG_FOUND" and agent_type == "developer":
            bug_context = self._latest_bug_context(product)
            if bug_context:
                task["input_data"]["bug_context"] = bug_context
            lb = product.get("last_bug_context")
            if isinstance(lb, dict):
                if lb.get("qa_findings"):
                    task["input_data"]["qa_findings"] = lb.get("qa_findings")
                if lb.get("test_output"):
                    task["input_data"]["test_output"] = lb.get("test_output")
        if agent_type == "methodologist":
            task["input_data"]["stage"] = "post_spec"
        return task

    def _get_priority(self, agent_type: str) -> int:
        priorities = {
            "__complete__": 0,
            "analyst": 1,
            "pm": 2,
            "marketing": 3,
            "methodologist": 4,
            "architect": 5,
            "developer": 6,
            "design_critic": 6,
            "hardening": 6,
            "qa": 7,
            "security": 7,
            "devops": 8,
            "sales": 9,
            "evolution_analyst": 10,
        }
        return priorities.get(agent_type, 5)

    def _compute_content_hash(self) -> str:
        """Compute SHA256 hash of the state file to detect content changes beyond mtime."""
        try:
            with open(self.state_file, "rb") as f:
                return hashlib.sha256(f.read()).hexdigest()
        except (IOError, OSError):
            return ""

    async def _run_state_watch(self) -> None:
        from core.pipeline_state_watch import run_pipeline_state_watch

        sqlite_path = pipeline_db_path() if self.use_sql_store else None
        await run_pipeline_state_watch(
            json_path=self.state_file,
            sqlite_path=sqlite_path,
            on_wake=self.signal_new_work,
            stop_event=self._watch_stop,
        )

    def signal_new_work(self):
        """Signal the worker to wake up and process immediately (instead of waiting for next poll cycle)."""
        self._wake_event.set()

    def stop(self):
        self._running = False
        self._wake_event.set()  # Unblock the wait loop so it exits promptly


async def main():
    """Entry point for the pipeline worker."""
    worker = PipelineWorker()
    try:
        await worker.run()
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("Shutting down pipeline worker...")
        worker.stop()


if __name__ == "__main__":
    asyncio.run(main())
