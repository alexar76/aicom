"""
QA repair budget: extend before human review; never fail the product on first budget exhaustion.
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def qa_repair_max_extensions() -> int:
    raw = os.environ.get("AIFACTORY_QA_REPAIR_EXTENSIONS", "2")
    try:
        return max(0, int(raw))
    except ValueError:
        return 2


def resolve_qa_repair_after_failure(
    product: dict[str, Any],
    *,
    new_repair_round: int,
    max_quality_loops: int,
) -> tuple[bool, int, str]:
    """
    Decide state after QA gate failure once repair round is incremented.

    Returns:
        (quality_gates_exhausted, effective_repair_round_for_dev_task, product_state)
    """
    pid = str(product.get("id") or "")
    if new_repair_round <= max_quality_loops:
        return False, new_repair_round, "BUG_FOUND"

    extensions = int(product.get("qa_repair_extensions") or 0)
    max_ext = qa_repair_max_extensions()
    if extensions < max_ext:
        product["qa_repair_extensions"] = extensions + 1
        product["quality_repair_round"] = 0
        product.pop("failure_reason", None)
        product.pop("human_review_kind", None)
        logger.warning(
            "Product %s: QA repair budget extended (%s/%s) — continuing DEV_FIXING "
            "(round reset, max=%s)",
            pid,
            extensions + 1,
            max_ext,
            max_quality_loops,
        )
        return False, 0, "BUG_FOUND"

    product.pop("failure_reason", None)
    product["human_review_kind"] = "qa_repair_exhausted"
    product["human_review_reason"] = (
        f"QA gates not satisfied after {max_quality_loops} repair cycles × "
        f"{max_ext + 1} budget extensions. Operator review — approve to grant another repair cycle."
    )
    logger.warning(
        "Product %s: QA repair budgets exhausted — HUMAN_REVIEW_PENDING (not FAILED)",
        pid,
    )
    return True, new_repair_round, "HUMAN_REVIEW_PENDING"


def resolve_security_repair_after_failure(
    product: dict[str, Any],
    *,
    new_sec_round: int,
    max_security_loops: int,
) -> tuple[bool, str]:
    """Same philosophy for security gate repair budget."""
    pid = str(product.get("id") or "")
    if new_sec_round <= max_security_loops:
        return False, "BUG_FOUND"

    extensions = int(product.get("security_repair_extensions") or 0)
    max_ext = qa_repair_max_extensions()
    if extensions < max_ext:
        product["security_repair_extensions"] = extensions + 1
        product["security_repair_round"] = 0
        product.pop("failure_reason", None)
        logger.warning(
            "Product %s: security repair budget extended (%s/%s)",
            pid,
            extensions + 1,
            max_ext,
        )
        return False, "BUG_FOUND"

    product.pop("failure_reason", None)
    product["human_review_kind"] = "security_repair_exhausted"
    product["human_review_reason"] = (
        f"Security gate not satisfied after {max_security_loops} repair cycles. "
        "Operator review required to continue."
    )
    return True, "HUMAN_REVIEW_PENDING"


def notify_qa_human_review_pending(product_id: str, product: dict[str, Any]) -> None:
    try:
        from web.backend.services.pipeline_chat_notify import notify_pipeline_event

        notify_pipeline_event(
            product_id,
            title="Pipeline needs human review",
            body=str(product.get("human_review_reason") or "QA repair budget exhausted"),
            level="warning",
        )
    except Exception:
        logger.debug("pipeline_chat_notify skipped for %s human review", product_id, exc_info=True)
