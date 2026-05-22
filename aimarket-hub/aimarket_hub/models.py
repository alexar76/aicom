"""Data models for hub entities — capabilities, peers, stats."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class Capability:
    """A single AI capability indexed by the hub."""

    capability_id: str
    product_id: str
    name: str
    version: str = "v1"
    description: str = ""
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    price_per_call_usd: float = 0.35
    p50_latency_ms: int = 3000
    success_rate_30d: float = 0.97
    source_hub: str = "local"
    source_hub_name: str = ""
    routed_price_usd: Optional[float] = None
    routing_fee_bps: int = 0
    trust_score: float = 0.0
    agent: str = ""
    prompt_template: str = ""

    def tool_name(self) -> str:
        return f"{self.product_id}.{self.name}@{self.version}"


@dataclass
class Peer:
    """A known peer hub."""

    url: str
    name: str
    capabilities_count: int = 0
    last_crawl: str = ""
    trust_score: float = 0.0
    well_known_url: str = ""
    manifest_url: str = ""
    public_key: str = ""
    depth: int = 0  # BFS depth from seed
    discoverer: str = ""  # Which hub told us about this one


@dataclass
class InvocationStat:
    """A recorded invocation for stats/live feed."""

    capability_id: str
    product_id: str
    source_hub: str
    price_usd: float
    latency_ms: int
    success: bool
    timestamp: str
    consumer_hub: str = "local"


@dataclass
class ReputationEvent:
    """A signed reputation attestation."""

    event_type: str  # invocation_success, invocation_failure, bond_update
    provider_hub: str
    capability_id: Optional[str]
    timestamp: str
    price_usd: float
    latency_ms: int
    consumer_hub: str
    signature: str
