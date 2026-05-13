"""
Delivery profile constants + normalization (no dependency on ``agents`` package).

Used by marketplace gates, quality settings, and orchestrator paths that must not
import the full agent stack at module load time.
"""

from __future__ import annotations

MARKETING_LANDING = "marketing_landing"
FULL_SOFTWARE = "full_software"


def normalize_delivery_profile(raw: str | None) -> str:
    if raw is None:
        return FULL_SOFTWARE
    key = str(raw).strip().lower().replace(" ", "_").replace("-", "_")
    if not key:
        return FULL_SOFTWARE
    if key in (
        "marketing_landing",
        "marketing",
        "landing_only",
        "promo_only",
        "brochure",
    ):
        return MARKETING_LANDING
    return FULL_SOFTWARE
