"""
LLM Router
===========
Routes generation requests to the appropriate provider based on:
- ``default_provider`` when available (per-task heavy/light still from routing rules)
- Provider availability (health checks + circuit breaker)
- Failover to ``fallback_provider`` / other backends when the default is down or circuit OPEN
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from core.logging_utils import log_suppressed
import os
import time
from pathlib import Path
from typing import Optional

import yaml

from core.paths import model_providers_path
from core.throughput_limits import effective_llm_max_parallel_requests, effective_llm_min_interval_sec
from .bootstrap_providers import ensure_model_providers_file
from .circuit_breaker import CircuitOpenError, get_circuit_store, sync_prometheus_from_snapshot
from .cost_guard import get_cost_guard
from .provider import LLMProvider, GenerationConfig, ProviderStatus
from .usage_guard import get_usage_guard
from .local_ollama import LocalOllamaProvider
from .openai_compatible import OpenAICompatibleProvider
from .anthropic_provider import AnthropicProvider
logger = logging.getLogger(__name__)


def _metrics():
    from web.backend.api.metrics import PrometheusMetrics

    return PrometheusMetrics


class LLMRouter:
    """
    Routes LLM requests to the best available provider.
    
    Features:
    - Task-type routing (timeouts, model roles); primary backend is ``default_provider``
    - Automatic health checks every 60 seconds
    - Per-provider circuit breaker (CLOSED → OPEN → HALF_OPEN → CLOSED)
    - Failover when the default provider is unavailable or circuit is OPEN
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
        self._circuit = get_circuit_store()
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

            for name, pconf in providers_config.items():
                if pconf.get("enabled", False):
                    api_key_val = pconf.get("api_key")
                    has_env = pconf.get("api_key_env")
                    key_preview = f"{api_key_val[:8]}..." if api_key_val and len(api_key_val) > 8 else ("<SET>" if api_key_val else "<NOT SET>")
                    logger.debug(
                        f"Provider '{name}': api_key={key_preview}, api_key_env={has_env!r}"
                    )

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

    def _circuit_allows(self, name: str) -> bool:
        allowed, _reason = self._circuit.allow_request(name)
        return allowed

    def _record_circuit_success(self, name: str) -> None:
        prev = self._circuit.snapshot([name])["providers"].get(name, {})
        row = self._circuit.record_success(name)
        self._sync_circuit_metrics(name, row, prev)

    def _record_circuit_failure(self, name: str, error: str) -> None:
        prev = self._circuit.snapshot([name])["providers"].get(name, {})
        row = self._circuit.record_failure(name, error)
        m = _metrics()
        m.inc_circuit_failure(name)
        if row.get("state") == "open" and prev.get("state") != "open":
            m.inc_circuit_open(name)
        self._sync_circuit_metrics(name, row, prev)

    @staticmethod
    def _publish_llm_event(provider_name: str, task_type: str, config: GenerationConfig, duration_s: float) -> None:
        try:
            from core.events import LLMCallLogged, get_event_bus
            get_event_bus().publish_background(LLMCallLogged(
                provider=provider_name,
                model=config.model_override or "unknown",
                task_type=task_type,
                tokens_used=config.max_tokens,
                duration_ms=duration_s * 1000.0,
            ))
        except Exception:
            pass

    @staticmethod
    def _sync_circuit_metrics(name: str, row: dict, prev: dict) -> None:
        m = _metrics()
        m.set_circuit_state(name, str(row.get("state") or "closed"))
        recovery = row.get("last_recovery_duration_sec")
        if recovery is not None and prev.get("state") in ("open", "half_open"):
            m.observe_circuit_recovery(name, float(recovery))

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
            except asyncio.CancelledError as _suppressed_exc:
                log_suppressed(logger, "non-fatal (llm/router.py)", exc_info=_suppressed_exc)
        logger.info("Health check loop stopped")

    async def _health_check_loop(self, interval_sec: int):
        """Periodically check health of all providers."""
        while self._running:
            for name, provider in self.providers.items():
                try:
                    health = await provider.check_health()
                    is_healthy = health.status not in (ProviderStatus.UNAVAILABLE, ProviderStatus.UNKNOWN)
                    _metrics().set_provider_health(name, is_healthy)
                    logger.debug(f"Health check {name}: {health.status.value} ({health.latency_ms:.0f}ms)")
                except Exception as e:
                    _metrics().set_provider_health(name, False)
                    logger.error(f"Health check failed for {name}: {e}")
            try:
                snap = self.get_circuit_snapshot()
                sync_prometheus_from_snapshot(snap)
            except Exception as _suppressed_exc:
                log_suppressed(logger, "non-fatal (llm/router.py)", exc_info=_suppressed_exc)
            await asyncio.sleep(interval_sec)

    def get_circuit_snapshot(self) -> dict:
        """Public circuit breaker state for admin / metrics."""
        return self._circuit.snapshot(list(self.providers.keys()))

    async def generate(
        self,
        prompt: str,
        task_type: str = "code_generation",
        config: Optional[GenerationConfig] = None,
    ) -> str:
        """
        Generate a response using the best provider for the task type.
        """
        provider_name = self._select_provider(task_type)
        if not provider_name:
            raise RuntimeError(f"No available provider for task type: {task_type}")

        rule = self._get_rule(task_type)
        timeout = rule.get("timeout_sec", 30) if rule else 30

        if config is None:
            config = GenerationConfig(timeout_sec=timeout)
        config.task_type = task_type

        if rule and config.model_override is None:
            model_role = rule.get("model_role", "heavy")
            model_name = self._get_model_for_role(provider_name, model_role)
            if model_name:
                config.model_override = model_name

        config.model_role = self._resolve_model_role_for_config(provider_name, config, rule)

        # Dynamic model routing: downgrade when budget is tight/critical.
        config.model_override = get_cost_guard().resolve_model(
            provider_name, task_type, config.model_override,
            available_models=self._provider_configs.get(provider_name, {}).get("models"),
        )

        cache_key = self._build_cache_key(prompt, task_type, config)
        if self._cache_enabled:
            cached = self._cache_get(cache_key)
            if cached is not None:
                logger.debug("LLM cache hit for task_type=%s", task_type)
                return cached

        tried: set[str] = set()
        last_error: Optional[Exception] = None
        current = provider_name

        while current and current not in tried:
            tried.add(current)
            if not self._circuit_allows(current):
                logger.warning("Circuit OPEN for '%s', failing over task '%s'", current, task_type)
                last_error = CircuitOpenError(current)
                current = self._next_failover(task_type, current, tried)
                continue

            start_time = time.time()
            try:
                logger.info(
                    f"Routing to provider '{current}' for task '{task_type}'"
                    f" (model: {config.model_override or 'default'})"
                )
                self._apply_output_token_budget(current, config)
                result = await self._generate_via_provider(current, prompt, config)
                if self._cache_enabled:
                    self._cache_set(cache_key, result)
                duration = time.time() - start_time
                _metrics().inc_llm_request(current, "success")
                _metrics().observe_llm_duration(current, duration)
                self._record_circuit_success(current)
                self._publish_llm_event(current, task_type, config, duration)
                return result
            except Exception as e:
                duration = time.time() - start_time
                _metrics().inc_llm_request(current, "error")
                _metrics().observe_llm_duration(current, duration)
                self._record_circuit_failure(current, str(e))
                last_error = e
                logger.warning("Provider '%s' failed for task '%s': %s", current, task_type, e)
                current = self._next_failover(task_type, current, tried)

        if last_error:
            raise last_error
        raise RuntimeError(f"No available provider for task type: {task_type}")

    def _apply_output_token_budget(self, provider_name: str, config: GenerationConfig) -> None:
        """Clamp or raise ``max_tokens`` to the active model/provider ceiling."""
        from llm.token_budget import resolve_max_output_tokens_for_generation

        pconf = self._provider_configs.get(provider_name) or {}
        model = config.model_override
        if not model:
            role = config.model_role or "heavy"
            model = self._get_model_for_role(provider_name, role)
        config.max_tokens = resolve_max_output_tokens_for_generation(
            config.max_tokens,
            provider_name=provider_name,
            model=model,
            provider_config=pconf,
        )

    async def _generate_via_provider(
        self,
        provider_name: str,
        prompt: str,
        config: GenerationConfig,
    ) -> str:
        provider = self.providers[provider_name]
        allowed, reason = self._circuit.allow_request(provider_name)
        if not allowed:
            raise CircuitOpenError(provider_name, reason)
        await self._usage_guard.acquire()
        async with self._request_sem:
            await self._rate_limit_wait()
            return await provider.generate(prompt, config)

    def _next_failover(
        self,
        task_type: str,
        current: str,
        tried: set[str],
    ) -> Optional[str]:
        """After the current provider fails, only try an explicit routing fallback (if configured)."""
        fb = self._get_fallback(task_type, current)
        if not fb or fb in tried or fb == current:
            return None
        if fb not in self.providers:
            return None
        return fb

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
            oldest_key = min(self._response_cache, key=lambda k: self._response_cache[k][0])
            self._response_cache.pop(oldest_key, None)
        self._response_cache[key] = (time.time(), value)

    def _get_model_for_role(self, provider_name: str, role: str) -> Optional[str]:
        pconf = self._provider_configs.get(provider_name)
        if not pconf:
            return None
        models = pconf.get("models", {})
        if role == "light":
            return models.get("light") or models.get("heavy")
        return models.get("heavy") or models.get("light")

    def _infer_model_role(self, provider_name: str, active_model: Optional[str]) -> Optional[str]:
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
        """Stream a response from the best provider (with circuit-aware failover)."""
        provider_name = self._select_provider(task_type)
        if not provider_name:
            raise RuntimeError(f"No available provider for task type: {task_type}")

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

        # Dynamic model routing: downgrade when budget is tight/critical.
        config.model_override = get_cost_guard().resolve_model(
            provider_name, task_type, config.model_override,
            available_models=self._provider_configs.get(provider_name, {}).get("models"),
        )

        tried: set[str] = set()
        current = provider_name
        last_error: Optional[Exception] = None

        while current and current not in tried:
            tried.add(current)
            if not self._circuit_allows(current):
                last_error = CircuitOpenError(current)
                current = self._next_failover(task_type, current, tried)
                continue
            provider = self.providers[current]
            allowed, reason = self._circuit.allow_request(current)
            if not allowed:
                last_error = CircuitOpenError(current, reason)
                current = self._next_failover(task_type, current, tried)
                continue
            try:
                start_time = time.time()
                await self._usage_guard.acquire()
                async with self._request_sem:
                    await self._rate_limit_wait()
                    async for token in provider.stream(prompt, config):
                        yield token
                self._record_circuit_success(current)
                self._publish_llm_event(current, task_type, config, time.time() - start_time)
                return
            except Exception as e:
                self._record_circuit_failure(current, str(e))
                _metrics().inc_llm_request(current, "error")
                last_error = e
                current = self._next_failover(task_type, current, tried)

        if last_error:
            raise last_error
        raise RuntimeError(f"No available provider for task type: {task_type}")

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
        """True if provider is loaded, health is not UNAVAILABLE, and circuit allows traffic."""
        if not name or not isinstance(name, str):
            return False
        provider = self.providers.get(name)
        if provider is None:
            return False
        if provider.health.status == ProviderStatus.UNAVAILABLE:
            return False
        return self._circuit_allows(name)

    def _select_provider(self, task_type: str) -> Optional[str]:
        """Select provider for a task. Default provider is always tried first when configured."""
        if self.default_provider and self.default_provider in self.providers:
            return self.default_provider

        rule = self._get_rule(task_type)
        if not rule:
            return self._select_fastest_available()

        fallback = rule.get("fallback_provider")
        if fallback and fallback in self.providers:
            return fallback

        preferred = rule.get("preferred_provider", "auto")
        if preferred not in (None, "auto") and preferred in self.providers:
            return preferred

        return self._select_fastest_available()

    def _select_fastest_available(self) -> Optional[str]:
        available = [
            (name, p.health.latency_ms)
            for name, p in self.providers.items()
            if self._provider_is_available(name)
        ]
        if not available:
            return None
        
        if self.default_provider:
            for name, _ in available:
                if name == self.default_provider:
                    return name
        
        available.sort(key=lambda x: x[1])
        return available[0][0]

    def _get_rule(self, task_type: str) -> dict:
        for rule in self.routing_rules:
            if rule.get("task_type") == task_type:
                return rule
        return {}

    def _get_fallback(self, task_type: str, current_provider: str) -> Optional[str]:
        rule = self._get_rule(task_type)
        fallback = rule.get("fallback_provider")
        if fallback and fallback != current_provider:
            return fallback
        return None

    def get_provider_metrics(self) -> dict[str, dict]:
        return {name: p.get_metrics() for name, p in self.providers.items()}

    def get_available_providers(self) -> list[str]:
        return [
            name for name in self.providers
            if self._provider_is_available(name)
        ]

    async def reload_config(self):
        old_providers = self.providers
        self.providers = {}
        self._load_config()
        
        for provider in old_providers.values():
            try:
                if hasattr(provider, "close"):
                    await provider.close()
            except Exception as _suppressed_exc:
                log_suppressed(logger, "non-fatal (llm/router.py)", exc_info=_suppressed_exc)
        
        logger.info("Provider configuration reloaded")

    async def close(self):
        await self.stop_health_checks()
        for provider in self.providers.values():
            try:
                if hasattr(provider, "close"):
                    await provider.close()
            except Exception as _suppressed_exc:
                log_suppressed(logger, "non-fatal (llm/router.py)", exc_info=_suppressed_exc)
