"""
LLM Provider Abstraction Layer
================================
Defines the abstract interface for all LLM providers (local and external).
All providers must implement this interface to be used by the AI-Factory.
"""

from __future__ import annotations

import enum
import time
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import AsyncGenerator, Optional

from llm.factory_defaults import FACTORY_MAX_OUTPUT_TOKENS_HEAVY

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
    model_override: Optional[str] = None
    # Filled by LLMRouter / BaseAgent for admin LLM logs (llm_calls.jsonl)
    task_type: Optional[str] = None
    agent_type: Optional[str] = None
    #: Routing tier for pricing when only total token counts exist ("heavy" | "light")
    model_role: Optional[str] = None


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
    async def generate(self, prompt: str, config: Optional[GenerationConfig] = None) -> str:
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
        self, prompt: str, config: Optional[GenerationConfig] = None
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
