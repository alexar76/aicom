"""AIMarket discovery manifests for SKOPOS supply side."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .capabilities import CAPABILITIES, CapabilitySpec
from .config import EconomyConfig
from .signing import get_signer


def _tool_entry(cfg: EconomyConfig, spec: CapabilitySpec) -> dict[str, Any]:
    base = cfg.public_base_url.rstrip("/")
    return {
        "name": spec.capability_id,
        "description": spec.description,
        "input_schema": spec.input_schema,
        "output_schema": spec.output_schema,
        "price_per_call_usd": spec.price_per_call_usd,
        "p50_latency_ms": spec.p50_latency_ms,
        "product_id": cfg.product_id,
        "capability_id": spec.capability_id,
        "source_hub": base,
        "source_hub_name": "SKOPOS",
        "invoke_url": cfg.invoke_url,
    }


def build_well_known(cfg: EconomyConfig) -> dict[str, Any]:
    base = cfg.public_base_url.rstrip("/")
    signer = get_signer()
    return {
        "name": "SKOPOS Fleet Intelligence",
        "description": "Self-hosted nginx analytics & security posture — billable fleet telemetry for AI agents.",
        "protocol_versions": ["v2"],
        "protocol_version": "v2",
        "hub_name": "SKOPOS",
        "hub_url": base,
        "manifest_url": f"{base}/ai-market/v2/manifest",
        "mcp_endpoint": cfg.invoke_url,
        "capabilities_count": len(CAPABILITIES),
        "signer_public_key": signer.public_key_b64,
        "prices_url": f"{base}/ai-market/v2/prices",
        "federation": {"role": "provider"},
        "categories": ["observability", "security", "fleet"],
        "ecosystem": {"product": "skopos.fleet", "related": ["aimarket-hub", "momus"]},
    }


def build_v2_manifest(cfg: EconomyConfig) -> dict[str, Any]:
    base = cfg.public_base_url.rstrip("/")
    signer = get_signer()
    tools = [_tool_entry(cfg, spec) for spec in CAPABILITIES]
    body: dict[str, Any] = {
        "protocol_version": "v2",
        "generated_at": datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z"),
        "base_url": base,
        "products_count": 1,
        "capabilities_count": len(tools),
        "total_capabilities": len(tools),
        "local_capabilities": len(tools),
        "federated_capabilities": 0,
        "hubs_indexed": 1,
        "tools": tools,
        "by_hub": {base: {"name": "SKOPOS", "capabilities": len(tools)}},
    }
    body["signature"] = signer.sign_manifest(body)
    return body


def build_prices(cfg: EconomyConfig) -> dict[str, Any]:
    prices = [
        {
            "product_id": cfg.product_id,
            "capability_id": spec.capability_id,
            "price_per_call_usd": spec.price_per_call_usd,
            "currency": "USD",
        }
        for spec in CAPABILITIES
    ]
    return {
        "protocol_version": "v2",
        "currency": "USD",
        "count": len(prices),
        "prices": prices,
    }


def build_supply_manifest(cfg: EconomyConfig) -> list[dict[str, Any]]:
    """One registration payload per capability (Hub supply/register)."""
    out: list[dict[str, Any]] = []
    for spec in CAPABILITIES:
        out.append(
            {
                "product_id": cfg.product_id,
                "capability_id": spec.capability_id,
                "name": spec.name,
                "description": spec.description,
                "invoke_url": cfg.invoke_url,
                "price_per_call_usd": spec.price_per_call_usd,
                "publisher_id": cfg.publisher_id,
                "input_schema": spec.input_schema,
                "output_schema": spec.output_schema,
            }
        )
    return out
