"""
Stakeholder-facing narrative for how a product was defined (idea → marketing → PM spec).
Presented as a structured «discussion» for the storefront; backed by real artifacts on disk.
"""

from __future__ import annotations

from typing import Any, Optional


def build_stakeholder_brief(
    product_id: str,
    idea: str,
    spec: Optional[dict],
    marketing: Optional[dict],
) -> dict[str, Any]:
    spec = spec if isinstance(spec, dict) else {}
    marketing = marketing if isinstance(marketing, dict) else {}

    product_name = (
        spec.get("product_name")
        or marketing.get("product_name")
        or (idea[:80] if idea else product_id)
    )

    tagline = marketing.get("tagline") or ""
    audience = spec.get("target_audience") or marketing.get("target_audience") or ""
    selling = marketing.get("selling_description") or marketing.get("short_description") or ""
    spec_desc = spec.get("description") or ""

    turns: list[dict[str, str]] = []

    turns.append(
        {
            "role": "director",
            "display_name": "Director",
            "title": "Strategy & pipeline charter",
            "body": (
                f"We green-lit **{product_name}** from the following charter:\n\n"
                f"> {idea.strip() or '—'}\n\n"
                "The autonomous **11-role factory path** (analyst → PM → architect with **Designer/UX** "
                "(`ui_experience`) → developer → QA → security → DevOps → marketing → sales → evolution) "
                "must deliver a shippable demo that reflects this direction."
            ),
        }
    )

    m_parts = []
    if tagline:
        m_parts.append(f"**Positioning:** {tagline}")
    if audience:
        m_parts.append(f"**Audience:** {audience}")
    if selling:
        m_parts.append(f"**Pitch:** {selling}")
    if marketing.get("key_benefits"):
        kb = marketing["key_benefits"]
        if isinstance(kb, list) and kb:
            m_parts.append("**Key benefits:** " + "; ".join(str(x) for x in kb[:6]))

    turns.append(
        {
            "role": "marketing",
            "display_name": "Marketing",
            "title": "Market framing & go-to-market",
            "body": "\n\n".join(m_parts) if m_parts else "Marketing artifact not persisted yet for this product.",
        }
    )

    pm_parts = []
    if spec_desc:
        pm_parts.append(f"**Summary:** {spec_desc}")
    feats = spec.get("core_features") or []
    if isinstance(feats, list) and feats:
        lines = []
        for f in feats[:12]:
            if isinstance(f, dict):
                nm = f.get("name", "")
                ds = f.get("description", "")
                pr = f.get("priority", "")
                lines.append(f"- **{nm}** ({pr}) — {ds}")
            elif isinstance(f, str):
                lines.append(f"- {f}")
        if lines:
            pm_parts.append("**Scope (core features):**\n" + "\n".join(lines))
    stories = spec.get("user_stories") or []
    if isinstance(stories, list) and stories:
        sl = []
        for s in stories[:8]:
            if isinstance(s, dict) and s.get("story"):
                sl.append(f"- {s['story']}")
            elif isinstance(s, str):
                sl.append(f"- {s}")
        if sl:
            pm_parts.append("**User stories:**\n" + "\n".join(sl))

    risks = spec.get("technical_risks") or []
    if isinstance(risks, list) and risks:
        pm_parts.append("**Risks:** " + "; ".join(str(r) for r in risks[:6]))

    turns.append(
        {
            "role": "pm",
            "display_name": "Product (PM agent)",
            "title": "Technical specification (build contract)",
            "body": "\n\n".join(pm_parts)
            if pm_parts
            else "Specification fields are empty — the PM stage may not have completed for this product.",
        }
    )

    return {
        "product_id": product_id,
        "product_name": product_name,
        "format_version": 1,
        "turns": turns,
        "footer_note": "This narrative is assembled from your pipeline artifacts (idea, marketing JSON, PM specification). "
        "Corporate chat sessions that reference this product appear separately in the admin console.",
    }
