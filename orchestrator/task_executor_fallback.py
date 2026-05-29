"""
Fallback pipeline execution when no agent implementation is registered.
"""

from __future__ import annotations

import asyncio
import logging
import time

from orchestrator.task_executor_helpers import (
    PipelineTaskExecutorHost,
    fallback_agent_output,
    save_task_artifact,
)
from orchestrator.worker_utils import delivery_profile_from_product_dict
from web.backend.services.marketplace_quality import evaluate_marketplace_quality
from web.backend.services.requirements_clarifier import build_clarification_pack_llm

logger = logging.getLogger("pipeline-worker")


async def run_fallback_task(
    host: PipelineTaskExecutorHost,
    *,
    agent_type: str,
    task: dict,
    products: dict,
    task_queue: list,
    product: dict,
    pid: str,
    task_id: str,
) -> None:
    # Agent not initialized - use structured fallback
    logger.warning(f"Agent '{agent_type}' not initialized for task {task_id}, using fallback")
    await asyncio.sleep(2)  # Brief processing delay for realism

    task["status"] = "completed"
    task["completed_at"] = time.time()
    task["output_data"] = fallback_agent_output(agent_type, pid, product)
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
    save_task_artifact(pid, agent_type, task["output_data"])

    # Check if product reached COMPLETED
    if target_state == "COMPLETED":
        logger.info(f"Product {pid} pipeline completed! (fallback)")
        try:
            spec_done = host._load_spec(pid)
            dp_done = delivery_profile_from_product_dict(products[pid]) if pid in products else None
            mq_done = evaluate_marketplace_quality(
                pid, specification=spec_done, delivery_profile=dp_done
            )
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
        next_task = host._create_next_task(product)
        if next_task:
            if next_task.get("agent_type") == "pm":
                next_task.setdefault("input_data", {})["clarification_pack"] = await build_clarification_pack_llm(
                    product.get("idea", ""),
                    host._llm_router,
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
                host._audit_agent_handoff(
                    product_id=pid,
                    from_agent=agent_type,
                    from_state=prev_state,
                    next_task=next_task,
                    task_id=task_id,
                    reason="sequential_fallback",
                    output_data=task.get("output_data") if isinstance(task.get("output_data"), dict) else None,
                )
                logger.info(f"Next task created for {pid}: {next_task['agent_type']} -> {next_task['state']}")