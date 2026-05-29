"""
OpenAI-Compatible Provider
==========================
Implements LLMProvider for external OpenAI-compatible APIs:
- DeepSeek API
- Together.ai
- Groq
- Fireworks.ai
- AnyScale
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import httpx

from .pricing_estimate import estimate_llm_call_cost_usd
from .provider import (
    GenerationConfig,
    LLMProvider,
    ModelCapabilities,
    ProviderHealth,
    ProviderStatus,
)
from .usage_guard import record_llm_call_spend

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

logger = logging.getLogger(__name__)


class OpenAICompatibleProvider(LLMProvider):
    """
    Provider for external OpenAI-compatible APIs.
    
    Supports any API that follows the OpenAI chat completions format:
    - DeepSeek (api.deepseek.com/v1)
    - Together.ai (api.together.xyz/v1)
    - Groq (api.groq.com/openai/v1)
    - Fireworks.ai
    - AnyScale
    """

    def __init__(
        self,
        name: str = "openai_compatible",
        config: dict | None = None,
        base_url: str = "https://api.deepseek.com/v1",
        api_key: str | None = None,
        api_key_env: str | None = None,
        model: str = "deepseek-chat",
        fallback_model: str | None = None,
    ):
        super().__init__(name, config or {})
        self.base_url = base_url.rstrip("/")
        
        # Resolve API key from env var or direct value
        if api_key_env and not api_key:
            api_key = os.environ.get(api_key_env, "")
        self.api_key = api_key or ""
        
        self.model = model
        self.fallback_model = fallback_model

        # Build headers — only add Authorization if an API key is configured
        # (local providers like LM Studio don't require API keys)
        headers = {
            "Content-Type": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        else:
            logger.info(
                f"Provider '{name}': no API key configured, "
                f"skipping Authorization header (base_url: {self.base_url})"
            )
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers=headers,
            timeout=httpx.Timeout(120.0),
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
        )

    async def generate(self, prompt: str, config: GenerationConfig | None = None) -> str:
        cfg = config or GenerationConfig()
        start_time = time.time()
        response_text = ""
        tokens_used = 0
        active_model = cfg.model_override or self.model

        try:
            messages = self._build_messages(prompt, cfg)
            # Use model_override if provided (for per-task model selection)
            payload = {
                "model": active_model,
                "messages": messages,
                "temperature": cfg.temperature,
                "max_tokens": cfg.max_tokens,
                "top_p": cfg.top_p,
                "stream": False,
            }

            # Reasoning models (deepseek-reasoner, o1, o3) don't support response_format
            # Check the ACTIVE model, not self.model, since model_override may differ
            active_is_reasoning = "reasoner" in active_model.lower() or active_model.startswith(("o1", "o3"))
            if cfg.json_mode and not active_is_reasoning:
                payload["response_format"] = {"type": "json_object"}

            if cfg.stop_sequences:
                payload["stop"] = cfg.stop_sequences

            response = await self._client.post(
                "/chat/completions",
                json=payload,
                timeout=cfg.timeout_sec,
            )
            response.raise_for_status()
            result = response.json()

            latency = (time.time() - start_time) * 1000
            usage = result.get("usage") or {}
            pt = usage.get("prompt_tokens")
            ct = usage.get("completion_tokens")
            tt = usage.get("total_tokens")
            tokens_used = int(tt or 0)
            if pt is not None and ct is not None:
                tokens_used = int(pt) + int(ct)
            elif not tokens_used and isinstance(tt, (int, float)):
                tokens_used = int(tt)

            response_text = result["choices"][0]["message"]["content"]

            self._update_metrics(tokens_used, latency)
            self._record_success()

            self._log_llm_call(
                prompt,
                response_text,
                latency,
                True,
                tokens_used=tokens_used,
                prompt_tokens=pt,
                completion_tokens=ct,
                model=active_model,
                task_type=cfg.task_type,
                agent_type=cfg.agent_type,
                model_role=getattr(cfg, "model_role", None),
                product_id=getattr(cfg, "product_id", None),
            )
            return response_text

        except httpx.HTTPError as e:
            latency = (time.time() - start_time) * 1000
            self._update_metrics(0, latency)
            self._record_failure(str(e))
            str(e)
            
            # Try fallback model if available
            if self.fallback_model and self.model != self.fallback_model:
                logger.warning(f"Primary model {self.model} failed, trying fallback {self.fallback_model}")
                original_model = self.model
                self.model = self.fallback_model
                try:
                    return await self.generate(prompt, config)
                finally:
                    self.model = original_model
            
            logger.error(f"OpenAI-compatible generate failed: {e}")
            self._log_llm_call(
                prompt,
                str(e),
                latency,
                False,
                error=str(e),
                model=active_model,
                task_type=cfg.task_type,
                agent_type=cfg.agent_type,
                model_role=getattr(cfg, "model_role", None),
                product_id=getattr(cfg, "product_id", None),
            )
            raise RuntimeError(f"Generation failed for {self.name}: {e}") from e

    async def stream(
        self, prompt: str, config: GenerationConfig | None = None
    ) -> AsyncGenerator[str, None]:
        cfg = config or GenerationConfig()
        start_time = time.time()
        total_tokens = 0

        try:
            messages = self._build_messages(prompt, cfg)
            payload = {
                "model": self.model,
                "messages": messages,
                "temperature": cfg.temperature,
                "max_tokens": cfg.max_tokens,
                "top_p": cfg.top_p,
                "stream": True,
            }

            async with self._client.stream(
                "POST", "/chat/completions", json=payload, timeout=cfg.timeout_sec
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:].strip()
                        if data_str == "[DONE]":
                            break
                        if data_str:
                            import json
                            data = json.loads(data_str)
                            delta = data.get("choices", [{}])[0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                total_tokens += 1
                                yield content

            latency = (time.time() - start_time) * 1000
            self._update_metrics(total_tokens, latency)
            self._record_success()

        except httpx.HTTPError as e:
            latency = (time.time() - start_time) * 1000
            self._update_metrics(total_tokens, latency)
            self._record_failure(str(e))
            logger.error(f"OpenAI-compatible stream failed: {e}")
            raise RuntimeError(f"Streaming failed for {self.name}: {e}") from e

    async def check_health(self) -> ProviderHealth:
        start_time = time.time()
        try:
            # Use a minimal request to check availability
            response = await self._client.get("/models", timeout=5.0)
            latency = (time.time() - start_time) * 1000

            if response.status_code == 200:
                models_data = response.json()
                available_models = [m["id"] for m in models_data.get("data", [])]
                model_available = self.model in available_models

                self.health.status = ProviderStatus.ONLINE if model_available else ProviderStatus.DEGRADED
                self.health.latency_ms = latency
                self.health.last_check = time.time()
                self.health.consecutive_failures = 0
                if not model_available:
                    self.health.error_message = f"Model '{self.model}' not available"
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
        caps = (self.config or {}).get("capabilities") or {}
        if isinstance(caps, dict) and caps.get("context_window"):
            ctx_heavy = int(caps.get("context_window") or 128_000)
            ctx_light = int(caps.get("context_window_light") or ctx_heavy)
            max_tok = int(caps.get("max_tokens") or 8192)
            models = (self.config or {}).get("models") or {}
            light_model = str(models.get("light") or "").strip()
            active = str(self.model or "").strip()
            ctx = ctx_light if light_model and active == light_model else ctx_heavy
            return ModelCapabilities(
                context_window=ctx,
                max_tokens=max_tok,
                supports_vision=bool(caps.get("supports_vision", False)),
                supports_streaming=bool(caps.get("supports_streaming", True)),
                supports_functions=True,
                supports_json_mode=True,
            )
        # Legacy fallbacks when YAML capabilities are missing
        if "70b" in self.model.lower() or "deepseek-chat" in self.model.lower():
            return ModelCapabilities(
                context_window=65536,
                max_tokens=8192,
                supports_vision=False,
                supports_streaming=True,
                supports_functions=True,
                supports_json_mode=True,
            )
        return ModelCapabilities(
            context_window=32768,
            max_tokens=4096,
            supports_vision=False,
            supports_streaming=True,
            supports_functions=True,
            supports_json_mode=True,
        )

    def _build_messages(self, prompt: str, config: GenerationConfig) -> list[dict]:
        """Build the messages array for the chat completions API."""
        messages = [{"role": "user", "content": prompt}]
        return messages

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
    ):
        """Log LLM API call to JSONL file for admin visibility."""
        try:
            from core.paths import logs_dir

            log_dir = logs_dir()
            log_dir.mkdir(parents=True, exist_ok=True)
            log_file = log_dir / "llm_calls.jsonl"

            entry = {
                "timestamp": datetime.now(UTC).isoformat(),
                "provider": self.name,
                "model": model or self.model,
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

            amodel = model or self.model
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
            logger.debug(f"Failed to log LLM call: {e}")

    async def close(self):
        await self._client.aclose()
