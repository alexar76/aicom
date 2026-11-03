"""Hub capital pricing for Pulse Terminal (ACEX Phase 2)."""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi import HTTPException


# acex/ lives at monorepo root (sibling of aimarket-hub) or at /app/acex in Hub image.
def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for base in (here.parents[2], here.parents[1]):
        if (base / "acex").is_dir():
            return base
    return here.parents[2]


_REPO_ROOT = _repo_root()
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Guarded, because `acex` is a sibling monorepo DIRECTORY, not a dependency: it is not declared
# in pyproject, it is not packaged into the wheel, and the name `acex` on PyPI belongs to an
# unrelated project. The sys.path insertion above only finds it when a sibling acex/ exists —
# true in the monorepo and in the Hub image (Dockerfile copies it to /app/acex), false in every
# `pip install aimarket-hub`. Unguarded, this made `create_app()` raise ModuleNotFoundError, so
# a pip-installed hub could not boot at all: the module is imported unconditionally by api.py
# to register two /capital/pricing routes.
#
# Not a regression — the published 3.1.0 has the identical file — but a PyPI version can be
# yanked and never replaced, so shipping it again would spend a second version number on the
# same unbootable defect. The two routes now answer 503 instead of taking the whole app down;
# ACEX capital pricing is one optional feature, and the rest of the hub does not depend on it.
try:
    from acex.integrations.pricing import build_pricing_snapshot
except ImportError:  # pragma: no cover - exercised by the pip-install path, not the monorepo
    build_pricing_snapshot = None  # type: ignore[assignment]

from aimarket_hub.database import HubDatabase


def hub_capital_pricing(
    db: HubDatabase,
    *,
    chain: str = "any",
    listing_id: str | None = None,
    limit: int = 50,
) -> dict:
    if build_pricing_snapshot is None:
        # 503, not 500: the feature is absent, not broken. A pip-installed hub has no sibling
        # acex/ tree — see the guarded import above — and every other route works fine.
        raise HTTPException(
            status_code=503,
            detail=(
                "ACEX capital pricing is unavailable: the `acex` package is not importable. "
                "It ships with the monorepo and the Hub container image, not with the "
                "`aimarket-hub` distribution. Every other hub route is unaffected."
            ),
        )
    caps = db.list_capabilities(limit=1000)

    # Overlay live ACEX Agent IPO state (CapShares + distributed revenue) by product.
    overlay: dict = {}
    audit_overlay: dict = {}
    try:
        from aimarket_hub import acex_ipo

        for st in acex_ipo.list_listings(limit=500):
            if not st.get("error"):
                overlay[st["listing_id"]] = st
    except Exception:
        overlay = {}

    try:
        from aimarket_hub import acex_audit

        for st in acex_audit.list_audit_states(limit=500):
            if not st.get("error"):
                audit_overlay[st["listing_id"]] = st
    except Exception:
        audit_overlay = {}

    return build_pricing_snapshot(
        caps,
        chain=chain,
        listing_id=listing_id,
        limit=limit,
        ipo_overlay=overlay,
        audit_overlay=audit_overlay,
    )
