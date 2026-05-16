"""
PM Agent (Product Manager)
==========================
Responsible for:
- Analyzing the idea
- Writing product specification
- Defining requirements and user stories
- Estimating effort and complexity

Delivery profile (marketing_landing vs full_software) drives depth and spec gate.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Optional

from .base_agent import BaseAgent, AgentInput, AgentOutput
from .product_profile import (
    FULL_SOFTWARE,
    MARKETING_LANDING,
    admin_charter_forces_landing_only,
    idea_charter_forces_landing_only,
    infer_delivery_profile,
    normalize_delivery_profile,
    research_artifact_implies_full_product,
)
from web.backend.services.domain_methodology import select_domain_pack, get_domain_pack
from web.backend.services.methodology_review import review_spec as _methodology_review_spec
from .spec_quality_gate import (
    FUNCTIONAL_REQUIREMENT_ACCEPTANCE_MIN_CHARS,
    USER_STORY_ACCEPTANCE_MIN_CHARS,
    validate_specification,
)

PRODUCTION_SPEC_PREFIX = "[production_mode] "
_METHODOLOGY_ISSUE_CAP = 22


def _pg(msg: str) -> str:
    return f"{PRODUCTION_SPEC_PREFIX}{msg}"


def _format_final_spec_gate_error(max_rounds: int, issues: list[str]) -> str:
    bullets = "\n".join(f"  {i + 1}. {x}" for i, x in enumerate(issues))
    return (
        f"Specification failed quality gate after {max_rounds} attempts.\n"
        "Each numbered line is one failing automated check — address all of them in the next spec revision:\n"
        f"{bullets}"
    )


def _repair_issue_bucket(line: str) -> str:
    if line.startswith("[structural_spec]"):
        return "structural_spec"
    if line.startswith("[production_mode]"):
        return "production_mode"
    if line.startswith("[methodology|") or line.startswith("methodology["):
        return "methodology"
    return "other"


def _format_repair_issues_block(issues: list[str]) -> str:
    buckets: dict[str, list[str]] = {
        "structural_spec": [],
        "production_mode": [],
        "methodology": [],
        "other": [],
    }
    for x in issues:
        buckets[_repair_issue_bucket(x)].append(x)
    headers = (
        ("structural_spec", "structural_spec — JSON shape, minimum lengths, list sizes"),
        ("production_mode", "production_mode — narrative depth, differentiation, catalog collision rules"),
        ("methodology", "methodology — domain pack (entities, capabilities, lifecycle, score threshold)"),
        ("other", "other"),
    )
    parts: list[str] = []
    for key, title in headers:
        rows = buckets[key]
        if not rows:
            continue
        parts.append(f"### {title}\n" + "\n".join(f"- {r}" for r in rows))
    return "\n\n".join(parts) if parts else "\n".join(f"- {x}" for x in issues)
from llm import LLMRouter, GenerationConfig
from llm.factory_defaults import FACTORY_MAX_OUTPUT_TOKENS_HEAVY, FACTORY_TIMEOUT_PM_SPEC_SEC
from web.backend.services.spec_compiler import compile_product_brief

PM_SYSTEM_PROMPT_BASE = """You are the Principal Product Manager for an autonomous AI software factory — sharp,
market-grounded, and allergic to vanity backlog filler.

For each idea, you must:
1. Analyze feasibility and market potential **using analyst/market inputs when provided** (those artifacts exist because we paid for discovery — treat them as primary evidence, not decoration).
2. Define functionality at the depth required by delivery_profile — **full_software means ship-worthy MVP**, not “later phases”.
3. Write user stories and **testable** acceptance criteria a QA engineer could verify.
4. Estimate development effort (S/M/L/XL) realistically from FR breadth + integrations + auth/data posture.
5. Identify technical risks, regulatory/integration realities, and dependencies named explicitly (providers, protocols).
6. Generate a distinctive product_name and avoid collisions with common/public names.

**Market research contract:** When `MARKET RESEARCH DATA` appears in the user prompt, you MUST:
- Ground personas and JTBD in that research (names/segments may be synthetic but pains and outcomes must trace to evidence).
- Encode **differentiation vs competitors or alternatives** called out in research into concrete functional_requirements — not generic marketing adjectives.
- Reflect pricing/monetization hypotheses from research in scope (e.g. trials, seats, usage tiers) where they imply product behavior.
If research was skipped empty, say less — never invent fake citations.
"""

PM_SECTION_LANDING = """
DELIVERY PROFILE: **marketing_landing** (single scroll HTML/CSS/JS promo site)

Unless the Product Idea **explicitly** asks for a Python/CLI tool, terminal utility, or backend/API-first product:
- Shipped artifact is **one marketing landing**: hero → sections → CTA.
- **Visual direction:** in `description`, name a **bold, ownable** look-and-feel (palette + font personality + one hero visual idea) so this landing is not interchangeable with every other dark-glass-cyan promo. Call out **SVG-first** opportunities: hero/section backgrounds, illustrative vector scenes, patterns, ornaments — the Developer can generate arbitrary SVG (not limited to icons).
- `product_name`: short, **human and evocative**. Never ™, ®, (TM), or corporate SKU names.
- If the idea is clearly for reusable starter/boilerplate/template output, include "Template: " prefix in product_name.
- Never use placeholder names like "prod-*", "Product *", "Untitled", "New Product".
- `description` and each `core_features[]` entry = **real landing copy** for the idea — not a generic app backlog.
- Prefer 4–7 `core_features` mapping to **visible sections** (hero, problem/solution, proof, offer, FAQ).
- Do **not** scope microservices, databases, or REST APIs unless the idea clearly requires them.

Set JSON field `delivery_profile` to the string: "marketing_landing".
"""

PM_SECTION_FULL = """
DELIVERY PROFILE: **full_software** (implementable application / service — browser slice + real backend shape)

This is **auto-development**, not a slide deck. Produce a spec an Architect can turn into **runnable** services + persistence + APIs + browser UI.

Mandatory stance:
- Tie personas, priorities, and **killer differentiation** to market research when present — competitors, gaps, pricing hooks become FRs and NFRs.
- Scope an **MVP that earns retention**: auth/session boundaries, core entities, core APIs/events, error semantics, and at least one **integration or export path** when research mentions ecosystems (never leave “integrations TBD” without naming protocol level).
- **Brand & UI personality:** concrete visual direction for the shipped UI (mood, palette family, typography, signature moment, SVG surfaces). Ban filler like “modern and clean”.
- `functional_requirements`: contract-grade — each with **testable** acceptance_criteria (happy path + edge/error + observability where relevant).
- `non_functional_requirements`: measurable — latency targets, availability, security (authn/z, data handling), accessibility bar appropriate to audience.
- `technical_risks`: include stack/regulatory/hosting realities (PII, payments, SLAs) when research implies them.

Set JSON field `delivery_profile` to the string: "full_software".
"""

PM_OUTPUT_LANDING = """
Output format: JSON with fields:
- delivery_profile: string (must be "marketing_landing")
- product_name: string (artistic/boutique tone — not trademark-style or corporate SKU)
- description: string (min ~2 sentences; state that deliverable is a single-page marketing landing when applicable)
- target_audience: string
- core_features: list of {name, description, priority}
- user_stories: list of {story, acceptance_criteria} — each acceptance_criteria must be testable prose (see length rule below); no "TBD", "N/A", or one-word stubs
- technical_risks: list of string
- estimated_effort: "S" | "M" | "L" | "XL"
- estimated_days: number
- market_potential: "low" | "medium" | "high"
"""

PM_OUTPUT_FULL = """
Output format: JSON with fields:
- delivery_profile: string (must be "full_software")
- product_name: string (evocative but implementable product identity; no ™/®/(TM))
- description: string (what we build, for whom, success definition)
- target_audience: string
- core_features: list of {name, description, priority} (at least 3; may map to epics/FRs)
- functional_requirements: list of {id, title, description, priority, acceptance_criteria} — **at least 3**; ids like FR-01
- personas: list of {name, context, jobs_to_be_done: list of string} — **at least 1 persona**, each with ≥1 job
- non_functional_requirements: list of {category, requirement, measurable_criteria} — **at least 2**
- user_stories: list of {story, acceptance_criteria} — **at least 2**; each acceptance_criteria testable and tied to audience (see length rule below); no stubs
- technical_risks: list of string
- estimated_effort: "S" | "M" | "L" | "XL"
- estimated_days: number
- market_potential: "low" | "medium" | "high"
"""


def _gate_length_hint(profile: str) -> str:
    """Same thresholds as spec_quality_gate — keeps PM output aligned with validation."""
    lines = [
        "FACTORY QUALITY GATE (non-negotiable):",
        (
            f"- Every user_stories[].acceptance_criteria: ≥ {USER_STORY_ACCEPTANCE_MIN_CHARS} characters, "
            "one or two sentences a reviewer could verify (visible copy, CTA, section, or scroll behavior on the shipped page)."
        ),
    ]
    if profile == FULL_SOFTWARE:
        lines.append(
            f"- Every functional_requirements[].acceptance_criteria: ≥ {FUNCTIONAL_REQUIREMENT_ACCEPTANCE_MIN_CHARS} characters, "
            "with observable outcome (Given/When/Then, or bullets for happy path + one error/edge case where relevant)."
        )
    return "\n" + "\n".join(lines) + "\n"


def _pm_system_block(profile: str) -> str:
    hint = _gate_length_hint(profile)
    if profile == FULL_SOFTWARE:
        return PM_SYSTEM_PROMPT_BASE + PM_SECTION_FULL + PM_OUTPUT_FULL + hint
    return PM_SYSTEM_PROMPT_BASE + PM_SECTION_LANDING + PM_OUTPUT_LANDING + hint


def _build_pm_user_prompt(
    *,
    idea: str,
    research_context: str,
    profile: str,
    repair_issues: list[str] | None,
    production_mode: bool,
) -> str:
    repair = ""
    if repair_issues:
        ac_fix = (
            f"If failures mention acceptance_criteria length, expand each named field into full testable sentences "
            f"(≥{USER_STORY_ACCEPTANCE_MIN_CHARS} characters per user story"
        )
        if profile == FULL_SOFTWARE:
            ac_fix += (
                f"; ≥{FUNCTIONAL_REQUIREMENT_ACCEPTANCE_MIN_CHARS} characters per functional_requirements item"
            )
        ac_fix += ").\n"
        grouped = _format_repair_issues_block(repair_issues)
        repair = (
            "\n=== SPEC QUALITY GATE — FIX REQUIRED ===\n"
            "The previous JSON failed one or more automated gates (sections below). "
            "Address **every** bullet; gate labels tell you which rules fired.\n\n"
            f"{grouped}\n\n"
            "Return a complete corrected JSON object (do not return a diff or commentary).\n"
            + ac_fix
        )

    production_hint = ""
    if production_mode:
        production_hint = (
            "\nPRODUCTION MODE (strict):\n"
            "- Avoid generic copy ('for everyone', 'modern clean platform', vague buzzwords).\n"
            "- Include audience-specific ICP language and concrete JTBD pressure.\n"
            "- Ensure core_features are differentiated (not interchangeable template bullets).\n"
        )

    if research_context:
        return f"""{_pm_system_block(profile)}

Product Idea: {idea}

=== MARKET RESEARCH DATA ===
The following market research has been conducted for this product:

{research_context}

Please analyze this idea and create a comprehensive product specification aligned with delivery_profile={profile}.
The research is **binding context**: personas, competitor landscape, differentiation, monetization — must materially shape FRs and scope (not a decorative appendix).
If delivery_profile is full_software, reflect **what we build to win** from that research in explicit requirements and risks.
{production_hint}
{repair}
"""
    return f"""{_pm_system_block(profile)}

Product Idea: {idea}

Please analyze this idea and create a comprehensive product specification aligned with delivery_profile={profile}.
{production_hint}
{repair}
"""


def _production_spec_issues(spec: dict, profile: str, product_id: str | None = None) -> list[str]:
    issues: list[str] = []
    if not isinstance(spec, dict):
        return [_pg("spec must be JSON object")]
    desc = str(spec.get("description") or "").strip()
    ta = str(spec.get("target_audience") or "").strip()
    if len(desc) < 90:
        issues.append(_pg("description too short for production_mode (need concrete narrative)"))
    if len(ta) < 16 or ta.lower() in {"everyone", "all users", "general audience"}:
        issues.append(_pg("target_audience too generic for production_mode"))
    feats = spec.get("core_features") or []
    if not isinstance(feats, list) or len(feats) < 4:
        issues.append(_pg("core_features need >=4 differentiated items in production_mode"))
    generic_tokens = ("modern", "clean", "innovative", "powerful", "seamless", "easy to use")
    generic_hits = sum(1 for g in generic_tokens if g in desc.lower())
    if generic_hits >= 3:
        issues.append(_pg("description reads as generic template copy"))
    if profile == FULL_SOFTWARE:
        personas = spec.get("personas") or []
        if not isinstance(personas, list) or len(personas) < 2:
            issues.append(_pg("production full_software needs >=2 personas"))
    product_name = str(spec.get("product_name") or "").strip()
    n = product_name.lower()
    if (
        not product_name
        or n.startswith("prod-")
        or n.startswith("product ")
        or n in {"product", "untitled", "new product"}
    ):
        issues.append(_pg("product_name is placeholder-like; provide marketable unique name"))
    if len(product_name) < 4:
        issues.append(_pg("product_name too short for production_mode"))
    existing = _load_existing_product_name_slugs(exclude_product_id=product_id)
    slug = _slug(product_name)
    if slug and slug in existing:
        issues.append(_pg("product_name collides with existing catalog name; generate unique alternative"))
    return issues


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")


def _load_existing_product_name_slugs(
    data_root: str = "/app/data",
    exclude_product_id: str | None = None,
) -> set[str]:
    specs_root = Path(data_root) / "specs"
    out: set[str] = set()
    if not specs_root.exists():
        return out
    for p in specs_root.glob("*/specification.json"):
        if exclude_product_id and p.parent.name == exclude_product_id:
            continue
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
            spec = raw.get("specification") if isinstance(raw, dict) else {}
            name = str((spec or {}).get("product_name", "")).strip()
            sl = _slug(name)
            if sl:
                out.add(sl)
        except Exception:
            continue
    return out


class PMAgent(BaseAgent):
    """Product Manager Agent - writes specifications from ideas."""

    def __init__(self, llm_router: LLMRouter):
        super().__init__(
            agent_type="pm",
            llm_router=llm_router,
            task_type="pm_analysis",
        )

    async def execute(self, agent_input: AgentInput) -> AgentOutput:
        start_time = time.time()
        idea = agent_input.data.get("idea", "")
        product_id = agent_input.product_id
        admin = (agent_input.data.get("admin_instructions") or "").strip()
        production_mode = bool(agent_input.data.get("production_mode"))

        raw_profile = agent_input.data.get("delivery_profile")
        if raw_profile:
            pipeline_profile = normalize_delivery_profile(str(raw_profile))
        else:
            pipeline_profile = infer_delivery_profile(admin or None, idea or None)

        research_context = ""
        research_file = Path(self.data_root / "state" / product_id / "market_research.json")
        if research_file.exists():
            try:
                with open(research_file, encoding="utf-8") as f:
                    research_data = json.load(f)
                research_context = json.dumps(research_data, indent=2)
                self._log("INFO", f"Loaded market research for {product_id}")
            except (json.JSONDecodeError, OSError) as e:
                self._log("WARNING", f"Could not load market research: {e}")

        profile = pipeline_profile
        if (
            pipeline_profile == MARKETING_LANDING
            and research_context.strip()
            and not admin_charter_forces_landing_only(admin)
            and not idea_charter_forces_landing_only(idea)
            and research_artifact_implies_full_product(research_context)
        ):
            profile = FULL_SOFTWARE
            self._log(
                "INFO",
                "PM escalated delivery_profile marketing_landing→full_software based on substantive market research",
            )

        self._log(
            "INFO",
            f"Analyzing idea: {idea[:100]}... (pipeline_profile={pipeline_profile}, effective_profile={profile})",
        )

        max_rounds = 5 if production_mode else 3
        last_issues: list[str] = []

        try:
            spec = None
            for attempt in range(max_rounds):
                compiled_brief = compile_product_brief(idea, admin)
                prompt = _build_pm_user_prompt(
                    idea=idea,
                    research_context=research_context,
                    profile=profile,
                    repair_issues=last_issues if attempt else None,
                    production_mode=production_mode,
                )
                prompt += (
                    "\n=== SPEC COMPILER BRIEF (structured intake) ===\n"
                    f"{json.dumps(compiled_brief, ensure_ascii=False, indent=2)}\n"
                    "Use this as additional grounding while preserving hard validation schema.\n"
                )
                prompt += (
                    "\nIMPORTANT: Use discovery_pack.questions to clarify scope assumptions; "
                    "translate them into concrete personas, functional_requirements, and non_functional_requirements.\n"
                )

                config = GenerationConfig(
                    temperature=0.65 if attempt == 0 else 0.45,
                    max_tokens=FACTORY_MAX_OUTPUT_TOKENS_HEAVY,
                    timeout_sec=FACTORY_TIMEOUT_PM_SPEC_SEC,
                    json_mode=True,
                )

                response = await self._generate(prompt, config=config, agent_input=agent_input)
                spec = self._extract_json(response)
                if spec is None:
                    elapsed = time.time() - start_time
                    self._log("WARNING", f"Specification non-JSON for {product_id} (attempt {attempt + 1})")
                    return AgentOutput(
                        task_id=agent_input.task_id,
                        product_id=product_id,
                        agent_type=self.agent_type,
                        success=False,
                        error="LLM returned invalid/non-JSON response — specification generation failed",
                        timestamp=time.time(),
                        metrics={"elapsed_seconds": elapsed},
                    )

                spec["delivery_profile"] = profile
                ok, issues = validate_specification(spec, profile)
                if ok and production_mode:
                    prod_issues = _production_spec_issues(spec, profile, product_id=product_id)
                    if prod_issues:
                        ok = False
                        issues = [*issues, *prod_issues]
                if ok:
                    methodology_issues = self._methodology_spec_issues(
                        idea=idea,
                        admin=admin,
                        category=agent_input.data.get("category"),
                        spec=spec,
                        profile=profile,
                        product_id=product_id,
                    )
                    if methodology_issues:
                        ok = False
                        issues = [*issues, *methodology_issues]
                if ok:
                    break
                last_issues = issues
                self._log("WARNING", f"Spec gate failed for {product_id}: {issues} (attempt {attempt + 1}/{max_rounds})")

            if spec is None:
                raise RuntimeError("spec unset")

            ok_final, issues_final = validate_specification(spec, profile)
            if ok_final and production_mode:
                prod_final = _production_spec_issues(spec, profile, product_id=product_id)
                if prod_final:
                    ok_final = False
                    issues_final = [*issues_final, *prod_final]
            if ok_final:
                methodology_final = self._methodology_spec_issues(
                    idea=idea,
                    admin=admin,
                    category=agent_input.data.get("category"),
                    spec=spec,
                    profile=profile,
                    product_id=product_id,
                )
                if methodology_final:
                    ok_final = False
                    issues_final = [*issues_final, *methodology_final]
            if not ok_final:
                elapsed = time.time() - start_time
                return AgentOutput(
                    task_id=agent_input.task_id,
                    product_id=product_id,
                    agent_type=self.agent_type,
                    success=False,
                    error=_format_final_spec_gate_error(max_rounds, issues_final),
                    timestamp=time.time(),
                    metrics={"elapsed_seconds": elapsed},
                )

            self._save_artifact(
                product_id,
                "specs",
                {
                    "product_id": product_id,
                    "idea": idea,
                    "specification": spec,
                    "delivery_profile": profile,
                    "created_at": time.time(),
                    "agent": "pm",
                },
                "specification.json",
            )

            # Persist final methodology review next to the spec so admin/QA/marketplace can read it.
            methodology_report = self._build_methodology_spec_report(
                idea=idea,
                category=agent_input.data.get("category"),
                spec=spec,
                profile=profile,
                product_id=product_id,
            )

            elapsed = time.time() - start_time
            self._log("INFO", f"Specification complete for {product_id} ({elapsed:.1f}s) profile={profile}")

            return AgentOutput(
                task_id=agent_input.task_id,
                product_id=product_id,
                agent_type=self.agent_type,
                success=True,
                data={
                    "specification": spec,
                    "delivery_profile": profile,
                    "spec_file": f"specs/{product_id}/specification.json",
                    "methodology_spec_review": methodology_report,
                    "peer_review": {
                        "recommended": "approve",
                        "blockers": [],
                        "notes": "PM spec validated and ready for architecture.",
                    },
                },
                timestamp=time.time(),
                metrics={"elapsed_seconds": elapsed},
            )

        except Exception as e:
            elapsed = time.time() - start_time
            self._log("ERROR", f"Failed to create specification: {e}")
            return AgentOutput(
                task_id=agent_input.task_id,
                product_id=product_id,
                agent_type=self.agent_type,
                success=False,
                error=str(e),
                timestamp=time.time(),
                metrics={"elapsed_seconds": elapsed},
            )

    # ------------------------------------------------------------------
    # Methodology gate (post-spec) — see agents.methodologist for full agent.
    # ------------------------------------------------------------------

    def _select_methodology_pack(
        self,
        *,
        idea: str,
        admin: str,
        category: Optional[str],
        spec: dict,
    ):
        forced = ""
        if isinstance(spec, dict):
            forced = str(spec.get("domain") or "").strip()
        if not forced:
            for src in (admin, idea):
                lower = (src or "").lower()
                # Cheap explicit override hint: "domain: helpdesk_support" in admin/idea text.
                m = re.search(r"domain[:=]\s*([a-z_]+)", lower)
                if m:
                    forced = m.group(1)
                    break
        forced_pack = get_domain_pack(forced) if forced else None
        if forced_pack is not None:
            return forced_pack
        return select_domain_pack(idea or "", category=category, spec=spec)

    def _methodology_spec_issues(
        self,
        *,
        idea: str,
        admin: str,
        category: Optional[str],
        spec: dict,
        profile: str,
        product_id: str,
    ) -> list[str]:
        """Return a list of human-readable hints (PM retry prompt) when methodology gate fails."""
        if normalize_delivery_profile(profile) == MARKETING_LANDING:
            return []
        pack = self._select_methodology_pack(idea=idea, admin=admin, category=category, spec=spec)
        if pack is None:
            return []
        report = _methodology_review_spec(spec, pack=pack, stage="post_spec")
        if report.get("passed"):
            return []
        domain = str(report.get("domain") or "generic")
        findings = [f for f in (report.get("findings") or []) if isinstance(f, dict)]
        high = [f for f in findings if f.get("severity") == "high"]
        medium = [f for f in findings if f.get("severity") == "medium"]

        def _one_line(f: dict) -> str:
            sev = str(f.get("severity") or "?").upper()
            code = str(f.get("code") or "").strip() or "?"
            detail = str(f.get("detail") or f.get("code") or "finding").strip()
            fix = str(f.get("fix_hint") or "").strip()
            head = f"[methodology|{domain}|{sev}|{code}] {detail}"
            if fix:
                return f"{head} — Action: {fix}"
            return head

        issues = [_one_line(f) for f in high]
        cap = _METHODOLOGY_ISSUE_CAP
        if len(issues) < cap and medium:
            for f in medium:
                line = _one_line(f)
                if line not in issues:
                    issues.append(line)
                if len(issues) >= cap:
                    break
        return issues

    def _build_methodology_spec_report(
        self,
        *,
        idea: str,
        category: Optional[str],
        spec: dict,
        profile: str,
        product_id: str,
    ) -> dict:
        pack = self._select_methodology_pack(idea=idea, admin="", category=category, spec=spec)
        report = _methodology_review_spec(spec, pack=pack, stage="post_spec")
        report["delivery_profile"] = profile
        report["product_id"] = product_id
        report["created_at"] = time.time()
        try:
            self._save_artifact(
                product_id,
                "state",
                report,
                filename="methodology_spec_review.json",
            )
        except Exception:
            pass
        return report
