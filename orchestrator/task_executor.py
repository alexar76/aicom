"""
Execute a single running pipeline task (agent dispatch, gates, remediation).

Orchestrates submodules: builtins, real agents, and fallbacks.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from orchestrator.task_executor_agent import run_agent_task
from orchestrator.task_executor_builtin import run_builtin_task
from orchestrator.task_executor_fallback import run_fallback_task

# Re-export helpers used by tests and pipeline_worker
from orchestrator.task_executor_helpers import (  # noqa: F401
    build_task_context,
    fallback_agent_output,
    record_task_lesson,
    save_task_artifact,
)

if TYPE_CHECKING:
    from orchestrator.task_executor_helpers import (
        PipelineTaskExecutorHost,
    )


class PipelineTaskExecutor:
    """Runs one pipeline task against shared in-memory state (mutates task_queue/products)."""

    async def process_task(
        self,
        host: PipelineTaskExecutorHost,
        task: dict,
        products: dict,
        task_queue: list,
        *,
        dirty_products: set[str] | None = None,
        dirty_tasks: set[str] | None = None,
    ):
        """Process a running task using the appropriate agent."""
        agent_type = task.get("agent_type", "")
        pid = task.get("product_id", "")
        task_id = task.get("id", "")

        if pid and dirty_products is not None:
            dirty_products.add(pid)
        if task_id and dirty_tasks is not None:
            dirty_tasks.add(str(task_id))

        if pid not in products:
            task["status"] = "failed"
            task["error"] = f"Product {pid} not found"
            return

        product = products[pid]

        if await run_builtin_task(
            host,
            agent_type=agent_type,
            task=task,
            products=products,
            task_queue=task_queue,
            product=product,
            pid=pid,
            task_id=task_id,
        ):
            return

        agent = host._agents.get(agent_type)
        if agent:
            await run_agent_task(
                host,
                agent_type=agent_type,
                agent=agent,
                task=task,
                products=products,
                task_queue=task_queue,
                product=product,
                pid=pid,
                task_id=task_id,
            )
            return

        await run_fallback_task(
            host,
            agent_type=agent_type,
            task=task,
            products=products,
            task_queue=task_queue,
            product=product,
            pid=pid,
            task_id=task_id,
        )
