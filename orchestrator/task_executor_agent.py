"""
Real-agent pipeline task execution (success, failure, retries).
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid

from core.agent_roles import is_architect_agent, is_developer_agent
from core.quality_settings import (
    gate_failing_model,
    max_pipeline_repair_rounds_for_delivery_profile,
    max_pipeline_repair_rounds_for_product,
    monitoring_dev_refresh_enabled,
)
from orchestrator.task_executor_helpers import (
    PipelineTaskExecutorHost,
    build_task_context,
    record_task_lesson,
)
from orchestrator.worker_utils import delivery_profile_from_product_dict, monitoring_refresh_decision
from web.backend.services.marketplace_quality import evaluate_marketplace_quality
from web.backend.services.requirements_clarifier import build_clarification_pack_llm
from web.backend.services.security_pipeline_gate import (
    build_security_gate_feedback,
    security_scan_passes_pipeline_gate,
)

logger = logging.getLogger("pipeline-worker")


async def run_agent_task(
    host: PipelineTaskExecutorHost,
    *,
    agent_type: str,
    agent,
    task: dict,
    products: dict,
    task_queue: list,
    product: dict,
    pid: str,
    task_id: str,
) -> None:

    # Idempotency guard: only a task that is still actively running may be executed and
    # advance the product. If a concurrent runner / requeue already drove this task to a
    # terminal status, re-running it would double-process the agent and (worse) enqueue
    # the next sequential task twice. Bail out cleanly instead.
    current_status = str(task.get("status") or "").lower()
    if current_status not in ("running", "pending"):
        logger.info(
            "Skipping agent task %s for %s: already in terminal status '%s' (idempotency guard)",
            task_id,
            pid,
            current_status,
        )
        return

    try:
        from agents.base_agent import AgentInput
        from agents.product_profile import infer_delivery_profile, normalize_delivery_profile

        # Collect context from previous tasks
        context = build_task_context(task_queue, pid)

        dp_raw = product.get("delivery_profile")
        if dp_raw:
            delivery_profile = normalize_delivery_profile(str(dp_raw))
        else:
            delivery_profile = infer_delivery_profile(
                product.get("admin_instructions"),
                product.get("idea"),
            )

        agent_input_data = {
            "idea": product.get("idea", ""),
            "category": product.get("category", ""),
            "tags": product.get("tags", []),
            "specification": host._load_spec(pid),
            "architecture": host._load_arch(pid),
            "admin_instructions": product.get("admin_instructions", ""),
            "delivery_profile": delivery_profile,
            "production_mode": bool(product.get("production_mode")),
            "interface_locale": product.get("interface_locale") or "en",
            "content_locale": product.get("content_locale") or "auto",
            "surrogate_repair_hint": product.get("surrogate_repair_hint"),
            **task.get("input_data", {}),
        }
        # Gate-failing repair rounds get a stronger model when configured
        gfm = gate_failing_model()
        if gfm and isinstance(agent_input_data.get("quality_repair_round"), (int, float)) and int(agent_input_data["quality_repair_round"]) >= 1:
            agent_input_data["gate_failing_model"] = gfm

        agent_input = AgentInput(
            task_id=task_id,
            product_id=pid,
            agent_type=agent_type,
            data=agent_input_data,
            context=context,
            timestamp=time.time(),
        )

        from core.pipeline_cost_guard import PipelineCostBudgetExceeded, assert_product_within_budget
        from core.tracing import span

        try:
            assert_product_within_budget(pid)
        except PipelineCostBudgetExceeded as budget_exc:
            err = str(budget_exc)
            logger.error("Product %s pipeline LLM budget exceeded: %s", pid, err)
            task["status"] = "failed"
            task["error"] = err
            task["completed_at"] = time.time()
            task["failure_category"] = "budget_exceeded"
            if pid in products:
                products[pid]["state"] = "FAILED"
                products[pid]["failure_reason"] = err
                products[pid]["updated_at"] = time.time()
            return

        logger.info(f"Calling real agent '{agent_type}' for task {task_id}")
        with span(
            "pipeline.agent_task",
            attributes={"agent.type": agent_type, "product.id": pid, "task.id": task_id},
        ):
            output = await agent.execute(agent_input)

        if output.success:
            task["status"] = "completed"
            task["completed_at"] = time.time()
            task["output_data"] = output.data
            task["metrics"] = output.metrics
            task["output_summary"] = str(output.data)[:200]
            if pid in products:
                host.peer_review_engine.register(
                    products[pid], agent_type, output.data if isinstance(output.data, dict) else {}
                )

            peer_blocked = False
            # QA failures use structured qa_gate_failed handling (repair budget + rich feedback).
            if pid in products and agent_type != "qa":
                peer_blocked = host.peer_review_engine.apply_block(
                    task, products[pid], task_queue, product
                )
            if peer_blocked:
                logger.warning("Peer review blocked progression for %s at %s", pid, agent_type)
                return

            if agent_type == "pm" and pid in products and isinstance(output.data, dict):
                dp = output.data.get("delivery_profile")
                if dp:
                    products[pid]["delivery_profile"] = dp
                    products[pid]["updated_at"] = time.time()

            if agent_type in ("architect", "landing_architect") and pid in products:
                arch_ok, arch_issues = host._architecture_gate(
                    pid, delivery_profile=delivery_profile_from_product_dict(products[pid])
                )
                if not arch_ok:
                    task["status"] = "failed"
                    task["error"] = "architecture gate failed: " + "; ".join(arch_issues)
                    task["completed_at"] = time.time()
                    products[pid]["state"] = "METHODOLOGY_REVIEWED"
                    products[pid]["updated_at"] = time.time()
                    existing = any(
                        t.get("product_id") == pid
                        and is_architect_agent(t.get("agent_type"))
                        and t.get("status") in ("pending", "running")
                        for t in task_queue
                    )
                    if not existing:
                        arch_retry_task = {
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
                            "priority": host._get_priority("architect"),
                        }
                        task_queue.append(arch_retry_task)
                        host._audit_agent_handoff(
                            product_id=pid,
                            from_agent=agent_type,
                            from_state=str(task.get("state") or ""),
                            next_task=arch_retry_task,
                            task_id=task_id,
                            reason="architecture_gate",
                            success=False,
                            output_data=output.data if isinstance(output.data, dict) else None,
                            extra={"issues": arch_issues[:8]},
                        )
                    logger.warning("Architecture gate blocked developer stage for %s: %s", pid, arch_issues)
                    return

            if agent_type in ("developer", "landing_developer") and pid in products:
                try:
                    host._apply_watermark_policy(pid, products[pid])
                except Exception as wm_exc:
                    logger.warning("Watermark policy apply failed for %s: %s", pid, wm_exc)
                try:
                    from web.backend.services.site_head_snippet import (
                        inject_published_site_head_if_configured,
                    )

                    inject_published_site_head_if_configured(host.data_root, pid)
                except Exception as head_exc:
                    logger.warning("Published site <head> inject failed for %s: %s", pid, head_exc)
                try:
                    from web.backend.services.site_badge import inject_site_badge_if_enabled

                    inject_site_badge_if_enabled(host.data_root, pid)
                except Exception as badge_exc:
                    logger.warning("Site badge inject failed for %s: %s", pid, badge_exc)
                try:
                    from web.backend.services.landing_embeds import inject_landing_embeds_for_product

                    inject_landing_embeds_for_product(host.data_root, pid, products[pid])
                except Exception as embed_exc:
                    logger.warning("Landing embed inject failed for %s: %s", pid, embed_exc)

            if agent_type == "marketing" and pid in products:
                try:
                    from web.backend.services.landing_embeds import inject_landing_embeds_for_product

                    inject_landing_embeds_for_product(host.data_root, pid, products[pid])
                except Exception as embed_exc:
                    logger.warning("Landing embed inject after marketing failed for %s: %s", pid, embed_exc)

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
            auto_recovered = False
            max_quality_loops = (
                max_pipeline_repair_rounds_for_product(products[pid])
                if pid in products
                else max_pipeline_repair_rounds_for_delivery_profile(None)
            )
            sec_raw = os.environ.get("AIFACTORY_MAX_SECURITY_LOOPS")
            if sec_raw is not None and str(sec_raw).strip() != "":
                try:
                    max_security_loops = max(1, int(sec_raw))
                except ValueError:
                    max_security_loops = max_quality_loops
            else:
                max_security_loops = max_quality_loops

            # Successful QA (all gates pass): reset repair counter
            if (
                agent_type == "qa"
                and isinstance(qg, dict)
                and qg.get("passed") is True
                and pid in products
            ):
                products[pid]["quality_repair_round"] = 0
                # Gates passed — the surrogate's repair guidance is now stale; drop it.
                products[pid].pop("surrogate_repair_hint", None)

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
                        "quality_gates_feedback": dict(qg or {}),
                    }
                products[pid]["updated_at"] = time.time()
                from orchestrator.qa_repair_policy import (
                    notify_qa_human_review_pending,
                    resolve_qa_repair_after_failure,
                )

                quality_gates_exhausted, effective_round, product_state = resolve_qa_repair_after_failure(
                    products[pid],
                    new_repair_round=new_repair_round,
                    max_quality_loops=max_quality_loops,
                )
                new_repair_round = effective_round
                products[pid]["quality_repair_round"] = effective_round
                products[pid]["state"] = product_state
                from orchestrator.auto_recovery import try_auto_recovery_after_qa_failure

                if try_auto_recovery_after_qa_failure(
                    products[pid],
                    task_queue,
                    repair_round=new_repair_round,
                    data_root=host.data_root,
                ):
                    auto_recovered = True
                    quality_gates_exhausted = False
                    qa_gate_failed = False
                    products[pid]["state"] = "COMPLETED"
                    target_state = "COMPLETED"
                elif quality_gates_exhausted:
                    from core.autonomy_mode import is_full_autonomy
                    from orchestrator.autonomy_bridge import resolve_human_gate_async

                    if is_full_autonomy():
                        resolved = await resolve_human_gate_async(
                            products[pid],
                            point="qa_repair_exhausted",
                            data_root=host.data_root,
                            context={"quality_gates": qg},
                            llm_router=getattr(host, "_llm_router", None),
                        )
                        if resolved:
                            products[pid]["state"] = resolved
                            logger.warning(
                                "Product %s: QA exhaust resolved by surrogate → %s",
                                pid,
                                resolved,
                            )
                            quality_gates_exhausted = False
                    if quality_gates_exhausted:
                        notify_qa_human_review_pending(pid, products[pid])
                    logger.warning(
                        "Product %s: QA repair budgets exhausted → HUMAN_REVIEW_PENDING (round %s/%s)",
                        pid,
                        effective_round,
                        max_quality_loops,
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
                from orchestrator.qa_repair_policy import (
                    notify_qa_human_review_pending,
                    resolve_security_repair_after_failure,
                )

                security_budget_exhausted, product_state = resolve_security_repair_after_failure(
                    products[pid],
                    new_sec_round=new_sec_round,
                    max_security_loops=max_security_loops,
                )
                products[pid]["state"] = product_state
                if security_budget_exhausted:
                    from core.autonomy_mode import is_full_autonomy
                    from orchestrator.autonomy_bridge import resolve_human_gate_async

                    if is_full_autonomy():
                        resolved = await resolve_human_gate_async(
                            products[pid],
                            point="security_repair_exhausted",
                            data_root=host.data_root,
                            context={"security_reasons": sec_reasons},
                            llm_router=getattr(host, "_llm_router", None),
                        )
                        if resolved:
                            products[pid]["state"] = resolved
                            logger.warning(
                                "Product %s: security exhaust resolved by surrogate → %s",
                                pid,
                                resolved,
                            )
                            security_budget_exhausted = False
                    if security_budget_exhausted:
                        notify_qa_human_review_pending(pid, products[pid])
                    logger.warning(
                        "Product %s: security repair budgets exhausted → HUMAN_REVIEW_PENDING",
                        pid,
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
                    effective_state = target_state
                    if (
                        agent_type == "devops"
                        and str(target_state or "").upper() == "HUMAN_REVIEW_PENDING"
                    ):
                        from core.autonomy_mode import is_full_autonomy
                        from orchestrator.autonomy_bridge import resolve_human_gate_async
                        from web.backend.services.product_followup import (
                            post_devops_human_review_approved,
                        )

                        if is_full_autonomy():
                            resolved = await resolve_human_gate_async(
                                products[pid],
                                point="post_devops_gate",
                                data_root=host.data_root,
                                llm_router=getattr(host, "_llm_router", None),
                            )
                            if resolved:
                                effective_state = resolved
                        elif post_devops_human_review_approved(pid):
                            effective_state = "SALES_ACTIVE"
                    products[pid]["state"] = effective_state
                products[pid]["updated_at"] = time.time()
                try:
                    from core.outcome_memory import record_terminal_outcome

                    st_terminal = str(products[pid].get("state") or "").upper()
                    if st_terminal in ("COMPLETED", "FAILED"):
                        record_terminal_outcome(host.data_root, products[pid])
                except Exception as exc:
                    logger.warning("record_terminal_outcome failed for %s: %s", pid, exc)

            # Analyst periodic monitoring may request a shipped-slice refresh (shares QA repair budget)
            if (
                agent_type == "analyst"
                and isinstance(output.data, dict)
                and (task.get("input_data") or {}).get("mode") == "monitoring"
                and prev_state == "COMPLETED"
                and target_state == "EVOLUTION_ANALYZING"
                and pid in products
                and products[pid].get("state") == "COMPLETED"
                and monitoring_dev_refresh_enabled()
            ):
                from web.backend.services.policy_audit import _dev_fixing_pending

                want_r, qg_payload = monitoring_refresh_decision(output.data)
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
                                "priority": host._get_priority("developer"),
                            }
                            task_queue.append(dev_task)
                            host._audit_agent_handoff(
                                product_id=pid,
                                from_agent=agent_type,
                                from_state=prev_state,
                                next_task=dev_task,
                                task_id=task_id,
                                reason="monitoring_refresh",
                                output_data=output.data if isinstance(output.data, dict) else None,
                            )
                            logger.warning(
                                "Monitoring → developer refresh for %s (repair %s/%s)",
                                pid,
                                mr_round,
                                max_quality_loops,
                            )

            eff_state = products[pid].get("state", "") if pid in products else target_state
            logger.info(f"Agent '{agent_type}' completed task {task_id} -> {eff_state}")
            record_task_lesson(pid, agent_type, eff_state, output.data if isinstance(output.data, dict) else {})

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
                ok_release, critic_issues = host._release_critic(pid, products[pid])
                if not ok_release:
                    critic_blocked = True
                    # Bounded repair budget with escalation (mirrors QA/security).
                    # Without a cap the product ping-pongs COMPLETED→release_critic→
                    # DEV_FIXING→… forever, burning paid heavy LLM calls — especially
                    # for issues code regen cannot fix (missing real feedback rows,
                    # architect-owned design_system.json).
                    new_critic_round = int(products[pid].get("critic_repair_round", 0) or 0) + 1
                    products[pid]["critic_repair_round"] = new_critic_round
                    products[pid]["updated_at"] = time.time()
                    products[pid]["last_bug_context"] = {
                        "source": "release_critic",
                        "issues": critic_issues,
                    }
                    critic_exhausted = new_critic_round > max_quality_loops
                    if critic_exhausted:
                        from core.autonomy_mode import is_full_autonomy
                        from orchestrator.autonomy_bridge import resolve_human_gate_async
                        from orchestrator.qa_repair_policy import notify_qa_human_review_pending

                        products[pid]["state"] = "HUMAN_REVIEW_PENDING"
                        if is_full_autonomy():
                            resolved = await resolve_human_gate_async(
                                products[pid],
                                point="release_critic_exhausted",
                                data_root=host.data_root,
                                context={"critic_issues": critic_issues},
                                llm_router=getattr(host, "_llm_router", None),
                            )
                            if resolved:
                                products[pid]["state"] = resolved
                                critic_exhausted = False
                                logger.warning(
                                    "Product %s: release-critic exhaust resolved by surrogate → %s",
                                    pid,
                                    resolved,
                                )
                        if critic_exhausted:
                            notify_qa_human_review_pending(pid, products[pid])
                            logger.warning(
                                "Product %s: release-critic repair budget exhausted → "
                                "HUMAN_REVIEW_PENDING (round %s/%s); issues=%s",
                                pid,
                                new_critic_round,
                                max_quality_loops,
                                critic_issues,
                            )
                    else:
                        products[pid]["state"] = "BUG_FOUND"
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
                                "critic_repair_round": new_critic_round,
                                "critic_repair_max": max_quality_loops,
                            },
                            "created_at": time.time(),
                            "priority": host._get_priority("developer"),
                        }
                        task_queue.append(dev_task)
                        host._audit_agent_handoff(
                            product_id=pid,
                            from_agent=agent_type,
                            from_state=prev_state,
                            next_task=dev_task,
                            task_id=task_id,
                            reason="release_critic",
                            blocked=True,
                            output_data=output.data if isinstance(output.data, dict) else None,
                        )
                        logger.warning(
                            "Release critic blocked completion for %s; queued DEV_FIXING "
                            "(%s) round %s/%s",
                            pid,
                            dev_task["id"],
                            new_critic_round,
                            max_quality_loops,
                        )
            if target_state == "COMPLETED" and not critic_blocked and pid in products:
                logger.info(f"Product {pid} pipeline completed!")
                try:
                    from web.backend.services.funnel_distribute import on_product_completed

                    on_product_completed(pid, products[pid])
                except Exception:
                    logger.debug("funnel_distribute failed for %s", pid, exc_info=True)
                try:
                    from web.backend.services.funnel_leads import (
                        notify_lead_product_completed,
                        on_product_state_change,
                    )

                    on_product_state_change(pid, products[pid])
                    await notify_lead_product_completed(pid, products[pid])
                except Exception:
                    logger.debug("funnel lead notify failed for %s", pid, exc_info=True)
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
            elif qa_gate_failed and not quality_gates_exhausted and not auto_recovered:
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
                            "backend_runtime_e2e": (qg or {}).get("backend_runtime_e2e"),
                            "methodology_review": (qg or {}).get("methodology_review"),
                            "reasons": (qg or {}).get("reasons"),
                            "issue_codes": [
                                i.get("code")
                                for i in ((qg or {}).get("demo_quality") or {}).get("issues", [])
                                if isinstance(i, dict) and i.get("code")
                            ],
                        },
                        "quality_repair_round": new_repair_round,
                        "quality_repair_max": max_quality_loops,
                        "qa_gate_blocked": True,
                    },
                    "created_at": time.time(),
                    "priority": host._get_priority("developer"),
                }
                exists = any(
                    t.get("product_id") == pid
                    and is_developer_agent(t.get("agent_type"))
                    and t.get("state") == "DEV_FIXING"
                    and t.get("status") in ("pending", "running")
                    for t in task_queue
                )
                if not exists:
                    task_queue.append(dev_task)
                    host._audit_agent_handoff(
                        product_id=pid,
                        from_agent=agent_type,
                        from_state=prev_state,
                        next_task=dev_task,
                        task_id=task_id,
                        reason="qa_gate",
                        blocked=True,
                        output_data=output.data if isinstance(output.data, dict) else None,
                    )
                    logger.warning(
                        f"QA gates failed for {pid} (repair {new_repair_round}/{max_quality_loops}); "
                        "BUG_FOUND → developer DEV_FIXING (mandatory regen/fix until gates pass or limit)"
                    )
            elif qa_gate_failed and quality_gates_exhausted:
                logger.warning(
                    "QA gates failed for %s — repair budgets exhausted; awaiting human review (not FAILED)",
                    pid,
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
                    "priority": host._get_priority("developer"),
                }
                exists = any(
                    t.get("product_id") == pid
                    and is_developer_agent(t.get("agent_type"))
                    and t.get("state") == "DEV_FIXING"
                    and t.get("status") in ("pending", "running")
                    for t in task_queue
                )
                if not exists:
                    task_queue.append(dev_task)
                    host._audit_agent_handoff(
                        product_id=pid,
                        from_agent=agent_type,
                        from_state=prev_state,
                        next_task=dev_task,
                        task_id=task_id,
                        reason="security_gate",
                        blocked=True,
                        output_data=output.data if isinstance(output.data, dict) else None,
                    )
                    logger.warning(
                        "Security gate failed for %s (repair %s/%s); "
                        "BUG_FOUND → developer DEV_FIXING",
                        pid,
                        sec_round,
                        max_security_loops,
                    )
            elif security_gate_failed and security_budget_exhausted:
                logger.warning(
                    "Security gate failed for %s — repair budgets exhausted; awaiting human review",
                    pid,
                )
            elif (
                agent_type == "devops"
                and pid in products
                and str(products[pid].get("state") or "") == "HUMAN_REVIEW_PENDING"
            ):
                from web.backend.services.product_followup import post_devops_human_review_approved

                if post_devops_human_review_approved(pid):
                    next_task = host._create_next_task(products[pid])
                    if next_task and next_task.get("agent_type") == "sales":
                        exists = any(
                            t.get("product_id") == pid
                            and t.get("agent_type") == "sales"
                            and t.get("status") in ("pending", "running")
                            for t in task_queue
                        )
                        if not exists:
                            task_queue.append(next_task)
                            logger.info(
                                "Product %s human gate already approved — queued sales (%s)",
                                pid,
                                next_task.get("id"),
                            )
                else:
                    logger.info(
                        "Product %s paused at post-DevOps human gate — awaiting admin approve before sales",
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
                            reason="sequential",
                            output_data=output.data if isinstance(output.data, dict) else None,
                        )
                        logger.info(f"Next task created for {pid}: {next_task['agent_type']} -> {next_task['state']}")
        else:
            task["status"] = "failed"
            task["error"] = output.error or "Agent returned failure"
            category, playbook = host.quality_manager.classify_failure(task["error"])
            task["failure_category"] = category
            task["auto_remediation_playbook"] = playbook
            task["completed_at"] = time.time()
            task.setdefault("retry_count", 0)
            from core.pipeline_retry_limits import task_max_retries

            task.setdefault("max_retries", task_max_retries())
            logger.warning(
                f"Agent '{agent_type}' failed task {task_id}: {output.error} "
                f"(retry {task['retry_count']}/{task['max_retries']})"
            )
            host.quality_manager.auto_requeue_pm_spec_gate(task, products, task_queue)

    except Exception as e:
        error_msg = str(e)
        logger.error(f"Error calling agent '{agent_type}' for task {task_id}: {error_msg}")

        # === RETRY LOGIC for LLM JSON parse failures ===
        is_json_error = any(kw in error_msg for kw in [
            "invalid/non-JSON", "Invalid JSON", "JSON parse error",
            "non-JSON response"
        ])

        if is_json_error:
            json_retries = int(task.get("json_parse_retry_count") or 0)
            from core.pipeline_retry_limits import json_parse_max_retries

            max_json_retries = json_parse_max_retries()

            if json_retries < max_json_retries:
                logger.warning(
                    "JSON parse retry %d/%d for %s task %s: %s",
                    json_retries + 1,
                    max_json_retries,
                    agent_type,
                    task_id,
                    error_msg,
                )
                task["json_parse_retry_count"] = json_retries + 1
                task["status"] = "pending"
                task["error"] = None
                task["started_at"] = None
                task["completed_at"] = None
                await asyncio.sleep(min(2 ** json_retries, 8))
                return

        # Permanent failure (exhausted retries or non-retryable error)
        task["status"] = "failed"
        task["error"] = error_msg
        category, playbook = host.quality_manager.classify_failure(error_msg)
        task["failure_category"] = category
        task["auto_remediation_playbook"] = playbook
        task["completed_at"] = time.time()
        task.setdefault("retry_count", 0)
        from core.pipeline_retry_limits import task_max_retries

        task.setdefault("max_retries", task_max_retries())
        host.quality_manager.auto_requeue_pm_spec_gate(task, products, task_queue)
