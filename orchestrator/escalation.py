"""
Escalation Handler
==================
Handles error recovery, task restarts, and escalation procedures.
When an agent fails or times out, this module determines the appropriate action.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from core.logging_utils import log_suppressed

logger = logging.getLogger(__name__)

from typing import TYPE_CHECKING

from core.paths import escalations_log_path

if TYPE_CHECKING:
    from .state_machine import PipelineStateMachine

ESCALATION_LOG_FILE = str(escalations_log_path())


class EscalationHandler:
    """
    Handles task failures and determines recovery actions.
    
    Escalation levels:
    1. Retry: Simple retry with same parameters
    2. Restart: Restart the task from scratch
    3. Escalate: Mark as failed and notify admin
    4. Bypass: Skip the failed step and continue
    """

    def __init__(self, state_machine: PipelineStateMachine):
        self.state_machine = state_machine
        self._escalation_log: list[dict] = []
        self._load_log()

    def _load_log(self):
        """Load escalation log from persistent file."""
        log_file = Path(ESCALATION_LOG_FILE)
        if log_file.exists():
            try:
                with open(log_file) as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                self._escalation_log.append(json.loads(line))
                            except json.JSONDecodeError as _suppressed_exc:
                                log_suppressed(logger, "non-fatal (orchestrator/escalation.py)", exc_info=_suppressed_exc)
                # Keep only last 1000 entries
                if len(self._escalation_log) > 1000:
                    self._escalation_log = self._escalation_log[-1000:]
            except Exception as e:
                logger.error(f"Failed to load escalation log: {e}")

    def _persist_entry(self, entry: dict):
        """Append a single escalation entry to the persistent log file."""
        try:
            log_file = Path(ESCALATION_LOG_FILE)
            log_file.parent.mkdir(parents=True, exist_ok=True)
            with open(log_file, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            logger.error(f"Failed to persist escalation entry: {e}")

    def handle_failure(self, task_id: str, error: str, agent_type: str) -> str:
        """
        Handle a task failure and determine the action.
        
        Returns:
            Action taken: "retry", "restart", "escalate", or "bypass"
        """
        task = self._find_task(task_id)
        if not task:
            return "escalate"

        entry = {
            "timestamp": time.time(),
            "task_id": task_id,
            "agent_type": agent_type,
            "error": error,
            "retry_count": task.retry_count if task else 0,
            "max_retries": task.max_retries if task else 0,
            "action_taken": "",
        }

        # fail_task owns retry_count / PENDING vs FAILED. Decide the label from
        # the post-state so we never claim "retry" when the last attempt was spent.
        from .state_machine import TaskStatus

        if task.retry_count < task.max_retries:
            self.state_machine.fail_task(task_id, error)
            refreshed = self._find_task(task_id)
            if refreshed is not None and refreshed.status == TaskStatus.PENDING:
                entry["action_taken"] = "retry"
                entry["retry_count"] = refreshed.retry_count
                logger.info(
                    "Retrying task %s (%s/%s)",
                    task_id,
                    refreshed.retry_count,
                    refreshed.max_retries,
                )
                action = "retry"
            elif agent_type in {"marketing", "sales", "evolution_analyst"}:
                entry["action_taken"] = "bypass"
                logger.warning(
                    "Bypassing failed task %s for non-critical agent %s (retries exhausted)",
                    task_id,
                    agent_type,
                )
                self.state_machine.complete_task(task_id, {"bypassed": True, "error": error})
                action = "bypass"
            else:
                entry["action_taken"] = "escalate"
                logger.error(
                    "Escalating failed task %s for critical agent %s (retries exhausted)",
                    task_id,
                    agent_type,
                )
                action = "escalate"

        elif agent_type in {"marketing", "sales", "evolution_analyst"}:
            entry["action_taken"] = "bypass"
            logger.warning(f"Bypassing failed task {task_id} for non-critical agent {agent_type}")
            self.state_machine.complete_task(task_id, {"bypassed": True, "error": error})
            action = "bypass"

        else:
            entry["action_taken"] = "escalate"
            logger.error(f"Escalating failed task {task_id} for critical agent {agent_type}")
            self.state_machine.fail_task(task_id, error)
            action = "escalate"

        # Log and persist
        self._escalation_log.append(entry)
        self._persist_entry(entry)

        return action

    def handle_timeout(self, task_id: str) -> str:
        """Handle a task timeout."""
        task = self._find_task(task_id)
        if not task:
            return "escalate"

        logger.warning(f"Task {task_id} timed out (agent: {task.agent_type})")
        return self.handle_failure(task_id, "Task timed out (>30s no response)", task.agent_type)

    def get_escalation_log(self, limit: int = 50) -> list[dict]:
        """Get recent escalation events."""
        return self._escalation_log[-limit:]

    def get_agent_failure_rate(self, agent_type: str, window_hours: int = 1) -> float:
        """Calculate failure rate for an agent type."""
        cutoff = time.time() - (window_hours * 3600)
        
        relevant = [
            e for e in self._escalation_log
            if e["agent_type"] == agent_type
        ]
        
        if not relevant:
            return 0.0
        
        recent = [e for e in relevant if e.get("timestamp", 0) >= cutoff]
        return len(recent) / max(len(relevant), 1)

    def get_summary(self) -> dict:
        """Get a summary of recent escalation activity."""
        now = time.time()
        one_hour_ago = now - 3600
        
        recent = [e for e in self._escalation_log if e.get("timestamp", 0) >= one_hour_ago]
        
        by_agent = {}
        for e in recent:
            agent = e.get("agent_type", "unknown")
            if agent not in by_agent:
                by_agent[agent] = {"total": 0, "retries": 0, "bypasses": 0, "escalations": 0}
            by_agent[agent]["total"] += 1
            action = e.get("action_taken", "")
            if action == "retry":
                by_agent[agent]["retries"] += 1
            elif action == "bypass":
                by_agent[agent]["bypasses"] += 1
            elif action == "escalate":
                by_agent[agent]["escalations"] += 1
        
        return {
            "total_escalations": len(self._escalation_log),
            "recent_1h": len(recent),
            "by_agent": by_agent,
            "recent_events": recent[-20:],
        }

    def _find_task(self, task_id: str):
        """Find a task in the state machine."""
        for task in self.state_machine.task_queue:
            if task.id == task_id:
                return task
        return None
