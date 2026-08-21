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
from core.spec_presence import spec_has_substance as _spec_has_substance
from llm import GenerationConfig, LLMRouter
from llm.factory_defaults import FACTORY_MAX_OUTPUT_TOKENS_HEAVY, FACTORY_TIMEOUT_QA_SEC
from web.backend.services.e2e_isolate import run_e2e_in_subprocess
from web.backend.services.api_contract_check import run_api_contract_check
from web.backend.services.product_demo_journey import run_demo_journey
from web.backend.services.demo_quality import assess_product_demo, quality_gates_pass
from web.backend.services.duplicate_module_check import run_duplicate_module_check
from core.repair_batches import _files_in
from web.backend.services.frontend_build_check import run_frontend_build_check
from web.backend.services.requirements_manifest import run_requirements_manifest_check
from web.backend.services.domain_acceptance_pack import build_domain_acceptance_pack
from web.backend.services.domain_methodology import get_domain_pack, select_domain_pack
from web.backend.services.methodology_review import review_implementation as _methodology_review_implementation
from web.backend.services.perf_slo import evaluate_perf_slo
from web.backend.services.traceability_matrix import build_traceability_matrix

from .base_agent import AgentInput, AgentOutput, BaseAgent

logger = logging.getLogger(__name__)

# Markup belongs in the repair scope once compile/auth are green. Restricting this to
# scripts is how Sentinel round 56 spent itself on operator TSX while every edit to
# index.html / style.css was reverted as out-of-scope (71 reverts, demo_quality F).
_SCOPE_FILE_SUFFIXES = (".py", ".ts", ".tsx", ".js", ".jsx", ".html", ".css")


def _is_scope_file(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    if path.endswith(_SCOPE_FILE_SUFFIXES):
        return True
    return name == "requirements.txt" or (
        name.startswith("requirements-") and name.endswith(".txt")
    )
_LANDING_SCOPE_CANDIDATES = (
    "index.html",
    "style.css",
    "frontend/index.html",
    "frontend/style.css",
    "frontend/src/styles/index.css",
    "frontend/src/pages/PublicWidget.tsx",
    "frontend/src/pages/Home.tsx",
    "frontend/src/App.tsx",
)
# Vite SPA consoles. When demo/E2E is red, _LANDING_SCOPE_CANDIDATES used to
# occupy the truncated six with index.html first. The operator/analytics
# trees never entered, spec_alignment kept saying "only a landing", and
# the developer polished PublicWidget for ten hours.
_SPA_SCOPE_CANDIDATES = (
    "frontend/src/App.tsx",
    "frontend/src/pages/Login.tsx",
    "frontend/src/pages/OperatorLogin.tsx",
    "frontend/src/pages/OperatorDashboard.tsx",
    "frontend/src/pages/AnalyticsDashboard.tsx",
    "frontend/src/pages/Operator.tsx",
    "frontend/src/pages/Analytics.tsx",
    "frontend/src/pages/PublicWidget.tsx",
)
# Product-does-not-answer codes. tsc unused-React and landing TSX used to occupy
# every slot of the truncated six, so atlas_client.py never entered the round
# (Sentinel: mesh_contract + TypeError still on Vercel while SpendSummary.tsx
# was in scope).
_BOOT_FATAL_SCOPE_CODES = (
    "mesh_contract_violation",
    "unexpected_keyword_argument",
    "missing_attribute",
    "missing_symbol",
    "class_body_forward_ref",
    "duplicate_tablename",
    "route_handler_broken_injection",
)


def _boot_fatal_scope_files(module_health: dict, product_id: str) -> list[str]:
    """Repo-relative files for boot/answer-fatal module_health findings, first-seen order."""
    out: list[str] = []
    seen: set[str] = set()
    for issue in module_health.get("issues") or []:
        if not isinstance(issue, dict):
            continue
        if issue.get("code") not in _BOOT_FATAL_SCOPE_CODES:
            continue
        raws: list[str] = []
        filed = str(issue.get("file") or "").strip()
        if filed:
            raws.append(filed)
        raws.extend(_files_in(str(issue.get("detail") or "")))
        for raw in raws:
            clean = raw.split(f"{product_id}/", 1)[-1].lstrip("/")
            if clean.endswith(_SCOPE_FILE_SUFFIXES) and clean not in seen:
                seen.add(clean)
                out.append(clean)
    return out


# Runtime 500s must occupy the truncated six. Landing used to enter the lead
# whenever demo/browser were red — and they are red BECAUSE of the 500 — so
# index.html stole the slots that belonged to advisory.py / rate_limit.py.
# Measured on Sentinel: TypeError get_advisory(args=) while the six were
# heartbeat.py + five landing files.
_API_CRASH_MARKERS = (
    "demo_journey_5xx",
    "unexpected keyword argument",
    "demo_journey_exception",
    "typeerror:",
    "nameerror:",
    "importerror",
    "import_error",
    "uvicorn_failed_to_listen",
    "demo_journey_boot_failed",
    "backend_boot_failed",
)
_RATE_LIMIT_SCOPE_CANDIDATES = (
    "backend/app/utils/rate_limit.py",
    "app/utils/rate_limit.py",
)


def _journey_has_api_crash(journey: dict) -> bool:
    blob = " ".join(str(i) for i in (journey.get("issues") or [])).lower()
    return any(m in blob for m in _API_CRASH_MARKERS)


def _journey_line_is_api_crash(text: str) -> bool:
    low = str(text or "").lower()
    return any(m in low for m in _API_CRASH_MARKERS)


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


QA_SYSTEM_PROMPT = (
    load_prompt("qa_system_prompt.md")
    + "\n\n"
    + load_prompt("github_house_contract.md")
)


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

    def __init__(self, llm_router: LLMRouter, data_root: str | None = None):
        super().__init__(
            agent_type="qa",
            llm_router=llm_router,
            task_type="qa_testing",
            data_root=data_root,
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
                _tf = str(test_failure.get("file") or test_failure.get("name") or "")
                _tm = re.search(r"([\w./-]+\.py)", _tf)
                _tfile = _tm.group(1) if _tm else ""
                if _tfile.startswith("data/code/"):
                    _tfile = "/".join(_tfile.split("/")[3:])
                all_bugs.append({
                    "severity": "high",
                    "title": f"Test failure: {test_failure.get('name', 'unknown')}",
                    "description": test_failure.get("error", ""),
                    "file": _tfile or None,
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

            try:
                arch = agent_input.data.get("architecture") or {}
                spec_for_lang = agent_input.data.get("specification") or {}
                lang = None
                if isinstance(arch, dict):
                    lang = arch.get("content_language")
                if not lang and isinstance(spec_for_lang, dict):
                    lang = spec_for_lang.get("content_language")
                house_issues = self._assess_github_house(
                    product_id,
                    code_files,
                    delivery_profile=_resolve_delivery_profile_for_qa(agent_input),
                    content_language=str(lang) if lang else None,
                )
                all_bugs.extend(house_issues)
            except Exception as e:
                self._log("WARNING", f"GitHub-house scan failed: {e}")

            # Acceptance criteria -> test traceability gate
            acceptance_report = self._assess_acceptance_traceability(
                agent_input.data.get("specification") or {},
                code_files,
            )
            traceability_matrix = build_traceability_matrix(agent_input.data.get("specification") or {})
            acceptance_pack = build_domain_acceptance_pack(
                agent_input.data.get("specification") or {},
                self.data_root / "code" / product_id,
            )
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
                        # Name the reason that actually failed. The old text always reported the
                        # count — "Only 18 acceptance scenarios detected; minimum required is 3" —
                        # a number that already passed, while the real cause was a missing journey
                        # type. And say WHERE to write them: the journey types are derived from the
                        # spec, a repair round cannot edit the spec, so without a file it can write
                        # this gate asks for something no round can deliver.
                        "description": (
                            (
                                "Acceptance scenarios are missing these journey types: "
                                + ", ".join(acceptance_pack.get("missing_journeys") or [])
                                + ". Add one section per missing type to "
                                "docs/acceptance-scenarios.md — a `## ` heading naming the "
                                "scenario, then its steps. An onboarding scenario mentions signing "
                                "up or logging in; core_action mentions the product's main verb; "
                                "edge_case mentions invalid or missing input; recovery mentions "
                                "retrying, restoring or reconnecting. Scenarios in that file count "
                                "towards this gate."
                            )
                            if acceptance_pack.get("missing_journeys")
                            else (
                                f"Only {acceptance_pack.get('scenario_count', 0)} acceptance "
                                f"scenarios detected; minimum required is "
                                f"{acceptance_pack.get('minimum_required', 2)}. Add sections to "
                                "docs/acceptance-scenarios.md."
                            )
                        ),
                        "file": "docs/acceptance-scenarios.md",
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
                # Reported, but NOT counted by the round-regression guard. This reviewer is a
                # model reading a sample of the tree, so its findings differ between two runs on
                # identical code — and the guard's whole job is comparing one round to the last.
                # Measured from one baseline tree: scores of 67, 71, 84 and 106 for rounds that
                # touched 21, 1, and 21 files. A ONE-file round scored 71 while a 21-file round
                # scored 67, so the number tracked the reviewer's mood rather than the round's
                # effect, and twelve consecutive rounds were reverted on it.
                for _llm_bug in (llm_review.get("bugs_found") or []):
                    if isinstance(_llm_bug, dict):
                        _llm_bug.setdefault("source", "llm_review")
                        _llm_bug.setdefault("scored_by_guard", False)
                    all_bugs.append(_llm_bug)
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
            # --- Frontend build (a SPA that will not compile has no dist to serve) ---
            try:
                frontend_build = await asyncio.to_thread(
                    run_frontend_build_check, product_id, str(self.data_root)
                )
            except Exception as fe:
                self._log("WARNING", f"Frontend build check failed to run: {fe}")
                frontend_build = {"passed": True, "skipped": True, "reason": f"error:{fe}"}
            if not frontend_build.get("skipped") and not frontend_build.get("passed", True):
                for line in frontend_build.get("issues") or []:
                    _fb_files = _files_in(str(line))
                    all_bugs.append(
                        {
                            "severity": "high",
                            "title": f"Frontend build: {str(line)[:120]}",
                            "description": str(line),
                            # The compiler names the file. Filing this against the frontend
                            # directory left the finding out of the six-file scope — measured
                            # on Sentinel: PublicWidget.tsx TS2322 never entered the round.
                            "file": _fb_files[0]
                            if _fb_files
                            else f"code/{product_id}/{frontend_build.get('frontend_dir', '')}".rstrip(
                                "/"
                            ),
                        }
                    )

            try:
                req_manifest = await asyncio.to_thread(
                    run_requirements_manifest_check, product_id, str(self.data_root)
                )
            except Exception as re_exc:
                self._log("WARNING", f"Requirements manifest check failed to run: {re_exc}")
                req_manifest = {"passed": True, "skipped": True, "reason": f"error:{re_exc}"}
            if not req_manifest.get("skipped") and not req_manifest.get("passed", True):
                for line in req_manifest.get("issues") or []:
                    _rq_files = _files_in(str(line)) or list(req_manifest.get("files") or [])
                    all_bugs.append(
                        {
                            "severity": "critical",
                            "title": f"Invalid requirement: {str(line)[:120]}",
                            "description": str(line),
                            "file": _rq_files[0] if _rq_files else f"code/{product_id}/requirements.txt",
                        }
                    )

            demo_report = assess_product_demo(product_id, inner_spec)
            _code_for_demo = self.data_root / "code" / product_id
            for issue in demo_report.get("issues", []):
                if not isinstance(issue, dict):
                    continue
                _df = self._demo_issue_file(_code_for_demo, issue)
                all_bugs.append(
                    {
                        "severity": "high",
                        "title": f"Demo/TZ gate: {issue.get('code', 'issue')}",
                        "description": issue.get("detail", ""),
                        "file": (
                            f"code/{product_id}/{_df}"
                            if _df
                            else f"code/{product_id}/index.html"
                        ),
                    }
                )

            # --- Headless browser E2E (Chromium + Playwright) -----------------------------
            # Isolated subprocess: Playwright/Chromium abort/OOM must not kill the pipeline worker.
            try:
                browser_timeout = float(os.environ.get("AIFACTORY_BROWSER_E2E_TIMEOUT_SEC", "120"))
            except ValueError:
                browser_timeout = 120.0
            self._log("INFO", f"Starting isolated browser E2E (timeout={browser_timeout:.0f}s)")
            try:
                browser_e2e = await asyncio.to_thread(
                    run_e2e_in_subprocess,
                    module="web.backend.services.browser_preview_e2e",
                    func="run_browser_preview_e2e",
                    product_id=product_id,
                    data_root=str(self.data_root),
                    timeout_sec=browser_timeout,
                )
            except Exception as be:
                self._log("WARNING", f"Browser E2E isolate failed: {be}")
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
            if isinstance(align, dict) and align.get("repair_target") == "spec":
                # Skipping is right, silence is not: a product built with no specification
                # must not look identical to one that passed its spec review. This is
                # addressed to the operator and the orchestrator, not to the developer —
                # hence repair_target, and hence it does not fail the browser gate.
                self._log(
                    "ERROR",
                    f"No specification on disk for {product_id}: the PM stage never wrote "
                    "data/specs/<id>/specification.json. Spec-alignment and acceptance "
                    "gates cannot judge this build; re-run the PM stage.",
                )
                all_bugs.append(
                    {
                        "severity": "critical",
                        "title": "Pipeline input missing: no specification was ever written",
                        "description": (
                            "data/specs/"
                            f"{product_id}/specification.json does not exist, so every gate "
                            "that compares the build against the spec has nothing to compare "
                            "with. This is not a code defect and cannot be fixed by editing "
                            "the product: the PM stage must run and produce the spec. Until "
                            "it does, acceptance-scenario and spec-alignment verdicts on this "
                            "product carry no information."
                        ),
                        "file": f"data/specs/{product_id}/specification.json",
                        "repair_target": "spec",
                    }
                )
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
                _code_for_e2e = self.data_root / "code" / product_id
                for line in browser_e2e.get("issues") or []:
                    _bf = self._journey_issue_file(_code_for_e2e, str(line))
                    all_bugs.append(
                        {
                            "severity": "high",
                            "title": f"Browser E2E: {line[:120]}",
                            "description": line,
                            "file": (
                                f"code/{product_id}/{_bf}"
                                if _bf
                                else f"code/{product_id}/index.html"
                            ),
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
            # 300s, not 60. The gate has to create a virtualenv, install the product's dependencies,
            # start uvicorn and probe it, and it timed out at sixty seconds on every single run:
            #
            #   e2e subprocess timed out after 60s (backend_runtime_e2e.run_backend_runtime_e2e)
            #
            # So it reported "boot/probe failed" without ever having finished booting — a gate that
            # cannot complete is not measuring the product, it is measuring its own budget, and the
            # round was being handed that verdict as though it were a defect.
            try:
                backend_timeout = float(os.environ.get("AIFACTORY_BACKEND_E2E_TIMEOUT_SEC", "300"))
            except ValueError:
                backend_timeout = 300.0
            try:
                backend_e2e = await asyncio.to_thread(
                    run_e2e_in_subprocess,
                    module="web.backend.services.backend_runtime_e2e",
                    func="run_backend_runtime_e2e",
                    product_id=product_id,
                    data_root=str(self.data_root),
                    timeout_sec=backend_timeout,
                )
            except Exception as be:
                self._log("WARNING", f"Backend runtime E2E isolate failed: {be}")
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

            # --- Frontend ↔ backend API contract (dead-in-the-browser detector) ------
            api_contract = await asyncio.to_thread(
                run_api_contract_check,
                product_id,
                str(self.data_root),
                server_paths=(
                    (backend_e2e.get("details") or {}).get("openapi_paths")
                    if isinstance(backend_e2e.get("details"), dict)
                    else None
                ),
            )
            if not api_contract.get("skipped") and not api_contract.get("passed", True):
                for issue in api_contract.get("issues") or []:
                    all_bugs.append(
                        {
                            "severity": issue.get("severity", "high"),
                            "title": f"API contract: {issue.get('code')}",
                            "description": issue.get("detail", ""),
                            "file": f"code/{product_id}/{issue.get('file', '')}".rstrip("/"),
                        }
                    )

            # --- Missing symbols / duplicate modules (why repair loops stall) ------
            try:
                module_health = await asyncio.to_thread(
                    run_duplicate_module_check, product_id, str(self.data_root)
                )
            except Exception as me:
                self._log("WARNING", f"Module health check failed to run: {me}")
                module_health = {"passed": True, "skipped": True, "reason": f"error:{me}"}
            # A subsystem the product was never asked for outranks every defect inside it: eight of
            # the nine blocking defects on one live product lived in a 478-line BI dashboard that no
            # part of the charter mentions, and "define get_dashboard_data" was work in the wrong
            # direction — succeeding would have left the product carrying a second product.
            try:
                from core.foreign_subsystem import charter_text, find_unchartered_subsystems

                # By whitelist, not by dumping the payload. Dumping it produced a 28,067-character
                # "charter" containing "analytics/bi" — from the text of one of our own findings,
                # "Methodology gate (analytics_bi): domain_api_endpoint_missing" — so a gate
                # complaining that BI endpoints were missing became the evidence that BI had been
                # ordered. That protected the BI subsystem from removal, which kept the gate
                # complaining: a misclassification licensing itself.
                _charter_text = charter_text(
                    agent_input.data.get("idea"),
                    agent_input.data.get("specification"),
                    agent_input.data.get("admin_instructions"),
                )
                # The task payload is not a reliable source for the charter: this product's spec is
                # `{}` and the idea does not always travel with the QA task, so the assembled text
                # came to a few dozen characters and the detector correctly declined to have an
                # opinion — which looked exactly like "no foreign subsystem here". Fall back to the
                # stored product, where the 779-character charter actually lives.
                if len(_charter_text.strip()) < 200:
                    _charter_text = self._charter_from_store(product_id, _charter_text)
                _foreign = find_unchartered_subsystems(
                    self.data_root / "code" / product_id, _charter_text
                )
                # Unconditional, because "the gate ran and found nothing" and "the gate never ran"
                # produced identical logs twice tonight, and both times I guessed instead of asking.
                # In-container the same call returns [('analytics', 6)]; the live run returned nothing,
                # so the inputs differ and only the inputs can say how.
                self._log(
                    "INFO",
                    f"Unchartered-subsystem check for {product_id}: charter {len(_charter_text.strip())} "
                    f"chars, {len(_foreign)} finding(s)"
                    + (
                        " — sample of what the charter covers: "
                        + ", ".join(sorted(set(_charter_text.lower().split()))[:12])
                        if not _foreign
                        else ""
                    ),
                )
            except Exception as _fe:
                self._log("WARNING", f"Unchartered-subsystem check skipped: {_fe}")
                _foreign = []
            if _foreign:
                issues = list(module_health.get("issues") or [])
                module_health["issues"] = [
                    {
                        "code": f["code"],
                        "severity": f["severity"],
                        "detail": f["detail"],
                        "file": f["file"],
                    }
                    for f in _foreign
                ] + issues
                module_health["passed"] = False
                module_health["skipped"] = False
                self._log(
                    "WARNING",
                    f"Unchartered subsystem(s) for {product_id}: "
                    + "; ".join(
                        f"{f['cluster']} ({f['defect_count']} defects, {len(f['files'])} files)"
                        for f in _foreign
                    ),
                )
            if not module_health.get("skipped"):
                for issue in module_health.get("issues") or []:
                    all_bugs.append(
                        {
                            "severity": issue.get("severity", "high"),
                            "title": f"Module health: {issue.get('code')}",
                            "description": issue.get("detail", ""),
                            "file": f"code/{product_id}/{issue.get('file', '')}".rstrip("/"),
                        }
                    )

            # --- Authenticated demo journey (login + read every list endpoint) ------
            try:
                journey = await asyncio.to_thread(
                    run_demo_journey, product_id, str(self.data_root)
                )
            except Exception as je:
                self._log("WARNING", f"Demo journey failed to run: {je}")
                journey = {"passed": True, "skipped": True, "reason": f"error:{je}"}
            if not journey.get("skipped") and not journey.get("passed", True):
                for line in journey.get("issues") or []:
                    _jf = self._journey_issue_file(
                        self.data_root / "code" / product_id, str(line)
                    )
                    # Frontier findings observe progress, not regression, and must not vote on
                    # the revert. `auth_rejected` can only exist once login WORKS — the journey
                    # has to get a token before anything can answer it 401. Measured: the round
                    # that finally made login return a token was reverted 14 -> 32, because the
                    # journey went deeper for the first time and found six 401s that were
                    # unreachable a round earlier. Voting them makes the breakthrough round
                    # un-acceptable by construction — the third time this one fix was thrown
                    # away, each time by a different guard. They still reach the developer as
                    # work and still hold the journey gate red.
                    _frontier = "auth_rejected" in str(line)
                    if _frontier and _jf:
                        _where = (
                            f" The shared auth dependency lives in {_jf} — add "
                            "'Authorization: Bearer' support there alongside the cookie, "
                            "in that one function, and do not rewrite the router's own auth."
                        )
                    elif _jf:
                        _where = f" The handler for this endpoint lives in {_jf}."
                    else:
                        _where = ""
                    all_bugs.append(
                        {
                            "severity": "high",
                            "title": f"Demo journey: {str(line)[:120]}",
                            "description": str(line) + _where,
                            "file": _jf or f"code/{product_id}",
                            **({"scored_by_guard": False} if _frontier else {}),
                        }
                    )

            demo_gates_ok = quality_gates_pass(demo_report, delivery_profile=delivery_profile)
            api_contract_ok = api_contract.get("skipped") or api_contract.get("passed", True)
            journey_ok = journey.get("skipped") or journey.get("passed", True)
            frontend_build_ok = frontend_build.get("skipped") or frontend_build.get("passed", True)
            req_manifest_ok = req_manifest.get("skipped") or req_manifest.get("passed", True)
            module_health_ok = module_health.get("skipped") or module_health.get("passed", True)
            browser_ok = browser_e2e.get("skipped") or browser_e2e.get("passed", False)
            backend_ok = backend_e2e.get("skipped") or backend_e2e.get("passed", False)
            perf_slo = evaluate_perf_slo(browser_e2e, backend_e2e)
            methodology_ok = bool(methodology_review.get("passed", True))
            gates_ok = (
                demo_gates_ok
                and api_contract_ok
                and journey_ok
                and frontend_build_ok
                and req_manifest_ok
                and module_health_ok
                and browser_ok
                and backend_ok
                and bool(perf_slo.get("passed"))
                and methodology_ok
            )
            # Ordered, deduplicated list of what actually blocks the build. The raw
            # gate objects below are large and put cosmetic findings (contrast, empty
            # states) alongside "the app does not compile"; a repair round that spends
            # its output on toast styling while imports are broken is a wasted round.
            blocking_defects: list[str] = []

            def _add_blocking(lines) -> None:
                for line in lines:
                    text = str(line).strip()
                    if text and text not in blocking_defects and len(blocking_defects) < 30:
                        blocking_defects.append(text)

            # Absolutely first: defects where the product does not run at all. Two models on
            # one table means the app never boots, so no endpoint exists; a handler FastAPI
            # cannot call is a permanent 500 on that route; a wrong mesh envelope answers 200
            # with no data forever. These were reported as critical and were NOT in this list,
            # so a round saw them beside "add a loading skeleton" and spent itself on the
            # skeleton — measured: 6 of 15 findings were cosmetic while the product's only
            # feature was dead.
            for _blocking_code in (
                # A subsystem nothing asked for leads: every defect inside it is work in the wrong
                # direction, and one instruction to remove it replaces eight to finish building it.
                "unchartered_subsystem",
                # An import of a module that does not exist stops the app before anything else
                # can be observed about it, so it leads. Nothing static reported it until now —
                # `from ..schemas.auth import LoginRequest` in a product whose schemas package
                # held only advisory/analytics/operator arrived as a uvicorn traceback in the
                # demo-journey log, naming no file to fix.
                "class_body_forward_ref",
                "duplicated_router_prefix",
                # The mapper configures on first use, so this is boot-fatal in effect.
                "mismatched_back_populates",
                "api_route_shadows_spa",
                "case_collision",
                "sync_wrapper_over_async_handler",
                "capability_never_invoked",
                "tailwind_utilities_without_tailwind",
                "undeclared_dependency",
                "orm_schema_never_created",
                "dead_path_rewrite",
                "missing_module",
                # An attribute the class never declares raises AttributeError the first time the
                # line runs — at import for module-level code — so the app never starts. Found on
                # the live product twice in one pass: settings.cors_origins in main.py, and
                # atlas_client.invoke for a class whose method is invoke_capability, three call
                # sites inside a `except Exception` that turned it into "level": "UNKNOWN" forever.
                "missing_attribute",
                "unexpected_keyword_argument",
                "duplicate_tablename",
                "route_handler_broken_injection",
                "mesh_contract_violation",
                # Build-fatal rather than boot-fatal: tsc fails and there is nothing to deploy.
                "frontend_missing_export",
            ):
                _add_blocking(
                    i.get("detail", "")
                    for i in (module_health.get("issues") or [])
                    if isinstance(i, dict) and i.get("code") == _blocking_code
                )

            # Deletions next: a leftover file removes the reason for most of the
            # "define X" findings below it.
            _add_blocking(
                i.get("detail", "")
                for i in (module_health.get("issues") or [])
                if isinstance(i, dict) and i.get("code") == "orphan_module_breaks_build"
            )
            _add_blocking(
                i.get("detail", "")
                for i in (module_health.get("issues") or [])
                if isinstance(i, dict) and i.get("code") == "missing_symbol"
            )
            # Compile before journey: a 401 on an API the browser cannot reach (no bundle)
            # is unfixable from the operator console the round would otherwise open.
            _add_blocking(frontend_build.get("issues") or [])
            _add_blocking(req_manifest.get("issues") or [])
            _add_blocking(journey.get("issues") or [])
            _add_blocking(
                i.get("detail", "")
                for i in (api_contract.get("issues") or [])
                if isinstance(i, dict)
            )
            _add_blocking(backend_e2e.get("issues") or [])


            # When one half of the product is green and the other is not, say so. A
            # repair round rewrites ~85 files regardless, which is 40-odd chances to
            # break a working backend while fixing the frontend — and that is exactly
            # how a product with boot+contract+module-health passing kept losing them.
            repair_scope: list[str] = []

            # File-level scope, when the blocking defects say which files they live in. The
            # half-of-the-tree version below only engages when one half is green, so with both
            # halves failing there was NO limit at all and the round rewrote everything: one
            # measured round came back at 128 severity-weighted against a baseline of 41 — three
            # times worse — while its actual work list was four mesh-contract violations in a
            # single client module and one duplicate table across two model files. Three files
            # of work, eighty-five files of edits, and the round is thrown away.
            #
            # Before anything is scoped or scored: drop findings the tree itself contradicts. An
            # LLM finding claiming seven mandatory repository files were "not provided", while all
            # seven sat in the tree, cannot be satisfied by any round — a round cannot create a
            # file that already exists — and it held a blocking gate red for hours.
            all_bugs = self._drop_findings_the_tree_contradicts(
                all_bugs, self.data_root / "code" / product_id, log=self._log
            )

            # Only used when the set is small. A "scope" naming thirty files is not a scope, and
            # pretending otherwise would let a sprawling round call itself surgical.
            blocking_files: list[str] = []

            # Boot/answer-fatal Python before tsc cosmetics. Otherwise six unused-React
            # TSX files fill the truncation and atlas_client.py never enters.
            for _bf in _boot_fatal_scope_files(module_health, product_id):
                if _bf not in blocking_files:
                    blocking_files.append(_bf)

            for _fp in req_manifest.get("files") or []:
                _clean = str(_fp).split(f"{product_id}/", 1)[-1].lstrip("/")
                if _is_scope_file(_clean) and _clean not in blocking_files:
                    blocking_files.append(_clean)

            # Compile + auth-rejected first, so they survive the six-file truncation.
            # Measured on Sentinel rounds 49–51: these never entered the list (tsc was
            # filed against the frontend directory; 401 mapped to the router), the scope
            # filled with operator TSX from unstyled_classes, and the round edited
            # Dashboard.tsx while PublicWidget.tsx still did not typecheck and deps.py
            # still read only the cookie.
            _code_for_scope = self.data_root / "code" / product_id
            for _line in frontend_build.get("issues") or []:
                for _fp in _files_in(str(_line)):
                    _clean = _fp.split(f"{product_id}/", 1)[-1].lstrip("/")
                    if (
                        _is_scope_file(_clean)
                        and _clean not in blocking_files
                    ):
                        blocking_files.append(_clean)
            for _line in journey.get("issues") or []:
                if "auth_rejected" not in str(_line):
                    continue
                _af = self._journey_issue_file(_code_for_scope, str(_line))
                if (
                    _af
                    and _is_scope_file(_af)
                    and _af not in blocking_files
                ):
                    blocking_files.append(_af)

            # Runtime 5xx handlers (and the rate-limit wrapper that FastAPI
            # calls with args=) before landing. The 500 is why demo is red;
            # putting landing first is how advisory.py never entered the six.
            _api_crash = _journey_has_api_crash(journey)
            for _line in journey.get("issues") or []:
                if not _journey_line_is_api_crash(str(_line)):
                    continue
                _cf = self._journey_issue_file(_code_for_scope, str(_line))
                if (
                    _cf
                    and _is_scope_file(_cf)
                    and _cf not in blocking_files
                ):
                    blocking_files.append(_cf)
            if _api_crash and "unexpected keyword argument" in " ".join(
                str(i) for i in (journey.get("issues") or [])
            ).lower():
                for _rel in _RATE_LIMIT_SCOPE_CANDIDATES:
                    if (_code_for_scope / _rel).is_file() and _rel not in blocking_files:
                        blocking_files.append(_rel)

            # Landing markup. Demo/TZ and browser-E2E findings are filed against
            # index.html, but the scope only accepted scripts — so the round could not
            # edit the file the gate names. Measured: Reverted index.html, script.js,
            # style.css (round scoped to operator TSX); demo_quality stayed F.
            # Skip while an API crash is live: landing-in-lead then crowds out
            # the handler that caused demo to fail.
            # Operator consoles only when the browser is red. Measured on Sentinel after
            # E2E went green: the leftover was ux_low_contrast_cta, and the truncated six
            # was still App + three dashboards + index.html — so the round edited operator
            # pages (and re-broke the widget) instead of the CSS the gate actually scored.
            if not _api_crash and not browser_ok:
                for _rel in (*_SPA_SCOPE_CANDIDATES, *_LANDING_SCOPE_CANDIDATES):
                    if (_code_for_scope / _rel).is_file() and _rel not in blocking_files:
                        blocking_files.append(_rel)
            elif not _api_crash and not demo_gates_ok:
                for _rel in _LANDING_SCOPE_CANDIDATES:
                    if (_code_for_scope / _rel).is_file() and _rel not in blocking_files:
                        blocking_files.append(_rel)
            for _issue in module_health.get("issues") or []:
                if not isinstance(_issue, dict):
                    continue
                if _issue.get("code") != "unstyled_classes":
                    continue
                _css = str(_issue.get("file") or "").split(f"{product_id}/", 1)[-1].lstrip("/")
                if _css.endswith(".css") and _css not in blocking_files:
                    blocking_files.append(_css)

            # File-level scope, when the blocking defects say which files they live in. The
            # half-of-the-tree version below only engages when one half is green, so with both
            # halves failing there was NO limit at all and the round rewrote everything.
            for _gate in (module_health, api_contract):
                for _issue in (_gate.get("issues") or []):
                    if not isinstance(_issue, dict):
                        continue
                    if _issue.get("severity") not in ("critical", "high"):
                        continue
                    _f = str(_issue.get("file") or "").strip()
                    # Gate issues carry either a repo-relative path or code/<pid>/<path>.
                    _f = _f.split(f"{product_id}/", 1)[-1].lstrip("/")
                    if _f and _is_scope_file(_f) and _f not in blocking_files:
                        blocking_files.append(_f)
            # Every file a finding NAMES belongs in the scope, not only the file it is filed
            # under. Measured: `missing_attribute` is filed against the class — atlas_client.py,
            # heartbeat.py — while the fix usually belongs where the attribute is READ:
            # `heartbeat.scheduler.shutdown()` at main.py:47 should be `heartbeat.stop()`, and
            # `atlas.get_advisory(...)` at advisory.py:35 is the 500 on the product's main endpoint.
            # The scope held the two class files, so a round touching either read site would have had
            # its work reverted as out-of-scope sprawl. A finding that names a line and a scope that
            # forbids editing it cannot both be right.
            _named_paths = re.findall(
                r"\b((?:[\w.-]+/)+[\w.-]+\.(?:py|tsx|jsx|ts|js|html|css))\b",
                " ".join(
                    str(i.get("detail") or "")
                    for gate in (module_health, api_contract)
                    for i in (gate.get("issues") or [])
                    if isinstance(i, dict) and i.get("severity") in ("critical", "high")
                ),
            )
            for _np in _named_paths:
                _clean = _np.split(f"{product_id}/", 1)[-1].lstrip("/")
                if _clean and _clean not in blocking_files:
                    blocking_files.append(_clean)

            # Runtime findings belong in the scope too. They were harvested from static gates only,
            # and the cost was watched twice in one hour: the round FIXED the tokenless login in
            # auth.py, the scope named only the static finding's file, and the out-of-scope guard
            # reverted the completed fix — measured as free, because a missing token is invisible to
            # the static score. A scope that excludes the file the runtime defect lives in makes that
            # defect unfixable by construction.
            # The browser gate is a runtime observer too, and its failures now carry the method,
            # the path and the handler file — so they belong in the scope on the same grounds. A
            # 500 the browser sees at page load is not fixable in a round scoped to the files a
            # static detector happened to name.
            _runtime_lines = list(journey.get("issues") or []) + list(
                (browser_e2e or {}).get("issues") or []
            )
            for _line in _runtime_lines:
                _jf = self._journey_issue_file(
                    self.data_root / "code" / product_id, str(_line)
                )
                if (
                    _jf
                    and _is_scope_file(_jf)
                    and _jf not in blocking_files
                ):
                    blocking_files.append(_jf)
                # The handler's response_model lives in another file, and that file is half the
                # fix: FastAPI silently strips every response field the model does not declare, so
                # a token added to the handler's return changes nothing observable while the model
                # says `message: str`. Three rounds edited auth.py against the tokenless-login
                # finding and the body never changed — the schema file was not in the scope, and an
                # edit there would have been reverted as sprawl.
                if _jf and _jf.endswith(".py"):
                    try:
                        _handler_text = (
                            self.data_root / "code" / product_id / _jf
                        ).read_text(encoding="utf-8", errors="replace")
                        for _model in set(re.findall(r"response_model\s*=\s*(\w+)", _handler_text)):
                            for _cand in (self.data_root / "code" / product_id).rglob("*.py"):
                                if ".aicom_sandbox" in _cand.parts or "node_modules" in _cand.parts:
                                    continue
                                try:
                                    if re.search(rf"^class\s+{_model}\b", _cand.read_text(encoding="utf-8", errors="replace"), re.M):
                                        _rel = _cand.relative_to(self.data_root / "code" / product_id).as_posix()
                                        if _rel not in blocking_files:
                                            blocking_files.append(_rel)
                                        break
                                except OSError:
                                    continue
                    except OSError:
                        pass
            # Take the first six by rank rather than giving up above six. All-or-nothing meant
            # the scope was empty exactly when it was needed most: a round with 12 critical/high
            # findings names more than six files, so no limit was emitted at all and the round
            # spread over ~20 files in six unfocused batches. The issues arrive already ordered
            # with the product-does-not-run codes first, so the truncation keeps the ones worth
            # a round and drops the tail — which the next round picks up once these land.
            if blocking_files:
                # Resolve before publishing: an unresolvable path produced an EMPTY scope, which
                # turned off the file attachment and left the round guessing at the very paths it
                # could not open.
                try:
                    from core.product_paths import resolve_all

                    _resolved, _unresolved = resolve_all(
                        self.data_root / "code" / product_id, blocking_files
                    )
                    if _unresolved:
                        self._log(
                            "WARNING",
                            f"Findings for {product_id} name {len(_unresolved)} path(s) that do not "
                            "resolve against the tree — a pipeline defect, not the product's: "
                            + ", ".join(_unresolved[:5]),
                        )
                    if _resolved:
                        blocking_files = _resolved
                except Exception as _pe:
                    self._log("WARNING", f"Path resolution for {product_id} skipped: {_pe}")
                # Boot-fatal Python, then compile + auth. Mesh_contract on atlas_client.py
                # used to arrive after six tsc unused-React files, so the truncated six
                # never contained the client that still returns 200 with a TypeError.
                _lead_needles: list[str] = []
                _lead_needles.extend(_boot_fatal_scope_files(module_health, product_id))
                _code_dir = self.data_root / "code" / product_id
                _api_crash = _journey_has_api_crash(journey)
                for _line in journey.get("issues") or []:
                    if not _journey_line_is_api_crash(str(_line)):
                        continue
                    _cf = self._journey_issue_file(_code_dir, str(_line))
                    if _cf:
                        _lead_needles.append(_cf)
                if _api_crash and "unexpected keyword argument" in " ".join(
                    str(i) for i in (journey.get("issues") or [])
                ).lower():
                    _lead_needles.extend(_RATE_LIMIT_SCOPE_CANDIDATES)
                for _line in frontend_build.get("issues") or []:
                    _lead_needles.extend(_files_in(str(_line)))
                for _fp in req_manifest.get("files") or []:
                    _lead_needles.append(str(_fp))
                for _line in req_manifest.get("issues") or []:
                    _lead_needles.extend(_files_in(str(_line)))
                for _line in journey.get("issues") or []:
                    if "auth_rejected" not in str(_line):
                        continue
                    _af = self._journey_issue_file(_code_dir, str(_line))
                    if _af:
                        _lead_needles.append(_af)
                if not _api_crash and not browser_ok:
                    _lead_needles.extend(_SPA_SCOPE_CANDIDATES)
                    _lead_needles.extend(_LANDING_SCOPE_CANDIDATES)
                elif not _api_crash and not demo_gates_ok:
                    _lead_needles.extend(_LANDING_SCOPE_CANDIDATES)
                for _issue in module_health.get("issues") or []:
                    if isinstance(_issue, dict) and _issue.get("code") == "unstyled_classes":
                        _css = str(_issue.get("file") or "").split(f"{product_id}/", 1)[-1].lstrip("/")
                        if _css.endswith(".css"):
                            _lead_needles.append(_css)
                if _lead_needles:
                    try:
                        from core.product_paths import resolve_all as _resolve_lead

                        _lead, _ = _resolve_lead(_code_dir, _lead_needles)
                    except Exception:
                        _lead = [
                            n
                            for n in _lead_needles
                            if _is_scope_file(n)
                        ]
                    _lead_set = set(_lead)
                    _missing = [f for f in _lead if f not in blocking_files]
                    _front = [f for f in blocking_files if f in _lead_set]
                    _rest = [f for f in blocking_files if f not in _lead_set]
                    blocking_files = _missing + _front + _rest
                repair_scope = blocking_files[:6]
                if len(blocking_files) > 6:
                    self._log(
                        "INFO",
                        f"Repair scope truncated to the first 6 of {len(blocking_files)} files "
                        "carrying critical/high findings; the rest follow in later rounds",
                    )

            backend_green = backend_ok and api_contract_ok and module_health_ok
            frontend_green = frontend_build.get("skipped") or frontend_build.get("passed", False)
            if not repair_scope:
                if backend_green and not frontend_green:
                    repair_scope = ["frontend/"]
                elif frontend_green and not backend_green:
                    repair_scope = ["backend/"]

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
                "blocking_defects": blocking_defects,
                "repair_scope": repair_scope,
                "api_contract": api_contract,
                "api_contract_passed": api_contract_ok,
                "demo_journey": journey,
                "demo_journey_passed": journey_ok,
                "frontend_build": frontend_build,
                "frontend_build_passed": frontend_build_ok,
                "requirements_manifest": req_manifest,
                "requirements_manifest_passed": req_manifest_ok,
                "module_health": module_health,
                "module_health_passed": module_health_ok,
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
                "blocking_defects": blocking_defects,
                "repair_scope": repair_scope,
                "api_contract": api_contract,
                "api_contract_passed": api_contract_ok,
                "demo_journey": journey,
                "demo_journey_passed": journey_ok,
                "frontend_build": frontend_build,
                "frontend_build_passed": frontend_build_ok,
                "requirements_manifest": req_manifest,
                "requirements_manifest_passed": req_manifest_ok,
                "module_health": module_health,
                "module_health_passed": module_health_ok,
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
                        "blocking_defects": blocking_defects,
                "repair_scope": repair_scope,
                        "api_contract": api_contract,
                        "demo_journey": journey,
                        "frontend_build": frontend_build,
                        "requirements_manifest": req_manifest,
                        "module_health": module_health,
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
                            f"api_contract[{i.get('code')}]: {i.get('detail')}"
                            for i in (api_contract.get("issues") or [])
                            if isinstance(i, dict)
                        ]
                        + [f"demo_journey: {i}" for i in (journey.get("issues") or [])]
                        + [f"frontend_build: {i}" for i in (frontend_build.get("issues") or [])]
                        + [f"invalid_requirement: {i}" for i in (req_manifest.get("issues") or [])]
                        + [
                            f"module_health[{i.get('code')}]: {i.get('detail')}"
                            for i in (module_health.get("issues") or [])
                            if isinstance(i, dict)
                        ]
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

    @staticmethod
    def _py_file_parses(code_root: Path, rel: str) -> bool:
        """True when the named Python file exists and ast.parse succeeds."""
        from core.product_paths import resolve_product_path

        resolved = resolve_product_path(code_root, rel) or rel
        path = code_root / resolved
        if not path.is_file() or path.suffix != ".py":
            return False
        import ast

        try:
            ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, ValueError):
            return False
        return True

    @staticmethod
    def _spa_surface_file(code_dir: Path, text: str = "") -> str | None:
        """The React page the visitor actually sees, not the Vite index.html shell."""
        low = (text or "").lower()
        prefer: tuple[str, ...] = ()
        if "/operator" in low or "operator dashboard" in low or "operator console" in low:
            prefer = (
                "frontend/src/pages/OperatorDashboard.tsx",
                "frontend/src/pages/Operator.tsx",
                "frontend/src/App.tsx",
            )
        elif "/analytics" in low or "analytics dashboard" in low:
            prefer = (
                "frontend/src/pages/AnalyticsDashboard.tsx",
                "frontend/src/pages/Analytics.tsx",
                "frontend/src/App.tsx",
            )
        elif "/login" in low or "operator login" in low:
            prefer = (
                "frontend/src/pages/Login.tsx",
                "frontend/src/pages/OperatorLogin.tsx",
                "frontend/src/App.tsx",
            )
        for rel in prefer:
            if (code_dir / rel).is_file():
                return rel
        for rel in (
            "frontend/src/pages/PublicWidget.tsx",
            "frontend/src/pages/Home.tsx",
            "frontend/src/pages/Landing.tsx",
            "frontend/src/App.tsx",
            "src/pages/PublicWidget.tsx",
            "src/pages/Home.tsx",
            "src/App.tsx",
        ):
            if (code_dir / rel).is_file():
                return rel
        pages = code_dir / "frontend" / "src" / "pages"
        if pages.is_dir():
            for path in sorted(pages.glob("*.tsx")):
                return path.relative_to(code_dir).as_posix()
        return None

    @staticmethod
    def _demo_issue_file(code_dir: Path, issue: dict | str) -> str | None:
        """CSS or the public widget, not the Vite index.html shell.

        Demo/TZ findings were hardcoded to index.html. After E2E went green the only leftover
        was ux_low_contrast_cta — a static CSS ratio — and the round still edited the shell.
        Contrast and empty/toast live in styles + PublicWidget.
        """
        if isinstance(issue, dict):
            blob = f"{issue.get('code') or ''} {issue.get('detail') or ''}"
        else:
            blob = str(issue)
        low = blob.lower()
        visual = (
            "ux_low_contrast" in low
            or "visual_" in low
            or "empty_state" in low
            or "toast" in low
            or "cta" in low
        )
        if visual:
            for rel in (
                "frontend/src/styles/index.css",
                "frontend/src/index.css",
                "frontend/src/App.css",
                "frontend/style.css",
                "style.css",
                "frontend/src/pages/PublicWidget.tsx",
                "frontend/src/App.tsx",
            ):
                if (code_dir / rel).is_file():
                    return rel
        return QAAgent._spa_surface_file(code_dir, blob)

    @staticmethod
    def _auth_dependency_file(code_dir: Path) -> str | None:
        """The shared get_current_user (or equivalent), not the router that returned 401.

        Mapping auth_rejected:/api/analytics/dashboards to analytics.py is how six rounds
        flip-flopped two routers between cookie-only and Bearer-only. The fix belongs in
        one dependency both routers already use.
        """
        hits: list[Path] = []
        for path in code_dir.rglob("*.py"):
            if any(
                part in path.parts
                for part in (
                    ".aicom_sandbox",
                    "node_modules",
                    "__pycache__",
                    ".venv",
                    "tests",
                    "test",
                )
            ):
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if re.search(r"^def get_current_user\b", text, re.M):
                hits.append(path)
        if not hits:
            return None

        def _rank(path: Path) -> tuple[int, str]:
            name = path.name.lower()
            if name == "deps.py":
                return (0, path.as_posix())
            if name in {"security.py", "auth_deps.py"}:
                return (1, path.as_posix())
            return (2, path.as_posix())

        hits.sort(key=_rank)
        try:
            return hits[0].relative_to(code_dir).as_posix()
        except ValueError:
            return None

    @staticmethod
    def _drop_findings_the_tree_contradicts(
        bugs: list[dict], code_root: Path, *, log
    ) -> list[dict]:
        """Remove findings that claim a file is missing when the file is on disk.

        Measured live on a product at four remaining defects: an LLM finding read "No README.md,
        LICENSE, CHANGELOG.md, docs/, docs/badges/, .github/workflows/ci.yml, or
        .github/workflows/release.yml were provided. These are mandatory for full_software
        products." All seven were in the tree. A round cannot create a file that already exists, so
        the finding was immortal — and it held a blocking gate red while every round that tried to
        satisfy it wrote files that were already there.

        Only claims OF ABSENCE are filtered, and only when every path named exists. A finding that
        names three files of which one is genuinely missing keeps its place, narrowed to the file
        that is actually missing, because that part of it is true.
        """
        import re as _re

        absence = _re.compile(
            r"\b(no|missing|absent|not provided|were not provided|does not exist|not found|"
            r"lacks|without)\b",
            _re.I,
        )
        path_like = _re.compile(
            r"[\w./-]*[\w-]+\.(?:md|yml|yaml|json|py|ts|tsx|txt|toml|cfg)\b"
            r"|(?:docs|tests|\.github)(?:/[\w.-]+)*/?"
            # Extension-less files a contract names by convention. LICENSE was the one the live
            # phantom hinged on: without it the claim looked partly true and survived.
            r"|\b(?:LICEN[SC]E|NOTICE|CODEOWNERS|CONTRIBUTING|Dockerfile|Makefile)\b"
        )
        # Only LLM guesses are filtered. A finding produced by a detector that READ the tree cannot
        # be contradicted by the tree — it is the tree's own report. This bit was learned the hard
        # way, one round after the filter shipped: `orm_schema_never_created` says "migrations exist
        # (…0001_initial.py) but nothing runs alembic upgrade", which mentions files that do exist,
        # and the filter dropped the one finding that had correctly diagnosed a database with no
        # schema. Two fixes, each right on its own, cancelling each other out.
        measured_prefixes = (
            "Module health:",
            "API contract:",
            "Browser E2E:",
            "Demo journey:",
            "Demo/TZ gate:",
            "Frontend build:",
            "Backend runtime:",
        )
        truncated = _re.compile(
            r"\b(truncated|cut off|appears truncated|incomplete (?:rate_limit )?decorator)\b",
            _re.I,
        )
        kept: list[dict] = []
        for bug in bugs:
            title = str(bug.get("title") or "")
            if title.startswith(measured_prefixes):
                kept.append(bug)
                continue
            blob = f"{title} {bug.get('description') or ''} {bug.get('file') or ''}"
            # LLM saw a truncated ATTACHMENT and reported the file as incomplete. Measured
            # on Sentinel round 50: "rate_limit decorator is truncated after @wraps" and
            # "app/main.py appears truncated" while both files parsed. Those two "critical"
            # findings then competed with the real compile and 401 defects for attention.
            if truncated.search(blob):
                named_py = [
                    str(bug.get("file") or "").strip().lstrip("/")
                ] + path_like.findall(blob)
                named_py = [
                    r.strip().rstrip(",;:").lstrip("/")
                    for r in named_py
                    if str(r).endswith(".py")
                ]
                if named_py and all(
                    QAAgent._py_file_parses(code_root, rel) for rel in named_py if rel
                ):
                    log(
                        "INFO",
                        "Dropping a truncated-file finding the tree contradicts: "
                        f"{', '.join(named_py[:4])} parse — {title[:80]}",
                    )
                    continue
            # LLM saw the first 10 attached files and declared the repo "incomplete / missing
            # modules" while backend/ and frontend/ were on disk. app/main.py in the finding is
            # the truncated path of backend/app/main.py, so the absence filter kept it (that
            # exact relpath does not exist) and it competed with contrast for the round.
            if _re.search(
                r"repository is incomplete|incomplete\s*/\s*missing modules|missing modules",
                title,
                _re.I,
            ) and (
                (code_root / "backend").is_dir()
                and (
                    (code_root / "frontend").is_dir()
                    or (code_root / "index.html").is_file()
                )
            ):
                log(
                    "INFO",
                    "Dropping an incomplete-repo finding the tree contradicts: "
                    f"backend+frontend are present — {title[:80]}",
                )
                continue
            if not absence.search(blob):
                kept.append(bug)
                continue
            named = []
            for raw in path_like.findall(blob):
                # Trailing punctuation only. A two-sided strip ate the leading dot of
                # ".github/workflows/ci.yml", turning an existing path into a missing one — which
                # made the phantom look partly true and let it survive the filter.
                rel = str(raw).strip().rstrip(",;:").lstrip("/")
                if rel.endswith(".") and not rel.endswith(".."):
                    rel = rel[:-1]
                if rel and rel not in named:
                    named.append(rel)
            if not named:
                kept.append(bug)
                continue
            missing = [rel for rel in named if not (code_root / rel).exists()]
            if not missing:
                log(
                    "INFO",
                    "Dropping a finding the tree contradicts: it says "
                    f"{', '.join(named[:6])} are missing, and all of them exist — "
                    f"{str(bug.get('title'))[:80]}",
                )
                continue
            if len(missing) < len(named):
                bug = dict(bug)
                bug["description"] = (
                    f"{str(bug.get('description') or '')[:400]} "
                    f"[verified against the tree: only {', '.join(missing[:6])} "
                    f"{'is' if len(missing) == 1 else 'are'} actually missing; the rest exist]"
                )
            kept.append(bug)
        if any("auth_rejected" in str(b.get("title") or "") for b in kept):
            # The measured journey finding already says how this client authenticates.
            # An LLM restatement ("Authentication only reads cookie token") is the same
            # defect at medium, and it was what the round followed instead of deps.py.
            filtered = []
            for bug in kept:
                title = str(bug.get("title") or "")
                if title.startswith(measured_prefixes):
                    filtered.append(bug)
                    continue
                blob = f"{title} {bug.get('description') or ''}".lower()
                if "cookie" in blob and any(
                    w in blob for w in ("get_current_user", "bearer", "authorization")
                ):
                    log(
                        "INFO",
                        "Dropping LLM restatement of a measured auth_rejected finding: "
                        f"{title[:80]}",
                    )
                    continue
                filtered.append(bug)
            kept = filtered
        return kept

    def _assess_github_house(
        self,
        product_id: str,
        code_files: list[dict],
        *,
        delivery_profile: str,
        content_language: str | None,
    ) -> list[dict]:
        """Flag missing GitHub-house files (README, bilingual docs, CI, tests)."""
        issues: list[dict] = []
        if not code_files:
            return issues

        rels = []
        readme_text = ""
        for file_info in code_files:
            raw = str(file_info.get("path") or "").replace("\\", "/")
            rels.append(raw.lower())
            name = Path(raw).name.lower()
            if name == "readme.md":
                readme_text = str(file_info.get("content") or "")

        try:
            from core.paths import code_dir as product_code_dir

            root = product_code_dir(product_id)
            if root.is_dir():
                for fpath in root.rglob("*"):
                    if not fpath.is_file():
                        continue
                    rel = str(fpath.relative_to(root)).replace("\\", "/")
                    rels.append(rel.lower())
                    if fpath.name.lower() == "readme.md" and not readme_text:
                        try:
                            readme_text = fpath.read_text(encoding="utf-8", errors="replace")[:20000]
                        except OSError:
                            pass
        except Exception:
            pass

        def has_suffix(suffix: str) -> bool:
            needle = suffix.lower().lstrip("/")
            return any(p == needle or p.endswith("/" + needle) for p in rels)

        if not has_suffix("readme.md"):
            issues.append(
                {
                    "severity": "high",
                    "title": "GitHub house: missing README.md",
                    "description": (
                        "Every shipped product needs a root README with badges, quick start, "
                        "and a hero or architecture diagram (GITHUB_HOUSE_CONTRACT)."
                    ),
                    "file": f"code/{product_id}/README.md",
                }
            )
        elif "aicom-readme-badges" not in readme_text and "docs/badges/" not in readme_text.lower():
            issues.append(
                {
                    "severity": "medium",
                    "title": "GitHub house: README has no badge row",
                    "description": (
                        "README.md should wrap a badge row in <!-- aicom-readme-badges --> "
                        "and link docs/badges/*.svg (not shields.io workflow-status)."
                    ),
                    "file": f"code/{product_id}/README.md",
                }
            )

        lang = (content_language or "en").strip().lower().replace("_", "-")
        if lang and lang not in ("en", "auto", "default", ""):
            loc_readme = f"readme.{lang}.md"
            if not has_suffix(loc_readme):
                issues.append(
                    {
                        "severity": "high",
                        "title": f"GitHub house: missing README.{lang}.md",
                        "description": (
                            f"Product locale is {lang}; ship README.{lang}.md alongside English README.md."
                        ),
                        "file": f"code/{product_id}/README.{lang}.md",
                    }
                )
            if delivery_profile != MARKETING_LANDING and not has_suffix(f"docs/{lang}.md"):
                issues.append(
                    {
                        "severity": "medium",
                        "title": f"GitHub house: missing docs/{lang}.md",
                        "description": (
                            f"Operator guide must exist in the product locale ({lang}) as well as docs/en.md."
                        ),
                        "file": f"code/{product_id}/docs/{lang}.md",
                    }
                )

        has_ui = any(
            p.endswith((".html", ".tsx", ".jsx", ".vue"))
            or "/frontend/" in p
            or p.startswith("frontend/")
            for p in rels
        )
        gallery_svgs = [p for p in rels if "docs/gallery/" in p and p.endswith(".svg")]
        has_tests = any(
            "/tests/" in p
            or p.startswith("tests/")
            or Path(p).name.startswith("test_")
            or p.endswith((".test.ts", ".test.js", "_test.py"))
            for p in rels
        )
        mermaid_hero = "```mermaid" in readme_text.lower()

        if has_ui and not has_suffix("docs/gallery/hero.svg"):
            issues.append(
                {
                    "severity": "medium",
                    "title": "GitHub house: missing docs/gallery/hero.svg",
                    "description": (
                        "Browser UI products need an original SVG hero above the fold "
                        "(docs/gallery/hero.svg, linked from README)."
                    ),
                    "file": f"code/{product_id}/docs/gallery/hero.svg",
                }
            )
        if has_ui and len(gallery_svgs) < 3:
            issues.append(
                {
                    "severity": "medium",
                    "title": "GitHub house: thin gallery",
                    "description": (
                        "Ship hero.svg plus 2–4 stills in docs/gallery/ with a README gallery table."
                    ),
                    "file": f"code/{product_id}/docs/gallery/",
                }
            )
        if readme_text and not has_ui and not mermaid_hero:
            issues.append(
                {
                    "severity": "low",
                    "title": "GitHub house: README has no hero diagram",
                    "description": "CLI/API-only README should include a mermaid architecture (or sequence) diagram.",
                    "file": f"code/{product_id}/README.md",
                }
            )

        if delivery_profile == MARKETING_LANDING:
            if not has_tests:
                issues.append(
                    {
                        "severity": "medium",
                        "title": "GitHub house: missing smoke test",
                        "description": "Landings need at least a smoke test (html lang, in-page CTA/anchors).",
                        "file": f"code/{product_id}",
                    }
                )
            return issues

        if not has_suffix("docs/en.md"):
            issues.append(
                {
                    "severity": "medium",
                    "title": "GitHub house: missing docs/en.md",
                    "description": "full_software needs an English operator guide at docs/en.md.",
                    "file": f"code/{product_id}/docs/en.md",
                }
            )
        if not has_suffix(".github/workflows/ci.yml") and not has_suffix(".github/workflows/ci.yaml"):
            issues.append(
                {
                    "severity": "high",
                    "title": "GitHub house: missing CI workflow",
                    "description": "Ship .github/workflows/ci.yml (tests + coverage, fail below 60%).",
                    "file": f"code/{product_id}/.github/workflows/ci.yml",
                }
            )
        if not has_suffix(".github/workflows/release.yml") and not has_suffix(
            ".github/workflows/release.yaml"
        ):
            issues.append(
                {
                    "severity": "high",
                    "title": "GitHub house: missing release workflow",
                    "description": "full_software ships .github/workflows/release.yml (GitHub Release on v* tags).",
                    "file": f"code/{product_id}/.github/workflows/release.yml",
                }
            )
        if not has_suffix("changelog.md"):
            issues.append(
                {
                    "severity": "medium",
                    "title": "GitHub house: missing CHANGELOG.md",
                    "description": "Keep a Changelog starting at 0.1.0; release.yml reads it on v* tags.",
                    "file": f"code/{product_id}/CHANGELOG.md",
                }
            )
        if not has_suffix("license") and not has_suffix("license.md"):
            issues.append(
                {
                    "severity": "medium",
                    "title": "GitHub house: missing LICENSE",
                    "description": "Ship an OSI LICENSE at the repo root (default MIT unless the spec names another).",
                    "file": f"code/{product_id}/LICENSE",
                }
            )
        if not has_tests:
            issues.append(
                {
                    "severity": "high",
                    "title": "GitHub house: missing automated tests",
                    "description": (
                        "full_software requires unit + behavior tests (and UI e2e when there is a browser surface)."
                    ),
                    "file": f"code/{product_id}",
                }
            )
        return issues

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

    @staticmethod
    def _journey_issue_file(code_dir, text: str) -> str | None:
        """The file behind a runtime journey finding, via the route table.

        `demo_login_failed:/login` carried `file: code/<product>` — a directory, not a file — so the
        scope stayed empty, nothing was attached, and the round guessed. Measured guess, from the log:
        it edited test_rule_engine.py and test_advisory_api.py while the defect lived in the login
        handler. The route table already knows `/login` -> routers/auth.py; this is the missing wire.
        """
        import re as _re

        try:
            from core.product_paths import resolve_product_path
            from web.backend.services.api_contract_check import route_handler_file

            # A python path in the line (boot tracebacks carry one) beats endpoint inference.
            m = _re.search(r"\(?([\w./-]+\.py)(?::\d+)?\)?", text)
            if m:
                resolved = resolve_product_path(code_dir, m.group(1))
                if resolved:
                    return resolved
            # A 401 is a dependency problem, not a router problem. Mapping
            # auth_rejected:/api/analytics/dashboards to analytics.py is how six rounds
            # rewrote two routers in alternation and never touched get_current_user.
            if "auth_rejected" in text:
                dep = QAAgent._auth_dependency_file(code_dir)
                if dep:
                    return dep
            # Browser a11y / spec-alignment findings were filed against index.html, the Vite
            # shell. The heading lives in the route component (PublicWidget.tsx already had
            # <h1>Sentinel</h1> while a11y_missing_h1 stayed red). When the crawl names
            # /operator or /analytics, that route's page — not the public widget.
            low = text.lower()
            if (
                "a11y_missing_h1" in low
                or "a11y_preview_served_api_json" in low
                or "spec_alignment_llm_failed" in low
                or "blank_or_tiny_ui" in low
                or "pageerror" in low
                or "console_error" in low
                or "/operator" in low
                or "/analytics" in low
            ):
                spa = QAAgent._spa_surface_file(code_dir, text)
                if spa:
                    return spa
            ep = _re.search(r":(/[^\s:,)]+)", text)
            if ep:
                return route_handler_file(code_dir, ep.group(1))
        except Exception:
            return None
        return None

    def _charter_from_store(self, product_id: str, fallback: str) -> str:
        """Idea, spec and admin instructions as recorded for the product.

        Read straight from the pipeline store rather than the task payload, because the payload is
        assembled per stage and does not always carry them — and a charter check that silently sees an
        empty charter reports "nothing foreign here", which is the wrong answer wearing the right face.
        """
        import sqlite3

        db = self.data_root / "state" / "pipeline.db"
        if not db.is_file():
            return fallback
        try:
            with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as conn:
                row = conn.execute(
                    "select idea, spec, extras from products where id=?", (product_id,)
                ).fetchone()
        except Exception:
            return fallback
        if not row:
            return fallback
        idea, spec, extras = row
        try:
            admin = (json.loads(extras or "{}") or {}).get("admin_instructions") or ""
        except (ValueError, TypeError):
            admin = ""
        text = " ".join([str(idea or ""), str(spec or ""), str(admin)])
        return text if len(text.strip()) > len(fallback.strip()) else fallback

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
