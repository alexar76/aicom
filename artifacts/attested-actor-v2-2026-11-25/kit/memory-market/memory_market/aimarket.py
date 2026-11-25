from __future__ import annotations

import asyncio
import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

from .signing import ProviderSigner


@dataclass(frozen=True)
class Capability:
    product_id: str
    capability_id: str
    name: str
    description: str
    price_usd: float
    category: str
    input_schema: dict
    output_schema: dict


OBJECT_OUTPUT = {"type": "object", "additionalProperties": True}
CAPABILITIES = (
    Capability("memory-write", "memory.write@v1", "Write Memory", "Create a portable Memory Unit and request provenance attestation.", 0.012, "memory/storage", {"type": "object", "required": ["title", "content"], "properties": {"title": {"type": "string"}, "content": {"type": "string"}, "tags": {"type": "array"}, "visibility": {"type": "string"}}}, OBJECT_OUTPUT),
    Capability("memory-read", "memory.read@v1", "Read Memory", "Read public or caller-authorized memory with trust and lineage state.", 0.006, "memory/retrieval", {"type": "object", "required": ["memory_id"], "properties": {"memory_id": {"type": "string"}}}, OBJECT_OUTPUT),
    Capability("memory-search", "memory.search@v1", "Search Memory", "Search discoverable Memory Units by title, content and tags; memories the Truth Layer rejected are left out unless truth asks for them.", 0.004, "memory/retrieval", {"type": "object", "properties": {"query": {"type": "string"}, "limit": {"type": "integer"}, "truth": {"type": "string", "description": "Truth Layer statuses to include, comma-separated (unverified, supported, contested, rejected), or any. Default: all but rejected."}}}, OBJECT_OUTPUT),
    Capability("memory-share", "memory.share@v1", "Share Memory", "Grant another agent access when the invoking actor owns the Memory Unit.", 0.008, "memory/access", {"type": "object", "required": ["memory_id", "grantee_id"], "properties": {"memory_id": {"type": "string"}, "grantee_id": {"type": "string"}}}, OBJECT_OUTPUT),
    Capability("memory-score", "memory.score@v1", "Score Memory", "Record one bounded quality score per invoking actor.", 0.003, "memory/reputation", {"type": "object", "required": ["memory_id", "score"], "properties": {"memory_id": {"type": "string"}, "score": {"type": "integer", "minimum": 1, "maximum": 5}}}, OBJECT_OUTPUT),
)
BY_CAPABILITY = {item.capability_id: item for item in CAPABILITIES}


def manifest(capability: Capability, signer: ProviderSigner) -> dict:
    base = os.getenv("AIMARKET_INVOKE_BASE", "http://memory-market:8810").rstrip("/")
    publisher = os.getenv("AIMARKET_PUBLISHER_ID", "memory-market")
    return {
        "product_id": capability.product_id, "capability_id": capability.capability_id,
        "name": capability.name, "version": "v1", "description": capability.description,
        "invoke_url": f"{base}/capabilities/{capability.product_id}/{capability.capability_id}/invoke",
        "price_per_call_usd": capability.price_usd, "publisher": publisher,
        "publisher_id": publisher, "provider_pubkey": signer.public_key,
        "input_schema": capability.input_schema, "output_schema": capability.output_schema,
        "category": capability.category, "p50_latency_ms": 45, "success_rate_30d": 0.99,
    }


def signed_protocol_manifest(signer: ProviderSigner) -> dict:
    payload = {
        "protocol_version": "v2",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "base_url": os.getenv("AIMARKET_INVOKE_BASE", "http://memory-market:8810").rstrip("/"),
        "products_count": len(CAPABILITIES), "capabilities_count": len(CAPABILITIES),
        "tools": [manifest(item, signer) for item in CAPABILITIES],
    }
    tools_hash = hashlib.sha256(json.dumps(payload["tools"], sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    by_hub_hash = hashlib.sha256(b"{}").hexdigest()
    canonical = f"capabilities_count:{len(CAPABILITIES)}|generated_at:{payload['generated_at']}|protocol_version:v2|tools_hash:{tools_hash}|by_hub_hash:{by_hub_hash}"
    payload["signature"] = signer.sign(canonical)
    return payload


async def register(signer: ProviderSigner) -> int:
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
                response = await client.post(f"{hub}/ai-market/v2/supply/register", json=manifest(capability, signer), headers={"Authorization": f"Bearer {token}"})
                response.raise_for_status()
                published += 1
            except httpx.HTTPError:
                continue
        return published
