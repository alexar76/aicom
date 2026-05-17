"""
Timeout Manager
===============
Monitors task execution time and triggers timeout handling.
If an agent is silent for >30 seconds, the task is restarted or failed.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Callable, Optional
from core.logging_utils import log_suppressed

logger = logging.getLogger(__name__)


class TimeoutManager:
    """
    Manages timeouts for agent tasks.
    
    Features:
    - Per-task timeout tracking
    - Configurable timeout per agent type
    - Callback on timeout (restart or fail)
    - Grace period for long-running tasks
    """

    def __init__(self, default_timeout_sec: int = 30):
        self.default_timeout_sec = default_timeout_sec
        self._timeouts: dict[str, float] = {}  # task_id -> deadline
        self._callbacks: dict[str, Callable] = {}
        self._agent_timeouts: dict[str, int] = {
            "pm": 200,
            "architect": 260,
            "developer": 320,
            "qa": 200,
            "devops": 130,
            "marketing": 130,
            "sales": 130,
            "evolution_analyst": 130,
            "methodologist": 60,
        }
        self._running = False
        self._monitor_task: Optional[asyncio.Task] = None

    def start_task(self, task_id: str, agent_type: str, callback: Callable, custom_timeout: Optional[int] = None):
        """Start tracking a task with timeout."""
        timeout = custom_timeout or self._agent_timeouts.get(agent_type, self.default_timeout_sec)
        deadline = time.time() + timeout
        self._timeouts[task_id] = deadline
        self._callbacks[task_id] = callback
        logger.debug(f"Started timeout tracking for {task_id} ({agent_type}, {timeout}s)")

    def complete_task(self, task_id: str):
        """Stop tracking a completed task."""
        self._timeouts.pop(task_id, None)
        self._callbacks.pop(task_id, None)

    def extend_timeout(self, task_id: str, extra_seconds: int = 30):
        """Extend the timeout for a running task."""
        if task_id in self._timeouts:
            self._timeouts[task_id] += extra_seconds
            logger.debug(f"Extended timeout for {task_id} by {extra_seconds}s")

    def set_agent_timeout(self, agent_type: str, timeout_sec: int):
        """Update timeout for an agent type."""
        self._agent_timeouts[agent_type] = timeout_sec
        logger.info(f"Updated timeout for {agent_type}: {timeout_sec}s")

    async def start_monitoring(self, check_interval: float = 1.0):
        """Start the timeout monitoring loop."""
        self._running = True
        self._monitor_task = asyncio.create_task(self._monitor_loop(check_interval))
        logger.info("Timeout monitoring started")

    async def stop_monitoring(self):
        """Stop the timeout monitoring loop."""
        self._running = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError as _suppressed_exc:
                log_suppressed(logger, "non-fatal (orchestrator/timeout_manager.py)", exc_info=_suppressed_exc)
        logger.info("Timeout monitoring stopped")

    async def _monitor_loop(self, check_interval: float):
        """Periodically check for timed-out tasks."""
        while self._running:
            now = time.time()
            timed_out = [
                task_id for task_id, deadline in self._timeouts.items()
                if now >= deadline
            ]

            for task_id in timed_out:
                callback = self._callbacks.get(task_id)
                if callback:
                    logger.warning(f"Task {task_id} timed out, triggering callback")
                    try:
                        if asyncio.iscoroutinefunction(callback):
                            await callback(task_id)
                        else:
                            callback(task_id)
                    except Exception as e:
                        logger.error(f"Timeout callback failed for {task_id}: {e}")
                
                self._timeouts.pop(task_id, None)
                self._callbacks.pop(task_id, None)

            await asyncio.sleep(check_interval)

    def get_active_timeouts(self) -> dict[str, float]:
        """Get all active timeouts with remaining time."""
        now = time.time()
        return {
            task_id: max(0, deadline - now)
            for task_id, deadline in self._timeouts.items()
        }

    def get_agent_timeouts(self) -> dict[str, int]:
        """Get current timeout settings per agent."""
        return dict(self._agent_timeouts)
