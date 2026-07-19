"""
LLM Provider Abstraction Layer
================================
Defines the abstract interface for all LLM providers (local and external).
All providers must implement this interface to be used by the AI-Factory.
"""

from __future__ import annotations

import enum
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from llm.factory_defaults import FACTORY_MAX_OUTPUT_TOKENS_HEAVY

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

logger = logging.getLogger(__name__)


class ProviderStatus(enum.Enum):
    """Health status of an LLM provider."""
    ONLINE = "online"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


@dataclass
class ModelCapabilities:
    """Capabilities and limitations of a model."""
    context_window: int = 128_000
    max_tokens: int = FACTORY_MAX_OUTPUT_TOKENS_HEAVY
    supports_vision: bool = False
    supports_streaming: bool = True
    supports_functions: bool = False
    supports_json_mode: bool = True


@dataclass
class GenerationConfig:
    """Configuration for a single generation request."""
    temperature: float = 0.7
    max_tokens: int = FACTORY_MAX_OUTPUT_TOKENS_HEAVY
    top_p: float = 0.95
    top_k: int = 40
    repetition_penalty: float = 1.1
    stop_sequences: list[str] = field(default_factory=list)
    stream: bool = False
    json_mode: bool = False
    timeout_sec: float = 30.0
    model_override: str | None = None
    # Filled by LLMRouter / BaseAgent for admin LLM logs (llm_calls.jsonl)
    task_type: str | None = None
    agent_type: str | None = None
    #: Routing tier for pricing when only total token counts exist ("heavy" | "light")
    model_role: str | None = None
    #: Pipeline product id for per-product LLM spend caps (llm_calls.jsonl)
    product_id: str | None = None
    #: Length (in characters) of the leading *stable* prefix of the prompt —
    #: the agent role / domain guide / style block that is identical across
    #: calls. Providers that support explicit prompt caching (Anthropic
    #: cache_control) place the cache breakpoint here; DeepSeek-style automatic
    #: prefix caching benefits from the stable-first ordering without using it.
    #: 0 means "no known stable boundary" (cache the whole prompt as usual).
    cache_prefix_len: int = 0


@dataclass
class ProviderHealth:
    """Health check result for a provider."""
    status: ProviderStatus = ProviderStatus.UNKNOWN
    latency_ms: float = 0.0
    last_check: float = 0.0
    consecutive_failures: int = 0
    error_message: str = ""


class LLMProvider(ABC):
    """
    Abstract base class for all LLM providers.
    
    All providers (local Ollama, OpenAI-compatible APIs) must implement
    the abstract methods defined here.
    """

    def __init__(self, name: str, config: dict):
        self.name = name
        self.config = config
        self.health = ProviderHealth()
        self._last_request_time = 0.0
        self._total_requests = 0
        self._total_tokens = 0
        # Last call's actual token usage (input+output). Populated by
        # `_update_metrics`. Best-effort under concurrency — a parallel call
        # to the SAME provider instance will overwrite. Router consumes this
        # immediately after `generate` returns, before yielding back.
        self._last_call_tokens = 0

    @abstractmethod
    async def generate(self, prompt: str, config: GenerationConfig | None = None) -> str:
        """
        Generate a complete response for the given prompt.
        
        Args:
            prompt: The input prompt
            config: Generation parameters
            
        Returns:
            Generated text response
        """
        ...

    @abstractmethod
    async def stream(
        self, prompt: str, config: GenerationConfig | None = None
    ) -> AsyncGenerator[str, None]:
        """
        Stream a response token by token.
        
        Args:
            prompt: The input prompt
            config: Generation parameters
            
        Yields:
            Text tokens as they are generated
        """
        ...
        yield  # pragma: no cover

    @abstractmethod
    async def check_health(self) -> ProviderHealth:
        """
        Perform a health check on this provider.
        
        Returns:
            ProviderHealth with current status and metrics
        """
        ...

    @abstractmethod
    def get_capabilities(self) -> ModelCapabilities:
        """
        Get the capabilities of this provider's current model.
        
        Returns:
            ModelCapabilities instance
        """
        ...

    def get_metrics(self) -> dict:
        """Get usage metrics for this provider."""
        return {
            "name": self.name,
            "status": self.health.status.value,
            "total_requests": self._total_requests,
            "total_tokens": self._total_tokens,
            "last_request_time": self._last_request_time,
            "latency_ms": self.health.latency_ms,
            "consecutive_failures": self.health.consecutive_failures,
        }

    def _update_metrics(self, tokens_used: int = 0, latency_ms: float = 0.0):
        """Update internal metrics after a request."""
        self._total_requests += 1
        self._total_tokens += tokens_used
        self._last_call_tokens = tokens_used
        self._last_request_time = time.time()
        self.health.latency_ms = latency_ms

    def _record_failure(self, error: str):
        """Record a failure for health tracking."""
        self.health.consecutive_failures += 1
        self.health.error_message = error
        if self.health.consecutive_failures >= 3:
            self.health.status = ProviderStatus.UNAVAILABLE
        elif self.health.consecutive_failures >= 1:
            self.health.status = ProviderStatus.DEGRADED

    def _record_success(self):
        """Record a successful request."""
        self.health.consecutive_failures = 0
        self.health.status = ProviderStatus.ONLINE
        self.health.error_message = ""

    def _log_llm_call(
        self,
        prompt: str,
        response: str,
        latency_ms: float,
        success: bool,
        error: str | None = None,
        tokens_used: int = 0,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        model: str | None = None,
        task_type: str | None = None,
        agent_type: str | None = None,
        model_role: str | None = None,
        product_id: str | None = None,
    ) -> None:
        """Append the call to ``llm_calls.jsonl`` AND book its estimated USD spend.

        Shared by all providers so cost caps / budget-tier downgrade see EVERY
        call. A provider that skips this (e.g. the old Anthropic path) silently
        bypassed daily/monthly USD limits — its spend was invisible to the guard.
        Best-effort: never let logging break a generation.
        """
        try:
            import json
            from datetime import UTC, datetime

            from core.paths import logs_dir
            from llm.pricing_estimate import estimate_llm_call_cost_usd
            from llm.usage_guard import record_llm_call_spend

            log_dir = logs_dir()
            log_dir.mkdir(parents=True, exist_ok=True)
            log_file = log_dir / "llm_calls.jsonl"

            amodel = model or getattr(self, "model", None) or ""
            entry = {
                "timestamp": datetime.now(UTC).isoformat(),
                "provider": self.name,
                "model": amodel,
                "task_type": task_type,
                "agent_type": agent_type,
                "prompt_preview": prompt[:500] if prompt else "",
                "response_preview": response[:500] if response else "",
                "latency_ms": round(latency_ms, 2),
                "success": success,
                "error": error,
                "tokens_used": tokens_used,
            }
            if prompt_tokens is not None:
                entry["prompt_tokens"] = int(prompt_tokens)
            if completion_tokens is not None:
                entry["completion_tokens"] = int(completion_tokens)
            if model_role:
                entry["model_role"] = str(model_role)
            if product_id:
                entry["product_id"] = str(product_id)

            est = estimate_llm_call_cost_usd(
                self.name,
                amodel,
                tokens_used,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                model_role=model_role,
            )
            if est is not None:
                entry["estimated_cost_usd"] = est

            with open(log_file, "a") as f:
                f.write(json.dumps(entry) + "\n")
            record_llm_call_spend(entry)
        except Exception as e:
            logger.debug("Failed to log LLM call: %s", e)
