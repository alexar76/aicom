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
from dataclasses import dataclass

from agents.prompt_utils import prompt_json
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

@dataclass(frozen=True)
class SearchOutcome:
    """One search, with failure kept OUT of the result set.

    This used to return the exception as a search hit — ``{"title": "Search unavailable",
    "body": str(e)}`` — which then went into the LLM prompt underneath the line telling the
    model to treat the block as factual basis. A network error became evidence. Failure is
    now a status the caller can act on, not a document the model can quote.
    """

    ok: bool
    results: list[dict]
    error: str = ""


@dataclass(frozen=True)
class MarketEvidence:
    """What retrieval actually produced, and how much of the report it can support."""

    text: str
    queries: int
    queries_ok: int
    sources: list[str]
    errors: list[str]

    @property
    def grounding(self) -> str:
        if not self.results_found:
            return "none"
        if self.queries_ok < self.queries:
            return "partial"
        return "full"

    @property
    def results_found(self) -> int:
        return len(self.sources)


def _duckduckgo_search(query: str, max_results: int = 5) -> SearchOutcome:
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
        return SearchOutcome(ok=True, results=results)
    except Exception as e:
        # Not installed, rate-limited, offline, blocked — all of it is a failed retrieval,
        # and none of it is market data.
        logger.warning("market search failed for %r: %s", query[:80], e)
        return SearchOutcome(ok=False, results=[], error=str(e))


def _market_search(product_idea: str) -> MarketEvidence:
    """Perform multiple DuckDuckGo searches to gather market intelligence."""
    searches = [
        f"market size {product_idea} software 2024 2025",
        f"competitors {product_idea} software tools",
        f"{product_idea} market trends analysis",
        f"best {product_idea} alternatives review",
    ]

    all_results: list[str] = []
    sources: list[str] = []
    errors: list[str] = []
    ok_count = 0
    for q in searches:
        outcome = _duckduckgo_search(q, max_results=3)
        if not outcome.ok:
            errors.append(f"{q}: {outcome.error}")
            continue
        ok_count += 1
        if not outcome.results:
            continue
        all_results.append(f"--- Search: {q} ---")
        for r in outcome.results:
            href = (r.get("href") or "").strip()
            if href:
                sources.append(href)
            all_results.append(f"Title: {r.get('title', 'N/A')}")
            all_results.append(f"Snippet: {(r.get('body') or 'N/A')[:300]}")
            all_results.append(f"URL: {href or 'N/A'}")
            all_results.append("")

    return MarketEvidence(
        text="\n".join(all_results),
        queries=len(searches),
        queries_ok=ok_count,
        sources=sources,
        errors=errors,
    )


def _evidence_block(evidence: MarketEvidence) -> str:
    """The retrieval section of the prompt — it must never overstate what was retrieved."""
    if evidence.results_found:
        header = (
            f"=== WEB SEARCH RESULTS (DuckDuckGo) — {evidence.results_found} result(s) "
            f"from {evidence.queries_ok}/{evidence.queries} queries ==="
        )
        footer = (
            "\nGround every competitor, price and trend you can in the results above, and cite "
            "the URL you took it from. Anything the results do not support is an estimate: say "
            "so in the field itself rather than presenting it as a finding."
        )
        if evidence.queries_ok < evidence.queries:
            footer += (
                f"\nNote: {evidence.queries - evidence.queries_ok} of {evidence.queries} searches "
                "did not run, so coverage is incomplete."
            )
        return f"{header}\n{evidence.text}\n{footer}"
    return (
        "=== WEB SEARCH RESULTS: NONE RETRIEVED ===\n"
        "Live search returned nothing for this idea. You have NO external evidence.\n"
        "Produce the analysis from general knowledge, and mark every market size, competitor "
        "and price as an unverified estimate. Do not invent sources, URLs or figures presented "
        "as researched facts."
    )


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
            evidence = await asyncio.to_thread(_market_search, idea)
            if evidence.errors:
                self._log(
                    "WARNING",
                    f"Market search degraded: {evidence.queries_ok}/{evidence.queries} queries "
                    f"succeeded ({len(evidence.errors)} failed)",
                )

            prompt = f"""{ANALYST_RESEARCH_PROMPT}

Product Idea: {idea}
Initial category: {category or "not assigned"}
Initial tags: {', '.join(tags) if tags else "not assigned"}

{_evidence_block(evidence)}
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

            # How well the report is grounded travels WITH the report. A reader (or a
            # downstream agent) must be able to tell a researched market size from one the
            # model produced with the search offline.
            # Counts and sources — never the error TEXT. market_research.json is read back
            # into the PM, architect and developer prompts, so an exception string stored here
            # is the same bug in a longer pipe: it would have travelled out of the analyst's
            # prompt and into four others. The text is logged for an operator instead.
            research["evidence"] = {
                "grounding": evidence.grounding,
                "queries": evidence.queries,
                "queries_succeeded": evidence.queries_ok,
                "results_found": evidence.results_found,
                "sources": evidence.sources,
                "failed_queries": len(evidence.errors),
            }
            for detail in evidence.errors:
                logger.warning("market search failed: %s", detail)

            # Save research artifact
            self._save_artifact(product_id, "state", {
                "product_id": product_id,
                "idea": idea,
                "market_research": research,
                "search_results": evidence.text[:2000],  # store truncated search
                "evidence": research["evidence"],
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
                    "evidence_grounding": evidence.grounding,
                    "evidence_sources": evidence.sources,
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
            telemetry_str = prompt_json(telemetry_bundle)
            initial_research_str = prompt_json(initial_research, limit=3000)

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
