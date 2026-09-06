"""AI Surrogate Reviewer — heavy-tier judge replaces human evaluators at gates."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from core.autonomy_mode import is_full_autonomy
from core.quality_settings import gate_failing_model
from core.surrogate_review import (
    SurrogateVerdict,
    apply_confidence_policy,
    autonomy_max_judge_calls,
    fail_safe_verdict,
    get_judge_call_count,
    increment_judge_call_count,
    is_point_surrogate_eligible,
    parse_verdict_json,
)
from llm.router import GenerationConfig, LLMRouter

logger = logging.getLogger(__name__)


def _judge_model() -> str | None:
    v = os.environ.get("AIFACTORY_AUTONOMY_JUDGE_MODEL", "").strip()
    if v:
        return v
    return gate_failing_model()


def _escalation_model() -> str | None:
    v = os.environ.get("AIFACTORY_AUTONOMY_ESCALATION_MODEL", "").strip()
    if v:
        return v
    return _judge_model()


def _build_prompt(point: str, product: dict[str, Any], context: dict[str, Any]) -> str:
    brief = {
        "point": point,
        "product_id": product.get("id"),
        "idea": (product.get("idea") or "")[:2000],
        "category": product.get("category"),
        "delivery_profile": product.get("delivery_profile"),
        "state": product.get("state"),
        "human_review_kind": product.get("human_review_kind"),
        "human_review_reason": product.get("human_review_reason"),
        "quality_repair_round": product.get("quality_repair_round"),
        "context": context,
    }
    return f"""You are the AI Surrogate Reviewer for an autonomous software factory.
Evaluate the intervention point and respond with JSON only (no markdown).

Intervention point: {point}

Product snapshot:
{json.dumps(brief, ensure_ascii=False, indent=2)}

Rules:
- decision must be one of: approve, block, fill
- approve: gate passes, product may advance
- block: gate fails, send to repair or FAILED (fail closed when uncertain)
- fill: provide structured owner/director input in "fill" object
- confidence: 0.0-1.0 (be conservative; below 0.55 will auto-block)
- rationale: short audit-grade reason (max 500 chars)

Respond with exactly this JSON shape:
{{"decision":"approve|block|fill","fill":{{}},"confidence":0.0,"rationale":"..."}}
"""


class SurrogateReviewer:
    def __init__(self, data_root: Path, llm_router: LLMRouter | None = None):
        self.data_root = Path(data_root)
        self._router = llm_router

    def _router_or_create(self) -> LLMRouter:
        if self._router is None:
            self._router = LLMRouter()
        return self._router

    async def decide(
        self,
        point: str,
        product: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> SurrogateVerdict:
        pid = str(product.get("id") or "")
        ctx = context or {}
        if not is_full_autonomy():
            return fail_safe_verdict(point, pid, "supervised mode")
        if not is_point_surrogate_eligible(point):
            return fail_safe_verdict(point, pid, f"point not surrogate-eligible: {point}")
        if get_judge_call_count(self.data_root, pid) >= autonomy_max_judge_calls():
            return fail_safe_verdict(point, pid, "judge call budget exhausted")

        increment_judge_call_count(self.data_root, pid)
        router = self._router_or_create()
        model = _judge_model()
        prompt = _build_prompt(point, product, ctx)
        cfg = GenerationConfig(timeout_sec=90, model_override=model, task_type="quality_gate")
        judge_label = model or "heavy"

        try:
            raw = await router.generate(prompt=prompt, task_type="quality_gate", config=cfg)
            verdict = parse_verdict_json(raw, point=point, product_id=pid, judge_model=judge_label)
        except Exception as exc:
            logger.warning("Surrogate judge failed for %s/%s: %s", pid, point, exc)
            verdict = fail_safe_verdict(point, pid, f"judge error: {exc}")

        if verdict.confidence < float(os.environ.get("AIFACTORY_AUTONOMY_MIN_CONFIDENCE", "0.55")):
            esc_model = _escalation_model()
            if esc_model and esc_model != model:
                try:
                    esc_cfg = GenerationConfig(timeout_sec=120, model_override=esc_model, task_type="quality_gate")
                    raw2 = await router.generate(
                        prompt=prompt + "\n\nPrevious low-confidence attempt — decide again, be explicit.",
                        task_type="quality_gate",
                        config=esc_cfg,
                    )
                    verdict2 = parse_verdict_json(raw2, point=point, product_id=pid, judge_model=esc_model)
                    verdict2.escalated = True
                    verdict = verdict2
                except Exception as exc:
                    logger.warning("Surrogate escalation failed for %s: %s", pid, exc)

        # L3: tighten the approve threshold for gates that have been over-confident.
        try:
            from core.calibration import calibrated_min_confidence
            from core.surrogate_review import autonomy_min_confidence

            threshold = calibrated_min_confidence(self.data_root, point, autonomy_min_confidence())
        except Exception:
            threshold = None
        return apply_confidence_policy(verdict, point=point, min_confidence=threshold)
