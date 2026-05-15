"""Client-free heuristics for product creation defaults (mirrors frontend inferProductDefaultsFromIdea)."""

from __future__ import annotations

import re

_LANDING = re.compile(
    r"\b(landing|brochure|one[- ]?pager|lead\s*gen|marketing\s*page|coming\s*soon|waitlist|hero\s*section)\b",
    re.I,
)
_APP = re.compile(
    r"\b(saas|api|dashboard|auth|jwt|postgres|websocket|microservice|mobile\s*app|crm|erp|admin\s*panel)\b",
    re.I,
)


def suggest_delivery_profile(idea: str) -> str | None:
    t = (idea or "").strip()
    if len(t) < 12:
        return None
    if _LANDING.search(t) and not _APP.search(t):
        return "marketing_landing"
    if _APP.search(t) and not _LANDING.search(t):
        return "full_software"
    return None
