"""Public **build replay** API — the shareable `/build/{id}` permalink backend.

Read-only, no auth. Returns a sanitized agent-stage timeline (see
`web.backend.services.build_replay` for the security boundary) plus a recent
builds feed for the public gallery.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query

from web.backend.services.build_replay import get_build_replay, list_recent_builds

logger = logging.getLogger(__name__)

router = APIRouter(tags=["public-build-replay"])


@router.get("/public/builds")
async def public_builds(limit: int = Query(default=24, ge=1, le=60)) -> dict:
    """Recent builds as slim cards for the public gallery (`/builds`)."""
    try:
        return list_recent_builds(limit=limit)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("public_builds failed: %s", exc)
        return {"builds": [], "count": 0}


@router.get("/public/build/{product_id}")
async def public_build_replay(product_id: str) -> dict:
    """Sanitized agent-stage replay for one product (powers `/build/{id}`)."""
    try:
        replay = get_build_replay(product_id)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("public_build_replay(%s) failed: %s", product_id, exc)
        raise HTTPException(status_code=503, detail="replay unavailable") from exc
    if replay is None:
        raise HTTPException(status_code=404, detail="build not found")
    return replay
