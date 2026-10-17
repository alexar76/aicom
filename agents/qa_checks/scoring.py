"""Scores and reviews: quality and release scores, the LLM review and the browser E2E spec
alignment.
"""

from __future__ import annotations

import os

from agents.prompt_utils import prompt_json
from core.logging_utils import log_suppressed
from core.spec_presence import spec_has_substance as _spec_has_substance
from llm import GenerationConfig
from llm.factory_defaults import FACTORY_MAX_OUTPUT_TOKENS_HEAVY, FACTORY_TIMEOUT_QA_SEC

from ..base_agent import AgentInput

from .helpers import QA_SYSTEM_PROMPT, _env_float, _qa_extract_json_object, logger


class ScoringMixin:
    """Quality and release scores, the LLM review, browser E2E spec alignment."""

    def _compute_quality_score(
        self,
        static_issues: list,
        test_results: dict,
        import_errors: list,
    ) -> int:
        """Compute a code quality score from 0-100."""
        score = 85  # Start high, deduct for issues

        # Deduct for static analysis issues
        errors = sum(1 for i in static_issues if i.get("type") == "error")
        warnings = sum(1 for i in static_issues if i.get("type") == "warning")
        conventions = sum(1 for i in static_issues if i.get("type") == "convention")

        score -= errors * 5
        score -= warnings * 2
        score -= conventions * 1

        # Deduct for test failures
        score -= test_results.get("failed", 0) * 10

        # Deduct for import errors
        score -= len(import_errors) * 15

        # Bonus for having tests
        if test_results.get("total", 0) > 0:
            pass_percentage = test_results.get("passed", 0) / max(test_results.get("total", 1), 1)
            if pass_percentage > 0.8:
                score += 5

        return max(0, min(100, score))

    def _compute_release_score(
        self,
        *,
        code_quality_score: int,
        demo_report: dict,
        browser_ok: bool,
        backend_ok: bool,
        acceptance_report: dict,
        bug_count: int,
        security_count: int,
        tests_total: int,
        tests_failed: int,
    ) -> int:
        """Composite release score (0-100) for marketplace/release gating."""
        code_w = _env_float("AIFACTORY_RELEASE_SCORE_CODE_WEIGHT", 0.45)
        demo_w = _env_float("AIFACTORY_RELEASE_SCORE_DEMO_WEIGHT", 0.25)
        browser_bonus = _env_float("AIFACTORY_RELEASE_SCORE_BROWSER_PASS_BONUS", 10.0)
        browser_penalty = _env_float("AIFACTORY_RELEASE_SCORE_BROWSER_FAIL_PENALTY", -10.0)
        backend_bonus = _env_float("AIFACTORY_RELEASE_SCORE_BACKEND_PASS_BONUS", 10.0)
        backend_penalty = _env_float("AIFACTORY_RELEASE_SCORE_BACKEND_FAIL_PENALTY", -15.0)
        acceptance_bonus = _env_float("AIFACTORY_RELEASE_SCORE_ACCEPTANCE_PASS_BONUS", 8.0)
        acceptance_penalty = _env_float("AIFACTORY_RELEASE_SCORE_ACCEPTANCE_FAIL_PENALTY", -8.0)
        no_tests_penalty = _env_float("AIFACTORY_RELEASE_SCORE_NO_TESTS_PENALTY", -4.0)
        bug_weight = _env_float("AIFACTORY_RELEASE_SCORE_BUG_WEIGHT", 1.5)
        security_weight = _env_float("AIFACTORY_RELEASE_SCORE_SECURITY_WEIGHT", 4.0)

        score = float(code_quality_score) * code_w
        score += float(demo_report.get("score", 0)) * demo_w
        score += browser_bonus if browser_ok else browser_penalty
        score += backend_bonus if backend_ok else backend_penalty
        score += acceptance_bonus if acceptance_report.get("passed") else acceptance_penalty
        if tests_total > 0:
            pass_ratio = max(0.0, min(1.0, (tests_total - tests_failed) / tests_total))
            score += (pass_ratio - 0.5) * 10.0
        else:
            score += no_tests_penalty
        score -= min(20.0, float(bug_count) * bug_weight)
        score -= min(20.0, float(security_count) * security_weight)
        return int(max(0, min(100, round(score))))

    async def _generate_llm_review(
        self,
        agent_input: AgentInput,
        product_id: str,
        code_files: list[dict],
        is_bug_fix: bool,
    ) -> dict | None:
        """Try to generate an LLM-based review if LLM is available.
        
        Falls back gracefully to None if LLM is unavailable.
        """
        try:
            code_samples = {}
            for file_info in code_files[:10]:
                code_samples[file_info["path"]] = file_info["content"][:2000]

            code_str = prompt_json(code_samples) if code_samples else "No code files found"
            bug_context = agent_input.data.get("bug_context", "")
            try:
                from web.backend.services.owner_chat_routing import format_owner_product_feedback_for_prompt

                owner_fb = format_owner_product_feedback_for_prompt(product_id)
            except Exception:
                owner_fb = ""
            owner_block = (owner_fb + "\n\n") if owner_fb else ""

            prompt = f"""{QA_SYSTEM_PROMPT}

Product ID: {product_id}
{'This is a bug fix verification. Previous bug: ' + bug_context if is_bug_fix else 'Initial QA review.'}

{owner_block}Code Files:
{code_str}

Please perform a thorough QA review of this codebase.
Focus on finding bugs, security issues, and performance problems.
"""

            config = GenerationConfig(
                temperature=0.7,
                max_tokens=FACTORY_MAX_OUTPUT_TOKENS_HEAVY,
                timeout_sec=FACTORY_TIMEOUT_QA_SEC,
                json_mode=True,  # openai_compatible skips response_format for reasoning models
            )

            response = await self._generate(prompt, config=config, agent_input=agent_input)

            result = self._extract_json(response)
            if result is not None:
                return result
        except Exception as _suppressed_exc:
            log_suppressed(logger, "non-fatal (agents/qa.py)", exc_info=_suppressed_exc)

        return None

    async def _browser_e2e_spec_alignment_llm(self, inner_spec: dict, browser_report: dict) -> dict:
        """
        Compare deep crawl observations + page text snippets to the specification (text-only LLM).
        Set ``AIFACTORY_BROWSER_E2E_SPEC_LLM=0`` to skip (saves tokens). Screenshots are stored on disk;
        paths appear in ``deep_crawl.pages[].screenshot`` for human / vision review.
        """
        if os.environ.get("AIFACTORY_BROWSER_E2E_SPEC_LLM", "1").strip().lower() in ("0", "false", "no"):
            return {"skipped": True, "reason": "AIFACTORY_BROWSER_E2E_SPEC_LLM disabled"}
        dc = browser_report.get("deep_crawl")
        if not isinstance(dc, dict) or dc.get("mode") != "deep_crawl":
            return {"skipped": True, "reason": "no_deep_crawl_report"}
        if not _spec_has_substance(inner_spec):
            # No spec on disk means the PM stage never produced one — this comparison has
            # no left-hand side. Running it anyway cost an LLM call per QA round to be told
            # "spec is empty", failed the build for a defect the developer cannot fix, and
            # then *misdirected* the next round: the verdict reads as "the demo invents a
            # brand not grounded in the spec", so the developer deletes correct product
            # naming to satisfy a specification that does not exist. One product burned
            # ~70 developer/QA cycles this way. A gate missing its own input is a pipeline
            # defect, reported as one, and never the product's fault.
            return {
                "skipped": True,
                "reason": "pipeline_input_missing:specification",
                "repair_target": "spec",
            }
        fr = inner_spec.get("functional_requirements")
        fr_trim = fr[:20] if isinstance(fr, list) else []
        excerpt = {
            "product_name": inner_spec.get("product_name"),
            "description": (inner_spec.get("description") or "")[:2800],
            "core_features": (inner_spec.get("core_features") or [])[:16]
            if isinstance(inner_spec.get("core_features"), list)
            else [],
            "functional_requirements": fr_trim,
            "user_stories": (inner_spec.get("user_stories") or [])[:12]
            if isinstance(inner_spec.get("user_stories"), list)
            else [],
        }
        slim_pages = []
        for p in (dc.get("pages") or [])[:40]:
            if not isinstance(p, dict):
                continue
            slim_pages.append(
                {
                    "url": p.get("url"),
                    "status": p.get("status"),
                    "screenshot": p.get("screenshot"),
                    "text_snippet": (p.get("text_snippet") or "")[:900],
                }
            )
        crawl_slim = {
            "pages_visited": dc.get("pages_visited"),
            "navigation_failures": dc.get("navigation_failures"),
            "loopback_hrefs": dc.get("loopback_hrefs"),
            "pages": slim_pages,
        }
        prompt = f"""You are a senior QA engineer reviewing a **generated browser demo** against a product specification.

SPEC excerpt (JSON):
{prompt_json(excerpt, limit=16000)}

Browser deep-crawl summary (visited URLs, HTTP status, text snippets cut from each page; screenshot paths are on-disk artifacts):
{prompt_json(crawl_slim, limit=24000)}

Task:
1. Judge whether the **observable UI and navigable pages** plausibly reflect the spec (features, flows, copy themes).
2. Flag obvious gaps (missing promised sections, auth/demo flows that never appear, broken narrative vs TZ).
3. Do NOT invent hidden server-side behavior — only what snippets suggest.
4. HTTP 401/403 on `/api/*` or a login form is an **authentication wall**, not proof the page is missing. Do not conclude "no operator/analytics console" from a 401 JSON body. A React route in App.tsx still exists.
5. A snippet that is FastAPI JSON (`{{"message": ...}}`) means the crawler hit the API origin, not the SPA. That is a factory preview-serve defect — not a missing heading and not a missing console.

Reply with **ONLY** a JSON object:
{{"passed": <bool>, "alignment_score": <0-100 integer>, "gaps": [<short string>, ...], "notes": "<one paragraph>"}}
Use passed=false if alignment_score < 55 or critical gaps exist."""

        try:
            text = await self.llm_router.generate(
                prompt,
                task_type="qa_testing",
                config=GenerationConfig(
                    timeout_sec=min(int(FACTORY_TIMEOUT_QA_SEC), 240),
                    max_tokens=min(FACTORY_MAX_OUTPUT_TOKENS_HEAVY, 4096),
                ),
            )
        except Exception as e:
            return {"skipped": True, "error": str(e)[:400]}
        parsed = _qa_extract_json_object(text or "")
        if not isinstance(parsed, dict):
            return {"skipped": True, "error": "llm_json_parse_failed", "raw_preview": (text or "")[:400]}
        passed = bool(parsed.get("passed", True))
        score = parsed.get("alignment_score")
        try:
            score_int = int(score) if score is not None else 70
        except (TypeError, ValueError):
            score_int = 70
        gaps = parsed.get("gaps") if isinstance(parsed.get("gaps"), list) else []
        notes = str(parsed.get("notes") or "")[:4000]
        if score_int < 55:
            passed = False
        return {
            "skipped": False,
            "passed": passed,
            "alignment_score": score_int,
            "gaps": [str(g)[:400] for g in gaps[:24]],
            "notes": notes,
        }
