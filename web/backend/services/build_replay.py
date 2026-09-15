"""Public **build replay** — turn a product's pipeline history into a shareable,
sanitized timeline of agent stages.

The replay is the viral artifact behind the public `/build/{id}` permalink: a
visitor (or a social-card crawler) can see *how* AI-Factory built a product —
which agents ran, in what order, how long each took, and whether quality gates
passed — without ever exposing prompts, secrets, or raw agent output.

Data source: the same `products` + `tasks` SQLite store the pipeline writes to
(see `orchestrator/sqlite_manager.py`). Each task row is one agent stage with
`agent_type`, `status`, `state`, and start/complete timestamps — exactly the
shape of a build timeline.

SECURITY: this module is the public boundary. It **whitelists** what leaves the
building. Raw `output_data` / `input_data` / `error` strings are never returned;
only a small set of explicitly-safe scalar highlights and booleans.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Agent presentation metadata
# ---------------------------------------------------------------------------
# (label, emoji, what-they-did blurb). Keep blurbs generic & safe — they are
# static, never derived from agent output.
#
# NOTE: landing fast-path agents (`landing_architect`, `landing_developer`) are
# mirrored alongside their generic counterparts — see MEMORY: landing fast-path
# agent mirroring. Any new "developer"/"architect" special-casing must add the
# landing_* variant here too.
_AGENT_META: dict[str, tuple[str, str, str]] = {
    "analyst": ("Analyst", "🔍", "Researched the market and validated demand"),
    "pm": ("Product Manager", "📝", "Wrote the product specification"),
    "marketing": ("Marketing", "📢", "Crafted positioning and copy"),
    "methodologist": ("Methodologist", "🧭", "Reviewed methodology (quality gate)"),
    "architect": ("Architect", "🎨", "Designed the system architecture"),
    "landing_architect": ("Landing Architect", "🎨", "Designed the landing structure"),
    "design_critic": ("Design Critic", "🪞", "Critiqued the design (quality gate)"),
    "designer": ("Designer", "🖌️", "Produced the UI design"),
    "developer": ("Developer", "👨‍💻", "Built the product"),
    "landing_developer": ("Landing Developer", "👨‍💻", "Built the landing page"),
    "qa": ("QA", "🧪", "Ran tests and browser E2E"),
    "hardening": ("Hardening", "🛡️", "Hardened robustness (conditional gate)"),
    "security": ("Security", "🔒", "Scanned for vulnerabilities"),
    "devops": ("DevOps", "🚀", "Deployed to the storefront sandbox"),
    "sales": ("Sales", "💰", "Set pricing and listed the product"),
    "product_profile": ("Product Profile", "🧩", "Resolved the delivery profile"),
    "spec_quality_gate": ("Spec Quality Gate", "✅", "Checked specification quality"),
    "evolution": ("Evolution", "🔄", "Analyzed post-ship signals"),
    "evolution_analyst": ("Evolution Analyst", "🔄", "Analyzed post-ship signals"),
}

# Pseudo-agents the worker records for runtime/gate steps.
_RUNTIME_META: dict[str, tuple[str, str, str]] = {
    "__runtime_test__": ("Test Gate", "🧪", "Ran the runtime test gate"),
    "__human_gate__": ("Human Review", "🙋", "Paused for human review"),
    "__complete__": ("Ship", "🎉", "Marked the build complete"),
}

# Keys we will surface from a task's output_data IF present and IF the value is a
# safe scalar (bool / number / short string from a constrained set). Everything
# else is dropped. Anything secret-ish is additionally filtered by name below.
_SAFE_HIGHLIGHT_KEYS: dict[str, str] = {
    "passed": "passed",
    "verdict": "verdict",
    "score": "score",
    "category": "category",
    "delivery_profile": "profile",
    "tech_stack_label": "stack",
    "findings_count": "findings",
    "tests_total": "tests",
    "tests_passed": "tests_passed",
    "files_written": "files",
    "quality_repair_round": "repair_round",
}

# Substrings that disqualify a key from ever being surfaced (defense in depth).
_FORBIDDEN_KEY_SUBSTRINGS = (
    "prompt", "secret", "token", "key", "password", "api", "auth",
    "raw", "content", "code", "html", "text", "body", "message", "trace",
    "url", "path", "env", "credential", "cookie", "header",
)

_MAX_HIGHLIGHT_STR = 48


def _agent_presentation(agent_type: str) -> tuple[str, str, str]:
    a = str(agent_type or "").strip()
    if a in _AGENT_META:
        return _AGENT_META[a]
    if a in _RUNTIME_META:
        return _RUNTIME_META[a]
    # Unknown agent: title-case the slug, no blurb.
    label = a.replace("__", "").replace("_", " ").strip().title() or "Stage"
    return (label, "•", "")


def _safe_scalar(value: Any) -> Any | None:
    """Return value only if it is a safe, short scalar; else None."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        # Guard against absurd magnitudes / NaN leaking through.
        try:
            if value != value or abs(float(value)) > 1e12:  # NaN or huge
                return None
        except Exception:
            return None
        return value
    if isinstance(value, str):
        v = value.strip()
        if not v or len(v) > _MAX_HIGHLIGHT_STR:
            return None
        # A short string is only safe if it has no whitespace runs / newlines
        # that suggest free-form text or a leaked blob.
        if "\n" in v or "\t" in v:
            return None
        return v
    return None


def _safe_highlights(output_data: Any) -> dict[str, Any]:
    """Whitelist a handful of safe scalar highlights from a stage's output."""
    if not isinstance(output_data, dict):
        return {}
    out: dict[str, Any] = {}
    for src_key, label in _SAFE_HIGHLIGHT_KEYS.items():
        if src_key not in output_data:
            continue
        lname = src_key.lower()
        if any(bad in lname for bad in _FORBIDDEN_KEY_SUBSTRINGS):
            continue
        scalar = _safe_scalar(output_data.get(src_key))
        if scalar is None:
            continue
        out[label] = scalar
    return out


def _normalize_status(status: Any) -> str:
    s = str(status or "").strip().lower()
    if s in ("completed", "done", "success", "succeeded"):
        return "completed"
    if s in ("running", "in_progress", "started"):
        return "running"
    if s in ("failed", "error"):
        return "failed"
    if s in ("pending", "queued", "waiting"):
        return "pending"
    return s or "unknown"


def _duration_sec(started: Any, completed: Any) -> float | None:
    try:
        s = float(started) if started is not None else None
        c = float(completed) if completed is not None else None
    except (TypeError, ValueError):
        return None
    if s is None or c is None or c < s:
        return None
    return round(c - s, 1)


def _product_title(product: dict[str, Any]) -> str:
    meta = product.get("metadata") or {}
    spec = meta.get("spec") or {}
    name = None
    if isinstance(spec, dict):
        name = spec.get("product_name") or spec.get("name")
    title = (name or product.get("idea") or "Untitled build").strip()
    return title[:90]


def _is_shipped(state: Any) -> bool:
    return str(state or "").strip().upper() in ("COMPLETED", "DEPLOYED_PRODUCTION")


def _open_manager():
    """Open the pipeline SQLite store, or None if it does not exist yet."""
    from core.paths import pipeline_db_path
    from orchestrator.sqlite_manager import SQLiteManager

    db = pipeline_db_path()
    if not db.is_file():
        return None
    sm = SQLiteManager(str(db))
    sm.connect()
    return sm


def _stage_from_task(task: dict[str, Any]) -> dict[str, Any]:
    agent_type = str(task.get("agent_type") or "")
    label, emoji, blurb = _agent_presentation(agent_type)
    status = _normalize_status(task.get("status"))
    started = task.get("started_at")
    completed = task.get("completed_at")
    return {
        "agent": agent_type,
        "label": label,
        "emoji": emoji,
        "blurb": blurb,
        "state": str(task.get("state") or "").upper() or None,
        "status": status,
        "is_gate": agent_type in ("methodologist", "design_critic", "hardening", "spec_quality_gate"),
        "had_error": bool(task.get("error")),
        "retry_count": int(task.get("retry_count") or 0),
        "started_at": float(started) if started is not None else None,
        "completed_at": float(completed) if completed is not None else None,
        "created_at": float(task.get("created_at") or 0) or None,
        "duration_sec": _duration_sec(started, completed),
        "highlights": _safe_highlights(task.get("output_data")),
    }


def _summary_card(product: dict[str, Any], stages: list[dict[str, Any]]) -> dict[str, Any]:
    meta = product.get("metadata") or {}
    completed_stages = [s for s in stages if s["status"] == "completed"]
    total_seconds = sum(s["duration_sec"] or 0 for s in stages)
    repair_rounds = sum(1 for s in stages if s["retry_count"] > 0)
    return {
        "id": str(product.get("id") or ""),
        "title": _product_title(product),
        "idea": str(product.get("idea") or "")[:280],
        "state": str(product.get("state") or "").upper() or None,
        "category": (meta.get("category") or None),
        "shipped": _is_shipped(product.get("state")),
        "created_at": float(product.get("created_at") or 0) or None,
        "updated_at": float(product.get("updated_at") or 0) or None,
        "stage_count": len(stages),
        "completed_stage_count": len(completed_stages),
        "total_build_seconds": round(total_seconds, 1) if total_seconds else None,
        "repair_rounds": repair_rounds,
        "product_url": f"/product/{product.get('id')}",
    }


def get_build_replay(product_id: str) -> dict[str, Any] | None:
    """Public, sanitized replay for one product. None if it does not exist."""
    pid = str(product_id or "").strip()
    if not pid:
        return None
    sm = _open_manager()
    if sm is None:
        return None
    try:
        product = sm.get_product(pid)
        if product is None:
            return None
        tasks = sm.get_tasks_by_product(pid)
    finally:
        sm.close()

    # Order by created_at (worker writes one task per stage transition), then by
    # started_at as a tiebreaker. get_tasks_by_product already orders by
    # created_at ASC; re-sort defensively.
    tasks = sorted(
        tasks,
        key=lambda t: (
            float(t.get("created_at") or 0),
            float(t.get("started_at") or 0),
        ),
    )
    stages = [_stage_from_task(t) for t in tasks]
    summary = _summary_card(product, stages)
    return {"build": summary, "stages": stages}


def list_recent_builds(limit: int = 24) -> dict[str, Any]:
    """Public gallery feed: most recent builds as slim cards."""
    try:
        lim = max(1, min(int(limit), 60))
    except (TypeError, ValueError):
        lim = 24
    sm = _open_manager()
    if sm is None:
        return {"builds": [], "count": 0}
    try:
        products = sm.get_all_products()
        products.sort(key=lambda p: float(p.get("created_at") or 0), reverse=True)
        products = products[:lim]
        counts = sm.get_task_counts_for_product_ids([str(p.get("id") or "") for p in products])
    finally:
        sm.close()

    builds: list[dict[str, Any]] = []
    for p in products:
        pid = str(p.get("id") or "")
        meta = p.get("metadata") or {}
        tc = counts.get(pid, {}) if isinstance(counts, dict) else {}
        stage_count = int(tc.get("total", 0) or 0) if isinstance(tc, dict) else 0
        builds.append(
            {
                "id": pid,
                "title": _product_title(p),
                "state": str(p.get("state") or "").upper() or None,
                "category": (meta.get("category") or None),
                "shipped": _is_shipped(p.get("state")),
                "created_at": float(p.get("created_at") or 0) or None,
                "stage_count": stage_count,
                "replay_url": f"/build/{pid}",
                "product_url": f"/product/{pid}",
            }
        )
    return {"builds": builds, "count": len(builds)}
