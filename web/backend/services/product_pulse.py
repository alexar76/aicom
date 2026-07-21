"""
Compact “Product Pulse” payload for Admin Pipeline cards and metrics SSE.

Mirrors frontend ``findTaskForStage`` / ``PIPELINE_STAGE_ORDER`` so stage counts
and current agent stay aligned with the existing stage flow bar.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Literal, Optional

from core.agent_roles import is_architect_agent

logger = logging.getLogger(__name__)

PIPELINE_STAGE_ORDER: tuple[str, ...] = (
    "analyst",
    "pm",
    "marketing",
    "methodologist",
    "architect",
    "designer",
    "developer",
    "qa",
    "security",
    "devops",
    "sales",
)

STAGE_AGENT_TITLE: dict[str, str] = {
    "analyst": "Market Analyst",
    "pm": "Product Manager",
    "methodologist": "Methodologist",
    "architect": "Architect",
    "designer": "Designer (UX)",
    "developer": "Developer",
    "qa": "QA Engineer",
    "security": "Security",
    "devops": "DevOps",
    "marketing": "Marketing",
    "sales": "Sales",
}

STUCK_RUNNING_SECONDS = 45 * 60
TOTAL_STAGES = len(PIPELINE_STAGE_ORDER)


def _task_status_lower(t: Optional[dict]) -> str:
    if not isinstance(t, dict):
        return ""
    return str(t.get("status") or "").strip().lower()


def _review_blob(task: Optional[dict], *keys: str) -> Any:
    if not isinstance(task, dict):
        return None
    res = task.get("result")
    if isinstance(res, dict):
        for k in keys:
            if k in res and res[k] is not None:
                return res[k]
    data = task.get("data")
    if isinstance(data, dict):
        for k in keys:
            if k in data and data[k] is not None:
                return data[k]
    return None


def _review_passed(review: Any) -> Optional[bool]:
    if not isinstance(review, dict) or "passed" not in review:
        return None
    return bool(review.get("passed"))


def find_task_for_stage(task_list: list[dict], stage: str) -> Optional[dict]:
    """Match ``PipelineTab.findTaskForStage`` (designer→architect, dev aliases, methodologist virtual)."""
    if stage == "designer":
        return next((x for x in task_list if is_architect_agent(x.get("agent_type"))), None)
    if stage == "methodologist":
        direct = next((x for x in task_list if x.get("agent_type") == "methodologist"), None)
        if direct:
            return direct
        pm = next((x for x in task_list if x.get("agent_type") == "pm"), None)
        qa = next((x for x in task_list if x.get("agent_type") == "qa"), None)
        pm_review = _review_blob(pm, "methodology_spec_review")
        qa_review = _review_blob(qa, "methodology_review")
        pm_passed = _review_passed(pm_review)
        qa_passed = _review_passed(qa_review)
        status = "pending"
        if pm_passed is False or qa_passed is False:
            status = "failed"
        elif _task_status_lower(pm) == "running" or _task_status_lower(qa) == "running":
            status = "running"
        elif pm_passed is True or qa_passed is True:
            status = "completed"
        elif _task_status_lower(pm) == "completed":
            status = "completed"
        return {
            "agent_type": "methodologist",
            "status": status,
            "data": {"methodology_spec_review": pm_review, "methodology_review": qa_review},
        }
    hit = next((x for x in task_list if x.get("agent_type") == stage), None)
    if hit:
        return hit
    if stage == "developer":
        return next((x for x in task_list if x.get("agent_type") in ("dev", "landing_developer")), None)
    if stage == "dev":
        return next((x for x in task_list if x.get("agent_type") in ("developer", "landing_developer")), None)
    return None


def _delivery_profile_from_row(row: dict[str, Any]) -> str:
    spec = row.get("spec")
    meta = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    if not isinstance(spec, dict):
        spec = meta.get("spec") if isinstance(meta.get("spec"), dict) else {}
    if not isinstance(spec, dict):
        return "full_software"
    raw = spec.get("delivery_profile")
    if raw:
        s = str(raw).strip().lower()
        if "landing" in s or s == "marketing_landing":
            return "marketing_landing"
    inner = spec.get("specification")
    if isinstance(inner, dict) and inner.get("delivery_profile"):
        s = str(inner.get("delivery_profile")).strip().lower()
        if "landing" in s:
            return "marketing_landing"
    return "full_software"


def _tech_stack_badges(arch: Any, *, max_items: int = 6) -> list[str]:
    if not isinstance(arch, dict):
        return []
    ts = arch.get("tech_stack")
    if not isinstance(ts, dict):
        return []
    out: list[str] = []
    for key in ("frontend", "backend", "database", "infrastructure"):
        v = ts.get(key)
        if not isinstance(v, str):
            continue
        s = v.strip()
        if not s or s.lower() == "none":
            continue
        chunk = s.split(",")[0].strip()
        if len(chunk) > 28:
            chunk = chunk[:25] + "…"
        out.append(chunk)
        if len(out) >= max_items:
            break
    return out


def _load_gate_telemetry(product_id: str, data_root: Path) -> Optional[dict[str, Any]]:
    p = data_root / "telemetry" / product_id / "demo_quality_gate.json"
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def enrich_pipeline_catalog_quality_fields(row: dict[str, Any], *, data_root: Path) -> None:
    """Attach qa_gates / demo score from gate telemetry (works for light + full catalog)."""
    pid = str(row.get("id") or "")
    if not pid:
        return
    tel = _load_gate_telemetry(pid, data_root)
    if not isinstance(tel, dict):
        return
    if "gates_all_passed" in tel:
        row["qa_gates_all_passed"] = tel.get("gates_all_passed")
    demo = tel.get("demo_quality")
    if isinstance(demo, dict) and demo.get("score") is not None:
        try:
            row["demo_quality"] = {"score": float(demo["score"])}
        except (TypeError, ValueError):
            pass


def _terminal_pipeline_state(state: str) -> bool:
    s = state.strip().upper()
    return s in ("COMPLETED", "DEPLOYED_PRODUCTION", "FAILED", "CANCELLED")


def _format_eta_label(seconds: Optional[int]) -> Optional[str]:
    if seconds is None or seconds <= 0:
        return None
    minutes = max(1, (seconds + 59) // 60)
    if minutes >= 120:
        h, m = divmod(minutes, 60)
        return f"~{h}h {m}m left"
    return f"~{minutes} min left"


def _max_running_age_seconds(task_list: list[dict]) -> float:
    now = time.time()
    worst = 0.0
    for t in task_list:
        if _task_status_lower(t) != "running":
            continue
        started = t.get("started_at")
        try:
            st = float(started) if started is not None else 0.0
        except (TypeError, ValueError):
            st = 0.0
        if st <= 0:
            continue
        worst = max(worst, now - st)
    return worst


def build_product_pulse(
    row: dict[str, Any],
    *,
    light: bool,
    data_root: Path,
) -> dict[str, Any]:
    """
    Build pulse dict for one catalog / metrics row (expects ``id``, ``state``, ``tasks``, ``architecture``).
    """
    pid = str(row.get("id") or "")
    state_raw = str(row.get("state") or "UNKNOWN")
    state_u = state_raw.strip().upper()
    tasks = [dict(x) for x in (row.get("tasks") or []) if isinstance(x, dict)]

    completed_agents = {
        str(t.get("agent_type") or "").lower()
        for t in tasks
        if _task_status_lower(t) == "completed"
    }
    if "developer" in completed_agents or "dev" in completed_agents:
        completed_agents.add("developer")
        completed_agents.add("dev")
    if "architect" in completed_agents:
        completed_agents.add("designer")
    repair_state = state_u in ("DEV_FIXING", "BUG_FOUND", "QA_TESTING", "CODE_TESTING")
    mature_build = len([t for t in tasks if _task_status_lower(t) == "completed"]) >= 40

    stage_statuses: list[str] = []
    stage_dots: list[Literal["done", "run", "todo", "fail"]] = []
    for st in PIPELINE_STAGE_ORDER:
        t = find_task_for_stage(tasks, st)
        status = _task_status_lower(t) if t else ""
        if not status:
            status = "pending"
        if mature_build and repair_state:
            agent_key = st
            if st == "designer" and "architect" in completed_agents:
                status = "completed"
            elif st == "methodologist" and (
                "methodologist" in completed_agents
                or ("pm" in completed_agents and "qa" in completed_agents)
            ):
                status = "completed"
            elif agent_key in completed_agents or (
                st == "developer" and ("developer" in completed_agents or "dev" in completed_agents)
            ):
                status = "completed"
        stage_statuses.append(status)
        if status == "completed":
            stage_dots.append("done")
        elif status == "running":
            stage_dots.append("run")
        elif status == "failed":
            stage_dots.append("fail")
        else:
            stage_dots.append("todo")

    completed_stages = sum(1 for s in stage_statuses if s == "completed")

    current_stage: Optional[str] = None
    current_status = "pending"
    for st, status in zip(PIPELINE_STAGE_ORDER, stage_statuses, strict=True):
        if status in ("running", "failed"):
            current_stage = st
            current_status = status
            break
    if current_stage is None:
        for st, status in zip(PIPELINE_STAGE_ORDER, stage_statuses, strict=True):
            if status == "pending":
                current_stage = st
                current_status = "pending"
                break
    if current_stage is None:
        current_stage = "sales"
        current_status = "completed" if completed_stages >= TOTAL_STAGES else "pending"

    _shipped_display_states = frozenset(
        {
            "SALES_ACTIVE",
            "SANDBOX_RUNNING",
            "TELEMETRY_COLLECTING",
            "EVOLUTION_ANALYZING",
            "COMPLETED",
            "DEPLOYED_PRODUCTION",
        }
    )
    if state_u in _shipped_display_states or (
        mature_build and state_u not in ("FAILED", "CANCELLED", "IDEA_RECEIVED")
    ):
        stage_statuses = ["completed"] * TOTAL_STAGES
        stage_dots = ["done"] * TOTAL_STAGES
        completed_stages = TOTAL_STAGES
        current_stage = "sales"
        current_status = "completed"

    agent_label = STAGE_AGENT_TITLE.get(current_stage, current_stage.replace("_", " ").title())
    if _terminal_pipeline_state(state_u):
        if state_u == "FAILED":
            current_status = "failed"
        elif state_u in ("COMPLETED", "DEPLOYED_PRODUCTION"):
            current_status = "completed"

    delivery = _delivery_profile_from_row(row)
    sec_per_stage = 240 if delivery == "marketing_landing" else 420
    remaining = max(0, TOTAL_STAGES - completed_stages)
    eta_seconds: Optional[int] = None
    if not _terminal_pipeline_state(state_u):
        eta_seconds = remaining * sec_per_stage
        if current_status == "running":
            eta_seconds = max(sec_per_stage // 2, eta_seconds - sec_per_stage // 2)

    run_age = _max_running_age_seconds(tasks)
    health: Literal["ok", "stuck", "degraded"] = "ok"
    health_hint: Optional[str] = None
    if current_status == "running" and run_age > STUCK_RUNNING_SECONDS:
        health = "stuck"
        health_hint = f"No progress for {int(run_age // 60)}+ min"
    elif any(_task_status_lower(t) == "failed" for t in tasks) or state_u == "FAILED":
        health = "degraded"

    quality_pulse: Literal["green", "amber", "red", "unknown"] = "unknown"
    quality_hint = "Quality signal pending"
    if state_u == "FAILED":
        quality_pulse, quality_hint = "red", "Pipeline failed"
    elif any(_task_status_lower(t) == "failed" for t in tasks):
        quality_pulse, quality_hint = "red", "Agent task failed"
    else:
        # Light catalog still reads demo_quality_gate.json (cheap); only skips heavy spec/task payloads.
        tel = _load_gate_telemetry(pid, data_root) if pid else None
        if isinstance(tel, dict):
            if tel.get("gates_all_passed") is True:
                quality_pulse, quality_hint = "green", "Demo gates passed"
            elif tel.get("gates_all_passed") is False:
                quality_pulse, quality_hint = "red", "Demo gates failed"
            else:
                quality_pulse, quality_hint = "amber", "Demo gates in progress"
        else:
            qa_done = any(
                x.get("agent_type") == "qa" and _task_status_lower(x) == "completed" for x in tasks
            )
            if qa_done:
                quality_pulse, quality_hint = "amber", "Awaiting demo gate telemetry"
            elif completed_stages >= 7:
                quality_pulse, quality_hint = "amber", "Build progressing — QA not finished"
            else:
                quality_pulse, quality_hint = "green", "No blocking issues yet"

    economics = row.get("economics") if isinstance(row.get("economics"), dict) else {}
    qs = economics.get("quality_score")
    quality_score: Optional[float] = None
    try:
        if qs is not None:
            quality_score = float(qs)
    except (TypeError, ValueError):
        quality_score = None

    arch = row.get("architecture")
    tech_stack = _tech_stack_badges(arch)

    return {
        "product_id": pid,
        "current_stage": current_stage,
        "current_agent_label": agent_label,
        "current_status": current_status,
        "completed_stages": completed_stages,
        "total_stages": TOTAL_STAGES,
        "stage_dots": stage_dots,
        "eta_seconds": eta_seconds,
        "eta_label": _format_eta_label(eta_seconds),
        "tech_stack": tech_stack,
        "quality_pulse": quality_pulse,
        "quality_hint": quality_hint,
        "quality_score": quality_score,
        "health": health,
        "health_hint": health_hint,
        "pipeline_state": state_u,
    }


def _is_shipped_pipeline_state(state: Any) -> bool:
    s = str(state or "").strip().upper()
    return s in ("COMPLETED", "DEPLOYED_PRODUCTION")


def build_product_pulses_for_metrics(
    products: dict[str, Any],
    task_queue: list[dict],
    *,
    data_root: Path,
    max_products: int = 64,
) -> dict[str, Any]:
    """Subset of products for SSE / dashboard (non-shipped, non-terminal first by recency)."""

    tasks_by_product: dict[str, list[dict]] = {}
    for t in task_queue:
        pid = str(t.get("product_id") or "")
        if not pid:
            continue
        tasks_by_product.setdefault(pid, []).append(dict(t))

    candidates: list[tuple[str, dict[str, Any], float]] = []
    for pid, p in products.items():
        if not isinstance(p, dict):
            continue
        st = str(p.get("state") or "").strip().upper()
        if _is_shipped_pipeline_state(p.get("state")):
            continue
        if st in ("FAILED", "CANCELLED"):
            continue
        try:
            ts = float(p.get("updated_at") or p.get("created_at") or 0.0)
        except (TypeError, ValueError):
            ts = 0.0
        candidates.append((pid, p, ts))
    candidates.sort(key=lambda x: x[2], reverse=True)

    out: dict[str, Any] = {}
    for pid, p, _ in candidates[:max_products]:
        meta = p.get("metadata") if isinstance(p.get("metadata"), dict) else {}
        synthetic: dict[str, Any] = {
            "id": pid,
            "state": p.get("state"),
            "spec": p.get("spec") or meta.get("spec"),
            "metadata": meta,
            "architecture": p.get("architecture") or meta.get("architecture"),
            "tasks": tasks_by_product.get(pid, []),
        }
        try:
            out[pid] = build_product_pulse(synthetic, light=False, data_root=data_root)
        except Exception as e:
            logger.debug("product pulse metrics for %s: %s", pid, e)
    return out
