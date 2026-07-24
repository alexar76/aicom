"""
Spec compiler: normalize idea/admin intake into a structured brief.
"""

from __future__ import annotations

import re
from typing import Any

from web.backend.services.feedback_digest import build_feedback_digest
from web.backend.services.domain_playbooks import build_discovery_pack


def compile_product_brief(idea: str, admin_instructions: str = "") -> dict[str, Any]:
    text = f"{idea}\n{admin_instructions}".strip()
    blob = text.lower()
    audience_hints = []
    for kw in ("marketers", "developer", "product manager", "designer", "sales", "support", "founder", "team"):
        if kw in blob:
            audience_hints.append(kw)
    domain = "general"
    for d in ("fintech", "health", "education", "ai", "developer tools", "ecommerce", "saas"):
        if d in blob:
            domain = d
            break
    outcomes = [s.strip() for s in re.split(r"[.;]\s+|\n+", text) if len(s.strip()) > 20][:6]
    constraints = []
    for c in ("production", "security", "a11y", "accessibility", "performance", "mobile", "offline"):
        if c in blob:
            constraints.append(c)
    feedback_digest = {}
    try:
        feedback_digest = build_feedback_digest(window_hours=168)
    except Exception:
        feedback_digest = {"source": "feedback_digest_v1", "error": "unavailable"}
    discovery_pack = {}
    try:
        discovery_pack = build_discovery_pack(idea, admin_instructions)
    except Exception:
        discovery_pack = {"source": "discovery_pack_v1", "error": "unavailable"}
    return {
        "source": "spec_compiler_v1",
        "domain": domain,
        "audience_hints": audience_hints,
        "primary_outcomes": outcomes,
        "constraints": constraints,
        "recent_feedback_digest": feedback_digest,
        "discovery_pack": discovery_pack,
    }
