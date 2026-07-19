"""
Director Integration
====================
Bridge between the Orchestrator and Director AI.
Receives decisions from Director and applies them to the pipeline.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from pathlib import Path
from typing import TYPE_CHECKING

from core.paths import director_decisions_path

if TYPE_CHECKING:
    from .state_machine import PipelineStateMachine
    from .timeout_manager import TimeoutManager

logger = logging.getLogger(__name__)


class DirectorIntegration:
    """
    Integrates Director AI decisions into the pipeline.
    
    Director AI does NOT directly command agents.
    It influences through:
    - Configuration changes (timeouts, priorities)
    - Creating tasks for PM/Marketing
    - Recommendations in the admin panel
    """

    def __init__(
        self,
        state_machine: PipelineStateMachine,
        timeout_manager: TimeoutManager,
        decisions_path: str | Path | None = None,
    ):
        self.state_machine = state_machine
        self.timeout_manager = timeout_manager
        self.decisions_path = str(decisions_path or director_decisions_path())
        self.db_path = self._resolve_db_path(decisions_path)
        self._conn: sqlite3.Connection | None = None
        self._pending_decisions: list[dict] = []
        self._applied_decisions: list[dict] = []
        self._init_storage()
        self._load_decisions()

    @staticmethod
    def _resolve_db_path(decisions_path: str) -> str:
        p = Path(decisions_path)
        if p.suffix.lower() == ".json":
            return str(p.with_suffix(".db"))
        return str(p.parent / "director_decisions.db")

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            p = Path(self.db_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(p))
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def _init_storage(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS director_decisions (
                id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                payload TEXT NOT NULL,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )
            """
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_director_decisions_status ON director_decisions(status)"
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_director_decisions_updated_at ON director_decisions(updated_at DESC)"
        )
        self.conn.commit()
        self._migrate_legacy_json()

    def _migrate_legacy_json(self) -> None:
        legacy = Path(self.decisions_path)
        if not legacy.exists() or legacy.suffix.lower() != ".json":
            return
        existing = self.conn.execute("SELECT COUNT(*) AS cnt FROM director_decisions").fetchone()["cnt"]
        if existing > 0:
            return
        try:
            with open(legacy) as f:
                data = json.load(f)
            now = time.time()
            for status, items in (("pending", data.get("pending", [])), ("applied", data.get("applied", []))):
                for d in items:
                    did = str(d.get("id") or f"legacy-{int(now*1000)}")
                    created_at = float(d.get("created_at") or d.get("applied_at") or d.get("approved_at") or now)
                    updated_at = float(d.get("applied_at") or d.get("approved_at") or d.get("rejected_at") or now)
                    self.conn.execute(
                        """
                        INSERT OR REPLACE INTO director_decisions (id, status, payload, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (did, status, json.dumps(d), created_at, updated_at),
                    )
            self.conn.commit()
        except Exception as e:
            logger.warning("Legacy director decisions migration failed: %s", e)

    def apply_decision(self, decision: dict) -> bool:
        """
        Apply a Director AI decision to the pipeline.
        
        Decision format:
        {
            "action": "increase_agent_timeout",
            "target": "developer",
            "new_value": 45,
            "reason": "...",
            "requires_approval": False
        }
        """
        action = decision.get("action")
        target = decision.get("target")
        
        try:
            if action == "increase_agent_timeout":
                new_timeout = decision.get("new_value", 45)
                self.timeout_manager.set_agent_timeout(target, new_timeout)
                logger.info(f"Director: Increased {target} timeout to {new_timeout}s")

            elif action == "switch_provider_fallback":
                logger.info(f"Director: Switching {target} to fallback provider")
                # This is handled by the LLM Router

            elif action == "adjust_agent_priority":
                new_priority = decision.get("new_value", 5)
                logger.info(f"Director: Adjusted {target} priority to {new_priority}")
                # Priority changes affect task queue ordering

            elif action == "trigger_marketing_review":
                # This action would enqueue autonomous pipeline work (a marketing task).
                # Honor the factory soft hold so Director-driven enqueues do not grow the
                # backlog while the factory is paused — consistent with the worker-side and
                # Discovery auto-enqueue hold gating. On-demand (human-requested) builds use
                # a different path and are unaffected.
                from core.factory_hold import is_factory_on_hold

                if is_factory_on_hold():
                    logger.info(
                        "Director: marketing review enqueue skipped — factory on hold (%s)",
                        decision.get("task", ""),
                    )
                    return False
                task_desc = decision.get("task", "")
                logger.info(f"Director: Creating marketing task: {task_desc}")
                # Create a task for the marketing agent

            elif action == "recommend_switch_to_local":
                logger.info(f"Director recommendation: {decision.get('message', '')}")
                # This is a recommendation, logged for admin review

            else:
                logger.warning(f"Unknown Director action: {action}")
                return False

            # Record the decision
            now = time.time()
            decision.setdefault("created_at", now)
            decision["applied_at"] = time.time()
            decision["status"] = "applied" if not decision.get("requires_approval") else "pending"
            
            if decision.get("requires_approval"):
                self._pending_decisions.append(decision)
            else:
                self._applied_decisions.append(decision)

            self._save_decisions()
            return True

        except Exception as e:
            logger.error(f"Failed to apply Director decision: {e}")
            return False

    def get_pending_decisions(self) -> list[dict]:
        """Get decisions awaiting admin approval."""
        return list(self._pending_decisions)

    def approve_decision(self, decision_id: str) -> bool:
        """Approve a pending decision."""
        for i, d in enumerate(self._pending_decisions):
            if d.get("id") == decision_id:
                decision = self._pending_decisions.pop(i)
                decision["status"] = "approved"
                decision["approved_at"] = time.time()
                # Prevent re-queuing back into pending during apply_decision.
                decision["requires_approval"] = False
                return self.apply_decision(decision)
        return False

    def reject_decision(self, decision_id: str) -> bool:
        """Reject a pending decision."""
        for i, d in enumerate(self._pending_decisions):
            if d.get("id") == decision_id:
                decision = self._pending_decisions.pop(i)
                decision["status"] = "rejected"
                decision["rejected_at"] = time.time()
                self._applied_decisions.append(decision)
                self._save_decisions()
                return True
        return False

    def get_recent_decisions(self, limit: int = 20) -> list[dict]:
        """Get recent decisions (applied + pending)."""
        all_decisions = self._applied_decisions + self._pending_decisions
        all_decisions.sort(key=lambda d: d.get("applied_at") or d.get("created_at", 0) or d.get("approved_at", 0), reverse=True)
        return all_decisions[:limit]

    def _load_decisions(self):
        """Load decisions from SQLite storage."""
        try:
            rows = self.conn.execute(
                "SELECT status, payload FROM director_decisions ORDER BY updated_at DESC"
            ).fetchall()
            pending: list[dict] = []
            applied: list[dict] = []
            for row in rows:
                payload = json.loads(row["payload"])
                if row["status"] == "pending":
                    pending.append(payload)
                else:
                    applied.append(payload)
            self._pending_decisions = pending
            self._applied_decisions = applied
        except Exception as e:
            logger.error(f"Failed to load decisions: {e}")

    def _save_decisions(self):
        """Save decisions to SQLite storage."""
        try:
            now = time.time()
            all_rows: list[tuple[str, str, str, float, float]] = []
            for d in self._pending_decisions:
                did = str(d.get("id") or f"pending-{int(now*1000)}")
                created_at = float(d.get("created_at") or d.get("applied_at") or now)
                all_rows.append((did, "pending", json.dumps(d), created_at, now))
            for d in self._applied_decisions:
                did = str(d.get("id") or f"applied-{int(now*1000)}")
                created_at = float(d.get("created_at") or d.get("applied_at") or d.get("approved_at") or now)
                all_rows.append((did, "applied", json.dumps(d), created_at, now))
            self.conn.execute("DELETE FROM director_decisions")
            self.conn.executemany(
                """
                INSERT OR REPLACE INTO director_decisions (id, status, payload, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                all_rows,
            )
            self.conn.commit()
        except Exception as e:
            try:
                self.conn.rollback()
            except Exception as rollback_err:
                logger.error("Failed to rollback director decisions save: %s", rollback_err)
            logger.error(f"Failed to save decisions: {e}")

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception as e:
                logger.warning("Failed to close director decisions DB: %s", e)
            self._conn = None
