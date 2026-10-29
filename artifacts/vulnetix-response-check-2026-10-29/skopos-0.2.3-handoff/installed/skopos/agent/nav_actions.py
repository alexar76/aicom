"""Allowlisted in-app navigation actions for the floating agent.

The model may append tags like ``[[nav:observability/hub]]``; we strip them from
the visible reply and return structured actions for the widget to execute
(sidebar page_link click + optional tab deeplink). No free-form URLs or scripts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

# page_key → Streamlit URL slug fragment (href path ends with this)
PAGE_SLUGS: dict[str, str] = {
    "analytics": "",  # dashboard root
    "dashboard": "",
    "security": "Security",
    "observability": "Observability",
    "fleet": "Fleet",
    "settings": "Settings",
    "history": "Scan_History",
    "scan_history": "Scan_History",
    "docs": "Documentation",
    "documentation": "Documentation",
    "quick_start": "Quick_Start",
    "wizard": "Quick_Start",
}

PAGE_TABS: dict[str, frozenset[str]] = {
    "analytics": frozenset(
        {"overview", "geo", "audience", "content", "sources", "journal", "system"}
    ),
    "dashboard": frozenset(
        {"overview", "geo", "audience", "content", "sources", "journal", "system"}
    ),
    "security": frozenset(
        {"score", "report", "overview", "ports", "knocks", "resources", "audit", "3d", "agent"}
    ),
    "observability": frozenset({"overview", "hub", "factory", "mesh", "graph"}),
    "history": frozenset({"timeline", "trend", "compare", "log"}),
    "scan_history": frozenset({"timeline", "trend", "compare", "log"}),
}

_NAV_TAG_RE = re.compile(
    r"\[\[\s*nav\s*:\s*([a-z0-9_]+)(?:\s*/\s*([a-z0-9_]+))?\s*\]\]",
    re.IGNORECASE,
)

_NAV_PROTOCOL = """
## In-app navigation (mandatory when guiding the operator)

When the operator should open a SKOPOS screen, append exactly one tag at the end
of your reply (after the prose). The UI opens it automatically; do not invent URLs.

Tags (allowlist only):
- [[nav:analytics]] or [[nav:analytics/overview|geo|audience|content|sources|journal|system]]
- [[nav:security]] or [[nav:security/score|report|overview|ports|knocks|resources|audit|3d|agent]]
- [[nav:observability]] or [[nav:observability/overview|hub|factory|mesh|graph]]
- [[nav:fleet]]
- [[nav:settings]]
- [[nav:history]]
- [[nav:docs]]
- [[nav:quick_start]]

Examples:
- Hub / 402 metrics → end with [[nav:observability/hub]]
- Exposed ports → [[nav:security/ports]]
- Traffic geography → [[nav:analytics/geo]]

Never emit more than two [[nav:…]] tags. Never emit javascript:, data:, or http links for in-app nav.
"""


@dataclass(frozen=True)
class NavAction:
    type: str  # always "navigate"
    page: str
    tab: str | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"type": self.type, "page": self.page}
        if self.tab:
            out["tab"] = self.tab
        return out


def navigation_protocol_for_prompt() -> str:
    return _NAV_PROTOCOL.strip()


def normalize_page_key(page: str) -> str | None:
    key = (page or "").strip().lower().replace("-", "_")
    if key in PAGE_SLUGS:
        return "analytics" if key == "dashboard" else ("history" if key == "scan_history" else key)
    return None


def extract_nav_actions(reply: str) -> tuple[str, list[NavAction]]:
    """Strip ``[[nav:…]]`` tags from ``reply`` and return allowlisted actions."""
    if not reply:
        return "", []
    actions: list[NavAction] = []
    seen: set[tuple[str, str | None]] = set()

    def _repl(match: re.Match[str]) -> str:
        page_raw = match.group(1) or ""
        tab_raw = match.group(2)
        page = normalize_page_key(page_raw)
        if page is None:
            return ""
        tab = (tab_raw or "").strip().lower() or None
        if tab:
            allowed = PAGE_TABS.get(page) or PAGE_TABS.get(page_raw.lower())
            if not allowed or tab not in allowed:
                tab = None
        key = (page, tab)
        if key not in seen and len(actions) < 2:
            seen.add(key)
            actions.append(NavAction(type="navigate", page=page, tab=tab))
        return ""

    cleaned = _NAV_TAG_RE.sub(_repl, reply)
    # Collapse leftover blank lines from stripped tags
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned, actions
