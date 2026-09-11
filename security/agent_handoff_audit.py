"""
Agent-to-agent handoff audit — tamper-evident pipeline transitions.

Logs each orchestrated transition (agent A finished → agent B queued) into the
same hash-chained ``AuditLogger`` store as admin security events. Payloads
store metadata and fingerprints only — not full LLM outputs or secrets.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from typing import Any

from core.paths import logs_dir

logger = logging.getLogger("ai_factory.security.agent_handoff")

_AUDIT: Any = None
_AUDIT_LOCK = threading.Lock()
_ACTION = "agent_handoff"


def _get_audit_logger():
    global _AUDIT
    if _AUDIT is not None:
        return _AUDIT
    with _AUDIT_LOCK:
        if _AUDIT is not None:
            return _AUDIT
        try:
            from security.audit_logger import AuditLogger

            _AUDIT = AuditLogger(log_dir=str(logs_dir() / "audit"))
        except Exception as exc:
            logger.warning("Agent handoff audit unavailable: %s", exc)
            _AUDIT = False
        return _AUDIT


def fingerprint_payload(data: Any, *, max_keys: int = 40) -> dict[str, Any]:
    """Summarize a dict for audit without storing values (PII/secret safe)."""
    if not isinstance(data, dict):
        return {"type": type(data).__name__, "size": 0}
    keys = sorted(str(k) for k in data)[:max_keys]
    blob = json.dumps(keys, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]
    return {"keys": keys, "key_count": len(data), "keys_digest": digest}


def log_agent_handoff(
    *,
    product_id: str,
    from_agent: str,
    to_agent: str,
    from_state: str = "",
    to_state: str = "",
    task_id: str = "",
    next_task_id: str = "",
    reason: str = "sequential",
    success: bool = True,
    blocked: bool = False,
    output_data: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> bool:
    """
    Append a hash-chained ``agent_handoff`` audit entry.

    Returns True when persisted, False when audit logger is unavailable.
    """
    audit = _get_audit_logger()
    if not audit or audit is False:
        return False

    details: dict[str, Any] = {
        "product_id": product_id,
        "from_agent": from_agent,
        "to_agent": to_agent,
        "from_state": from_state,
        "to_state": to_state,
        "task_id": task_id,
        "next_task_id": next_task_id,
        "reason": reason,
        "success": success,
        "blocked": blocked,
    }
    if output_data is not None:
        details["output_fingerprint"] = fingerprint_payload(output_data)
    if extra:
        details["extra"] = extra

    try:
        severity = "warning" if blocked or not success else "info"
        audit.log(
            action=_ACTION,
            actor=f"agent:{from_agent}",
            resource=f"pipeline/{product_id}",
            details=details,
            severity=severity,
        )
        return True
    except Exception as exc:
        logger.debug("Failed to log agent handoff: %s", exc)
        return False


def log_handoff_from_task(
    *,
    product_id: str,
    from_agent: str,
    from_state: str,
    next_task: dict[str, Any],
    task_id: str = "",
    reason: str = "sequential",
    success: bool = True,
    blocked: bool = False,
    output_data: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> bool:
    """Log handoff using the queued ``next_task`` dict from the pipeline worker."""
    return log_agent_handoff(
        product_id=product_id,
        from_agent=from_agent,
        to_agent=str(next_task.get("agent_type") or ""),
        from_state=from_state,
        to_state=str(next_task.get("state") or ""),
        task_id=task_id,
        next_task_id=str(next_task.get("id") or ""),
        reason=reason,
        success=success,
        blocked=blocked,
        output_data=output_data,
        extra=extra,
    )
