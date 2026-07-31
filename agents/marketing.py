"""
Marketing Agent
===============
Responsible for:
- Creating product descriptions and marketing copy for marketplace listing
- Generating promotional content (taglines, social media posts)
- SEO optimization
- Product naming and branding

Note: Market research and monetization scheme design is now handled
by the Market Research Analyst (analyst) agent.
"""

from __future__ import annotations

import json
import time

from agents.prompt_utils import prompt_json
from agents.prompts.load_prompt import load_prompt
from llm import GenerationConfig, LLMRouter
from llm.factory_defaults import FACTORY_MAX_OUTPUT_TOKENS_HEAVY, FACTORY_TIMEOUT_DEFAULT_AGENT_SEC
from marketplace_taxonomy import slug_to_marketplace_category

from .base_agent import AgentInput, AgentOutput, BaseAgent

MARKETING_SYSTEM_PROMPT = load_prompt("marketing_system_prompt.md")


class MarketingAgent(BaseAgent):
    """Marketing Agent - creates marketing content for products."""

    def __init__(self, llm_router: LLMRouter):
        super().__init__(
            agent_type="marketing",
            llm_router=llm_router,
            task_type="marketing_copy",
        )

    async def execute(self, agent_input: AgentInput) -> AgentOutput:
        start_time = time.time()
        product_id = agent_input.product_id
        spec = agent_input.data.get("specification", {})
        idea = agent_input.data.get("idea", "")

        self._log("INFO", f"Creating marketing content for {product_id}")

        # Load market research data if available (from analyst stage)
        research_context = ""
        from core.paths import market_research_path

        research_file = market_research_path(product_id)
        if research_file.exists():
            try:
                with open(research_file) as f:
                    research_data = json.load(f)
                research_context = prompt_json(research_data)
                self._log("INFO", f"Loaded market research for {product_id}")
            except (OSError, json.JSONDecodeError) as e:
                self._log("WARNING", f"Could not load market research: {e}")

        try:
            spec_str = prompt_json(spec) if spec else idea

            if research_context:
                prompt = f"""{MARKETING_SYSTEM_PROMPT}

Product Information:
{spec_str}

=== MARKET RESEARCH DATA ===
{research_context}

Please create compelling marketing content for this product based on the specification and market research above.
Focus on highlighting the product's unique value proposition and key benefits.
"""
            else:
                prompt = f"""{MARKETING_SYSTEM_PROMPT}

Product Information:
{spec_str}

Please create compelling marketing content for this product based on the specification above.
Focus on highlighting the product's unique value proposition and key benefits.
"""

            config = GenerationConfig(
                temperature=0.8,
                max_tokens=FACTORY_MAX_OUTPUT_TOKENS_HEAVY,
                timeout_sec=FACTORY_TIMEOUT_DEFAULT_AGENT_SEC,
                json_mode=True,  # openai_compatible skips response_format for reasoning models
            )

            response = await self._generate(prompt, config=config, agent_input=agent_input)

            marketing = self._extract_json(response)
            if (
                isinstance(marketing, dict)
                and marketing.get("category") is not None
                and slug_to_marketplace_category(marketing.get("category")) is None
            ):
                marketing.pop("category", None)

            if marketing is None:
                elapsed = time.time() - start_time
                self._log("WARNING", f"Marketing content generation failed: LLM returned non-JSON response for {product_id}")
                return AgentOutput(
                    task_id=agent_input.task_id,
                    product_id=product_id,
                    agent_type=self.agent_type,
                    success=False,
                    error="LLM returned invalid/non-JSON response — marketing content generation failed",
                    timestamp=time.time(),
                    metrics={"elapsed_seconds": elapsed},
                )

            # Save marketing content
            self._save_artifact(product_id, "state", {
                "product_id": product_id,
                "marketing": marketing,
                "created_at": time.time(),
                "agent": "marketing",
            }, "marketing_content.json")

            elapsed = time.time() - start_time
            self._log("INFO", f"Marketing content created ({elapsed:.1f}s)")

            return AgentOutput(
                task_id=agent_input.task_id,
                product_id=product_id,
                agent_type=self.agent_type,
                success=True,
                data={
                    "marketing": marketing,
                    "product_name": marketing.get("product_name", ""),
                    "tagline": marketing.get("tagline", ""),
                    "short_description": marketing.get("short_description", ""),
                    "long_description": marketing.get("long_description", ""),
                    "key_benefits": marketing.get("key_benefits", []),
                    "selling_description": marketing.get("selling_description", ""),
                    "seo_metadata": marketing.get("seo_metadata", {}),
                    "social_media_posts": marketing.get("social_media_posts", []),
                    "blog_post": marketing.get("blog_post"),
                    "marketing_file": f"state/{product_id}/marketing_content.json",
                },
                timestamp=time.time(),
                metrics={"elapsed_seconds": elapsed},
            )

        except Exception as e:
            elapsed = time.time() - start_time
            self._log("ERROR", f"Marketing content creation failed: {e}")
            return AgentOutput(
                task_id=agent_input.task_id,
                product_id=product_id,
                agent_type=self.agent_type,
                success=False,
                error=str(e),
                timestamp=time.time(),
                metrics={"elapsed_seconds": elapsed},
            )
