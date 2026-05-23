"""Pydantic request/response models for the hub API."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    intent: str = Field("", max_length=4000)
    budget: Optional[float] = Field(None, ge=0, le=100_000)
    max_latency_ms: Optional[int] = Field(None, ge=0)
    min_trust: Optional[float] = Field(None, ge=0, le=1)
    hub: str = Field("any", max_length=256)
    limit: int = Field(20, ge=1, le=100)


class InvokeRequest(BaseModel):
    product_id: str = Field(..., min_length=2, max_length=80)
    capability_id: str = Field(..., min_length=2, max_length=80)
    source_hub: str = Field("local", max_length=256)
    input: dict[str, Any] = Field(default_factory=dict)


class AnnounceRequest(BaseModel):
    hub_url: str = Field(..., max_length=256)
    well_known_url: str = Field(..., max_length=256)
    capabilities_count: int = Field(0, ge=0)
    hub_name: str = Field("", max_length=128)
    signer_public_key: str = Field("", max_length=128)
    signature: Optional[dict[str, str]] = None


class ReputationEventsRequest(BaseModel):
    events: list[dict[str, Any]] = Field(..., min_length=1, max_length=100)


class ChannelOpenRequest(BaseModel):
    deposit_usd: float = Field(..., gt=0, le=10_000)
    token: Optional[str] = Field(None, max_length=16)
    chain: Optional[str] = Field(None, max_length=32)
    wallet: str = Field("", max_length=128)
    tx_hash: str = Field("", max_length=128)


class ChannelCloseRequest(BaseModel):
    channel_id: str = Field(..., min_length=8, max_length=64)
    settle_tx_hash: str = Field("", max_length=128)
    wallet: str = Field("", max_length=128)  # for authorization
