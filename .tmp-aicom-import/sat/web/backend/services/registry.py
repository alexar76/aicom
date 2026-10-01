"""
Service domain registry — explicit module boundaries for the web/backend/services monolith.

New services should register here under one domain. Prefer importing sibling modules
only within the same domain; cross-domain calls go through documented facades
(e.g. ``sandbox_runtime``, ``product_economics``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class ServiceDomain:
    id: str
    title: str
    description: str
    modules: tuple[str, ...]
    facade: str | None = None


def _mods(*names: str) -> tuple[str, ...]:
    return names


SERVICE_DOMAINS: tuple[ServiceDomain, ...] = (
    ServiceDomain(
        "pipeline",
        "Pipeline & catalog",
        "Product lifecycle, queue, director, replay, methodology.",
        _mods(
            "pipeline_ops",
            "pipeline_replay_timeline",
            "pipeline_demo_replay",
            "pipeline_catalog",
            "director_integration",
            "methodology",
            "prompt_improvement_loop",
        ),
    ),
    ServiceDomain(
        "sandbox",
        "Sandbox preview",
        "Storefront/admin preview, static rewrite, compose, FastAPI subprocess.",
        _mods(
            "sandbox_runtime",
            "sandbox_preview_api",
            "sandbox_preview_env",
            "sandbox_compose_preview",
            "sandbox_preview_network",
            "sandbox_docker",
            "sandbox_static_entry",
            "sandbox_static_rewrite",
            "sandbox_spec_landing",
        ),
        facade="web.backend.services.sandbox_runtime",
    ),
    ServiceDomain(
        "storefront",
        "Storefront & commerce",
        "Public listing, pricing, payments, customer portal.",
        _mods("storefront_pricing", "storefront_counts_cache", "product_showcase"),
    ),
    ServiceDomain(
        "economics",
        "LLM economics",
        "Per-product cost aggregation and ROI helpers.",
        _mods("product_economics", "cost_outcome_heatmap", "pricing_estimate"),
        facade="web.backend.services.product_economics",
    ),
    ServiceDomain(
        "platform",
        "Platform admin",
        "Auth guards, backups, settings, users, quality gates.",
        _mods(
            "public_demo_guard",
            "factory_backup",
            "factory_backup_scheduler",
            "admin_users_store",
            "quality_constitution",
            "benchmark_gate",
        ),
    ),
    ServiceDomain(
        "observability",
        "Telemetry & security ops",
        "Firewall, audit, browser E2E artifacts.",
        _mods("browser_preview_e2e", "release_cockpit"),
    ),
)


def list_service_domains() -> list[dict[str, str | list[str]]]:
    return [
        {
            "id": d.id,
            "title": d.title,
            "description": d.description,
            "modules": list(d.modules),
            "facade": d.facade or "",
        }
        for d in SERVICE_DOMAINS
    ]


def module_to_domain() -> dict[str, str]:
    out: dict[str, str] = {}
    for d in SERVICE_DOMAINS:
        for m in d.modules:
            out[m] = d.id
    return out
