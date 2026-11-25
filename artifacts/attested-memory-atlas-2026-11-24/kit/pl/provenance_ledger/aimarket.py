from __future__ import annotations

import asyncio
import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

from .crypto import Signer


@dataclass(frozen=True)
class Capability:
    product_id: str
    capability_id: str
    name: str
    description: str
    price_usd: float
    category: str
    input_schema: dict


CAPABILITIES = (
    Capability(
        "memory-attest", "memory.attest@v1", "Attest Memory",
        "Append a signed, hash-linked provenance event for a Memory Unit.",
        0.014, "provenance/attestation",
        {"type": "object", "required": ["memory_id", "event_type", "content_hash"], "properties": {
            "memory_id": {"type": "string"}, "event_type": {"type": "string"},
            "content_hash": {"type": "string"}, "source_refs": {"type": "array"},
            "parent_memory_ids": {"type": "array"}, "metadata": {"type": "object"},
        }},
    ),
    Capability(
        "lineage-get", "lineage.get@v1", "Read Lineage",
        "Return the ordered receipt chain and current root for a Memory Unit.",
        0.007, "provenance/lineage",
        {"type": "object", "required": ["memory_id"], "properties": {"memory_id": {"type": "string"}}},
    ),
    Capability(
        "receipt-verify", "receipt.verify@v1", "Verify Receipt",
        "Verify event hash, chain link, Ed25519 signature and required ML-DSA-65 signature.",
        0.005, "provenance/verification",
        {"type": "object", "required": ["receipt_id"], "properties": {"receipt_id": {"type": "string"}}},
    ),
)
BY_CAPABILITY = {item.capability_id: item for item in CAPABILITIES}


def manifest(capability: Capability, signer: Signer) -> dict:
    base = os.getenv("AIMARKET_INVOKE_BASE", "http://provenance-ledger:8812").rstrip("/")
    publisher = os.getenv("AIMARKET_PUBLISHER_ID", "provenance-ledger")
    return {
        "product_id": capability.product_id, "capability_id": capability.capability_id,
        "name": capability.name, "version": "v1", "description": capability.description,
        "invoke_url": f"{base}/capabilities/{capability.product_id}/{capability.capability_id}/invoke",
        "price_per_call_usd": capability.price_usd, "publisher": publisher,
        "publisher_id": publisher, "provider_pubkey": signer.public_key,
        "input_schema": capability.input_schema,
        "output_schema": {"type": "object", "additionalProperties": True},
        "category": capability.category, "p50_latency_ms": 25, "success_rate_30d": 0.995,
    }


def signed_protocol_manifest(signer: Signer) -> dict:
    payload = {
        "protocol_version": "v2",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "base_url": os.getenv("AIMARKET_INVOKE_BASE", "http://provenance-ledger:8812").rstrip("/"),
        "products_count": len(CAPABILITIES), "capabilities_count": len(CAPABILITIES),
        "tools": [manifest(item, signer) for item in CAPABILITIES],
    }
    tools_hash = hashlib.sha256(json.dumps(payload["tools"], sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    by_hub_hash = hashlib.sha256(b"{}").hexdigest()
    canonical = f"capabilities_count:{len(CAPABILITIES)}|generated_at:{payload['generated_at']}|protocol_version:v2|tools_hash:{tools_hash}|by_hub_hash:{by_hub_hash}"
    payload["signature"] = signer.sign_block(canonical)
    return payload


async def register(signer: Signer) -> int:
    hub = os.getenv("AIMARKET_HUB_URL", "").rstrip("/")
    token = os.getenv("AIMARKET_PUBLISHER_TOKEN", "")
    if not hub or not token:
        return 0
    async with httpx.AsyncClient(timeout=5) as client:
        for attempt in range(18):
            try:
                if (await client.get(f"{hub}/ai-market/v2/health")).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            await asyncio.sleep(min(2 + attempt, 8))
        else:
            return 0
        published = 0
        for capability in CAPABILITIES:
            try:
                response = await client.post(
                    f"{hub}/ai-market/v2/supply/register", json=manifest(capability, signer),
                    headers={"Authorization": f"Bearer {token}"},
                )
                response.raise_for_status()
                published += 1
            except httpx.HTTPError:
                continue
        return published
