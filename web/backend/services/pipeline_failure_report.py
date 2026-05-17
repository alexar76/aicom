"""Human-readable failure reports for pipeline products (Admin UI)."""

from __future__ import annotations

from typing import Any


def _latest_failed_task(
    product: dict[str, Any],
    tasks: list[dict[str, Any]],
) -> dict[str, Any] | None:
    failed = [t for t in tasks if str(t.get("status") or "").lower() == "failed"]
    if not failed:
        return None

    try:
        from orchestrator.task_queue_hygiene import is_superseded_failed_task

        relevant = [t for t in failed if not is_superseded_failed_task(t, product)]
    except Exception:
        relevant = failed
    pool = relevant or failed

    def _score(t: dict[str, Any]) -> float:
        for key in ("completed_at", "updated_at", "started_at", "created_at"):
            v = t.get(key)
            if isinstance(v, (int, float)) and v > 0:
                return float(v)
        return 0.0

    return sorted(pool, key=_score, reverse=True)[0]


def _humanize_error(error: str, *, agent: str, state: str) -> str:
    e = (error or "").strip()
    low = e.lower()
    agent_label = agent or "unknown"
    state_label = (state or "unknown").replace("_", " ")

    if "specification failed quality gate" in low:
        bullets: list[str] = []
        for line in e.splitlines():
            line = line.strip()
            if line and line[0].isdigit() and "[" in line:
                bullets.append(line)
        detail = (
            "The PM agent produced a specification, but automated quality gates rejected it "
            "(structure, methodology coverage, or acceptance criteria). The pipeline paused here "
            "so the spec can be rewritten before architecture and development."
        )
        if bullets:
            detail += " Failed checks: " + "; ".join(bullets[:4])
            if len(bullets) > 4:
                detail += f" (+{len(bullets) - 4} more)."
        return detail

    if "architecture gate failed" in low:
        return (
            "The architect output did not pass the architecture gate "
            "(for example missing migration discipline or incomplete technical design). "
            "Development should not proceed until architecture is fixed."
        )

    if "peer review blocked" in low or "peer_review" in low:
        return (
            f"Peer review blocked progression after agent «{agent_label}». "
            "Downstream work was stopped until design/code quality issues are resolved."
        )

    if "security gate" in low or "security scan" in low:
        return "Security scanning found issues that must be fixed before release."

    if "marketplace readiness" in low or "storefront readiness" in low:
        return (
            "The build finished pipeline stages but did not pass storefront readiness gates "
            "(demo quality, marketplace listing rules, or QA realism)."
        )

    if "repair budget exhausted" in low or "repair cycles" in low:
        return (
            "Automatic repair loops exhausted the configured budget. "
            "Use «Send to rework» with operator instructions to continue."
        )

    if "timeout" in low or "timed out" in low:
        return f"Agent «{agent_label}» timed out while working on stage «{state_label}»."

    if e:
        return f"Agent «{agent_label}» failed at «{state_label}»: {e[:1200]}"
    return f"Agent «{agent_label}» failed at stage «{state_label}» with no stored error text."


def _false_failed_report(product: dict[str, Any], tasks: list[dict[str, Any]]) -> dict[str, Any] | None:
    try:
        from orchestrator.task_queue_hygiene import (
            _active_repair_tasks,
            is_likely_false_failed_product,
            recovery_state_after_false_failed,
        )
        from web.backend.api.products import _product_has_code
    except Exception:
        return None

    if not is_likely_false_failed_product(product, tasks):
        return None

    pid = str(product.get("id") or product.get("product_id") or "")
    repair = _active_repair_tasks(pid, tasks) if pid else []
    has_code = bool(pid and _product_has_code(pid))
    rec = recovery_state_after_false_failed(product, tasks)

    if repair and has_code:
        agent = str(repair[0].get("agent_type") or "developer")
        target = str(repair[0].get("state") or "DEV_FIXING")
        cause = (
            "This product was marked FAILED after a pipeline queue/restart glitch, not because "
            f"the current «{agent}» step actually failed. A repair task is already queued "
            f"({agent} → {target}). The worker will resume automatically; use «Send to rework» "
            "only if you want to change operator instructions."
        )
        suggested_agent, suggested_state = agent, target
    elif repair and not has_code:
        cause = (
            "FAILED was set by a queue/restart error while a developer repair task was still queued, "
            "but generated code is missing on disk — that repair cannot run. "
            "Use «Send to rework» to rebuild from PM/spec (full landing regeneration)."
        )
        suggested_agent, suggested_state = "pm", "MARKET_RESEARCHED"
    elif not has_code:
        cause = (
            "This product is in FAILED but has no generated code on disk (artifacts missing or removed). "
            "It was likely stopped by a queue/restart error, not a real QA failure. "
            "Use «Send to rework» to regenerate from PM/spec — choose instructions for a full landing rebuild."
        )
        suggested_agent, suggested_state = "pm", "MARKET_RESEARCHED"
    else:
        cause = (
            "This product was marked FAILED without a stored failure reason — usually a stale failed "
            "task from an earlier pipeline stage (often PM spec gate) after worker restart. "
            "Code is still on disk. Use «Send to rework» to continue developer/QA repair."
        )
        suggested_agent, suggested_state = "developer", "BUG_FOUND"

    if rec == "MARKET_RESEARCHED":
        suggested_agent, suggested_state = "pm", "MARKET_RESEARCHED"

    return {
        "headline": "False stop — queue/restart artifact (not a real agent failure)",
        "product_state": str(product.get("state") or "FAILED").upper(),
        "cause_plain": cause,
        "failed_agent": None,
        "failed_stage": None,
        "failure_reason": None,
        "technical_errors": [],
        "repair_round": product.get("quality_repair_round"),
        "pm_spec_requeue_count": product.get("pm_spec_requeue_count"),
        "suggested_recovery": {
            "agent_type": suggested_agent,
            "target_state": suggested_state,
        },
        "operator_hint": (
            "FAILED here is a pause label, not deletion. After the queue fix, the worker should "
            "auto-recover; rework overrides recovery with your instructions (min. 8 characters)."
        ),
        "false_failed": True,
    }


def build_failure_report(product: dict[str, Any], tasks: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Structured failure payload for Admin Pipeline UI."""
    tasks = tasks or []
    state = str(product.get("state") or "UNKNOWN").upper()

    false_report = _false_failed_report(product, tasks)
    if false_report is not None:
        return false_report

    primary = str(product.get("failure_reason") or "").strip()
    last_error = str(product.get("last_error") or product.get("error") or "").strip()

    latest = _latest_failed_task(product, tasks)
    agent = str(latest.get("agent_type") or "") if latest else ""
    task_state = str(latest.get("state") or "") if latest else ""
    task_error = str(latest.get("error") or "").strip() if latest else ""

    raw_errors: list[str] = []
    for src in (primary, last_error, task_error):
        if src and src not in raw_errors:
            raw_errors.append(src)
    for t in tasks:
        if str(t.get("status") or "").lower() != "failed":
            continue
        err = str(t.get("error") or "").strip()
        if err and err not in raw_errors:
            raw_errors.append(err)
        if len(raw_errors) >= 12:
            break

    headline = "Pipeline stopped — operator action recommended"
    if "specification failed quality gate" in (task_error or primary).lower():
        headline = "Specification quality gate failed"
    elif "architecture gate" in (task_error or primary).lower():
        headline = "Architecture gate failed"

    cause = _humanize_error(task_error or primary or last_error, agent=agent, state=task_state or state)

    repair_round = product.get("quality_repair_round")
    pm_requeue = product.get("pm_spec_requeue_count")

    suggested_agent = "pm"
    suggested_state = "MARKET_RESEARCHED"
    low = (task_error or primary).lower()
    if "architecture" in low:
        suggested_agent, suggested_state = "architect", "METHODOLOGY_REVIEWED"
    elif any(k in low for k in ("import error", "syntaxerror", "traceback", "test failure", "browser e2e")):
        suggested_agent, suggested_state = "developer", "BUG_FOUND"
    elif agent in ("developer", "hardening", "qa"):
        suggested_agent, suggested_state = "developer", "BUG_FOUND"

    return {
        "headline": headline,
        "product_state": state,
        "cause_plain": cause,
        "failed_agent": agent or None,
        "failed_stage": task_state if task_state and task_state != "FAILED" else None,
        "failure_reason": primary or None,
        "technical_errors": raw_errors,
        "repair_round": repair_round,
        "pm_spec_requeue_count": pm_requeue,
        "suggested_recovery": {
            "agent_type": suggested_agent,
            "target_state": suggested_state,
        },
        "operator_hint": (
            "Use «Send to rework» to queue a new attempt with your instructions. "
            "FAILED is a pause, not deletion — the product and artifacts are kept."
        ),
    }
