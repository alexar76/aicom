from __future__ import annotations

import hashlib
import logging
import os
import time
import uuid

from core.agent_roles import is_developer_agent
from core.logging_utils import log_suppressed

logger = logging.getLogger(__name__)

from typing import TYPE_CHECKING

from core.throughput_limits import effective_max_running_tasks
from orchestrator.task_queue_hygiene import (
    append_product_task,
    archive_superseded_failed_tasks,
    enforce_task_queue_hygiene,
    failed_task_may_terminalize_product,
    is_superseded_failed_task,
    pm_spec_requeue_allowed,
    recover_false_failed_products,
    try_pm_spec_requeue,
    unstick_blocked_tasks,
)

if TYPE_CHECKING:
    from collections.abc import Callable


def _task_status_norm(task: dict) -> str:
    return str((task or {}).get("status") or "").lower()


def _retry_jitter_factor(task_id: str) -> float:
    """Stable per-task backoff multiplier in roughly [0.8, 1.2] to avoid retry stampedes.

    Derived from a hash of the task id (not the global RNG) so a given task always
    gets the same factor within a run — keeps the backoff schedule monotonic per task
    while still spreading a cohort of co-failed tasks across the retry window.
    """
    if not task_id:
        return 1.0
    h = hashlib.blake2b(task_id.encode("utf-8"), digest_size=4).digest()
    frac = int.from_bytes(h, "big") / 0xFFFFFFFF  # 0.0 .. 1.0
    return 0.8 + 0.4 * frac


class TaskOrchestrator:
    def __init__(self, get_priority: Callable[[str], int]):
        self.get_priority = get_priority

    def recover_stale_running_tasks(self, task_queue: list, now: float) -> bool:
        """Reset tasks stuck in `running` (e.g. blocked sync I/O, hung LLM) back to pending.

        The threshold is adaptive (scales with the task's retry_count) so legitimate
        long-running deep-repair attempts are not killed on the same clock as a quick
        first try. A non-positive base disables the reset entirely.
        """
        from orchestrator.task_queue_hygiene import _stale_running_threshold_sec

        try:
            base_sec = float(os.environ.get("AIFACTORY_STALE_RUNNING_SEC", "1200"))
        except ValueError:
            base_sec = 1200.0
        if base_sec <= 0:
            return False
        changed = False
        to_front: list[dict] = []
        for task in list(task_queue):
            if _task_status_norm(task) != "running":
                continue
            started = float(task.get("started_at") or 0)
            if started <= 0:
                continue
            stale_sec = _stale_running_threshold_sec(
                str(task.get("agent_type") or ""), task=task
            )
            if now - started < stale_sec:
                continue
            try:
                task_queue.remove(task)
            except ValueError:
                continue
            task["status"] = "pending"
            task["started_at"] = None
            note = f"stale running reset after {stale_sec:.0f}s (AIFACTORY_STALE_RUNNING_SEC, adaptive)"
            prev = (task.get("error") or "").strip()
            task["error"] = f"{prev}; {note}" if prev else note
            to_front.append(task)
            changed = True
        for t in reversed(to_front):
            task_queue.insert(0, t)
        return changed

    def adopt_orphaned_running_tasks(self, products: dict, task_queue: list, now: float) -> bool:
        """ONE-SHOT at worker start: re-queue tasks the previous run died in the middle of.

        A task found ``running`` by a worker that has just started has no runner — the
        process that owned it is gone. Until now nothing said so: the first cycle simply
        dispatched it again, and because the crash happened before any failure handling,
        **the attempt was never counted**. A task that reliably kills the worker (OOM, a
        segfaulting native dep, a hang the supervisor times out) therefore restarted
        forever, with no backoff and no ladder — the one failure mode where "just retry"
        never converges.

        An unclean start IS an attempt, so it goes on ``retry_count`` and the existing
        retry ladder does the rest: backoff while attempts remain, terminalize when they
        run out. Nothing new to tune.

        Two caveats, stated where they matter.

        ONE WORKER per workspace, which is what the compose files deploy. Task rows carry no
        lease, so a second concurrent worker would already have re-dispatched these same rows
        before this method existed; adopting them does not make that worse, but it is not a
        fix for it either. Giving tasks a real owner is a separate decision.

        EVERY in-flight task is charged, not just the one that killed the worker — there is
        no way to know which one did. With a concurrency of 16 a single poison task therefore
        spends a bystander's ladder too, and after enough crashes parks its product for a
        human. That is deliberate: the alternative is the bug this method exists to fix, a
        ladder that silently resets on every restart. A worker crashing eight times over is
        not a state to keep running through quietly, and the products it was holding are
        exactly the list a human should be handed.
        """
        from core.pipeline_retry_limits import task_max_retries

        limit = task_max_retries()
        changed = False
        for task in task_queue:
            if _task_status_norm(task) != "running":
                continue
            pid = str(task.get("product_id") or "")
            # Every sibling sweep asks this before touching a task; skipping it here charged a
            # failed attempt against products an operator had explicitly paused.
            try:
                from core.pipeline_product_pause import is_product_pipeline_work_paused

                if pid and is_product_pipeline_work_paused(pid):
                    continue
            except Exception as exc:  # noqa: BLE001
                logger.warning("pause check failed for %s: %s", pid, exc)
            attempts = int(task.get("retry_count") or 0) + 1
            task["retry_count"] = attempts
            task["started_at"] = None
            note = (
                f"unclean worker start (attempt {attempts}/{limit}): "
                "the previous run died while this task was running"
            )
            prev = (task.get("error") or "").strip()
            task["error"] = (f"{prev}; {note}" if prev else note)[:8000]
            if attempts > limit:
                # Out of attempts: hand it to the failure path instead of restarting it
                # into the same crash.
                task["status"] = "failed"
                task["completed_at"] = now
                logger.warning(
                    "Task %s exhausted %d attempts across unclean worker starts — failing it",
                    task.get("id"),
                    limit,
                )
                self._park_crash_loop(products.get(pid), pid, now, note)
            else:
                task["status"] = "pending"
                logger.info(
                    "Adopted orphaned running task %s (attempt %d/%d) after an unclean start",
                    task.get("id"),
                    attempts,
                    limit,
                )
            changed = True
        return changed

    @staticmethod
    def _park_crash_loop(product: dict | None, product_id: str, now: float, note: str) -> None:
        """Stop the product being bootstrapped straight back into the crash.

        Failing the task is not enough on its own: `create_initial_tasks` re-creates a first
        stage for any IDEA_RECEIVED product with no live task, and the new row starts at
        retry_count 0. The ladder we just climbed would reset on every restart — the exact
        loop the counter exists to end, escaping through the bootstrap. Parking the product
        at the human gate closes it, and `crash_loop_parked` is in the same park-kind set the
        idle healer and the queue hygiene already refuse to advance.
        """
        if not product:
            return
        state = str(product.get("state") or "").upper()
        if state in ("COMPLETED", "FAILED", "CANCELLED", "HUMAN_REVIEW_PENDING"):
            return
        product["state"] = "HUMAN_REVIEW_PENDING"
        product["human_review_kind"] = "crash_loop_parked"
        product["human_review_reason"] = note
        product["pipeline_stuck_reason"] = note
        product["pipeline_stuck_at"] = now
        product["updated_at"] = now
        logger.warning(
            "Parked %s at the human gate: its stage keeps taking the worker down with it",
            product_id,
        )

    def archive_superseded_failed_tasks(self, products: dict, task_queue: list, now: float) -> bool:
        return archive_superseded_failed_tasks(products, task_queue, now)

    def recover_false_failed_products(self, products: dict, task_queue: list, now: float) -> bool:
        return recover_false_failed_products(products, task_queue, now)

    def reconcile_product_task_states(self, products: dict, task_queue: list, now: float) -> bool:
        from orchestrator.task_queue_hygiene import reconcile_product_task_states

        return reconcile_product_task_states(products, task_queue, now)

    def recover_stranded_pm_quality_failures(self, products: dict, task_queue: list, now: float) -> bool:
        changed = False
        try:
            max_recoveries = int(os.environ.get("AIFACTORY_PM_STRANDED_RECOVERY_MAX", "2"))
        except ValueError:
            max_recoveries = 2
        max_recoveries = max(0, max_recoveries)
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
            product_state = str(products[pid].get("state") or "").upper()
            if product_state == "FAILED":
                continue
            if not pm_spec_requeue_allowed(product_state):
                continue
            recovery_count = int(products[pid].get("pm_stranded_recovery_count") or 0)
            if recovery_count >= max_recoveries:
                continue
            # Cumulative-cost guard: do not auto-recover a stranded PM failure once the
            # product has already exhausted its LLM budget (each recovery is a full spec
            # regeneration). Mirrors the guard in try_pm_spec_requeue.
            try:
                from core.pipeline_cost_guard import check_product_budget

                within_budget, spent, cap = check_product_budget(str(pid))
                if not within_budget:
                    logger.warning(
                        "PM stranded recovery skipped for %s: pipeline cost budget exhausted ($%.2f/$%.2f)",
                        pid,
                        spent,
                        cap,
                    )
                    continue
            except Exception:
                logger.debug("PM stranded recovery cost-guard check failed for %s", pid, exc_info=True)
            err_low = (failed_task.get("error") or "").lower()
            try:
                from agents.product_profile import idea_charter_forces_landing_only

                if "[methodology|" in err_low and idea_charter_forces_landing_only(
                    products[pid].get("idea")
                ):
                    continue
            except ImportError as _suppressed_exc:
                log_suppressed(logger, "non-fatal (orchestrator/worker_components.py)", exc_info=_suppressed_exc)
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
            append_product_task(task_queue, new_task, products, get_priority=self.get_priority)
            failed_task["auto_recovered_after_restart"] = True
            products[pid]["state"] = "MARKET_RESEARCHED"
            products[pid]["pm_stranded_recovery_count"] = recovery_count + 1
            products[pid]["updated_at"] = now
            changed = True
        return changed

    def create_initial_tasks(self, products: dict, task_queue: list, now: float) -> bool:
        changed = False
        for pid, product in products.items():
            try:
                from core.pipeline_product_pause import is_product_pipeline_work_paused

                if is_product_pipeline_work_paused(pid):
                    continue
            except Exception as exc:
                logger.warning("pause check failed for %s: %s", pid, exc)
            if product.get("state") == "IDEA_RECEIVED":
                has_task = any(
                    t.get("product_id") == pid
                    and _task_status_norm(t) in ("pending", "running")
                    for t in task_queue
                )
                if not has_task:
                    from orchestrator.landing_fast_flow import is_landing_fast_product

                    if is_landing_fast_product(product):
                        first_agent, first_state = "__landing_spec__", "SPEC_WRITTEN"
                    else:
                        first_agent, first_state = "analyst", "MARKET_RESEARCHED"
                    # Prepend so new products are not starved behind a huge historical backlog
                    # (task_queue is scanned in list order; SQLite loads tasks by created_at ASC).
                    task_queue.insert(
                        0,
                        {
                            "id": f"task-{uuid.uuid4().hex[:12]}",
                            "product_id": pid,
                            "agent_type": first_agent,
                            "state": first_state,
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

    def start_pending_tasks(self, products: dict, task_queue: list, now: float) -> bool:
        changed = False
        max_running_total = effective_max_running_tasks()
        max_running_total = max(1, max_running_total)
        running_total = sum(1 for t in task_queue if _task_status_norm(t) == "running")
        for task in task_queue:
            if _task_status_norm(task) == "pending":
                if running_total >= max_running_total:
                    break
                pid = task["product_id"]
                try:
                    from core.pipeline_product_pause import is_product_pipeline_work_paused
                    from web.backend.services.product_followup import is_product_improvement_on_hold

                    if is_product_pipeline_work_paused(pid) or is_product_improvement_on_hold(pid):
                        continue
                except Exception as exc:
                    logger.warning("hold check failed for %s: %s", pid, exc)
                if str((products.get(pid) or {}).get("state") or "").upper() == "FAILED":
                    continue
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
        from core.pipeline_retry_limits import task_max_retries

        changed = False
        default_max = task_max_retries()
        terminalized_pids: set[str] = set()
        for task in task_queue:
            if _task_status_norm(task) != "failed":
                continue
            pid = str(task.get("product_id") or "")
            product = products.get(pid) or {}
            if is_superseded_failed_task(task, product):
                task["status"] = "cancelled"
                prev_err = (task.get("error") or "").strip()
                task["error"] = (
                    f"{prev_err}; archive_superseded_failed"
                    if prev_err
                    else "archive_superseded_failed"
                )[:8000]
                task["completed_at"] = task.get("completed_at") or now
                changed = True
                continue
            try:
                from core.pipeline_product_pause import is_product_pipeline_work_paused

                if pid and is_product_pipeline_work_paused(pid):
                    continue
            except Exception as exc:
                logger.warning("pause check failed for task %s: %s", task.get("id"), exc)
            retry_count = task.get("retry_count", 0)
            max_retries = int(task.get("max_retries") or default_max)
            if retry_count < max_retries:
                # Exponential backoff with per-task jitter so a burst of tasks that
                # failed together (e.g. provider outage) do not all retry on the same
                # tick and re-stampede the LLM/provider (thundering herd). The factor
                # is derived from the task id so a given task's schedule is stable
                # within a run, spread across roughly [0.8, 1.2].
                base_backoff = 30 * (2 ** retry_count)
                backoff = base_backoff * _retry_jitter_factor(str(task.get("id") or ""))
                failed_at = task.get("completed_at", task.get("started_at", 0))
                if now - failed_at >= backoff:
                    task["retry_count"] = retry_count + 1
                    task["status"] = "pending"
                    task["error"] = None
                    task["completed_at"] = None
                    changed = True
                continue
            if pid not in products or products[pid].get("state") == "FAILED":
                continue
            if try_pm_spec_requeue(task, products, task_queue, self.get_priority):
                changed = True
                continue
            if not failed_task_may_terminalize_product(task, product):
                task["status"] = "cancelled"
                prev_err = (task.get("error") or "").strip()
                task["error"] = (
                    f"{prev_err}; archive_stale_failed_no_terminalize"
                    if prev_err
                    else "archive_stale_failed_no_terminalize"
                )[:8000]
                task["completed_at"] = task.get("completed_at") or now
                changed = True
                continue
            if pid in terminalized_pids:
                task["status"] = "cancelled"
                prev_err = (task.get("error") or "").strip()
                task["error"] = (
                    f"{prev_err}; duplicate_failed_terminalize_skipped"
                    if prev_err
                    else "duplicate_failed_terminalize_skipped"
                )[:8000]
                task["completed_at"] = task.get("completed_at") or now
                changed = True
                continue
            products[pid]["state"] = "FAILED"
            terminalized_pids.add(pid)
            err = (task.get("error") or "").strip()
            if err:
                products[pid]["failure_reason"] = err[:4000]
            products[pid]["updated_at"] = now
            try:
                from web.backend.services.pipeline_failed_notify import (
                    notify_pipeline_product_failed,
                )

                notify_pipeline_product_failed(
                    pid,
                    product=products[pid],
                    task=task,
                    failure_reason=err or None,
                )
            except Exception:
                logger.debug(
                    "pipeline_failed_notify failed for %s (task failure)",
                    pid,
                    exc_info=True,
                )
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
        from web.backend.services.product_followup import is_product_improvement_on_hold

        for pid, product in products.items():
            if product.get("state") != "COMPLETED":
                continue
            if is_product_improvement_on_hold(pid):
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
        from web.backend.services.product_followup import is_product_improvement_on_hold

        changed = False
        for pid, product in products.items():
            if product.get("state") != "COMPLETED":
                continue
            if is_product_improvement_on_hold(pid):
                continue
            if any(
                t.get("product_id") == pid
                and t.get("agent_type") == "__complete__"
                and t.get("status") in ("pending", "running")
                for t in task_queue
            ):
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

    # Phase 0 of every cycle: five independent repairs of state a previous run left
    # behind. Order matters — archiving superseded failures first keeps the later
    # recoveries from resurrecting a task that is already obsolete — so they live
    # together here instead of being re-listed (and re-ordered) at each call site.
    RECOVERY_SWEEPS = (
        "archive_superseded_failed_tasks",
        "recover_false_failed_products",
        "reconcile_product_task_states",
        "recover_stranded_pm_quality_failures",
    )

    def run_recovery_sweeps(self, products: dict, task_queue: list, now: float) -> bool:
        """Run every startup/recovery sweep. True if any of them changed state.

        Each sweep runs regardless of what the earlier ones returned: they repair
        different damage and skipping the rest on the first hit would leave a product
        half-recovered until the next cycle.
        """
        changed = False
        for name in self.RECOVERY_SWEEPS:
            if getattr(self, name)(products, task_queue, now):
                changed = True
        # Tasks stuck in `running` (a blocked sync call, or a worker killed mid-flight).
        if self.recover_stale_running_tasks(task_queue, now):
            changed = True
        return changed

    def enforce_queue_hygiene(self, products: dict, task_queue: list, now: float) -> bool:
        return enforce_task_queue_hygiene(products, task_queue, now)

    def unstick_blocked_tasks(self, products: dict, task_queue: list, now: float) -> bool:
        return unstick_blocked_tasks(products, task_queue, now)


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

    def auto_requeue_pm_spec_gate(self, task: dict, products: dict, task_queue: list) -> bool:
        """Re-open PM after spec gate failure instead of terminal FAILED (product-level budget)."""
        return try_pm_spec_requeue(task, products, task_queue, self.get_priority)


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
        if agent_type == "qa":
            try:
                max_iters = int(os.environ.get("AIFACTORY_QA_PEER_REVIEW_MAX_ITERS", "0"))
            except ValueError:
                max_iters = 0
            if max_iters > 0:
                iterations = int(product_state.get("qa_peer_review_iterations") or 0)
                if iterations >= max_iters:
                    product_state["qa_review_forced_proceed"] = {
                        "iterations": iterations,
                        "max_iterations": max_iters,
                        "blockers": blockers,
                        "notes": current.get("notes", ""),
                        "forced_at": time.time(),
                    }
                    reviews[agent_type]["recommended"] = "approve"
                    product_state["peer_reviews"] = reviews
                    return False
                product_state["qa_peer_review_iterations"] = iterations + 1
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
                logger.debug("agent_handoff_audit skipped (peer_review_block)", exc_info=True)
        product_state["state"] = "BUG_FOUND" if (is_developer_agent(tgt_agent) or tgt_agent == "hardening") else product_state.get("state", "")
        product_state["updated_at"] = time.time()
        return True
