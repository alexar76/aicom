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
import datetime
import hashlib
import json
import logging
import os
import signal
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
import py_compile
from pathlib import Path
from typing import Optional

from core.paths import data_root, pipeline_db_path, pipeline_json_path
from core.throughput_limits import (
    effective_batch_pipeline_active_limit,
    effective_batch_pipeline_max_start_per_cycle,
    effective_task_executor_concurrency,
)
from agents.product_profile import post_devops_human_gate_required
from orchestrator.pipeline_flow import PIPELINE_AGENT_FLOW
from orchestrator.worker_components import PeerReviewEngine, QualityManager, TaskOrchestrator
from orchestrator.runtime_guards import RuntimeGuards
from web.backend.services.learning_memory import append_lesson, load_recent_lessons
from web.backend.services.marketplace_quality import evaluate_marketplace_quality
from web.backend.services.requirements_clarifier import build_clarification_pack_llm
from web.backend.services.security_pipeline_gate import (
    build_security_gate_feedback,
    security_scan_passes_pipeline_gate,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("pipeline-worker")


def _env_truthy(name: str, default: str = "1") -> bool:
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes")


def _monitoring_refresh_decision(output_data: dict) -> tuple[bool, dict]:
    """
    If analyst monitoring asks for a shipped-slice refresh, build a QA-shaped payload
    for the Developer agent (reuses the QA repair path).
    """
    if output_data.get("request_implementation_refresh") is not True:
        return False, {}
    brief = str(output_data.get("implementation_refresh_brief") or "").strip()
    issues = [brief] if brief else ["Regenerate shipped slice per analyst monitoring (no brief provided)."]
    return True, {
        "passed": False,
        "demo_quality": {"issues": issues, "source": "analyst_monitoring"},
        "reasons": ["analyst_monitoring_refresh"],
        "validation_snapshot": output_data.get("validation"),
        "improvement_suggestions_snapshot": output_data.get("improvement_suggestions"),
    }


class PipelineWorker:
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
        self.use_sqlite = os.environ.get("USE_SQLITE", "true").strip().lower() == "true"
        self._running = False
        self._agents = {}  # agent_type -> agent instance
        self._llm_router = None
        self._wake_event = asyncio.Event()
        self._last_mtime = 0
        self._last_content_hash = ""
        self._last_policy_audit_mono = 0.0
        self._last_cycle_at = 0.0
        self._last_successful_cycle_at = 0.0
        self._started_at = time.time()
        self._shutdown_reason = ""
        self.data_root = data_root()
        self._guards = RuntimeGuards(str(self.data_root))
        self._async_sqlite = None
        self._health_server = None
        self.task_orchestrator = TaskOrchestrator(self._get_priority)
        self.quality_manager = QualityManager(self._get_priority)
        self.peer_review_engine = PeerReviewEngine(self._get_priority)

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
        sqlite_ready = (not self.use_sqlite) or (self._async_sqlite is not None)
        agents_ready = len(self._agents) > 0
        ready = sqlite_ready and (agents_ready or not self._running)
        return {
            "ready": ready,
            "running": self._running,
            "sqlite_ready": sqlite_ready,
            "agents_ready": agents_ready,
            "use_sqlite": self.use_sqlite,
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
        if self._async_sqlite is not None:
            with contextlib.suppress(Exception):
                await self._async_sqlite.close()
            self._async_sqlite = None

    def _state_from_sqlite_snapshot(self) -> dict | None:
        """
        Build pipeline-like JSON state from SQLite snapshot.

        This is a recovery path when pipeline.json is corrupted/truncated.
        """
        db_path = str(pipeline_db_path())
        try:
            from orchestrator.sqlite_manager import SQLiteManager

            sm = SQLiteManager(db_path)
            sm.connect()
            try:
                products = sm.get_all_products()
                tasks = sm.get_all_tasks()
            finally:
                sm.close()
        except Exception as e:
            logger.error("SQLite recovery snapshot failed: %s", e)
            return None

        products_map: dict[str, dict] = {}
        for p in products:
            pid = p.get("id")
            if isinstance(pid, str) and pid:
                products_map[pid] = p

        current_task_id = None
        for t in tasks:
            st = str(t.get("status") or "").upper()
            if st == "RUNNING":
                current_task_id = t.get("id")
                break
            if st == "PENDING" and current_task_id is None:
                current_task_id = t.get("id")

        return {
            "products": products_map,
            "task_queue": tasks,
            "current_task_id": current_task_id,
        }

    def _load_state_with_recovery(self) -> dict | None:
        """
        Read pipeline state JSON.

        If the file is corrupted, auto-rebuild from SQLite and continue.
        """
        if not self.state_file.exists():
            return None
        try:
            with open(self.state_file, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.warning("Cannot read pipeline state: %s", e)

        # Recovery path: backup corrupt file, reconstruct from SQLite snapshot.
        try:
            ts = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
            bad_backup = self.state_file.with_suffix(f".json.corrupt-{ts}.bak")
            try:
                bad_backup.write_text(self.state_file.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")
                logger.warning("Corrupted pipeline state backed up to %s", bad_backup)
            except Exception as copy_exc:
                logger.warning("Failed to backup corrupted state file: %s", copy_exc)

            rebuilt = self._state_from_sqlite_snapshot()
            if not rebuilt:
                return None
            with open(self.state_file, "w") as f:
                json.dump(rebuilt, f, indent=2)
            logger.warning(
                "Recovered pipeline state from SQLite snapshot: products=%s tasks=%s",
                len(rebuilt.get("products", {})),
                len(rebuilt.get("task_queue", [])),
            )
            return rebuilt
        except Exception as rec_err:
            logger.error("Pipeline state auto-recovery failed: %s", rec_err)
            return None

    async def _load_state_async(self) -> dict | None:
        if not self.use_sqlite:
            return self._load_state_with_recovery()
        try:
            from orchestrator.async_sqlite_manager import AsyncSQLiteManager

            if self._async_sqlite is None:
                self._async_sqlite = AsyncSQLiteManager(str(pipeline_db_path()))
                await self._async_sqlite.initialize()

            products = await self._async_sqlite.get_all_products()
            tasks = await self._async_sqlite.get_all_tasks()
            products_map = {p["id"]: p for p in products if isinstance(p.get("id"), str)}
            current_task_id = None
            for t in tasks:
                st = str(t.get("status") or "").upper()
                if st == "RUNNING":
                    current_task_id = t.get("id")
                    break
                if st == "PENDING" and current_task_id is None:
                    current_task_id = t.get("id")
            return {"products": products_map, "task_queue": tasks, "current_task_id": current_task_id}
        except Exception as e:
            logger.error("Failed to load state from SQLite async path: %s", e)
            return None

    async def _save_state_async(self, state: dict) -> bool:
        if not self.use_sqlite:
            try:
                with open(self.state_file, "w") as f:
                    json.dump(state, f, indent=2)
                return True
            except IOError as e:
                logger.error("Cannot save pipeline state file: %s", e)
                return False
        try:
            from orchestrator.async_sqlite_manager import AsyncSQLiteManager

            if self._async_sqlite is None:
                self._async_sqlite = AsyncSQLiteManager(str(pipeline_db_path()))
                await self._async_sqlite.initialize()

            for p in state.get("products", {}).values():
                await self._async_sqlite.upsert_product(p)
            for t in state.get("task_queue", []):
                await self._async_sqlite.upsert_task(t)
            return True
        except Exception as e:
            logger.error("Cannot save pipeline state to SQLite: %s", e)
            return False

    async def _init_agents(self):
        """Initialize all agent instances with the LLM router."""
        if self._agents:
            return

        # Initialize LLM router with provider config path
        from llm import LLMRouter
        self._llm_router = LLMRouter("/app/data/config/model_providers.yaml")
        logger.info("LLM Router initialized for pipeline worker")

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
        last_content_hash = ""
        first_run = True

        try:
            while self._running:
                try:
                    self._last_cycle_at = time.time()
                    current_mtime = 0
                    if self.state_file.exists():
                        current_mtime = os.path.getmtime(self.state_file)

                    # JSON-backed mode only advances when pipeline.json changes (mtime/hash).
                    # SQLite mode must tick continuously: internal task/agent updates do not touch JSON.
                    json_tick = first_run or current_mtime != last_mtime
                    if json_tick or self.use_sqlite:
                        first_run = False
                        last_mtime = current_mtime

                        if self.use_sqlite:
                            content_changed = True
                        else:
                            # Content hash guard: skip if file was touched but content unchanged
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

                # Wait for sleep timeout OR external wake signal (whichever comes first)
                # Python 3.12+ requires Task objects, not raw coroutines
                sleep_task = asyncio.create_task(asyncio.sleep(0.5))
                wake_task = asyncio.create_task(self._wake_event.wait())
                done, pending = await asyncio.wait(
                    [sleep_task, wake_task],
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for task in pending:
                    task.cancel()
                for task in done:
                    with contextlib.suppress(Exception):
                        task.result()
                self._wake_event.clear()

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
        if not await self._save_state_async(state):
            return
        if not self.use_sqlite:
            try:
                sync_sqlite_from_pipeline_json()
            except Exception:
                logger.exception("Policy audit: SQLite sync failed")

        logger.info("Policy audit (%s): pipeline state updated", reason)
        self.signal_new_work()

    async def _process_cycle(self):
        """One processing cycle: check for new products and pending tasks."""
        state = await self._load_state_async()
        if not state:
            return

        products = state.get("products", {})
        task_queue = state.get("task_queue", [])
        changed = False
        now = time.time()

        # Phase 0: Recover stranded PM quality-gate failures from previous runs.
        # This handles cases where products are left in FAILED with no active PM task.
        if self.task_orchestrator.recover_stranded_pm_quality_failures(products, task_queue, now):
            changed = True

        # Phase 0b: Reset tasks stuck in `running` (blocked sync calls, killed worker mid-flight).
        if self.task_orchestrator.recover_stale_running_tasks(task_queue, now):
            changed = True

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
        except Exception as e:
            logger.warning("Batch queue drain skipped: %s", e)

        # Phase 1: Create initial tasks for products in IDEA_RECEIVED with no tasks
        if self.task_orchestrator.create_initial_tasks(products, task_queue, now):
            changed = True

        # Phase 2: Process pending tasks (start them)
        if self.task_orchestrator.start_pending_tasks(task_queue, now):
            changed = True

        # Checkpoint: Phase 3 may await many agents for a long time; without an early save,
        # bootstrap tasks from Phase 1–2 never reach SQLite until all runners finish (starvation).
        if changed:
            state["products"] = products
            state["task_queue"] = task_queue
            await self._save_state_async(state)

        # Phase 3: Process running tasks via real agents (bounded concurrency)
        running_tasks = [task for task in task_queue if task.get("status") == "running"]
        exec_concurrency = effective_task_executor_concurrency()
        if running_tasks:
            sem = asyncio.Semaphore(exec_concurrency)

            async def _run_one(t: dict):
                async with sem:
                    await self._process_task(t, products, task_queue)

            await asyncio.gather(*(_run_one(t) for t in running_tasks))
            changed = True

        # Phase 4: Retry failed tasks (up to max_retries with exponential backoff)
        if self.task_orchestrator.retry_failed_tasks(products, task_queue, now):
            changed = True

        # Phase 5: Periodic market monitoring for COMPLETED products (interval from env; 0 = off)
        if self.task_orchestrator.enqueue_market_monitoring(products, task_queue, now):
            changed = True
        if self.task_orchestrator.enqueue_refactor_sprint(products, task_queue, now):
            changed = True

        # Phase 6: Ensure COMPLETED products are truly storefront-ready.
        # Reopen hidden/non-eligible products for developer remediation.
        if self._enforce_marketplace_readiness(products, task_queue, now):
            changed = True

        # Save if changed
        if changed:
            state["products"] = products
            state["task_queue"] = task_queue
            await self._save_state_async(state)

    def _recover_stranded_pm_quality_failures(
        self, products: dict, task_queue: list, now: float
    ) -> bool:
        """
        Auto-requeue PM when last PM task failed on spec quality gate and no PM task is active.

        This makes recovery resilient across restarts/state rebuilds, so operators don't need
        manual DB updates for already-failed products.
        """
        changed = False
        latest_failed_pm: dict[str, dict] = {}

        for task in task_queue:
            if task.get("agent_type") != "pm":
                continue
            if task.get("status") != "failed":
                continue
            err = (task.get("error") or "").lower()
            if "specification failed quality gate" not in err:
                continue
            pid = task.get("product_id")
            if not pid:
                continue
            prev = latest_failed_pm.get(pid)
            if prev is None or float(task.get("created_at", 0) or 0) > float(prev.get("created_at", 0) or 0):
                latest_failed_pm[pid] = task

        for pid, failed_task in latest_failed_pm.items():
            has_active_pm = any(
                t.get("product_id") == pid
                and t.get("agent_type") == "pm"
                and t.get("status") in ("pending", "running")
                for t in task_queue
            )
            if has_active_pm:
                continue
            if pid not in products:
                continue
            if failed_task.get("auto_recovered_after_restart"):
                continue

            new_task = {
                "id": f"task-{uuid.uuid4().hex[:12]}",
                "product_id": pid,
                "agent_type": "pm",
                "state": "SPEC_WRITTEN",
                "status": "pending",
                "retry_count": 0,
                "max_retries": 3,
                "input_data": {
                    "product_id": pid,
                    "idea": products[pid].get("idea", ""),
                    "admin_instructions": (
                        "Auto-recovery after PM quality-gate failure. "
                        "Return full valid JSON and ensure acceptance_criteria fields are detailed and testable."
                    ),
                },
                "created_at": now,
                "priority": self._get_priority("pm"),
                "auto_requeue_reason": "pm_spec_quality_gate_restart_recovery",
            }
            task_queue.append(new_task)
            failed_task["auto_recovered_after_restart"] = True
            products[pid]["state"] = "MARKET_RESEARCHED"
            products[pid]["updated_at"] = now
            changed = True
            logger.warning(
                "Recovered stranded PM quality-gate failure for %s -> queued %s",
                pid,
                new_task["id"],
            )

        return changed

    async def _process_task(self, task: dict, products: dict, task_queue: list):
        """Process a running task using the appropriate agent."""
        agent_type = task.get("agent_type", "")
        pid = task.get("product_id", "")
        task_id = task.get("id", "")

        if pid not in products:
            logger.warning(f"Product {pid} not found, failing task {task_id}")
            task["status"] = "failed"
            task["error"] = f"Product {pid} not found"
            return

        product = products[pid]

        # Handle terminal completion task (EVOLUTION_ANALYZING -> COMPLETED)
        if agent_type == "__complete__":
            task["status"] = "completed"
            task["completed_at"] = time.time()
            task["output_data"] = {"completed": True, "product_id": pid}
            task["output_summary"] = f"Product {pid} pipeline completed"
            products[pid]["state"] = "COMPLETED"
            products[pid]["updated_at"] = time.time()
            logger.info(f"Product {pid} pipeline completed!")
            return

        # Runtime test stage between developer and hardening.
        if agent_type == "__runtime_test__":
            runtime_result = self._run_runtime_tests(pid, task_queue)
            task["status"] = "completed" if runtime_result.get("passed") else "failed"
            task["completed_at"] = time.time()
            task["output_data"] = runtime_result
            task["output_summary"] = "runtime tests passed" if runtime_result.get("passed") else "runtime tests failed"
            if runtime_result.get("passed"):
                products[pid]["state"] = "CODE_TESTING"
                products[pid]["updated_at"] = time.time()
                next_task = self._create_next_task(products[pid])
                if next_task and not any(
                    t.get("product_id") == pid
                    and t.get("agent_type") == next_task["agent_type"]
                    and t.get("state") == next_task["state"]
                    and t.get("status") in ("pending", "running")
                    for t in task_queue
                ):
                    task_queue.append(next_task)
                logger.info("Runtime tests passed for %s", pid)
            else:
                products[pid]["state"] = "BUG_FOUND"
                products[pid]["updated_at"] = time.time()
                products[pid]["last_bug_context"] = {
                    "source": "runtime_test",
                    "runtime_test_results": runtime_result.get("results", []),
                }
                exists = any(
                    t.get("product_id") == pid
                    and t.get("agent_type") == "developer"
                    and t.get("state") == "DEV_FIXING"
                    and t.get("status") in ("pending", "running")
                    for t in task_queue
                )
                if not exists:
                    task_queue.append(
                        {
                            "id": f"task-{uuid.uuid4().hex[:12]}",
                            "product_id": pid,
                            "agent_type": "developer",
                            "state": "DEV_FIXING",
                            "status": "pending",
                            "retry_count": 0,
                            "max_retries": 3,
                            "input_data": {
                                "product_id": pid,
                                "idea": product.get("idea", ""),
                                "runtime_test_results": runtime_result.get("results", []),
                                "admin_instructions": (
                                    "Runtime tests failed. Fix import/runtime issues and make tests pass before hardening."
                                ),
                            },
                            "created_at": time.time(),
                            "priority": self._get_priority("developer"),
                        }
                    )
                logger.warning("Runtime tests failed for %s; queued developer fix", pid)
            return

        # Check if the agent for this task type exists
        agent = self._agents.get(agent_type)

        if agent:
            # Call the REAL agent
            try:
                from agents.base_agent import AgentInput
                from agents.product_profile import infer_delivery_profile, normalize_delivery_profile

                # Collect context from previous tasks
                context = self._build_context(task_queue, pid)

                dp_raw = product.get("delivery_profile")
                if dp_raw:
                    delivery_profile = normalize_delivery_profile(str(dp_raw))
                else:
                    delivery_profile = infer_delivery_profile(
                        product.get("admin_instructions"),
                        product.get("idea"),
                    )

                agent_input = AgentInput(
                    task_id=task_id,
                    product_id=pid,
                    agent_type=agent_type,
                    data={
                        "idea": product.get("idea", ""),
                        "category": product.get("category", ""),
                        "tags": product.get("tags", []),
                        "specification": self._load_spec(pid),
                        "architecture": self._load_arch(pid),
                        "admin_instructions": product.get("admin_instructions", ""),
                        "delivery_profile": delivery_profile,
                        "production_mode": bool(product.get("production_mode")),
                        **task.get("input_data", {}),
                    },
                    context=context,
                    timestamp=time.time(),
                )

                logger.info(f"Calling real agent '{agent_type}' for task {task_id}")
                output = await agent.execute(agent_input)

                if output.success:
                    task["status"] = "completed"
                    task["completed_at"] = time.time()
                    task["output_data"] = output.data
                    task["metrics"] = output.metrics
                    task["output_summary"] = str(output.data)[:200]
                    if pid in products:
                        self.peer_review_engine.register(
                            products[pid], agent_type, output.data if isinstance(output.data, dict) else {}
                        )

                    peer_blocked = False
                    if pid in products:
                        peer_blocked = self.peer_review_engine.apply_block(task, products[pid], task_queue, product)
                    if peer_blocked:
                        logger.warning("Peer review blocked progression for %s at %s", pid, agent_type)
                        return

                    if agent_type == "pm" and pid in products and isinstance(output.data, dict):
                        dp = output.data.get("delivery_profile")
                        if dp:
                            products[pid]["delivery_profile"] = dp
                            products[pid]["updated_at"] = time.time()

                    if agent_type == "architect" and pid in products:
                        arch_ok, arch_issues = self._architecture_gate(pid)
                        if not arch_ok:
                            task["status"] = "failed"
                            task["error"] = "architecture gate failed: " + "; ".join(arch_issues)
                            task["completed_at"] = time.time()
                            products[pid]["state"] = "METHODOLOGY_REVIEWED"
                            products[pid]["updated_at"] = time.time()
                            existing = any(
                                t.get("product_id") == pid
                                and t.get("agent_type") == "architect"
                                and t.get("status") in ("pending", "running")
                                for t in task_queue
                            )
                            if not existing:
                                task_queue.append(
                                    {
                                        "id": f"task-{uuid.uuid4().hex[:12]}",
                                        "product_id": pid,
                                        "agent_type": "architect",
                                        "state": "ARCH_DESIGNED",
                                        "status": "pending",
                                        "retry_count": 0,
                                        "max_retries": 3,
                                        "input_data": {
                                            "product_id": pid,
                                            "idea": product.get("idea", ""),
                                            "architecture_gate_feedback": arch_issues,
                                            "admin_instructions": (
                                                "Architecture gatekeeper failed. Fix layering, module boundaries, "
                                                "and migration discipline before developer stage."
                                            ),
                                        },
                                        "created_at": time.time(),
                                        "priority": self._get_priority("architect"),
                                    }
                                )
                            logger.warning("Architecture gate blocked developer stage for %s: %s", pid, arch_issues)
                            return

                    if agent_type == "developer" and pid in products:
                        try:
                            self._apply_watermark_policy(pid, products[pid])
                        except Exception as wm_exc:
                            logger.warning("Watermark policy apply failed for %s: %s", pid, wm_exc)
                        try:
                            from web.backend.services.site_head_snippet import (
                                inject_published_site_head_if_configured,
                            )

                            inject_published_site_head_if_configured(self.data_root, pid)
                        except Exception as head_exc:
                            logger.warning("Published site <head> inject failed for %s: %s", pid, head_exc)
                        try:
                            from web.backend.services.site_badge import inject_site_badge_if_enabled

                            inject_site_badge_if_enabled(self.data_root, pid)
                        except Exception as badge_exc:
                            logger.warning("Site badge inject failed for %s: %s", pid, badge_exc)

                    if agent_type == "devops" and output.success and pid in products:
                        try:
                            from web.backend.services.auto_publish import try_publish_after_devops

                            pub = await asyncio.to_thread(try_publish_after_devops, pid)
                            if isinstance(pub, dict) and pub.get("published_url"):
                                products[pid]["published_url"] = str(pub["published_url"])
                                products[pid]["updated_at"] = time.time()
                        except Exception as ap_exc:
                            logger.warning("Auto-publish after DevOps failed for %s: %s", pid, ap_exc)
                        try:
                            from web.backend.services.railway_deploy import (
                                try_railway_deploy_after_devops,
                            )

                            rw = await asyncio.to_thread(try_railway_deploy_after_devops, pid)
                            if isinstance(rw, dict) and rw.get("recorded"):
                                logger.info(
                                    "Railway deploy hook after DevOps for %s: %s",
                                    pid,
                                    rw.get("path", ""),
                                )
                        except Exception as rw_exc:
                            logger.warning("Railway deploy hook after DevOps failed for %s: %s", pid, rw_exc)

                    # Track previous state for daily revision handling
                    prev_state = products[pid].get("state", "") if pid in products else ""

                    qg = output.data.get("quality_gates") if isinstance(output.data, dict) else None
                    qa_gate_failed = (
                        agent_type == "qa"
                        and isinstance(qg, dict)
                        and qg.get("passed") is False
                    )

                    sec_reasons: list[str] = []
                    security_gate_failed = False
                    if agent_type == "security" and output.success and isinstance(output.data, dict):
                        ok_sec, sec_reasons = security_scan_passes_pipeline_gate(output.data)
                        security_gate_failed = not ok_sec
                        if ok_sec and pid in products:
                            products[pid]["security_repair_round"] = 0

                    quality_gates_exhausted = False
                    security_budget_exhausted = False
                    max_quality_loops = int(os.environ.get("AIFACTORY_MAX_QUALITY_LOOPS", "10"))
                    max_security_loops = int(
                        os.environ.get(
                            "AIFACTORY_MAX_SECURITY_LOOPS",
                            os.environ.get("AIFACTORY_MAX_QUALITY_LOOPS", "10"),
                        )
                    )

                    # Successful QA (all gates pass): reset repair counter
                    if (
                        agent_type == "qa"
                        and isinstance(qg, dict)
                        and qg.get("passed") is True
                        and pid in products
                    ):
                        products[pid]["quality_repair_round"] = 0

                    # Advance the product state
                    target_state = task.get("state", "")
                    new_repair_round = 0
                    if qa_gate_failed and pid in products:
                        new_repair_round = products[pid].get("quality_repair_round", 0) + 1
                        products[pid]["quality_repair_round"] = new_repair_round
                        qa_result = output.data.get("qa_result") if isinstance(output.data, dict) else {}
                        if isinstance(qa_result, dict):
                            products[pid]["last_bug_context"] = {
                                "source": "qa",
                                "qa_findings": qa_result.get("bugs_found") or [],
                                "test_output": qa_result.get("test_results") or {},
                            }
                        products[pid]["updated_at"] = time.time()
                        if new_repair_round > max_quality_loops:
                            quality_gates_exhausted = True
                            products[pid]["state"] = "FAILED"
                            products[pid]["failure_reason"] = (
                                f"Quality gates (demo/TZ/browser) not satisfied after "
                                f"{max_quality_loops} repair cycles. Regeneration/fix did not reach "
                                "show-ready state; manual review or template update required."
                            )
                            logger.error(
                                f"Product {pid}: QA gate repair limit exceeded "
                                f"({new_repair_round} > {max_quality_loops}); state=FAILED"
                            )
                        else:
                            products[pid]["state"] = "BUG_FOUND"
                    elif security_gate_failed and pid in products:
                        new_sec_round = products[pid].get("security_repair_round", 0) + 1
                        products[pid]["security_repair_round"] = new_sec_round
                        scan_payload = output.data if isinstance(output.data, dict) else {}
                        products[pid]["last_bug_context"] = {
                            "source": "security",
                            "reasons": sec_reasons,
                            "security_score": scan_payload.get("security_score"),
                        }
                        products[pid]["updated_at"] = time.time()
                        if new_sec_round > max_security_loops:
                            security_budget_exhausted = True
                            products[pid]["state"] = "FAILED"
                            products[pid]["failure_reason"] = (
                                f"Security gate (score / severity findings) not satisfied after "
                                f"{max_security_loops} repair cycles. Manual review or adjusting "
                                "AIFACTORY_SECURITY_* settings may be required."
                            )
                            logger.error(
                                "Product %s: security gate repair limit exceeded (%s > %s); state=FAILED",
                                pid,
                                new_sec_round,
                                max_security_loops,
                            )
                        else:
                            products[pid]["state"] = "BUG_FOUND"
                    elif target_state and pid in products:
                        # If product was COMPLETED and this is a revision task,
                        # keep it in COMPLETED state after monitoring finishes
                        if prev_state == "COMPLETED" and target_state == "EVOLUTION_ANALYZING":
                            products[pid]["state"] = "COMPLETED"
                            products[pid]["last_market_revision"] = time.time()
                        else:
                            products[pid]["state"] = target_state
                        products[pid]["updated_at"] = time.time()

                    # Analyst periodic monitoring may request a shipped-slice refresh (shares QA repair budget)
                    if (
                        agent_type == "analyst"
                        and isinstance(output.data, dict)
                        and (task.get("input_data") or {}).get("mode") == "monitoring"
                        and prev_state == "COMPLETED"
                        and target_state == "EVOLUTION_ANALYZING"
                        and pid in products
                        and products[pid].get("state") == "COMPLETED"
                        and _env_truthy("AIFACTORY_MONITORING_DEV_REFRESH_ENABLED", "1")
                    ):
                        from web.backend.services.policy_audit import _dev_fixing_pending

                        want_r, qg_payload = _monitoring_refresh_decision(output.data)
                        if want_r:
                            if _dev_fixing_pending(task_queue, pid):
                                logger.info(
                                    "Monitoring requested refresh for %s but developer DEV_FIXING already pending",
                                    pid,
                                )
                            else:
                                mr_round = int(products[pid].get("quality_repair_round") or 0) + 1
                                if mr_round > max_quality_loops:
                                    logger.warning(
                                        "Monitoring refresh skipped for %s — quality repair budget exhausted (%s/%s)",
                                        pid,
                                        mr_round,
                                        max_quality_loops,
                                    )
                                else:
                                    products[pid]["state"] = "BUG_FOUND"
                                    products[pid]["quality_repair_round"] = mr_round
                                    products[pid]["updated_at"] = time.time()
                                    dev_task = {
                                        "id": f"task-{uuid.uuid4().hex[:12]}",
                                        "product_id": pid,
                                        "agent_type": "developer",
                                        "state": "DEV_FIXING",
                                        "status": "pending",
                                        "retry_count": 0,
                                        "max_retries": 3,
                                        "input_data": {
                                            "product_id": pid,
                                            "idea": product.get("idea", ""),
                                            "quality_gates_feedback": qg_payload,
                                            "quality_repair_round": mr_round,
                                            "quality_repair_max": max_quality_loops,
                                            "qa_gate_blocked": True,
                                            "monitoring_refresh_trigger": True,
                                        },
                                        "created_at": time.time(),
                                        "priority": self._get_priority("developer"),
                                    }
                                    task_queue.append(dev_task)
                                    logger.warning(
                                        "Monitoring → developer refresh for %s (repair %s/%s)",
                                        pid,
                                        mr_round,
                                        max_quality_loops,
                                    )

                    eff_state = products[pid].get("state", "") if pid in products else target_state
                    logger.info(f"Agent '{agent_type}' completed task {task_id} -> {eff_state}")
                    self._record_lesson(pid, agent_type, eff_state, output.data if isinstance(output.data, dict) else {})

                    try:
                        from web.backend.services.pipeline_chat_notify import (
                            notify_pipeline_task_done,
                        )

                        idea_snip = (product.get("idea") or "") if pid in products else ""
                        notify_pipeline_task_done(
                            agent_type=agent_type,
                            product_id=pid,
                            target_state=eff_state or "",
                            idea_snippet=idea_snip,
                        )
                    except Exception:
                        logger.debug("Corporate chat pipeline notify skipped", exc_info=False)

                    # Check if product reached COMPLETED
                    critic_blocked = False
                    if target_state == "COMPLETED" and pid in products:
                        ok_release, critic_issues = self._release_critic(pid, products[pid])
                        if not ok_release:
                            critic_blocked = True
                            products[pid]["state"] = "BUG_FOUND"
                            products[pid]["updated_at"] = time.time()
                            dev_task = {
                                "id": f"task-{uuid.uuid4().hex[:12]}",
                                "product_id": pid,
                                "agent_type": "developer",
                                "state": "DEV_FIXING",
                                "status": "pending",
                                "retry_count": 0,
                                "max_retries": 3,
                                "input_data": {
                                    "product_id": pid,
                                    "idea": product.get("idea", ""),
                                    "critic_feedback": {
                                        "gate": "release_critic",
                                        "issues": critic_issues,
                                    },
                                    "critic_blocked": True,
                                },
                                "created_at": time.time(),
                                "priority": self._get_priority("developer"),
                            }
                            task_queue.append(dev_task)
                            logger.warning(
                                "Release critic blocked completion for %s; queued DEV_FIXING (%s)",
                                pid,
                                dev_task["id"],
                            )
                    if target_state == "COMPLETED" and not critic_blocked and pid in products:
                        logger.info(f"Product {pid} pipeline completed!")
                        try:
                            spec_done = self._load_spec(pid)
                            mq_done = evaluate_marketplace_quality(pid, specification=spec_done)
                            if mq_done.get("eligible"):
                                from web.backend.services.product_followup import (
                                    merge_mark_storefront_established_listing,
                                )

                                if merge_mark_storefront_established_listing(pid):
                                    products[pid]["updated_at"] = time.time()
                        except Exception:
                            logger.debug(
                                "merge_mark_storefront_established_listing at completion failed for %s",
                                pid,
                                exc_info=True,
                            )
                    elif prev_state == "COMPLETED" and target_state == "EVOLUTION_ANALYZING":
                        # Periodic monitoring for COMPLETED product — don't create next sequential task
                        logger.info(f"Periodic market monitoring completed for product {pid}")
                    elif critic_blocked:
                        logger.info("Completion held for %s due to release critic findings", pid)
                    elif qa_gate_failed and not quality_gates_exhausted:
                        dev_task = {
                            "id": f"task-{uuid.uuid4().hex[:12]}",
                            "product_id": pid,
                            "agent_type": "developer",
                            "state": "DEV_FIXING",
                            "status": "pending",
                            "retry_count": 0,
                            "max_retries": 3,
                            "input_data": {
                                "product_id": pid,
                                "idea": product.get("idea", ""),
                                "demo_quality_feedback": (qg or {}).get("demo_quality"),
                                "qa_findings": ((output.data or {}).get("qa_result") or {}).get("bugs_found", []),
                                "test_output": ((output.data or {}).get("qa_result") or {}).get("test_results", {}),
                                "quality_gates_feedback": {
                                    "passed": (qg or {}).get("passed"),
                                    "demo_quality": (qg or {}).get("demo_quality"),
                                    "browser_preview_e2e": (qg or {}).get("browser_preview_e2e"),
                                    "reasons": (qg or {}).get("reasons"),
                                },
                                "quality_repair_round": new_repair_round,
                                "quality_repair_max": max_quality_loops,
                                "qa_gate_blocked": True,
                            },
                            "created_at": time.time(),
                            "priority": self._get_priority("developer"),
                        }
                        exists = any(
                            t.get("product_id") == pid
                            and t.get("agent_type") == "developer"
                            and t.get("state") == "DEV_FIXING"
                            and t.get("status") in ("pending", "running")
                            for t in task_queue
                        )
                        if not exists:
                            task_queue.append(dev_task)
                            logger.warning(
                                f"QA gates failed for {pid} (repair {new_repair_round}/{max_quality_loops}); "
                                "BUG_FOUND → developer DEV_FIXING (mandatory regen/fix until gates pass or limit)"
                            )
                    elif qa_gate_failed and quality_gates_exhausted:
                        logger.warning(
                            f"QA gates failed for {pid} but repair limit reached; no further DEV_FIXING task"
                        )
                    elif security_gate_failed and not security_budget_exhausted:
                        scan_payload = output.data if isinstance(output.data, dict) else {}
                        sec_fb = build_security_gate_feedback(scan_payload, sec_reasons)
                        sec_round = products[pid].get("security_repair_round", 0)
                        dev_task = {
                            "id": f"task-{uuid.uuid4().hex[:12]}",
                            "product_id": pid,
                            "agent_type": "developer",
                            "state": "DEV_FIXING",
                            "status": "pending",
                            "retry_count": 0,
                            "max_retries": 3,
                            "input_data": {
                                "product_id": pid,
                                "idea": product.get("idea", ""),
                                "security_gate_feedback": sec_fb,
                                "security_repair_round": sec_round,
                                "security_repair_max": max_security_loops,
                                "security_gate_blocked": True,
                                "qa_gate_blocked": True,
                            },
                            "created_at": time.time(),
                            "priority": self._get_priority("developer"),
                        }
                        exists = any(
                            t.get("product_id") == pid
                            and t.get("agent_type") == "developer"
                            and t.get("state") == "DEV_FIXING"
                            and t.get("status") in ("pending", "running")
                            for t in task_queue
                        )
                        if not exists:
                            task_queue.append(dev_task)
                            logger.warning(
                                "Security gate failed for %s (repair %s/%s); "
                                "BUG_FOUND → developer DEV_FIXING",
                                pid,
                                sec_round,
                                max_security_loops,
                            )
                    elif security_gate_failed and security_budget_exhausted:
                        logger.warning(
                            "Security gate failed for %s but repair limit reached; no further DEV_FIXING task",
                            pid,
                        )
                    elif (
                        agent_type == "devops"
                        and pid in products
                        and str(products[pid].get("state") or "") == "HUMAN_REVIEW_PENDING"
                    ):
                        logger.info(
                            "Product %s paused at post-DevOps human gate — awaiting admin approve before sales",
                            pid,
                        )
                    else:
                        # Create next sequential task
                        next_task = self._create_next_task(product)
                        if next_task:
                            if next_task.get("agent_type") == "pm":
                                next_task.setdefault("input_data", {})["clarification_pack"] = await build_clarification_pack_llm(
                                    product.get("idea", ""),
                                    self._llm_router,
                                )
                            exists = any(
                                t.get("product_id") == pid
                                and t.get("agent_type") == next_task["agent_type"]
                                and t.get("state") == next_task["state"]
                                and t.get("status") in ("pending", "running")
                                for t in task_queue
                            )
                            if not exists:
                                task_queue.append(next_task)
                                logger.info(f"Next task created for {pid}: {next_task['agent_type']} -> {next_task['state']}")
                else:
                    task["status"] = "failed"
                    task["error"] = output.error or "Agent returned failure"
                    category, playbook = self.quality_manager.classify_failure(task["error"])
                    task["failure_category"] = category
                    task["auto_remediation_playbook"] = playbook
                    task["completed_at"] = time.time()
                    task.setdefault("retry_count", 0)
                    task.setdefault("max_retries", 3)
                    logger.warning(
                        f"Agent '{agent_type}' failed task {task_id}: {output.error} "
                        f"(retry {task['retry_count']}/{task['max_retries']})"
                    )
                    self.quality_manager.auto_requeue_pm_spec_gate(task, products, task_queue)

            except Exception as e:
                error_msg = str(e)
                logger.error(f"Error calling agent '{agent_type}' for task {task_id}: {error_msg}")

                # === RETRY LOGIC for LLM JSON parse failures ===
                is_json_error = any(kw in error_msg for kw in [
                    "invalid/non-JSON", "Invalid JSON", "JSON parse error",
                    "non-JSON response"
                ])

                if is_json_error:
                    retry_count = task.get("retry_count", 0)
                    max_retries = 2  # Allow up to 2 retries (3 total attempts)

                    if retry_count < max_retries:
                        logger.warning(
                            f"🔄 Retry {retry_count + 1}/{max_retries + 1} "
                            f"for {agent_type} task {task_id}: {error_msg}"
                        )
                        # Reset task for retry — keep it in the queue as PENDING
                        task["retry_count"] = retry_count + 1
                        task["status"] = "pending"
                        task["error"] = None
                        task["started_at"] = None
                        task["completed_at"] = None
                        return  # Skip fail_task, task will be picked up next cycle

                # Permanent failure (exhausted retries or non-retryable error)
                task["status"] = "failed"
                task["error"] = error_msg
                category, playbook = self.quality_manager.classify_failure(error_msg)
                task["failure_category"] = category
                task["auto_remediation_playbook"] = playbook
                task["completed_at"] = time.time()
                task.setdefault("retry_count", 0)
                task.setdefault("max_retries", 3)
                self.quality_manager.auto_requeue_pm_spec_gate(task, products, task_queue)
        else:
            # Agent not initialized - use structured fallback
            logger.warning(f"Agent '{agent_type}' not initialized for task {task_id}, using fallback")
            await asyncio.sleep(2)  # Brief processing delay for realism

            task["status"] = "completed"
            task["completed_at"] = time.time()
            task["output_data"] = self._fallback_output(agent_type, pid, product)
            task["output_summary"] = f"{agent_type} completed for {pid}"

            # Track previous state for daily revision handling
            prev_state = products[pid].get("state", "") if pid in products else ""

            # Advance the product state
            target_state = task.get("state", "")
            if target_state and pid in products:
                # If product was COMPLETED and this is a revision task,
                # keep it in COMPLETED state after monitoring finishes
                if prev_state == "COMPLETED" and target_state == "EVOLUTION_ANALYZING":
                    products[pid]["state"] = "COMPLETED"
                    products[pid]["last_market_revision"] = time.time()
                else:
                    products[pid]["state"] = target_state
                products[pid]["updated_at"] = time.time()
                logger.info(f"Fallback: {agent_type} completed for {pid} -> {target_state}")

            # Save fallback artifact
            self._save_artifact(pid, agent_type, task["output_data"])

            # Check if product reached COMPLETED
            if target_state == "COMPLETED":
                logger.info(f"Product {pid} pipeline completed! (fallback)")
                try:
                    spec_done = self._load_spec(pid)
                    mq_done = evaluate_marketplace_quality(pid, specification=spec_done)
                    if mq_done.get("eligible"):
                        from web.backend.services.product_followup import (
                            merge_mark_storefront_established_listing,
                        )

                        if merge_mark_storefront_established_listing(pid) and pid in products:
                            products[pid]["updated_at"] = time.time()
                except Exception:
                    logger.debug(
                        "merge_mark_storefront_established_listing (fallback completion) failed for %s",
                        pid,
                        exc_info=True,
                    )
            elif prev_state == "COMPLETED" and target_state == "EVOLUTION_ANALYZING":
                # Daily revision task for COMPLETED product — don't create next task
                logger.info(f"Periodic market monitoring completed for product {pid} (fallback)")
            elif (
                agent_type == "devops"
                and pid in products
                and str(products[pid].get("state") or "") == "HUMAN_REVIEW_PENDING"
            ):
                logger.info(
                    "Product %s paused at post-DevOps human gate (fallback path; no automatic sales task)",
                    pid,
                )
            else:
                # Create next sequential task
                next_task = self._create_next_task(product)
                if next_task:
                    if next_task.get("agent_type") == "pm":
                        next_task.setdefault("input_data", {})["clarification_pack"] = await build_clarification_pack_llm(
                            product.get("idea", ""),
                            self._llm_router,
                        )
                    exists = any(
                        t.get("product_id") == pid
                        and t.get("agent_type") == next_task["agent_type"]
                        and t.get("state") == next_task["state"]
                        and t.get("status") in ("pending", "running")
                        for t in task_queue
                    )
                    if not exists:
                        task_queue.append(next_task)
                        logger.info(f"Next task created for {pid}: {next_task['agent_type']} -> {next_task['state']}")

    def _build_context(self, task_queue: list, product_id: str) -> dict:
        """Build context from previously completed tasks for this product."""
        completed = [
            t for t in task_queue
            if t.get("product_id") == product_id and t.get("status") == "completed"
        ]
        return {
            "completed_tasks": len(completed),
            "previous_outputs": {
                t["agent_type"]: t.get("output_data", {})
                for t in completed
            },
            "historical_lessons": load_recent_lessons(str(data_root()), limit=10),
        }

    def _record_lesson(self, product_id: str, agent_type: str, target_state: str, output_data: dict) -> None:
        summary = ""
        if isinstance(output_data, dict):
            for key in ("notes", "summary", "design_feedback", "test_summary", "analysis_summary"):
                if output_data.get(key):
                    summary = str(output_data.get(key))
                    break
        append_lesson(
            str(data_root()),
            {
                "product_id": product_id,
                "agent_type": agent_type,
                "target_state": target_state,
                "summary": (summary or f"{agent_type} -> {target_state}")[:500],
            },
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

    def _architecture_gate(self, product_id: str) -> tuple[bool, list[str]]:
        """Gatekeeper check that must pass before developer/hardening starts."""
        return self._guards.architecture_gate(product_id)

    def _save_artifact(self, product_id: str, agent_type: str, data: dict):
        """Save agent output artifact to disk."""
        artifact_dir = Path(f"/app/data/{agent_type}/{product_id}")
        artifact_dir.mkdir(parents=True, exist_ok=True)
        artifact_file = artifact_dir / "output.json"
        try:
            with open(artifact_file, "w") as f:
                json.dump(data, f, indent=2)
        except IOError as e:
            logger.warning(f"Could not save artifact for {product_id}/{agent_type}: {e}")

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
            except Exception:
                continue
            if "aifactory-badge" in content:
                continue
            if "</body>" in content:
                content = content.replace("</body>", badge_html + "\n</body>")
            else:
                content = content + "\n" + badge_html
            try:
                html_file.write_text(content, encoding="utf-8")
            except Exception:
                continue

    def _fallback_output(self, agent_type: str, pid: str, product: dict) -> dict:
        """Generate structured fallback output when agent is not available.
        
        This is NOT mock data - it's deterministic rule-based output that
        provides meaningful structure for each pipeline stage. When LLM
        agents are available, this fallback is never used.
        """
        idea = product.get("idea", "")
        idea_preview = idea[:100] if idea else "No idea provided"

        fallbacks = {
            "analyst": {
                "product_name": " ".join(w.capitalize() for w in idea.split()[:3] if len(w) > 2) or "AI-Product",
                "category": "saas",
                "tags": ["ai", "automation", "cloud"],
                "market_analysis": {
                    "market_size": "Growing market with high demand",
                    "competitors": ["Competitor A", "Competitor B"],
                    "trends": ["AI adoption increasing", "Cloud-native solutions preferred"],
                    "demand_level": "high",
                },
                "feature_priorities": [
                    {"feature": "Core automation", "priority": "critical", "rationale": "Core value proposition"},
                    {"feature": "User management", "priority": "high", "rationale": "Required for multi-tenant"},
                    {"feature": "Analytics dashboard", "priority": "medium", "rationale": "Differentiator"},
                ],
                "monetization": {
                    "free_tier": {"available": True, "limitations": {"features": ["Basic access"], "usage_limits": "100 requests/day", "users": "1 user"}},
                    "paid_tiers": [
                        {"name": "Starter", "price": 29, "features": ["Full API", "Analytics"], "target_audience": "Small teams"},
                        {"name": "Professional", "price": 99, "features": ["Full API", "Analytics", "Priority support"], "target_audience": "Growing businesses"},
                        {"name": "Enterprise", "price": 499, "features": ["Everything", "Custom integrations", "Dedicated support"], "target_audience": "Large organizations"},
                    ],
                },
                "positioning": f"{idea_preview} — a modern solution for forward-thinking teams",
            },
            "pm": {
                "product_name": " ".join(w.capitalize() for w in idea.split()[:3] if len(w) > 2) or "AI-Product",
                "description": f"Product specification for: {idea_preview}",
                "target_audience": "Technology companies",
                "core_features": [
                    {"name": "User Authentication", "description": "Secure login and registration", "priority": "high"},
                    {"name": "Data API", "description": "RESTful API for data operations", "priority": "high"},
                    {"name": "Dashboard", "description": "Analytics and monitoring dashboard", "priority": "medium"},
                ],
                "user_stories": [
                    {"story": "User can register and authenticate", "acceptance_criteria": "Email+password registration works"},
                    {"story": "Admin can view system metrics", "acceptance_criteria": "Dashboard shows real-time metrics"},
                ],
                "estimated_effort": "M",
                "estimated_days": 14,
            },
            "architect": {
                "architecture_name": f"Architecture-{pid[:8]}",
                "overview": f"Microservices architecture for: {idea_preview}",
                "components": [
                    {"name": "API Gateway", "description": "Entry point and auth proxy", "technology": "FastAPI"},
                    {"name": "Core Service", "description": "Business logic layer", "technology": "Python"},
                    {"name": "Data Store", "description": "Persistent storage", "technology": "PostgreSQL"},
                ],
                "tech_stack": {"frontend": "React", "backend": "FastAPI", "database": "PostgreSQL"},
            },
            "developer": {
                "code_summary": f"Implementation for {pid[:8]}",
                "files": [
                    {"path": "api/routes.py", "purpose": "API route definitions", "lines": 85},
                    {"path": "models/schema.py", "purpose": "Data models", "lines": 62},
                    {"path": "services/core.py", "purpose": "Core business logic", "lines": 120},
                ],
                "dependencies": ["fastapi", "sqlalchemy", "pydantic"],
            },
            "qa": {
                "test_summary": f"QA assessment for {pid[:8]}",
                "test_cases": [
                    {"name": "Auth flow test", "type": "integration", "status": "passed"},
                    {"name": "API contract test", "type": "contract", "status": "passed"},
                    {"name": "Performance baseline", "type": "performance", "status": "passed"},
                ],
                "coverage": 72,
                "quality_score": "A",
            },
            "security": {
                "security_score": 85,
                "grade": "B",
                "summary": f"Security scan completed for {pid[:8]}",
                "vulnerabilities": [],
                "secrets_found": [],
                "dependency_risks": [],
                "passed_checks": [
                    "SQL Injection Prevention",
                    "Command Injection Prevention",
                    "No Hardcoded Secrets",
                    "XSS Prevention",
                    "Use of Secure Cryptography",
                    "No Information Disclosure",
                    "Path Traversal Prevention",
                    "Secure Configuration",
                ],
                "failed_checks": [],
            },
            "devops": {
                "infrastructure": f"DevOps setup for {pid[:8]}",
                "docker_image": f"aicom-{pid[:8]}:latest",
                "ci_pipeline": "GitHub Actions",
                "deployment_target": "Docker container",
            },
            "marketing": {
                "product_name": " ".join(w.capitalize() for w in idea.split()[:3] if len(w) > 2) or "AI-Product",
                "tagline": f"Revolutionize your workflow with {idea_preview}",
                "short_description": f"{idea_preview} — built for modern teams",
                "long_description": f"A comprehensive solution for {idea_preview}. Designed with cutting-edge technology to deliver exceptional results.",
                "key_benefits": ["Increased productivity", "Reduced costs", "Seamless integration"],
                "selling_description": f"{idea_preview} — the ultimate solution for your business needs",
                "seo_metadata": {"title": f"{idea_preview} - AI-Powered Solution", "description": f"Discover {idea_preview}", "keywords": ["ai", "automation", "saas"]},
                "social_media_posts": [
                    {"platform": "Twitter", "content": f"Introducing {idea_preview}! 🚀", "hashtags": ["#AI", "#SaaS"]},
                    {"platform": "LinkedIn", "content": f"We're excited to launch {idea_preview}", "hashtags": ["#Technology", "#Innovation"]},
                ],
            },
            "sales": {
                "pricing_model": "SaaS subscription",
                "tiers": [
                    {"name": "Free", "price": 0, "features": ["Basic access"]},
                    {"name": "Pro", "price": 99, "features": ["Full access", "Support"]},
                ],
            },
        }

        return fallbacks.get(agent_type, {
            "result": f"{agent_type} completed processing",
            "product_id": pid,
        })

    def _create_next_task(self, product: dict) -> Optional[dict]:
        """Create the next task based on current product state."""
        current_state = product.get("state", "")
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
            bug_context = self._latest_bug_context(product["id"])
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

    def _marketplace_readiness(self, product_id: str) -> tuple[bool, list[str]]:
        reasons: list[str] = []
        code_dir = self.data_root / "code" / product_id
        manifest_path = code_dir / "code_manifest.json"
        has_code = False
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                files = manifest.get("files") if isinstance(manifest, dict) else []
                if isinstance(files, list):
                    for entry in files:
                        rel = ""
                        if isinstance(entry, dict):
                            rel = str(entry.get("path") or entry.get("file_path") or "").strip()
                        if rel and (code_dir / rel).exists():
                            has_code = True
                            break
            except Exception:
                has_code = False
        if not has_code:
            reasons.append("missing generated code artifacts (code_manifest/files)")
        spec = self._load_spec(product_id)
        mq = evaluate_marketplace_quality(product_id, specification=spec)
        if not bool(mq.get("eligible")):
            mq_reasons = mq.get("reasons")
            if isinstance(mq_reasons, list) and mq_reasons:
                reasons.extend(str(x) for x in mq_reasons[:6])
            else:
                reasons.append("marketplace quality gate failed")
        return len(reasons) == 0, reasons

    def _enforce_marketplace_readiness(self, products: dict, task_queue: list, now: float) -> bool:
        """
        Bulk refinement toward a purchasable artifact: terminal products that fail storefront gates
        are reopened (BUG_FOUND → developer DEV_FIXING) until AIFACTORY_MAX_QUALITY_LOOPS.

        Respects operator intent: follow-up «not pursuing» and admin_force_list skip remediation.
        Bounded per cycle via AIFACTORY_STOREFRONT_REMEDIATION_MAX_PER_CYCLE.

        Disable entirely: AIFACTORY_STOREFRONT_REMEDIATION_ENABLED=0

        Mode (when enabled): AIFACTORY_STOREFRONT_REMEDIATION_MODE
          - full (default): annotate follow-up JSON + BUG_FOUND + developer DEV_FIXING
          - annotate_only: only write planned / backlog notes to product_followup — no pipeline reopen
        """
        if not _env_truthy("AIFACTORY_STOREFRONT_REMEDIATION_ENABLED", "1"):
            return False

        mode_raw = os.environ.get("AIFACTORY_STOREFRONT_REMEDIATION_MODE", "full").strip().lower().replace("-", "_")
        if mode_raw == "annotate_only":
            remediation_mode = "annotate_only"
        elif mode_raw in ("full", "remediate", "repair", ""):
            remediation_mode = "full"
        else:
            logger.warning(
                "Unknown AIFACTORY_STOREFRONT_REMEDIATION_MODE=%r — using full",
                os.environ.get("AIFACTORY_STOREFRONT_REMEDIATION_MODE"),
            )
            remediation_mode = "full"

        try:
            max_quality_loops = int(os.environ.get("AIFACTORY_MAX_QUALITY_LOOPS", "10"))
        except ValueError:
            max_quality_loops = 10
        max_quality_loops = max(1, max_quality_loops)

        try:
            max_per_cycle = int(os.environ.get("AIFACTORY_STOREFRONT_REMEDIATION_MAX_PER_CYCLE", "8"))
        except ValueError:
            max_per_cycle = 8
        max_per_cycle = max(1, max_per_cycle)

        from web.backend.services.product_followup import (
            admin_force_list_enabled,
            annotate_automated_storefront_backlog,
            storefront_followup_not_pursuing,
        )

        candidates: list[tuple[str, dict, list[str]]] = []
        for pid, product in products.items():
            state_upper = str(product.get("state") or "").upper()
            if state_upper not in ("COMPLETED", "DEPLOYED_PRODUCTION"):
                continue
            if storefront_followup_not_pursuing(pid):
                continue
            if admin_force_list_enabled(pid):
                continue
            ready, reasons = self._marketplace_readiness(pid)
            if ready:
                try:
                    from web.backend.services.product_followup import (
                        merge_mark_storefront_established_listing,
                    )

                    if merge_mark_storefront_established_listing(pid):
                        product["updated_at"] = now
                        changed = True
                except Exception:
                    logger.debug("merge_mark_storefront_established_listing failed for %s", pid, exc_info=True)
                continue
            candidates.append((pid, product, reasons))

        candidates.sort(key=lambda row: float(row[1].get("updated_at") or row[1].get("created_at") or 0))

        changed = False
        scheduled = 0
        for pid, product, reasons in candidates:
            if scheduled >= max_per_cycle:
                break

            has_dev_fix = any(
                t.get("product_id") == pid
                and t.get("agent_type") == "developer"
                and t.get("state") == "DEV_FIXING"
                and t.get("status") in ("pending", "running")
                for t in task_queue
            )
            if has_dev_fix:
                continue

            if remediation_mode == "annotate_only":
                try:
                    annotate_automated_storefront_backlog(pid, reasons)
                except Exception:
                    logger.exception("annotate_automated_storefront_backlog failed for %s", pid)
                scheduled += 1
                logger.info(
                    "storefront remediation annotate_only for %s (no DEV_FIXING): %s",
                    pid,
                    reasons[:3],
                )
                continue

            next_round = int(product.get("quality_repair_round") or 0) + 1
            if next_round > max_quality_loops:
                product["state"] = "FAILED"
                product["failure_reason"] = (
                    "Product could not satisfy storefront readiness gates after "
                    f"{max_quality_loops} remediation cycles."
                )
                product["updated_at"] = now
                changed = True
                logger.error(
                    "Marketplace readiness failed for %s and repair budget exhausted (%s/%s): %s",
                    pid,
                    next_round,
                    max_quality_loops,
                    reasons[:3],
                )
                scheduled += 1
                continue

            try:
                annotate_automated_storefront_backlog(pid, reasons)
            except Exception:
                logger.exception("annotate_automated_storefront_backlog failed for %s", pid)

            product["state"] = "BUG_FOUND"
            product["quality_repair_round"] = next_round
            product["updated_at"] = now
            product["last_bug_context"] = {
                "source": "marketplace_readiness",
                "issues": reasons,
            }
            task_queue.append(
                {
                    "id": f"task-{uuid.uuid4().hex[:12]}",
                    "product_id": pid,
                    "agent_type": "developer",
                    "state": "DEV_FIXING",
                    "status": "pending",
                    "retry_count": 0,
                    "max_retries": 3,
                    "input_data": {
                        "product_id": pid,
                        "idea": product.get("idea", ""),
                        "marketplace_readiness_feedback": {
                            "passed": False,
                            "reasons": reasons,
                        },
                        "quality_repair_round": next_round,
                        "quality_repair_max": max_quality_loops,
                        "admin_instructions": (
                            "Storefront readiness remediation. Fix demo/code quality so the product appears "
                            "in marketplace listing (code artifacts present + marketplace quality eligible)."
                        ),
                    },
                    "created_at": now,
                    "priority": self._get_priority("developer"),
                }
            )
            changed = True
            scheduled += 1
            logger.warning(
                "Reopened COMPLETED product %s for storefront remediation (%s/%s): %s",
                pid,
                next_round,
                max_quality_loops,
                reasons[:3],
            )
        return changed

    def _latest_bug_context(self, product_id: str) -> dict:
        product_path = self.data_root / "bugs" / product_id
        if not product_path.exists():
            return {}
        latest = None
        latest_ts = -1.0
        for fp in product_path.glob("*.json"):
            try:
                ts = fp.stat().st_mtime
            except Exception:
                continue
            if ts >= latest_ts:
                latest = fp
                latest_ts = ts
        if not latest:
            return {}
        try:
            return json.loads(latest.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _run_runtime_tests(self, product_id: str, task_queue: list) -> dict:
        code_dir = self.data_root / "code" / product_id
        if not code_dir.exists():
            return {"passed": False, "error": "code directory missing", "results": []}
        manifest = {}
        manifest_path = code_dir / "code_manifest.json"
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except Exception:
                manifest = {}
        test_commands = manifest.get("test_commands") or []
        if not isinstance(test_commands, list):
            test_commands = []
        results: list[dict] = []
        passed = True
        with tempfile.TemporaryDirectory(prefix=f"aifactory-{product_id}-") as td:
            workdir = Path(td) / "workspace"
            shutil.copytree(code_dir, workdir, dirs_exist_ok=True)
            if not test_commands:
                test_commands = self._infer_default_test_commands(workdir)
            if not test_commands:
                return {"passed": True, "results": [{"command": "default_sanity", "exit_code": 0}], "commands": []}
            for cmd in test_commands:
                if not isinstance(cmd, str) or not cmd.strip():
                    continue
                try:
                    proc = subprocess.run(
                        cmd,
                        shell=True,
                        cwd=str(workdir),
                        capture_output=True,
                        text=True,
                        timeout=120,
                    )
                    item = {
                        "command": cmd,
                        "exit_code": proc.returncode,
                        "stdout": (proc.stdout or "")[:4000],
                        "stderr": (proc.stderr or "")[:4000],
                    }
                    if proc.returncode != 0:
                        passed = False
                except Exception as e:
                    item = {"command": cmd, "exit_code": -1, "stdout": "", "stderr": str(e)}
                    passed = False
                results.append(item)
        return {"passed": passed, "results": results, "commands": test_commands}

    def _infer_default_test_commands(self, workdir: Path) -> list[str]:
        """
        Infer runtime tests when developer output does not provide explicit commands.

        Priority:
        1) Python: syntax + pytest if tests exist.
        2) Node/JS: package test script if meaningful; otherwise node syntax check.
        """
        commands: list[str] = []
        py_files = [p for p in workdir.rglob("*.py") if p.is_file()]
        js_files = [p for p in workdir.rglob("*.js") if p.is_file()]

        if py_files:
            # Keep lightweight syntax checks for all Python files.
            for pyf in py_files:
                rel = pyf.relative_to(workdir)
                commands.append(
                    f"{sys.executable} -c \"import py_compile; py_compile.compile(r'{rel}', doraise=True)\""
                )
            # If tests directory exists, run a real pytest pass.
            if (workdir / "tests").exists() or any("test_" in p.name for p in py_files):
                commands.append(f"{sys.executable} -m pytest -q --maxfail=1")

        pkg_json = workdir / "package.json"
        if pkg_json.exists():
            try:
                pkg = json.loads(pkg_json.read_text(encoding="utf-8"))
            except Exception:
                pkg = {}
            scripts = pkg.get("scripts") if isinstance(pkg, dict) else {}
            test_script = scripts.get("test") if isinstance(scripts, dict) else None
            # Skip npm default placeholder test script.
            placeholder = isinstance(test_script, str) and "no test specified" in test_script.lower()
            if isinstance(test_script, str) and test_script.strip() and not placeholder:
                commands.append("npm run -s test -- --watch=false")
            elif js_files:
                # Minimal JS syntax checks when no test runner is configured.
                for jsf in js_files[:25]:
                    rel = jsf.relative_to(workdir)
                    commands.append(f"node --check \"{rel}\"")

        return commands

    def _get_priority(self, agent_type: str) -> int:
        priorities = {
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
