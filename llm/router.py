"""
LLM Router
===========
Routes generation requests to the appropriate provider based on:
- ``default_provider`` when available (per-task heavy/light still from routing rules)
- Provider availability (health checks)
- Failover to ``fallback_provider`` / other backends only when the default is down
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import time
from pathlib import Path
from typing import Optional

import yaml

from core.paths import model_providers_path
from core.throughput_limits import effective_llm_max_parallel_requests, effective_llm_min_interval_sec
from .bootstrap_providers import ensure_model_providers_file
from .provider import LLMProvider, GenerationConfig, ProviderStatus
from .usage_guard import get_usage_guard
from .local_ollama import LocalOllamaProvider
from .openai_compatible import OpenAICompatibleProvider
from .anthropic_provider import AnthropicProvider
from web.backend.api.metrics import PrometheusMetrics

logger = logging.getLogger(__name__)


class LLMRouter:
    """
    Routes LLM requests to the best available provider.
    
    Features:
    - Task-type routing (timeouts, model roles); primary backend is ``default_provider``
    - Automatic health checks every 60 seconds
    - Failover when the default provider is unavailable
    - Provider metrics tracking
    - Parallel + min-interval throttling, RPM cap, and USD cost caps (see ``llm.usage_guard``)
    """

    def __init__(self, config_path: str | Path | None = None):
        self.config_path = str(config_path or model_providers_path())
        self.providers: dict[str, LLMProvider] = {}
        self.routing_rules: list[dict] = []
        self.default_provider: Optional[str] = None
        self._provider_configs: dict[str, dict] = {}
        self._health_check_task: Optional[asyncio.Task] = None
        self._running = False
        self._parallel_limit = max(1, effective_llm_max_parallel_requests())
        self._min_interval_sec = max(0.0, effective_llm_min_interval_sec())
        self._request_sem = asyncio.Semaphore(self._parallel_limit)
        self._last_request_mono = 0.0
        self._request_lock = asyncio.Lock()
        self._cache_enabled = os.environ.get("AIFACTORY_LLM_CACHE_ENABLED", "1").strip().lower() in {"1", "true", "yes", "on"}
        self._cache_ttl_sec = max(1, int(os.environ.get("AIFACTORY_LLM_CACHE_TTL_SEC", "300")))
        self._cache_max_entries = max(1, int(os.environ.get("AIFACTORY_LLM_CACHE_MAX_ENTRIES", "500")))
        self._response_cache: dict[str, tuple[float, str]] = {}
        self._usage_guard = get_usage_guard()
        self._load_config()

    def _load_config(self):
        """Load provider configuration from YAML file."""
        try:
            config_path = Path(self.config_path)
            logger.debug(f"LLMRouter loading config from: {self.config_path} (exists: {config_path.exists()})")
            ensure_model_providers_file(config_path)

            with open(self.config_path, "r") as f:
                config = yaml.safe_load(f)

            self.routing_rules = config.get("routing_rules", [])
            self.default_provider = config.get("default_provider")
            providers_config = config.get("providers", {})
            self._provider_configs = dict(providers_config)

            # Log enabled providers and their API key presence (helpful for debugging auth issues)
            for name, pconf in providers_config.items():
                if pconf.get("enabled", False):
                    api_key_val = pconf.get("api_key")
                    has_env = pconf.get("api_key_env")
                    key_preview = f"{api_key_val[:8]}..." if api_key_val and len(api_key_val) > 8 else ("<SET>" if api_key_val else "<NOT SET>")
                    logger.debug(
                        f"Provider '{name}': api_key={key_preview}, api_key_env={has_env!r}"
                    )

            # Initialize providers
            for name, pconf in providers_config.items():
                if not pconf.get("enabled", False):
                    continue

                provider_type = pconf.get("provider_type", "openai_compatible")
                
                if provider_type in ("local_ollama", "ollama"):
                    provider = LocalOllamaProvider(
                        name=name,
                        config=pconf,
                        base_url=pconf.get("base_url", "http://localhost:11434"),
                        model=pconf.get("models", {}).get("heavy", "qwen2.5-7b"),
                    )
                elif provider_type == "anthropic":
                    provider = AnthropicProvider(
                        name=name,
                        config=pconf,
                        base_url=pconf.get("base_url", "https://api.anthropic.com/v1"),
                        api_key=pconf.get("api_key"),
                        api_key_env=pconf.get("api_key_env", "ANTHROPIC_API_KEY"),
                        model=pconf.get("models", {}).get("heavy", "claude-3-5-sonnet-latest"),
                    )
                else:
                    provider = OpenAICompatibleProvider(
                        name=name,
                        config=pconf,
                        base_url=pconf.get("base_url", ""),
                        api_key=pconf.get("api_key"),
                        api_key_env=pconf.get("api_key_env"),
                        model=pconf.get("models", {}).get("heavy", "deepseek-chat"),
                        fallback_model=pconf.get("models", {}).get("light"),
                    )

                self.providers[name] = provider
                logger.info(f"Initialized provider: {name} ({provider_type})")

        except FileNotFoundError:
            logger.warning(f"Config file {self.config_path} not found, using defaults")
        except Exception as e:
            logger.error(f"Failed to load provider config: {e}")

    async def start_health_checks(self, interval_sec: int = 60):
        """Start periodic health checks for all providers."""
        self._running = True
        self._health_check_task = asyncio.create_task(
            self._health_check_loop(interval_sec)
        )
        logger.info("Health check loop started")

    async def stop_health_checks(self):
        """Stop periodic health checks."""
        self._running = False
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
        logger.info("Health check loop stopped")

    async def _health_check_loop(self, interval_sec: int):
        """Periodically check health of all providers."""
        while self._running:
            for name, provider in self.providers.items():
                try:
                    health = await provider.check_health()
                    # Update Prometheus health gauge
                    is_healthy = health.status not in (ProviderStatus.UNAVAILABLE, ProviderStatus.UNKNOWN)
                    PrometheusMetrics.set_provider_health(name, is_healthy)
                    logger.debug(f"Health check {name}: {health.status.value} ({health.latency_ms:.0f}ms)")
                except Exception as e:
                    PrometheusMetrics.set_provider_health(name, False)
                    logger.error(f"Health check failed for {name}: {e}")
            await asyncio.sleep(interval_sec)

    async def generate(
        self,
        prompt: str,
        task_type: str = "code_generation",
        config: Optional[GenerationConfig] = None,
    ) -> str:
        """
        Generate a response using the best provider for the task type.
        
        Args:
            prompt: The input prompt
            task_type: Type of task (determines routing)
            config: Generation parameters
            
        Returns:
            Generated text
        """
        provider_name = self._select_provider(task_type)
        if not provider_name:
            raise RuntimeError(f"No available provider for task type: {task_type}")

        provider = self.providers[provider_name]
        rule = self._get_rule(task_type)
        timeout = rule.get("timeout_sec", 30) if rule else 30

        if config is None:
            config = GenerationConfig(timeout_sec=timeout)
        config.task_type = task_type

        # Apply model_role from routing rule: set model_override if specified
        if rule and config.model_override is None:
            model_role = rule.get("model_role", "heavy")
            # Look up provider config to find the model name for this role
            model_name = self._get_model_for_role(provider_name, model_role)
            if model_name:
                config.model_override = model_name

        config.model_role = self._resolve_model_role_for_config(provider_name, config, rule)

        cache_key = self._build_cache_key(prompt, task_type, config)
        if self._cache_enabled:
            cached = self._cache_get(cache_key)
            if cached is not None:
                logger.debug("LLM cache hit for task_type=%s", task_type)
                return cached

        start_time = time.time()
        try:
            logger.info(
                f"Routing to provider '{provider_name}' for task '{task_type}'"
                f" (model: {config.model_override or 'default'})"
            )
            await self._usage_guard.acquire()
            async with self._request_sem:
                await self._rate_limit_wait()
                result = await provider.generate(prompt, config)
                if self._cache_enabled:
                    self._cache_set(cache_key, result)
            duration = time.time() - start_time
            PrometheusMetrics.inc_llm_request(provider_name, "success")
            PrometheusMetrics.observe_llm_duration(provider_name, duration)
            return result
        except Exception as e:
            duration = time.time() - start_time
            PrometheusMetrics.inc_llm_request(provider_name, "error")
            PrometheusMetrics.observe_llm_duration(provider_name, duration)
            # Try fallback
            fallback = self._get_fallback(task_type, provider_name)
            if fallback and fallback in self.providers:
                fallback_provider = self.providers[fallback]
                if fallback_provider.health.status != ProviderStatus.UNAVAILABLE:
                    logger.warning(f"Failing over to '{fallback}' for task '{task_type}'")
                    fallback_start = time.time()
                    try:
                        await self._usage_guard.acquire()
                        async with self._request_sem:
                            await self._rate_limit_wait()
                            result = await fallback_provider.generate(prompt, config)
                        if self._cache_enabled:
                            self._cache_set(cache_key, result)
                        fb_duration = time.time() - fallback_start
                        PrometheusMetrics.inc_llm_request(fallback, "success")
                        PrometheusMetrics.observe_llm_duration(fallback, fb_duration)
                        return result
                    except Exception as fb_e:
                        fb_duration = time.time() - fallback_start
                        PrometheusMetrics.inc_llm_request(fallback, "error")
                        PrometheusMetrics.observe_llm_duration(fallback, fb_duration)
                        raise fb_e
            raise

    def _build_cache_key(self, prompt: str, task_type: str, config: GenerationConfig) -> str:
        raw = "|".join(
            [
                task_type,
                config.model_override or "",
                str(config.temperature),
                str(config.max_tokens),
                str(config.json_mode),
                prompt,
            ]
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _cache_get(self, key: str) -> Optional[str]:
        row = self._response_cache.get(key)
        if not row:
            return None
        ts, value = row
        if time.time() - ts > self._cache_ttl_sec:
            self._response_cache.pop(key, None)
            return None
        return value

    def _cache_set(self, key: str, value: str) -> None:
        if len(self._response_cache) >= self._cache_max_entries:
            # Remove oldest entry (small in-memory map, O(n) acceptable).
            oldest_key = min(self._response_cache, key=lambda k: self._response_cache[k][0])
            self._response_cache.pop(oldest_key, None)
        self._response_cache[key] = (time.time(), value)

    def _get_model_for_role(self, provider_name: str, role: str) -> Optional[str]:
        """Get the model name for a given provider and role (heavy/light).
        
        Reads from the stored provider YAML config to find the model for the requested role.
        Falls back to the provider's default model if the role is not specified.
        """
        pconf = self._provider_configs.get(provider_name)
        if not pconf:
            return None
        models = pconf.get("models", {})
        if role == "light":
            return models.get("light") or models.get("heavy")
        return models.get("heavy") or models.get("light")

    def _infer_model_role(self, provider_name: str, active_model: Optional[str]) -> Optional[str]:
        """If ``active_model`` matches configured heavy/light ids, return that role."""
        if not active_model or not str(active_model).strip():
            return None
        pconf = self._provider_configs.get(provider_name) or {}
        models = pconf.get("models", {}) or {}
        am = str(active_model).strip()
        light = str(models.get("light") or "").strip()
        heavy = str(models.get("heavy") or "").strip()
        if light and am == light:
            return "light"
        if heavy and am == heavy:
            return "heavy"
        return None

    def _resolve_model_role_for_config(
        self,
        provider_name: str,
        config: GenerationConfig,
        rule: Optional[dict[str, object]],
    ) -> str:
        """Resolve heavy/light for LLM log pricing when token totals are used without in/out split."""
        pconf = self._provider_configs.get(provider_name) or {}
        models = pconf.get("models", {}) or {}
        active = (config.model_override or models.get("heavy") or models.get("light") or "").strip()
        inferred = self._infer_model_role(provider_name, active)
        if inferred:
            return inferred
        if rule:
            mr = str(rule.get("model_role", "heavy")).strip().lower()
            return mr if mr in ("heavy", "light") else "heavy"
        return "heavy"

    async def stream(
        self,
        prompt: str,
        task_type: str = "code_generation",
        config: Optional[GenerationConfig] = None,
    ):
        """Stream a response from the best provider."""
        provider_name = self._select_provider(task_type)
        if not provider_name:
            raise RuntimeError(f"No available provider for task type: {task_type}")

        provider = self.providers[provider_name]
        rule = self._get_rule(task_type)
        timeout = rule.get("timeout_sec", 30) if rule else 30

        if config is None:
            config = GenerationConfig(timeout_sec=timeout, stream=True)
        config.task_type = task_type

        if rule and config.model_override is None:
            model_role = rule.get("model_role", "heavy")
            model_name = self._get_model_for_role(provider_name, model_role)
            if model_name:
                config.model_override = model_name
        config.model_role = self._resolve_model_role_for_config(provider_name, config, rule)

        await self._usage_guard.acquire()
        async with self._request_sem:
            await self._rate_limit_wait()
            async for token in provider.stream(prompt, config):
                yield token

    async def _rate_limit_wait(self) -> None:
        if self._min_interval_sec <= 0:
            return
        async with self._request_lock:
            now = time.monotonic()
            delta = now - self._last_request_mono
            if delta < self._min_interval_sec:
                await asyncio.sleep(self._min_interval_sec - delta)
            self._last_request_mono = time.monotonic()

    def _provider_is_available(self, name: Optional[str]) -> bool:
        """True if provider is loaded and health is not UNAVAILABLE."""
        if not name or not isinstance(name, str):
            return False
        provider = self.providers.get(name)
        if provider is None:
            return False
        return provider.health.status != ProviderStatus.UNAVAILABLE

    def _select_provider(self, task_type: str) -> Optional[str]:
        """Select the best provider for a task type.

        Policy: always prefer ``default_provider`` when it is configured and
        available (heavy/light still come from that provider's YAML). Other
        providers are used only for failover — explicit ``fallback_provider``,
        then a non-auto ``preferred_provider``, then fastest remaining.
        """
        rule = self._get_rule(task_type)

        # 1) Global default first (single primary backend; two models there)
        if self._provider_is_available(self.default_provider):
            return self.default_provider

        # 2) No routing rule: any available provider by latency heuristic
        if not rule:
            return self._select_fastest_available()

        # 3) Default down / missing: rule-level failover chain
        fallback = rule.get("fallback_provider")
        if self._provider_is_available(fallback):
            return fallback

        preferred = rule.get("preferred_provider", "auto")
        if preferred not in (None, "auto") and self._provider_is_available(preferred):
            return preferred

        return self._select_fastest_available()

    def _select_fastest_available(self) -> Optional[str]:
        """Select the provider with lowest latency that is available.
        Prefers the default provider if it's healthy."""
        available = [
            (name, p.health.latency_ms)
            for name, p in self.providers.items()
            if p.health.status != ProviderStatus.UNAVAILABLE
        ]
        if not available:
            return None
        
        # If default provider is available, prefer it
        if self.default_provider:
            for name, _ in available:
                if name == self.default_provider:
                    return name
        
        # Sort by latency (lower is better)
        available.sort(key=lambda x: x[1])
        return available[0][0]

    def _get_rule(self, task_type: str) -> dict:
        """Get routing rule for a task type."""
        for rule in self.routing_rules:
            if rule.get("task_type") == task_type:
                return rule
        return {}

    def _get_fallback(self, task_type: str, current_provider: str) -> Optional[str]:
        """Get fallback provider for a task type."""
        rule = self._get_rule(task_type)
        fallback = rule.get("fallback_provider")
        if fallback and fallback != current_provider:
            return fallback
        return None

    def get_provider_metrics(self) -> dict[str, dict]:
        """Get metrics for all providers."""
        return {name: p.get_metrics() for name, p in self.providers.items()}

    def get_available_providers(self) -> list[str]:
        """Get list of provider names that are not unavailable."""
        return [
            name for name, p in self.providers.items()
            if p.health.status != ProviderStatus.UNAVAILABLE
        ]

    async def reload_config(self):
        """Hot-reload provider configuration."""
        old_providers = self.providers
        self.providers = {}
        self._load_config()
        
        # Close old provider connections
        for provider in old_providers.values():
            try:
                if hasattr(provider, "close"):
                    await provider.close()
            except Exception:
                pass
        
        logger.info("Provider configuration reloaded")

    async def close(self):
        """Clean up all provider connections."""
        await self.stop_health_checks()
        for provider in self.providers.values():
            try:
                if hasattr(provider, "close"):
                    await provider.close()
            except Exception:
                pass
