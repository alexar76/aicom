"""
Re-verify terminal products against **current** marketplace / demo rules.

When gates or env thresholds change, completed products can become non-compliant.
This module schedules developer rework (same path as QA gate failure).
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any

from core.agent_roles import is_developer_agent
from core.paths import resolve_data_root
from core.quality_settings import max_pipeline_repair_rounds_for_delivery_profile
from web.backend.services.marketplace_quality import evaluate_marketplace_quality

logger = logging.getLogger(__name__)

_TERMINAL_STATES = frozenset({"COMPLETED", "DEPLOYED_PRODUCTION"})


def _truthy(name: str, default: str = "1") -> bool:
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes")


def _product_has_code(pid: str, data_root: str | Path | None = None) -> bool:
    """Same rules as storefront: manifest lists files that exist on disk."""
    product_code = resolve_data_root(data_root) / "code" / pid
    manifest_path = product_code / "code_manifest.json"
    if not manifest_path.exists():
        return False
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        files = manifest.get("files", [])
        if not files:
            return False
        for f_entry in files:
            fpath = f_entry.get("path") or f_entry.get("file_path", "")
            if fpath and (product_code / fpath).exists():
                return True
        return False
    except (OSError, json.JSONDecodeError):
        return False


def _load_spec_inner(pid: str, data_root: str | Path | None = None) -> dict | None:
    spec_path = resolve_data_root(data_root) / "specs" / pid / "specification.json"
    if not spec_path.is_file():
        return None
    try:
        raw = json.loads(spec_path.read_text(encoding="utf-8"))
        spec = raw.get("specification")
        return spec if isinstance(spec, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _dev_fixing_pending(task_queue: list, pid: str) -> bool:
    return any(
        t.get("product_id") == pid
        and is_developer_agent(t.get("agent_type"))
        and t.get("state") == "DEV_FIXING"
        and t.get("status") in ("pending", "running")
        for t in task_queue
    )


def apply_policy_audit(
    products: dict[str, Any],
    task_queue: list,
    now: float,
    *,
    data_root: str | Path | None = None,
) -> bool:
    """
    Audit COMPLETED / DEPLOYED products against current marketplace quality rules.
    On failure: BUG_FOUND + developer DEV_FIXING (or FAILED if repair budget exhausted).

    Returns True if pipeline state should be persisted.
    """
    if not _truthy("AIFACTORY_POLICY_AUDIT_ENABLED", "1"):
        return False

    changed = False

    for pid, product in list(products.items()):
        max_loops = max_pipeline_repair_rounds_for_delivery_profile(
            str(product.get("delivery_profile") or "") or None
        )
        state = (product.get("state") or "").upper()
        if state not in _TERMINAL_STATES:
            continue
        if not _product_has_code(pid, data_root):
            continue
        if _dev_fixing_pending(task_queue, pid):
            continue

        meta = product.get("metadata")
        if isinstance(meta, dict) and meta.get("operator_locked"):
            logger.debug("policy_audit skip %s (operator_locked metadata)", pid)
            continue
        if product.get("operator_locked"):
            logger.debug("policy_audit skip %s (operator_locked)", pid)
            continue
        try:
            from web.backend.services.product_followup import is_product_pipeline_on_hold

            if is_product_pipeline_on_hold(pid):
                logger.debug("policy_audit skip %s (pipeline_on_hold)", pid)
                continue
        except Exception:
            pass

        try:
            from core.paths import code_dir as product_code_dir
            from web.backend.services.visual_gate_autofix import apply_visual_gate_autofix

            apply_visual_gate_autofix(product_code_dir(pid))
        except Exception:
            logger.debug("policy_audit visual_gate_autofix skipped for %s", pid, exc_info=True)

        spec_inner = _load_spec_inner(pid, data_root)
        ev = evaluate_marketplace_quality(
            pid,
            specification=spec_inner,
            data_root=data_root,
            delivery_profile=str(product.get("delivery_profile") or "") or None,
        )

        if ev.get("eligible"):
            had_fail_flag = product.get("policy_audit_eligible") is False
            rr = int(product.get("quality_repair_round") or 0)
            product["last_policy_audit_at"] = now
            product["policy_audit_eligible"] = True
            try:
                from web.backend.services.product_followup import merge_mark_storefront_established_listing

                if merge_mark_storefront_established_listing(pid):
                    product["updated_at"] = now
                    changed = True
            except Exception:
                logger.debug("merge_mark_storefront_established_listing (policy audit) failed for %s", pid, exc_info=True)
            if rr > 0:
                product["quality_repair_round"] = 0
                product["updated_at"] = now
                changed = True
            elif had_fail_flag:
                product["updated_at"] = now
                changed = True
            logger.info("Policy audit OK for %s (marketplace rules)", pid)
            continue

        # Failed current rules — align with QA gate repair budget
        new_round = product.get("quality_repair_round", 0) + 1
        product["quality_repair_round"] = new_round
        product["updated_at"] = now
        product["last_policy_audit_at"] = now
        product["policy_audit_eligible"] = False

        demo = ev.get("demo_quality") or {}

        if new_round > max_loops:
            product["state"] = "FAILED"
            product["failure_reason"] = (
                "Policy/marketplace quality audit: product no longer meets current storefront "
                f"rules after {max_loops} repair attempts. Manual review or template update required."
            )
            logger.error(
                "Policy audit exhausted repairs for %s (%s > %s); state=FAILED",
                pid,
                new_round,
                max_loops,
            )
            changed = True
            continue

        product["state"] = "BUG_FOUND"
        dev_task = {
            "id": f"task-{uuid.uuid4().hex[:12]}",
            "product_id": pid,
            "agent_type": "developer",
            "state": "DEV_FIXING",
            "status": "pending",
            "retry_count": 0,
            "max_retries": 3,
            "input_data": {
                "product_id": pid,
                "idea": product.get("idea", ""),
                "demo_quality_feedback": demo,
                "quality_gates_feedback": {
                    "passed": False,
                    "demo_quality": demo,
                    "reasons": ev.get("reasons"),
                    "source": "policy_audit",
                },
                "quality_repair_round": new_round,
                "quality_repair_max": max_loops,
                "qa_gate_blocked": True,
                "policy_audit_trigger": True,
            },
            "created_at": now,
            "priority": 5,
        }
        task_queue.append(dev_task)
        logger.warning(
            "Policy audit failed for %s — BUG_FOUND → DEV_FIXING (repair %s/%s): %s",
            pid,
            new_round,
            max_loops,
            ev.get("reasons"),
        )
        changed = True

    return changed


def sync_sqlite_from_pipeline_json() -> None:
    """Legacy hook — worker persists via SQL; JSON→SQL import only when explicitly allowed."""
    from core.pipeline_state_writer import sync_sqlite_from_pipeline_json as _sync

    _sync()
