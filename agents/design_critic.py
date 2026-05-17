"""
from agents.prompts.load_prompt import load_prompt
Design Critic Agent
===================
Blocking art-direction loop after architecture and before development.

Inputs: architecture + design_pipeline/variants (from architect artifacts).
Outputs: taste-level metrics + blockers to send architect for iteration.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from .base_agent import BaseAgent, AgentInput, AgentOutput
from llm import LLMRouter, GenerationConfig
from llm.factory_defaults import FACTORY_MAX_OUTPUT_TOKENS_HEAVY, FACTORY_TIMEOUT_ARCHITECTURE_SEC


DESIGN_CRITIC_SYSTEM = load_prompt("design_critic_system_prompt.md")


def _load_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _heuristic_score(arch: dict, selected_variant: dict) -> tuple[int, list[str]]:
    issues: list[str] = []
    ux = arch.get("ui_experience") if isinstance(arch, dict) else {}
    if not isinstance(ux, dict):
        ux = {}
    tokens = ux.get("css_variables") if isinstance(ux.get("css_variables"), dict) else {}
    svg = str(ux.get("svg_creative_brief") or "").strip()
    mood = str(ux.get("mood") or "").strip()
    if len(tokens) < 6:
        issues.append("ui_experience.css_variables too small (need >=6 tokens)")
    if len(svg) < 120:
        issues.append("svg_creative_brief too shallow (need concrete hero + section SVG plan)")
    if len(mood) < 80:
        issues.append("mood too generic/short (need product-specific art direction)")

    sv_svg = str(selected_variant.get("svg_creative_brief") or "").strip() if isinstance(selected_variant, dict) else ""
    if sv_svg and len(sv_svg) < 120:
        issues.append("selected_variant svg brief too shallow")

    base = 78
    base -= min(25, len(issues) * 8)
    return max(0, min(100, base)), issues


class DesignCriticAgent(BaseAgent):
    def __init__(self, llm_router: LLMRouter):
        super().__init__(
            agent_type="design_critic",
            llm_router=llm_router,
            task_type="design_critic",
        )

    async def execute(self, agent_input: AgentInput) -> AgentOutput:
        start = time.time()
        pid = agent_input.product_id
        production_mode = bool(agent_input.data.get("production_mode"))

        arch_path = Path(self.data_root / "arch" / pid / "architecture.json")
        pipe_path = Path(self.data_root / "arch" / pid / "design_pipeline.json")
        arch_doc = _load_json(arch_path)
        pipe_doc = _load_json(pipe_path)

        arch = arch_doc.get("architecture") if isinstance(arch_doc, dict) else {}
        if not isinstance(arch, dict):
            arch = {}
        selected = pipe_doc.get("selected_variant") if isinstance(pipe_doc, dict) else {}
        if not isinstance(selected, dict):
            selected = {}

        # Heuristic quick pass first
        heuristic_score, heuristic_issues = _heuristic_score(arch, selected)

        prompt = (
            f"{DESIGN_CRITIC_SYSTEM}\n\n"
            f"Product idea:\n{agent_input.data.get('idea','')}\n\n"
            f"Architecture.ui_experience:\n{json.dumps(arch.get('ui_experience', {}), ensure_ascii=False, indent=2)}\n\n"
            f"Selected design variant:\n{json.dumps(selected, ensure_ascii=False, indent=2)}\n\n"
            f"Heuristic pre-score={heuristic_score} issues={heuristic_issues}\n"
        )

        result = None
        try:
            cfg = GenerationConfig(
                temperature=0.2,
                max_tokens=FACTORY_MAX_OUTPUT_TOKENS_HEAVY,
                timeout_sec=FACTORY_TIMEOUT_ARCHITECTURE_SEC,
                json_mode=True,
            )
            raw = await self._generate(prompt, config=cfg, agent_input=agent_input)
            result = self._extract_json(raw)
        except Exception:
            result = None

        if not isinstance(result, dict):
            # Fallback to heuristics when LLM is unavailable
            passed = heuristic_score >= (82 if production_mode else 72)
            result = {
                "passed": passed,
                "design_score": heuristic_score,
                "scores": {
                    "originality": heuristic_score,
                    "clarity": heuristic_score,
                    "brand_coherence": heuristic_score,
                    "feasibility": heuristic_score,
                    "accessibility": heuristic_score,
                },
                "issues": heuristic_issues if not passed else [],
                "recommendations": [
                    "Add stronger SVG hero direction (one scene/metaphor, section dividers, icon system).",
                    "Ensure tokens include bg/surface/text/accent/radius/shadow and are used consistently.",
                ],
            }

        # Enforce strict threshold in production
        min_score = 86 if production_mode else 74
        passed = bool(result.get("passed")) and int(result.get("design_score") or 0) >= min_score
        issues = list(result.get("issues") or [])
        if int(result.get("design_score") or 0) < min_score:
            issues.append(f"design_score below threshold ({result.get('design_score')} < {min_score})")

        out = dict(result)
        out["passed"] = passed
        out["issues"] = issues
        out["min_score"] = min_score

        # Persist critique artifact
        self._save_artifact(
            pid,
            "arch",
            {
                "product_id": pid,
                "design_critic": out,
                "created_at": time.time(),
                "agent": "design_critic",
            },
            "design_critique.json",
        )

        elapsed = time.time() - start
        return AgentOutput(
            task_id=agent_input.task_id,
            product_id=pid,
            agent_type=self.agent_type,
            success=True,
            data={
                "design_critic": out,
                "design_score": out.get("design_score"),
                "peer_review": {
                    "recommended": "approve" if passed else "block",
                    "blockers": issues if not passed else [],
                    "notes": "Design critic gate: art direction must be distinct and implementable.",
                },
            },
            timestamp=time.time(),
            metrics={"elapsed_seconds": elapsed},
        )

