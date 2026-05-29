"""
Developer Agent
===============
Responsible for:
- Writing code based on architecture
- Implementing features
- Creating tests
- Code documentation

Delivery mode (web vs Python CLI) is inferred from admin_instructions and validated on disk.
"""

from __future__ import annotations

import json
import logging
import shutil
import time

from agents.prompts.load_prompt import load_prompt
from core.logging_utils import log_suppressed

logger = logging.getLogger(__name__)

from typing import TYPE_CHECKING

from llm import GenerationConfig, LLMRouter
from llm.agent_prompt_split import (
    build_developer_system_prompt,
    build_developer_user_data,
    format_user_data_message,
)
from llm.factory_defaults import FACTORY_MAX_OUTPUT_TOKENS_HEAVY, FACTORY_TIMEOUT_CODE_GENERATION_SEC
from web.backend.services.reference_templates import build_reference_template_prompt_block

from .base_agent import AgentInput, AgentOutput, BaseAgent
from .dev_delivery import (
    DeliveryMode,
    desktop_app_appendix,
    full_software_browser_appendix,
    infer_delivery_mode,
    infer_desktop_stack,
    system_prompt_for_mode,
    validate_saved_files,
)
from .product_profile import DESKTOP_APP, FULL_SOFTWARE, normalize_delivery_profile

if TYPE_CHECKING:
    from pathlib import Path

DEV_CORE_PROMPT = load_prompt("developer_core_prompt.md")


def _load_developer_investigation_brief(data_root: Path, product_id: str) -> str:
    """Analyst-authored handoff stored in state/{product_id}/market_research.json."""
    path = data_root / "state" / product_id / "market_research.json"
    if not path.is_file():
        return ""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    inner = raw.get("market_research")
    if isinstance(inner, dict):
        text = inner.get("developer_investigation_brief")
    else:
        text = raw.get("developer_investigation_brief")
    if isinstance(text, str) and text.strip():
        return text.strip()
    return ""


class DeveloperAgent(BaseAgent):
    """Developer Agent - writes code from architecture designs."""

    def __init__(self, llm_router: LLMRouter):
        super().__init__(
            agent_type="developer",
            llm_router=llm_router,
            task_type="code_generation",
        )

    async def execute(self, agent_input: AgentInput) -> AgentOutput:
        start_time = time.time()
        product_id = agent_input.product_id
        architecture = agent_input.data.get("architecture", {})
        spec = agent_input.data.get("specification", {})
        admin_instructions = (agent_input.data.get("admin_instructions") or "").strip()
        idea = (agent_input.data.get("idea") or "").strip()
        category = (agent_input.data.get("category") or "").strip()
        tags = agent_input.data.get("tags") or []
        if not isinstance(tags, list):
            tags = []

        if not isinstance(spec, dict):
            spec = {}
        if not isinstance(architecture, dict):
            architecture = {}

        raw_dp = agent_input.data.get("delivery_profile")
        dprof = normalize_delivery_profile(str(raw_dp).strip() if raw_dp is not None else None)
        if not agent_input.data.get("delivery_profile") and spec.get("delivery_profile"):
            dprof = normalize_delivery_profile(str(spec.get("delivery_profile")))
        mode = infer_delivery_mode(admin_instructions or None, spec, dprof)
        desktop_stack = infer_desktop_stack(admin_instructions or None, spec) if mode == DeliveryMode.DESKTOP_APP else "tauri"
        stack_rules = system_prompt_for_mode(mode, desktop_stack=desktop_stack)
        fs_appendix = (
            full_software_browser_appendix()
            if dprof == FULL_SOFTWARE and mode == DeliveryMode.WEB_APP
            else ""
        )
        desktop_appendix = (
            desktop_app_appendix(desktop_stack)
            if dprof == DESKTOP_APP or mode == DeliveryMode.DESKTOP_APP
            else ""
        )
        fs_appendix = (fs_appendix + desktop_appendix).strip()

        polyglot_block = ""
        if dprof == FULL_SOFTWARE and isinstance(architecture, dict):
            ic = architecture.get("implementation_contract")
            if isinstance(ic, dict) and ic:
                polyglot_block = (
                    "\n=== ARCHITECT IMPLEMENTATION CONTRACT — BINDING ===\n"
                    "These runtimes and paths are **mandatory**. Implement them as real source trees — not comments.\n"
                    f"{json.dumps(ic, indent=2, ensure_ascii=False)}\n"
                    "- Match **tech_stack** + **runnable_services**: Python→`.py` trees + requirements/pyproject; "
                    "Node→package.json + TS sources; .NET→csproj/sln.\n"
                    "- If both **api** and **web** services exist, **do not** collapse everything into one static HTML file.\n"
                    "- Ship **docker-compose.yml** (unless marketing-only landing) so `docker compose up -d --build` starts "
                    "API, frontend, and every **data_plane** store that is not file-only SQLite. "
                    "Publish host ports via env vars **API_HOST_PORT**, **WEB_HOST_PORT** (and **POSTGRES_HOST_PORT** if DB port is exposed).\n"
                    "- README must list install + run + test commands from **verification_commands** (adapt if stack differs slightly).\n"
                    "- **testing_contract**: run the **test pyramid** in order — (1) component/unit, (2) functional/integration "
                    "(API + DB, no browser), (3) UI e2e last. Do not skip straight to Playwright.\n"
                    "- If **sandbox_demo_credentials** is present: seed that user in migrations/compose startup; expose "
                    "`SANDBOX_DEMO_EMAIL` / `SANDBOX_DEMO_PASSWORD` (and Vite `VITE_*` mirrors); **prefill login/password inputs** "
                    "from env when set so sandbox reviewers see populated forms.\n"
                )

        self._log(
            "INFO",
            f"Generating code for {product_id} (delivery_mode={mode.value}, admin_instructions_len={len(admin_instructions)})",
        )

        analyst_brief = ""
        if mode == DeliveryMode.WEB_APP:
            analyst_brief = _load_developer_investigation_brief(self.data_root, product_id)

        remediation: dict = {}
        qg_full = agent_input.data.get("quality_gates_feedback")
        dq_fb = agent_input.data.get("demo_quality_feedback")
        repair_round = agent_input.data.get("quality_repair_round")
        repair_max = agent_input.data.get("quality_repair_max")
        if qg_full or dq_fb:
            remediation["quality_gates"] = qg_full if qg_full else {"demo_quality": dq_fb}
            if repair_round is not None and repair_max is not None:
                remediation["quality_repair_round"] = repair_round
                remediation["quality_repair_max"] = repair_max
        if agent_input.data.get("policy_audit_trigger"):
            remediation["policy_audit_trigger"] = True
        if agent_input.data.get("monitoring_refresh_trigger"):
            remediation["monitoring_refresh_trigger"] = True
        if agent_input.data.get("user_support_trigger"):
            remediation["user_support_trigger"] = True
        sg_fb = agent_input.data.get("security_gate_feedback")
        if sg_fb:
            remediation["security_gate_feedback"] = sg_fb
            sec_round = agent_input.data.get("security_repair_round")
            sec_max = agent_input.data.get("security_repair_max")
            if sec_round is not None and sec_max is not None:
                remediation["security_repair_round"] = sec_round
                remediation["security_repair_max"] = sec_max

        implementation_plan = {
            "modules": [
                "ui",
                "services",
                "state_or_data_layer",
                "tests",
            ],
            "contracts_first": {
                "api_contract_needed": bool("api" in json.dumps(spec).lower() or "endpoint" in json.dumps(spec).lower()),
                "schema_or_model_needed": bool("model" in json.dumps(spec).lower() or "data" in json.dumps(spec).lower()),
            },
            "quality_targets": ["pass quality gates", "maintainability", "security", "a11y"],
        }
        # implementation_plan.json is written AFTER LLM files — shutil.rmtree(code_root) would delete an early save.

        patch_mode = bool(
            agent_input.data.get("qa_gate_blocked")
            or agent_input.data.get("peer_review_feedback")
            or agent_input.data.get("security_gate_blocked")
        )
        patch_mode_note = (
            "\nSELF-HEALING PATCH MODE: Prefer minimal targeted edits to failing files/modules based on feedback, "
            "instead of full rewrites, unless architecture mismatch forces regeneration.\n"
            if patch_mode
            else ""
        )

        reference_shell_block = ""
        if mode == DeliveryMode.WEB_APP:
            reference_shell_block = build_reference_template_prompt_block(
                product_id=product_id,
                specification=spec,
                admin_instructions=admin_instructions,
                data_root=self.data_root,
            )

        developer_user_data = build_developer_user_data(
            idea=idea,
            category=category,
            tags=tags,
            admin_instructions=admin_instructions,
            architecture=architecture,
            specification=spec,
            delivery_mode=mode.value,
            delivery_profile=dprof,
            implementation_plan=implementation_plan,
            analyst_brief=analyst_brief or None,
            remediation=remediation or None,
            interface_locale=str(agent_input.data.get("interface_locale") or "") or None,
            content_locale=str(agent_input.data.get("content_locale") or "") or None,
        )
        user_message = format_user_data_message(developer_user_data)

        max_attempts = 2
        last_error = ""
        code_data: dict | None = None

        try:
            for attempt in range(max_attempts):
                correction_note = ""
                if attempt > 0:
                    correction_note = (
                        f"CORRECTION REQUIRED (attempt {attempt + 1} of {max_attempts}): "
                        f"previous output failed validation — {last_error}. "
                        f"Regenerate the entire JSON output; delivery_mode={mode.value}."
                    )
                system_prompt = build_developer_system_prompt(
                    core_prompt=DEV_CORE_PROMPT,
                    stack_rules=stack_rules,
                    reference_shell_block=reference_shell_block,
                    fs_appendix=fs_appendix,
                    polyglot_block=polyglot_block,
                    patch_mode_note=patch_mode_note,
                    correction_note=correction_note,
                )
                prompt = user_message

                timeout_sec = (
                    FACTORY_TIMEOUT_CODE_GENERATION_SEC
                    if dprof in (FULL_SOFTWARE, DESKTOP_APP)
                    else (120.0 if mode == DeliveryMode.PYTHON_CLI else 150.0)
                )
                config = GenerationConfig(
                    temperature=0.55 if attempt > 0 else 0.65,
                    max_tokens=FACTORY_MAX_OUTPUT_TOKENS_HEAVY,
                    timeout_sec=timeout_sec,
                    json_mode=True,
                )

                response = await self._generate(
                    prompt,
                    config=config,
                    agent_input=agent_input,
                    system_prompt=system_prompt,
                )

                code_data = self._extract_json(response)
                if code_data is None:
                    last_error = (
                        "LLM returned invalid/non-JSON response (often truncated output — "
                        "retrying with same token budget)"
                    )
                    self._log("WARNING", f"Code generation invalid JSON for {product_id} (attempt {attempt + 1})")
                    if attempt + 1 >= max_attempts:
                        break
                    continue

                code_root = self.data_root / "code" / product_id
                if code_root.exists():
                    shutil.rmtree(code_root)

                saved_relative_paths = []
                saved_files = []
                for file_info in code_data.get("files", []) or []:
                    file_path = file_info.get("path", "")
                    content = file_info.get("content", "")
                    if file_path and content:
                        full_path = self.data_root / "code" / product_id / file_path
                        full_path.parent.mkdir(parents=True, exist_ok=True)
                        with open(full_path, "w", encoding="utf-8") as f:
                            f.write(content)
                        saved_relative_paths.append(file_path)
                        saved_files.append({
                            "path": file_path,
                            "full_path": str(full_path),
                            "content": content[:5000],
                        })

                ok, validation_msg = validate_saved_files(mode, saved_relative_paths)
                if ok:
                    break

                last_error = validation_msg
                self._log(
                    "WARNING",
                    f"Delivery validation failed for {product_id}: {validation_msg} (attempt {attempt + 1})",
                )
            else:
                elapsed = time.time() - start_time
                err = last_error or "LLM returned invalid/non-JSON response — code generation failed"
                if "invalid/non-JSON" in err or "invalid JSON" in err.lower():
                    err = "LLM returned invalid/non-JSON response — code generation failed"
                return AgentOutput(
                    task_id=agent_input.task_id,
                    product_id=product_id,
                    agent_type=self.agent_type,
                    success=False,
                    error=f"Delivery constraints not satisfied after {max_attempts} attempts: {err}",
                    timestamp=time.time(),
                    metrics={"elapsed_seconds": elapsed},
                )

            if code_data is None:
                raise RuntimeError("Developer agent finished without code_data")

            self._save_artifact(
                product_id,
                "code",
                {"product_id": product_id, "implementation_plan": implementation_plan, "created_at": time.time()},
                "implementation_plan.json",
            )

            self._save_artifact(product_id, "code", {
                "product_id": product_id,
                "delivery_mode": mode.value,
                "admin_instructions_applied": bool(admin_instructions),
                "files": saved_files,
                "dependencies": code_data.get("dependencies", []),
                "setup_instructions": code_data.get("setup_instructions", ""),
                "test_commands": code_data.get("test_commands", []),
                "documentation": code_data.get("documentation", ""),
                "created_at": time.time(),
                "agent": "developer",
            }, "code_manifest.json")

            if mode.value == "web_app":
                try:
                    from web.backend.services.code_entrypoint import ensure_web_entrypoint_at_product_root

                    ensure_web_entrypoint_at_product_root(product_id)
                except Exception as _suppressed_exc:
                    log_suppressed(logger, "non-fatal (agents/dev.py)", exc_info=_suppressed_exc)

            elapsed = time.time() - start_time
            self._log("INFO", f"Code generation complete: {len(saved_files)} files ({elapsed:.1f}s), mode={mode.value}")

            return AgentOutput(
                task_id=agent_input.task_id,
                product_id=product_id,
                agent_type=self.agent_type,
                success=True,
                data={
                    "files": saved_files,
                    "file_count": len(saved_files),
                    "delivery_mode": mode.value,
                    "dependencies": code_data.get("dependencies", []),
                    "test_commands": code_data.get("test_commands", []),
                    "setup_instructions": code_data.get("setup_instructions", ""),
                    "manifest_file": f"code/{product_id}/code_manifest.json",
                    "peer_review": {
                        "recommended": "approve",
                        "blockers": [],
                        "notes": "Developer implementation completed; handoff to hardening/QA.",
                    },
                },
                timestamp=time.time(),
                metrics={
                    "elapsed_seconds": elapsed,
                    "files_created": len(saved_files),
                },
            )

        except Exception as e:
            elapsed = time.time() - start_time
            self._log("ERROR", f"Code generation failed: {e}")
            return AgentOutput(
                task_id=agent_input.task_id,
                product_id=product_id,
                agent_type=self.agent_type,
                success=False,
                error=str(e),
                timestamp=time.time(),
                metrics={"elapsed_seconds": elapsed},
            )
