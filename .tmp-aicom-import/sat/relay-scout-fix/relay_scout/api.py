from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(title="Relay Scout Ops API", version="0.1.0")

# In-memory devtools/ops store (project, environment, deployment, log, alert lifecycle)
PROJECTS: dict[str, dict[str, Any]] = {}
DEPLOYMENTS: dict[str, dict[str, Any]] = {}
LOGS: dict[str, list[dict[str, Any]]] = {}
ALERTS: dict[str, dict[str, Any]] = {}


class ProjectCreate(BaseModel):
    name: str
    repo: str | None = None


class DeploymentCreate(BaseModel):
    version: str
    environment: str = "staging"


class EnvironmentConfig(BaseModel):
    name: str = Field(description="dev/staging/production")
    config: dict[str, Any] = Field(default_factory=dict)


class AlertAck(BaseModel):
    note: str = ""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "relay-scout-api"}


@app.post("/api/projects")
def create_project(body: ProjectCreate) -> dict[str, Any]:
    """create_project capability — register a monitored project."""
    pid = uuid.uuid4().hex[:12]
    PROJECTS[pid] = {
        "id": pid,
        "name": body.name,
        "repo": body.repo,
        "environments": {"staging": {"name": "staging"}, "production": {"name": "production"}},
        "created_at": _now(),
    }
    LOGS[pid] = [{"timestamp": _now(), "level": "info", "message": "project created", "source": "api"}]
    return PROJECTS[pid]


@app.post("/api/projects/{project_id}/environments")
def configure_env(project_id: str, body: EnvironmentConfig) -> dict[str, Any]:
    """configure_env — register or update a deployment environment."""
    if project_id not in PROJECTS:
        raise HTTPException(status_code=404, detail="project not found")
    project = PROJECTS[project_id]
    envs = project.setdefault("environments", {})
    envs[body.name] = {"name": body.name, "config": body.config}
    LOGS.setdefault(project_id, []).append(
        {
            "timestamp": _now(),
            "level": "info",
            "message": f"environment {body.name} configured",
            "source": "configure_env",
        }
    )
    return {"project_id": project_id, "environment": envs[body.name]}


@app.post("/api/projects/{project_id}/deployments")
def ship_deployment(project_id: str, body: DeploymentCreate) -> dict[str, Any]:
    """ship_deployment — trigger deployment (queued -> running -> succeeded/failed)."""
    if project_id not in PROJECTS:
        raise HTTPException(status_code=404, detail="project not found")
    did = uuid.uuid4().hex[:12]
    dep = {
        "id": did,
        "project_id": project_id,
        "environment_id": body.environment,
        "version": body.version,
        "status": "queued",
        "started_at": _now(),
        "finished_at": None,
    }
    DEPLOYMENTS[did] = dep
    LOGS.setdefault(project_id, []).append(
        {
            "timestamp": _now(),
            "level": "info",
            "message": f"deployment {did} queued for staging",
            "source": "deploy",
        }
    )
    dep["status"] = "running"
    LOGS[project_id].append(
        {
            "timestamp": _now(),
            "level": "info",
            "message": f"deployment {did} running",
            "source": "deploy",
        }
    )
    dep["status"] = "succeeded"
    dep["finished_at"] = _now()
    LOGS[project_id].append(
        {
            "timestamp": _now(),
            "level": "info",
            "message": f"deployment {did} succeeded",
            "source": "deploy",
        }
    )
    return dep


@app.get("/api/deployments/{deployment_id}")
def deployment_status(deployment_id: str) -> dict[str, Any]:
    dep = DEPLOYMENTS.get(deployment_id)
    if not dep:
        raise HTTPException(status_code=404, detail="deployment not found")
    return dep


@app.post("/api/deployments/{deployment_id}/rollback")
def rollback_deployment(deployment_id: str) -> dict[str, Any]:
    dep = DEPLOYMENTS.get(deployment_id)
    if not dep:
        raise HTTPException(status_code=404, detail="deployment not found")
    dep["status"] = "rolled back"
    dep["finished_at"] = _now()
    pid = dep["project_id"]
    LOGS.setdefault(pid, []).append(
        {
            "timestamp": _now(),
            "level": "warning",
            "message": f"deployment {deployment_id} rolled back",
            "source": "rollback",
        }
    )
    return dep


@app.get("/api/projects/{project_id}/logs")
def view_logs(project_id: str) -> dict[str, Any]:
    """view_logs capability."""
    if project_id not in PROJECTS:
        raise HTTPException(status_code=404, detail="project not found")
    return {"project_id": project_id, "logs": LOGS.get(project_id, [])}


@app.post("/api/alerts")
def configure_alert(body: dict[str, Any]) -> dict[str, Any]:
    """configure_alert — create alert rule (open state)."""
    aid = uuid.uuid4().hex[:12]
    alert = {
        "id": aid,
        "name": body.get("name", "endpoint-down"),
        "condition": body.get("condition", "status != 200"),
        "severity": body.get("severity", "high"),
        "state": "open",
        "opened_at": _now(),
        "resolved_at": None,
    }
    ALERTS[aid] = alert
    return alert


@app.post("/api/alerts/{alert_id}/ack")
def ack_incident(alert_id: str, body: AlertAck = AlertAck()) -> dict[str, Any]:
    """ack_incident — acknowledge alert (open -> ack -> resolved)."""
    alert = ALERTS.get(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="alert not found")
    alert["state"] = "acknowledged"
    alert["ack_note"] = body.note
    alert["resolved_at"] = _now()
    return alert


@app.post("/api/integrations")
def manage_integration(body: dict[str, Any]) -> dict[str, Any]:
    """manage_integration — register Slack/PagerDuty/webhook integration."""
    iid = uuid.uuid4().hex[:12]
    integration = {
        "id": iid,
        "kind": body.get("kind", "webhook"),
        "config": body.get("config", {}),
        "created_at": _now(),
    }
    return integration


@app.get("/api/checks/run")
def run_check_summary() -> dict[str, Any]:
    """Operator endpoint: summarize endpoint health polling."""
    return {
        "checks": [
            {"name": "factory", "url": "https://magic-ai-factory.com/api/health", "status": "configured"},
            {"name": "monitor", "url": "https://monitor.modelmarket.dev/api/health", "status": "configured"},
        ]
    }
