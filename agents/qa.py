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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agents.product_profile import infer_delivery_profile
from agents.prompt_utils import prompt_json
from agents.prompts.load_prompt import load_prompt
from core.child_env import scrub_child_env
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
from core.json_state import write_text_atomic
from .qa_checks.tree import TreeReadingMixin
from .qa_checks.findings import FindingsMixin
from .qa_checks.relay import RelayChecksMixin
from .qa_checks.github_house import GithubHouseMixin
from .qa_checks.realism import RealismMixin
from .qa_checks.tooling import ToolingMixin
from .qa_checks.scoring import ScoringMixin
from .qa_checks.helpers import (  # noqa: F401 - re-exported
    logger,
    _qa_extract_json_object,
    QA_SYSTEM_PROMPT,
    _env_float,
)


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
    "mesh_participant_violation",
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



@dataclass
class _QARun:
    """One QA run: what it was given, what each gate reported, and the findings so far.

    `QAAgent.execute` creates it and hands it to each phase in turn; a phase reads the
    reports it needs and records its own.
    """

    agent_input: AgentInput
    start_time: float
    product_id: str
    is_bug_fix: bool
    delivery_profile: str
    landing_methodology_skip: bool
    code_files: Any = None
    static_analysis_results: Any = None
    test_results: Any = None
    import_errors: Any = None
    llm_review: Any = None
    all_bugs: list = field(default_factory=list)
    all_security: list = field(default_factory=list)
    all_performance: list = field(default_factory=list)
    acceptance_report: Any = None
    traceability_matrix: Any = None
    acceptance_pack: Any = None
    maintainability_review: Any = None
    methodology_review: Any = None
    inner_spec: Any = None
    frontend_build: Any = None
    req_manifest: Any = None
    demo_report: Any = None
    browser_e2e: Any = None
    backend_e2e: Any = None
    api_contract: Any = None
    module_health: Any = None
    journey: Any = None
    # The verdicts, decided once every gate has reported (`_qa_gate_verdicts`).
    demo_gates_ok: Any = None
    api_contract_ok: Any = None
    journey_ok: Any = None
    frontend_build_ok: Any = None
    req_manifest_ok: Any = None
    module_health_ok: Any = None
    browser_ok: Any = None
    backend_ok: Any = None
    perf_slo: Any = None
    methodology_ok: Any = None
    gates_ok: Any = None
    blocking_defects: list = field(default_factory=list)
    repair_scope: list = field(default_factory=list)
    release_score: Any = None
    overall_verdict: str = ""


class QAAgent(
    TreeReadingMixin, FindingsMixin, RelayChecksMixin, GithubHouseMixin, RealismMixin,
    ToolingMixin, ScoringMixin, BaseAgent,
):
    """QA Agent - tests code and reports bugs."""

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

        run = _QARun(
            agent_input=agent_input,
            start_time=start_time,
            product_id=product_id,
            is_bug_fix=is_bug_fix,
            delivery_profile=delivery_profile,
            landing_methodology_skip=landing_methodology_skip,
        )

        try:
            # Mechanical gate fixes before discovery/assessment (loopback URLs, anchors, static stubs).
            self._qa_autofix(product_id)

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

            run.code_files, run.static_analysis_results = code_files, static_analysis_results
            run.test_results, run.import_errors, run.llm_review = test_results, import_errors, llm_review

            # Step 6: Compile all results
            self._qa_static_findings(run)
            self._qa_heuristic_scans(run)
            self._qa_acceptance_and_methodology(run)
            self._qa_merge_llm_review(run)
            await self._qa_build_checks(run)
            self._qa_demo_quality(run)
            await self._qa_browser_e2e(run)
            await self._qa_backend_e2e(run)
            await self._qa_api_contract(run)
            await self._qa_module_health(run)
            await self._qa_demo_journey(run)
            self._qa_gate_verdicts(run)
            self._qa_blocking_defects(run)

            # Before anything is scoped or scored: drop findings the tree itself contradicts. An
            # LLM finding claiming seven mandatory repository files were "not provided", while all
            # seven sat in the tree, cannot be satisfied by any round — a round cannot create a
            # file that already exists — and it held a blocking gate red for hours.
            run.all_bugs = self._drop_findings_the_tree_contradicts(
                run.all_bugs, self.data_root / "code" / product_id, log=self._log
            )
            run.repair_scope = self._qa_repair_scope(run)
            self._qa_verdict(run)
            qa_result = self._qa_report(run)
            return self._qa_output(run, qa_result)

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

    def _qa_autofix(self, product_id: str) -> None:
        """Mechanical gate fixes, applied to the tree before anything is assessed."""
        try:
            from core.paths import code_dir as product_code_dir
            from web.backend.services.visual_gate_autofix import apply_visual_gate_autofix
            from web.backend.services.vercel_fullstack_adapter import apply_live_auth_autofix

            code_root = product_code_dir(product_id)
            apply_visual_gate_autofix(code_root)
            # Factory-owned: login/session salt and UUID PK coerce land in data/code.
            apply_live_auth_autofix(code_root)
            from web.backend.services.github_house_assets import apply_github_house_asset_autofix

            apply_github_house_asset_autofix(code_root)
        except Exception as _autofix_exc:
            log_suppressed(logger, "visual_gate_autofix before QA", exc_info=_autofix_exc)

    def _qa_static_findings(self, run: _QARun) -> None:
        """Static analysis, failing tests and import errors, as findings."""
        static_analysis_results, test_results, import_errors = (
            run.static_analysis_results, run.test_results, run.import_errors)
        all_bugs, all_security = run.all_bugs, run.all_security

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

    def _qa_heuristic_scans(self, run: _QARun) -> None:
        """The tree scans: insecure auth, realism, session salt, UUID keys, relay, GitHub house."""
        agent_input, product_id, code_files = run.agent_input, run.product_id, run.code_files
        all_bugs, all_security = run.all_bugs, run.all_security

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
            salt_issues = self._assess_session_token_salt(product_id, code_files)
            all_bugs.extend(salt_issues)
        except Exception as e:
            self._log("WARNING", f"Session token salt scan failed: {e}")

        try:
            uuid_pk_issues = self._assess_uuid_pk_lookup(product_id, code_files)
            all_bugs.extend(uuid_pk_issues)
        except Exception as e:
            self._log("WARNING", f"UUID PK lookup scan failed: {e}")

        try:
            pinned_issues = self._assess_relay_pinned_compat(product_id, code_files)
            all_bugs.extend(pinned_issues)
        except Exception as e:
            self._log("WARNING", f"Relay pinned compat scan failed: {e}")

        try:
            from core.github_catalog import github_house_gate_active

            if github_house_gate_active():
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
            else:
                self._log(
                    "INFO",
                    "GitHub-house gate skipped (catalog off or GH_PAT not configured)",
                )
        except Exception as e:
            self._log("WARNING", f"GitHub-house scan failed: {e}")

    def _qa_acceptance_and_methodology(self, run: _QARun) -> None:
        """Acceptance traceability, the domain acceptance pack, maintainability, methodology."""
        agent_input, product_id, code_files = run.agent_input, run.product_id, run.code_files
        landing_methodology_skip, all_bugs = run.landing_methodology_skip, run.all_bugs

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
        run.acceptance_report, run.traceability_matrix = acceptance_report, traceability_matrix
        run.acceptance_pack, run.maintainability_review = acceptance_pack, maintainability_review
        run.methodology_review = methodology_review

    def _qa_merge_llm_review(self, run: _QARun) -> None:
        llm_review = run.llm_review
        all_bugs, all_security, all_performance = run.all_bugs, run.all_security, run.all_performance

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
                    from web.backend.services.qa_llm_finding_filters import (
                        is_test_hygiene_llm_finding,
                    )

                    if is_test_hygiene_llm_finding(_llm_bug):
                        self._log(
                            "INFO",
                            "Dropping LLM test-hygiene finding (does not block ship): "
                            f"{str(_llm_bug.get('title') or '')[:80]}",
                        )
                        continue
                all_bugs.append(_llm_bug)
            all_security.extend(llm_review.get("security_issues", []))
            all_performance.extend(llm_review.get("performance_concerns", []))

    async def _qa_build_checks(self, run: _QARun) -> None:
        """The spec the later gates compare against, then the frontend build and requirements."""
        agent_input, product_id, all_bugs = run.agent_input, run.product_id, run.all_bugs

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
        run.inner_spec, run.frontend_build, run.req_manifest = inner_spec, frontend_build, req_manifest

    def _qa_demo_quality(self, run: _QARun) -> None:
        product_id, inner_spec, all_bugs = run.product_id, run.inner_spec, run.all_bugs

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
        run.demo_report = demo_report

    async def _qa_browser_e2e(self, run: _QARun) -> None:
        product_id, inner_spec, all_bugs = run.product_id, run.inner_spec, run.all_bugs

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
        run.browser_e2e = browser_e2e

    async def _qa_backend_e2e(self, run: _QARun) -> None:
        product_id, all_bugs = run.product_id, run.all_bugs

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
        run.backend_e2e = backend_e2e

    async def _qa_api_contract(self, run: _QARun) -> None:
        product_id, backend_e2e, all_bugs = run.product_id, run.backend_e2e, run.all_bugs

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
        run.api_contract = api_contract

    async def _qa_module_health(self, run: _QARun) -> None:
        """Missing symbols and duplicate modules, then what the charter rules out or pins."""
        agent_input, product_id, all_bugs = run.agent_input, run.product_id, run.all_bugs

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
        # Bound before the try because the charter-contract gates below read it too, and an
        # import failure here must not turn into a NameError three checks later.
        _charter_text = ""
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
        # A charter may pin a dependency the product must import rather than rewrite, and
        # state properties the product must actually satisfy. Both are enforced here rather
        # than trusted to the prose, because every other gate in this stage is structural:
        # they establish that the code is well-formed, and none of them can see that a
        # function is wrong while being well-formed. That is the shape of all three
        # verifiable-output bugs this ecosystem has shipped — platon's vacuous proof (twice),
        # sortes' prover/verifier wire-format split, and a signed bill of materials no buyer
        # can verify. Folded into module_health so the findings travel the same path as the
        # rest; the charter comes from the same store fallback the unchartered-subsystem
        # check uses, for the same reason (the task payload does not reliably carry it).
        for _label, _runner in (
            ("pinned dependency", "pinned_dependency_gate.run_pinned_dependency_check"),
            ("executable property", "property_contract_gate.run_property_contract_check"),
        ):
            try:
                _mod_name, _fn_name = _runner.split(".")
                _mod = __import__(
                    f"web.backend.services.{_mod_name}", fromlist=[_fn_name]
                )
                _contract = await asyncio.to_thread(
                    getattr(_mod, _fn_name),
                    product_id,
                    str(self.data_root),
                    _charter_text,
                )
            except Exception as _ce:
                self._log("WARNING", f"{_label} check failed to run: {_ce}")
                continue
            # Unconditional, for the reason stated above the unchartered-subsystem log:
            # "the gate ran and found nothing" and "the gate never ran" have already
            # produced identical logs in this pipeline, and both times it cost a night.
            self._log(
                "INFO",
                f"{_label} check for {product_id}: "
                f"{_contract.get('declared', 0)} declared, "
                f"{len(_contract.get('issues') or [])} finding(s)"
                + (" (skipped)" if _contract.get("skipped") else ""),
            )
            for _result in _contract.get("results") or []:
                self._log(
                    "INFO",
                    f"  property '{_result.get('name')}' ({_result.get('kind')}): "
                    f"{'ok' if _result.get('ok') else 'FAILED'} — {_result.get('detail', '')}",
                )
            if _contract.get("issues"):
                module_health["issues"] = list(_contract["issues"]) + list(
                    module_health.get("issues") or []
                )
                if not _contract.get("passed", True):
                    module_health["passed"] = False
                module_health["skipped"] = False

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
        run.module_health = module_health

    async def _qa_demo_journey(self, run: _QARun) -> None:
        product_id, all_bugs = run.product_id, run.all_bugs

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
                # A timeout caused by a dependency that does not answer is a CONSEQUENCE,
                # not an independent defect — and scoring it as one is what selected for the
                # wrong fix on Sentinel for 38 rounds. Its advisory endpoint carried two
                # ATLAS addresses (services/aimarket_participant.py:29 pointed at the real
                # service, app/config.py:9 at localhost:8001 where nothing listens), so every
                # round that restored the real call scored 9 -> 12 on one high finding and was
                # reverted; the only edit the gate would accept was a static placeholder,
                # which is the one the developer finally made. Reported as work, no vote —
                # the same treatment auth_rejected already gets, for the same reason.
                _dead_deps = journey.get("external_unreachable") or []
                _frontier = (
                    "auth_rejected" in str(line)
                    or (bool(_dead_deps) and "demo_journey_unreachable" in str(line))
                )
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

        # The dead dependency itself, named once with the file and line to edit. This is the
        # finding the developer can actually act on in one round, and without it the only
        # signal was "your endpoint times out", whose cheapest cure is deleting the call.
        for _dep in (journey.get("external_unreachable") or []):
            all_bugs.append(
                {
                    "severity": "high",
                    "title": (
                        "Config: declared external dependency does not answer — "
                        f"{_dep.get('url')}"
                    ),
                    "description": (
                        f"{_dep.get('source')} declares {_dep.get('url')} and nothing answers "
                        f"there from the sandbox ({_dep.get('detail')}). Every endpoint that "
                        "calls it will time out, and those timeouts are reported separately "
                        "and do NOT count against the round. Fix the address — do not remove "
                        "the call, and do not replace the response with a placeholder: check "
                        "the other places in this product that name the same service, because "
                        "a second, correct address usually already exists somewhere in it."
                    ),
                    "file": f"code/{product_id}/{str(_dep.get('source') or '').split(':')[0]}",
                }
            )
        run.journey = journey

    def _qa_gate_verdicts(self, run: _QARun) -> None:
        demo_report, delivery_profile, methodology_review = run.demo_report, run.delivery_profile, run.methodology_review
        api_contract, journey, frontend_build = run.api_contract, run.journey, run.frontend_build
        req_manifest, module_health = run.req_manifest, run.module_health
        browser_e2e, backend_e2e = run.browser_e2e, run.backend_e2e

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
        run.demo_gates_ok, run.api_contract_ok, run.journey_ok = demo_gates_ok, api_contract_ok, journey_ok
        run.frontend_build_ok, run.req_manifest_ok = frontend_build_ok, req_manifest_ok
        run.module_health_ok, run.browser_ok, run.backend_ok = module_health_ok, browser_ok, backend_ok
        run.perf_slo, run.methodology_ok, run.gates_ok = perf_slo, methodology_ok, gates_ok

    def _qa_blocking_defects(self, run: _QARun) -> None:
        module_health, frontend_build, req_manifest = run.module_health, run.frontend_build, run.req_manifest
        journey, api_contract, backend_e2e = run.journey, run.api_contract, run.backend_e2e

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
            "mesh_participant_violation",
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
        run.blocking_defects = blocking_defects

    def _qa_repair_scope(self, run: _QARun) -> list[str]:
        """The files the next repair round may edit, ranked and cut to six; else half the tree."""
        product_id, module_health, frontend_build = run.product_id, run.module_health, run.frontend_build
        backend_ok, api_contract_ok, module_health_ok = run.backend_ok, run.api_contract_ok, run.module_health_ok

        # File-level scope, when the blocking defects say which files they live in. The
        # half-of-the-tree version below only engages when one half is green, so with both
        # halves failing there was NO limit at all and the round rewrote everything: one
        # measured round came back at 128 severity-weighted against a baseline of 41 — three
        # times worse — while its actual work list was four mesh-contract violations in a
        # single client module and one duplicate table across two model files. Three files
        # of work, eighty-five files of edits, and the round is thrown away.
        # Only used when the set is small. A "scope" naming thirty files is not a scope, and
        # pretending otherwise would let a sprawling round call itself surgical.
        blocking_files: list[str] = []

        # Boot/answer-fatal Python before tsc cosmetics. Otherwise six unused-React
        # TSX files fill the truncation and atlas_client.py never enters.
        for _bf in _boot_fatal_scope_files(module_health, product_id):
            if _bf not in blocking_files:
                blocking_files.append(_bf)

        self._qa_live_mesh_scope(run, blocking_files)
        self._qa_gate_scope(run, blocking_files)
        self._qa_finding_scope(run, blocking_files)
        repair_scope = self._qa_rank_scope(run, blocking_files)

        # When one half of the product is green and the other is not, say so. A
        # repair round rewrites ~85 files regardless, which is 40-odd chances to
        # break a working backend while fixing the frontend — and that is exactly
        # how a product with boot+contract+module-health passing kept losing them.
        backend_green = backend_ok and api_contract_ok and module_health_ok
        frontend_green = frontend_build.get("skipped") or frontend_build.get("passed", False)
        if not repair_scope:
            if backend_green and not frontend_green:
                repair_scope = ["frontend/"]
            elif frontend_green and not backend_green:
                repair_scope = ["backend/"]
        return repair_scope

    def _qa_live_mesh_scope(self, run: _QARun, blocking_files: list[str]) -> None:
        product_id, all_bugs = run.product_id, run.all_bugs

        # Live soft mesh (UNKNOWN / payment_authorization / escrow) outranks
        # undeclared_dep noise — otherwise developer thrash never opens atlas_client.
        try:
            from pathlib import Path as _Path
            import json as _json
            import urllib.request as _urlreq

            _ap = self.data_root / "state" / product_id / "auto_publish.json"
            _live_url = ""
            if _ap.is_file():
                _rec = _json.loads(_ap.read_text(encoding="utf-8"))
                _live_url = str(
                    _rec.get("vercel_url")
                    or (_rec.get("vercel") or {}).get("published_url")
                    or _rec.get("published_url")
                    or ""
                ).strip()
                _lg = _rec.get("live_gate") if isinstance(_rec.get("live_gate"), dict) else {}
                for _iss in _lg.get("issues") or []:
                    _txt = str(_iss)
                    if "live_mesh" in _txt.lower() or "payment_authorization" in _txt.lower() or "mesh response" in _txt.lower():
                        all_bugs.insert(
                            0,
                            {
                                "severity": "critical",
                                "title": _txt[:180],
                                "detail": _txt[:400],
                                "file": "backend/app/services/atlas_client.py",
                            },
                        )
            if _live_url:
                _probe = _live_url.rstrip("/") + "/api/advisory?lat=34.05&lon=-118.25"
                try:
                    with _urlreq.urlopen(_probe, timeout=20) as _resp:
                        _body = _json.loads(_resp.read().decode("utf-8", errors="replace"))
                    _reason = str(((_body.get("overall") or {}) if isinstance(_body, dict) else {}).get("reason") or "")
                    if any(
                        x in _reason.lower()
                        for x in (
                            "mesh response unavailable",
                            "payment_authorization",
                            "not open on chain",
                            "all connection attempts failed",
                        )
                    ):
                        all_bugs.insert(
                            0,
                            {
                                "severity": "critical",
                                "title": f"live_mesh_unreachable:{_reason[:160]}",
                                "detail": (
                                    "Deployed /api/advisory soft-fails mesh. Prefer "
                                    "atlas_client / aimarket_participant / escrow reopen "
                                    f"({_reason[:200]})"
                                ),
                                "file": "backend/app/services/atlas_client.py",
                            },
                        )
                        for _mesh_rel in (
                            "backend/app/services/atlas_client.py",
                            "backend/app/services/aimarket_participant.py",
                            "backend/app/services/rule_engine.py",
                        ):
                            if _mesh_rel not in blocking_files:
                                blocking_files.insert(0, _mesh_rel)
                except Exception:
                    pass
        except Exception:
            pass

    def _qa_gate_scope(self, run: _QARun, blocking_files: list[str]) -> None:
        product_id, module_health, journey = run.product_id, run.module_health, run.journey
        frontend_build, req_manifest = run.frontend_build, run.req_manifest
        browser_ok, demo_gates_ok = run.browser_ok, run.demo_gates_ok

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

    def _qa_finding_scope(self, run: _QARun, blocking_files: list[str]) -> None:
        product_id, module_health, api_contract = run.product_id, run.module_health, run.api_contract
        journey, browser_e2e = run.journey, run.browser_e2e

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

    def _qa_rank_scope(self, run: _QARun, blocking_files: list[str]) -> list[str]:
        product_id, module_health, journey = run.product_id, run.module_health, run.journey
        frontend_build, req_manifest = run.frontend_build, run.req_manifest
        browser_ok, demo_gates_ok = run.browser_ok, run.demo_gates_ok
        repair_scope: list[str] = []
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
        return repair_scope

    def _qa_verdict(self, run: _QARun) -> None:
        static_analysis_results, test_results, import_errors = (
            run.static_analysis_results, run.test_results, run.import_errors)
        demo_report, browser_ok, backend_ok, gates_ok = run.demo_report, run.browser_ok, run.backend_ok, run.gates_ok
        acceptance_report, all_bugs, all_security = run.acceptance_report, run.all_bugs, run.all_security

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
        run.release_score, run.overall_verdict = release_score, overall_verdict

    def _qa_report(self, run: _QARun) -> dict:
        """The QA result, saved as the product's QA report and as demo-gate telemetry."""
        product_id, is_bug_fix = run.product_id, run.is_bug_fix
        all_bugs, all_security, all_performance = run.all_bugs, run.all_security, run.all_performance
        static_analysis_results, test_results, import_errors = (
            run.static_analysis_results, run.test_results, run.import_errors)
        release_score, overall_verdict = run.release_score, run.overall_verdict
        demo_report, demo_gates_ok, browser_e2e, browser_ok = (
            run.demo_report, run.demo_gates_ok, run.browser_e2e, run.browser_ok)
        backend_e2e, backend_ok, api_contract, api_contract_ok = (
            run.backend_e2e, run.backend_ok, run.api_contract, run.api_contract_ok)
        journey, journey_ok, frontend_build, frontend_build_ok = (
            run.journey, run.journey_ok, run.frontend_build, run.frontend_build_ok)
        req_manifest, req_manifest_ok, module_health, module_health_ok = (
            run.req_manifest, run.req_manifest_ok, run.module_health, run.module_health_ok)
        blocking_defects, repair_scope, gates_ok, perf_slo = (
            run.blocking_defects, run.repair_scope, run.gates_ok, run.perf_slo)
        acceptance_report, acceptance_pack, maintainability_review = (
            run.acceptance_report, run.acceptance_pack, run.maintainability_review)
        methodology_review, methodology_ok, traceability_matrix = (
            run.methodology_review, run.methodology_ok, run.traceability_matrix)

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
            write_text_atomic(tel / "demo_quality_gate.json", json.dumps(
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
                ))
        except OSError as _suppressed_exc:
            log_suppressed(logger, "non-fatal (agents/qa.py)", exc_info=_suppressed_exc)
        return qa_result

    def _qa_output(self, run: _QARun, qa_result: dict) -> AgentOutput:
        agent_input, product_id, start_time = run.agent_input, run.product_id, run.start_time
        delivery_profile, gates_ok, perf_slo = run.delivery_profile, run.gates_ok, run.perf_slo
        all_bugs, all_security, test_results = run.all_bugs, run.all_security, run.test_results
        demo_report, browser_e2e, backend_e2e = run.demo_report, run.browser_e2e, run.backend_e2e
        blocking_defects, repair_scope, api_contract = run.blocking_defects, run.repair_scope, run.api_contract
        journey, frontend_build, req_manifest = run.journey, run.frontend_build, run.req_manifest
        module_health, acceptance_report, acceptance_pack = (
            run.module_health, run.acceptance_report, run.acceptance_pack)
        maintainability_review, methodology_review, methodology_ok = (
            run.maintainability_review, run.methodology_review, run.methodology_ok)
        traceability_matrix = run.traceability_matrix

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
