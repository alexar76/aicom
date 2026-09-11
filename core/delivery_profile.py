"""
Delivery profile constants + normalization (no dependency on ``agents`` package).

Used by marketplace gates, quality settings, and orchestrator paths that must not
import the full agent stack at module load time.
"""

from __future__ import annotations

MARKETING_LANDING = "marketing_landing"
FULL_SOFTWARE = "full_software"
DESKTOP_APP = "desktop_app"


def normalize_delivery_profile(raw: str | None) -> str:
    if raw is None:
        return FULL_SOFTWARE
    key = str(raw).strip().lower().replace(" ", "_").replace("-", "_")
    if not key:
        return FULL_SOFTWARE
    if key in (
        "marketing_landing",
        "marketing",
        "landing",
        "landing_only",
        "promo_only",
        "brochure",
    ):
        return MARKETING_LANDING
    if key in (
        "desktop_app",
        "desktop",
        "desktop_application",
        "native_app",
        "electron_app",
        "tauri_app",
        "flutter_desktop",
    ):
        return DESKTOP_APP
    return FULL_SOFTWARE


def is_desktop_delivery_profile(raw: str | None) -> bool:
    return normalize_delivery_profile(raw) == DESKTOP_APP
