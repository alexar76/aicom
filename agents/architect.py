"""
Architect Agent
===============
Responsible for:
- Designing system architecture
- Defining component structure
- Planning data models and APIs
- Technology stack decisions
"""

from __future__ import annotations

import json
import logging
import time

from llm import GenerationConfig, LLMRouter
from llm.agent_prompt_split import (
    build_architect_system_prompt,
    build_architect_user_data,
    format_user_data_message,
)
from llm.content_languages import ensure_architecture_content_language
from llm.factory_defaults import FACTORY_MAX_OUTPUT_TOKENS_HEAVY, FACTORY_TIMEOUT_ARCHITECTURE_SEC

from agents.architect_contracts import _ensure_implementation_contract
from agents.architect_ui import (
    _build_design_pipeline,
    _build_design_system,
    _design_variants,
    _ensure_ui_experience,
    _is_generic_ui_brief,
    _novelty_score_against_recent_ui,
    _rank_design_variants,
)
from agents.prompt_utils import prompt_json
from agents.prompts.architect_role import ARCHITECT_SYSTEM_PROMPT
from agents.prompts.load_prompt import load_prompt

from .base_agent import AgentInput, AgentOutput, BaseAgent

logger = logging.getLogger(__name__)


class ArchitectAgent(BaseAgent):
    """Architect Agent - designs system architecture from specifications."""

    def __init__(self, llm_router: LLMRouter, data_root: str | None = None):
        super().__init__(
            agent_type="architect",
            llm_router=llm_router,
            task_type="architecture_design",
            data_root=data_root,
        )

    async def execute(self, agent_input: AgentInput) -> AgentOutput:
        start_time = time.time()
        product_id = agent_input.product_id
        spec = agent_input.data.get("specification", {})
        idea = agent_input.data.get("idea", "")
        production_mode = bool(agent_input.data.get("production_mode"))
        peer_feedback = agent_input.data.get("peer_review_feedback")

        self._log("INFO", f"Designing architecture for {product_id}")

        try:
            spec_str = prompt_json(spec) if spec else idea
            admin_raw = (agent_input.data.get("admin_instructions") or "").strip()
            admin_l = admin_raw.lower()
            blob_l = spec_str.lower()

            research_context = ""
            research_path = self.data_root / "state" / product_id / "market_research.json"
            if research_path.is_file():
                try:
                    raw_mr = json.loads(research_path.read_text(encoding="utf-8"))
                    research_context = prompt_json(raw_mr, limit=28_000)
                    self._log("INFO", "Architect loaded market_research.json for context")
                except (json.JSONDecodeError, OSError) as e:
                    self._log("WARNING", f"Architect could not read market research: {e}")
            landing_charter = any(
                k in admin_l or k in blob_l
                for k in (
                    "marketing landing",
                    "landing page",
                    "single scroll",
                    "promo page",
                    "html/css/js",
                    "single-page",
                    "promotional",
                )
            )

            landing_note = ""
            if landing_charter:
                landing_note = (
                    "\nThis build is **landing-first**. Prefer static files only; align components with the Product Idea phrase.\n"
                )

            full_sw = isinstance(spec, dict) and spec.get("delivery_profile") == "full_software"
            full_note = ""
            if full_sw and not landing_charter:
                full_note = (
                    "\nThis build is **full_software**: design **runnable** services — persistence models, API contracts, "
                    "auth/session boundaries, and deployment topology — exactly as demanded by functional_requirements. "
                    "You MUST emit a complete **implementation_contract** JSON object (repository_layout, runnable_services, "
                    "data_plane, docker_compose, testing_contract, verification_commands, forbidden_shortcuts). Root **docker-compose.yml** must "
                    "orchestrate every service in data_plane (Postgres/Redis in containers, not mystery host daemons) except "
                    "file-only SQLite when explicit. **testing_contract** must mandate component/unit → functional/integration → UI/e2e "
                    "in that order; if Postgres/MySQL/Mongo appear in data_plane, include **sandbox_demo_credentials** with seeded "
                    "user + env-driven prefilled login forms.\n"
                    "The Developer will ship Python/Node/.NET/React files accordingly — not a "
                    "single marketing HTML file pretending to be the whole product.\n"
                    "Market research (when attached below) should inform integration posture and differentiation surfaces.\n"
                )

            ux_note = ""
            if landing_charter or (isinstance(spec, dict) and spec.get("delivery_profile") == "marketing_landing"):
                ux_note = (
                    "\nInclude a **rich `ui_experience` object** (designer-quality: tokens, typography, motion, "
                    "signature_moment). The Developer will implement it literally alongside HTML/CSS.\n"
                )
            elif full_sw and not landing_charter:
                ux_note = (
                    "\nInclude a **rich, distinctive `ui_experience` object** for the shipped browser UI (same fields as "
                    "landing mode). **Visual diversity:** pick a bold art direction that fits THIS product — not the "
                    "same dark+cyan+glass formula as every other build; the Developer binds to these tokens.\n"
                )

            methodology_block = ""
            meth_path = self.data_root / "state" / product_id / "methodology_spec_review.json"
            if meth_path.is_file():
                try:
                    mr = json.loads(meth_path.read_text(encoding="utf-8"))
                    blob = prompt_json(mr, limit=28_000)
                    methodology_block = (
                        "\n=== DOMAIN METHODOLOGY REVIEW (pre-architecture; treat as TZ backlog) ===\n"
                        "Resolve `findings` in components, data_models, api_endpoints, and acceptance-oriented notes. "
                        "If `passed` is false, architecture must close the gaps (entities, capabilities, lifecycle) "
                        "without shrinking agreed scope.\n"
                        f"{blob}\n"
                    )
                    self._log("INFO", "Architect loaded methodology_spec_review.json for remediation backlog")
                except (json.JSONDecodeError, OSError) as e:
                    self._log("WARNING", f"Architect could not read methodology review: {e}")

            interface_locale = agent_input.data.get("interface_locale")
            product_content_locale = agent_input.data.get("content_locale")

            prompt = format_user_data_message(
                build_architect_user_data(
                    idea=idea,
                    spec=spec if isinstance(spec, dict) else {},
                    admin_instructions=admin_raw,
                    landing_charter=landing_charter,
                    peer_feedback=peer_feedback,
                    research_context=research_context,
                    methodology_block=methodology_block,
                    landing_note=landing_note,
                    full_note=full_note,
                    ux_note=ux_note,
                    interface_locale=str(interface_locale) if interface_locale else None,
                    content_locale=str(product_content_locale) if product_content_locale else None,
                )
            )
            system_prompt = build_architect_system_prompt(
                ARCHITECT_SYSTEM_PROMPT,
                github_house_contract=load_prompt("github_house_contract.md"),
            )

            config = GenerationConfig(
                temperature=0.7,
                max_tokens=FACTORY_MAX_OUTPUT_TOKENS_HEAVY,
                timeout_sec=FACTORY_TIMEOUT_ARCHITECTURE_SEC,
                json_mode=True,  # openai_compatible skips response_format for reasoning models
            )

            response = await self._generate(
                prompt,
                config=config,
                agent_input=agent_input,
                system_prompt=system_prompt,
            )

            arch = self._extract_json(response)
            if arch is None:
                elapsed = time.time() - start_time
                self._log("WARNING", f"Architecture generation failed: LLM returned non-JSON response for {product_id}")
                return AgentOutput(
                    task_id=agent_input.task_id,
                    product_id=product_id,
                    agent_type=self.agent_type,
                    success=False,
                    error="LLM returned invalid/non-JSON response — architecture generation failed",
                    timestamp=time.time(),
                    metrics={"elapsed_seconds": elapsed},
                )

            _ensure_implementation_contract(
                arch,
                spec if isinstance(spec, dict) else {},
                idea,
                landing_charter=landing_charter,
            )

            brief_for_lang = "\n".join(
                p
                for p in (
                    str(idea or ""),
                    admin_raw,
                    json.dumps(spec, ensure_ascii=False) if isinstance(spec, dict) else "",
                )
                if p
            )
            lang_code = ensure_architecture_content_language(
                arch,
                product_content_locale=product_content_locale,
                interface_locale=interface_locale,
                user_text=brief_for_lang,
            )
            self._log("INFO", f"content_language={lang_code} for {product_id}")

            if _ensure_ui_experience(arch, spec if isinstance(spec, dict) else {}, landing_charter, idea):
                self._log("INFO", "ui_experience was missing or shallow — applied factory default for browser UI")
            design_system = _build_design_system(arch)
            design_pipeline = _build_design_pipeline(arch)
            design_variants = _design_variants(idea, 3)
            ranked_variants, selected_variant = _rank_design_variants(
                design_variants,
                arch.get("ui_experience") if isinstance(arch, dict) else {},
            )
            novelty = _novelty_score_against_recent_ui(arch.get("ui_experience") if isinstance(arch, dict) else {})
            if production_mode:
                ux = arch.get("ui_experience") if isinstance(arch, dict) else {}
                if _is_generic_ui_brief(ux):
                    raise RuntimeError("production_mode: architecture ui_experience is too generic")
                if novelty < 0.18:
                    raise RuntimeError(
                        f"production_mode: novelty score too low ({novelty:.2f}) vs recent architecture outputs"
                    )

            self._save_artifact(product_id, "arch", {
                "product_id": product_id,
                "architecture": arch,
                "design_system": design_system,
                "novelty_score": round(novelty, 3),
                "created_at": time.time(),
                "agent": "architect",
            }, "architecture.json")
            self._save_artifact(
                product_id,
                "arch",
                {
                    "product_id": product_id,
                    "design_system": design_system,
                    "design_pipeline": design_pipeline,
                    "created_at": time.time(),
                    "agent": "architect",
                },
                "design_system.json",
            )
            self._save_artifact(
                product_id,
                "arch",
                {
                    "product_id": product_id,
                    "design_pipeline": design_pipeline,
                    "design_variants": ranked_variants,
                    "selected_variant": selected_variant,
                    "created_at": time.time(),
                    "agent": "architect",
                },
                "design_pipeline.json",
            )

            elapsed = time.time() - start_time
            self._log("INFO", f"Architecture design complete ({elapsed:.1f}s)")

            return AgentOutput(
                task_id=agent_input.task_id,
                product_id=product_id,
                agent_type=self.agent_type,
                success=True,
                data={
                    "architecture": arch,
                    "design_system": design_system,
                    "design_pipeline": design_pipeline,
                    "design_variants": ranked_variants,
                    "selected_variant": selected_variant,
                    "novelty_score": round(novelty, 3),
                    "arch_file": f"arch/{product_id}/architecture.json",
                    "peer_review": {
                        "recommended": "approve",
                        "blockers": [],
                        "notes": "Architecture/design pipeline prepared for implementation.",
                    },
                },
                timestamp=time.time(),
                metrics={"elapsed_seconds": elapsed},
            )

        except Exception as e:
            elapsed = time.time() - start_time
            self._log("ERROR", f"Architecture design failed: {e}")
            return AgentOutput(
                task_id=agent_input.task_id,
                product_id=product_id,
                agent_type=self.agent_type,
                success=False,
                error=str(e),
                timestamp=time.time(),
                metrics={"elapsed_seconds": elapsed},
            )
