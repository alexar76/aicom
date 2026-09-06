"""Periodic UNI maintenance (treasury audit, hold expiry, withdraw dispatcher)."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_INTERVAL_SEC = 300


def _interval_sec() -> int:
    raw = os.environ.get("AIFACTORY_UNI_JOBS_INTERVAL_SEC", "").strip()
    try:
        return max(60, int(raw)) if raw else _DEFAULT_INTERVAL_SEC
    except ValueError:
        return _DEFAULT_INTERVAL_SEC


async def uni_scheduler_loop(app: Any) -> None:
    """Run UNI background jobs on a fixed interval while the web backend is up."""
    from core.uni.config import uni_enabled
    from core.uni.jobs import (
        run_holds_expirer_job,
        run_treasury_audit_job,
        run_withdraw_dispatcher_job,
    )

    interval = _interval_sec()
    logger.info("UNI scheduler loop started (interval=%ss)", interval)
    while True:
        try:
            if uni_enabled():
                audit = await asyncio.to_thread(run_treasury_audit_job)
                holds = await asyncio.to_thread(run_holds_expirer_job)
                withdraw = await asyncio.to_thread(run_withdraw_dispatcher_job)
                app.state.uni_jobs_last = {
                    "treasury": audit,
                    "holds": holds,
                    "withdraw": withdraw,
                }
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("UNI scheduler tick failed")
        await asyncio.sleep(interval)
