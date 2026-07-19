"""
QA Agent (Quality Assurance)
=============================
Responsible for:
- Testing code for bugs and issues
- Running static analysis (pylint, flake8)
- Executing test files and verifying output
- Testing API endpoints via HTTP calls
- Security vulnerability scanning
- Performance testing
- Reporting bugs with reproduction steps
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path

from agents.product_profile import infer_delivery_profile
from agents.prompt_utils import prompt_json
from agents.prompts.load_prompt import load_prompt
from core.delivery_profile import MARKETING_LANDING, normalize_delivery_profile
from core.logging_utils import log_suppressed
from llm import GenerationConfig, LLMRouter
from llm.factory_defaults import FACTORY_MAX_OUTPUT_TOKENS_HEAVY, FACTORY_TIMEOUT_QA_SEC
from web.backend.services.backend_runtime_e2e import run_backend_runtime_e2e
from web.backend.services.browser_preview_e2e import run_browser_preview_e2e
from web.backend.services.demo_quality import assess_product_demo, quality_gates_pass
from web.backend.services.domain_acceptance_pack import build_domain_acceptance_pack
from web.backend.services.domain_methodology import get_domain_pack, select_domain_pack
from web.backend.services.methodology_review import review_implementation as _methodology_review_implementation
from web.backend.services.perf_slo import evaluate_perf_slo
from web.backend.services.traceability_matrix import build_traceability_matrix

from .base_agent import AgentInput, AgentOutput, BaseAgent

logger = logging.getLogger(__name__)


def _landing_skip_methodology_gate() -> bool:
    """Brochure landings may skip domain methodology only when explicitly disabled."""
    return os.environ.get("AIFACTORY_LANDING_SKIP_METHODOLOGY_QA", "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _resolve_delivery_profile_for_qa(agent_input: AgentInput) -> str:
    data = agent_input.data or {}
    spec_payload = data.get("specification") or {}
    inner = (
        spec_payload.get("specification")
        if isinstance(spec_payload, dict) and "specification" in spec_payload
        else spec_payload
    )
    if isinstance(inner, dict) and inner.get("delivery_profile"):
        return normalize_delivery_profile(str(inner["delivery_profile"]))
    if data.get("delivery_profile"):
        return normalize_delivery_profile(str(data["delivery_profile"]))
    return infer_delivery_profile(data.get("admin_instructions"), data.get("idea"))


def _qa_extract_json_object(text: str) -> dict | None:
    """Best-effort JSON object parse from an LLM reply."""
    raw = text.strip()
    if "```" in raw:
        parts = raw.split("```")
        for block in parts:
            b = block.strip()
            if b.lower().startswith("json"):
                b = b[4:].lstrip()
            if b.startswith("{"):
                try:
                    return json.loads(b)
                except json.JSONDecodeError:
                    continue
    try:
        s = raw.index("{")
        e = raw.rindex("}") + 1
        return json.loads(raw[s:e])
    except (ValueError, json.JSONDecodeError):
        return None


QA_SYSTEM_PROMPT = load_prompt("qa_system_prompt.md")


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)))
    except ValueError:
        return default


class QAAgent(BaseAgent):
    """QA Agent - tests code and reports bugs."""

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

    def __init__(self, llm_router: LLMRouter):
        super().__init__(
            agent_type="qa",
            llm_router=llm_router,
            task_type="qa_testing",
        )

    async def execute(self, agent_input: AgentInput) -> AgentOutput:
        start_time = time.time()
        product_id = agent_input.product_id
        agent_input.data.get("code_data", {})
        is_bug_fix = agent_input.data.get("is_bug_fix", False)

        self._log("INFO", f"Testing product {product_id}")

        delivery_profile = _resolve_delivery_profile_for_qa(agent_input)
        landing_methodology_skip = (
            delivery_profile == MARKETING_LANDING and _landing_skip_methodology_gate()
        )

        try:
            # Mechanical gate fixes before discovery/assessment (loopback URLs, anchors, static stubs).
            try:
                from core.paths import code_dir as product_code_dir
                from web.backend.services.visual_gate_autofix import apply_visual_gate_autofix

                apply_visual_gate_autofix(product_code_dir(product_id))
            except Exception as _autofix_exc:
                log_suppressed(logger, "visual_gate_autofix before QA", exc_info=_autofix_exc)

            # Step 1: Discover code files
            code_files = self._discover_code_files(product_id)
            
            # Step 2: Run static analysis (pylint/flake8 if available)
            static_analysis_results = self._run_static_analysis(code_files)
            
            # Step 3: Execute test files if any exist
            test_results = self._run_tests(code_files)
            
            # Step 4: Try to import and verify Python modules
            import_errors = self._check_imports(code_files)
            
            # Step 5: Generate LLM-based review (if LLM available)
            llm_review = await self._generate_llm_review(
                agent_input, product_id, code_files, is_bug_fix
            )

            # Step 6: Compile all results
            all_bugs = []
            all_security = []
            all_performance = []

            # Add static analysis findings
            for issue in static_analysis_results:
                if any(kw in issue.get("message", "").lower() for kw in ["security", "injection", "xss", "sql"]):
                    all_security.append({
                        "severity": "high", "issue": issue["message"],
                        "file": issue.get("file", ""), "line": issue.get("line", 0),
                    })
                else:
                    all_bugs.append({
                        "severity": issue.get("type", "warning"),
                        "title": issue["message"],
                        "file": issue.get("file", ""), "line": issue.get("line", 0),
                    })

            # Add test failures as bugs
            for test_failure in test_results.get("failures", []):
                all_bugs.append({
                    "severity": "high",
                    "title": f"Test failure: {test_failure.get('name', 'unknown')}",
                    "description": test_failure.get("error", ""),
                    "reproduction_steps": [f"Run: python -m pytest {test_failure.get('file', '')}"],
                })

            # Add import errors
            for imp_err in import_errors:
                all_bugs.append({
                    "severity": "high",
                    "title": f"Import error: {imp_err.get('module', 'unknown')}",
                    "description": imp_err.get("error", ""),
                    "file": imp_err.get("file", ""),
                })

            # Heuristic: detect trivial hard-coded authentication stubs which are not acceptable for real products.
            try:
                insecure_auth = self._scan_for_insecure_auth(code_files)
                all_security.extend(insecure_auth)
            except Exception as e:
                self._log("WARNING", f"Insecure auth scan failed: {e}")

            try:
                realism_issues = self._assess_project_realism(product_id, code_files)
                all_bugs.extend(realism_issues)
            except Exception as e:
                self._log("WARNING", f"Project realism scan failed: {e}")

            # Acceptance criteria -> test traceability gate
            acceptance_report = self._assess_acceptance_traceability(
                agent_input.data.get("specification") or {},
                code_files,
            )
            traceability_matrix = build_traceability_matrix(agent_input.data.get("specification") or {})
            acceptance_pack = build_domain_acceptance_pack(agent_input.data.get("specification") or {})
            if not acceptance_report.get("passed", True):
                all_bugs.append(
                    {
                        "severity": "high",
                        "title": "Acceptance traceability: insufficient automated coverage",
                        "description": acceptance_report.get("summary", "Acceptance criteria are weakly covered by tests."),
                        "file": f"code/{product_id}",
                    }
                )
            if not acceptance_pack.get("passed", True):
                all_bugs.append(
                    {
                        "severity": "high",
                        "title": "Domain acceptance pack: insufficient scenario depth",
                        "description": (
                            f"Only {acceptance_pack.get('scenario_count', 0)} acceptance scenarios detected; "
                            f"minimum required is {acceptance_pack.get('minimum_required', 2)}."
                        ),
                        "file": f"code/{product_id}",
                    }
                )

            maintainability_review = self._assess_maintainability(product_id, code_files)
            if not maintainability_review.get("passed", True):
                all_bugs.append(
                    {
                        "severity": "high",
                        "title": "Maintainability review: architecture/code quality below release bar",
                        "description": maintainability_review.get("summary", "Maintainability checks failed."),
                        "file": f"code/{product_id}",
                    }
                )

            if landing_methodology_skip:
                methodology_review = {
                    "product_id": product_id,
                    "stage": "post_implementation",
                    "domain": None,
                    "domain_label": "marketing_landing",
                    "passed": True,
                    "skipped": True,
                    "reason": "methodology gate skipped for marketing_landing delivery profile",
                }
            else:
                methodology_review = self._assess_methodology(
                    product_id=product_id,
                    idea=str(agent_input.data.get("idea") or ""),
                    category=agent_input.data.get("category"),
                    spec_payload=agent_input.data.get("specification") or {},
                )
            if not methodology_review.get("passed", True):
                for f in methodology_review.get("findings") or []:
                    if not isinstance(f, dict):
                        continue
                    if f.get("severity") != "high":
                        continue
                    all_bugs.append(
                        {
                            "severity": "high",
                            "title": (
                                f"Methodology gate ({methodology_review.get('domain') or 'generic'}): "
                                f"{f.get('code')}"
                            ),
                            "description": f.get("detail", ""),
                            "file": f"code/{product_id}",
                        }
                    )

            # Merge LLM review findings
            if llm_review:
                all_bugs.extend(llm_review.get("bugs_found", []))
                all_security.extend(llm_review.get("security_issues", []))
                all_performance.extend(llm_review.get("performance_concerns", []))

            # --- Demo / sandbox / spec-alignment gates (ship-quality bar) ----------------
            spec_payload = agent_input.data.get("specification") or {}
            inner_spec = (
                spec_payload.get("specification")
                if isinstance(spec_payload, dict) and "specification" in spec_payload
                else spec_payload
            )
            if not isinstance(inner_spec, dict):
                inner_spec = {}
            demo_report = assess_product_demo(product_id, inner_spec)
            for issue in demo_report.get("issues", []):
                if not isinstance(issue, dict):
                    continue
                all_bugs.append(
                    {
                        "severity": "high",
                        "title": f"Demo/TZ gate: {issue.get('code', 'issue')}",
                        "description": issue.get("detail", ""),
                        "file": f"code/{product_id}/index.html",
                    }
                )

            # --- Headless browser E2E (Chromium + Playwright) -----------------------------
            try:
                browser_e2e = await asyncio.to_thread(
                    run_browser_preview_e2e,
                    product_id,
                    str(self.data_root),
                )
            except Exception as be:
                self._log("WARNING", f"Browser E2E thread failed: {be}")
                browser_e2e = {
                    "passed": False,
                    "skipped": False,
                    "error": "browser_e2e_exception",
                    "detail": str(be),
                }

            try:
                align = await self._browser_e2e_spec_alignment_llm(inner_spec, browser_e2e)
            except Exception as ex:
                align = {"skipped": True, "error": str(ex)[:400]}
            browser_e2e["spec_alignment_llm"] = align
            if (
                isinstance(align, dict)
                and not align.get("skipped")
                and align.get("passed") is False
            ):
                browser_e2e["passed"] = False
                gaps = align.get("gaps") or []
                gist = "; ".join(str(g)[:200] for g in gaps[:10]) if gaps else (align.get("notes") or "alignment failure")
                browser_e2e.setdefault("issues", []).append(f"spec_alignment_llm_failed:{gist[:1200]}")

            if not browser_e2e.get("skipped") and not browser_e2e.get("passed", False):
                detail = browser_e2e.get("detail") or browser_e2e.get("error") or "browser check failed"
                for line in browser_e2e.get("issues") or []:
                    all_bugs.append(
                        {
                            "severity": "high",
                            "title": f"Browser E2E: {line[:120]}",
                            "description": line,
                            "file": f"code/{product_id}/index.html",
                        }
                    )
                if not browser_e2e.get("issues"):
                    all_bugs.append(
                        {
                            "severity": "high",
                            "title": "Browser E2E: preview check failed",
                            "description": detail,
                            "file": f"code/{product_id}/index.html",
                        }
                    )

            # --- Runtime backend E2E (boot app + probe health/business route) ------------
            try:
                backend_e2e = await asyncio.to_thread(
                    run_backend_runtime_e2e,
                    product_id,
                    str(self.data_root),
                )
            except Exception as be:
                self._log("WARNING", f"Backend runtime E2E thread failed: {be}")
                backend_e2e = {
                    "passed": False,
                    "skipped": False,
                    "error": "backend_runtime_e2e_exception",
                    "detail": str(be),
                    "issues": [str(be)],
                }

            if not backend_e2e.get("skipped") and not backend_e2e.get("passed", False):
                detail = backend_e2e.get("detail") or backend_e2e.get("error") or "backend runtime check failed"
                for line in backend_e2e.get("issues") or []:
                    all_bugs.append(
                        {
                            "severity": "high",
                            "title": f"Backend runtime E2E: {line[:120]}",
                            "description": line,
                            "file": f"code/{product_id}",
                        }
                    )
                if not backend_e2e.get("issues"):
                    all_bugs.append(
                        {
                            "severity": "high",
                            "title": "Backend runtime E2E: boot/probe failed",
                            "description": detail,
                            "file": f"code/{product_id}",
                        }
                    )

            demo_gates_ok = quality_gates_pass(demo_report, delivery_profile=delivery_profile)
            browser_ok = browser_e2e.get("skipped") or browser_e2e.get("passed", False)
            backend_ok = backend_e2e.get("skipped") or backend_e2e.get("passed", False)
            perf_slo = evaluate_perf_slo(browser_e2e, backend_e2e)
            methodology_ok = bool(methodology_review.get("passed", True))
            gates_ok = (
                demo_gates_ok
                and browser_ok
                and backend_ok
                and bool(perf_slo.get("passed"))
                and methodology_ok
            )
            release_score = self._compute_release_score(
                code_quality_score=self._compute_quality_score(static_analysis_results, test_results, import_errors),
                demo_report=demo_report,
                browser_ok=browser_ok,
                backend_ok=backend_ok,
                acceptance_report=acceptance_report,
                bug_count=len(all_bugs),
                security_count=len(all_security),
                tests_total=test_results.get("total", 0),
                tests_failed=test_results.get("failed", 0),
            )

            if not gates_ok:
                overall_verdict = "needs_fixes"
            elif len(all_security) > 0:
                overall_verdict = "fail"
            elif len(all_bugs) == 0 and test_results.get("failed", 0) == 0:
                overall_verdict = "pass"
            else:
                overall_verdict = "needs_fixes"

            qa_result = {
                "bugs_found": all_bugs,
                "security_issues": all_security,
                "performance_concerns": all_performance,
                "code_quality_score": self._compute_quality_score(static_analysis_results, test_results, import_errors),
                "release_score": release_score,
                "static_analysis": {
                    "issues_found": len(static_analysis_results),
                    "tools_used": ["pylint", "flake8", "py_compile"],
                },
                "test_results": {
                    "passed": test_results.get("passed", 0),
                    "failed": test_results.get("failed", 0),
                    "total": test_results.get("total", 0),
                },
                "import_errors": len(import_errors),
                "overall_verdict": overall_verdict,
                "demo_quality": demo_report,
                "demo_quality_gates_passed": demo_gates_ok,
                "browser_preview_e2e": browser_e2e,
                "browser_e2e_gates_passed": browser_ok,
                "backend_runtime_e2e": backend_e2e,
                "backend_runtime_e2e_passed": backend_ok,
                "quality_gates_all_passed": gates_ok,
                "acceptance_traceability": acceptance_report,
                "domain_acceptance_pack": acceptance_pack,
                "maintainability_review": maintainability_review,
                "methodology_review": methodology_review,
                "methodology_gate_passed": methodology_ok,
                "traceability_matrix": traceability_matrix,
                "perf_slo": perf_slo,
            }

            # Save comprehensive QA report
            self._save_artifact(product_id, "bugs", {
                "product_id": product_id,
                "qa_result": qa_result,
                "is_bug_fix": is_bug_fix,
                "demo_quality": demo_report,
                "demo_quality_gates_passed": demo_gates_ok,
                "browser_preview_e2e": browser_e2e,
                "browser_e2e_gates_passed": browser_ok,
                "backend_runtime_e2e": backend_e2e,
                "backend_runtime_e2e_passed": backend_ok,
                "quality_gates_all_passed": gates_ok,
                "acceptance_traceability": acceptance_report,
                "domain_acceptance_pack": acceptance_pack,
                "maintainability_review": maintainability_review,
                "methodology_review": methodology_review,
                "methodology_gate_passed": methodology_ok,
                "traceability_matrix": traceability_matrix,
                "perf_slo": perf_slo,
                "execution_results": {
                    "static_analysis": static_analysis_results,
                    "test_execution": test_results,
                    "import_errors": import_errors,
                },
                "created_at": time.time(),
                "agent": "qa",
            }, "qa_report.json")

            try:
                tel = self.data_root / "telemetry" / product_id
                tel.mkdir(parents=True, exist_ok=True)
                (tel / "demo_quality_gate.json").write_text(
                    json.dumps(
                        {
                            "demo_quality": demo_report,
                            "demo_gates_passed": demo_gates_ok,
                            "browser_preview_e2e": browser_e2e,
                            "browser_e2e_passed": browser_ok,
                            "backend_runtime_e2e": backend_e2e,
                            "backend_runtime_e2e_passed": backend_ok,
                            "acceptance_traceability": acceptance_report,
                            "domain_acceptance_pack": acceptance_pack,
                            "maintainability_review": maintainability_review,
                            "methodology_review": methodology_review,
                            "methodology_gate_passed": methodology_ok,
                            "traceability_matrix": traceability_matrix,
                            "perf_slo": perf_slo,
                            "gates_all_passed": gates_ok,
                        },
                        indent=2,
                    ),
                    encoding="utf-8",
                )
            except OSError as _suppressed_exc:
                log_suppressed(logger, "non-fatal (agents/qa.py)", exc_info=_suppressed_exc)

            elapsed = time.time() - start_time
            self._log(
                "INFO",
                f"QA complete: {len(all_bugs)} bugs, {len(all_security)} security, "
                f"{test_results.get('total', 0)} tests, browser_e2e={browser_e2e.get('passed')} "
                f"backend_e2e={backend_e2e.get('passed')} skipped={backend_e2e.get('skipped')} "
                f"gates_ok={gates_ok} profile={delivery_profile} ({elapsed:.1f}s)",
            )

            return AgentOutput(
                task_id=agent_input.task_id,
                product_id=product_id,
                agent_type=self.agent_type,
                success=True,
                data={
                    "qa_result": qa_result,
                    "has_bugs": len(all_bugs) > 0,
                    "bug_count": len(all_bugs),
                    "security_count": len(all_security),
                    "quality_score": qa_result.get("code_quality_score", 50),
                    "verdict": qa_result.get("overall_verdict", "needs_fixes"),
                    "qa_file": f"bugs/{product_id}/qa_report.json",
                    "tests_run": test_results.get("total", 0),
                    "tests_passed": test_results.get("passed", 0),
                    "quality_gates": {
                        "passed": gates_ok,
                        "demo_quality": demo_report,
                        "browser_preview_e2e": browser_e2e,
                        "backend_runtime_e2e": backend_e2e,
                        "acceptance_traceability": acceptance_report,
                        "domain_acceptance_pack": acceptance_pack,
                        "maintainability_review": maintainability_review,
                        "methodology_review": methodology_review,
                        "methodology_gate_passed": methodology_ok,
                        "traceability_matrix": traceability_matrix,
                        "perf_slo": perf_slo,
                        "reasons": [i.get("detail") for i in demo_report.get("issues", []) if isinstance(i, dict)]
                        + (browser_e2e.get("issues") or [])
                        + (backend_e2e.get("issues") or [])
                        + [
                            f"methodology[{methodology_review.get('domain') or 'generic'}]: "
                            f"{f.get('detail') or f.get('code')}"
                            for f in (methodology_review.get("findings") or [])
                            if isinstance(f, dict) and f.get("severity") == "high"
                        ]
                        + (perf_slo.get("issues") or []),
                    },
                    "peer_review": {
                        "recommended": "approve" if gates_ok else "block",
                        "blockers": ([] if gates_ok else ([(i.get("detail") or i.get("code")) for i in demo_report.get("issues", []) if isinstance(i, dict)] + (browser_e2e.get("issues") or []) + (backend_e2e.get("issues") or []))),
                        "notes": "QA peer review gate over demo/runtime/acceptance/maintainability.",
                    },
                },
                timestamp=time.time(),
                metrics={
                    "elapsed_seconds": elapsed,
                    "bugs_found": len(all_bugs),
                    "security_issues": len(all_security),
                    "tests_run": test_results.get("total", 0),
                    "tests_passed": test_results.get("passed", 0),
                    "quality_score": qa_result.get("code_quality_score", 50),
                },
            )

        except Exception as e:
            elapsed = time.time() - start_time
            self._log("ERROR", f"QA testing failed: {e}")
            self._log("ERROR", traceback.format_exc())
            return AgentOutput(
                task_id=agent_input.task_id,
                product_id=product_id,
                agent_type=self.agent_type,
                success=False,
                error=str(e),
                timestamp=time.time(),
                metrics={"elapsed_seconds": elapsed},
            )

    def _discover_code_files(self, product_id: str) -> list[dict]:
        """Discover Python code files for this product."""
        files = []
        from core.code_discovery import iter_product_files, should_skip_code_path
        from core.paths import agent_artifact_dir, code_dir

        search_dirs = [
            code_dir(product_id),
            agent_artifact_dir("dev", product_id),
        ]
        for search_dir in search_dirs:
            if not search_dir.exists():
                continue
            for fpath in iter_product_files(search_dir, "*.py"):
                if should_skip_code_path(fpath):
                    continue
                try:
                    content = fpath.read_text()
                    files.append({
                        "path": str(fpath),
                        "content": content,
                        "size": len(content),
                        "lines": content.count("\n") + 1,
                    })
                except Exception as _suppressed_exc:
                    log_suppressed(logger, "non-fatal (agents/qa.py)", exc_info=_suppressed_exc)
        return files

    def _scan_for_insecure_auth(self, code_files: list[dict]) -> list[dict]:
        """Detect trivial hard-coded auth patterns (e.g. demo login stubs)."""
        issues: list[dict] = []
        for file_info in code_files:
            path = file_info.get("path", "")
            content = file_info.get("content", "")
            lower = content.lower()
            if "login" not in lower and "auth" not in lower:
                continue
            # Very basic heuristic: hard-coded email/password pair in a conditional.
            if "admin@example.com" in lower and "password" in lower and "== 'password'" in content:
                issues.append(
                    {
                        "severity": "high",
                        "issue": "Hard-coded demo credentials in authentication logic",
                        "affected_code": path,
                        "recommendation": (
                            "Remove hard-coded email/password checks. Introduce a user store and "
                            "verify hashed passwords instead."
                        ),
                    }
                )
        return issues

    def _assess_acceptance_traceability(self, spec_payload: dict, code_files: list[dict]) -> dict:
        """
        Check that generated tests reference acceptance criteria semantics.
        Lightweight heuristic for now: keyword overlap from criteria -> test files.
        """
        inner = spec_payload.get("specification") if isinstance(spec_payload, dict) and "specification" in spec_payload else spec_payload
        spec = inner if isinstance(inner, dict) else {}

        criteria: list[str] = []
        for us in spec.get("user_stories") or []:
            if isinstance(us, dict):
                ac = us.get("acceptance_criteria")
                if isinstance(ac, str) and ac.strip():
                    criteria.append(ac.strip())
        for fr in spec.get("functional_requirements") or []:
            if isinstance(fr, dict):
                ac = fr.get("acceptance_criteria")
                if isinstance(ac, str) and ac.strip():
                    criteria.append(ac.strip())

        if not criteria:
            return {"passed": True, "criteria_total": 0, "covered": 0, "summary": "No acceptance criteria to trace."}

        test_files = [
            f for f in code_files
            if Path(str(f.get("path", ""))).name.startswith("test_")
            or "/tests/" in str(f.get("path", "")).replace("\\", "/").lower()
        ]
        if not test_files:
            return {
                "passed": False,
                "criteria_total": len(criteria),
                "covered": 0,
                "summary": "Specification has acceptance criteria but no explicit test files were generated.",
            }

        test_blob = "\n".join(str(f.get("content", "")).lower() for f in test_files)

        stop = {"with", "from", "that", "this", "have", "will", "must", "should", "when", "then", "user", "users", "into", "over", "under", "after", "before", "their", "there", "where"}
        covered = 0
        missing_samples: list[str] = []
        for c in criteria:
            tokens = [t for t in re.split(r"[^a-z0-9]+", c.lower()) if len(t) >= 5 and t not in stop]
            key_tokens = tokens[:5]
            if key_tokens and any(tok in test_blob for tok in key_tokens):
                covered += 1
            else:
                missing_samples.append(c[:120])

        ratio = covered / max(1, len(criteria))
        passed = ratio >= 0.5
        return {
            "passed": passed,
            "criteria_total": len(criteria),
            "covered": covered,
            "coverage_ratio": round(ratio, 3),
            "missing_examples": missing_samples[:5],
            "summary": (
                f"Acceptance criteria coverage in tests: {covered}/{len(criteria)} "
                f"({int(ratio * 100)}%). Minimum required: 50%."
            ),
        }

    def _assess_project_realism(self, product_id: str, code_files: list[dict]) -> list[dict]:
        """
        Flag toy backend structures that are unlikely to be sellable.

        This check is intentionally heuristic and lightweight:
        - backend-like code should ship with tests;
        - backend-like code should include minimal docs (README);
        - extremely tiny backend module count is suspicious for non-trivial products.
        """
        issues: list[dict] = []
        if not code_files:
            return issues

        py_files = [f for f in code_files if str(f.get("path", "")).endswith(".py")]
        py_count = len(py_files)
        py_blob = "\n".join(str(f.get("content", "")) for f in py_files).lower()

        backend_like = any(
            tok in py_blob
            for tok in ("fastapi", "flask", "django", "@app.", "apirouter", "http")
        )
        if not backend_like:
            return issues

        has_tests = any(
            "/tests/" in str(f.get("path", "")).replace("\\", "/").lower()
            or Path(str(f.get("path", ""))).name.startswith("test_")
            for f in py_files
        )
        if not has_tests:
            issues.append(
                {
                    "severity": "high",
                    "title": "Backend realism: missing explicit test files",
                    "description": (
                        "Backend/API project detected but no dedicated test modules were found "
                        "(expected tests/test_*.py or test_*.py)."
                    ),
                    "file": f"code/{product_id}",
                }
            )

        code_root = Path(self.data_root) / "code" / product_id
        has_readme = (code_root / "README.md").is_file() or (code_root / "readme.md").is_file()
        if not has_readme:
            issues.append(
                {
                    "severity": "medium",
                    "title": "Backend realism: missing README",
                    "description": (
                        "No README found for generated backend package. "
                        "A sellable project should document setup, run, and test commands."
                    ),
                    "file": f"code/{product_id}",
                }
            )

        # If API stack appears to be in a single tiny file, it is likely still a demo skeleton.
        if py_count <= 2:
            issues.append(
                {
                    "severity": "medium",
                    "title": "Backend realism: structure too thin",
                    "description": (
                        "Backend/API code appears to be very small (<=2 Python files). "
                        "Expected clearer separation (routes/services/models/tests) for production-like output."
                    ),
                    "file": f"code/{product_id}",
                }
            )

        # Flag obvious fake API behavior often seen in demo stubs.
        saw_api_handlers = False
        saw_stateful_signal = False
        for file_info in py_files:
            path = str(file_info.get("path", ""))
            content = str(file_info.get("content", ""))
            lower = content.lower()
            api_like = any(tok in lower for tok in ("@app.", "apirouter", "def login", "def register"))
            if not api_like:
                continue
            saw_api_handlers = True

            fake_markers = (
                "mock-jwt-token",
                "mock token",
                "demo token",
                "return {'token': 'mock",
                'return {"token": "mock',
            )
            if any(m in lower for m in fake_markers):
                issues.append(
                    {
                        "severity": "high",
                        "title": "Backend realism: mocked API auth response",
                        "description": (
                            "API/login handler appears to return fake token payloads. "
                            "Replace with real auth flow and persistence-backed credential verification."
                        ),
                        "file": path,
                    }
                )

            # Heuristic: endpoints that look like static JSON stubs.
            # Example pattern:
            #   @app.get(...)
            #   def x(...):
            #       return {"ok": true}
            # This should be treated as non-sellable for non-trivial backend products.
            static_return_hits = 0
            for line in content.splitlines():
                s = line.strip().lower()
                if s.startswith(("return {", 'return {"', "return {'")):
                    static_return_hits += 1
            if "@app." in lower and static_return_hits >= 2:
                issues.append(
                    {
                        "severity": "high",
                        "title": "Backend realism: constant-only API responses",
                        "description": (
                            "Multiple API handlers appear to return static JSON stubs. "
                            "Implement real business logic, persistence-backed state, and input-driven behavior."
                        ),
                        "file": path,
                    }
                )

            # Stateful behavior hints: persistence, service/repository usage, or write operations.
            stateful_markers = (
                "sqlite",
                "sqlalchemy",
                "session",
                "repository",
                "service.",
                "crud",
                "insert ",
                "update ",
                "delete ",
                ".append(",
                ".add(",
                ".commit(",
                "save(",
                "create(",
            )
            if any(tok in lower for tok in stateful_markers):
                saw_stateful_signal = True

        if saw_api_handlers and not saw_stateful_signal:
            issues.append(
                {
                    "severity": "high",
                    "title": "Backend realism: no stateful behavior signals",
                    "description": (
                        "API handlers were detected, but no persistence/service/state-change signals were found. "
                        "Implement stateful business behavior (storage/repository/service writes), not stateless stubs."
                    ),
                    "file": f"code/{product_id}",
                }
            )

        return issues

    def _run_static_analysis(self, code_files: list[dict]) -> list[dict]:
        """Run static analysis tools on discovered code files.
        
        Attempts to use available tools (pylint, flake8, py_compile).
        Falls back gracefully if tools aren't installed.
        """
        issues = []

        for file_info in code_files:
            fpath = file_info["path"]
            content = file_info["content"]

            # 1. Try py_compile (built-in syntax check)
            try:
                compile(content, fpath, "exec")
            except SyntaxError as e:
                issues.append({
                    "type": "error",
                    "tool": "py_compile",
                    "file": fpath,
                    "line": e.lineno or 0,
                    "message": f"SyntaxError: {e.msg}",
                })

            # 2. Try pylint if available
            try:
                result = subprocess.run(
                    [sys.executable, "-m", "pylint", "--score=n", fpath],
                    capture_output=True, text=True, timeout=15,
                )
                for line in result.stdout.split("\n"):
                    if ":" in line and line.strip():
                        parts = line.split(":")
                        if len(parts) >= 4:
                            issues.append({
                                "type": parts[2].strip() if len(parts) > 2 else "warning",
                                "tool": "pylint",
                                "file": fpath,
                                "line": parts[1].strip() if len(parts) > 1 else 0,
                                "message": ":".join(parts[3:]).strip(),
                            })
            except (FileNotFoundError, subprocess.TimeoutExpired, Exception) as _suppressed_exc:
                log_suppressed(logger, "non-fatal (agents/qa.py)", exc_info=_suppressed_exc)

            # 3. Try flake8 if available
            try:
                result = subprocess.run(
                    [sys.executable, "-m", "flake8", fpath],
                    capture_output=True, text=True, timeout=15,
                )
                for line in result.stdout.split("\n"):
                    if line.strip():
                        parts = line.split(":")
                        if len(parts) >= 4:
                            issues.append({
                                "type": "warning",
                                "tool": "flake8",
                                "file": parts[0],
                                "line": parts[1],
                                "message": ":".join(parts[3:]).strip(),
                            })
            except (FileNotFoundError, subprocess.TimeoutExpired, Exception) as _suppressed_exc:
                log_suppressed(logger, "non-fatal (agents/qa.py)", exc_info=_suppressed_exc)

        return issues

    def _run_tests(self, code_files: list[dict]) -> dict:
        """Discover and execute test files.
        
        Finds files matching test_*.py or *_test.py patterns and runs them.
        """
        results = {"passed": 0, "failed": 0, "total": 0, "failures": []}
        test_files = []

        from core.code_discovery import should_skip_code_path

        for file_info in code_files:
            fpath = Path(str(file_info["path"]))
            if should_skip_code_path(fpath):
                continue
            fname = fpath.name
            if fname.startswith("test_") or fname.endswith("_test.py"):
                test_files.append(str(fpath))

        if not test_files:
            # Generate basic test cases from code
            test_files = self._generate_tests(code_files)
            if not test_files:
                return results

        # Run each test file
        for test_file in test_files:
            try:
                result = subprocess.run(
                    [sys.executable, "-m", "pytest", test_file, "-v", "--tb=short"],
                    capture_output=True, text=True, timeout=30,
                )
                # Parse pytest output
                stdout = result.stdout
                # Count passed/failed from pytest summary
                if "passed" in stdout and "failed" in stdout:
                    import re
                    passed_match = re.search(r'(\d+) passed', stdout)
                    failed_match = re.search(r'(\d+) failed', stdout)
                    if passed_match:
                        results["passed"] += int(passed_match.group(1))
                    if failed_match:
                        results["failed"] += int(failed_match.group(1))
                        # Extract failure details
                        for line in stdout.split("\n"):
                            if "FAILED" in line:
                                results["failures"].append({
                                    "name": line.strip(),
                                    "file": test_file,
                                    "error": line.strip(),
                                })
                results["total"] = results["passed"] + results["failed"]
            except (FileNotFoundError, subprocess.TimeoutExpired, Exception) as e:
                results["failures"].append({
                    "name": "pytest execution failed",
                    "file": test_file,
                    "error": str(e),
                })

        return results

    def _generate_tests(self, code_files: list[dict]) -> list[str]:
        """Generate basic test files from code if none exist.
        
        Creates temporary test files that verify basic functionality
        like import validity and function existence.
        """
        generated_tests = []

        for file_info in code_files:
            fpath = file_info["path"]
            try:
                # Parse imports from the file
                import_lines = []
                for line in file_info["content"].split("\n"):
                    line = line.strip()
                    if line.startswith(("import ", "from ")):
                        import_lines.append(line)

                if import_lines:
                    # Create a basic test that verifies imports work
                    test_content = (
                        "#!/usr/bin/env python3\n"
                        "\"\"\"Auto-generated QA test for imports.\"\"\"\n"
                        "import sys\n"
                        "import os\n"
                        f"sys.path.insert(0, os.path.dirname('{fpath}'))\n"
                        "\n"
                    )
                    for imp_line in import_lines:
                        test_content += f"def test_{imp_line.split()[1].split('.')[0]}_import():\n"
                        test_content += f"    \"\"\"Verify {imp_line} works.\"\"\"\n"
                        test_content += "    try:\n"
                        test_content += f"        {imp_line}\n"
                        test_content += "        assert True\n"
                        test_content += "    except ImportError as e:\n"
                        test_content += "        assert False, f'Import failed: {e}'\n"
                        test_content += "\n"

                    test_dir = Path(tempfile.mkdtemp())
                    test_file = test_dir / f"test_{Path(fpath).stem}.py"
                    test_file.write_text(test_content)
                    generated_tests.append(str(test_file))
            except Exception as _suppressed_exc:
                log_suppressed(logger, "non-fatal (agents/qa.py)", exc_info=_suppressed_exc)

        return generated_tests

    def _check_imports(self, code_files: list[dict]) -> list[dict]:
        """Try to import and verify Python modules.
        
        This actually executes code to check for import/runtime errors.
        """
        errors = []

        for file_info in code_files[:5]:  # Limit to 5 files
            fpath = file_info["path"]
            try:
                # Add parent dir to sys.path
                parent = str(Path(fpath).parent)
                if parent not in sys.path:
                    sys.path.insert(0, parent)

                # Try to compile and check the AST
                compile(file_info["content"], fpath, "exec")
            except SyntaxError as e:
                errors.append({
                    "file": fpath,
                    "module": Path(fpath).stem,
                    "error": f"SyntaxError at line {e.lineno}: {e.msg}",
                })

        return errors

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

    def _assess_methodology(
        self,
        *,
        product_id: str,
        idea: str,
        category: str | None,
        spec_payload: dict,
    ) -> dict:
        """Domain methodology gate (post-implementation). See ``agents.methodologist``."""
        inner_spec = (
            spec_payload.get("specification")
            if isinstance(spec_payload, dict) and "specification" in spec_payload
            else spec_payload
        )
        if not isinstance(inner_spec, dict):
            inner_spec = {}

        forced = ""
        if isinstance(inner_spec, dict):
            forced = str(inner_spec.get("domain") or "").strip()
        pack = get_domain_pack(forced) if forced else None
        if pack is None:
            pack = select_domain_pack(idea or "", category=category, spec=inner_spec)
        if pack is None:
            return {
                "product_id": product_id,
                "stage": "post_implementation",
                "domain": None,
                "domain_label": "not_applicable",
                "score": None,
                "checks": {},
                "findings": [],
                "passed": True,
                "skipped": True,
                "reason": "no matching domain methodology pack",
            }

        code_dir = self.data_root / "code" / product_id
        report = _methodology_review_implementation(
            code_dir,
            pack=pack,
            spec=inner_spec,
            stage="post_implementation",
        )
        report["product_id"] = product_id
        try:
            tel_dir = self.data_root / "telemetry" / product_id
            tel_dir.mkdir(parents=True, exist_ok=True)
            (tel_dir / "methodology_implementation.json").write_text(
                json.dumps(report, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as _suppressed_exc:
            log_suppressed(logger, "non-fatal (agents/qa.py)", exc_info=_suppressed_exc)
        return report

    def _assess_maintainability(self, product_id: str, code_files: list[dict]) -> dict:
        """
        Lightweight maintainability review:
        - ensure architecture artifact exists;
        - ensure non-trivial backend has layered module shape.
        """
        Path(self.data_root) / "code" / product_id
        arch_path = Path(self.data_root) / "arch" / product_id / "architecture.json"
        py_paths = [str(f.get("path", "")) for f in code_files if str(f.get("path", "")).endswith(".py")]
        py_count = len(py_paths)
        has_arch = arch_path.is_file()
        has_layers = any(
            any(tok in p.lower() for tok in ("/service", "/repository", "/models", "/routes", "/api"))
            for p in py_paths
        )
        backend_like = any(
            tok in "\n".join(str(f.get("content", "")).lower() for f in code_files)
            for tok in ("fastapi", "flask", "django", "@app.", "apirouter")
        )
        issues: list[str] = []
        if not has_arch:
            issues.append("architecture artifact missing (arch/<product>/architecture.json)")
        if backend_like and py_count >= 3 and not has_layers:
            issues.append("backend files lack clear layering (expected routes/services/models/repository split)")
        passed = len(issues) == 0
        return {
            "passed": passed,
            "issues": issues,
            "summary": "Maintainability checks passed." if passed else "; ".join(issues),
            "python_file_count": py_count,
            "has_architecture_artifact": has_arch,
        }

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
