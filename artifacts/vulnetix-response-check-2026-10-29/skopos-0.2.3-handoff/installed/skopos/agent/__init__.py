"""Public surface for skopos.agent — keep imports lazy so light modules
(injection_guard, etc.) do not pull pandas/streamlit at import time.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "AgentConfig",
    "AnalysisResult",
    "ChatMessage",
    "LLMProviderError",
    "build_agent_context",
    "build_server_context",
    "chat_completion",
    "chat_with_agent",
    "chat_with_agent_stream",
    "load_agent_config",
    "run_security_analysis",
]


def __getattr__(name: str) -> Any:
    if name in ("AgentConfig", "load_agent_config"):
        from .config import AgentConfig, load_agent_config

        return {"AgentConfig": AgentConfig, "load_agent_config": load_agent_config}[name]
    if name in ("build_agent_context", "build_server_context"):
        from .context import build_agent_context, build_server_context

        return {
            "build_agent_context": build_agent_context,
            "build_server_context": build_server_context,
        }[name]
    if name in ("ChatMessage", "LLMProviderError", "chat_completion"):
        from .providers import ChatMessage, LLMProviderError, chat_completion

        return {
            "ChatMessage": ChatMessage,
            "LLMProviderError": LLMProviderError,
            "chat_completion": chat_completion,
        }[name]
    if name in (
        "AnalysisResult",
        "chat_with_agent",
        "chat_with_agent_stream",
        "run_security_analysis",
    ):
        from .analyst import (
            AnalysisResult,
            chat_with_agent,
            chat_with_agent_stream,
            run_security_analysis,
        )

        return {
            "AnalysisResult": AnalysisResult,
            "chat_with_agent": chat_with_agent,
            "chat_with_agent_stream": chat_with_agent_stream,
            "run_security_analysis": run_security_analysis,
        }[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
