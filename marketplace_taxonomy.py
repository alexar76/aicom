"""
Vertical topic slugs for Director / agents / canonical listing category.

Storefront also exposes a separate ``landings`` shelf (marketing_landing only); see
``web/backend/api/products.py`` LISTING_CATEGORY_IDS — do not add ``landings`` here or the LLM may mis-assign topics.

Keep in sync with tab labels in web/frontend (lib/categories.ts, app/page.tsx), minus ``landings``.
"""

from __future__ import annotations

from typing import Any, Optional

# Canonical IDs used in /api/products and marketplace UI
MARKETPLACE_CATEGORY_IDS: tuple[str, ...] = (
    "ai_ml",
    "devtools",
    "fintech",
    "saas",
    "ecommerce",
    "iot",
    "security",
    "productivity",
)

_MARKETPLACE_CATEGORY_SET = frozenset(MARKETPLACE_CATEGORY_IDS)


def slug_to_marketplace_category(raw: Any) -> Optional[str]:
    """
    Map a free-text or slug value to a storefront category id, or None if unknown.
    """
    if raw is None:
        return None
    if isinstance(raw, str) and not raw.strip():
        return None
    s = str(raw).strip().lower().replace(" ", "_").replace("-", "_")
    aliases: dict[str, Optional[str]] = {
        "ai/ml": "ai_ml",
        "machine_learning": "ai_ml",
        "artificial_intelligence": "ai_ml",
        "generative_ai": "ai_ml",
        "ml": "ai_ml",
        "llm": "ai_ml",
        "dev_tools": "devtools",
        "developer_tools": "devtools",
        "fintech": "fintech",
        "fin_tech": "fintech",
        "finance": "fintech",
        "payments": "fintech",
        "e_commerce": "ecommerce",
        "ecommerce": "ecommerce",
        "e-commerce": "ecommerce",
        "retail": "ecommerce",
        "saas": "saas",
        "software_as_a_service": "saas",
        "b2b_saas": "saas",
        "iot": "iot",
        "internet_of_things": "iot",
        "embedded": "iot",
        "security": "security",
        "cybersecurity": "security",
        "infosec": "security",
        "productivity": "productivity",
        "collaboration": "productivity",
        "workflow": "productivity",
        # funnel noise to None so caller can fall back to product.category
        "uncategorized": None,
        "other": None,
        "general": None,
        "misc": None,
        "technology": None,
        "business": None,
        "software": None,
    }
    mapped = aliases.get(s, s)
    if mapped is None:
        return None
    if mapped in _MARKETPLACE_CATEGORY_SET:
        return mapped
    return None


def infer_marketplace_category_from_signals(product: dict, marketing: Optional[dict] = None) -> Optional[str]:
    """
    Last-resort bucket from idea + tags (+ optional marketing blurbs).
    Order: specific niches before broad saas.
    """
    parts: list[str] = [
        str(product.get("idea") or ""),
        " ".join(str(t) for t in (product.get("tags") or []) if t),
    ]
    if marketing:
        parts.extend(
            [
                str(marketing.get("long_description") or ""),
                str(marketing.get("short_description") or ""),
                str(marketing.get("tagline") or ""),
                " ".join(str(k) for k in (marketing.get("seo_metadata") or {}).get("keywords", []) or []),
            ]
        )
    blob = " ".join(parts).lower()

    rules: tuple[tuple[str, tuple[str, ...]], ...] = (
        ("ai_ml", ("llm", "gpt", "neural", "embedding", "classifier", "inference", "training data", "torch", "tensorflow")),
        ("devtools", ("cli for dev", "git hook", "cicd", "linter", "compiler", "sdk", "debugger", "api client", "localhost")),
        ("fintech", ("payment", "invoice", "ledger", "portfolio", "defi", "trading", "budget", "expense", "receipt", "tax")),
        ("ecommerce", ("cart", "checkout", "catalog", "sku", "inventory", "dropship", "seller", "storefront")),
        ("iot", ("sensor", "mqtt", "firmware", "embedded", "smart device", "edge device")),
        ("security", ("sso", "oauth", "encrypt", "vulnerability", "xss", "audit log", "secrets", "mfa")),
        ("productivity", ("kanban", "calendar", "reminder", "notes app", "tasks", "time track", "meeting")),
        ("saas", ("dashboard", "crm", "subscription", "workspace", "team", "multi-tenant")),
    )
    for cat_id, kws in rules:
        if any(k in blob for k in kws):
            return cat_id
    return None


def canonical_marketplace_category(marketing: dict, product: dict) -> str:
    """
    Resolve listing category: pipeline product.category wins over marketing LLM noise;
    then keyword inference; else uncategorized (UI: Other).
    """
    p = slug_to_marketplace_category(product.get("category"))
    if p:
        return p
    m = slug_to_marketplace_category((marketing or {}).get("category"))
    if m:
        return m
    inferred = infer_marketplace_category_from_signals(product, marketing)
    if inferred:
        return inferred
    return "uncategorized"
