"""
DevOps Agent
============
Responsible for:
- Security scanning
- Deployment configuration
- Docker/container setup
- CI/CD pipeline configuration
- Sandbox environment setup
"""

from __future__ import annotations

import json
import logging
import time

from agents.prompt_utils import prompt_json
from agents.prompts.load_prompt import load_prompt
from core.logging_utils import log_suppressed
from llm import GenerationConfig, LLMRouter
from llm.factory_defaults import FACTORY_MAX_OUTPUT_TOKENS_HEAVY, FACTORY_TIMEOUT_DEFAULT_AGENT_SEC

from .base_agent import AgentInput, AgentOutput, BaseAgent

logger = logging.getLogger(__name__)

DEVOPS_SYSTEM_PROMPT = load_prompt("devops_system_prompt.md")


class DevOpsAgent(BaseAgent):
    """DevOps Agent - handles deployment, security, and infrastructure."""

    def __init__(self, llm_router: LLMRouter):
        super().__init__(
            agent_type="devops",
            llm_router=llm_router,
            task_type="devops_setup",
        )

    async def execute(self, agent_input: AgentInput) -> AgentOutput:
        start_time = time.time()
        product_id = agent_input.product_id
        agent_input.data.get("code_data", {})

        self._log("INFO", f"Running DevOps tasks for {product_id}")

        try:
            # Load code manifest
            manifest = self._load_artifact(product_id, "code", "code_manifest.json")
            code_files = manifest.get("files", []) if manifest else []

            code_str = prompt_json({"file_count": len(code_files), "files": code_files[:20]})

            spec_hint = ""
            from core.paths import specification_path

            sp = specification_path(product_id)
            if sp.is_file():
                try:
                    raw_sp = json.loads(sp.read_text(encoding="utf-8"))
                    dp = (raw_sp or {}).get("delivery_profile") if isinstance(raw_sp, dict) else None
                    if dp:
                        spec_hint = f"\nSpecification delivery_profile: {dp}\n"
                except Exception as _suppressed_exc:
                    log_suppressed(logger, "non-fatal (agents/devops.py)", exc_info=_suppressed_exc)

            prompt = f"""{DEVOPS_SYSTEM_PROMPT}

Product ID: {product_id}
{spec_hint}
Code Files:
{code_str}

Please perform security scanning and create deployment configuration.
"""

            config = GenerationConfig(
                temperature=0.7,
                max_tokens=FACTORY_MAX_OUTPUT_TOKENS_HEAVY,
                timeout_sec=FACTORY_TIMEOUT_DEFAULT_AGENT_SEC,
                json_mode=True,  # openai_compatible skips response_format for reasoning models
            )

            response = await self._generate(prompt, config=config, agent_input=agent_input)

            devops_result = self._extract_json(response)
            if devops_result is None:
                elapsed = time.time() - start_time
                self._log("WARNING", f"DevOps analysis failed: LLM returned non-JSON response for {product_id}")
                return AgentOutput(
                    task_id=agent_input.task_id,
                    product_id=product_id,
                    agent_type=self.agent_type,
                    success=False,
                    error="LLM returned invalid/non-JSON response — DevOps analysis failed",
                    timestamp=time.time(),
                    metrics={"elapsed_seconds": elapsed},
                )

            # Save security report
            self._save_artifact(product_id, "bugs", {
                "product_id": product_id,
                "devops_result": devops_result,
                "created_at": time.time(),
                "agent": "devops",
            }, "security_report.json")
            lifecycle = devops_result.get("lifecycle_release") if isinstance(devops_result, dict) else None
            if isinstance(lifecycle, dict):
                self._save_artifact(
                    product_id,
                    "state",
                    {
                        "product_id": product_id,
                        "lifecycle_release": lifecycle,
                        "created_at": time.time(),
                        "agent": "devops",
                    },
                    "lifecycle_release.json",
                )

            elapsed = time.time() - start_time
            vulns = devops_result.get("security_scan", {}).get("vulnerabilities_found", 0)
            self._log("INFO", f"DevOps complete: {vulns} vulnerabilities ({elapsed:.1f}s)")

            return AgentOutput(
                task_id=agent_input.task_id,
                product_id=product_id,
                agent_type=self.agent_type,
                success=True,
                data={
                    "devops_result": devops_result,
                    "vulnerabilities_found": vulns,
                    "has_docker_config": bool(devops_result.get("docker_config")),
                    "security_file": f"bugs/{product_id}/security_report.json",
                    "lifecycle_release_file": (f"state/{product_id}/lifecycle_release.json" if isinstance(lifecycle, dict) else None),
                },
                timestamp=time.time(),
                metrics={
                    "elapsed_seconds": elapsed,
                    "vulnerabilities": vulns,
                },
            )

        except Exception as e:
            elapsed = time.time() - start_time
            self._log("ERROR", f"DevOps tasks failed: {e}")
            return AgentOutput(
                task_id=agent_input.task_id,
                product_id=product_id,
                agent_type=self.agent_type,
                success=False,
                error=str(e),
                timestamp=time.time(),
                metrics={"elapsed_seconds": elapsed},
            )
