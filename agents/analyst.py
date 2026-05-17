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
import time
from pathlib import Path
from typing import Optional

from core.telemetry_signals import extract_evolution_signals_from_jsonl_dir

from .base_agent import BaseAgent, AgentInput, AgentOutput
from llm import LLMRouter, GenerationConfig
from llm.factory_defaults import FACTORY_MAX_OUTPUT_TOKENS_HEAVY, FACTORY_TIMEOUT_ANALYST_SEC

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

ANALYST_RESEARCH_PROMPT = """You are the Market Research Analyst for an AI-powered software factory.
Your role is to analyze product ideas from a market perspective and produce
a comprehensive market research brief that guides product development.

You have access to real-time web search results from DuckDuckGo.
Use these results as factual input for your analysis.

For each idea, you must conduct thorough analysis:

=== 1. MARKET ANALYSIS ===
- Industry / sector classification
- Total Addressable Market (TAM), Serviceable Addressable Market (SAM)
- Competitor analysis based on search results: main competitors, strengths, weaknesses
- Market gaps: what features or solutions are missing
- Current trends from search data

=== 2. TARGET AUDIENCE ===
- Primary audience: who will pay
- Pain points: specific problems this solves
- Willingness to pay: realistic price range

=== 3. FEATURE PRIORITIZATION ===
- MVP features: absolute minimum to launch
- Competitive advantage features: what makes this stand out
- Future features: what can wait
- For each feature, explain the market rationale

=== 4. MONETIZATION STRATEGY ===
- Recommended business model (SaaS / one-time / freemium / usage-based)
- Free tier limitations (if applicable)
- Paid tiers with realistic pricing
- Recommended tier for new customers

=== 5. PRODUCT POSITIONING ===
- Product name suggestions
- Tagline / one-liner
- Value proposition
- Key differentiators vs competitors found in search

=== 6. DEVELOPER INVESTIGATION BRIEF (handoff to implementer) ===
You are the **investigator before the Developer**. Write `developer_investigation_brief`: one string (800–2000 characters)
of **numbered, imperative instructions** for whoever builds the **HTML/CSS/JS marketing landing**. Base it on sections 1–5
and on standard landing-page practice (clear hero + outcome headline, primary CTA, proof/benefits, repeated CTA, optional FAQ).

The brief MUST explicitly include all of the following themes (use your own words, stay specific to this product):
- **Sandbox / preview reality**: QA and the storefront load the product from on-disk `index.html` (and siblings) under
  `data/code/<product_id>/`, served inside an **iframe** (same-origin style as `/api/sandbox/file/...`). Therefore **all**
  asset URLs in HTML/CSS must be **relative** (`./style.css`, `./app.js`, `./assets/...`) — never root-absolute paths like
  `href="/style.css"` or `src="/app.js"` (they break the iframe and fail automated gates). Never `http://localhost…`,
  `https://127.0.0.1…`, or protocol-relative `href="//localhost…"` — use `./` and section anchors (`href="#faq"`).
- **Quality gates the Developer must pass**: no fake launch copy or `alert('Full application deployed'...)`; visible page
  must reflect the product idea and spec vocabulary; avoid tiny placeholder HTML; prefer self-contained SVG/CSS over
  broken hotlinked images.
- **Landing structure**: what the hero must promise, who it is for, what the primary CTA says, which 2–4 sections follow
  and in what order, and what trust/proof element fits this niche.
- **Motion & accessibility**: keep JS minimal; respect reduced motion where relevant.

Output format: JSON with fields:
- product_name, tagline, value_proposition (strings)
- industry: string
- market_analysis: {tam, sam, competitors: [{name, strengths, weaknesses}], market_gaps, trends, demand_level}
- target_audience: {primary, secondary, pain_points, willingness_to_pay}
- feature_priorities: {mvp: [{feature, rationale}], competitive_advantage: [...], future: [...]}
- monetization: {model, free_tier: {available, limitations}, paid_tiers: [{name, price_usd_monthly, features}], recommended_tier}
- positioning: {key_differentiators, suggested_categories, suggested_tags}
- developer_investigation_brief: string (required; see section 6)
"""

ANALYST_MONITOR_PROMPT = """You are the Market Research Analyst monitoring a product's performance.
Your role is to analyze telemetry data and compare actual results with the
initial market research, then suggest improvements.

=== 1. REVIEW INITIAL RESEARCH ===
Compare the original market research with actual results.

=== 2. ANALYZE TELEMETRY ===
- What metrics are available?
- Is the product meeting expected targets?
- Are there any issues or anomalies?

=== 3. MARKET VALIDATION ===
- Is the initial market assessment still valid?
- Have competitors or market conditions changed?
- Does the product still address the target audience's pain points?

=== 4. IMPROVEMENT SUGGESTIONS ===
- What features should be added/changed based on market feedback?
- Should pricing be adjusted?
- Are there new market opportunities?

Output format: JSON with fields:
- execution_summary: string
- market_trends: list of {trend, impact, action}
- improvement_suggestions: list of {area, suggestion, priority, expected_impact}
- validation: {initial_assessment_valid: bool, changes_in_market: string, recommended_actions: list}
- request_implementation_refresh: bool (true **only** if the shipped browser slice should be regenerated or materially revised — UX, copy, IA, proof, or demo gaps vs research; **not** for analytics-only or pricing copy tweaks alone)
- implementation_refresh_brief: string (when request_implementation_refresh is true: 3–8 crisp bullet lines the Developer must follow; otherwise empty string)
"""


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
            with open(research_file, "r") as f:
                research_data = json.load(f)
            initial_research = research_data.get("market_research", {})

            # Load telemetry data (saved evolution bundles + live evolution_signal JSONL)
            telemetry_dir = self.data_root / "telemetry" / product_id
            telemetry_data = []
            if telemetry_dir.exists():
                for evo_file in sorted(telemetry_dir.glob("evolution_*.json")):
                    try:
                        with open(evo_file, "r") as f:
                            telemetry_data.append(json.load(f))
                    except Exception:
                        pass

            evolution_signals = extract_evolution_signals_from_jsonl_dir(telemetry_dir, limit=120)

            # Load evolution history for monitoring context
            evolution_history = []
            state_dir = self.data_root / "state" / product_id
            if state_dir.exists():
                for f in sorted(state_dir.glob("evolution_*.json")):
                    try:
                        with open(f) as fh:
                            evolution_history.append(json.load(fh))
                    except Exception:
                        pass

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
