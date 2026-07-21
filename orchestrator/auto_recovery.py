"""
Pipeline auto-recovery: when QA/dev ping-pong stalls, verify current code and COMPLETE+lock.

Skips another developer round when automated gates pass and storefront is eligible.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from core.quality_settings import (
    auto_recovery_enabled,
    auto_recovery_min_repair_round,
    auto_recovery_require_storefront_eligible,
    auto_recovery_require_tests,
)
from web.backend.services.product_automated_verify import verify_product_automated
from web.backend.services.product_pipeline_complete import apply_product_completed_locked
from web.backend.services.product_storefront_refresh import refresh_product_storefront_telemetry

logger = logging.getLogger(__name__)


def _eligible_for_auto_recovery(product: dict[str, Any], *, repair_round: int) -> bool:
    if not auto_recovery_enabled():
        return False
    if product.get("operator_locked"):
        return False
    state = str(product.get("state") or "").upper()
    if state in ("COMPLETED", "DEPLOYED_PRODUCTION", "FAILED", "CANCELLED"):
        return False
    if repair_round < auto_recovery_min_repair_round():
        return False
    return True


def try_auto_recovery_after_qa_failure(
    product: dict[str, Any],
    task_queue: list[dict[str, Any]],
    *,
    repair_round: int,
    data_root: str | None = None,
) -> bool:
    """
    Attempt automated verify → refresh telemetry → COMPLETED+lock.

    Returns True when recovery succeeded (caller must skip developer queue).
    """
    pid = str(product.get("id") or "").strip()
    if not pid or not _eligible_for_auto_recovery(product, repair_round=repair_round):
        return False

    try:
        verify = verify_product_automated(
            pid,
            data_root=data_root,
            require_tests=auto_recovery_require_tests(),
        )
        if not verify.get("passed"):
            logger.info(
                "Auto-recovery skip %s (repair %s): verify failed (%s)",
                pid,
                repair_round,
                verify.get("reason") or "gates",
            )
            return False

        refresh = refresh_product_storefront_telemetry(pid, data_root=data_root)
        if auto_recovery_require_storefront_eligible() and not refresh.get("ok"):
            logger.info(
                "Auto-recovery skip %s: storefront not eligible (%s)",
                pid,
                (refresh.get("marketplace") or {}).get("reasons"),
            )
            return False

        apply_product_completed_locked(
            product,
            task_queue,
            now=time.time(),
            reason="auto_recovery",
        )
        logger.warning(
            "Product %s: auto-recovery COMPLETED+locked after repair round %s "
            "(demo=%s release=%s)",
            pid,
            repair_round,
            refresh.get("demo_score"),
            refresh.get("release_score"),
        )
        return True
    except Exception as exc:
        logger.warning("Auto-recovery failed for %s: %s", pid, exc, exc_info=True)
        return False
