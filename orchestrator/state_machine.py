"""
Pipeline State Machine
=======================
Finite State Machine for the product development pipeline.
Manages the lifecycle of each product from idea to deployment.
"""

from __future__ import annotations

import asyncio
import enum
import logging
import os
import threading
import time
from dataclasses import dataclass, field

from agents.product_profile import post_devops_human_gate_required
from core.delivery_profile import MARKETING_LANDING, normalize_delivery_profile
from core.paths import pipeline_db_path, pipeline_json_path
from orchestrator.pipeline_flow import PIPELINE_AGENT_FLOW
from orchestrator.pipeline_repository import PipelineRepository
from web.backend.api.metrics import PrometheusMetrics

logger = logging.getLogger(__name__)


class PipelineState(enum.Enum):
    """All possible states in the product development pipeline."""
    IDEA_RECEIVED = "idea_received"
    MARKET_RESEARCHED = "market_researched"
    SPEC_WRITTEN = "spec_written"
    ARCH_DESIGNED = "arch_designed"
    DESIGN_CRITIQUED = "design_critiqued"
    CODE_COMMITTED = "code_committed"
    CODE_TESTING = "code_testing"
    QA_TESTING = "qa_testing"
    BUG_FOUND = "bug_found"
    DEV_FIXING = "dev_fixing"
    SECURITY_SCANNED = "security_scanned"
    HUMAN_REVIEW_PENDING = "human_review_pending"
    MARKET_CONTENT_READY = "market_content_ready"
    METHODOLOGY_REVIEWED = "methodology_reviewed"
    SALES_ACTIVE = "sales_active"
    SANDBOX_RUNNING = "sandbox_running"
    TELEMETRY_COLLECTING = "telemetry_collecting"
    EVOLUTION_ANALYZING = "evolution_analyzing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskStatus(enum.Enum):
    """Status of a task within the pipeline."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    BLOCKED = "blocked"


@dataclass
class Task:
    """A single task in the pipeline."""
    id: str
    product_id: str
    agent_type: str
    state: PipelineState
    status: TaskStatus = TaskStatus.PENDING
    input_data: dict = field(default_factory=dict)
    output_data: dict = field(default_factory=dict)
    created_at: float = 0.0
    started_at: float | None = None
    completed_at: float | None = None
    timeout_sec: int = 30
    retry_count: int = 0
    max_retries: int = 3
    error: str | None = None
    priority: int = 5

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "product_id": self.product_id,
            "agent_type": self.agent_type,
            "state": self.state.value,
            "status": self.status.value,
            "input_data": self.input_data,
            "output_data": self.output_data,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "timeout_sec": self.timeout_sec,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "error": self.error,
            "priority": self.priority,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Task:
        task = cls(
            id=data["id"],
            product_id=data["product_id"],
            agent_type=data["agent_type"],
            state=PipelineState(data["state"]),
            status=TaskStatus(data["status"]),
            input_data=data.get("input_data", {}),
            output_data=data.get("output_data", {}),
            created_at=data.get("created_at", 0),
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
            timeout_sec=data.get("timeout_sec", 30),
            retry_count=data.get("retry_count", 0),
            max_retries=data.get("max_retries", 3),
            error=data.get("error"),
            priority=data.get("priority", 5),
        )
        return task


@dataclass
class Product:
    """A product moving through the pipeline."""
    id: str
    idea: str
    state: PipelineState = PipelineState.IDEA_RECEIVED
    tasks: list[Task] = field(default_factory=list)
    created_at: float = 0.0
    updated_at: float = 0.0
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "idea": self.idea,
            "state": self.state.value,
            "tasks": [t.to_dict() for t in self.tasks],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Product:
        product = cls(
            id=data["id"],
            idea=data["idea"],
            state=PipelineState(data["state"]),
            tasks=[Task.from_dict(t) for t in data.get("tasks", [])],
            created_at=data.get("created_at", 0),
            updated_at=data.get("updated_at", 0),
            metadata=data.get("metadata", {}),
        )
        return product


# State transition map: current_state -> list of possible next states
STATE_TRANSITIONS: dict[PipelineState, list[PipelineState]] = {
    PipelineState.IDEA_RECEIVED: [PipelineState.MARKET_RESEARCHED, PipelineState.FAILED],
    PipelineState.MARKET_RESEARCHED: [PipelineState.SPEC_WRITTEN, PipelineState.FAILED],
    PipelineState.SPEC_WRITTEN: [PipelineState.MARKET_CONTENT_READY, PipelineState.FAILED],
    PipelineState.MARKET_CONTENT_READY: [
        PipelineState.METHODOLOGY_REVIEWED,
        PipelineState.FAILED,
    ],
    PipelineState.METHODOLOGY_REVIEWED: [PipelineState.ARCH_DESIGNED, PipelineState.FAILED],
    PipelineState.ARCH_DESIGNED: [PipelineState.DESIGN_CRITIQUED, PipelineState.CODE_COMMITTED, PipelineState.FAILED],
    PipelineState.DESIGN_CRITIQUED: [PipelineState.CODE_COMMITTED, PipelineState.FAILED],
    PipelineState.CODE_COMMITTED: [PipelineState.CODE_TESTING, PipelineState.QA_TESTING, PipelineState.FAILED],
    PipelineState.CODE_TESTING: [PipelineState.DEV_FIXING, PipelineState.QA_TESTING, PipelineState.FAILED],
    PipelineState.QA_TESTING: [
        PipelineState.BUG_FOUND,
        PipelineState.SECURITY_SCANNED,
        PipelineState.FAILED,
    ],
    PipelineState.BUG_FOUND: [PipelineState.DEV_FIXING, PipelineState.FAILED],
    PipelineState.DEV_FIXING: [PipelineState.QA_TESTING, PipelineState.FAILED],
    PipelineState.SECURITY_SCANNED: [
        PipelineState.HUMAN_REVIEW_PENDING,
        PipelineState.SALES_ACTIVE,
        PipelineState.FAILED,
    ],
    PipelineState.HUMAN_REVIEW_PENDING: [PipelineState.SALES_ACTIVE, PipelineState.BUG_FOUND, PipelineState.FAILED],
    PipelineState.SALES_ACTIVE: [PipelineState.SANDBOX_RUNNING, PipelineState.FAILED],
    PipelineState.SANDBOX_RUNNING: [PipelineState.TELEMETRY_COLLECTING, PipelineState.FAILED],
    PipelineState.TELEMETRY_COLLECTING: [PipelineState.EVOLUTION_ANALYZING, PipelineState.FAILED],
    PipelineState.EVOLUTION_ANALYZING: [PipelineState.COMPLETED, PipelineState.FAILED],
    PipelineState.COMPLETED: [],
    PipelineState.FAILED: [],
    PipelineState.CANCELLED: [],
}


class PipelineStateMachine:
    """
    Finite State Machine managing the product pipeline.
    
    Features:
    - Strict state transitions (no skipping steps)
    - File-based persistence (single source of truth) when use_sqlite=False
    - SQLite persistence when use_sqlite=True
    - Task queue management
    - Retry logic with configurable limits
    """

    def __init__(
        self,
        state_file: str | None = None,
        use_sqlite: bool | None = None,
        db_path: str | None = None,
    ):
        self.state_file = state_file or str(pipeline_json_path())
        if use_sqlite is None:
            # Prefer JSON for explicit file-based test/dev instances; runtime worker passes explicit sqlite intent.
            self.use_sqlite = False if state_file else os.environ.get("USE_SQLITE", "true").strip().lower() == "true"
        else:
            self.use_sqlite = use_sqlite
        self.db_path = db_path or str(pipeline_db_path())
        self.products: dict[str, Product] = {}
        self.task_queue: list[Task] = []
        self._repo = PipelineRepository(self.state_file, self.db_path, self.use_sqlite)
        # Serializes the pending -> running flip within this process; the conditional
        # UPDATE in the repository is what serializes it across processes.
        self._claim_lock = threading.Lock()
        self._aclaim_lock: asyncio.Lock | None = None
        self._aclaim_lock_loop: asyncio.AbstractEventLoop | None = None
        self._load_state()

    @property
    def sqlite_manager(self):
        """The synchronous SQLiteManager backing this machine (None unless use_sqlite)."""
        return self._repo.sqlite_manager

    def close(self) -> None:
        """Release the synchronous store connection."""
        self._repo.close()

    async def aclose(self) -> None:
        """Release the async store connection held across saves."""
        await self._repo.aclose()

    def create_product(self, idea: str, product_id: str | None = None) -> Product:
        """Create a new product and add it to the pipeline."""
        import uuid
        pid = product_id or f"prod-{uuid.uuid4().hex[:12]}"
        
        product = Product(
            id=pid,
            idea=idea,
            state=PipelineState.IDEA_RECEIVED,
            created_at=time.time(),
            updated_at=time.time(),
        )
        
        self.products[pid] = product
        self._save_state()
        PrometheusMetrics.inc_product_created()
        logger.info(f"Created product {pid}: {idea[:50]}...")
        return product

    async def acreate_product(self, idea: str, product_id: str | None = None) -> Product:
        """Async create path with non-blocking SQLite persistence."""
        import uuid
        pid = product_id or f"prod-{uuid.uuid4().hex[:12]}"
        product = Product(
            id=pid,
            idea=idea,
            state=PipelineState.IDEA_RECEIVED,
            created_at=time.time(),
            updated_at=time.time(),
        )
        self.products[pid] = product
        await self._asave_state()
        PrometheusMetrics.inc_product_created()
        return product

    def _pending_by_priority(self) -> list[Task]:
        """Pending tasks, highest priority first, then oldest first."""
        pending = [t for t in self.task_queue if t.status == TaskStatus.PENDING]
        # Sort by priority (lower number = higher priority) then by creation time
        pending.sort(key=lambda t: (t.priority, t.created_at))
        return pending

    @staticmethod
    def _apply_claim_loss(task: Task, stored: dict | None) -> None:
        """Adopt the store's view of a task another worker claimed out from under us.

        Without this the task stays PENDING in memory, gets offered again on the next
        call, and loses the same race forever — and the next save would write our stale
        copy back over the winner's row.
        """
        if stored:
            try:
                task.status = TaskStatus(str(stored.get("status") or "").lower())
            except ValueError:
                task.status = TaskStatus.RUNNING
            task.started_at = stored.get("started_at")
        else:
            task.status = TaskStatus.RUNNING

    def get_next_task(self) -> Task | None:
        """Claim the next pending task from the queue (highest priority first).

        The pending -> running flip is delegated to the store, so two workers picking
        from the same queue cannot both come away with the same task: the loser's
        conditional UPDATE matches no row and it moves on to the next candidate.
        """
        with self._claim_lock:
            for task in self._pending_by_priority():
                started_at = time.time()
                if not self._repo.claim_pending_task(task.id, started_at):
                    self._apply_claim_loss(task, self._repo.read_task(task.id))
                    continue
                task.status = TaskStatus.RUNNING
                task.started_at = started_at
                self._save_state()
                return task
        return None

    def _async_claim_lock(self) -> asyncio.Lock:
        """Per-loop claim lock (an asyncio.Lock is bound to the loop that awaits it)."""
        loop = asyncio.get_running_loop()
        if self._aclaim_lock is None or self._aclaim_lock_loop is not loop:
            self._aclaim_lock = asyncio.Lock()
            self._aclaim_lock_loop = loop
        return self._aclaim_lock

    async def aget_next_task(self) -> Task | None:
        """Async twin of :meth:`get_next_task`, with the same store-level claim."""
        async with self._async_claim_lock():
            for task in self._pending_by_priority():
                started_at = time.time()
                if not await self._repo.aclaim_pending_task(task.id, started_at):
                    self._apply_claim_loss(task, await self._repo.aread_task(task.id))
                    continue
                task.status = TaskStatus.RUNNING
                task.started_at = started_at
                await self._asave_state()
                return task
        return None

    @staticmethod
    def _publish_task_event(task: Task, status: str) -> None:
        """Publish a TaskCompleted event on the global event bus (best-effort)."""
        try:
            from core.events import TaskCompleted, get_event_bus
            get_event_bus().publish_background(TaskCompleted(
                task_id=task.id,
                product_id=task.product_id,
                agent_type=task.agent_type,
                status=status,
                state=task.state,
                output_data=task.output_data if status == "completed" else None,
                error=task.error if status == "failed" else None,
            ))
        except Exception as exc:
            logger.warning("Event publish failed for task %s: %s", task.id, exc)

    def _apply_task_completion(
        self, task_id: str, output: dict
    ) -> tuple[bool, Product | None, str | None]:
        """
        Mark task completed in memory, record metrics, advance product state / queue next task.

        Returns (ok, product, product_id) for logging; persistence is caller responsibility.
        """
        task = self._find_task(task_id)
        if not task:
            return False, None, None

        task.status = TaskStatus.COMPLETED
        task.completed_at = time.time()
        task.output_data = output

        if task.started_at:
            duration = task.completed_at - task.started_at
            PrometheusMetrics.observe_task_duration(task.agent_type, duration)
        PrometheusMetrics.inc_task("completed")

        self._publish_task_event(task, "completed")

        product = self.products.get(task.product_id)
        if product:
            next_states = STATE_TRANSITIONS.get(product.state, [])
            if task.state in next_states:
                product.state = task.state
                product.updated_at = time.time()
                if product.state != PipelineState.COMPLETED:
                    self._create_next_task(product)

        return True, product, task.product_id

    def complete_task(self, task_id: str, output: dict) -> bool:
        """Mark a task as completed and advance the pipeline."""
        ok, product, product_id = self._apply_task_completion(task_id, output)
        if not ok:
            logger.error(f"Task {task_id} not found")
            return False

        self._save_state()
        logger.info(
            f"Task {task_id} completed, product {product_id} -> {product.state.value if product else 'unknown'}"
        )
        return True

    async def acomplete_task(self, task_id: str, output: dict) -> bool:
        ok, product, product_id = self._apply_task_completion(task_id, output)
        if not ok:
            return False

        await self._asave_state()
        logger.info(
            f"Task {task_id} completed, product {product_id} -> {product.state.value if product else 'unknown'}"
        )
        return True

    def _apply_task_failure(self, task_id: str, error: str) -> bool:
        """Update task retry state in memory; returns False if task missing."""
        task = self._find_task(task_id)
        if not task:
            return False

        task.retry_count += 1
        task.error = error

        # Allow retry_count == max_retries as the final PENDING attempt
        # (so max_retries=3 yields retries labeled 1/3, 2/3, 3/3 before FAILED).
        if task.retry_count <= task.max_retries:
            task.status = TaskStatus.PENDING
            logger.warning(f"Task {task_id} failed (retry {task.retry_count}/{task.max_retries}): {error}")
        else:
            task.status = TaskStatus.FAILED
            PrometheusMetrics.inc_task("failed")
            self._publish_task_event(task, "failed")
            product = self.products.get(task.product_id)
            if product:
                product.state = PipelineState.FAILED
                product.updated_at = time.time()
            logger.error(f"Task {task_id} failed permanently: {error}")

        return True

    def fail_task(self, task_id: str, error: str) -> bool:
        """Mark a task as failed, with retry logic."""
        if not self._apply_task_failure(task_id, error):
            return False
        self._save_state()
        return True

    async def afail_task(self, task_id: str, error: str) -> bool:
        if not self._apply_task_failure(task_id, error):
            return False
        await self._asave_state()
        return True

    def timeout_task(self, task_id: str) -> bool:
        """Handle a task timeout."""
        task = self._find_task(task_id)
        if task:
            PrometheusMetrics.inc_task("timedout")
        return self.fail_task(task_id, "Task timed out")

    def add_task_to_queue(self, task: Task):
        """Add a task to the queue."""
        self.task_queue.append(task)
        self._save_state()

    def get_product(self, product_id: str) -> Product | None:
        return self.products.get(product_id)

    def get_all_products(self) -> list[Product]:
        return list(self.products.values())

    def get_active_products(self) -> list[Product]:
        return [
            p for p in self.products.values()
            if p.state not in (PipelineState.COMPLETED, PipelineState.FAILED, PipelineState.CANCELLED)
        ]

    def get_pipeline_metrics(self) -> dict:
        """Get pipeline metrics for Director AI."""
        products = self.get_all_products()
        completed = [p for p in products if p.state == PipelineState.COMPLETED]
        failed = [p for p in products if p.state == PipelineState.FAILED]
        active = self.get_active_products()

        total_time = 0
        for p in completed:
            if p.created_at and p.updated_at:
                total_time += p.updated_at - p.created_at

        return {
            "total_products": len(products),
            "active_products": len(active),
            "completed_products": len(completed),
            "failed_products": len(failed),
            "avg_completion_time_hours": (total_time / max(len(completed), 1)) / 3600 if completed else 0,
            "pending_tasks": len([t for t in self.task_queue if t.status == TaskStatus.PENDING]),
            "running_tasks": len([t for t in self.task_queue if t.status == TaskStatus.RUNNING]),
            "failed_tasks": len([t for t in self.task_queue if t.status == TaskStatus.FAILED]),
            "timeout_tasks": len([t for t in self.task_queue if t.status == TaskStatus.TIMEOUT]),
        }

    def get_metrics(self) -> dict:
        """
        Return current Prometheus gauge values (state distribution, active count, etc.).
        
        Returns:
            dict with keys: state_counts, active_products, total_products
        """
        products = self.get_all_products()
        from collections import Counter as CollectionsCounter
        state_counts: dict[str, int] = CollectionsCounter()
        for p in products:
            state_counts[p.state.value] += 1

        return {
            "state_counts": dict(state_counts),
            "active_products": len(self.get_active_products()),
            "total_products": len(products),
        }

    def _create_next_task(self, product: Product):
        """Create the next task based on current product state."""
        # Handle terminal transition: EVOLUTION_ANALYZING -> COMPLETED
        if product.state == PipelineState.EVOLUTION_ANALYZING:
            product.state = PipelineState.COMPLETED
            product.updated_at = time.time()
            logger.info(f"Product {product.id} pipeline completed!")
            self._save_state()
            return

        next_info_raw = PIPELINE_AGENT_FLOW.get(product.state.name)
        if not next_info_raw:
            return
        agent_type_raw, next_state_raw = next_info_raw
        # Legacy/compact flow mode used in tests and lightweight runs:
        # skip design_critic and hardening hops unless explicitly enabled.
        extended_flow = os.environ.get("AIFACTORY_EXTENDED_PIPELINE", "0").strip().lower() in ("1", "true", "yes")
        if not extended_flow:
            if agent_type_raw == "design_critic":
                agent_type_raw, next_state_raw = "developer", "CODE_COMMITTED"
            elif agent_type_raw == "__runtime_test__" or agent_type_raw == "hardening":
                agent_type_raw, next_state_raw = "qa", "QA_TESTING"
        agent_type, next_state = agent_type_raw, PipelineState[next_state_raw]

        dp = normalize_delivery_profile((product.metadata or {}).get("delivery_profile"))
        if dp == MARKETING_LANDING and product.state == PipelineState.TELEMETRY_COLLECTING:
            agent_type, next_state = "__complete__", PipelineState.COMPLETED

        if product.state == PipelineState.SECURITY_SCANNED and agent_type == "devops":
            gate_prod = {
                "delivery_profile": (product.metadata or {}).get("delivery_profile"),
                "admin_instructions": (product.metadata or {}).get("admin_instructions"),
                "idea": product.idea,
            }
            if post_devops_human_gate_required(gate_prod):
                from core.autonomy_mode import is_full_autonomy
                from core.paths import data_root
                from orchestrator.autonomy_bridge import resolve_human_gate_sync

                if is_full_autonomy():
                    prod_dict = {
                        "id": product.id,
                        "idea": product.idea,
                        "metadata": product.metadata or {},
                        "delivery_profile": (product.metadata or {}).get("delivery_profile"),
                    }
                    resolved = resolve_human_gate_sync(
                        prod_dict,
                        point="post_devops_gate",
                        data_root=data_root(),
                    )
                    next_state = (
                        PipelineState.SALES_ACTIVE
                        if resolved == "SALES_ACTIVE"
                        else PipelineState.FAILED if resolved == "FAILED" else PipelineState.HUMAN_REVIEW_PENDING
                    )
                else:
                    next_state = PipelineState.HUMAN_REVIEW_PENDING
            else:
                next_state = PipelineState.SALES_ACTIVE
        import uuid
        task = Task(
            id=f"task-{uuid.uuid4().hex[:12]}",
            product_id=product.id,
            agent_type=agent_type,
            state=next_state,
            input_data={"product_id": product.id, "idea": product.idea},
            created_at=time.time(),
            priority=self._get_agent_priority(agent_type),
        )
        self.add_task_to_queue(task)

    def _get_agent_priority(self, agent_type: str) -> int:
        priorities = {
            "analyst": 1,
            "pm": 2,
            "marketing": 3,
            "methodologist": 4,
            "architect": 5,
            "design_critic": 6,
            "developer": 6,
            "hardening": 6,
            "qa": 7,
            "security": 7,
            "devops": 8,
            "sales": 9,
        }
        return priorities.get(agent_type, 5)

    def _find_task(self, task_id: str) -> Task | None:
        for task in self.task_queue:
            if task.id == task_id:
                return task
        return None

    # ------------------------------------------------------------------
    # Persistence (delegated to PipelineRepository)
    # ------------------------------------------------------------------

    def _product_dicts(self) -> dict[str, dict]:
        return {pid: p.to_dict() for pid, p in self.products.items()}

    def _task_dicts(self) -> list[dict]:
        return [t.to_dict() for t in self.task_queue]

    @staticmethod
    def _on_product_saved(product: dict) -> None:
        """Deploy-time showcase hook, fired per product that actually changed."""
        try:
            from web.backend.services.product_showcase import maybe_enqueue_on_deploy

            maybe_enqueue_on_deploy(str(product.get("id") or ""), str(product.get("state") or ""))
        except Exception as exc:
            logger.warning("maybe_enqueue_on_deploy skipped for %s: %s", product.get("id"), exc)

    def _load_state(self):
        """Load pipeline state from file or SQLite based on self.use_sqlite."""
        if self.use_sqlite:
            self._load_state_from_sqlite()
        else:
            self._load_state_from_json()
        # Adopt what we just read as the persisted baseline, so the first save after a
        # load writes only what the machine has since changed.
        self._repo.record_persisted(list(self._product_dicts().values()), self._task_dicts())

    def _load_state_from_json(self):
        """Load pipeline state from the JSON file."""
        data = self._repo.load_json()
        try:
            self.products = {
                pid: Product.from_dict(pdata) for pid, pdata in data["products"].items()
            }
            self.task_queue = [Task.from_dict(t) for t in data["task_queue"]]
        except Exception as exc:
            logger.error(f"Failed to load pipeline state: {exc}")
            self.products = {}
            self.task_queue = []
            return
        if self.products or self.task_queue:
            logger.info(
                f"Loaded pipeline state: {len(self.products)} products, {len(self.task_queue)} tasks"
            )

    def _load_state_from_sqlite(self):
        """Load pipeline state from SQLite."""
        data = self._repo.load_sqlite()
        try:
            task_dicts = data["task_queue"]
            self.products = {}
            for pd in data["products"]:
                product = Product.from_dict(pd)
                # Restore tasks that belong to this product
                product_tasks = [t for t in task_dicts if t.get("product_id") == product.id]
                product.tasks = [Task.from_dict(t) for t in product_tasks]
                self.products[product.id] = product

            self.task_queue = [Task.from_dict(t) for t in task_dicts]
        except Exception as exc:
            logger.error(f"Failed to load pipeline state from SQLite: {exc}")
            self.products = {}
            self.task_queue = []
            return

        logger.info(
            f"Loaded pipeline state from SQLite: {len(self.products)} products, {len(self.task_queue)} tasks"
        )

    def _save_state(self):
        """Save pipeline state to file or SQLite based on self.use_sqlite."""
        if self.use_sqlite:
            self._save_state_to_sqlite()
        else:
            self._save_state_to_json()

    async def _asave_state(self):
        """Async twin of :meth:`_save_state`."""
        if self.use_sqlite:
            await self._asave_state_to_sqlite()
        else:
            await self._repo.asave_json(self._product_dicts(), self._task_dicts())

    def _save_state_to_json(self):
        """Save pipeline state to the JSON file."""
        self._repo.save_json(self._product_dicts(), self._task_dicts())

    def _save_state_to_sqlite(self):
        """Save the products and tasks that changed since the last save."""
        self._repo.save_sqlite(
            self._product_dicts(), self._task_dicts(), on_product_saved=self._on_product_saved
        )

    async def _asave_state_to_sqlite(self):
        """Async twin of :meth:`_save_state_to_sqlite`, over one long-lived connection."""
        await self._repo.asave_sqlite(
            self._product_dicts(), self._task_dicts(), on_product_saved=self._on_product_saved
        )

    def resave_all(self):
        """Force the next save to rewrite every row, ignoring the change baseline."""
        self._repo.mark_all_dirty()
        self._save_state()

    def migrate_json_to_sqlite(self, db_path: str | None = None) -> dict:
        """Migrate data from the JSON state file to SQLite.

        Reads the existing JSON state file and bulk-inserts all products
        and tasks into the SQLite database. Does NOT modify the JSON file.

        Args:
            db_path: Optional path to the SQLite database. Uses self.db_path if not provided.

        Returns:
            dict with keys: products_migrated, tasks_migrated
        """
        return self._repo.migrate_json_to_sqlite(db_path)
