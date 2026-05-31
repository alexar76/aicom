"""
Built-in pipeline tasks (__complete__, __runtime_test__).
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from orchestrator.task_executor_helpers import PipelineTaskExecutorHost

logger = logging.getLogger("pipeline-worker")


async def run_builtin_task(
    host: PipelineTaskExecutorHost,
    *,
    agent_type: str,
    task: dict,
    products: dict,
    task_queue: list,
    product: dict,
    pid: str,
    task_id: str,
) -> bool:
    """Run built-in task types. Returns True when ``agent_type`` was handled."""
    if agent_type == "__complete__":
        task["status"] = "completed"
        task["completed_at"] = time.time()
        task["output_data"] = {"completed": True, "product_id": pid}
        task["output_summary"] = f"Product {pid} pipeline completed"
        products[pid]["state"] = "COMPLETED"
        products[pid]["updated_at"] = time.time()
        logger.info(f"Product {pid} pipeline completed!")
        return True

    if agent_type == "__landing_spec__":
        from core.paths import resolve_data_root
        from orchestrator.landing_fast_flow import resolve_style_preset, write_landing_mini_spec

        preset_id = str(product.get("style_preset_id") or "").strip() or None
        preset = resolve_style_preset(
            preset_id,
            product_id=pid,
            idea=str(product.get("idea") or ""),
        )
        spec_inner = write_landing_mini_spec(
            pid,
            idea=str(product.get("idea") or ""),
            preset=preset,
            data_root=resolve_data_root(host.data_root),
            admin_instructions=str(product.get("admin_instructions") or ""),
            agent_to_website=bool(product.get("agent_to_website")),
        )
        product["spec"] = spec_inner
        product["style_preset_id"] = preset.get("id", "")
        product["state"] = "SPEC_WRITTEN"
        product["updated_at"] = time.time()
        task["status"] = "completed"
        task["completed_at"] = time.time()
        task["output_data"] = {"specification": spec_inner, "style_preset": preset}
        task["output_summary"] = f"Landing mini-spec written ({preset.get('id', 'preset')})"
        next_task = host._create_next_task(product)
        if next_task and not any(
            t.get("product_id") == pid
            and t.get("agent_type") == next_task["agent_type"]
            and t.get("state") == next_task["state"]
            and t.get("status") in ("pending", "running")
            for t in task_queue
        ):
            task_queue.append(next_task)
            host._audit_agent_handoff(
                product_id=pid,
                from_agent="__landing_spec__",
                from_state="IDEA_RECEIVED",
                next_task=next_task,
                task_id=task_id,
                reason="landing_mini_spec_ready",
            )
        logger.info("Landing mini-spec ready for %s (preset=%s)", pid, preset.get("id"))
        return True

    # Runtime test stage between developer and hardening.
    if agent_type == "__runtime_test__":
        runtime_result = host._run_runtime_tests(pid, task_queue)
        task["status"] = "completed" if runtime_result.get("passed") else "failed"
        task["completed_at"] = time.time()
        task["output_data"] = runtime_result
        task["output_summary"] = "runtime tests passed" if runtime_result.get("passed") else "runtime tests failed"
        if runtime_result.get("passed"):
            products[pid]["state"] = "CODE_TESTING"
            products[pid]["updated_at"] = time.time()
            next_task = host._create_next_task(products[pid])
            if next_task and not any(
                t.get("product_id") == pid
                and t.get("agent_type") == next_task["agent_type"]
                and t.get("state") == next_task["state"]
                and t.get("status") in ("pending", "running")
                for t in task_queue
            ):
                task_queue.append(next_task)
                host._audit_agent_handoff(
                    product_id=pid,
                    from_agent="__runtime_test__",
                    from_state="CODE_COMMITTED",
                    next_task=next_task,
                    task_id=task_id,
                    reason="runtime_test_passed",
                )
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
                runtime_dev_task = {
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
                    "priority": host._get_priority("developer"),
                }
                task_queue.append(runtime_dev_task)
                host._audit_agent_handoff(
                    product_id=pid,
                    from_agent="__runtime_test__",
                    from_state="CODE_COMMITTED",
                    next_task=runtime_dev_task,
                    task_id=task_id,
                    reason="runtime_test_failed",
                    success=False,
                )
            logger.warning("Runtime tests failed for %s; queued developer fix", pid)
        return True

    return False
