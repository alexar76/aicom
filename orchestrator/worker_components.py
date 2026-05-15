from __future__ import annotations

import os
import time
import uuid
from typing import Callable

from core.throughput_limits import effective_max_running_tasks


def _task_status_norm(task: dict) -> str:
    return str((task or {}).get("status") or "").lower()


class TaskOrchestrator:
    def __init__(self, get_priority: Callable[[str], int]):
        self.get_priority = get_priority

    def recover_stale_running_tasks(self, task_queue: list, now: float) -> bool:
        """Reset tasks stuck in `running` (e.g. blocked sync I/O, hung LLM) back to pending."""
        try:
            stale_sec = float(os.environ.get("AIFACTORY_STALE_RUNNING_SEC", "1200"))
        except ValueError:
            stale_sec = 1200.0
        if stale_sec <= 0:
            return False
        changed = False
        to_front: list[dict] = []
        for task in list(task_queue):
            if _task_status_norm(task) != "running":
                continue
            started = float(task.get("started_at") or 0)
            if started <= 0:
                continue
            if now - started < stale_sec:
                continue
            try:
                task_queue.remove(task)
            except ValueError:
                continue
            task["status"] = "pending"
            task["started_at"] = None
            note = f"stale running reset after {stale_sec:.0f}s (AIFACTORY_STALE_RUNNING_SEC)"
            prev = (task.get("error") or "").strip()
            task["error"] = f"{prev}; {note}" if prev else note
            to_front.append(task)
            changed = True
        for t in reversed(to_front):
            task_queue.insert(0, t)
        return changed

    def recover_stranded_pm_quality_failures(self, products: dict, task_queue: list, now: float) -> bool:
        changed = False
        latest_failed_pm: dict[str, dict] = {}
        for task in task_queue:
            if task.get("agent_type") != "pm" or task.get("status") != "failed":
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
            if has_active_pm or pid not in products or failed_task.get("auto_recovered_after_restart"):
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
                "priority": self.get_priority("pm"),
                "auto_requeue_reason": "pm_spec_quality_gate_restart_recovery",
            }
            task_queue.append(new_task)
            failed_task["auto_recovered_after_restart"] = True
            products[pid]["state"] = "MARKET_RESEARCHED"
            products[pid]["updated_at"] = now
            changed = True
        return changed

    def create_initial_tasks(self, products: dict, task_queue: list, now: float) -> bool:
        changed = False
        for pid, product in products.items():
            if product.get("state") == "IDEA_RECEIVED":
                has_task = any(
                    t.get("product_id") == pid
                    and _task_status_norm(t) in ("pending", "running")
                    for t in task_queue
                )
                if not has_task:
                    # Prepend so new products are not starved behind a huge historical backlog
                    # (task_queue is scanned in list order; SQLite loads tasks by created_at ASC).
                    task_queue.insert(
                        0,
                        {
                            "id": f"task-{uuid.uuid4().hex[:12]}",
                            "product_id": pid,
                            "agent_type": "analyst",
                            "state": "MARKET_RESEARCHED",
                            "status": "pending",
                            "retry_count": 0,
                            "max_retries": 3,
                            "input_data": {
                                "product_id": pid,
                                "idea": product.get("idea", ""),
                                "admin_instructions": product.get("admin_instructions", ""),
                            },
                            "created_at": now,
                            "priority": 0,
                        },
                    )
                    changed = True
        return changed

    def start_pending_tasks(self, task_queue: list, now: float) -> bool:
        changed = False
        max_running_total = effective_max_running_tasks()
        max_running_total = max(1, max_running_total)
        running_total = sum(1 for t in task_queue if _task_status_norm(t) == "running")
        for task in task_queue:
            if _task_status_norm(task) == "pending":
                if running_total >= max_running_total:
                    break
                pid = task["product_id"]
                other_running = any(
                    t.get("product_id") == pid and _task_status_norm(t) == "running"
                    for t in task_queue
                )
                if not other_running:
                    task["status"] = "running"
                    task["started_at"] = now
                    running_total += 1
                    changed = True
        return changed

    def retry_failed_tasks(self, products: dict, task_queue: list, now: float) -> bool:
        changed = False
        for task in task_queue:
            if task.get("status") == "failed":
                retry_count = task.get("retry_count", 0)
                max_retries = task.get("max_retries", 3)
                if retry_count < max_retries:
                    backoff = 30 * (2 ** retry_count)
                    failed_at = task.get("completed_at", task.get("started_at", 0))
                    if now - failed_at >= backoff:
                        task["retry_count"] = retry_count + 1
                        task["status"] = "pending"
                        task["error"] = None
                        task["completed_at"] = None
                        changed = True
                else:
                    pid = task.get("product_id", "")
                    if pid in products and products[pid].get("state") != "FAILED":
                        products[pid]["state"] = "FAILED"
                        products[pid]["updated_at"] = now
                        changed = True
        return changed

    def enqueue_market_monitoring(self, products: dict, task_queue: list, now: float) -> bool:
        changed = False
        try:
            interval = float(os.environ.get("AIFACTORY_MARKET_REVISION_INTERVAL_SEC", "86400"))
        except ValueError:
            interval = 86400.0
        if interval <= 0:
            return False
        for pid, product in products.items():
            if product.get("state") != "COMPLETED":
                continue
            last_revision = product.get("last_market_revision", 0)
            if now - last_revision < interval:
                continue
            has_revision_task = any(
                t.get("product_id") == pid
                and t.get("agent_type") == "analyst"
                and t.get("state") == "EVOLUTION_ANALYZING"
                and t.get("status") in ("pending", "running")
                for t in task_queue
            )
            if has_revision_task:
                continue
            task_queue.append(
                {
                    "id": f"task-{uuid.uuid4().hex[:12]}",
                    "product_id": pid,
                    "agent_type": "analyst",
                    "state": "EVOLUTION_ANALYZING",
                    "status": "pending",
                    "retry_count": 0,
                    "max_retries": 2,
                    "input_data": {
                        "product_id": pid,
                        "idea": product.get("idea", ""),
                        "mode": "monitoring",
                        "admin_instructions": product.get("admin_instructions", ""),
                    },
                    "created_at": now,
                    "priority": 1,
                }
            )
            product["last_market_revision"] = now
            changed = True
        return changed

    def enqueue_refactor_sprint(self, products: dict, task_queue: list, now: float) -> bool:
        """
        Explicit anti-tech-debt phase for shipped products.
        Creates periodic hardening/refactor tasks so refactoring is not implicit.
        """
        try:
            interval = float(os.environ.get("AIFACTORY_REFACTOR_INTERVAL_SEC", "604800"))
        except ValueError:
            interval = 604800.0
        if interval <= 0:
            return False
        changed = False
        for pid, product in products.items():
            if product.get("state") != "COMPLETED":
                continue
            last_refactor = float(product.get("last_refactor_sprint_at") or 0)
            if now - last_refactor < interval:
                continue
            exists = any(
                t.get("product_id") == pid
                and t.get("agent_type") == "hardening"
                and t.get("status") in ("pending", "running")
                for t in task_queue
            )
            if exists:
                continue
            task_queue.append(
                {
                    "id": f"task-{uuid.uuid4().hex[:12]}",
                    "product_id": pid,
                    "agent_type": "hardening",
                    "state": "DEV_FIXING",
                    "status": "pending",
                    "retry_count": 0,
                    "max_retries": 3,
                    "input_data": {
                        "product_id": pid,
                        "idea": product.get("idea", ""),
                        "refactor_sprint": True,
                        "admin_instructions": (
                            "Run explicit refactoring sprint: reduce complexity and tech debt, "
                            "improve maintainability without regressing functionality."
                        ),
                    },
                    "created_at": now,
                    "priority": 4,
                    "auto_requeue_reason": "scheduled_refactor_sprint",
                }
            )
            product["last_refactor_sprint_at"] = now
            changed = True
        return changed


class QualityManager:
    def __init__(self, get_priority: Callable[[str], int]):
        self.get_priority = get_priority

    def classify_failure(self, error_text: str) -> tuple[str, str]:
        e = (error_text or "").lower()
        if any(k in e for k in ("specification failed quality gate", "acceptance_criteria", "non_functional_requirements")):
            return "spec", "pm_spec_rewrite"
        if any(k in e for k in ("browser e2e", "demo/tz gate", "a11y_", "ux_")):
            return "design", "developer_ui_regen"
        if any(k in e for k in ("import error", "syntaxerror", "traceback", "test failure")):
            return "code", "developer_code_fix"
        if any(k in e for k in ("connection refused", "timeout", "docker", "service unavailable")):
            return "infra", "devops_runtime_probe"
        return "unknown", "manual_triage"

    def auto_requeue_pm_spec_gate(self, task: dict, products: dict, task_queue: list) -> None:
        if task.get("agent_type") != "pm":
            return
        error_text = (task.get("error") or "").lower()
        if "specification failed quality gate" not in error_text or task.get("auto_requeued_pm_spec_gate"):
            return
        pid = task.get("product_id")
        if not pid or pid not in products:
            return
        exists = any(
            t.get("product_id") == pid
            and t.get("agent_type") == "pm"
            and t.get("status") in ("pending", "running")
            for t in task_queue
        )
        task["auto_requeued_pm_spec_gate"] = True
        if exists:
            return
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
                    "Auto-recovery: previous PM attempt failed the specification quality gate. "
                    "Return complete JSON with testable acceptance_criteria for every user story; "
                    "for full_software include detailed functional_requirements acceptance criteria."
                ),
            },
            "created_at": time.time(),
            "priority": self.get_priority("pm"),
            "auto_requeue_reason": "pm_spec_quality_gate",
        }
        task_queue.append(new_task)
        products[pid]["state"] = "MARKET_RESEARCHED"
        products[pid]["updated_at"] = time.time()


class PeerReviewEngine:
    def __init__(self, get_priority: Callable[[str], int]):
        self.get_priority = get_priority

    def register(self, product: dict, agent_type: str, output_data: dict) -> None:
        reviews = product.get("peer_reviews")
        if not isinstance(reviews, dict):
            reviews = {}
        review_obj = output_data.get("peer_review") if isinstance(output_data, dict) else None
        if not isinstance(review_obj, dict):
            review_obj = {
                "recommended": "approve",
                "blockers": [],
                "notes": f"{agent_type} completed without explicit peer review payload",
            }
        reviews[agent_type] = {
            "recommended": str(review_obj.get("recommended", "approve")).lower(),
            "blockers": review_obj.get("blockers") or [],
            "notes": review_obj.get("notes") or "",
            "updated_at": time.time(),
        }
        product["peer_reviews"] = reviews

    def apply_block(self, task: dict, product_state: dict, task_queue: list, product_row: dict) -> bool:
        reviews = product_state.get("peer_reviews")
        if not isinstance(reviews, dict):
            return False
        current = reviews.get(task.get("agent_type"))
        if not isinstance(current, dict):
            return False
        if str(current.get("recommended", "approve")).lower() != "block":
            return False
        blockers = current.get("blockers") or []
        agent_type = task.get("agent_type")
        remap = {
            "pm": ("pm", "SPEC_WRITTEN"),
            "architect": ("architect", "ARCH_DESIGNED"),
            "design_critic": ("architect", "ARCH_DESIGNED"),
            "developer": ("developer", "CODE_COMMITTED"),
            "hardening": ("hardening", "DEV_FIXING"),
            "qa": ("developer", "DEV_FIXING"),
        }
        target = remap.get(agent_type)
        if not target:
            return False
        tgt_agent, tgt_state = target
        if agent_type == "design_critic":
            try:
                max_iters = int(os.environ.get("AIFACTORY_DESIGN_REVIEW_MAX_ITERS", "3"))
            except ValueError:
                max_iters = 3
            iterations = int(product_state.get("design_review_iterations") or 0)
            if iterations >= max(1, max_iters):
                # Force proceed after capped review loops; keep issues visible on product.
                product_state["design_review_forced_proceed"] = {
                    "iterations": iterations,
                    "max_iterations": max_iters,
                    "blockers": blockers,
                    "notes": current.get("notes", ""),
                    "forced_at": time.time(),
                }
                return False
            product_state["design_review_iterations"] = iterations + 1
        pid = task.get("product_id")
        exists = any(
            t.get("product_id") == pid
            and t.get("agent_type") == tgt_agent
            and t.get("status") in ("pending", "running")
            for t in task_queue
        )
        if not exists:
            handoff_task = {
                "id": f"task-{uuid.uuid4().hex[:12]}",
                "product_id": pid,
                "agent_type": tgt_agent,
                "state": tgt_state,
                "status": "pending",
                "retry_count": 0,
                "max_retries": 3,
                "input_data": {
                    "product_id": pid,
                    "idea": product_row.get("idea", ""),
                    "peer_review_feedback": {
                        "source_agent": agent_type,
                        "blockers": blockers,
                        "notes": current.get("notes", ""),
                    },
                },
                "created_at": time.time(),
                "priority": self.get_priority(tgt_agent),
            }
            task_queue.append(handoff_task)
            try:
                from security.agent_handoff_audit import log_handoff_from_task

                log_handoff_from_task(
                    product_id=str(pid or ""),
                    from_agent=str(agent_type or ""),
                    from_state=str(task.get("state") or ""),
                    next_task=handoff_task,
                    task_id=str(task.get("id") or ""),
                    reason="peer_review_block",
                    blocked=True,
                    extra={"blockers": blockers[:8] if isinstance(blockers, list) else []},
                )
            except Exception:
                pass
        product_state["state"] = "BUG_FOUND" if tgt_agent in ("developer", "hardening") else product_state.get("state", "")
        product_state["updated_at"] = time.time()
        return True
