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

import logging
import os
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

            choice = (result.get("choices") or [{}])[0]
            cfg.finish_reason = str(choice.get("finish_reason") or "")
            if cfg.was_truncated:
                logger.warning(
                    "%s: completion stopped at the output limit (finish_reason=%s) — the reply is "
                    "CUT OFF, not finished", active_model, cfg.finish_reason)
            response_text = result["choices"][0]["message"]["content"]
            if response_text is None:
                # `content: null` is what this API returns when the model produced no text at
                # all — a refusal, a filter, a tool-only turn. Returning None from a function
                # annotated `-> str` pushed the problem to whoever called len() on it, inside
                # a bare except. Say what happened instead.
                cfg.finish_reason = cfg.finish_reason or "no_content"
                logger.warning("%s: returned no content (finish_reason=%s)",
                               active_model, cfg.finish_reason)
                response_text = ""

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
        # Honor the per-task model selection — streaming previously always used
        # self.model, ignoring model_override (wrong model + mispriced spend).
        active_model = cfg.model_override or self.model

        try:
            messages = self._build_messages(prompt, cfg)
            payload = {
                "model": active_model,
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
                            choice = (data.get("choices") or [{}])[0]
                            # The terminal chunk carries it; a stream that ran out of budget
                            # otherwise ends exactly like one that finished, and the caller
                            # cannot tell a complete answer from a severed one.
                            if choice.get("finish_reason"):
                                cfg.finish_reason = str(choice["finish_reason"])
                            delta = choice.get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                total_tokens += 1
                                yield content

            latency = (time.time() - start_time) * 1000
            if cfg.was_truncated:
                logger.warning(
                    "%s: STREAM stopped at the output limit (finish_reason=%s) — what was "
                    "yielded is cut off, not finished", active_model, cfg.finish_reason)
            self._update_metrics(total_tokens, latency)
            self._record_success()
            # Book spend for the streamed call (was previously unrecorded, so
            # streaming bypassed the daily/monthly USD cost caps).
            self._log_llm_call(
                prompt, "", latency, True,
                tokens_used=total_tokens,
                completion_tokens=total_tokens,
                model=active_model,
                task_type=cfg.task_type,
                agent_type=cfg.agent_type,
                model_role=getattr(cfg, "model_role", None),
                product_id=getattr(cfg, "product_id", None),
            )

        except httpx.HTTPError as e:
            latency = (time.time() - start_time) * 1000
            self._update_metrics(total_tokens, latency)
            self._record_failure(str(e))
            self._log_llm_call(
                prompt, str(e), latency, False, error=str(e),
                tokens_used=total_tokens, model=active_model,
                task_type=cfg.task_type, agent_type=cfg.agent_type,
                model_role=getattr(cfg, "model_role", None),
                product_id=getattr(cfg, "product_id", None),
            )
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

    # _log_llm_call is provided by the base LLMProvider so cost accounting is
    # shared across every provider (see llm/provider.py).

    async def close(self):
        await self._client.aclose()
