"""
Local Ollama Provider
======================
Implements LLMProvider for local Ollama/vLLM models.
Supports heavy (35B+), light (7B), and vision models.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

import httpx

from .provider import (
    GenerationConfig,
    LLMProvider,
    ModelCapabilities,
    ProviderHealth,
    ProviderStatus,
)

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

logger = logging.getLogger(__name__)


class LocalOllamaProvider(LLMProvider):
    """
    Provider for locally-hosted Ollama models.
    
    Supports:
    - Heavy models: qwen3.6-35b-a3b, llama3.1-70b, mistral-large
    - Light models: qwen2.5-7b, gemma2-27b
    - Vision models: llava-llama3
    """

    def __init__(
        self,
        name: str = "local_ollama",
        config: dict | None = None,
        base_url: str = "http://localhost:11434",
        model: str = "qwen2.5-7b",
    ):
        super().__init__(name, config or {})
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(120.0),
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
        )

    async def generate(self, prompt: str, config: GenerationConfig | None = None) -> str:
        cfg = config or GenerationConfig()
        start_time = time.time()

        try:
            payload = {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": cfg.temperature,
                    "top_p": cfg.top_p,
                    "top_k": cfg.top_k,
                    "num_predict": cfg.max_tokens,
                    "repeat_penalty": cfg.repetition_penalty,
                    "stop": cfg.stop_sequences if cfg.stop_sequences else None,
                },
            }

            response = await self._client.post("/api/generate", json=payload, timeout=cfg.timeout_sec)
            response.raise_for_status()
            result = response.json()

            latency = (time.time() - start_time) * 1000
            tokens_used = result.get("eval_count", 0)
            self._update_metrics(tokens_used, latency)
            self._record_success()

            return result.get("response", "")

        except httpx.HTTPError as e:
            latency = (time.time() - start_time) * 1000
            self._update_metrics(0, latency)
            self._record_failure(str(e))
            logger.error(f"Ollama generate failed: {e}")
            raise RuntimeError(f"Ollama generation failed: {e}") from e

    async def stream(
        self, prompt: str, config: GenerationConfig | None = None
    ) -> AsyncGenerator[str, None]:
        cfg = config or GenerationConfig()
        start_time = time.time()
        total_tokens = 0

        try:
            payload = {
                "model": self.model,
                "prompt": prompt,
                "stream": True,
                "options": {
                    "temperature": cfg.temperature,
                    "top_p": cfg.top_p,
                    "top_k": cfg.top_k,
                    "num_predict": cfg.max_tokens,
                    "repeat_penalty": cfg.repetition_penalty,
                },
            }

            async with self._client.stream(
                "POST", "/api/generate", json=payload, timeout=cfg.timeout_sec
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.strip():
                        import json
                        data = json.loads(line)
                        token = data.get("response", "")
                        if token:
                            total_tokens += 1
                            yield token

            latency = (time.time() - start_time) * 1000
            self._update_metrics(total_tokens, latency)
            self._record_success()

        except httpx.HTTPError as e:
            latency = (time.time() - start_time) * 1000
            self._update_metrics(total_tokens, latency)
            self._record_failure(str(e))
            logger.error(f"Ollama stream failed: {e}")
            raise RuntimeError(f"Ollama streaming failed: {e}") from e

    async def check_health(self) -> ProviderHealth:
        start_time = time.time()
        try:
            response = await self._client.get("/api/tags", timeout=5.0)
            latency = (time.time() - start_time) * 1000
            if response.status_code == 200:
                tags = response.json()
                models = [t["name"] for t in tags.get("models", [])]
                model_available = self.model in models or any(
                    self.model in m for m in models
                )
                self.health.status = ProviderStatus.ONLINE if model_available else ProviderStatus.DEGRADED
                self.health.latency_ms = latency
                self.health.last_check = time.time()
                self.health.consecutive_failures = 0
                if not model_available:
                    self.health.error_message = f"Model '{self.model}' not found in Ollama"
            else:
                self.health.status = ProviderStatus.DEGRADED
                self.health.error_message = f"Unexpected status: {response.status_code}"
        except httpx.HTTPError as e:
            self.health.status = ProviderStatus.UNAVAILABLE
            self.health.error_message = str(e)
            self.health.consecutive_failures += 1

        self.health.last_check = time.time()
        return self.health

    def get_capabilities(self) -> ModelCapabilities:
        # Default capabilities for Ollama models
        if "70b" in self.model.lower() or "35b" in self.model.lower():
            return ModelCapabilities(
                context_window=32768,
                max_tokens=8192,
                supports_vision="llava" in self.model.lower(),
                supports_streaming=True,
                supports_json_mode=True,
            )
        elif "vision" in self.model.lower() or "llava" in self.model.lower():
            return ModelCapabilities(
                context_window=8192,
                max_tokens=4096,
                supports_vision=True,
                supports_streaming=True,
                supports_json_mode=True,
            )
        else:
            return ModelCapabilities(
                context_window=16384,
                max_tokens=4096,
                supports_vision=False,
                supports_streaming=True,
                supports_json_mode=True,
            )

    async def close(self):
        await self._client.aclose()
