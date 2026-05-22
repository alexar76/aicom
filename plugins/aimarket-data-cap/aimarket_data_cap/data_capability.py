"""Data-as-Capability (#7)

Paid upload of private corpus → corpus becomes paid RAG-capability.
Example: "notary company uploads 50k court decisions → legal.us-cases.search@v1,
$0.05 per query, 70% revenue to owner."

Doubles TAM — sell compute AND data. Snowflake-level monetization.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class DataCapability:
    """A capability backed by user-uploaded private data."""

    capability_id: str
    product_id: str
    owner_address: str  # Who uploaded the data
    data_hash: str  # SHA-256 of the corpus
    data_size_bytes: int
    document_count: int
    description: str
    query_price_usd: float  # Per-query price
    owner_revenue_share_pct: float = 0.70  # 70% to data owner
    total_queries: int = 0
    total_revenue_usd: float = 0.0
    owner_earned_usd: float = 0.0
    created_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    active: bool = True
    tags: list[str] = field(default_factory=list)
    access_policy: dict[str, Any] = field(default_factory=lambda: {
        "allowed_consumers": ["*"],  # or specific addresses
        "rate_limit_per_minute": 60,
        "max_query_length": 4000,
    })

    @property
    def avg_revenue_per_query(self) -> float:
        return self.total_revenue_usd / max(self.total_queries, 1)

    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural language query against the private corpus",
                    "maxLength": self.access_policy.get("max_query_length", 4000),
                },
                "max_results": {"type": "integer", "default": 10, "maximum": 100},
            },
            "required": ["query"],
        }

    def output_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "results": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "snippet": {"type": "string"},
                            "relevance_score": {"type": "number"},
                            "document_id": {"type": "string"},
                        },
                    },
                },
                "total_matches": {"type": "integer"},
            },
        }


class DataCapabilityRegistry:
    """Registry for data-backed capabilities.

    Data owners upload private corpora, set pricing, earn 70% of query revenue.
    Platform takes 30% for infrastructure.
    """

    def __init__(self, platform_fee_pct: float = 0.30):
        self.platform_fee_pct = platform_fee_pct
        self._capabilities: dict[str, DataCapability] = {}

    def register(
        self,
        owner_address: str,
        description: str,
        data_size_bytes: int,
        document_count: int,
        query_price_usd: float = 0.05,
        data_hash: str | None = None,
        tags: list[str] | None = None,
        owner_revenue_share_pct: float = 0.70,
    ) -> DataCapability:
        """Register a new data-backed capability."""
        cap_id = f"data.{hashlib.sha256(f'{owner_address}:{description}:{time.time()}'.encode()).hexdigest()[:10]}"
        product_id = f"data-prod-{cap_id[:8]}"

        if data_hash is None:
            data_hash = hashlib.sha256(f"{owner_address}:{time.time()}".encode()).hexdigest()

        dc = DataCapability(
            capability_id=f"{cap_id}@v1",
            product_id=product_id,
            owner_address=owner_address,
            data_hash=data_hash,
            data_size_bytes=data_size_bytes,
            document_count=document_count,
            description=description,
            query_price_usd=query_price_usd,
            owner_revenue_share_pct=owner_revenue_share_pct,
            tags=tags or [],
        )
        self._capabilities[dc.capability_id] = dc
        return dc

    def query(self, capability_id: str, query_text: str, max_results: int = 10) -> dict[str, Any]:
        """Execute a paid query against a data capability.

        Returns results + revenue split between owner and platform.
        """
        dc = self._capabilities.get(capability_id)
        if not dc:
            return {"error": "data capability not found"}
        if not dc.active:
            return {"error": "data capability is inactive"}

        # Simulate search against private corpus
        results = [
            {
                "snippet": f"Match for '{query_text[:50]}...' in {dc.description[:80]}",
                "relevance_score": 0.95,
                "document_id": f"doc_{i}",
            }
            for i in range(min(max_results, 3))
        ]

        # Revenue split
        owner_share = dc.query_price_usd * dc.owner_revenue_share_pct
        platform_share = dc.query_price_usd - owner_share

        dc.total_queries += 1
        dc.total_revenue_usd += dc.query_price_usd
        dc.owner_earned_usd += owner_share

        return {
            "capability_id": capability_id,
            "results": results,
            "total_matches": dc.document_count,
            "price_usd": dc.query_price_usd,
            "revenue_split": {
                "owner_usd": round(owner_share, 6),
                "platform_usd": round(platform_share, 6),
                "owner_share_pct": dc.owner_revenue_share_pct,
            },
            "data_owner": dc.owner_address[:8] + "...",  # Partially anonymized
            "data_info": {
                "documents": dc.document_count,
                "size_mb": round(dc.data_size_bytes / 1_000_000, 2),
            },
        }

    def get_owner_revenue(self, owner_address: str) -> dict[str, Any]:
        """Get total revenue earned by a data owner."""
        total = 0.0
        caps = []
        for c in self._capabilities.values():
            if c.owner_address == owner_address:
                total += c.owner_earned_usd
                caps.append({
                    "capability_id": c.capability_id,
                    "queries": c.total_queries,
                    "earned_usd": round(c.owner_earned_usd, 4),
                    "description": c.description,
                })

        return {
            "owner_address": owner_address[:8] + "...",
            "total_earned_usd": round(total, 4),
            "capabilities": caps,
            "active_capabilities": sum(1 for c in caps if self._capabilities.get(c["capability_id"]) and self._capabilities[c["capability_id"]].active),
        }

    def list_available(self) -> list[dict[str, Any]]:
        """List all active data capabilities."""
        return [
            {
                "capability_id": dc.capability_id,
                "description": dc.description,
                "query_price_usd": dc.query_price_usd,
                "documents": dc.document_count,
                "tags": dc.tags,
                "owner_share_pct": dc.owner_revenue_share_pct,
            }
            for dc in self._capabilities.values()
            if dc.active
        ]

    def stats(self) -> dict[str, Any]:
        total_queries = sum(c.total_queries for c in self._capabilities.values())
        total_revenue = sum(c.total_revenue_usd for c in self._capabilities.values())
        total_owner_earned = sum(c.owner_earned_usd for c in self._capabilities.values())

        return {
            "total_data_capabilities": len(self._capabilities),
            "active": sum(1 for c in self._capabilities.values() if c.active),
            "total_queries": total_queries,
            "total_revenue_usd": round(total_revenue, 4),
            "total_owner_earned_usd": round(total_owner_earned, 4),
            "platform_earned_usd": round(total_revenue - total_owner_earned, 4),
            "total_documents": sum(c.document_count for c in self._capabilities.values()),
            "total_data_size_gb": round(sum(c.data_size_bytes for c in self._capabilities.values()) / 1e9, 2),
        }
