"""
Agent package — lazy exports so ``import agents.product_profile`` (and similar)
does not eagerly load every agent implementation (LLM router, metrics, etc.).
"""

from __future__ import annotations

import importlib
from typing import Any

__all__ = [
    "BaseAgent",
    "AgentInput",
    "AgentOutput",
    "PMAgent",
    "ArchitectAgent",
    "DeveloperAgent",
    "QAAgent",
    "SecurityAgent",
    "DevOpsAgent",
    "MarketingAgent",
    "SalesAgent",
    "EvolutionAnalystAgent",
    "MarketResearchAgent",
    "MethodologyAgent",
]

_EXPORTS: dict[str, tuple[str, str]] = {
    "BaseAgent": ("agents.base_agent", "BaseAgent"),
    "AgentInput": ("agents.base_agent", "AgentInput"),
    "AgentOutput": ("agents.base_agent", "AgentOutput"),
    "PMAgent": ("agents.pm", "PMAgent"),
    "ArchitectAgent": ("agents.architect", "ArchitectAgent"),
    "DeveloperAgent": ("agents.dev", "DeveloperAgent"),
    "QAAgent": ("agents.qa", "QAAgent"),
    "SecurityAgent": ("agents.security", "SecurityAgent"),
    "DevOpsAgent": ("agents.devops", "DevOpsAgent"),
    "MarketingAgent": ("agents.marketing", "MarketingAgent"),
    "SalesAgent": ("agents.sales", "SalesAgent"),
    "EvolutionAnalystAgent": ("agents.evolution_analyst", "EvolutionAnalystAgent"),
    "MarketResearchAgent": ("agents.analyst", "MarketResearchAgent"),
    "MethodologyAgent": ("agents.methodologist", "MethodologyAgent"),
}


def __getattr__(name: str) -> Any:
    if name in _EXPORTS:
        mod_path, attr = _EXPORTS[name]
        mod = importlib.import_module(mod_path)
        value = getattr(mod, attr)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(set(__all__) | {k for k in globals() if not k.startswith("_")})
