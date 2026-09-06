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
from pathlib import Path
from typing import Any, Optional

from core.paths import data_root, model_providers_path, pipeline_db_path, pipeline_json_path
from core.public_site_url import resolve_public_site_url, sync_watermark_in_html
from core.logging_utils import log_suppressed
from core.throughput_limits import (
    effective_batch_pipeline_active_limit,
    effective_batch_pipeline_max_start_per_cycle,
    effective_task_executor_concurrency,
)
from orchestrator.pipeline_flow import PIPELINE_AGENT_FLOW
from orchestrator.pipeline_worker_persistence import PipelineStatePersistence
from orchestrator.pipeline_worker_sidecars import PipelineWorkerSidecarMixin
from orchestrator.worker_components import PeerReviewEngine, QualityManager, TaskOrchestrator
from orchestrator.runtime_guards import RuntimeGuards
from orchestrator.task_executor import PipelineTaskExecutor
from core.factory_hold import is_factory_hard_stopped, is_factory_on_hold
from orchestrator.worker_dispatch import TaskDispatcher
from orchestrator.worker_hold_gate import HoldGate
from orchestrator.worker_idle_healer import IdleProductHealer
from orchestrator.worker_task_planner import NextTaskPlanner
from orchestrator.worker_utils import env_truthy

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("pipeline-worker")

def _factory_focus_product_ids() -> list[str]:
    """Focus mode, read late and defensively: the module is imported lazily elsewhere in this
    file for the same reason — it is optional, and an import error must not stop the pipeline."""
    try:
        from core.pipeline_product_pause import get_factory_focus_product_ids

        return list(get_factory_focus_product_ids() or [])
    except Exception:  # noqa: BLE001 - focus mode is a convenience, never a blocker
        return []


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
        self._loop: asyncio.AbstractEventLoop | None = None
        # A `running` task means "someone is running it" only after our first cycle.
        self._adopted_orphans = False
        self._watch_stop = asyncio.Event()
        self._watch_task: Optional[asyncio.Task] = None
        self._last_mtime = 0
        self._last_content_hash = ""
        self._last_policy_audit_mono = 0.0
        self._last_sandbox_gc_mono = 0.0
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
        self.task_planner = NextTaskPlanner()
        # Bound to THIS module's names, resolved at call time, so the switches stay patchable
        # where every existing test already patches them — and so an operator flipping a hold
        # mid-run is seen on the next cycle rather than at worker start.
        # Late-bound like the hold switches: the concurrency env is re-read every cycle,
        # so raising it does not need a worker restart.
        self.dispatcher = TaskDispatcher(
            concurrency=lambda: effective_task_executor_concurrency()
        )
        self.idle_healer = IdleProductHealer(
            create_next_task=self._create_next_task,
            get_priority=self._get_priority,
        )
        self.hold_gate = HoldGate(
            is_hard_stopped=lambda: is_factory_hard_stopped(),
            is_on_hold=lambda: is_factory_on_hold(),
            focus_ids=_factory_focus_product_ids,
        )
        self.task_orchestrator = TaskOrchestrator(self._get_priority)
        self.quality_manager = QualityManager(self._get_priority)
        self.peer_review_engine = PeerReviewEngine(self._get_priority)
        self._task_executor = PipelineTaskExecutor()
        # Per-product locks serialize the mutate-and-save in Phase 3: two tasks for the
        # same product (or a task + a heal/recover path) must not interleave at agent
        # await points and have the later writer clobber the earlier one's product/task
        # mutations. Keyed by product_id; created lazily.
        self._product_locks: dict[str, asyncio.Lock] = {}
        self._redis_wake: Any = None

    def _start_redis_wake_listener(self) -> None:
        from orchestrator.queue_backend import pipeline_queue_backend

        if pipeline_queue_backend() != "redis":
            return
        try:
            from orchestrator.redis_wake import RedisWakeListener

            # wake_local, NOT signal_new_work: the listener pops a wake off the very key
            # signal_new_work publishes to. Wired to the fan-out version it answered every
            # wake with a fresh wake and span the queue forever.
            self._redis_wake = RedisWakeListener(on_wake=self.wake_local)
            self._redis_wake.start()
            logger.info("Redis pipeline wake listener started")
        except Exception as exc:
            logger.warning("Redis wake listener disabled: %s", exc)

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

        # Sync LLM key/models from secrets before loading router (respects fleet profile)
        try:
            from llm.startup_provider_sync import sync_provider_at_startup

            sync_provider_at_startup(reset_circuit=True)
        except Exception as exc:
            logger.warning("LLM provider sync skipped: %s", exc)

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
            from agents.landing_architect import LandingArchitectAgent
            from agents.landing_developer import LandingDeveloperAgent

            self._agents = {
                "pm": PMAgent(self._llm_router),
                "architect": ArchitectAgent(self._llm_router),
                "landing_architect": LandingArchitectAgent(self._llm_router),
                "design_critic": DesignCriticAgent(self._llm_router),
                "methodologist": MethodologyAgent(self._llm_router),
                "developer": DeveloperAgent(self._llm_router),
                "landing_developer": LandingDeveloperAgent(self._llm_router),
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
        # The wake event belongs to THIS loop. Remember it so a background thread
        # (the Redis wake listener) can wake us without touching asyncio internals
        # from the wrong thread.
        self._loop = asyncio.get_running_loop()
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
        self._start_redis_wake_listener()
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
        try:
            await self._reap_sandbox_previews_once("startup")
        except Exception as e:
            logger.error("Startup sandbox preview GC failed: %s", e)
        self._last_sandbox_gc_mono = time.monotonic()

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
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.error(f"Processing cycle error: {e}")

                # Event-driven idle: wake on /wake or signal_new_work(); else adaptive poll timeout.
                from core.pipeline_product_pause import is_factory_focus_mode_active

                paused = is_factory_on_hold() and not is_factory_focus_mode_active()
                poll_active = self._has_active_pipeline_work and not paused
                woke = await self._wait_next_cycle(
                    self._poll_interval_sec(poll_active)
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
                        except asyncio.CancelledError:
                            raise
                        except Exception as e:
                            logger.error(f"Periodic policy audit failed: {e}")
                try:
                    gc_interval = float(os.environ.get("AIFACTORY_SANDBOX_GC_INTERVAL_SEC", "900"))
                except ValueError:
                    gc_interval = 900.0
                if gc_interval > 0:
                    now_gc = time.monotonic()
                    if now_gc - self._last_sandbox_gc_mono >= gc_interval:
                        self._last_sandbox_gc_mono = now_gc
                        try:
                            await self._reap_sandbox_previews_once("periodic")
                        except asyncio.CancelledError:
                            raise
                        except Exception as e:
                            logger.error("Periodic sandbox preview GC failed: %s", e)
        finally:
            self._watch_stop.set()
            if self._watch_task is not None:
                self._watch_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await self._watch_task
            await self._close_resources()

    async def _reap_sandbox_previews_once(self, reason: str) -> None:
        """Drop leftover DinD preview containers/volumes. Safe during factory hold."""
        from web.backend.services.sandbox_docker import reap_stale_preview_resources

        stats = await asyncio.to_thread(reap_stale_preview_resources)
        if any(int(v or 0) for v in stats.values()):
            logger.info("sandbox preview GC (%s): %s", reason, stats)

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

        now = time.time()

        # Phase 0 (once per process): tasks still `running` when we start belong to a run that
        # died. Ahead of the hold gate on purpose — under a soft hold the gate flips every
        # `running` row to `pending` before anything can tell they were orphans, so the crash
        # ladder was silently skipped for exactly the worker that had just crashed. Never under
        # a hard stop, where the instruction is to touch nothing.
        if not self._adopted_orphans and not self.hold_gate.hard_stopped():
            if self.task_orchestrator.adopt_orphaned_running_tasks(products, task_queue, now):
                state["products"] = products
                state["task_queue"] = task_queue
                # Persisted HERE, and the flag is only set once it lands. Setting the flag first
                # meant a single failed write lost the adoption for the life of the process,
                # while the tasks stayed `running` in the store for the next start to find.
                if await self._save_state_async(state, sql_full_save=True):
                    self._adopted_orphans = True
                    changed = True
            else:
                self._adopted_orphans = True

        # Hard stop / focus mode / soft hold, decided in one place (orchestrator/worker_hold_gate.py).
        # The gate's only mutation is putting held `running` tasks back to `pending`; persisting
        # that is this worker's job, because the gate does no IO.
        verdict = self.hold_gate.evaluate(task_queue)
        # A plain soft hold says nothing: the pre-split code was silent unless it actually
        # reset running tasks, and a line every poll interval turns a paused factory into a
        # log nobody reads. The reset below still announces itself.
        if verdict.reason and not (verdict.soft_hold and not verdict.reset_running):
            logger.info("%s", verdict.reason)
        if not verdict.proceed:
            self._has_active_pipeline_work = False
            if verdict.reset_running:
                state["products"] = products
                state["task_queue"] = task_queue
                await self._save_state_async(state, sql_full_save=True)
                logger.info(
                    "Factory on hold — reset %d running task(s) to pending (%d products, %d tasks paused)",
                    verdict.reset_running,
                    len(products),
                    len(task_queue),
                )
            return
        soft_hold = verdict.soft_hold

        changed = False
        dirty_products: set[str] = set()
        dirty_tasks: set[str] = set()
        sql_full_save = False

        # Phase 0/0b: repair what a previous run left behind — stranded PM quality-gate
        # failures, products FAILED with no live task, state that disagrees with its own
        # task, and tasks stuck in `running`. The sweeps and their order are owned by
        # TaskOrchestrator.RECOVERY_SWEEPS.
        if self.task_orchestrator.run_recovery_sweeps(products, task_queue, now):
            changed = True
            sql_full_save = True

        # Phase 0.1: Drain batch idea queue with controlled concurrency.
        # Skipped on soft hold or focus mode — bulk starts would compete with the focus target.
        if not soft_hold:
            try:
                from core.pipeline_product_pause import is_factory_focus_mode_active

                focus_active = is_factory_focus_mode_active()
            except Exception:
                focus_active = False
            if not focus_active:
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
        if not soft_hold and self.task_orchestrator.create_initial_tasks(products, task_queue, now):
            changed = True
            sql_full_save = True

        # Phase 2: Process pending tasks (start them)
        if not soft_hold and self.task_orchestrator.start_pending_tasks(products, task_queue, now):
            changed = True
            sql_full_save = True

        # Checkpoint: Phase 3 may await many agents for a long time; without an early save,
        # bootstrap tasks from Phase 1–2 never reach SQLite until all runners finish (starvation).
        if changed:
            cp_products, cp_tasks = products, task_queue
            state["products"] = cp_products
            state["task_queue"] = cp_tasks
            await self._save_state_async(state, sql_full_save=True)
            self._has_active_pipeline_work = any(
                t.get("status") in ("pending", "running") for t in cp_tasks
            )

        # Phase 3: Process running tasks via real agents (bounded concurrency)
        if not soft_hold:
            outcome = await self.dispatcher.dispatch(
                task_queue,
                lambda t: self._process_task(
                    t, products, task_queue, dirty_products=dirty_products, dirty_tasks=dirty_tasks
                ),
            )
            if outcome.changed:
                changed = True

        # Phase 4: Retry failed tasks (up to max_retries with exponential backoff)
        if not soft_hold and self.task_orchestrator.retry_failed_tasks(products, task_queue, now):
            changed = True
            sql_full_save = True

        # Phase 4b: Dedupe active tasks; cancel regressive re-queues (PM on DEV_FIXING, etc.)
        if not soft_hold and self.task_orchestrator.enforce_queue_hygiene(products, task_queue, now):
            changed = True
            sql_full_save = True

        # Phase 4b2: budget-parked products resume the moment headroom exists. Unconditional — not
        # gated by soft_hold — because focus products keep running under a hold, and this is exactly
        # the state a held factory left a product to rot in for 45 minutes.
        from orchestrator.task_queue_hygiene import unpark_budget_exhausted

        for _pid in unpark_budget_exhausted(products):
            changed = True
            sql_full_save = True
            dirty_products.add(_pid)

        # Phase 4b3: a shipped product that today's detectors call broken goes back into repair.
        # Bounded to once per scoring-rules version, so a sharper gate reconsiders its own past
        # verdicts exactly once instead of spinning.
        from orchestrator.task_queue_hygiene import reopen_completed_with_critical_defects

        for _pid in reopen_completed_with_critical_defects(products):
            changed = True
            sql_full_save = True
            dirty_products.add(_pid)

        # Phase 4c: Idle mid-pipeline products with no active task → enqueue next sequential step
        if not soft_hold:
            healed = self.idle_healer.heal(products, task_queue)
            if healed.changed:
                changed = True
                sql_full_save = True
                dirty_products |= healed.healed_product_ids
                dirty_tasks |= healed.healed_task_ids

        # A COMPLETED product whose Vercel --prod failed is not shipped. Reopen even
        # during a soft hold: this is a gate, not a polish sprint.
        try:
            if self._enforce_failed_vercel_publish(products, task_queue, now):
                changed = True
                sql_full_save = True
        except Exception as exc:
            logger.debug("vercel publish reopen skipped: %s", exc)

        # Phases 5 & 6 are post-ship *improvement* work (re-opening already-shipped
        # products). They stay paused during a soft hold — only fresh on-demand
        # builds advance.
        if not soft_hold:
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
        final_products, final_tasks = products, task_queue
        if changed:
            state["products"] = final_products
            state["task_queue"] = final_tasks
            await self._save_state_async(
                state,
                sql_full_save=sql_full_save,
                dirty_product_ids=dirty_products if not sql_full_save else None,
                dirty_task_ids=dirty_tasks if not sql_full_save else None,
            )

        self._has_active_pipeline_work = (
            not soft_hold
            and any(t.get("status") in ("pending", "running") for t in final_tasks)
        )

        # Bound the per-product lock registry: drop unheld locks for products no longer
        # present in the state so it cannot grow without limit over a long-lived worker.
        if self._product_locks:
            live_ids = set(final_products.keys())
            for stale_pid in [
                k
                for k, lk in self._product_locks.items()
                if k not in live_ids and not lk.locked()
            ]:
                self._product_locks.pop(stale_pid, None)

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
        link_url = resolve_public_site_url()
        for html_file in code_dir.rglob("*.html"):
            try:
                content = html_file.read_text(encoding="utf-8")
                updated = sync_watermark_in_html(content, link_url)
                if updated != content:
                    html_file.write_text(updated, encoding="utf-8")
            except OSError as exc:
                logger.warning("Watermark inject failed for %s: %s", html_file, exc)

    def _product_lock(self, product_id: str) -> asyncio.Lock:
        """Lazily get (or create) the per-product Phase 3 mutate-and-save lock."""
        lock = self._product_locks.get(product_id)
        if lock is None:
            lock = asyncio.Lock()
            self._product_locks[product_id] = lock
        return lock

    async def _process_task(
        self,
        task: dict,
        products: dict,
        task_queue: list,
        *,
        dirty_products: set[str] | None = None,
        dirty_tasks: set[str] | None = None,
    ):
        """Delegate to :class:`orchestrator.task_executor.PipelineTaskExecutor`.

        Wrapped in a ``factory.pipeline_stage`` span so any LLM calls the
        agent makes during the stage become child spans — LangSmith /
        Phoenix render the resulting trace tree as
        ``factory.pipeline_stage → llm.generate``.

        Serialized per product (asyncio.Lock keyed by product_id) so concurrent
        Phase 3 runners for the same product cannot interleave their reads/writes of
        the shared ``products`` / ``task_queue`` state and overwrite each other.
        """
        from core.tracing import span

        attrs = {
            "factory.task_id": str(task.get("id") or ""),
            "factory.agent_type": str(task.get("agent_type") or ""),
            "factory.target_state": str(task.get("state") or ""),
            "aifactory.product_id": str(task.get("product_id") or ""),
            "product.id": str(task.get("product_id") or ""),
            "factory.retry": int(task.get("retry_count") or 0),
        }
        stage_name = f"factory.pipeline_stage:{task.get('agent_type') or 'unknown'}"
        pid = str(task.get("product_id") or "")
        async with self._product_lock(pid):
            with span(stage_name, attributes=attrs):
                await self._task_executor.process_task(
                    self,
                    task,
                    products,
                    task_queue,
                    dirty_products=dirty_products,
                    dirty_tasks=dirty_tasks,
                )
                # Optional, auto-detecting, fail-open Metis confidence-gate.
                # No-op when Metis is absent/disabled; never blocks the pipeline.
                await self._maybe_metis_gate(task, products)

    async def _maybe_metis_gate(self, task: dict, products: dict) -> None:
        """Advisory Metis confidence-gate on high-stakes stages.

        Auto-detects a Metis service (``AIFACTORY_METIS_GATE`` defaults to
        ``auto``); when one is reachable it records a verification envelope on the
        product (``product["metis_gate"]``) and, if it flags low confidence,
        logs a warning. It is purely additive telemetry: the pipeline flow is
        unchanged unless ``AIFACTORY_METIS_GATE_BLOCK`` is set. Fully fail-open —
        Metis being absent, down, or slow is a silent no-op, never an error.
        """
        try:
            from llm.metis_gate import metis_gate_blocking, metis_gate_enabled

            if not metis_gate_enabled():
                return
            agent_type = str(task.get("agent_type") or "")
            gated = os.environ.get("AIFACTORY_METIS_GATE_STAGES", "architect,methodologist")
            if agent_type not in {s.strip() for s in gated.split(",") if s.strip()}:
                return
            pid = str(task.get("product_id") or "")
            product = products.get(pid) if isinstance(products, dict) else None
            if not isinstance(product, dict):
                return

            from llm.metis_gate import verify_product_understanding

            idea = str(product.get("idea") or (task.get("input_data") or {}).get("idea") or "")
            spec = product.get("spec") or product.get("architecture") or ""
            if isinstance(spec, (dict, list)):
                spec = json.dumps(spec, ensure_ascii=False, default=str)[:8000]
            verdict = await asyncio.to_thread(
                verify_product_understanding, idea, str(spec) if spec else None
            )
            product["metis_gate"] = {
                "stage": agent_type,
                "ok": verdict.ok,
                "status": verdict.status,
                "verify_score": verdict.verify_score,
                "verified": verdict.verified,
                "route": verdict.route,
                "clarifications": verdict.clarifications[:5],
                "blocked": bool(not verdict.ok and metis_gate_blocking()),
                "at": time.time(),
                "reason": verdict.reason or None,
            }
            if not verdict.available:
                # Fail-open but keep telemetry (e.g. client timeout vs Metis down).
                return
            if not verdict.ok:
                logger.warning(
                    "metis gate flagged %s for %s: status=%s score=%.2f%s",
                    agent_type, pid, verdict.status, verdict.verify_score,
                    " [BLOCK]" if metis_gate_blocking() else " (advisory)",
                )
        except Exception:  # never let the gate destabilise the pipeline
            log_suppressed(logger, "metis confidence-gate skipped")

    # ── next-task planning ───────────────────────────────────────────────────
    # The rules moved to orchestrator/worker_task_planner.py — they are a pure function of a
    # product dict, and living on a worker made them reachable only through state, a queue and an
    # event loop. These stay as the worker's own surface because every call site inside the cycle
    # reads better through it.

    def _latest_bug_context(self, product: dict) -> str:
        return self.task_planner.latest_bug_context(product)

    def _create_next_task(self, product: dict) -> Optional[dict]:
        return self.task_planner.create_next_task(product)

    def _get_priority(self, agent_type: str) -> int:
        return self.task_planner.priority(agent_type)

    def _compute_content_hash(self) -> str:
        """Compute SHA256 hash of the state file to detect content changes beyond mtime.

        Stays on the worker: it is about THIS worker's state file, not about what a product
        needs next.
        """
        try:
            with open(self.state_file, "rb") as f:
                return hashlib.sha256(f.read()).hexdigest()
        except (IOError, OSError):
            return ""


    async def _run_state_watch(self) -> None:
        from core.pipeline_state_watch import run_pipeline_state_watch

        sqlite_path = pipeline_db_path() if self.use_sql_store else None
        while self._running and not self._watch_stop.is_set():
            try:
                await run_pipeline_state_watch(
                    json_path=self.state_file,
                    sqlite_path=sqlite_path,
                    on_wake=self.wake_local,
                    stop_event=self._watch_stop,
                )
                return
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Pipeline state watch crashed; restarting in 2s")
                try:
                    await asyncio.wait_for(self._watch_stop.wait(), timeout=2.0)
                except TimeoutError:
                    continue

    def wake_local(self) -> None:
        """Wake THIS worker, safely from any thread, without telling anyone else.

        ``asyncio.Event.set()`` is not thread-safe: it resolves waiter futures, which must
        happen on the loop that owns them. The Redis wake listener is a real thread, so it
        called this across a thread boundary on every wake — usually getting away with it,
        which is the worst way for a bug like this to behave.
        """
        loop = self._loop
        if loop is None:
            self._wake_event.set()
            return
        try:
            on_loop = asyncio.get_running_loop() is loop
        except RuntimeError:
            on_loop = False
        if on_loop:
            self._wake_event.set()
            return
        try:
            loop.call_soon_threadsafe(self._wake_event.set)
        except RuntimeError:
            # Loop already closed — the worker is shutting down and has nothing to wake for.
            logger.debug("wake dropped: event loop closed")

    @staticmethod
    def _publish_wake() -> None:
        try:
            from orchestrator.redis_wake import publish_wake

            publish_wake("local")
        except Exception:
            pass

    def signal_new_work(self):
        """Wake this worker AND fan the signal out to the other workers over Redis."""
        self.wake_local()
        loop = self._loop
        try:
            on_loop = loop is not None and asyncio.get_running_loop() is loop
        except RuntimeError:
            on_loop = False
        if not on_loop:
            self._publish_wake()
            return
        # publish_wake opens a TCP connection and LPUSHes synchronously. On the Redis
        # backend that is a blocking network call, and two of its callers run on the event
        # loop — including the /wake HTTP handler, where an unreachable Redis would stall
        # the whole worker for the connect timeout. Our own wake already happened above;
        # telling the others can finish in a thread.
        try:
            loop.run_in_executor(None, self._publish_wake)
        except RuntimeError:
            self._publish_wake()

    def stop(self):
        self._running = False
        if self._redis_wake is not None:
            self._redis_wake.stop()
        self.wake_local()  # Unblock the wait loop so it exits promptly


async def main():
    """Entry point for the pipeline worker."""
    # Initialize OpenTelemetry tracing (no-op when OTEL_EXPORTER_OTLP_ENDPOINT
    # is unset). Boots the tracer once so pipeline-stage spans + their child
    # LLM spans appear in LangSmith / Phoenix from the very first cycle.
    try:
        from core.tracing import init_tracing

        if init_tracing(service_name=os.environ.get("OTEL_SERVICE_NAME") or "aicom-worker"):
            logger.info("OpenTelemetry tracing active (pipeline worker)")
    except Exception as exc:
        logger.warning("OpenTelemetry init skipped: %s", exc)

    worker = PipelineWorker()
    try:
        await worker.run()
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("Shutting down pipeline worker...")
        worker.stop()


if __name__ == "__main__":
    asyncio.run(main())
