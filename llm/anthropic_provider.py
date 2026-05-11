"""
Anthropic Cloud Provider
========================
Native provider for Anthropic Messages API (Claude models).
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import AsyncGenerator, Optional

import httpx

from .provider import (
    GenerationConfig,
    LLMProvider,
    ModelCapabilities,
    ProviderHealth,
    ProviderStatus,
)

logger = logging.getLogger(__name__)


class AnthropicProvider(LLMProvider):
    def __init__(
        self,
        name: str = "anthropic_cloud",
        config: Optional[dict] = None,
        base_url: str = "https://api.anthropic.com/v1",
        api_key: Optional[str] = None,
        api_key_env: Optional[str] = "ANTHROPIC_API_KEY",
        model: str = "claude-3-5-sonnet-latest",
    ):
        super().__init__(name, config or {})
        self.base_url = base_url.rstrip("/")
        if api_key_env and not api_key:
            api_key = os.environ.get(api_key_env, "")
        self.api_key = api_key or ""
        self.model = model

        headers = {
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
        }
        if self.api_key:
            headers["x-api-key"] = self.api_key
        else:
            logger.warning("Anthropic provider '%s' has no API key configured", name)

        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers=headers,
            timeout=httpx.Timeout(120.0),
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
        )

    async def generate(self, prompt: str, config: Optional[GenerationConfig] = None) -> str:
        cfg = config or GenerationConfig()
        start = time.time()
        active_model = cfg.model_override or self.model
        try:
            payload = {
                "model": active_model,
                "max_tokens": int(min(max(cfg.max_tokens, 1), 8192)),
                "temperature": cfg.temperature,
                "messages": [{"role": "user", "content": prompt}],
            }
            if cfg.stop_sequences:
                payload["stop_sequences"] = cfg.stop_sequences

            response = await self._client.post("/messages", json=payload, timeout=cfg.timeout_sec)
            response.raise_for_status()
            result = response.json()
            text = self._extract_text(result)
            latency = (time.time() - start) * 1000
            usage = result.get("usage", {}) if isinstance(result, dict) else {}
            tokens = int((usage.get("input_tokens") or 0) + (usage.get("output_tokens") or 0))
            self._update_metrics(tokens, latency)
            self._record_success()
            return text
        except Exception as e:
            latency = (time.time() - start) * 1000
            self._update_metrics(0, latency)
            self._record_failure(str(e))
            raise RuntimeError(f"Generation failed for {self.name}: {e}")

    async def stream(self, prompt: str, config: Optional[GenerationConfig] = None) -> AsyncGenerator[str, None]:
        cfg = config or GenerationConfig(stream=True)
        active_model = cfg.model_override or self.model
        start = time.time()
        out_tokens = 0
        payload = {
            "model": active_model,
            "max_tokens": int(min(max(cfg.max_tokens, 1), 8192)),
            "temperature": cfg.temperature,
            "messages": [{"role": "user", "content": prompt}],
            "stream": True,
        }
        if cfg.stop_sequences:
            payload["stop_sequences"] = cfg.stop_sequences

        try:
            async with self._client.stream("POST", "/messages", json=payload, timeout=cfg.timeout_sec) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    chunk = line[6:].strip()
                    if not chunk or chunk == "[DONE]":
                        continue
                    try:
                        data = json.loads(chunk)
                    except json.JSONDecodeError:
                        continue
                    if data.get("type") == "content_block_delta":
                        delta = data.get("delta") or {}
                        text = delta.get("text", "")
                        if text:
                            out_tokens += 1
                            yield text
        except Exception as e:
            latency = (time.time() - start) * 1000
            self._update_metrics(out_tokens, latency)
            self._record_failure(str(e))
            raise RuntimeError(f"Streaming failed for {self.name}: {e}")

        latency = (time.time() - start) * 1000
        self._update_metrics(out_tokens, latency)
        self._record_success()

    async def check_health(self) -> ProviderHealth:
        start = time.time()
        try:
            # Lightweight endpoint that validates auth/base URL quickly.
            response = await self._client.get("/models", timeout=5.0)
            latency = (time.time() - start) * 1000
            if response.status_code in (200, 401, 403):
                # 401/403 means endpoint is reachable but key invalid; still degraded, not dead.
                self.health.status = ProviderStatus.ONLINE if response.status_code == 200 else ProviderStatus.DEGRADED
                self.health.error_message = "" if response.status_code == 200 else f"Auth status {response.status_code}"
                self.health.latency_ms = latency
                self.health.consecutive_failures = 0
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
        return ModelCapabilities(
            context_window=200_000,
            max_tokens=8192,
            supports_vision=True,
            supports_streaming=True,
            supports_functions=False,
            supports_json_mode=True,
        )

    async def close(self):
        await self._client.aclose()

    @staticmethod
    def _extract_text(result: dict) -> str:
        content = result.get("content", []) if isinstance(result, dict) else []
        if not isinstance(content, list):
            return ""
        chunks: list[str] = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                t = part.get("text")
                if isinstance(t, str):
                    chunks.append(t)
        return "".join(chunks).strip()
