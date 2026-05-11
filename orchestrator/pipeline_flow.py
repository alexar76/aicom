from __future__ import annotations

# Canonical state -> (agent, next_state) map used across orchestrator + worker.
PIPELINE_AGENT_FLOW: dict[str, tuple[str, str]] = {
    "IDEA_RECEIVED": ("analyst", "MARKET_RESEARCHED"),
    "MARKET_RESEARCHED": ("pm", "SPEC_WRITTEN"),
    "SPEC_WRITTEN": ("marketing", "MARKET_CONTENT_READY"),
    "MARKET_CONTENT_READY": ("methodologist", "METHODOLOGY_REVIEWED"),
    "METHODOLOGY_REVIEWED": ("architect", "ARCH_DESIGNED"),
    "ARCH_DESIGNED": ("design_critic", "DESIGN_CRITIQUED"),
    "DESIGN_CRITIQUED": ("developer", "CODE_COMMITTED"),
    "CODE_COMMITTED": ("__runtime_test__", "CODE_TESTING"),
    "CODE_TESTING": ("hardening", "DEV_FIXING"),
    "DEV_FIXING": ("qa", "QA_TESTING"),
    "QA_TESTING": ("security", "SECURITY_SCANNED"),
    "BUG_FOUND": ("developer", "DEV_FIXING"),
    "SECURITY_SCANNED": ("devops", "SALES_ACTIVE"),
    "SALES_ACTIVE": ("sales", "SANDBOX_RUNNING"),
    "SANDBOX_RUNNING": ("devops", "TELEMETRY_COLLECTING"),
    "TELEMETRY_COLLECTING": ("analyst", "EVOLUTION_ANALYZING"),
    "EVOLUTION_ANALYZING": ("__complete__", "COMPLETED"),
}

