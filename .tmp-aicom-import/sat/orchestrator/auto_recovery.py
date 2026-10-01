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


def _probe_live_demo_login(url: str) -> int | None:
    """POST factory demo credentials at the live origin. None if the probe itself failed."""
    import json
    import urllib.error
    import urllib.request

    from core.demo_identity import sandbox_demo_email
    from web.backend.services.demo_credentials import effective_sandbox_demo_password_for_compose

    login_url = url.rstrip("/") + "/api/auth/login"
    payload = json.dumps(
        {
            "email": sandbox_demo_email(),
            "password": effective_sandbox_demo_password_for_compose(),
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        login_url,
        data=payload,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return int(getattr(resp, "status", 200) or 200)
    except urllib.error.HTTPError as exc:
        return int(exc.code)
    except Exception as exc:
        logger.debug("Auto-recovery live login probe failed for %s: %s", url[:80], exc)
        return None


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

        from web.backend.services.live_deployment_gate import live_gate_blocks_completion

        blocked = live_gate_blocks_completion(product)
        if blocked:
            logger.info(
                "Auto-recovery skip %s (repair %s): live gate blocks completion (%s)",
                pid,
                repair_round,
                blocked[:160],
            )
            return False

        # Verify/storefront scores can be green while the product still has hollow mesh
        # (capability declared, never invoked → live advisory "mesh response unavailable").
        # Completing over that is what stranded Sentinel after round 42.
        try:
            from core.paths import code_dir as resolve_code_dir
            from web.backend.services.duplicate_module_check import find_capabilities_never_invoked

            code_root = resolve_code_dir(pid, data_root=data_root) if data_root else resolve_code_dir(pid)
            if code_root.is_dir():
                hollow = find_capabilities_never_invoked(code_root, limit=5)
                if hollow:
                    logger.info(
                        "Auto-recovery skip %s (repair %s): capability_never_invoked (%s)",
                        pid,
                        repair_round,
                        (hollow[0].get("file") or "")[:80],
                    )
                    return False
        except Exception as exc:
            logger.debug("Auto-recovery capability probe failed for %s: %s", pid, exc)

        # Soft mesh UNKNOWN on the live URL: storefront can still look eligible.
        url = (
            str(product.get("vercel_url") or "").strip()
            or str((product.get("metadata") or {}).get("vercel_url") or "").strip()
        )
        try:
            import json
            import urllib.request

            if not url and data_root:
                from pathlib import Path

                ap = Path(data_root) / "state" / pid / "auto_publish.json"
                if ap.is_file():
                    rec = json.loads(ap.read_text(encoding="utf-8"))
                    url = str(
                        rec.get("vercel_url")
                        or (rec.get("vercel") or {}).get("published_url")
                        or ""
                    ).strip()
            if url:
                probe = url.rstrip("/") + "/api/advisory?lat=34.05&lon=-118.25"
                with urllib.request.urlopen(probe, timeout=25) as resp:
                    body = json.loads(resp.read().decode("utf-8", errors="replace"))
                reason = str(((body.get("overall") or {}) if isinstance(body, dict) else {}).get("reason") or "")
                soft = reason.lower()
                if (
                    "mesh response unavailable" in soft
                    or "payment_authorization" in soft
                    or "all connection attempts failed" in soft
                ):
                    logger.info(
                        "Auto-recovery skip %s (repair %s): live soft mesh (%s)",
                        pid,
                        repair_round,
                        reason[:100],
                    )
                    return False
        except Exception as exc:
            logger.debug("Auto-recovery live mesh probe failed for %s: %s", pid, exc)

        if url:
            login_status = _probe_live_demo_login(url)
            if login_status in (401, 403):
                logger.info(
                    "Auto-recovery skip %s (repair %s): live demo login HTTP %s",
                    pid,
                    repair_round,
                    login_status,
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
