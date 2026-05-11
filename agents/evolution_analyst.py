"""
Evolution Analyst Agent (KILLER FEATURE)
=========================================
Responsible for:
- Analyzing product telemetry
- Identifying improvement opportunities
- Suggesting auto-improvements
- Tracking product evolution metrics
- Generating evolution reports
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from core.telemetry_signals import extract_evolution_signals_from_jsonl_dir

from .base_agent import BaseAgent, AgentInput, AgentOutput
from llm import LLMRouter, GenerationConfig
from llm.factory_defaults import FACTORY_MAX_OUTPUT_TOKENS_HEAVY, FACTORY_TIMEOUT_DEFAULT_AGENT_SEC

EVOLUTION_SYSTEM_PROMPT = """You are the Evolution Analyst Agent for an AI-powered software factory.
This is the KILLER FEATURE — you autonomously improve products based on telemetry.

For each product, you must:
1. Analyze usage telemetry and user behavior
2. Identify patterns and pain points
3. Suggest concrete improvements
4. Prioritize improvements by impact
5. Generate evolution report
6. Weight explicit **evolution_signal** rows (from `/api/telemetry/evolution-signal`) alongside saved JSON artifacts

Output format: JSON with fields:
- product_health_score: number (0-100)
- usage_metrics: {active_users, avg_session_duration, feature_usage, drop_off_points}
- improvements: list of {priority, title, description, expected_impact, effort, category}
- auto_fixes_applied: list of {issue, fix, result}
- evolution_recommendations: list of string
- next_iteration_focus: string
"""


class EvolutionAnalystAgent(BaseAgent):
    """Evolution Analyst Agent - analyzes telemetry and suggests improvements."""

    def __init__(self, llm_router: LLMRouter):
        super().__init__(
            agent_type="evolution_analyst",
            llm_router=llm_router,
            task_type="evolution_analysis",
        )

    async def execute(self, agent_input: AgentInput) -> AgentOutput:
        start_time = time.time()
        product_id = agent_input.product_id
        telemetry = agent_input.data.get("telemetry", {})
        spec = agent_input.data.get("specification", {})

        self._log("INFO", f"Analyzing evolution for {product_id}")

        try:
            # Load telemetry data
            telemetry_files = self._list_artifacts(product_id, "telemetry")
            telemetry_data = {}
            for fname in telemetry_files[-5:]:  # Last 5 telemetry files
                data = self._load_artifact(product_id, "telemetry", fname)
                if data:
                    telemetry_data[fname] = data

            telemetry_str = json.dumps(telemetry_data, indent=2) if telemetry_data else "No telemetry data available"
            tel_dir = Path(self.data_root) / "telemetry" / product_id
            evolution_signals = extract_evolution_signals_from_jsonl_dir(tel_dir, limit=200)
            signals_str = (
                json.dumps(evolution_signals[-120:], indent=2)
                if evolution_signals
                else "No evolution_signal JSONL events recorded yet."
            )
            spec_str = json.dumps(spec, indent=2) if spec else "{}"

            try:
                from web.backend.services.owner_chat_routing import format_owner_product_feedback_for_prompt

                owner_fb = format_owner_product_feedback_for_prompt(product_id)
            except Exception:
                owner_fb = ""
            owner_block = (owner_fb + "\n\n") if owner_fb else ""

            prompt = f"""{EVOLUTION_SYSTEM_PROMPT}

Product ID: {product_id}

{owner_block}Telemetry JSON artifacts (saved evolution reports / bundles):
{telemetry_str}

Evolution signals from telemetry JSONL (API `/api/telemetry/evolution-signal` and related):
{signals_str}

Inline telemetry payload from task (if any):
{json.dumps(telemetry, indent=2) if telemetry else "{{}}"}

Product Specification:
{spec_str}

Please analyze the product telemetry and suggest improvements.
Focus on data-driven decisions and measurable impact.
"""

            config = GenerationConfig(
                temperature=0.7,
                max_tokens=FACTORY_MAX_OUTPUT_TOKENS_HEAVY,
                timeout_sec=FACTORY_TIMEOUT_DEFAULT_AGENT_SEC,
                json_mode=True,  # openai_compatible skips response_format for reasoning models
            )

            response = await self._generate(prompt, config=config, agent_input=agent_input)

            evolution = self._extract_json(response)
            if evolution is None:
                elapsed = time.time() - start_time
                self._log("WARNING", f"Evolution analysis failed: LLM returned non-JSON response for {product_id}")
                return AgentOutput(
                    task_id=agent_input.task_id,
                    product_id=product_id,
                    agent_type=self.agent_type,
                    success=False,
                    error="LLM returned invalid/non-JSON response — evolution analysis failed",
                    timestamp=time.time(),
                    metrics={"elapsed_seconds": elapsed},
                )

            # Save evolution report
            self._save_artifact(product_id, "telemetry", {
                "product_id": product_id,
                "evolution": evolution,
                "created_at": time.time(),
                "agent": "evolution_analyst",
            }, f"evolution_{int(time.time())}.json")

            improvements = evolution.get("improvements", [])
            auto_fixes = evolution.get("auto_fixes_applied", [])

            elapsed = time.time() - start_time
            self._log("INFO", f"Evolution analysis complete: {len(improvements)} improvements, {len(auto_fixes)} auto-fixes ({elapsed:.1f}s)")

            return AgentOutput(
                task_id=agent_input.task_id,
                product_id=product_id,
                agent_type=self.agent_type,
                success=True,
                data={
                    "evolution": evolution,
                    "health_score": evolution.get("product_health_score", 70),
                    "improvements": improvements,
                    "auto_fixes": auto_fixes,
                    "improvement_count": len(improvements),
                    "auto_fix_count": len(auto_fixes),
                },
                timestamp=time.time(),
                metrics={
                    "elapsed_seconds": elapsed,
                    "health_score": evolution.get("product_health_score", 70),
                    "improvements_suggested": len(improvements),
                    "auto_fixes_applied": len(auto_fixes),
                },
            )

        except Exception as e:
            elapsed = time.time() - start_time
            self._log("ERROR", f"Evolution analysis failed: {e}")
            return AgentOutput(
                task_id=agent_input.task_id,
                product_id=product_id,
                agent_type=self.agent_type,
                success=False,
                error=str(e),
                timestamp=time.time(),
                metrics={"elapsed_seconds": elapsed},
            )
