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
import os
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from core.logging_utils import log_suppressed
from core.paths import model_providers_path
from core.throughput_limits import effective_llm_max_parallel_requests, effective_llm_min_interval_sec

from .anthropic_provider import AnthropicProvider
from .bootstrap_providers import ensure_model_providers_file
from .circuit_breaker import CircuitOpenError, get_circuit_store, sync_prometheus_from_snapshot
from .cost_guard import get_cost_guard
from .local_ollama import LocalOllamaProvider
from .openai_compatible import OpenAICompatibleProvider
from .provider import GenerationConfig, LLMProvider, ProviderStatus
from .usage_guard import get_usage_guard

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from web.backend.api.metrics import PrometheusMetrics


def _metrics() -> type[PrometheusMetrics]:
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
        self.routing_rules: list[dict[str, Any]] = []
        self.default_provider: str | None = None
        self._provider_configs: dict[str, dict[str, Any]] = {}
        self._health_check_task: asyncio.Task[None] | None = None
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

    def _load_config(self) -> None:
        """Load provider configuration from YAML file."""
        try:
            config_path = Path(self.config_path)
            logger.debug(f"LLMRouter loading config from: {self.config_path} (exists: {config_path.exists()})")
            ensure_model_providers_file(config_path)

            with open(self.config_path) as f:
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

                provider: LLMProvider
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

    def _publish_llm_event(
        self,
        provider_name: str,
        task_type: str,
        config: GenerationConfig,
        duration_s: float,
    ) -> None:
        # M2: prefer actual tokens from the provider's last call. `_last_call_tokens`
        # is populated by `_update_metrics` inside each provider's generate/stream.
        # Falls back to `config.max_tokens` (upper bound) for providers that don't
        # report usage or when the call failed before metrics were updated.
        actual_tokens: int | None = None
        try:
            provider = self.providers.get(provider_name)
            if provider is not None:
                last = getattr(provider, "_last_call_tokens", 0)
                if last and last > 0:
                    actual_tokens = int(last)
        except Exception:
            actual_tokens = None
        try:
            from core.events import LLMCallLogged, get_event_bus
            get_event_bus().publish_background(LLMCallLogged(
                provider=provider_name,
                model=config.model_override or "unknown",
                task_type=task_type,
                tokens_used=actual_tokens if actual_tokens is not None else config.max_tokens,
                duration_ms=duration_s * 1000.0,
            ))
        except Exception:
            pass

    @staticmethod
    def _sync_circuit_metrics(name: str, row: dict[str, Any], prev: dict[str, Any]) -> None:
        m = _metrics()
        m.set_circuit_state(name, str(row.get("state") or "closed"))
        recovery = row.get("last_recovery_duration_sec")
        if recovery is not None and prev.get("state") in ("open", "half_open"):
            m.observe_circuit_recovery(name, float(recovery))

    async def start_health_checks(self, interval_sec: int = 60) -> None:
        """Start periodic health checks for all providers."""
        self._running = True
        self._health_check_task = asyncio.create_task(
            self._health_check_loop(interval_sec)
        )
        logger.info("Health check loop started")

    async def stop_health_checks(self) -> None:
        """Stop periodic health checks."""
        self._running = False
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError as _suppressed_exc:
                log_suppressed(logger, "non-fatal (llm/router.py)", exc_info=_suppressed_exc)
        logger.info("Health check loop stopped")

    async def _health_check_loop(self, interval_sec: int) -> None:
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

    def get_circuit_snapshot(self) -> dict[str, Any]:
        """Public circuit breaker state for admin / metrics."""
        return self._circuit.snapshot(list(self.providers.keys()))

    async def generate(
        self,
        prompt: str,
        task_type: str = "code_generation",
        config: GenerationConfig | None = None,
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

        from core.pipeline_cost_guard import assert_product_within_budget

        pid = getattr(config, "product_id", None)
        if pid:
            assert_product_within_budget(str(pid))

        # A caller-pinned model (explicit config.model_override, e.g. the
        # gate-failing repair model) is honored on every provider. When the
        # router itself picks the model, it must be re-bound per provider on
        # failover — a model id is provider-specific, so carrying the default
        # provider's model onto an escalation target would 404.
        caller_override = config.model_override

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
        last_error: Exception | None = None
        current: str | None = provider_name

        while current and current not in tried:
            tried.add(current)
            if not self._circuit_allows(current):
                logger.warning("Circuit OPEN for '%s', failing over task '%s'", current, task_type)
                last_error = CircuitOpenError(current)
                current = self._next_failover(task_type, current, tried)
                continue

            self._rebind_model_for_provider(current, config, task_type, caller_override)

            start_time = time.time()
            try:
                from core.tracing import span

                # OTel `gen_ai.*` semantic conventions — LangSmith / Phoenix /
                # Helicone recognise spans tagged this way as LLM calls and
                # render them with model / tokens / cost rather than as opaque
                # "llm.generate" rows. Legacy `llm.*` / `product.id` aliases
                # are kept so existing dashboards keep working.
                model_name = config.model_override or "default"
                span_attrs = {
                    "gen_ai.system": current,
                    "gen_ai.operation.name": "chat",
                    "gen_ai.request.model": model_name,
                    "gen_ai.request.temperature": float(getattr(config, "temperature", 0.0) or 0.0),
                    "gen_ai.request.max_tokens": int(getattr(config, "max_tokens", 0) or 0),
                    "llm.provider": current,
                    "llm.task_type": task_type,
                    "ai.task_type": task_type,
                }
                if pid:
                    span_attrs["aifactory.product_id"] = str(pid)
                    span_attrs["product.id"] = str(pid)
                with span("llm.generate", attributes=span_attrs) as llm_span:
                    logger.info(
                        f"Routing to provider '{current}' for task '{task_type}'"
                        f" (model: {config.model_override or 'default'})"
                    )
                    self._apply_output_token_budget(current, config)
                    result = await self._generate_via_provider(current, prompt, config)
                    # Best-effort token accounting — providers here return raw
                    # strings, so we use the chars/4 fallback OTel recommends
                    # when no tokenizer is wired. Replace per-provider once a
                    # real usage payload is available.
                    if llm_span is not None:
                        try:
                            in_tokens = max(1, len(prompt) // 4)
                            out_tokens = max(1, len(result) // 4)
                            llm_span.set_attribute("gen_ai.usage.input_tokens", in_tokens)
                            llm_span.set_attribute("gen_ai.usage.output_tokens", out_tokens)
                            llm_span.set_attribute(
                                "gen_ai.usage.total_tokens", in_tokens + out_tokens
                            )
                            llm_span.set_attribute("gen_ai.response.model", model_name)
                        except Exception:
                            pass
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

    def _rebind_model_for_provider(
        self,
        provider_name: str,
        config: GenerationConfig,
        task_type: str,
        caller_override: str | None,
    ) -> None:
        """Bind ``config.model_override`` to ``provider_name``'s role-appropriate
        model (re-applying budget downgrades). Honors a caller-pinned model.

        Idempotent for the originally selected provider; on cross-provider
        failover it replaces the previous provider's (now invalid) model id.
        """
        if caller_override:
            config.model_override = caller_override
            return
        role = config.model_role or "heavy"
        model = self._get_model_for_role(provider_name, role)
        config.model_override = get_cost_guard().resolve_model(
            provider_name, task_type, model,
            available_models=self._provider_configs.get(provider_name, {}).get("models"),
        )

    def _apply_output_token_budget(self, provider_name: str, config: GenerationConfig) -> None:
        """Clamp or raise ``max_tokens`` to the active model/provider ceiling.

        A per-task soft cap is then applied on top so stages that emit small
        JSON documents don't carry the full 128k heavy budget (bounds runaway
        generation; quality-neutral because caps sit above healthy outputs).
        """
        from llm.token_budget import (
            resolve_max_output_tokens_for_generation,
            task_output_soft_cap,
        )

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
        soft_cap = task_output_soft_cap(config.task_type)
        if soft_cap and soft_cap > 0:
            config.max_tokens = min(config.max_tokens, soft_cap)

    async def _generate_via_provider(
        self,
        provider_name: str,
        prompt: str,
        config: GenerationConfig,
    ) -> str:
        provider = self.providers[provider_name]
        # The circuit gate is applied exactly once per attempt by the caller loop
        # (_circuit_allows). Re-checking here would call allow_request() a SECOND
        # time, re-consuming the one-shot HALF_OPEN probe → "half_open_probe_busy"
        # → the provider could never recover through generate() and stayed OPEN.
        await self._usage_guard.acquire()
        async with self._request_sem:
            await self._rate_limit_wait()
            return await provider.generate(prompt, config)

    def _next_failover(
        self,
        task_type: str,
        current: str,
        tried: set[str],
    ) -> str | None:
        """Pick the next provider after ``current`` failed.

        1. An explicit routing ``fallback_provider`` (if configured & loaded).
        2. Otherwise, for CRITICAL tasks with cross-provider escalation enabled,
           the strongest other provider that has credentials (opt-in).
        """
        fb = self._get_fallback(task_type, current)
        if fb and fb not in tried and fb != current and fb in self.providers:
            return fb
        return self._critical_escalation_target(task_type, tried)

    def _provider_has_credentials(self, name: str) -> bool:
        """True if provider ``name`` has an API key wired (or needs none).

        Local providers (Ollama) require no key. For everyone else we require a
        literal ``api_key`` or a populated ``api_key_env`` — so escalation never
        targets a keyless cloud provider the user hasn't actually configured.
        """
        pconf = self._provider_configs.get(name) or {}
        ptype = str(pconf.get("provider_type", "openai_compatible"))
        if ptype in ("local_ollama", "ollama"):
            return True
        if pconf.get("api_key"):
            return True
        env = pconf.get("api_key_env")
        return bool(env and os.environ.get(env))

    def _critical_escalation_target(self, task_type: str, tried: set[str]) -> str | None:
        """Strongest untried, healthy, credentialed provider for a critical task.

        Returns None unless (a) ``llm.critical_escalation_enabled`` is on,
        (b) ``task_type`` is critical, and (c) some other provider both has
        credentials and is currently available. "Strongest" = highest provider
        ``priority`` in config (operator-declared ranking).
        """
        from core.throughput_limits import effective_llm_critical_escalation_enabled
        from llm.cost_guard import is_critical_task

        if not effective_llm_critical_escalation_enabled():
            return None
        if not is_critical_task(task_type):
            return None

        candidates: list[tuple[str, int]] = []
        for name in self.providers:
            if name in tried:
                continue
            if not self._provider_is_available(name):
                continue
            if not self._provider_has_credentials(name):
                continue
            prio = self._provider_configs.get(name, {}).get("priority", 0) or 0
            candidates.append((name, int(prio)))
        if not candidates:
            return None
        candidates.sort(key=lambda x: x[1], reverse=True)
        target = candidates[0][0]
        logger.warning(
            "Critical-task escalation: task '%s' failing over across providers to '%s' (priority=%s)",
            task_type, target, candidates[0][1],
        )
        return target

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

    def _cache_get(self, key: str) -> str | None:
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

    def _get_model_for_role(self, provider_name: str, role: str) -> str | None:
        pconf = self._provider_configs.get(provider_name)
        if not pconf:
            return None
        models: dict[str, str] = pconf.get("models", {})
        if role == "light":
            return models.get("light") or models.get("heavy")
        return models.get("heavy") or models.get("light")

    def _infer_model_role(self, provider_name: str, active_model: str | None) -> str | None:
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
        rule: dict[str, object] | None,
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
        config: GenerationConfig | None = None,
    ) -> AsyncGenerator[str, None]:
        """Stream a response from the best provider (with circuit-aware failover)."""
        provider_name = self._select_provider(task_type)
        if not provider_name:
            raise RuntimeError(f"No available provider for task type: {task_type}")

        rule = self._get_rule(task_type)
        timeout = rule.get("timeout_sec", 30) if rule else 30

        if config is None:
            config = GenerationConfig(timeout_sec=timeout, stream=True)
        config.task_type = task_type

        caller_override = config.model_override

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
        current: str | None = provider_name
        last_error: Exception | None = None

        while current and current not in tried:
            tried.add(current)
            if not self._circuit_allows(current):
                last_error = CircuitOpenError(current)
                current = self._next_failover(task_type, current, tried)
                continue
            provider = self.providers[current]
            # Single circuit gate per attempt: _circuit_allows() above already
            # consumed any HALF_OPEN probe. A second allow_request() here would
            # re-consume it ("half_open_probe_busy") and prevent recovery.
            self._rebind_model_for_provider(current, config, task_type, caller_override)
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

    def _provider_is_available(self, name: str | None) -> bool:
        """True if provider is loaded, health is not UNAVAILABLE, and circuit allows traffic."""
        if not name or not isinstance(name, str):
            return False
        provider = self.providers.get(name)
        if provider is None:
            return False
        if provider.health.status == ProviderStatus.UNAVAILABLE:
            return False
        return self._circuit_allows(name)

    def _select_provider(self, task_type: str) -> str | None:
        """Select provider for a task. Default provider is always tried first when configured."""
        if self.default_provider and self.default_provider in self.providers:
            return self.default_provider

        rule = self._get_rule(task_type)
        if not rule:
            return self._select_fastest_available()

        fallback: str | None = rule.get("fallback_provider")
        if fallback and fallback in self.providers:
            return fallback

        preferred: str | None = rule.get("preferred_provider", "auto")
        if preferred not in (None, "auto") and preferred in self.providers:
            return preferred

        return self._select_fastest_available()

    def _select_fastest_available(self) -> str | None:
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

    def _get_rule(self, task_type: str) -> dict[str, Any]:
        for rule in self.routing_rules:
            if rule.get("task_type") == task_type:
                return rule
        return {}

    def _get_fallback(self, task_type: str, current_provider: str) -> str | None:
        rule = self._get_rule(task_type)
        fallback: str | None = rule.get("fallback_provider")
        if fallback and fallback != current_provider:
            return fallback
        return None

    def get_provider_metrics(self) -> dict[str, dict[str, Any]]:
        return {name: p.get_metrics() for name, p in self.providers.items()}

    def get_available_providers(self) -> list[str]:
        return [
            name for name in self.providers
            if self._provider_is_available(name)
        ]

    async def reload_config(self) -> None:
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

    async def close(self) -> None:
        await self.stop_health_checks()
        for provider in self.providers.values():
            try:
                if hasattr(provider, "close"):
                    await provider.close()
            except Exception as _suppressed_exc:
                log_suppressed(logger, "non-fatal (llm/router.py)", exc_info=_suppressed_exc)
