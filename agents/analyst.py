"""
Market Research Analyst Agent
=============================
Responsible for TWO stages in the pipeline:

STAGE 1 — Market Research (early, after IDEA_RECEIVED):
- Real-time web search via DuckDuckGo for competitor/market data
- Market analysis and TAM/SAM estimation
- Target audience definition and pain point analysis
- Feature prioritization based on market gaps
- Monetization strategy design
- Product naming and positioning

STAGE 2 — Market Monitoring (late, after TELEMETRY_COLLECTING):
- Analyze telemetry and product results
- Compare actual performance against initial market research
- Suggest improvements based on market changes
- Validate if product still meets market needs
"""

from __future__ import annotations

import asyncio
import json
import logging
import time

from agents.prompts.load_prompt import load_prompt
from core.logging_utils import log_suppressed
from core.telemetry_signals import extract_evolution_signals_from_jsonl_dir

logger = logging.getLogger(__name__)

from typing import TYPE_CHECKING

from llm import GenerationConfig, LLMRouter
from llm.factory_defaults import FACTORY_MAX_OUTPUT_TOKENS_HEAVY, FACTORY_TIMEOUT_ANALYST_SEC

from .base_agent import AgentInput, AgentOutput, BaseAgent

if TYPE_CHECKING:
    from pathlib import Path

# ── DuckDuckGo Search ────────────────────────────────────────────────────────

def _duckduckgo_search(query: str, max_results: int = 5) -> list[dict]:
    """Search DuckDuckGo for market research (no API key needed)."""
    try:
        from duckduckgo_search import DDGS
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                results.append({
                    "title": r.get("title", ""),
                    "body": r.get("body", ""),
                    "href": r.get("href", ""),
                })
        return results
    except Exception as e:
        # If duckduckgo_search is not installed or fails, return empty
        return [{"title": "Search unavailable", "body": str(e), "href": ""}]


def _market_search(product_idea: str) -> str:
    """Perform multiple DuckDuckGo searches to gather market intelligence."""
    searches = [
        f"market size {product_idea} software 2024 2025",
        f"competitors {product_idea} software tools",
        f"{product_idea} market trends analysis",
        f"best {product_idea} alternatives review",
    ]

    all_results = []
    for q in searches:
        results = _duckduckgo_search(q, max_results=3)
        if results:
            all_results.append(f"--- Search: {q} ---")
            for r in results:
                all_results.append(f"Title: {r.get('title', 'N/A')}")
                all_results.append(f"Snippet: {r.get('body', 'N/A')[:300]}")
                all_results.append(f"URL: {r.get('href', 'N/A')}")
                all_results.append("")

    return "\n".join(all_results) if all_results else "No search results available."


# ── Prompts ──────────────────────────────────────────────────────────────────

ANALYST_RESEARCH_PROMPT = load_prompt("analyst_research_prompt.md")

ANALYST_MONITOR_PROMPT = load_prompt("analyst_monitor_prompt.md")


# ── Agent ────────────────────────────────────────────────────────────────────

class MarketResearchAgent(BaseAgent):
    """Market Research Analyst — market research (early) + monitoring (late)."""

    def __init__(self, llm_router: LLMRouter):
        super().__init__(
            agent_type="analyst",
            llm_router=llm_router,
            task_type="market_research",
        )

    async def execute(self, agent_input: AgentInput) -> AgentOutput:
        start_time = time.time()
        product_id = agent_input.product_id
        idea = agent_input.data.get("idea", "")

        # Determine stage: research (no research file yet) or monitoring (research exists)
        from core.paths import market_research_path

        research_file = market_research_path(product_id)
        is_monitoring = research_file.exists()

        if is_monitoring:
            return await self._run_monitoring(agent_input, start_time, product_id, idea, research_file)
        else:
            return await self._run_research(agent_input, start_time, product_id, idea)

    # ── Stage 1: Market Research ──────────────────────────────────────────────

    async def _run_research(
        self, agent_input: AgentInput, start_time: float,
        product_id: str, idea: str,
    ) -> AgentOutput:
        """Run market research with DuckDuckGo web search."""
        category = agent_input.data.get("category", "")
        tags = agent_input.data.get("tags", [])

        self._log("INFO", f"Market researching: {idea[:80]}...")

        try:
            # Step 1: Gather real-time market data from DuckDuckGo
            self._log("INFO", f"Searching DuckDuckGo for market data on '{idea[:50]}'...")
            # DDG + httpx are synchronous; run off the asyncio loop so the pipeline worker
            # can still tick other tasks and persist checkpoint saves.
            search_results = await asyncio.to_thread(_market_search, idea)

            prompt = f"""{ANALYST_RESEARCH_PROMPT}

Product Idea: {idea}
Initial category: {category or "not assigned"}
Initial tags: {', '.join(tags) if tags else "not assigned"}

=== REAL-TIME WEB SEARCH RESULTS (DuckDuckGo) ===
{search_results}

Use the web search results above as factual basis for your market analysis.
Be specific about competitors, pricing, and market trends found in the search.
"""

            config = GenerationConfig(
                temperature=0.7,
                max_tokens=FACTORY_MAX_OUTPUT_TOKENS_HEAVY,
                timeout_sec=FACTORY_TIMEOUT_ANALYST_SEC,
                json_mode=True,
            )

            response = await self._generate(prompt, config=config, agent_input=agent_input)
            research = self._extract_json(response)

            if research is None:
                elapsed = time.time() - start_time
                self._log("WARNING", f"Market research failed: non-JSON response for {product_id}")
                return AgentOutput(
                    task_id=agent_input.task_id,
                    product_id=product_id,
                    agent_type=self.agent_type,
                    success=False,
                    error="LLM returned invalid/non-JSON response — market research failed",
                    timestamp=time.time(),
                    metrics={"elapsed_seconds": elapsed},
                )

            brief = (research.get("developer_investigation_brief") or "").strip()
            if len(brief) < 120:
                research["developer_investigation_brief"] = (
                    "1) Deliver a single marketing landing as static HTML/CSS/JS with index.html at project root.\n"
                    "2) Use only relative asset paths (./style.css, ./app.js) so the page loads inside an iframe sandbox.\n"
                    "3) Hero must state the outcome for the target audience from the Product Idea; include one clear primary CTA.\n"
                    "4) Add 2–4 sections (benefits, proof, FAQ, or offer) appropriate to the niche; repeat the CTA once.\n"
                    "5) Forbidden: fake «Full application deployed» text or alert-based placeholders; no root-absolute /… asset URLs.\n"
                    "6) Keep JS minimal; ensure visible copy reflects the idea and downstream PM spec keywords.\n"
                )

            # Save research artifact
            self._save_artifact(product_id, "state", {
                "product_id": product_id,
                "idea": idea,
                "market_research": research,
                "search_results": search_results[:2000],  # store truncated search
                "created_at": time.time(),
                "agent": "analyst",
            }, "market_research.json")

            elapsed = time.time() - start_time
            self._log("INFO", f"Market research complete ({elapsed:.1f}s)")

            return AgentOutput(
                task_id=agent_input.task_id,
                product_id=product_id,
                agent_type=self.agent_type,
                success=True,
                data={
                    "market_research": research,
                    "product_name": research.get("product_name", ""),
                    "tagline": research.get("tagline", ""),
                    "value_proposition": research.get("value_proposition", ""),
                    "industry": research.get("industry", ""),
                    "category": (
                        research.get("positioning", {}).get("suggested_categories", [category])[0]
                        if research.get("positioning", {}).get("suggested_categories") else category
                    ),
                    "tags": research.get("positioning", {}).get("suggested_tags", tags),
                    "research_file": f"state/{product_id}/market_research.json",
                },
                timestamp=time.time(),
                metrics={"elapsed_seconds": elapsed},
            )

        except Exception as e:
            elapsed = time.time() - start_time
            self._log("ERROR", f"Market research failed: {e}")
            return AgentOutput(
                task_id=agent_input.task_id,
                product_id=product_id,
                agent_type=self.agent_type,
                success=False,
                error=str(e),
                timestamp=time.time(),
                metrics={"elapsed_seconds": elapsed},
            )

    # ── Stage 2: Market Monitoring ────────────────────────────────────────────

    async def _run_monitoring(
        self, agent_input: AgentInput, start_time: float,
        product_id: str, idea: str, research_file: Path,
    ) -> AgentOutput:
        """Monitor product results vs initial market research."""
        self._log("INFO", f"Monitoring market fit for {product_id}...")

        try:
            # Load initial research
            with open(research_file) as f:
                research_data = json.load(f)
            initial_research = research_data.get("market_research", {})

            # Load telemetry data (saved evolution bundles + live evolution_signal JSONL)
            telemetry_dir = self.data_root / "telemetry" / product_id
            telemetry_data = []
            if telemetry_dir.exists():
                for evo_file in sorted(telemetry_dir.glob("evolution_*.json")):
                    try:
                        with open(evo_file) as f:
                            telemetry_data.append(json.load(f))
                    except Exception as _suppressed_exc:
                        log_suppressed(logger, "non-fatal (agents/analyst.py)", exc_info=_suppressed_exc)

            evolution_signals = extract_evolution_signals_from_jsonl_dir(telemetry_dir, limit=120)

            # Load evolution history for monitoring context
            evolution_history = []
            state_dir = self.data_root / "state" / product_id
            if state_dir.exists():
                for f in sorted(state_dir.glob("evolution_*.json")):
                    try:
                        with open(f) as fh:
                            evolution_history.append(json.load(fh))
                    except Exception as _suppressed_exc:
                        log_suppressed(logger, "non-fatal (agents/analyst.py)", exc_info=_suppressed_exc)

            telemetry_bundle = {
                "saved_evolution_json": telemetry_data[-5:] if telemetry_data else [],
                "evolution_signals_jsonl": evolution_signals[-80:] if evolution_signals else [],
            }
            telemetry_str = json.dumps(telemetry_bundle, indent=2)
            initial_research_str = json.dumps(initial_research, indent=2)[:3000]

            prompt = f"""{ANALYST_MONITOR_PROMPT}

Product: {product_id}
Idea: {idea}

=== INITIAL MARKET RESEARCH ===
{initial_research_str}

=== TELEMETRY / EVOLUTION DATA ===
{telemetry_str}

Compare the product's actual performance against the initial market research.
Has the product achieved its market potential? What should change?
"""

            config = GenerationConfig(
                temperature=0.7,
                max_tokens=FACTORY_MAX_OUTPUT_TOKENS_HEAVY,
                timeout_sec=FACTORY_TIMEOUT_ANALYST_SEC,
                json_mode=True,
            )

            response = await self._generate(prompt, config=config, agent_input=agent_input)
            monitoring = self._extract_json(response)

            if monitoring is None:
                elapsed = time.time() - start_time
                self._log("WARNING", f"Market monitoring failed: non-JSON response for {product_id}")
                return AgentOutput(
                    task_id=agent_input.task_id,
                    product_id=product_id,
                    agent_type=self.agent_type,
                    success=False,
                    error="LLM returned invalid/non-JSON response — market monitoring failed",
                    timestamp=time.time(),
                    metrics={"elapsed_seconds": elapsed},
                )

            # Save monitoring result
            self._save_artifact(product_id, "state", {
                "product_id": product_id,
                "idea": idea,
                "monitoring": monitoring,
                "created_at": time.time(),
                "agent": "analyst",
            }, "evolution_report.json")

            elapsed = time.time() - start_time
            self._log("INFO", f"Market monitoring complete ({elapsed:.1f}s)")

            return AgentOutput(
                task_id=agent_input.task_id,
                product_id=product_id,
                agent_type=self.agent_type,
                success=True,
                data={
                    "evolution": monitoring,
                    "validation": monitoring.get("validation", {}),
                    "improvement_suggestions": monitoring.get("improvement_suggestions", []),
                    "market_trends": monitoring.get("market_trends", []),
                },
                timestamp=time.time(),
                metrics={"elapsed_seconds": elapsed},
            )

        except Exception as e:
            elapsed = time.time() - start_time
            self._log("ERROR", f"Market monitoring failed: {e}")
            return AgentOutput(
                task_id=agent_input.task_id,
                product_id=product_id,
                agent_type=self.agent_type,
                success=False,
                error=str(e),
                timestamp=time.time(),
                metrics={"elapsed_seconds": elapsed},
            )
