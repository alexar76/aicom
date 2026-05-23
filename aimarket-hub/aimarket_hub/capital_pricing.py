"""Hub capital pricing for Pulse Terminal (ACEX Phase 2)."""

from __future__ import annotations

import sys
from pathlib import Path

# acex/integrations lives at repo root (sibling of aimarket-hub).
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from acex.integrations.pricing import build_pricing_snapshot  # noqa: E402

from aimarket_hub.database import HubDatabase  # noqa: E402


def hub_capital_pricing(
    db: HubDatabase,
    *,
    chain: str = "any",
    listing_id: str | None = None,
    limit: int = 50,
) -> dict:
    caps = db.list_capabilities(limit=1000)
    return build_pricing_snapshot(caps, chain=chain, listing_id=listing_id, limit=limit)
