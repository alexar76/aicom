"""
from agents.prompts.load_prompt import load_prompt
Sales Agent
===========
Responsible for:
- Managing product sales pages
- Handling customer inquiries
- Processing payments
- Managing licenses
- Customer communication

Platform-wide audience broadcasts (email, webhooks, Telegram) live in **Admin → Outreach**
(env-based credentials); this agent only produces per-product `sales_config.json` in the pipeline.
"""

from __future__ import annotations

import json
import time

from .base_agent import BaseAgent, AgentInput, AgentOutput
from llm import LLMRouter, GenerationConfig
from llm.factory_defaults import FACTORY_MAX_OUTPUT_TOKENS_HEAVY, FACTORY_TIMEOUT_DEFAULT_AGENT_SEC

SALES_SYSTEM_PROMPT = load_prompt("sales_system_prompt.md")


class SalesAgent(BaseAgent):
    """Sales Agent - handles sales, pricing, and customer communication."""

    def __init__(self, llm_router: LLMRouter):
        super().__init__(
            agent_type="sales",
            llm_router=llm_router,
            task_type="sales_response",
        )

    async def execute(self, agent_input: AgentInput) -> AgentOutput:
        start_time = time.time()
        product_id = agent_input.product_id
        marketing = agent_input.data.get("marketing", {})
        spec = agent_input.data.get("specification", {})

        self._log("INFO", f"Setting up sales for {product_id}")

        try:
            marketing_str = json.dumps(marketing, indent=2) if marketing else "{}"
            spec_str = json.dumps(spec, indent=2) if spec else "{}"

            prompt = f"""{SALES_SYSTEM_PROMPT}

Product ID: {product_id}

Marketing Content (including monetization scheme):
{marketing_str}

Product Specification:
{spec_str}

Please set up the sales configuration for this product.
Follow the monetization scheme proposed by Marketing (free tier limitations, paid tier pricing).
Convert USD prices to USDT/USDC equivalents and add crypto-specific features.
Create clear sales page content explaining the free vs paid tier differences.
"""

            config = GenerationConfig(
                temperature=0.7,
                max_tokens=FACTORY_MAX_OUTPUT_TOKENS_HEAVY,
                timeout_sec=FACTORY_TIMEOUT_DEFAULT_AGENT_SEC,
                json_mode=True,  # openai_compatible skips response_format for reasoning models
            )

            response = await self._generate(prompt, config=config, agent_input=agent_input)

            sales_data = self._extract_json(response)
            if sales_data is None:
                elapsed = time.time() - start_time
                self._log("WARNING", f"Sales configuration failed: LLM returned non-JSON response for {product_id}")
                return AgentOutput(
                    task_id=agent_input.task_id,
                    product_id=product_id,
                    agent_type=self.agent_type,
                    success=False,
                    error="LLM returned invalid/non-JSON response — sales configuration failed",
                    timestamp=time.time(),
                    metrics={"elapsed_seconds": elapsed},
                )

            # Save sales configuration
            self._save_artifact(product_id, "state", {
                "product_id": product_id,
                "sales_data": sales_data,
                "created_at": time.time(),
                "agent": "sales",
            }, "sales_config.json")

            elapsed = time.time() - start_time
            self._log("INFO", f"Sales configuration complete ({elapsed:.1f}s)")

            return AgentOutput(
                task_id=agent_input.task_id,
                product_id=product_id,
                agent_type=self.agent_type,
                success=True,
                data={
                    "sales_data": sales_data,
                    "price_usdt": sales_data.get("pricing", {}).get("usdt_price", 4.99),
                    "chains": sales_data.get("pricing", {}).get("supported_chains", []),
                    "sales_file": f"state/{product_id}/sales_config.json",
                },
                timestamp=time.time(),
                metrics={"elapsed_seconds": elapsed},
            )

        except Exception as e:
            elapsed = time.time() - start_time
            self._log("ERROR", f"Sales setup failed: {e}")
            return AgentOutput(
                task_id=agent_input.task_id,
                product_id=product_id,
                agent_type=self.agent_type,
                success=False,
                error=str(e),
                timestamp=time.time(),
                metrics={"elapsed_seconds": elapsed},
            )
