"""
Admin Dashboard API (split module).
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import re
import socket
import tempfile
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Optional
from urllib.parse import urlparse

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from fastapi.responses import FileResponse, StreamingResponse

from core.logging_utils import log_suppressed
from core.paths import (
    architecture_json_path,
    audit_log_dir,
    benchmark_alerts_path,
    benchmark_scorecard_path,
    benchmark_status_path,
    data_root as factory_data_root,
    director_decisions_path,
    director_reports_dir,
    discovery_dir,
    escalations_log_path,
    legacy_audit_log_path,
    llm_calls_log_path,
    logs_dir,
    market_research_path,
    marketing_content_path,
    metrics_history_path,
    model_providers_path,
    pipeline_db_path,
    pipeline_json_path,
    reports_dir,
    specification_path,
)
from web.backend.core.admin_roles import AdminRole, normalize_role, rank, require_admin_with_rbac
from finance_stats import compute_dashboard_revenue
from llm.bootstrap_providers import ensure_model_providers_file
from llm.factory_defaults import FACTORY_CONTEXT_WINDOW_DEFAULT, FACTORY_MAX_OUTPUT_TOKENS_HEAVY
from web.backend.services.catalog_hardening import harden_catalog_products
from web.backend.services.product_naming import resolve_product_name
from web.backend.services.policy_audit import sync_sqlite_from_pipeline_json
from web.backend.services.human_pipeline import (
    approve_post_devops_human_review,
    inject_human_admin_rework,
    reject_post_devops_human_review,
)
from web.backend.services.pipeline_failure_report import build_failure_report
from web.backend.services.pipeline_reopen import reopen_failed_product
from web.backend.services.pipeline_failed_notify import failure_reason_from_product
from web.backend.services.product_followup import (
    normalize_pipeline_followup,
    patch_admin_decisions,
    read_followup,
    validate_and_save,
)
from web.backend.services.pipeline_demo_replay import metrics_demo_replay_slice
from web.backend.services.dashboard_metrics_cache import (
    get_cached_dashboard,
    get_or_build_dashboard,
    set_cached_dashboard,
)
from web.backend.services.storefront_counts_cache import invalidate_storefront_categories_cache
from web.backend.services.product_economics import compute_roi_band, get_product_llm_costs
from web.backend.services.factory_floor import build_factory_floor_slice
from web.backend.services.cost_outcome_heatmap import build_cost_outcome_heatmap
from web.backend.services.product_pulse import build_product_pulse, build_product_pulses_for_metrics
from web.backend.services.storefront_pricing import (
    patch_admin_storefront_usdt,
    read_sales_inner_and_pricing,
    resolve_storefront_price_usdt,
)
from web.backend.api.products import count_showcase_listable_products, is_shipped_pipeline_product_state
from web.backend.core.http_errors import client_error_detail

from ._router import router
from .models import *
from .helpers import *
from .helpers import _circuit_breakers_metrics

@router.get("/providers")
async def get_providers():
    """Get LLM provider status with available models."""
    providers_file = model_providers_path()
    ensure_model_providers_file(providers_file)
    providers = {}
    default_provider = None
    
    if providers_file.exists():
        import yaml
        with open(providers_file, "r") as f:
            config = yaml.safe_load(f)
        
        default_provider = config.get("default_provider")
        
        for name, pconf in config.get("providers", {}).items():
            configured_models = pconf.get("models", {})
            active_heavy = configured_models.get("heavy", "")
            active_light = configured_models.get("light", "")
            base_url = pconf.get("base_url", "")
            api_key = _resolve_provider_api_key(pconf)

            available_models: list[str] = []
            if base_url and pconf.get("enabled", False):
                health_path = pconf.get("health_check_endpoint", "/v1/models")
                available_models = _provider_models_probe(
                    base_url=base_url,
                    health_path=health_path,
                    api_key=api_key,
                )

            if not available_models:
                available_models = list(set(filter(None, [active_heavy, active_light])))
            
            caps = pconf.get("capabilities") if isinstance(pconf.get("capabilities"), dict) else {}
            providers[name] = {
                "enabled": pconf.get("enabled", False),
                "type": pconf.get("provider_type", "unknown"),
                "base_url": base_url,
                "api_key_configured": bool(api_key),
                "api_key_env": pconf.get("api_key_env"),
                "models": {
                    "heavy": active_heavy,
                    "light": active_light,
                },
                "capabilities": {
                    "context_window": caps.get("context_window", FACTORY_CONTEXT_WINDOW_DEFAULT),
                    "context_window_light": caps.get(
                        "context_window_light",
                        caps.get("context_window", FACTORY_CONTEXT_WINDOW_DEFAULT),
                    ),
                    "max_tokens": caps.get("max_tokens", FACTORY_MAX_OUTPUT_TOKENS_HEAVY),
                    "supports_vision": bool(caps.get("supports_vision", False)),
                    "supports_streaming": bool(caps.get("supports_streaming", True)),
                },
                "priority": pconf.get("priority", 10),
                "health_check_endpoint": pconf.get("health_check_endpoint", "/v1/models"),
                "available_models": available_models,
                "status": "online" if available_models else ("disabled" if not pconf.get("enabled", False) else "offline"),
                "is_default": name == default_provider,
            }

    circuit_snap = _circuit_breakers_metrics(list(providers.keys()))
    for name, row in (circuit_snap.get("providers") or {}).items():
        if name in providers:
            providers[name]["circuit"] = row
            cstate = str(row.get("state") or "closed")
            if cstate in ("open", "half_open"):
                providers[name]["status"] = "circuit_" + cstate
            elif row.get("half_open_probe_in_flight"):
                providers[name]["status"] = "circuit_probe_busy"
        else:
            providers[name] = {
                "enabled": False,
                "type": "unknown",
                "base_url": "",
                "models": {"heavy": "", "light": ""},
                "available_models": [],
                "status": "disabled",
                "is_default": False,
                "circuit": row,
            }

    return {
        "providers": providers,
        "default_provider": default_provider,
        "circuit_breakers": circuit_snap,
    }


@router.get("/providers/circuits")
async def get_provider_circuits():
    """Circuit breaker snapshot for all known providers."""
    return _circuit_breakers_metrics()


@router.post("/providers/{provider_name}/circuit/open")
async def circuit_force_open(provider_name: str):
    from llm.circuit_breaker import get_circuit_store, sync_prometheus_from_snapshot

    store = get_circuit_store()
    row = store.force_open(provider_name, reason="admin_manual_open")
    snap = store.snapshot([provider_name])
    sync_prometheus_from_snapshot(snap)
    return {"status": "ok", "circuit": row}


@router.post("/providers/{provider_name}/circuit/close")
async def circuit_force_close(provider_name: str):
    from llm.circuit_breaker import get_circuit_store, sync_prometheus_from_snapshot

    store = get_circuit_store()
    row = store.force_closed(provider_name, reason="admin_manual_close")
    snap = store.snapshot([provider_name])
    sync_prometheus_from_snapshot(snap)
    return {"status": "ok", "circuit": row}


@router.post("/providers/{provider_name}/circuit/reset")
async def circuit_reset(provider_name: str):
    from llm.circuit_breaker import get_circuit_store, sync_prometheus_from_snapshot

    store = get_circuit_store()
    row = store.reset(provider_name, reason="admin_reset")
    snap = store.snapshot([provider_name])
    sync_prometheus_from_snapshot(snap)
    return {"status": "ok", "circuit": row}


@router.patch("/providers/{provider_name}")
async def update_provider_models(provider_name: str, request: Request):
    """Update model selection for a provider."""
    body = await request.json()
    providers_file = model_providers_path()
    
    if not providers_file.exists():
        raise HTTPException(status_code=404, detail="Providers config not found")
    
    import yaml
    with open(providers_file, "r") as f:
        config = yaml.safe_load(f)
    
    if provider_name not in config.get("providers", {}):
        raise HTTPException(status_code=404, detail=f"Provider '{provider_name}' not found")
    
    # Update models
    models = config["providers"][provider_name].get("models", {})
    if "heavy" in body:
        models["heavy"] = body["heavy"]
    if "light" in body:
        models["light"] = body["light"]
    config["providers"][provider_name]["models"] = models
    
    # Write back
    with open(providers_file, "w") as f:
        yaml.dump(config, f, default_flow_style=False)
    
    # Hot-reload - try to reload LLM router if it exists
    try:
        if hasattr(request.app.state, 'llm_router'):
            request.app.state.llm_router.reload_config()
    except Exception:
        log_suppressed(logger, "dashboard: non-fatal error", exc_info=True)
    
    return {"message": f"Provider '{provider_name}' updated", "models": models}


@router.post("/providers/{provider_name}/test")
async def test_provider(provider_name: str, request: Request):
    """Test a provider by sending a simple prompt to calibrate response quality."""
    providers_file = model_providers_path()
    
    if not providers_file.exists():
        raise HTTPException(status_code=404, detail="Providers config not found")
    
    import yaml
    import httpx
    
    with open(providers_file, "r") as f:
        config = yaml.safe_load(f)
    
    if provider_name not in config.get("providers", {}):
        raise HTTPException(status_code=404, detail=f"Provider '{provider_name}' not found")
    
    pconf = config["providers"][provider_name]
    body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    model_role = body.get("model_role", "heavy")
    custom_prompt = body.get("prompt", "")
    
    # Determine which model to use
    models = pconf.get("models", {})
    model_name = models.get(model_role, "")
    if not model_name:
        model_name = pconf.get("model", "")
    if not model_name and pconf.get("available_models"):
        model_name = pconf["available_models"][0]
    
    # Remove trailing /v1 suffix if present (OpenAI-compatible format)
    base_url = pconf.get("base_url", "").replace("/v1", "").rstrip("/")
    _assert_url_safe_for_outbound(base_url)
    api_key = pconf.get("api_key", "")
    chat_endpoint = f"{base_url}/v1/chat/completions"
    
    prompt = custom_prompt or "Reply with exactly three words describing your capabilities:"
    
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    
    payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 50,
        "temperature": 0.3,
    }
    
    start_time = time.time()
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(chat_endpoint, json=payload, headers=headers)
            latency_ms = round((time.time() - start_time) * 1000)
            
            if resp.status_code != 200:
                return {
                    "success": False,
                    "status_code": resp.status_code,
                    "latency_ms": latency_ms,
                    "model": model_name,
                    "error": resp.text[:500],
                }
            
            data = resp.json()
            response_text = ""
            if "choices" in data and len(data["choices"]) > 0:
                response_text = data["choices"][0].get("message", {}).get("content", "")
            
            return {
                "success": True,
                "status_code": resp.status_code,
                "latency_ms": latency_ms,
                "model": model_name,
                "response": response_text[:500],
                "prompt": prompt,
            }
    except Exception as e:
        latency_ms = round((time.time() - start_time) * 1000)
        return {
            "success": False,
            "latency_ms": latency_ms,
            "model": model_name,
            "error": str(e),
        }


# ── Provider CRUD Management ─────────────────────────────────────────────────

# ── SSRF guard for provider base_url ──────────────────────────────────────────
_SSRF_BLOCKED_HOSTS = {
    "localhost", "127.0.0.1", "0.0.0.0", "::1", "169.254.169.254",
    "metadata.google.internal", "metadata.aws.internal",
}
_SSRF_BLOCKED_PREFIXES = ("10.", "172.16.", "172.17.", "172.18.", "172.19.",
                          "172.20.", "172.21.", "172.22.", "172.23.", "172.24.",
                          "172.25.", "172.26.", "172.27.", "172.28.", "172.29.",
                          "172.30.", "172.31.", "192.168.")


def _assert_url_safe_for_outbound(url: str) -> None:
    """Raise HTTPException(400) when *url* targets a private / link-local host."""
    if not url:
        return
    try:
        parsed = urlparse(url)
    except Exception:
        raise HTTPException(status_code=400, detail=f"Invalid provider URL: {url!r}")
    host = (parsed.hostname or "").lower()
    if not host:
        return
    if host in _SSRF_BLOCKED_HOSTS:
        raise HTTPException(status_code=400, detail=f"Provider URL targets a blocked host: {host}")
    if host.startswith(_SSRF_BLOCKED_PREFIXES):
        raise HTTPException(status_code=400, detail=f"Provider URL targets a private network: {host}")
    # Resolve DNS and check the resolved IP as well (catches DNS rebinding to
    # private ranges when the hostname itself looks innocent).
    try:
        resolved = socket.getaddrinfo(host, None, socket.AF_INET)
        for _, _, _, _, sockaddr in resolved:
            ip = sockaddr[0]
            if ip in _SSRF_BLOCKED_HOSTS or ip.startswith(_SSRF_BLOCKED_PREFIXES):
                raise HTTPException(status_code=400, detail=f"Provider URL resolves to a private IP: {ip}")
    except HTTPException:
        raise
    except Exception:
        pass  # DNS failure — let the actual HTTP request fail naturally


def _resolve_provider_api_key(pconf: dict) -> str:
    """Direct yaml key or env var value (never returned to clients)."""
    direct = pconf.get("api_key")
    if direct:
        return str(direct).strip()
    env_name = pconf.get("api_key_env")
    if env_name:
        return str(os.environ.get(str(env_name), "") or "").strip()
    return ""


def _provider_models_probe(
    *,
    base_url: str,
    health_path: str,
    api_key: str,
) -> list[str]:
    """Fetch model ids from provider health endpoint (best effort)."""
    if not base_url:
        return []
    root = base_url.rstrip("/")
    if root.endswith("/v1"):
        root = root[:-3]
    url = f"{root}{health_path if health_path.startswith('/') else '/' + health_path}"
    # The guard lives HERE, not at the caller. `test_provider` validated its URL and this
    # probe did not, even though this one is the path that attaches the provider's API KEY as
    # a bearer header — and `_resolve_provider_api_key` is explicit that the key is "never
    # returned to clients", so the dashboard withholds it deliberately. Whatever populates
    # base_url (today: the operator's model_providers.yaml, not the API), a probe that ships a
    # withheld credential to an unvalidated address should not be reachable by a future
    # caller who simply forgets the check the sibling route remembered.
    try:
        _assert_url_safe_for_outbound(url)
    except HTTPException:
        logger.warning("provider probe refused: %r is not a safe outbound URL", root)
        return []
    headers: dict[str, str] = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    try:
        import httpx

        resp = httpx.get(url, headers=headers or None, timeout=3)
        if resp.status_code != 200:
            return []
        data = resp.json()
        if "data" in data:
            return [m["id"] for m in data["data"] if isinstance(m, dict) and m.get("id")]
        if "models" in data:
            return [m["name"] for m in data["models"] if isinstance(m, dict) and m.get("name")]
    except Exception:
        log_suppressed(logger, "dashboard: provider models probe failed", exc_info=True)
    return []


def _load_providers_config() -> dict:
    """Load providers config from YAML file."""
    providers_file = model_providers_path()
    ensure_model_providers_file(providers_file)
    if not providers_file.exists():
        return {"providers": {}, "routing_rules": []}
    import yaml
    with open(providers_file, "r") as f:
        return yaml.safe_load(f) or {"providers": {}, "routing_rules": []}


def _save_providers_config(config: dict):
    """Save providers config to YAML file."""
    import yaml
    providers_file = model_providers_path()
    providers_file.parent.mkdir(parents=True, exist_ok=True)
    with open(providers_file, "w") as f:
        yaml.dump(config, f, default_flow_style=False)


async def _reload_llm_router(request: Request):
    """Try to hot-reload the LLM router after config changes."""
    try:
        if hasattr(request.app.state, 'llm_router'):
            await request.app.state.llm_router.reload_config()
    except Exception:
        log_suppressed(logger, "dashboard: non-fatal error", exc_info=True)


DEFAULT_PROVIDER_TEMPLATE = {
    "enabled": True,
    "provider_type": "openai_compatible",
    "base_url": "",
    "api_key": None,
    "api_key_env": None,
    "models": {"heavy": "", "light": "", "vision": None},
    "capabilities": {
        "context_window": FACTORY_CONTEXT_WINDOW_DEFAULT,
        "context_window_light": FACTORY_CONTEXT_WINDOW_DEFAULT,
        "max_tokens": FACTORY_MAX_OUTPUT_TOKENS_HEAVY,
        "supports_vision": False,
        "supports_streaming": True,
    },
    "health_check_endpoint": "/v1/models",
    "priority": 10,
}


@router.post("/providers")
async def create_provider(request: Request):
    """Add a new LLM provider."""
    body = await request.json()
    config = _load_providers_config()
    
    name = body.get("name", "").strip().lower().replace(" ", "_")
    if not name:
        raise HTTPException(status_code=400, detail="Provider name is required")
    if name in config.get("providers", {}):
        raise HTTPException(status_code=409, detail=f"Provider '{name}' already exists")
    
    provider_config = dict(DEFAULT_PROVIDER_TEMPLATE)
    provider_config.update({
        k: v for k, v in body.items()
        if k != "name" and k in DEFAULT_PROVIDER_TEMPLATE
    })
    # Override specific fields from body
    if "base_url" in body:
        provider_config["base_url"] = body["base_url"]
    if "enabled" in body:
        provider_config["enabled"] = bool(body["enabled"])
    if "provider_type" in body:
        provider_config["provider_type"] = body["provider_type"]
    if "api_key" in body:
        provider_config["api_key"] = body["api_key"] or None
    if "api_key_env" in body:
        provider_config["api_key_env"] = body["api_key_env"] or None
    if "models" in body:
        provider_config["models"]["heavy"] = body["models"].get("heavy", "")
        provider_config["models"]["light"] = body["models"].get("light", "")
    if "capabilities" in body:
        caps = provider_config["capabilities"]
        for cap in ("context_window", "context_window_light", "max_tokens"):
            if cap in body["capabilities"]:
                caps[cap] = body["capabilities"][cap]
    if "priority" in body:
        provider_config["priority"] = int(body["priority"])
    if "health_check_endpoint" in body:
        provider_config["health_check_endpoint"] = body["health_check_endpoint"]
    
    config.setdefault("providers", {})[name] = provider_config
    _save_providers_config(config)
    await _reload_llm_router(request)
    
    return {"message": f"Provider '{name}' created", "name": name}


@router.put("/providers/{provider_name}")
async def update_provider(provider_name: str, request: Request):
    """Update full provider configuration."""
    body = await request.json()
    config = _load_providers_config()
    
    if provider_name not in config.get("providers", {}):
        raise HTTPException(status_code=404, detail=f"Provider '{provider_name}' not found")
    
    pconf = config["providers"][provider_name]
    
    # Update scalar fields — empty api_key means "keep existing" on update
    for key in ("base_url", "provider_type", "api_key_env", "health_check_endpoint"):
        if key in body:
            pconf[key] = body[key] if body[key] else None
    if "api_key" in body and body.get("api_key"):
        pconf["api_key"] = body["api_key"]
        pconf["api_key_env"] = None
    
    if "enabled" in body:
        pconf["enabled"] = bool(body["enabled"])
    if "priority" in body:
        pconf["priority"] = int(body["priority"])
    
    # Update models
    if "models" in body:
        pconf.setdefault("models", {})
        for role in ("heavy", "light", "vision"):
            if role in body["models"]:
                pconf["models"][role] = body["models"][role] if body["models"][role] else None
    
    # Update capabilities
    if "capabilities" in body:
        pconf.setdefault("capabilities", {})
        for cap in (
            "context_window",
            "context_window_light",
            "max_tokens",
            "supports_vision",
            "supports_streaming",
        ):
            if cap in body["capabilities"]:
                pconf["capabilities"][cap] = body["capabilities"][cap]
    
    _save_providers_config(config)
    await _reload_llm_router(request)
    
    return {"message": f"Provider '{provider_name}' updated", "provider": pconf}


@router.post("/providers/{provider_name}/set-default")
async def set_default_provider(provider_name: str, request: Request):
    """Set a provider as the default (primary) provider."""
    providers_file = model_providers_path()
    
    try:
        import yaml
        with open(providers_file, "r") as f:
            config = yaml.safe_load(f) or {}
        
        # Verify provider exists
        if provider_name not in config.get("providers", {}):
            return {"status": "error", "message": f"Provider '{provider_name}' not found"}
        
        # Set default
        config["default_provider"] = provider_name
        
        with open(providers_file, "w") as f:
            yaml.dump(config, f, default_flow_style=False)
        
        # Hot-reload LLM router
        await _reload_llm_router(request)
        
        return {"status": "ok", "default_provider": provider_name}
    except Exception as e:
        logger.error(f"Failed to set default provider: {e}")
        return {"status": "error", "message": str(e)}


@router.delete("/providers/{provider_name}")
async def delete_provider(provider_name: str, request: Request):
    """Remove a provider."""
    config = _load_providers_config()
    
    if provider_name not in config.get("providers", {}):
        raise HTTPException(status_code=404, detail=f"Provider '{provider_name}' not found")
    
    del config["providers"][provider_name]
    
    # Also clean up routing rules that reference this provider
    if "routing_rules" in config:
        for rule in config["routing_rules"]:
            if rule.get("preferred_provider") == provider_name:
                rule["preferred_provider"] = "auto"
            if rule.get("fallback_provider") == provider_name:
                rule["fallback_provider"] = None
    
    _save_providers_config(config)
    await _reload_llm_router(request)
    
    return {"message": f"Provider '{provider_name}' deleted"}


@router.patch("/providers/{provider_name}/toggle")
async def toggle_provider(provider_name: str, request: Request):
    """Enable or disable a provider."""
    body = await request.json()
    config = _load_providers_config()
    
    if provider_name not in config.get("providers", {}):
        raise HTTPException(status_code=404, detail=f"Provider '{provider_name}' not found")
    
    enabled = body.get("enabled", not config["providers"][provider_name].get("enabled", False))
    config["providers"][provider_name]["enabled"] = bool(enabled)
    
    _save_providers_config(config)
    await _reload_llm_router(request)
    
    return {
        "message": f"Provider '{provider_name}' {'enabled' if enabled else 'disabled'}",
        "enabled": enabled,
    }


@router.get("/providers/routing-rules")
async def get_routing_rules():
    """Get routing rules configuration."""
    config = _load_providers_config()
    return {"routing_rules": config.get("routing_rules", [])}


@router.put("/providers/routing-rules")
async def update_routing_rules(request: Request):
    """Update all routing rules."""
    body = await request.json()
    config = _load_providers_config()
    
    rules = body.get("routing_rules", [])
    # Validate rules
    valid_task_types = [
        "architecture_design", "code_generation", "pm_analysis",
        "qa_testing", "security_scan", "devops_setup",
        "marketing_copy", "sales_response", "evolution_analysis",
    ]
    for rule in rules:
        if rule.get("task_type") not in valid_task_types:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid task_type '{rule.get('task_type')}'. Must be one of: {valid_task_types}"
            )
        if "timeout_sec" in rule:
            rule["timeout_sec"] = max(10, int(rule["timeout_sec"]))
    
    config["routing_rules"] = rules
    _save_providers_config(config)
    await _reload_llm_router(request)
    
    return {"message": "Routing rules updated", "routing_rules": rules}


class PutProviderLlmPricingBody(BaseModel):
    """USD per 1M tokens for admin cost estimates when model id has no specific rate."""

    usd_per_mtok: float = Field(..., ge=0.0, le=1_000_000.0)


class PutLlmLimitsBody(BaseModel):
    """Router RPM + USD spend caps (persisted under ``llm.limits`` in platform YAML)
    plus ``llm.critical_escalation_enabled`` (cross-provider routing toggle)."""

    max_requests_per_minute: int = Field(0, ge=0, le=10_000)
    daily_cost_cap_usd: float = Field(0.0, ge=0.0, le=1_000_000.0)
    monthly_cost_cap_usd: float = Field(0.0, ge=0.0, le=1_000_000.0)
    pre_call_reserve_usd: float = Field(0.05, ge=0.0, le=100.0)
    critical_escalation_enabled: bool = False


@router.get("/llm-limits")
async def get_llm_limits():
    """Saved vs effective LLM router limits and current spend snapshot."""
    from core.llm_limits import admin_llm_limits_panel_dict

    return admin_llm_limits_panel_dict()


@router.put("/llm-limits")
async def put_llm_limits(body: PutLlmLimitsBody, request: Request):
    """Persist ``llm.limits`` to platform config (env ``AIFACTORY_LLM_*`` still wins at runtime)."""
    from core.llm_limits import admin_llm_limits_panel_dict, bump_llm_limits_cache_after_config_write

    cfg = getattr(request.app.state, "config", None)
    if cfg is None:
        raise HTTPException(status_code=503, detail="App config not available")

    limits = {
        "max_requests_per_minute": body.max_requests_per_minute,
        "daily_cost_cap_usd": body.daily_cost_cap_usd,
        "monthly_cost_cap_usd": body.monthly_cost_cap_usd,
        "pre_call_reserve_usd": body.pre_call_reserve_usd,
    }
    llm_block = cfg.get("llm")
    if not isinstance(llm_block, dict):
        llm_block = {}
    llm_block = dict(llm_block)
    llm_block["limits"] = limits
    # Routing toggle persisted as a top-level llm key (not under limits) — see
    # config/fragments/50-llm.yaml. Env AIFACTORY_LLM_CRITICAL_ESCALATION_ENABLED
    # still wins at runtime.
    llm_block["critical_escalation_enabled"] = bool(body.critical_escalation_enabled)
    cfg.set("llm", llm_block)
    bump_llm_limits_cache_after_config_write()
    return {"ok": True, **admin_llm_limits_panel_dict()}


@router.get("/llm-pricing")
async def get_llm_pricing():
    """Per-provider blended $/Mtok for LLM log estimates (YAML override > builtin > global default)."""
    from llm.pricing_estimate import (
        builtin_provider_fallback_usd_per_mtok,
        effective_provider_fallback_usd_per_mtok,
        yaml_override_usd_per_mtok_for_provider,
    )

    config = _load_providers_config()
    providers_out: dict[str, Any] = {}
    for name in sorted(config.get("providers", {}).keys()):
        eff, src = effective_provider_fallback_usd_per_mtok(name)
        providers_out[name] = {
            "effective_usd_per_mtok": eff,
            "source": src,
            "yaml_override_usd_per_mtok": yaml_override_usd_per_mtok_for_provider(name),
            "builtin_usd_per_mtok": builtin_provider_fallback_usd_per_mtok(name),
        }
    return {"providers": providers_out}


@router.put("/llm-pricing/providers/{provider_name}")
async def put_llm_pricing_provider(provider_name: str, body: PutProviderLlmPricingBody):
    """Set YAML override for provider-tier cost estimate (writes ``data/config/llm_pricing.yaml``)."""
    config = _load_providers_config()
    if provider_name not in config.get("providers", {}):
        raise HTTPException(status_code=404, detail=f"Provider '{provider_name}' not found")

    from llm.pricing_estimate import write_llm_pricing_provider_rate

    try:
        write_llm_pricing_provider_rate(provider_name, body.usd_per_mtok)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=client_error_detail(e)) from e
    return {"ok": True, "provider": provider_name, "usd_per_mtok": body.usd_per_mtok}


@router.delete("/llm-pricing/providers/{provider_name}")
async def delete_llm_pricing_provider_override(provider_name: str):
    """Remove YAML override so built-in / global default applies again."""
    config = _load_providers_config()
    if provider_name not in config.get("providers", {}):
        raise HTTPException(status_code=404, detail=f"Provider '{provider_name}' not found")

    from llm.pricing_estimate import write_llm_pricing_provider_rate

    try:
        write_llm_pricing_provider_rate(provider_name, None)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=client_error_detail(e)) from e
    return {"ok": True, "provider": provider_name, "cleared": True}

