"""Landing-only developer — static HTML/CSS landing deliverable."""

from __future__ import annotations

from typing import TYPE_CHECKING

from agents.dev import DeveloperAgent

if TYPE_CHECKING:
    from llm import LLMRouter


class LandingDeveloperAgent(DeveloperAgent):
    """Lightweight landing developer (marketing_landing fast pipeline)."""

    AGENT_TYPE = "landing_developer"

    def __init__(self, llm_router: LLMRouter):
        super().__init__(llm_router)
