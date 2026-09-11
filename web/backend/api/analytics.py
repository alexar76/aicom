"""Factory IQ analytics API — read-only data plane for the "watch it get smarter" dashboard.

Returns only the whitelisted scalar rollup from ``core.factory_iq`` (spec §9.4): EV
learning curve (live vs frozen), Factory IQ, ship-rate, cost-per-ship, and the active
playbook rule feed. No prompts, raw outputs, paths, or per-product internals — safe to
mirror publicly behind ``AIFACTORY_PUBLIC_IQ``.
"""

from __future__ import annotations

import logging
import os

from fastapi import APIRouter

from core.factory_iq import factory_iq_snapshot
from core.paths import data_root as factory_data_root

logger = logging.getLogger(__name__)

router = APIRouter(tags=["analytics-factory-iq"])


@router.get("/analytics/factory-iq")
async def analytics_factory_iq() -> dict:
    """Factory IQ snapshot for the Admin dashboard (learning curve + playbook feed)."""
    try:
        return factory_iq_snapshot(factory_data_root())
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("factory_iq snapshot failed: %s", exc)
        return {"factory_iq": None, "error": "unavailable"}


@router.get("/public/factory-iq")
async def public_factory_iq() -> dict:
    """Public mirror of the Factory IQ snapshot. Gated by ``AIFACTORY_PUBLIC_IQ=1``."""
    if (os.environ.get("AIFACTORY_PUBLIC_IQ", "") or "").strip().lower() not in ("1", "true", "yes", "on"):
        return {"enabled": False}
    try:
        snap = factory_iq_snapshot(factory_data_root())
        snap["enabled"] = True
        return snap
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("public factory_iq snapshot failed: %s", exc)
        return {"enabled": True, "factory_iq": None, "error": "unavailable"}
