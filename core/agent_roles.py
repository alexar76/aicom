"""Canonical agent-role families.

The landing fast-path uses dedicated agent types (``landing_architect`` /
``landing_developer``) that behave like their generic counterparts for pipeline
bookkeeping (active-task detection, false-FAILED recovery, hardening, progress).
Any site that special-cases ``"developer"`` / ``"architect"`` against a raw task
``agent_type`` must treat the landing variants the same way — use these helpers
instead of bare ``== "developer"`` comparisons so the two never drift apart.
"""

from __future__ import annotations

DEVELOPER_AGENT_TYPES = frozenset({"developer", "landing_developer"})
ARCHITECT_AGENT_TYPES = frozenset({"architect", "landing_architect"})


def is_developer_agent(agent_type: str | None) -> bool:
    """True for the developer family (generic + landing fast-path)."""
    return str(agent_type or "") in DEVELOPER_AGENT_TYPES


def is_architect_agent(agent_type: str | None) -> bool:
    """True for the architect family (generic + landing fast-path)."""
    return str(agent_type or "") in ARCHITECT_AGENT_TYPES
