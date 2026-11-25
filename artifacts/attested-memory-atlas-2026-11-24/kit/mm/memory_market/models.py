from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


Visibility = Literal["private", "shared", "public", "paid"]
TruthStatus = Literal["unverified", "supported", "contested", "rejected"]


class MemoryCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=200_000)
    tags: list[str] = Field(default_factory=list, max_length=20)
    visibility: Visibility = "private"
    price_usdc: str | None = None
    source_refs: list[str] = Field(default_factory=list, max_length=50)
    parent_memory_ids: list[str] = Field(default_factory=list, max_length=50)

    @field_validator("tags")
    @classmethod
    def clean_tags(cls, tags: list[str]) -> list[str]:
        cleaned = []
        for tag in tags:
            value = tag.strip().casefold()
            if not value or len(value) > 48:
                raise ValueError("tags must contain 1-48 characters")
            if value not in cleaned:
                cleaned.append(value)
        return cleaned

    @field_validator("source_refs", "parent_memory_ids")
    @classmethod
    def bound_reference_values(cls, values: list[str]) -> list[str]:
        if any(not isinstance(value, str) or not value.strip() or len(value) > 2048 for value in values):
            raise ValueError("reference values must be non-empty strings of at most 2048 characters")
        return values

    @model_validator(mode="after")
    def paid_price(self) -> "MemoryCreate":
        if self.visibility == "paid":
            if self.price_usdc is None:
                raise ValueError("paid memory requires price_usdc")
            try:
                price = Decimal(self.price_usdc)
            except InvalidOperation as error:
                raise ValueError("price_usdc must be decimal") from error
            if (not price.is_finite() or price <= 0 or price > Decimal("1000000")
                    or price.as_tuple().exponent < -6):
                raise ValueError("price_usdc must be finite, positive, <= 1000000, with at most 6 decimals")
        elif self.price_usdc is not None:
            raise ValueError("price_usdc is only valid for paid memory")
        return self


class TruthState(BaseModel):
    status: TruthStatus = "unverified"
    confidence: float = 0
    evidence_pack_id: str | None = None


class ProvenanceState(BaseModel):
    status: Literal["unattested", "attested"] = "unattested"
    receipt_id: str | None = None
    lineage_root: str | None = None


class MemorySummary(BaseModel):
    id: str
    title: str
    owner_id: str
    content_hash: str
    tags: list[str]
    visibility: Visibility
    price_usdc: str | None
    truth: TruthState
    provenance: ProvenanceState
    average_score: float | None
    score_count: int
    created_at: str
    updated_at: str


class MemoryUnit(MemorySummary):
    content: str
    source_refs: list[str]
    parent_memory_ids: list[str]


class Catalog(BaseModel):
    items: list[MemorySummary]
    total: int
    query: str


class GrantCreate(BaseModel):
    grantee_id: str = Field(min_length=1, max_length=120)


class Grant(BaseModel):
    id: str
    memory_id: str
    grantee_id: str
    granted_by: str
    created_at: str


class ScoreCreate(BaseModel):
    score: int = Field(ge=1, le=5)


class ScoreResult(BaseModel):
    memory_id: str
    average_score: float
    score_count: int


class Evidence(BaseModel):
    source_uri: str = Field(min_length=1, max_length=2048)
    excerpt_hash: str = Field(min_length=71, max_length=71)
    stance: Literal["supports", "refutes", "context"]
    quality: float = Field(default=0.5, ge=0, le=1)
    retrieved_at: str | None = None

    @field_validator("retrieved_at")
    @classmethod
    def bound_timestamp(cls, value: str | None) -> str | None:
        if value is not None and len(value) > 80:
            raise ValueError("retrieved_at is too long")
        return value


class VerifyMemory(BaseModel):
    claim: str = Field(min_length=3, max_length=20_000)
    evidence: list[Evidence] = Field(default_factory=list, max_length=100)


class HubStats(BaseModel):
    discoverable_memories: int
    attested_memories: int
    verified_memories: int
    paid_memories: int
    payment_enabled: bool


class PaymentOrderCreate(BaseModel):
    memory_id: str = Field(min_length=5, max_length=80)
    grantee_id: str = Field(min_length=1, max_length=120)

    @field_validator("memory_id", "grantee_id")
    @classmethod
    def clean_payment_identity(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("payment identity fields cannot be blank")
        return cleaned


class PaymentConfirm(BaseModel):
    tx_hash: str = Field(min_length=66, max_length=66)


class PaymentOrder(BaseModel):
    order_id: str
    number: str
    state: Literal["pending", "expired", "confirmed"]
    settled: bool
    memory_id: str
    memory_title: str
    grantee_id: str
    price_usdc: str
    amount_usdc: str
    amount_raw: str
    chain: str
    chain_id: int
    token: str
    token_address: str
    decimals: int
    pay_to: str
    eip681: str
    created_at: str
    expires_at: str
    required_confirmations: int
    late: bool
    tx_hash: str | None
    payer: str | None
    explorer_address: str
    explorer_tx: str | None
    grant_id: str | None
