"""
Product delivery profile — drives PM depth, spec gate, and architect emphasis.
"""
from __future__ import annotations

import os
import re

from core.delivery_profile import DESKTOP_APP, FULL_SOFTWARE, MARKETING_LANDING, normalize_delivery_profile

__all__ = [
    "DESKTOP_APP",
    "FULL_SOFTWARE",
    "MARKETING_LANDING",
    "normalize_delivery_profile",
    "infer_delivery_profile",
    "post_devops_human_gate_required",
    "admin_charter_forces_landing_only",
    "research_artifact_implies_full_product",
]


def infer_delivery_profile(admin_instructions: str | None, idea: str | None) -> str:
    """
    Infer profile from admin text + idea when product has no explicit delivery_profile.
    full_software when build clearly targets an app/service with backend or rich client.
    """
    a = (admin_instructions or "").lower()
    i = (idea or "").lower()
    blob = f"{a}\n{i}"

    # Explicit operator charter in admin instructions wins over all heuristics.
    if admin_charter_forces_landing_only(admin_instructions):
        return MARKETING_LANDING

    desktop_markers = (
        "desktop app",
        "desktop application",
        "electron",
        "tauri",
        "flutter desktop",
        "native client",
        "native app",
        "system tray",
        "macos app",
        "windows app",
        "linux app",
        "offline-first desktop",
        "desktop tool",
        "installable app",
    )
    if any(x in blob for x in desktop_markers):
        return DESKTOP_APP

    # Strong backend / platform signals — prefer full_software even if copy says "page"
    strong_backend = any(
        h in blob
        for h in (
            "rest api",
            "graphql",
            "database",
            "postgresql",
            "mysql",
            "mongodb",
            "microservices",
            "authentication service",
            "oauth provider",
            "multi-tenant",
            "webhook receiver",
            "crud api",
            "fastapi",
            "django",
            "flask",
            "nestjs",
            "express.js",
            "express api",
            "spring boot",
            "go api",
            "gin-gonic",
            "websocket server",
            "real-time sync",
            "payment processing",
            "stripe integration",
            "asp.net",
            "aspnet",
            "dotnet",
            ".net core",
            "c# web api",
            "minimal api",
        )
    )

    # Brochure-only deliverables — **narrow** phrases so generic SaaS ideas default to full_software.
    # (Words like "landing page" alone appear in almost every pitch and wrongly forced brochure mode.)
    landing_markers = (
        "marketing landing",
        "landing page only",
        "only a landing page",
        "just a landing page",
        "single-page marketing",
        "single page marketing",
        "promo page",
        "one html page",
        "brochure site",
        "brochure only",
        "sales page only",
        "single-scroll",
        "single scroll",
        "scroll landing",
        "one-pager",
        "one pager",
        "brochure page",
        "promotional page only",
        "portfolio page only",
    )
    mobile_or_native = any(
        m in blob
        for m in (
            "mobile app",
            "ios app",
            "android app",
            "react native",
            "flutter app",
            "flutter desktop",
        )
    )
    # Nuclear option for operators: default everything to full product (brochure needs explicit charter or --landing).
    if os.getenv("AIFACTORY_FORCE_FULL_SOFTWARE", "").strip().lower() in ("1", "true", "yes"):
        return FULL_SOFTWARE

    if not strong_backend and not mobile_or_native and any(x in blob for x in landing_markers):
        return MARKETING_LANDING

    # Full product signals
    full_hints = (
        "full software",
        "full_software",
        "full-stack",
        "full stack",
        "saas application",
        "web application",
        "rest api",
        "graphql",
        "database",
        "postgresql",
        "authentication service",
        "microservices",
        "backend +",
        "backend and",
        "mobile app",
        "multi-tenant",
        "admin dashboard",
        "customer portal",
        "multi-page app",
        "authenticated users",
    )
    if any(h in blob for h in full_hints):
        return FULL_SOFTWARE

    if re.search(r"\b(api|backend|crud|dashboard app|spa)\b", blob) and "landing" not in blob:
        return FULL_SOFTWARE

    return FULL_SOFTWARE


def research_artifact_implies_full_product(research_json_text: str) -> bool:
    """
    Analyst JSON (stringified) suggests shipping more than a brochure:
    competitors, pricing, integrations, workflow depth — use to escalate PM profile when pipeline defaulted landing.
    """
    if not research_json_text or not str(research_json_text).strip():
        return False
    b = str(research_json_text).lower()
    signals = (
        "competitor",
        "competitive",
        "pricing",
        "subscription",
        "integration",
        "workflow",
        "saas",
        "platform",
        "enterprise",
        "dashboard",
        "differentiation",
        "market gap",
        "feature gap",
        "retention",
        "monetization",
        "api",
        "multi-tenant",
    )
    hits = sum(1 for s in signals if s in b)
    return hits >= 2


def post_devops_human_gate_required(product: dict | None) -> bool:
    """
    Full-software builds pause after DevOps until an operator approves (via admin API).
    Marketing-landing-only profiles skip this gate.

    Env:
      AIFACTORY_POST_DEVOPS_HUMAN_GATE — explicit override: off/false/0 or on/true/1
      AIFACTORY_HUMAN_REVIEW_REQUIRED — default on (1): gate applies when profile is full_software;
        set to 0/false/no to disable unless POST_DEVOPS override forces it on.
    """
    if not isinstance(product, dict):
        return False
    explicit = os.getenv("AIFACTORY_POST_DEVOPS_HUMAN_GATE", "").strip().lower()
    if explicit in ("0", "false", "no", "off"):
        return False
    if explicit in ("1", "true", "yes", "on"):
        return True
    if os.getenv("AIFACTORY_HUMAN_REVIEW_REQUIRED", "1").strip().lower() in ("0", "false", "no"):
        return False
    dp = product.get("delivery_profile")
    if dp:
        prof = normalize_delivery_profile(str(dp))
    else:
        prof = infer_delivery_profile(product.get("admin_instructions"), product.get("idea"))
    return prof in (FULL_SOFTWARE, DESKTOP_APP)


def admin_charter_forces_landing_only(admin_instructions: str | None) -> bool:
    """True when admin text is an explicit factory/marketing-landing-only charter — do not escalate profile."""
    low = (admin_instructions or "").lower()
    needles = (
        "delivery_profile for pm/spec: marketing_landing",
        "primary deliverable (guest): exactly one **business marketing landing",
        "brochure-only page",
        "landing page only",
        "single-page marketing",
        "marketing_landing only",
        "do not ship a python cli",
    )
    return any(n in low for n in needles)


def idea_charter_forces_landing_only(idea: str | None) -> bool:
    """
    True when the product idea is an explicit marketing-landing charter.

    Prevents PM from escalating ``marketing_landing`` → ``full_software`` after analyst
  research mentions competitors/pricing (common on demo + guest landing briefs).
    """
    low = (idea or "").strip().lower()
    if not low:
        return False
    if low.startswith(("marketing landing", "marketing-landing")):
        return True
    needles = (
        "marketing landing —",
        "marketing landing -",
        "marketing landing:",
        "single-scroll landing",
        "scroll landing",
        "one-pager",
        "one pager",
        "brochure page",
        "promo page only",
        "promotional page only",
    )
    return any(n in low for n in needles)
