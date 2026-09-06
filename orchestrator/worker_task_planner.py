"""What task a product needs next — the pipeline's single answer to that question.

Lifted out of ``pipeline_worker.py`` unchanged. It sat there as four private methods on a
1180-line worker, which made the most rule-dense part of the pipeline reachable only through a
running worker with state, a queue and an event loop. Nothing here needs any of that: given a
product dict, the answer is a pure function of the flow table plus a handful of gates.

The gates are the reason this is worth naming. Three of them look like ordinary branches and are
each a bug that reached production:

* a repair-loop park is NOT the post-devops sales gate. A product parked at
  ``HUMAN_REVIEW_PENDING`` after exhausting QA repairs already carried an approval from an
  earlier pass, so idle-healing read it as "approved → sales" and bounced it straight back into
  QA. It stays parked until an operator grants another repair cycle.
* the landing fast path completes at ``TELEMETRY_COLLECTING`` instead of continuing, and that has
  to be decided before the flow table is consulted, not after.
* ``BUG_FOUND`` hands the developer the bug context. Losing it turns a targeted fix into a guess.
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any, Optional

from agents.product_profile import post_devops_human_gate_required
from orchestrator.landing_fast_flow import agent_flow_for_product
from orchestrator.worker_utils import delivery_profile_from_product_dict

#: Lower runs first. Kept as one table so "which agent goes first" has a single answer — the
#: queue helper, the orchestrator and the healer all read it through `priority()`.
AGENT_PRIORITIES: dict[str, int] = {
    "__complete__": 0,
    "analyst": 1,
    "pm": 2,
    "marketing": 3,
    "methodologist": 4,
    "architect": 5,
    "landing_architect": 5,
    "developer": 6,
    "landing_developer": 6,
    "design_critic": 6,
    "hardening": 6,
    "qa": 7,
    "security": 7,
    "devops": 8,
    "sales": 9,
    "evolution_analyst": 10,
}
DEFAULT_PRIORITY = 5

#: A park an operator has to lift. These are repair loops that ran out of attempts, not the
#: post-devops sales gate — telling them apart is what stops a parked product being bounced back
#: into the loop that just exhausted itself.
_REPAIR_PARK_KINDS = frozenset({
    "qa_repair_exhausted", "security_repair_exhausted", "qa_repair_stuck", "live_mesh_payment_ops",
    # A product whose stage kills the worker process itself. Parked by
    # TaskOrchestrator.adopt_orphaned_running_tasks once the crash ladder runs out.
    "crash_loop_parked",
})

MAX_BUG_CONTEXT_CHARS = 8000


def priority(agent_type: str) -> int:
    return AGENT_PRIORITIES.get(agent_type, DEFAULT_PRIORITY)


def latest_bug_context(product: dict[str, Any]) -> str:
    """Compact bug summary for developer/QA fix tasks (from ``product.last_bug_context``)."""
    lb = product.get("last_bug_context")
    if not isinstance(lb, dict) or not lb:
        return ""
    try:
        return json.dumps(lb, ensure_ascii=False, default=str)[:MAX_BUG_CONTEXT_CHARS]
    except (TypeError, ValueError):
        return str(lb)[:MAX_BUG_CONTEXT_CHARS]


class NextTaskPlanner:
    """Decides the next task for a product. Holds no state; safe to share."""

    def priority(self, agent_type: str) -> int:
        return priority(agent_type)

    def latest_bug_context(self, product: dict[str, Any]) -> str:
        return latest_bug_context(product)

    def create_next_task(self, product: dict[str, Any]) -> Optional[dict[str, Any]]:
        """Create the next task based on current product state."""
        from core.delivery_profile import MARKETING_LANDING

        current_state = product.get("state", "")
        if (current_state == "TELEMETRY_COLLECTING"
                and delivery_profile_from_product_dict(product) == MARKETING_LANDING):
            return {
                "id": f"task-{uuid.uuid4().hex[:12]}",
                "product_id": product["id"],
                "agent_type": "__complete__",
                "state": "COMPLETED",
                "status": "pending",
                "retry_count": 0,
                "max_retries": 3,
                "input_data": {
                    "product_id": product["id"],
                    "idea": product.get("idea", ""),
                    "landing_fast_path": True,
                },
                "created_at": time.time(),
                "priority": self.priority("__complete__"),
            }

        next_info = agent_flow_for_product(product).get(current_state)
        if not next_info:
            return None

        agent_type, next_state = next_info
        if current_state == "HUMAN_REVIEW_PENDING":
            from web.backend.services.product_followup import post_devops_human_review_approved

            kind = str(product.get("human_review_kind") or "").strip().lower()
            if kind in _REPAIR_PARK_KINDS:
                # A repair-loop park is not the post-devops sales gate. Sentinel already had
                # post_devops_human_review_approved_at from an earlier pass, so idle-heal
                # treated HUMAN_REVIEW_PENDING as "approved → sales" and bounced it back
                # into QA/DEV. Stay parked until an operator grants another repair cycle.
                return None
            if agent_type == "__human_gate__" and not post_devops_human_review_approved(
                str(product.get("id") or "")
            ):
                return None
            agent_type, next_state = "sales", "SALES_ACTIVE"
        if current_state == "SECURITY_SCANNED" and agent_type == "devops":
            from web.backend.services.product_followup import post_devops_human_review_approved

            if post_devops_human_gate_required(product) and not post_devops_human_review_approved(
                str(product.get("id") or "")
            ):
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
            "priority": self.priority(agent_type),
        }
        if current_state == "BUG_FOUND" and agent_type in ("developer", "landing_developer"):
            bug_context = self.latest_bug_context(product)
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
