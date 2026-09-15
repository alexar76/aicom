"""
Requirements clarifier
======================
Builds an iterative clarification pack from a raw idea.
This helps PM/spec stages emulate human requirement discovery.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any
from core.logging_utils import log_suppressed

logger = logging.getLogger(__name__)


def build_clarification_pack(idea: str) -> dict:
    text = (idea or "").strip()
    lower = text.lower()
    audience_hint = "B2B teams" if any(k in lower for k in ("team", "company", "business", "enterprise")) else "end users"
    risk_hint = "integration and migration risk" if any(k in lower for k in ("api", "legacy", "migration", "database")) else "scope and UX risk"
    return {
        "summary": f"Clarification pass for idea: {text[:140]}",
        "assumptions_to_validate": [
            f"Primary audience is {audience_hint}",
            "Launch scope should prioritize one core workflow",
            "Success metric must be measurable in first 30 days",
        ],
        "questions": [
            "What is the single most painful user job-to-be-done?",
            "What is explicitly out-of-scope for v1?",
            "What evidence will prove this solves the target problem?",
            "What data/security constraints are non-negotiable?",
            f"What is the highest delivery risk ({risk_hint}) and mitigation?",
        ],
        "acceptance_probes": [
            "Each core feature maps to a measurable user outcome",
            "Each user story has testable acceptance criteria",
            "Non-functional requirements include latency and reliability targets",
        ],
    }


async def build_clarification_pack_llm(idea: str, llm_router: Any | None = None) -> dict:
    """
    LLM-backed clarification pack with deterministic fallback.
    """
    if llm_router is None:
        return build_clarification_pack(idea)
    prompt = f"""
You are a senior product analyst preparing discovery questions before writing a software specification.
Return JSON only with keys:
- summary (string)
- assumptions_to_validate (array of strings, >=3)
- questions (array of strings, >=5)
- acceptance_probes (array of strings, >=3)

Product idea:
{idea}
"""
    try:
        raw = await llm_router.generate(prompt=prompt, task_type="pm_analysis")
        raw = raw.strip()
        fence_match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", raw, flags=re.DOTALL | re.IGNORECASE)
        if fence_match:
            raw = fence_match.group(1).strip()
        if len(raw) > 100_000:
            raise ValueError("clarification payload too large")
        data = json.loads(raw)
        if isinstance(data, dict) and isinstance(data.get("questions"), list) and len(data["questions"]) >= 3:
            return data
    except Exception as _suppressed_exc:
        log_suppressed(logger, "non-fatal (web/backend/services/requirements_clarifier.py)", exc_info=_suppressed_exc)
    return build_clarification_pack(idea)
