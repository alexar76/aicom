"""Task queue hygiene: dedupe active tasks and block regressive re-queues."""

from __future__ import annotations

import time as _time

import logging
import os
import time
from typing import TYPE_CHECKING

from core.agent_roles import is_architect_agent, is_developer_agent
from core.spec_presence import spec_has_substance as _spec_has_substance
from orchestrator.pipeline_flow import PIPELINE_AGENT_FLOW, pipeline_product_states

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)

_STATE_RANK: dict[str, int] = {
    str(s).upper(): i for i, s in enumerate(pipeline_product_states())
}

# States at or before spec — PM spec auto-requeue is allowed only here (plus explicit FAILED recovery).
_PM_SPEC_REQUEUE_MAX_RANK = _STATE_RANK.get("SPEC_WRITTEN", 2)

_REPAIR_AGENT_STATES: frozenset[tuple[str, str]] = frozenset(
    {
        ("developer", "DEV_FIXING"),
        ("developer", "CODE_COMMITTED"),
        ("qa", "QA_TESTING"),
        ("hardening", "DEV_FIXING"),
        ("design_critic", "DESIGN_CRITIQUED"),
        ("architect", "ARCH_DESIGNED"),
    }
)


def _is_repair_agent_state(agent: str, state: str) -> bool:
    """Membership in ``_REPAIR_AGENT_STATES``, treating the landing fast-path
    variants (``landing_developer`` / ``landing_architect``) exactly like their
    generic counterparts — see ``core/agent_roles`` for the mirroring contract."""
    if (agent, state) in _REPAIR_AGENT_STATES:
        return True
    if is_developer_agent(agent) and ("developer", state) in _REPAIR_AGENT_STATES:
        return True
    if is_architect_agent(agent) and ("architect", state) in _REPAIR_AGENT_STATES:
        return True
    return False


def state_rank(state: str | None) -> int:
    return _STATE_RANK.get(str(state or "").upper(), -1)


def is_superseded_failed_task(task: dict, product: dict) -> bool:
    """
    True when a failed task row is historical noise for the product's current stage.

    Prevents retry_failed_tasks from marking advanced products FAILED because of
    ancient PM spec-gate failures still present in the SQLite task history.
    """
    if str(task.get("status") or "").lower() != "failed":
        return False
    ps = str(product.get("state") or "").upper()
    if ps in ("COMPLETED", "DEPLOYED_PRODUCTION", "CANCELLED"):
        return True
    agent = str(task.get("agent_type") or "").lower()
    tgt = str(task.get("state") or "").upper()
    pr = product_state_rank(ps)
    tr = _task_rank(task)
    if tr < 0 or pr < 0:
        return False
    if _is_repair_agent_state(agent, tgt) and ps in (
        "BUG_FOUND",
        "DEV_FIXING",
        "QA_TESTING",
        "CODE_TESTING",
        "CODE_COMMITTED",
    ):
        return False
    if pr > tr:
        return True
    err = (task.get("error") or "").lower()
    return bool(agent == "pm" and "specification failed quality gate" in err and not pm_spec_requeue_allowed(ps))


def failed_task_may_terminalize_product(task: dict, product: dict) -> bool:
    """Only failures at/near the product's current stage may set state=FAILED."""
    if is_superseded_failed_task(task, product):
        return False
    ps = str(product.get("state") or "").upper()
    if ps in ("COMPLETED", "DEPLOYED_PRODUCTION", "CANCELLED", "IDEA_RECEIVED"):
        return False
    tr = _task_rank(task)
    pr = product_state_rank(ps)
    if tr < 0 or pr < 0:
        return True
    return tr >= pr - 1


_FALSE_FAILED_ERROR_MARKERS = (
    "archive_superseded_failed",
    "archive_stale_failed_no_terminalize",
)


def _active_repair_tasks(product_id: str, task_queue: list) -> list[dict]:
    out: list[dict] = []
    for t in task_queue:
        if str(t.get("product_id") or "") != product_id:
            continue
        if str(t.get("status") or "").lower() not in ("pending", "running"):
            continue
        agent = str(t.get("agent_type") or "").lower()
        state = str(t.get("state") or "").upper()
        if _is_repair_agent_state(agent, state):
            out.append(t)
    return out


def is_likely_false_failed_product(product: dict, task_queue: list) -> bool:
    """
    Detect products marked FAILED only because stale queue rows were retried on worker restart,
    or terminal FAILED stuck while a repair task is already queued.
    """
    ps = str(product.get("state") or "").upper()
    if ps != "FAILED":
        return False
    pid = str(product.get("id") or product.get("product_id") or "")
    if not pid:
        return False

    product_tasks = [t for t in task_queue if str(t.get("product_id") or "") == pid]
    failed_rows = [t for t in product_tasks if str(t.get("status") or "").lower() == "failed"]
    if failed_rows and all(is_superseded_failed_task(t, product) for t in failed_rows):
        return True

    fr = str(product.get("failure_reason") or product.get("error") or "").lower()
    if any(marker in fr for marker in _FALSE_FAILED_ERROR_MARKERS):
        return True

    # FAILED with repair already queued but no failed task — state/desync after restart.
    if not failed_rows and _active_repair_tasks(pid, task_queue):
        return True

    # Empty failure_reason — typical false-FAILED from retry_failed_tasks on stale PM rows.
    if not fr.strip():
        return True

    return bool("specification failed quality gate" in fr and not failed_rows)


def recovery_state_after_false_failed(product: dict, task_queue: list | None = None) -> str:
    """Pick a safe non-terminal state when undoing a false FAILED."""
    ps = str(product.get("state") or "").upper()
    if ps != "FAILED":
        return ps
    pid = str(product.get("id") or product.get("product_id") or "")
    tasks = task_queue or []
    repair = _active_repair_tasks(pid, tasks) if pid else []
    if repair:
        # Match the queued repair task (usually DEV_FIXING).
        st = str(repair[0].get("state") or "").upper()
        if st == "DEV_FIXING":
            return "BUG_FOUND"
        if st:
            return st
    try:
        from web.backend.api.products import _product_has_code

        if pid and _product_has_code(pid):
            return "BUG_FOUND"
    except Exception:
        logger.debug("_infer_reopen_state: _product_has_code check failed for %s", pid, exc_info=True)
    return "MARKET_RESEARCHED"


def recover_false_failed_products(
    products: dict,
    task_queue: list,
    now: float,
) -> bool:
    """Re-open products wrongly terminalized from superseded failed task rows."""
    changed = False
    for pid, product in list(products.items()):
        if not is_likely_false_failed_product(product, task_queue):
            continue
        reopen = recovery_state_after_false_failed(product, task_queue)
        product["state"] = reopen
        for key in ("failure_reason", "error", "last_error"):
            product.pop(key, None)
        meta = product.get("metadata")
        if isinstance(meta, dict):
            meta.pop("failure_reason", None)
            meta.pop("error", None)
        product["updated_at"] = now
        logger.warning(
            "Recovered false FAILED product %s → %s (stale queue row, not a real terminal failure)",
            pid,
            reopen,
        )
        changed = True
    return changed


def archive_superseded_failed_tasks(
    products: dict,
    task_queue: list,
    now: float,
) -> bool:
    """Cancel failed tasks that no longer apply to the product's pipeline stage."""
    changed = False
    for task in task_queue:
        pid = task.get("product_id")
        if not pid or pid not in products:
            continue
        if not is_superseded_failed_task(task, products[pid]):
            continue
        task["status"] = "cancelled"
        prev_err = (task.get("error") or "").strip()
        suffix = "archive_superseded_failed"
        task["error"] = f"{prev_err}; {suffix}" if prev_err else suffix
        task["error"] = str(task["error"])[:8000]
        task["completed_at"] = task.get("completed_at") or now
        changed = True
    if changed:
        logger.info("Archived superseded failed tasks in worker queue snapshot")
    return changed


def product_state_rank(state: str | None) -> int:
    return state_rank(state)


def pm_spec_requeue_allowed(product_state: str | None) -> bool:
    """PM spec gate recovery must not rewind products already past specification."""
    ps = str(product_state or "").upper()
    if ps == "FAILED":
        return True
    rank = product_state_rank(ps)
    if rank < 0:
        return False
    return rank <= _PM_SPEC_REQUEUE_MAX_RANK


def _task_rank(task: dict) -> int:
    agent = str(task.get("agent_type") or "").lower()
    state = str(task.get("state") or "").upper()
    if agent == "analyst" and state == "EVOLUTION_ANALYZING":
        return _STATE_RANK.get("EVOLUTION_ANALYZING", 999)
    if agent == "__complete__":
        return _STATE_RANK.get("COMPLETED", 999)
    if agent == "__runtime_test__":
        return _STATE_RANK.get("CODE_TESTING", state_rank("CODE_COMMITTED"))
    return state_rank(state)


def is_regressive_task(product_state: str | None, task: dict) -> bool:
    """True when an active task targets a stage clearly behind product progress."""
    ps = str(product_state or "").upper()
    if ps in ("FAILED", "CANCELLED", "IDEA_RECEIVED"):
        return False
    pr = product_state_rank(ps)
    if pr < 0:
        return False
    agent = str(task.get("agent_type") or "").lower()
    state = str(task.get("state") or "").upper()
    if _is_repair_agent_state(agent, state):
        return False
    tr = _task_rank(task)
    if tr < 0:
        return False
    # Monitoring / completion tasks are never regressive.
    if agent == "analyst" and state == "EVOLUTION_ANALYZING":
        return False
    if agent == "__complete__":
        return False
    # Allow at most one step behind (e.g. BUG_FOUND repair while nominally QA_TESTING).
    return tr < pr - 1


def cancel_task(task: dict, now: float, *, reason: str) -> None:
    task["status"] = "cancelled"
    task["completed_at"] = now
    note = reason[:500]
    prev = (task.get("error") or "").strip()
    task["error"] = f"{prev}; {note}" if prev else note


def _stale_running_threshold_sec(
    agent_type: str,
    *,
    task: dict | None = None,
    product: dict | None = None,
) -> float:
    """Adaptive stale-running threshold.

    Long-running legitimate work (deep repair loops on a heavy product) should not be
    killed on the same fixed clock as a quick first attempt. The base threshold is:

      * agent-tuned (lightweight planning agents get the aggressive timeout),
      * scaled up with the task's retry_count (a task on its Nth retry is doing harder
        work — give it more headroom, capped),
      * overridable per product via ``stale_running_sec_override`` (operators can pin a
        longer timeout for a known-slow product without touching globals).
    """
    try:
        default = float(os.environ.get("AIFACTORY_STALE_RUNNING_SEC", "1200"))
        aggressive = float(os.environ.get("AIFACTORY_AGGRESSIVE_STALE_SEC", "600"))
    except ValueError:
        default, aggressive = 1200.0, 600.0

    base = (
        aggressive
        if str(agent_type or "").lower() in ("design_critic", "pm", "architect", "analyst")
        else default
    )


    # Per-product override wins outright when set to a positive value.
    if isinstance(product, dict):
        try:
            override = float(product.get("stale_running_sec_override") or 0)
        except (TypeError, ValueError):
            override = 0.0
        if override > 0:
            base = override

    # The floor is applied LAST, after the per-product override and the retry scaling. Applied
    # earlier it was simply overwritten: an override of 60 seconds reintroduced the bug by
    # another route, which my own test caught before this shipped.
    #
    # Never below the agent's OWN execute timeout. A task still inside its budget is not stale by
    # definition — the agent times out on its own and reports properly — and resetting it re-runs
    # work on a tree the first pass already rewrote. The developer's timeout is 1500s while this
    # threshold defaulted to 1200s, so every healthy 20-25 minute round was reset mid-flight.
    # Repair batching made that the normal case rather than the rare one: six sequential calls
    # land squarely in that band, and a live round was observed being reset right after producing
    # all six batches. The margin covers the writes, the static self-check and the rollbacks,
    # which all happen after the last generation returns.
    def _floor(value: float) -> float:
        try:
            from orchestrator.task_executor_agent import _agent_execute_timeout_sec

            return max(value, float(_agent_execute_timeout_sec(str(agent_type or ""))) + 300.0)
        except Exception:
            logger.debug(
                "stale threshold: agent timeout unavailable for %s", agent_type, exc_info=True
            )
            return value

    # Scale with retry_count: +50% per prior retry, capped at 3x so it can never grow
    # unbounded and strand a truly hung task forever.
    if isinstance(task, dict):
        try:
            retry_count = int(task.get("retry_count") or 0)
        except (TypeError, ValueError):
            retry_count = 0
        if retry_count > 0:
            base *= min(3.0, 1.0 + 0.5 * retry_count)

    return _floor(base)


def unstick_blocked_tasks(
    products: dict,
    task_queue: list,
    now: float | None = None,
) -> bool:
    """
    Cancel duplicate active tasks when stage already completed; reset long-running tasks;
    clear stuck design_critic on products already at DESIGN_CRITIQUED.
    """
    now = now if now is not None else time.time()
    changed = False
    by_pid: dict[str, list[dict]] = {}
    for task in task_queue:
        pid = task.get("product_id")
        if pid:
            by_pid.setdefault(str(pid), []).append(task)

    for pid, tasks in by_pid.items():
        product = products.get(pid) or {}
        pstate = str(product.get("state") or "").upper()
        completed_keys: set[tuple[str, str]] = set()
        for t in tasks:
            if str(t.get("status") or "").lower() == "completed":
                completed_keys.add(
                    (str(t.get("agent_type") or "").lower(), str(t.get("state") or "").upper())
                )

        for t in tasks:
            st = str(t.get("status") or "").lower()
            if st not in ("pending", "running"):
                continue
            key = (str(t.get("agent_type") or "").lower(), str(t.get("state") or "").upper())
            if key in completed_keys:
                cancel_task(t, now, reason="queue_hygiene: duplicate active after stage completed")
                changed = True
                logger.info("Cancelled duplicate %s/%s for %s", key[0], key[1], pid)

        if pstate == "DESIGN_CRITIQUED" and ("design_critic", "DESIGN_CRITIQUED") in completed_keys:
            for t in tasks:
                if str(t.get("agent_type") or "").lower() != "design_critic":
                    continue
                if str(t.get("status") or "").lower() in ("pending", "running"):
                    cancel_task(t, now, reason="queue_hygiene: design review already completed")
                    changed = True
                    logger.info("Cancelled redundant design_critic for %s (already critiqued)", pid)

        for t in tasks:
            if str(t.get("status") or "").lower() != "running":
                continue
            started = float(t.get("started_at") or 0)
            if started <= 0:
                continue
            age = now - started
            threshold = _stale_running_threshold_sec(
                str(t.get("agent_type") or ""), task=t, product=product
            )
            if age < threshold:
                continue
            t["status"] = "pending"
            t["started_at"] = None
            note = f"unstick: running {age:.0f}s >= {threshold:.0f}s"
            prev = (t.get("error") or "").strip()
            t["error"] = f"{prev}; {note}" if prev else note
            changed = True
            logger.info("Reset stale running %s/%s for %s (%.0fs)", t.get("agent_type"), t.get("state"), pid, age)

    return changed


def enforce_task_queue_hygiene(
    products: dict,
    task_queue: list,
    now: float | None = None,
) -> bool:
    """
    Per product: cancel regressive pending/running tasks; if multiple active remain,
    keep the forward-most (highest pipeline rank).
    """
    now = now if now is not None else time.time()
    changed = False
    by_product: dict[str, list[dict]] = {}
    for task in task_queue:
        if str(task.get("status") or "").lower() not in ("pending", "running"):
            continue
        pid = task.get("product_id")
        if not pid:
            continue
        by_product.setdefault(str(pid), []).append(task)

    for pid, active in by_product.items():
        product = products.get(pid) or {}
        pstate = str(product.get("state") or "").upper()

        for task in list(active):
            if is_regressive_task(pstate, task):
                cancel_task(task, now, reason="queue_hygiene: regressive task cancelled")
                active.remove(task)
                changed = True
                logger.info(
                    "Cancelled regressive %s/%s for %s (product state %s)",
                    task.get("agent_type"),
                    task.get("state"),
                    pid,
                    pstate,
                )

        active = [t for t in active if str(t.get("status") or "").lower() in ("pending", "running")]
        if len(active) <= 1:
            continue

        active.sort(key=lambda t: (_task_rank(t), float(t.get("created_at") or 0)), reverse=True)
        winner = active[0]
        for task in active[1:]:
            cancel_task(
                task,
                now,
                reason=f"queue_hygiene: duplicate active task (kept {winner.get('agent_type')}/{winner.get('state')})",
            )
            changed = True
            logger.info(
                "Deduped %s: dropped %s/%s, kept %s/%s",
                pid,
                task.get("agent_type"),
                task.get("state"),
                winner.get("agent_type"),
                winner.get("state"),
            )

    if unstick_blocked_tasks(products, task_queue, now):
        changed = True
    return changed


def append_product_task(
    task_queue: list,
    task: dict,
    products: dict,
    *,
    get_priority: Callable[[str], int] | None = None,
) -> bool:
    """
    Append a task after cancelling other active tasks on the same product.
    Returns False if the task is regressive and was skipped.
    """
    pid = task.get("product_id")
    if not pid:
        task_queue.append(task)
        return True
    product = products.get(pid) or {}
    pstate = str(product.get("state") or "").upper()
    if is_regressive_task(pstate, task):
        logger.warning(
            "Skipped regressive enqueue %s/%s for %s (product %s)",
            task.get("agent_type"),
            task.get("state"),
            pid,
            pstate,
        )
        return False
    now = time.time()
    for other in task_queue:
        if other is task:
            continue
        if other.get("product_id") != pid:
            continue
        if str(other.get("status") or "").lower() in ("pending", "running"):
            cancel_task(other, now, reason="queue_hygiene: superseded by new task")
    if get_priority is not None and "priority" not in task:
        task["priority"] = get_priority(str(task.get("agent_type") or ""))
    task_queue.append(task)
    return True


def ensure_sequential_next_task(
    products: dict,
    task_queue: list,
    product_id: str,
    create_next: Callable[[dict], dict | None],
) -> dict | None:
    """Create next pipeline task if none active; uses append_product_task."""
    product = products.get(product_id)
    if not product:
        return None
    has_active = any(
        t.get("product_id") == product_id
        and str(t.get("status") or "").lower() in ("pending", "running")
        for t in task_queue
    )
    if has_active:
        return None
    next_task = create_next(product)
    if not next_task:
        return None
    if append_product_task(task_queue, next_task, products):
        return next_task
    return None


def try_pm_spec_requeue(
    task: dict,
    products: dict,
    task_queue: list,
    get_priority: Callable[[str], int],
) -> bool:
    """Re-open PM after spec gate failure — only while product is still at/before spec stage."""
    import uuid

    from core.pipeline_retry_limits import pm_spec_auto_requeue_max, task_max_retries

    if task.get("agent_type") != "pm":
        return False
    error_text = (task.get("error") or "").lower()
    if "specification failed quality gate" not in error_text:
        return False
    pid = task.get("product_id")
    if not pid or pid not in products:
        return False

    product = products[pid]
    product_state = str(product.get("state") or "").upper()
    if not pm_spec_requeue_allowed(product_state):
        logger.info(
            "PM spec requeue skipped for %s: product already at %s",
            pid,
            product_state,
        )
        return False

    count = int(product.get("pm_spec_requeue_count") or 0)
    if count >= pm_spec_auto_requeue_max():
        return False

    # Cumulative-cost guard: even within the requeue-count cap, a product that has
    # already burned its LLM budget must not keep auto-requeuing PM (each requeue is
    # another full spec generation). Stop and let the budget guard terminalize it
    # rather than silently growing spend past the cap.
    try:
        from core.pipeline_cost_guard import check_product_budget

        within_budget, spent, cap = check_product_budget(str(pid))
        if not within_budget:
            logger.warning(
                "PM spec requeue skipped for %s: pipeline cost budget exhausted ($%.2f/$%.2f)",
                pid,
                spent,
                cap,
            )
            return False
    except Exception:
        logger.debug("PM spec requeue cost-guard check failed for %s", pid, exc_info=True)

    exists = any(
        t.get("product_id") == pid
        and t.get("agent_type") == "pm"
        and str(t.get("status") or "").lower() in ("pending", "running")
        for t in task_queue
    )
    if exists:
        return False

    product["pm_spec_requeue_count"] = count + 1
    product.pop("failure_reason", None)
    new_task = {
        "id": f"task-{uuid.uuid4().hex[:12]}",
        "product_id": pid,
        "agent_type": "pm",
        "state": "SPEC_WRITTEN",
        "status": "pending",
        "retry_count": 0,
        "max_retries": task_max_retries(),
        "input_data": {
            "product_id": pid,
            "idea": product.get("idea", ""),
            "admin_instructions": (
                "Auto-recovery: previous PM attempt failed the specification quality gate. "
                "Return complete JSON with testable acceptance_criteria for every user story; "
                "for full_software include detailed functional_requirements acceptance criteria."
            ),
        },
        "created_at": time.time(),
        "priority": get_priority("pm"),
        "auto_requeue_reason": "pm_spec_quality_gate",
    }
    if not append_product_task(task_queue, new_task, products, get_priority=get_priority):
        return False
    product["state"] = "MARKET_RESEARCHED"
    product["updated_at"] = time.time()
    return True


def requeue_pm_when_spec_absent(
    product_id: str,
    products: dict,
    task_queue: list,
    get_priority: Callable[[str], int],
    *,
    spec_loader: Callable[[str], dict],
) -> dict | None:
    """Refuse to start development with no specification, and re-run PM to get one.

    ``requeue_pm_after_spec_gate_failure`` above recovers the case the pipeline was
    designed for: PM ran, produced a spec, and the spec failed its quality gate. It keys
    off that gate's error text, which means it does not fire when PM never delivered at
    all — a **cancelled** PM task, for instance, leaves no error to match and no spec on
    disk, and the product sails on to the architect and the developer.

    That happened, and it is expensive rather than merely untidy. Every downstream gate
    that judges the build against its spec then compares against nothing: spec alignment
    reports "spec is empty" and blames the demo for inventing the product's own name, the
    acceptance-pack gate counts zero scenarios and demands two, and neither verdict can be
    satisfied by changing code. One product absorbed roughly seventy developer/QA rounds
    in that state before anyone looked at *why* the gates were unsatisfiable.

    So absence of the artifact is itself the trigger, checked at the last point before
    development. Bounded by the same requeue cap and the same cumulative cost guard as the
    gate-failure path — a spec that cannot be produced must terminate the product, not
    loop it.
    """
    import uuid

    from core.pipeline_retry_limits import pm_spec_auto_requeue_max, task_max_retries

    pid = str(product_id or "")
    if not pid or pid not in products:
        return None
    product = products[pid]

    try:
        spec = spec_loader(pid)
    except Exception:
        logger.debug("spec_loader failed for %s; treating spec as absent", pid, exc_info=True)
        spec = {}
    if _spec_has_substance(spec):
        return None

    return requeue_pm_bounded(
        pid,
        products,
        task_queue,
        get_priority,
        reason="spec_artifact_absent",
        instructions=(
            "Auto-recovery: this product reached the architecture stage with no "
            "specification on disk, so no downstream gate can judge the build. Write the "
            "full specification JSON now — product_name, description, core_features, "
            "functional_requirements and user_stories with testable acceptance_criteria."
        ),
    )


def requeue_pm_bounded(
    product_id: str,
    products: dict,
    task_queue: list,
    get_priority: Callable[[str], int],
    *,
    reason: str,
    instructions: str,
) -> dict | None:
    """Send a product back to PM once more, under the caps that stop this becoming a loop.

    Shared by every automatic reason for re-running PM — a missing spec artifact, a spec that
    dropped an operator requirement — because the guards are what make such a requeue safe
    and duplicating them is how one caller ends up without the cost check. The reason is
    recorded on the task so the requeues are distinguishable in the queue.
    """
    import uuid

    from core.pipeline_retry_limits import pm_spec_auto_requeue_max, task_max_retries

    pid = str(product_id or "")
    if not pid or pid not in products:
        return None
    product = products[pid]

    count = int(product.get("pm_spec_requeue_count") or 0)
    if count >= pm_spec_auto_requeue_max():
        logger.error(
            "PM requeue cap reached for %s (%d, reason=%s); leaving it for human review rather "
            "than looping — an unbounded retry is the failure this whole path exists to avoid.",
            pid,
            count,
            reason,
        )
        return None

    try:
        from core.pipeline_cost_guard import check_product_budget

        within_budget, spent, cap = check_product_budget(pid)
        if not within_budget:
            logger.warning(
                "PM requeue skipped for %s (reason=%s): cost budget exhausted ($%.2f/$%.2f)",
                pid,
                reason,
                spent,
                cap,
            )
            return None
    except Exception:
        logger.debug("PM requeue cost-guard check failed for %s", pid, exc_info=True)

    if any(
        t.get("product_id") == pid
        and t.get("agent_type") == "pm"
        and str(t.get("status") or "").lower() in ("pending", "running")
        for t in task_queue
    ):
        return None

    product["pm_spec_requeue_count"] = count + 1
    new_task = {
        "id": f"task-{uuid.uuid4().hex[:12]}",
        "product_id": pid,
        "agent_type": "pm",
        "state": "SPEC_WRITTEN",
        "status": "pending",
        "retry_count": 0,
        "max_retries": task_max_retries(),
        "input_data": {
            "product_id": pid,
            "idea": product.get("idea", ""),
            "admin_instructions": instructions,
        },
        "created_at": time.time(),
        "priority": get_priority("pm"),
        "auto_requeue_reason": reason,
    }
    # Rewind *before* enqueueing. ``append_product_task`` rejects a task that targets an
    # earlier stage than the product's current one, and a spec task is by definition earlier
    # than wherever this was noticed — so appending first would be refused as regressive and
    # the product would sail on with the defect, which is the exact bug. Restore the state if
    # the enqueue is refused for any other reason, so a failed recovery does not leave the
    # product silently rewound with nothing queued.
    previous_state = product.get("state")
    previous_repair_round = product.get("quality_repair_round")
    product["state"] = "MARKET_RESEARCHED"
    # Repair rounds spent under the old spec say nothing about the new one. A product that
    # burned twelve rounds against gates that could not pass — because there was no spec to
    # compare with — was two over the cap of ten, so its next QA failure would have
    # terminalized it as FAILED for rounds it was never given a fair chance to use. The
    # defect list those rounds produced described a build made from a different brief.
    product["quality_repair_round"] = 0
    if not append_product_task(task_queue, new_task, products, get_priority=get_priority):
        product["state"] = previous_state
        product["pm_spec_requeue_count"] = count
        product["quality_repair_round"] = previous_repair_round
        return None

    # A rewind that the reconciler undoes is not a rewind. Product state is re-derived from
    # task rows every cycle (``reconcile_all_products_from_tasks``), and a *completed* row
    # whose target outranks the spec stage puts the product straight back where it was — the
    # PM task is then regressive, queue hygiene cancels it, the product heals forward into
    # development without the spec it was sent back for, and the recovery attempt is spent.
    # Those rows are no longer true once the decision is to redo the spec, so retire them.
    # Cancelled rows are skipped by the reconciler; the spec-stage row we just queued is not
    # touched, since its own target is the state we want to land on.
    spec_rank = _STATE_RANK.get("SPEC_WRITTEN", 2)
    for row in task_queue:
        if row is new_task or row.get("product_id") != pid:
            continue
        if str(row.get("status") or "").lower() not in ("completed", "failed"):
            continue
        if state_rank(row.get("state")) < spec_rank:
            continue
        row["status"] = "cancelled"
        row["error"] = (
            f"superseded by a spec re-run (reason={reason}): this row claimed "
            f"{row.get('state')}, which the product no longer holds"
        )

    product["updated_at"] = time.time()
    logger.warning(
        "Re-queued PM for %s (reason=%s, attempt %d, rewound %s -> MARKET_RESEARCHED).",
        pid,
        reason,
        count + 1,
        previous_state,
    )
    return new_task


def missing_forward_task(product: dict, task_queue: list) -> dict | None:
    """If product has no active task, return the expected next task dict from PIPELINE_AGENT_FLOW."""
    import uuid

    pstate = str(product.get("state") or "").upper()
    if pstate in ("COMPLETED", "FAILED", "CANCELLED"):
        return None
    flow = PIPELINE_AGENT_FLOW.get(pstate)
    if not flow:
        return None
    agent_type, next_state = flow
    if pstate == "HUMAN_REVIEW_PENDING":
        from web.backend.services.product_followup import post_devops_human_review_approved

        pid_gate = str(product.get("id") or "")
        if agent_type == "__human_gate__" and not post_devops_human_review_approved(pid_gate):
            return None
        agent_type, next_state = "sales", "SALES_ACTIVE"
    pid = product.get("id")
    if not pid:
        return None
    if any(
        t.get("product_id") == pid
        and str(t.get("status") or "").lower() in ("pending", "running")
        for t in task_queue
    ):
        return None
    return {
        "id": f"task-{uuid.uuid4().hex[:12]}",
        "product_id": pid,
        "agent_type": agent_type,
        "state": next_state,
        "status": "pending",
        "retry_count": 0,
        "max_retries": 3,
        "input_data": {
            "product_id": pid,
            "idea": product.get("idea", ""),
        },
        "created_at": time.time(),
    }


# A product whose state disagrees with its own live task, or that holds a working
# state with nothing queued, makes no further progress on its own. Both shapes were
# produced by an operator reopen this session and each one parked a product until it
# was corrected by hand.
_WORKING_STATES = frozenset(
    {
        "BUG_FOUND",
        "DEV_FIXING",
        "CODE_READY",
        "TESTING",
        "ARCHITECTURE_READY",
        "METHODOLOGY_REVIEWED",
        "MARKET_RESEARCHED",
        "PLANNING",
        "DESIGNING",
        "SECURITY_REVIEW",
        "DEPLOYING",
    }
)

_TASK_STATE_TO_PRODUCT_STATE = {"DEV_FIXING": "BUG_FOUND"}


def stranded_since_seconds() -> float:
    raw = os.environ.get("AIFACTORY_STRANDED_PRODUCT_SEC", "1800").strip()
    try:
        return max(300.0, float(raw))
    except ValueError:
        return 1800.0


def reconcile_product_task_states(products: dict, task_queue: list, now: float) -> bool:
    """Realign products whose state no longer matches their own queue.

    Two shapes, both observed in production this session:

    * a live task exists but the product sits in an unrelated state — e.g. a human
      gate left over a running developer round. The completion then lands in a state
      the advance logic does not recognise and nothing is queued next.
    * the product holds a working state with no active task at all, for longer than
      any stage legitimately takes. It waits forever.

    The first is repaired here. The second is only reported: guessing the next stage
    risks running an agent twice, and a loud log is the honest response.
    """
    changed = False
    active_by_product: dict[str, list[dict]] = {}
    for task in task_queue:
        if str(task.get("status") or "").lower() not in ("running", "pending"):
            continue
        active_by_product.setdefault(str(task.get("product_id") or ""), []).append(task)

    for pid, product in list(products.items()):
        state = str(product.get("state") or "").upper()
        if state in ("COMPLETED", "FAILED", "CANCELLED"):
            continue
        active = active_by_product.get(pid) or []

        if active:
            task_state = str(active[0].get("state") or "").upper()
            expected = _TASK_STATE_TO_PRODUCT_STATE.get(task_state, task_state)
            if expected and state != expected and state == "HUMAN_REVIEW_PENDING":
                product["state"] = expected
                product["updated_at"] = now
                changed = True
                logger.warning(
                    "Realigned %s: %s → %s to match its live %s task",
                    pid,
                    state,
                    expected,
                    active[0].get("agent_type"),
                )
            continue

        if state in _WORKING_STATES:
            idle = now - float(product.get("updated_at") or now)
            if idle > stranded_since_seconds():
                logger.error(
                    "Product %s stranded: state %s with no active task for %.0f min — "
                    "needs an operator reopen at the correct stage",
                    pid,
                    state,
                    idle / 60.0,
                )
    return changed


# Last time each parked product's budget warning was emitted (module memory: see the note
# inside unpark_budget_exhausted about why this cannot live on the product dict).
_BUDGET_WARNED_AT: dict[str, float] = {}


# Products already reopened for a given rules version, so a sharper detector reopens each product
# once rather than on every worker pass.
_REOPENED_FOR_RULES: dict[str, int] = {}


def reopen_completed_with_critical_defects(products: dict, data_root=None) -> list[str]:
    """A finished product that today's detectors call broken goes back into repair.

    The case that forced this, measured end to end: a product reached nine green gates, published to
    Vercel, and was marked COMPLETED. Within the hour two new detectors landed and found, in that
    same tree, an import with no dependency behind it (`import jwt`, no PyJWT — every API route on
    the live deployment answered FUNCTION_INVOCATION_FAILED) and 47 Tailwind utility classes in a
    product with no Tailwind (the page rendered as unstyled HTML). Both critical, both true, and
    nothing looked at them: COMPLETED is terminal, and the verdict that produced it was measured
    under rules that could not see either defect.

    A gate that gets sharper must be allowed to reconsider what it already passed, or every
    improvement only applies to products built after it — and the ones already shipped keep their
    defects forever.

    Bounded deliberately: a product is reopened at most once per SCORING_RULES_VERSION, so a
    detector that keeps firing cannot spin the pipeline. If the repair fails, the next reopen waits
    for the next time the rules genuinely change.
    """
    import logging

    from core.round_regression_guard import SCORING_RULES_VERSION

    logger = logging.getLogger("pipeline-worker")
    reopened: list[str] = []

    for pid, product in list(products.items()):
        if not isinstance(product, dict):
            continue
        state = str(product.get("state") or "").upper()
        if state not in ("COMPLETED", "SALES_ACTIVE"):
            continue
        if _REOPENED_FOR_RULES.get(pid) == SCORING_RULES_VERSION:
            continue
        if product.get("last_reopen_rules_version") == SCORING_RULES_VERSION:
            _REOPENED_FOR_RULES[pid] = SCORING_RULES_VERSION
            continue

        try:
            from core.paths import code_dir as resolve_code_dir
            from web.backend.services.duplicate_module_check import run_duplicate_module_check

            code_root = resolve_code_dir(pid, data_root=data_root) if data_root else resolve_code_dir(pid)
            if not code_root.is_dir():
                continue
            health = run_duplicate_module_check(code_root)
        except Exception as exc:
            logger.debug("Reopen sweep could not measure %s: %s", pid, exc)
            continue

        criticals = [
            i for i in (health.get("issues") or [])
            if isinstance(i, dict) and i.get("severity") == "critical"
        ]
        if not criticals:
            _REOPENED_FOR_RULES[pid] = SCORING_RULES_VERSION
            product["last_reopen_rules_version"] = SCORING_RULES_VERSION
            continue

        codes = sorted({str(i.get("code")) for i in criticals})
        product["state"] = "BUG_FOUND"
        product["last_reopen_rules_version"] = SCORING_RULES_VERSION
        product["quality_repair_round"] = 0
        product["updated_at"] = _time.time()
        _REOPENED_FOR_RULES[pid] = SCORING_RULES_VERSION
        reopened.append(pid)
        logger.warning(
            "Reopening %s from %s: sharper detectors (rules %s) find %s critical defect(s) in the "
            "shipped tree — %s. A gate that gets sharper has to be allowed to reconsider what it "
            "already passed.",
            pid, state, SCORING_RULES_VERSION, len(criticals), ", ".join(codes),
        )
    return reopened


def unpark_budget_exhausted(products: dict) -> list[str]:
    """Resume budget-parked products the moment headroom exists, and never let a park go quiet.

    The failure this closes, measured: the LLM cap tripped at $11.0105 against $11.00, the product
    went to terminal ``FAILED``, its QA task was cancelled, and the worker looped "Factory on hold"
    every two seconds for 45 minutes — a log that looks alive and does nothing. Raising the cap
    resumed nothing, because the healer skips ``FAILED`` by design; a human had to notice and
    hand-edit the state.

    Two behaviours, both of which must live in the worker loop rather than in anyone's memory:

    * a parked product whose spend is back under the cap (the cap was raised, or the guard was
      disabled) is restored to the state it parked from and left for the idle-healer to requeue —
      the same proven path that requeues any idle product;
    * a parked product still over the cap is shouted about every ten minutes at WARNING, with the
      numbers and the fix, so a park can never again be something a human discovers by absence.
    """
    import logging
    import time as _time

    logger = logging.getLogger("pipeline-worker")
    unparked: list[str] = []
    try:
        from core.pipeline_cost_guard import (
            effective_max_pipeline_cost_usd,
            pipeline_cost_guard_enabled,
            product_spend_usd,
        )
    except Exception:
        return unparked

    for pid, product in list(products.items()):
        if not isinstance(product, dict):
            continue
        reason = str(product.get("failure_reason") or "")
        parked = bool(product.get("budget_parked")) or (
            str(product.get("state") or "").upper() == "FAILED"
            and "LLM budget exceeded" in reason
        )
        if not parked:
            continue
        try:
            cap = float(effective_max_pipeline_cost_usd()) if pipeline_cost_guard_enabled() else 0.0
            spent = float(product_spend_usd(pid))
        except Exception:
            continue
        if cap > 0 and spent >= cap:
            # Throttled in module memory, not on the product. The timestamp was stored as
            # product["_budget_park_warned_at"], a key that is not in PRODUCT_EXTRA_KEYS — so under
            # SQLite it was dropped on every save, the throttle never saw its own previous value,
            # and the warning fired on every worker pass: ~30 lines a second for four hours, in a
            # log on a disk that had already filled up once tonight. A warning nobody can read is
            # not a warning.
            last = float(_BUDGET_WARNED_AT.get(pid) or 0.0)
            if _time.time() - last > 600:
                _BUDGET_WARNED_AT[pid] = _time.time()
                logger.warning(
                    "PARKED ON BUDGET: %s spent $%.4f of $%.2f — raise "
                    "AIFACTORY_MAX_PIPELINE_COST_USD or the admin cap and it resumes by itself.",
                    pid, spent, cap,
                )
            continue
        prior = str(product.get("state_before_budget_park") or "DEV_FIXING")
        product["state"] = prior
        product["budget_parked"] = False
        product.pop("failure_reason", None)
        product.pop("_budget_park_warned_at", None)
        product["updated_at"] = _time.time()
        logger.warning(
            "Budget headroom restored for %s ($%.4f of $%.2f) — resumed at %s; the idle-healer "
            "will requeue the next task.",
            pid, spent, cap if cap > 0 else float("inf"), prior,
        )
        unparked.append(pid)
    return unparked
