"""Intent-based capability discovery with LLM ranking and keyword fallback."""

from __future__ import annotations

import json
import re
from typing import Any

from web.backend.services.ai_market_protocol.catalog import (
    list_capabilities,
    list_factory_capabilities,
    parse_capability_ref,
)


def _draft_input(cap: dict[str, Any], query: str) -> dict[str, Any]:
    schema = cap.get("input_schema") or {}
    props = schema.get("properties") or {}
    cap_name, _ = parse_capability_ref(str(cap.get("capability_id") or ""))
    if "text" in props:
        draft: dict[str, Any] = {"text": query[:8000] if query else ""}
        if cap_name.startswith("translate"):
            draft["locales"] = ["ru", "en", "de", "fr", "ja"]
        return draft
    if "documents" in props:
        return {"documents": {"primary": query[:4000] if query else ""}, "jurisdiction": "US"}
    if "task" in props:
        return {"task": query[:4000] if query else "", "context": {}}
    return {"input": query[:2000] if query else ""}


# ---------------------------------------------------------------------------
# Keyword scoring (fallback)
# ---------------------------------------------------------------------------

def _keyword_score(cap: dict[str, Any], query: str, budget: float | None) -> float:
    q = query.lower()
    blob = f"{cap.get('name','')} {cap.get('description','')} {cap.get('capability_id','')}".lower()
    if not q:
        return 0.1
    if q in blob:
        score = 0.95
    else:
        tokens = [t for t in re.split(r"\W+", q) if len(t) > 2]
        if not tokens:
            return 0.0
        hits = sum(1 for t in tokens if t in blob)
        score = hits / max(1, len(tokens))
    if budget is not None and float(cap.get("price_per_call_usd") or 0) > budget:
        score *= 0.35
    return score


# ---------------------------------------------------------------------------
# LLM-powered semantic ranking
# ---------------------------------------------------------------------------

def _build_ranking_prompt(caps: list[dict[str, Any]], query: str, budget: float | None, limit: int) -> str:
    """Build a prompt for the LLM to rank capabilities."""
    budget_line = f"\nBudget constraint: ${budget:.2f} USD per call" if budget is not None else ""
    lines: list[str] = []
    for i, c in enumerate(caps):
        lines.append(
            f"{i}. {c['capability_id']} ({c['product_id']}) — "
            f"{c.get('description','')} — "
            f"${c.get('price_per_call_usd',0):.2f}/call, "
            f"{c.get('p50_latency_ms',0)}ms"
        )
    numbered = "\n".join(lines)
    return (
        f"Task: \"{query}\"{budget_line}\n\n"
        f"Available capabilities:\n{numbered}\n\n"
        f"Return a JSON array of the {limit} most relevant capability indices (integers), "
        f"sorted by relevance descending. Format: {{\"ranking\": [3, 0, 7, ...]}}"
    )


async def _llm_ranking(
    caps: list[dict[str, Any]],
    query: str,
    budget: float | None,
    limit: int,
    llm_router: Any,
) -> list[int] | None:
    """Ask the LLM to rank capabilities by intent match. Returns index list or None."""
    prompt = _build_ranking_prompt(caps, query, budget, limit)
    try:
        from llm.provider import GenerationConfig

        raw = await llm_router.generate(
            prompt=prompt,
            task_type="ai_market_discover",
            config=GenerationConfig(temperature=0.1, max_tokens=512, json_mode=True),
        )
        text = raw.strip()
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            m = re.search(r"\{[\s\S]*\}", text)
            if m:
                parsed = json.loads(m.group(0))
            else:
                return None
        ranking = parsed.get("ranking") if isinstance(parsed, dict) else None
        if isinstance(ranking, list) and all(isinstance(i, int) for i in ranking):
            return [i for i in ranking if 0 <= i < len(caps)]
        return None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def discover_capabilities(
    *,
    query: str,
    budget_usd: float | None = None,
    constraints: dict[str, Any] | None = None,
    limit: int = 8,
    llm_router: Any = None,
    catalog: str = "shipped",
) -> dict[str, Any]:
    constraints = constraints or {}
    max_latency = constraints.get("max_latency_ms")

    if catalog == "factory":
        all_caps = list_factory_capabilities()
    else:
        all_caps = list_capabilities()
    candidates: list[dict[str, Any]] = []
    for cap in all_caps:
        if max_latency is not None and int(cap.get("p50_latency_ms") or 0) > int(max_latency):
            continue
        candidates.append(cap)

    if not candidates:
        return {"query": query, "matches": [], "plan": [], "estimated_total_usd": 0, "protocol_version": "v1"}

    # LLM-powered ranking when router is available and query is non-trivial
    ranked_indices: list[int] | None = None
    if llm_router is not None and query.strip() and len(candidates) > 1:
        ranked_indices = await _llm_ranking(candidates, query, budget_usd, min(limit, len(candidates)), llm_router)

    # Build scored matches
    matches: list[dict[str, Any]] = []
    if ranked_indices:
        for rank, idx in enumerate(ranked_indices[:limit]):
            cap = candidates[idx]
            matches.append({
                "product_id": cap["product_id"],
                "capability_id": cap["capability_id"],
                "score": round(1.0 - rank * 0.08, 3),
                "price_per_call_usd": cap["price_per_call_usd"],
                "draft_input": _draft_input(cap, query),
                "why": [f"LLM-ranked at position {rank + 1}"],
            })
    else:
        # Keyword fallback
        scored: list[dict[str, Any]] = []
        for cap in candidates:
            sc = _keyword_score(cap, query, budget_usd)
            if sc <= 0.05:
                continue
            scored.append({
                "product_id": cap["product_id"],
                "capability_id": cap["capability_id"],
                "score": round(sc, 3),
                "price_per_call_usd": cap["price_per_call_usd"],
                "draft_input": _draft_input(cap, query),
                "why": [f"keyword match score={sc:.2f}"],
            })
        scored.sort(key=lambda x: x["score"], reverse=True)
        matches = scored[:limit]

    # Build execution plan from top matches + continuation hints
    plan: list[dict[str, Any]] = []
    if matches:
        first = matches[0]
        plan.append({
            "step": 1,
            "product_id": first["product_id"],
            "capability_id": first["capability_id"],
            "draft_input": first["draft_input"],
        })
        cap0 = next(
            (c for c in candidates if c["capability_id"] == first["capability_id"]),
            None,
        )
        if cap0:
            for hint in (cap0.get("suggested_next") or [])[:2]:
                if "/" in hint:
                    pid, cid = hint.split("/", 1)
                    c2 = next(
                        (c for c in candidates if c["product_id"] == pid and c["capability_id"] == cid),
                        None,
                    )
                    if c2:
                        plan.append({
                            "step": len(plan) + 1,
                            "product_id": pid,
                            "capability_id": cid,
                            "draft_input": _draft_input(c2, query),
                        })

    est = sum(
        float(next(
            (c["price_per_call_usd"] for c in candidates
             if c["product_id"] == s["product_id"] and c["capability_id"] == s["capability_id"]),
            0.5,
        ))
        for s in plan
    )
    return {
        "query": query,
        "matches": matches,
        "plan": plan,
        "estimated_total_usd": round(est, 2),
        "protocol_version": "v1",
    }
