"""
Market research + product idea generation for autonomous pipeline.
Uses LLM preliminary research (training-data synthesis); idea must pass JSON validation.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from llm import GenerationConfig, LLMRouter
from llm.factory_defaults import FACTORY_MAX_OUTPUT_TOKENS_HEAVY
from marketplace_taxonomy import MARKETPLACE_CATEGORY_IDS, slug_to_marketplace_category

logger = logging.getLogger(__name__)

ALLOWED_CATEGORIES = frozenset(MARKETPLACE_CATEGORY_IDS)


def _strip_trademark_noise(s: str) -> str:
    """Remove fake ™/®/ТМ clutter from LLM briefs; marketing owns naming."""
    if not s:
        return s
    out = s
    for bad in (
        "\u2122",
        "\u00ae",
        "(TM)",
        "(tm)",
        "(R)",
        "ТМ",
        "®",
        "™",
    ):
        out = out.replace(bad, "")
    return " ".join(out.split())


def _parse_llm_json(text: str) -> dict[str, Any]:
    raw = (text or "").strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
    if fence:
        raw = fence.group(1).strip()
    return json.loads(raw)


def _pick_underrepresented_category(existing: list[str]) -> str:
    """Rotate storefront verticals so autonomous builds don't pile into one slug."""
    ordered = list(MARKETPLACE_CATEGORY_IDS)
    if not existing:
        return ordered[0]
    counts = {c: 0 for c in ordered}
    for c in existing:
        k = slug_to_marketplace_category(c)
        if k in counts:
            counts[k] += 1
    m = min(counts.values())
    for cid in ordered:
        if counts[cid] == m:
            return cid
    return "saas"


def _normalize_idea_payload(data: dict[str, Any], existing_categories: list[str] | None) -> dict[str, Any]:
    idea = _strip_trademark_noise(str(data.get("idea", "")).strip())
    if len(idea) < 20:
        raise ValueError("idea too short")
    raw_cat = data.get("category")
    if raw_cat is None or (isinstance(raw_cat, str) and not str(raw_cat).strip()):
        cat = _pick_underrepresented_category(existing_categories or [])
    else:
        cat = str(raw_cat).strip().lower().replace(" ", "_").replace("-", "_")
        if cat not in ALLOWED_CATEGORIES:
            cat = slug_to_marketplace_category(cat) or _pick_underrepresented_category(
                existing_categories or []
            )
    tags_raw = data.get("tags") or []
    if isinstance(tags_raw, str):
        tags = [t.strip() for t in tags_raw.split(",") if t.strip()]
    elif isinstance(tags_raw, list):
        tags = [str(t).strip() for t in tags_raw if str(t).strip()]
    else:
        tags = []
    tags = tags[:12] or ["saas", "b2b"]
    summary = _strip_trademark_noise(str(data.get("research_summary", "")).strip())
    rationale = _strip_trademark_noise(str(data.get("market_rationale", "")).strip())
    return {
        "idea": idea[:2000],
        "category": cat,
        "tags": tags,
        "research_summary": summary[:4000],
        "market_rationale": rationale[:4000],
    }


async def generate_product_from_market_research(
    existing_ideas: list[str],
    router: LLMRouter,
    existing_categories: list[str] | None = None,
) -> dict[str, Any]:
    """
    Run preliminary market research via LLM and return a validated product brief.

    existing_ideas: short strings from current pipeline (dedupe themes).
    """
    themes = "\n".join(f"- {t[:280]}" for t in existing_ideas[-20:]) if existing_ideas else "(none yet)"
    cat_slugs = ", ".join(MARKETPLACE_CATEGORY_IDS)
    recent_cats = ", ".join(str(c).strip() for c in (existing_categories or [])[-24:] if str(c).strip())
    if not recent_cats:
        recent_cats = "(none yet)"

    prompt = f"""You are inventing the NEXT autonomous build for an AI studio whose shipped artifact is a **ship-ready browser product slice**
(multi-file HTML/CSS/JS: clear IA, at least one credible interactive flow, README — not a bare one-liner homework page).

Perform concise preliminary research using general market knowledge (no browsing):
- Niche, primary user job-to-be-done, what screens or flows prove value in a demo.
- Differentiation vs obvious templates; one memorable hook (visual, interaction, or data story).
- **Visual differentiation:** the shipped UI must not look like every other “dark SaaS + cyan accent + glass card” clone. In `research_summary` and especially in **`idea`**, include **at least one concrete sentence** on art direction (palette + typography personality + one signature visual move) that a designer could execute — bold, category-appropriate, and **not** the same recipe as typical AI landing pages. Mention **SVG-first** hero or section treatments where vector art (patterns, illustrated shapes, mesh gradients) can replace generic stock imagery.
- Avoid duplicating these existing product themes:
{themes}

The Director will use your "idea" as the customer-facing phrase/brief for the pipeline.
Do not include ™, ®, (TM), or "ТМ" in any field — the Marketing agent will choose an artistic product name later.

Return ONLY valid JSON with keys:
{{
  "research_summary": "3-5 sentences: audience, pain, why this product slice wins attention now",
  "idea": "ONE sentence: describe the front-end slice to build (audience, core interaction, key screens). Sound like a PM/design brief for a credible mini-app or tool — no vague “nice website”.",
  "category": "exactly one slug from: {cat_slugs}",
  "tags": ["4-8 lowercase kebab-case tags; include the vertical, e.g. fintech, iot-sensor, devtools-cli"],
  "market_rationale": "who would adopt this slice first and why"
}}

**Category discipline:** `category` MUST be one of the slugs above (underscore form). Spread love across **all** storefront tabs over time: FinTech, E-Commerce, IoT, Security, DevTools, Productivity, AI/ML, and SaaS — do **not** default everything to generic SaaS. Prefer a vertical that is **under-represented** in recent autonomous builds.

Recent `category` values from the pipeline (bias toward the least frequent among these): {recent_cats}
No markdown, no code fences, JSON only."""

    cfg = GenerationConfig(
        temperature=0.45,
        max_tokens=FACTORY_MAX_OUTPUT_TOKENS_HEAVY,
        timeout_sec=120.0,
    )
    text = await router.generate(prompt, task_type="market_research", config=cfg)
    data = _parse_llm_json(text)
    if not isinstance(data, dict):
        raise ValueError("LLM returned non-object JSON")
    return _normalize_idea_payload(data, existing_categories)
