"""Optional LLM-backed prefill for New Product fields (short, low-token call)."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from llm import GenerationConfig

from web.backend.services.idea_creation_heuristic import suggest_delivery_profile
from core.logging_utils import log_suppressed

logger = logging.getLogger(__name__)

_VALID_DELIVERY = frozenset({"full_software", "marketing_landing", "infer"})


def _heuristic_fallback(idea: str) -> dict[str, Any]:
    sd = suggest_delivery_profile(idea)
    delivery = sd or "infer"
    reason = ""
    if sd == "marketing_landing":
        reason = "Heuristic: landing-style wording."
    elif sd == "full_software":
        reason = "Heuristic: app/platform-style wording."
    return {
        "delivery_profile": delivery,
        "production_mode": False,
        "instructions": "",
        "source": "heuristic",
        "rationale": reason,
    }


def _extract_json_object(text: str) -> dict[str, Any] | None:
    if not text:
        return None
    t = text.strip()
    try:
        obj = json.loads(t)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError as _suppressed_exc:
        log_suppressed(logger, "non-fatal (web/backend/services/idea_prefill_llm.py)", exc_info=_suppressed_exc)
    m = re.search(r"\{[\s\S]*\}\s*$", t)
    if m:
        try:
            obj = json.loads(m.group(0))
            return obj if isinstance(obj, dict) else None
        except json.JSONDecodeError:
            return None
    return None


def _normalize_llm_payload(raw: dict[str, Any], idea: str) -> dict[str, Any] | None:
    dp = str(raw.get("delivery_profile") or raw.get("delivery") or "").strip().lower()
    if dp not in _VALID_DELIVERY:
        dp = "infer"
    pm = raw.get("production_mode")
    if isinstance(pm, str):
        pm = pm.strip().lower() in ("1", "true", "yes", "production")
    prod_mode = bool(pm) if isinstance(pm, (bool, int)) else False
    instr = str(raw.get("instructions") or raw.get("admin_instructions") or "").strip()
    rationale = str(raw.get("rationale") or raw.get("reason") or "").strip()
    if len(instr) > 12000:
        instr = instr[:12000]
    return {
        "delivery_profile": dp,
        "production_mode": prod_mode,
        "instructions": instr,
        "source": "llm",
        "rationale": rationale[:2000],
    }


async def prefill_from_idea(idea: str, llm_router: Any | None) -> dict[str, Any]:
    idea_clean = (idea or "").strip()
    if not idea_clean:
        out = _heuristic_fallback("")
        out["source"] = "empty"
        return out

    if llm_router is None:
        return _heuristic_fallback(idea_clean)

    prompt = (
        "You help configure an AI software factory product run. Given the user's IDEA, "
        "reply with a single JSON object only, no markdown, keys:\n"
        '- "delivery_profile": one of "full_software", "marketing_landing", "infer"\n'
        '- "production_mode": boolean\n'
        '- "instructions": concise English instructions for agents (string, may be empty)\n'
        '- "rationale": one short sentence why these defaults fit\n'
        f"IDEA:\n{idea_clean[:8000]}\n"
    )
    cfg = GenerationConfig(
        temperature=0.25,
        max_tokens=512,
        timeout_sec=28.0,
        json_mode=True,
    )
    try:
        text = await llm_router.generate(prompt, task_type="pm_analysis", config=cfg)
    except Exception as e:
        logger.warning("idea_prefill_llm: generate failed: %s", e)
        out = _heuristic_fallback(idea_clean)
        out["source"] = "heuristic"
        out["rationale"] = (out.get("rationale") or "") + " (LLM unavailable)"
        return out

    parsed = _extract_json_object(text)
    if not parsed:
        out = _heuristic_fallback(idea_clean)
        out["source"] = "heuristic"
        out["rationale"] = (out.get("rationale") or "") + " (LLM JSON parse failed)"
        return out

    norm = _normalize_llm_payload(parsed, idea_clean)
    if not norm:
        out = _heuristic_fallback(idea_clean)
        out["source"] = "heuristic"
        return out
    return norm
