"""Phase 4c: a mid-pipeline product with no live task is stuck forever unless someone
queues its next step. This is that someone.

Split out of ``pipeline_worker.py``. Like the dispatcher it does no IO and no saving —
it appends to the task queue it is handed and reports which products and tasks it touched,
so the caller can persist exactly those.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# States that are not "mid-pipeline": terminal ones, plus IDEA_RECEIVED, which Phase 1 owns.
# The ONLY definition of this rule. A second copy lived in worker_task_planner.py, unread —
# the shape where adding a fifth state to the constant that documents itself as owning the
# rule changes nothing at all.
TERMINAL_STATES = ("COMPLETED", "FAILED", "CANCELLED", "IDEA_RECEIVED")
ACTIVE_TASK_STATUSES = ("pending", "running")


def _default_on_hold(product_id: str) -> bool:
    """Improvement hold + product pipeline pause, either of which means "leave it alone"."""
    try:
        from core.pipeline_product_pause import is_product_pipeline_work_paused
        from web.backend.services.product_followup import is_product_improvement_on_hold

        return bool(is_product_improvement_on_hold(product_id)) or bool(
            is_product_pipeline_work_paused(product_id)
        )
    except Exception:  # noqa: BLE001 - a failed hold lookup must not wedge the pipeline
        logger.debug("hold probe failed for %s", product_id, exc_info=True)
        return False


def _default_append(task_queue: list, task: dict, products: dict, get_priority) -> bool:
    from orchestrator.task_queue_hygiene import append_product_task

    return bool(append_product_task(task_queue, task, products, get_priority=get_priority))


@dataclass
class HealOutcome:
    healed_product_ids: set[str] = field(default_factory=set)
    healed_task_ids: set[str] = field(default_factory=set)

    @property
    def changed(self) -> bool:
        return bool(self.healed_product_ids)


class IdleProductHealer:
    """Queues the next sequential step for products that fell idle mid-pipeline."""

    def __init__(
        self,
        *,
        create_next_task: Callable[[dict], Optional[dict]],
        get_priority: Callable[[str], int],
        on_hold: Callable[[str], bool] | None = None,
        append_task=None,
    ) -> None:
        self._create_next_task = create_next_task
        self._get_priority = get_priority
        self._on_hold = on_hold or _default_on_hold
        self._append_task = append_task or _default_append

    @staticmethod
    def _has_active_task(task_queue: list, product_id: str) -> bool:
        return any(
            task.get("product_id") == product_id
            and str(task.get("status") or "").lower() in ACTIVE_TASK_STATUSES
            for task in task_queue
        )

    def heal(self, products: dict, task_queue: list) -> HealOutcome:
        outcome = HealOutcome()
        for product_id, product in list(products.items()):
            if self._on_hold(product_id):
                continue
            state = str(product.get("state") or "").upper()
            if state in TERMINAL_STATES:
                continue
            if self._has_active_task(task_queue, product_id):
                continue
            next_task = self._create_next_task(product)
            if not next_task:
                continue
            if not self._append_task(task_queue, next_task, products, self._get_priority):
                continue
            outcome.healed_product_ids.add(product_id)
            task_id = next_task.get("id")
            if task_id:
                outcome.healed_task_ids.add(str(task_id))
            logger.info(
                "Healed idle product %s at %s: queued %s -> %s",
                product_id,
                state,
                next_task.get("agent_type"),
                next_task.get("state"),
            )
        return outcome
