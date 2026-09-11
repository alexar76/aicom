"""
Fallback pipeline execution when no agent implementation is registered.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time

from orchestrator.task_executor_helpers import (
    PipelineTaskExecutorHost,
    fallback_agent_output,
    save_task_artifact,
)
from web.backend.services.requirements_clarifier import build_clarification_pack_llm

logger = logging.getLogger("pipeline-worker")


def _is_production() -> bool:
    """Production when AIFACTORY_PROD=1 (matches security/prod_startup_guard.py)."""
    try:
        from security.prod_startup_guard import is_production_mode

        return is_production_mode()
    except Exception:
        return (os.environ.get("AIFACTORY_PROD") or "").strip() == "1"


def _fallback_allowed() -> bool:
    """Explicit opt-in to keep the synthetic fallback path enabled in production."""
    return (os.environ.get("AIFACTORY_ALLOW_FALLBACK_AGENTS") or "").strip().lower() in (
        "1",
        "true",
        "yes",
    )


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

    # Fail CLOSED in production: synthetic fallback output is fabricated and must never
    # silently advance a product to COMPLETED / the marketplace. Only an explicit opt-in
    # (AIFACTORY_ALLOW_FALLBACK_AGENTS) keeps the synthetic path enabled in production;
    # dev/test still use it so the pipeline can run without live LLM agents.
    if _is_production() and not _fallback_allowed():
        task["status"] = "failed"
        task["completed_at"] = time.time()
        task["error"] = (
            f"Agent '{agent_type}' is not initialized and synthetic fallback is disabled "
            "in production. Refusing to fabricate agent output (set "
            "AIFACTORY_ALLOW_FALLBACK_AGENTS=1 to override). Fix agent/LLM initialization."
        )
        if pid in products:
            products[pid]["last_error"] = task["error"]
            products[pid]["updated_at"] = time.time()
        logger.error(
            "Fallback REFUSED for product %s task %s: agents unavailable in production",
            pid,
            task_id,
        )
        return

    await asyncio.sleep(2)  # Brief processing delay for realism

    # Mark the output as synthetic so downstream gates/reporting never treat it as real.
    output_data = fallback_agent_output(agent_type, pid, product)
    if isinstance(output_data, dict):
        output_data["is_fallback"] = True
    task["status"] = "completed"
    task["completed_at"] = time.time()
    task["output_data"] = output_data
    task["is_fallback"] = True
    task["output_summary"] = f"{agent_type} completed for {pid} (synthetic fallback)"
    if pid in products:
        products[pid]["fallback_used"] = True

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
        # A product built from SYNTHETIC fallback output must never be auto-listed on the
        # marketplace — its spec/code/QA are fabricated. Allow it to reach the COMPLETED
        # state (so the pipeline does not deadlock) but WITHHOLD storefront eligibility;
        # real-agent completions (run_agent_task) keep their normal listing path.
        logger.warning(
            "Product %s reached COMPLETED via synthetic fallback — withholding marketplace "
            "listing (output is not from a real agent)",
            pid,
        )
        if pid in products:
            products[pid]["publish_blocked_reason"] = "synthetic_fallback_output"
            products[pid]["updated_at"] = time.time()
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