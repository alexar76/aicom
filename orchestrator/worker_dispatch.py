"""Phase 3 of the pipeline cycle: run this cycle's `running` tasks through the agents.

Split out of ``pipeline_worker.py`` so the concurrency bound, the pause sweep and the
"one failing task must not abort the cycle" rule can be tested without a worker, a
state file or an event loop full of agents.

Nothing here does IO or touches persistence: the caller owns the state dict and decides
when to save. The dispatcher only mutates task rows it is told to (paused ``running`` →
``pending``) and reports what happened.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Iterable

logger = logging.getLogger(__name__)


def _default_is_paused(product_id: str) -> bool:
    """Product-level pipeline pause. Imported late: the module pulls in app config."""
    try:
        from core.pipeline_product_pause import is_product_pipeline_work_paused

        return bool(is_product_pipeline_work_paused(product_id))
    except Exception:  # noqa: BLE001 - a pause lookup that fails must not stop the pipeline
        logger.debug("pipeline pause probe failed for %s", product_id, exc_info=True)
        return False


def _default_before_task(product_id: str) -> None:
    """Warn when the product's code tree is not writable — a silent no-op build otherwise."""
    try:
        from core.code_tree_ownership import warn_if_product_code_unwritable

        warn_if_product_code_unwritable(product_id)
    except Exception:  # noqa: BLE001
        logger.debug("code tree ownership probe failed", exc_info=True)


@dataclass
class DispatchOutcome:
    """What one Phase 3 pass did. `changed` is what the caller persists on."""

    dispatched: int = 0
    paused_back: int = 0
    errors: list[BaseException] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return bool(self.dispatched or self.paused_back)


class TaskDispatcher:
    """Bounded-concurrency runner for the tasks a cycle found in `running`."""

    def __init__(
        self,
        *,
        concurrency: Callable[[], int],
        is_paused: Callable[[str], bool] | None = None,
        before_task: Callable[[str], None] | None = None,
    ) -> None:
        self._concurrency = concurrency
        self._is_paused = is_paused or _default_is_paused
        self._before_task = before_task or _default_before_task

    def release_paused(self, task_queue: Iterable[dict]) -> int:
        """Put `running` tasks of paused products back to `pending`.

        Done before the run rather than inside it: a task that is about to be skipped must
        not stay `running`, or the stale-running recovery reaps it as a crash next cycle.
        """
        released = 0
        for task in task_queue:
            if str(task.get("status") or "").lower() != "running":
                continue
            product_id = str(task.get("product_id") or "")
            if product_id and self._is_paused(product_id):
                task["status"] = "pending"
                task.pop("started_at", None)
                released += 1
        return released

    def runnable(self, task_queue: Iterable[dict]) -> list[dict]:
        return [
            task
            for task in task_queue
            if task.get("status") == "running"
            and not self._is_paused(str(task.get("product_id") or ""))
        ]

    async def dispatch(
        self,
        task_queue: Iterable[dict],
        run_task: Callable[[dict], Awaitable[None]],
    ) -> DispatchOutcome:
        outcome = DispatchOutcome(paused_back=self.release_paused(task_queue))
        running = self.runnable(task_queue)
        if not running:
            return outcome

        semaphore = asyncio.Semaphore(max(1, int(self._concurrency())))

        async def _run_one(task: dict) -> None:
            async with semaphore:
                self._before_task(str(task.get("product_id") or ""))
                await run_task(task)

        results = await asyncio.gather(
            *(_run_one(task) for task in running), return_exceptions=True
        )
        for task, result in zip(running, results):
            if isinstance(result, BaseException):
                outcome.errors.append(result)
                logger.error(
                    "Phase 3 task %s failed: %s", task.get("id"), result, exc_info=result
                )
        if outcome.errors:
            # One agent blowing up must not cost the other tasks their cycle: the retry
            # ladder only runs if we come back and finish.
            logger.error(
                "Phase 3: %d task(s) raised; continuing cycle so retries can run",
                len(outcome.errors),
            )
        outcome.dispatched = len(running)
        return outcome
