"""Landing-only architect — same stack as ArchitectAgent with fast-path metadata."""

from __future__ import annotations

from llm import LLMRouter

from agents.architect import ArchitectAgent


class LandingArchitectAgent(ArchitectAgent):
    """Lightweight landing architect (marketing_landing fast pipeline)."""

    AGENT_TYPE = "landing_architect"

    def __init__(self, llm_router: LLMRouter):
        super().__init__(llm_router)
