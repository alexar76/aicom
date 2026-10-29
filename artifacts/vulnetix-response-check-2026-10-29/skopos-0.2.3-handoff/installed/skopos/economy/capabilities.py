"""Billable SKOPOS capabilities for AIMarket Hub."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CapabilitySpec:
    capability_id: str
    name: str
    description: str
    price_per_call_usd: float
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    p50_latency_ms: int = 800


CAPABILITIES: tuple[CapabilitySpec, ...] = (
    CapabilitySpec(
        capability_id="skopos.fleet.status@v1",
        name="Fleet status",
        # Every description here names WHOSE fleet. They report on the operator's own
        # servers and take no input about the caller's — a buyer reading "fleet security
        # score" beside a price reasonably assumed it was theirs. Analysing your own
        # infrastructure means running SKOPOS yourself; the rules it scans with are sold
        # separately as security-rules.sec-feed@v1, which keeps your logs on your disk.
        description=(
            "Live heartbeat of the operator's own SKOPOS-monitored fleet (modelmarket.dev): "
            "servers monitored, request count, security score. Reports on OUR servers, not "
            "yours — a working sample of SKOPOS output."
        ),
        price_per_call_usd=0.01,
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        output_schema={
            "type": "object",
            "properties": {
                "ok": {"type": "boolean"},
                "servers_monitored": {"type": "integer"},
                "requests_total": {"type": "integer"},
                "security_score": {"type": "integer"},
            },
        },
        p50_latency_ms=120,
    ),
    CapabilitySpec(
        capability_id="skopos.security.posture@v1",
        name="Security posture",
        description=(
            "Security score, grade, top alerts and expert remarks for the operator's own "
            "fleet (modelmarket.dev). Reports on OUR servers — the optional server_name "
            "filters within that fleet, it does not accept yours."
        ),
        price_per_call_usd=0.08,
        input_schema={
            "type": "object",
            "properties": {
                "server_name": {"type": "string", "description": "Optional single-server filter"},
            },
        },
        output_schema={
            "type": "object",
            "properties": {
                "fleet_score": {"type": "integer"},
                "grade": {"type": "string"},
                "critical_count": {"type": "integer"},
                "high_count": {"type": "integer"},
                "alerts": {"type": "array"},
                "remarks": {"type": "array", "items": {"type": "string"}},
            },
        },
        p50_latency_ms=600,
    ),
    CapabilitySpec(
        capability_id="skopos.traffic.summary@v1",
        name="Traffic summary",
        description=(
            "Recent nginx/Apache traffic aggregates — requests, unique IPs, top segment, "
            "error rate — for the operator's own fleet (modelmarket.dev). Reports on OUR "
            "traffic; it does not ingest logs you supply."
        ),
        price_per_call_usd=0.05,
        input_schema={
            "type": "object",
            "properties": {
                "hours": {"type": "integer", "minimum": 1, "maximum": 168, "default": 24},
            },
        },
        output_schema={
            "type": "object",
            "properties": {
                "requests": {"type": "integer"},
                "unique_ips": {"type": "integer"},
                "top_segment": {"type": ["string", "null"]},
                "error_rate_pct": {"type": "number"},
            },
        },
        p50_latency_ms=400,
    ),
    CapabilitySpec(
        capability_id="skopos.briefing@v1",
        name="Fleet health briefing",
        description=(
            "Human-language health summary of the operator's own fleet (modelmarket.dev) — "
            "rules-based, LLM-written when a key is configured. Describes OUR fleet, not yours."
        ),
        price_per_call_usd=0.15,
        input_schema={
            "type": "object",
            "properties": {
                "language": {"type": "string", "enum": ["en", "ru", "es"], "default": "en"},
            },
        },
        output_schema={
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "mood": {"type": "string"},
                "fleet_score": {"type": "integer"},
                "grade": {"type": "string"},
                "source": {"type": "string"},
            },
        },
        p50_latency_ms=2500,
    ),
)

CAPABILITY_BY_ID: dict[str, CapabilitySpec] = {c.capability_id: c for c in CAPABILITIES}
