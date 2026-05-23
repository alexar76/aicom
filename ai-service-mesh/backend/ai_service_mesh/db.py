"""Mesh persistence — SQLite (default) or PostgreSQL via MESH_DATABASE_URL / DATABASE_URL."""

from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Optional
from uuid import uuid4

from ai_service_mesh.db_backend import DBBackend, create_backend
from ai_service_mesh.models import (
    ActivityEventOut,
    ActivityKind,
    AgentOut,
    AgentStatus,
    MeshHopOut,
    MeshStatsOut,
    TaskOut,
    TaskStatus,
    new_id,
    utc_now_iso,
)
from ai_service_mesh.payments import EscrowHold
from ai_service_mesh.schema import AGENT_LEGACY_COLUMNS, MESH_SCHEMA_SQL


class MeshStore:
    def __init__(self, data_dir: Path, database_url: str = "") -> None:
        data_dir.mkdir(parents=True, exist_ok=True)
        self._sqlite_path = data_dir / "mesh.db"
        self._backend: DBBackend = create_backend(
            database_url=database_url,
            db_path=self._sqlite_path,
        )
        self._lock = threading.Lock()
        self._init_schema()

    @property
    def backend_type(self) -> str:
        return self._backend.backend_type

    def close(self) -> None:
        self._backend.close()

    def _init_schema(self) -> None:
        with self._lock:
            self._backend.executescript(MESH_SCHEMA_SQL)
            self._backend.commit()
            for col_def in AGENT_LEGACY_COLUMNS:
                try:
                    self._backend.execute(f"ALTER TABLE agents ADD COLUMN {col_def}")
                    self._backend.commit()
                except Exception as exc:
                    msg = str(exc).lower()
                    if "duplicate column" not in msg and "already exists" not in msg:
                        raise

    def _execute(self, sql: str, params: tuple = ()) -> None:
        with self._lock:
            self._backend.execute(sql, params)
            self._backend.commit()

    def _fetchone(self, sql: str, params: tuple = ()) -> Optional[dict[str, Any]]:
        with self._lock:
            self._backend.execute(sql, params)
            row = self._backend.fetchone()
            self._backend.commit()
            return row

    def _fetchall(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        with self._lock:
            self._backend.execute(sql, params)
            rows = self._backend.fetchall()
            self._backend.commit()
            return rows

    def _scalar(self, sql: str, params: tuple = ()) -> Any:
        row = self._fetchone(sql, params)
        if not row:
            return 0
        return next(iter(row.values()))

    @staticmethod
    def _utc_cutoff_24h() -> str:
        return (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S+00:00")

    def emit(
        self,
        kind: ActivityKind,
        message: str,
        *,
        task_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        payload: Optional[dict[str, Any]] = None,
    ) -> ActivityEventOut:
        ev = ActivityEventOut(
            id=new_id("act_"),
            kind=kind,
            message=message,
            task_id=task_id,
            agent_id=agent_id,
            payload=payload or {},
            timestamp=utc_now_iso(),
        )
        self._execute(
            "INSERT INTO activity (id, kind, message, task_id, agent_id, payload_json, timestamp) VALUES (?,?,?,?,?,?,?)",
            (
                ev.id,
                ev.kind.value,
                ev.message,
                ev.task_id,
                ev.agent_id,
                json.dumps(ev.payload),
                ev.timestamp,
            ),
        )
        return ev

    def register_agent(
        self,
        name: str,
        endpoint_url: str,
        public_key_pem: str,
        capabilities: list[str],
        attestation: str,
        *,
        product_id: str = "",
        capability_id: str = "",
        source_hub: str = "local",
    ) -> AgentOut:
        agent = AgentOut(
            id=new_id("agt_"),
            name=name,
            endpoint_url=endpoint_url,
            status=AgentStatus.PENDING,
            trust_score=0.5,
            capabilities=capabilities,
            product_id=product_id,
            capability_id=capability_id,
            source_hub=source_hub,
            created_at=utc_now_iso(),
        )
        self._execute(
            """INSERT INTO agents (
                id, name, endpoint_url, public_key_pem, capabilities, status,
                trust_score, attestation, product_id, capability_id, source_hub, created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                agent.id,
                agent.name,
                agent.endpoint_url,
                public_key_pem,
                json.dumps(capabilities),
                agent.status.value,
                agent.trust_score,
                attestation,
                product_id,
                capability_id,
                source_hub,
                agent.created_at,
            ),
        )
        self.emit(
            ActivityKind.AGENT_REGISTERED,
            f"Agent {name} registered",
            agent_id=agent.id,
            payload={"endpoint": endpoint_url, "capabilities": capabilities},
        )
        return agent

    def verify_agent(self, agent_id: str, trust_score: float) -> Optional[AgentOut]:
        verified_at = utc_now_iso()
        self._execute(
            "UPDATE agents SET status=?, trust_score=?, verified_at=? WHERE id=?",
            (AgentStatus.VERIFIED.value, trust_score, verified_at, agent_id),
        )
        agent = self.get_agent(agent_id)
        if agent:
            self.emit(
                ActivityKind.AGENT_VERIFIED,
                f"Zero-trust verification passed for {agent.name}",
                agent_id=agent_id,
                payload={"trust_score": trust_score},
            )
        return agent

    def get_agent(self, agent_id: str) -> Optional[AgentOut]:
        row = self._fetchone("SELECT * FROM agents WHERE id=?", (agent_id,))
        return self._row_agent(row) if row else None

    def list_agents(self, *, verified_only: bool = False) -> list[AgentOut]:
        q = "SELECT * FROM agents"
        params: tuple[Any, ...] = ()
        if verified_only:
            q += " WHERE status=?"
            params = (AgentStatus.VERIFIED.value,)
        q += " ORDER BY trust_score DESC, created_at DESC"
        return [self._row_agent(r) for r in self._fetchall(q, params)]

    def create_task(
        self,
        intent: str,
        budget_usd: float,
        consumer_agent_id: str,
    ) -> TaskOut:
        task = TaskOut(
            id=new_id("tsk_"),
            intent=intent,
            budget_usd=budget_usd,
            status=TaskStatus.QUEUED,
            created_at=utc_now_iso(),
        )
        self._execute(
            "INSERT INTO tasks (id, intent, budget_usd, consumer_agent_id, status, hops_json, created_at) VALUES (?,?,?,?,?,?,?)",
            (
                task.id,
                task.intent,
                task.budget_usd,
                consumer_agent_id or None,
                task.status.value,
                "[]",
                task.created_at,
            ),
        )
        self.emit(
            ActivityKind.TASK_CREATED,
            f"Task queued: {intent[:80]}",
            task_id=task.id,
            payload={"budget_usd": budget_usd},
        )
        return task

    def update_task(self, task: TaskOut) -> None:
        self._execute(
            """UPDATE tasks SET status=?, selected_agent_id=?, total_spent_usd=?, hops_json=?, error=?, completed_at=? WHERE id=?""",
            (
                task.status.value,
                task.selected_agent_id,
                task.total_spent_usd,
                json.dumps([h.model_dump() for h in task.hops]),
                task.error,
                task.completed_at,
                task.id,
            ),
        )

    def get_task(self, task_id: str) -> Optional[TaskOut]:
        row = self._fetchone("SELECT * FROM tasks WHERE id=?", (task_id,))
        return self._row_task(row) if row else None

    def list_tasks(self, limit: int = 50) -> list[TaskOut]:
        rows = self._fetchall(
            "SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        return [self._row_task(r) for r in rows]

    def fail_stale_tasks(self, max_age_seconds: int) -> int:
        """Dead-letter in-progress tasks older than max_age_seconds (crash recovery)."""
        if max_age_seconds <= 0:
            return 0
        cutoff = (
            datetime.now(timezone.utc) - timedelta(seconds=max_age_seconds)
        ).strftime("%Y-%m-%dT%H:%M:%S+00:00")
        stale = (
            TaskStatus.QUEUED.value,
            TaskStatus.DISCOVERING.value,
            TaskStatus.VERIFYING.value,
            TaskStatus.ESCROWED.value,
            TaskStatus.INVOKING.value,
        )
        placeholders = ",".join("?" * len(stale))
        rows = self._fetchall(
            f"""SELECT id FROM tasks
                WHERE status IN ({placeholders})
                  AND (completed_at IS NULL OR completed_at = '')
                  AND created_at < ?""",
            (*stale, cutoff),
        )
        now = utc_now_iso()
        for row in rows:
            self._execute(
                "UPDATE tasks SET status=?, error=?, completed_at=? WHERE id=?",
                (
                    TaskStatus.FAILED.value,
                    "task_timeout_dead_letter",
                    now,
                    row["id"],
                ),
            )
            self.emit(
                ActivityKind.ERROR,
                "Task timed out (dead-letter recovery)",
                task_id=row["id"],
            )
        return len(rows)

    def list_activity(self, limit: int = 100, since_id: Optional[str] = None) -> list[ActivityEventOut]:
        if since_id:
            ts_row = self._fetchone("SELECT timestamp FROM activity WHERE id=?", (since_id,))
            if ts_row:
                rows = self._fetchall(
                    "SELECT * FROM activity WHERE timestamp > ? ORDER BY timestamp ASC LIMIT ?",
                    (ts_row["timestamp"], limit),
                )
            else:
                rows = self._fetchall(
                    "SELECT * FROM activity ORDER BY timestamp DESC LIMIT ?",
                    (limit,),
                )
                rows = list(reversed(rows))
        else:
            rows = self._fetchall(
                "SELECT * FROM activity ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            )
            rows = list(reversed(rows))
        return [self._row_activity(r) for r in rows]

    def create_escrow_hold(self, task_id: str, agent_id: str, amount_usd: float) -> EscrowHold:
        hold = EscrowHold(
            id=f"esc_{uuid4().hex[:12]}",
            task_id=task_id,
            agent_id=agent_id,
            amount_usd=amount_usd,
            status="held",
        )
        self._execute(
            "INSERT INTO escrow_holds (id, task_id, agent_id, amount_usd, status, created_at) VALUES (?,?,?,?,?,?)",
            (hold.id, hold.task_id, hold.agent_id, hold.amount_usd, hold.status, utc_now_iso()),
        )
        return hold

    def update_escrow_status(self, hold_id: str, status: str) -> EscrowHold:
        self._execute("UPDATE escrow_holds SET status=? WHERE id=?", (status, hold_id))
        row = self._fetchone("SELECT * FROM escrow_holds WHERE id=?", (hold_id,))
        if not row:
            raise KeyError(hold_id)
        return EscrowHold(
            id=row["id"],
            task_id=row["task_id"],
            agent_id=row["agent_id"],
            amount_usd=float(row["amount_usd"]),
            status=row["status"],
        )

    def stats(self) -> MeshStatsOut:
        cutoff = self._utc_cutoff_24h()
        agents_total = int(self._scalar("SELECT COUNT(*) AS n FROM agents"))
        agents_verified = int(
            self._scalar(
                "SELECT COUNT(*) AS n FROM agents WHERE status=?",
                (AgentStatus.VERIFIED.value,),
            )
        )
        tasks_24h = int(
            self._scalar("SELECT COUNT(*) AS n FROM tasks WHERE created_at >= ?", (cutoff,))
        )
        ok = int(
            self._scalar(
                "SELECT COUNT(*) AS n FROM tasks WHERE created_at >= ? AND status=?",
                (cutoff, TaskStatus.COMPLETED.value),
            )
        )
        vol = float(
            self._scalar(
                "SELECT COALESCE(SUM(total_spent_usd), 0) AS n FROM tasks WHERE created_at >= ?",
                (cutoff,),
            )
        )
        hops = 0
        for row in self._fetchall(
            "SELECT hops_json FROM tasks WHERE created_at >= ?",
            (cutoff,),
        ):
            hops += len(json.loads(row["hops_json"] or "[]"))
        rate = (ok / tasks_24h) if tasks_24h else 1.0
        return MeshStatsOut(
            agents_total=agents_total,
            agents_verified=agents_verified,
            tasks_24h=tasks_24h,
            mesh_hops_24h=hops,
            success_rate_24h=round(rate, 4),
            volume_usd_24h=round(vol, 2),
        )

    @staticmethod
    def _row_agent(row: Mapping[str, Any]) -> AgentOut:
        keys = row.keys()
        return AgentOut(
            id=row["id"],
            name=row["name"],
            endpoint_url=row["endpoint_url"],
            status=AgentStatus(row["status"]),
            trust_score=float(row["trust_score"]),
            capabilities=json.loads(row["capabilities"] or "[]"),
            product_id=row["product_id"] if "product_id" in keys else "",
            capability_id=row["capability_id"] if "capability_id" in keys else "",
            source_hub=row["source_hub"] if "source_hub" in keys else "local",
            verified_at=row.get("verified_at"),
            created_at=row["created_at"],
        )

    @staticmethod
    def _row_task(row: Mapping[str, Any]) -> TaskOut:
        hops_raw = json.loads(row["hops_json"] or "[]")
        return TaskOut(
            id=row["id"],
            intent=row["intent"],
            budget_usd=float(row["budget_usd"]),
            status=TaskStatus(row["status"]),
            selected_agent_id=row.get("selected_agent_id"),
            total_spent_usd=float(row["total_spent_usd"] or 0),
            hops=[MeshHopOut(**h) for h in hops_raw],
            created_at=row["created_at"],
            completed_at=row.get("completed_at"),
            error=row.get("error"),
        )

    @staticmethod
    def _row_activity(row: Mapping[str, Any]) -> ActivityEventOut:
        return ActivityEventOut(
            id=row["id"],
            kind=ActivityKind(row["kind"]),
            message=row["message"],
            task_id=row.get("task_id"),
            agent_id=row.get("agent_id"),
            payload=json.loads(row["payload_json"] or "{}"),
            timestamp=row["timestamp"],
        )
