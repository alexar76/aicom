from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class AttestationCreate(BaseModel):
    memory_id: str = Field(min_length=5, max_length=80)
    event_type: Literal["created", "derived", "verified", "shared", "revoked", "updated"]
    content_hash: str
    actor_id: str = Field(min_length=1, max_length=120)
    source_refs: list[str] = Field(default_factory=list, max_length=50)
    parent_memory_ids: list[str] = Field(default_factory=list, max_length=50)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("content_hash")
    @classmethod
    def valid_hash(cls, value: str) -> str:
        prefix, separator, digest = value.partition(":")
        if separator != ":" or prefix != "sha256" or len(digest) != 64:
            raise ValueError("content_hash must be sha256:<64 lowercase hex chars>")
        if any(char not in "0123456789abcdef" for char in digest):
            raise ValueError("content_hash must use lowercase hexadecimal")
        return value

    @field_validator("source_refs", "parent_memory_ids")
    @classmethod
    def bound_references(cls, values: list[str]) -> list[str]:
        if any(not value.strip() or len(value) > 2048 for value in values):
            raise ValueError("reference values must be non-empty and at most 2048 characters")
        return values

    @field_validator("metadata")
    @classmethod
    def bound_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        import json
        if len(json.dumps(value, ensure_ascii=False, default=str)) > 65536:
            raise ValueError("metadata exceeds 64 KiB")
        return value


class Receipt(BaseModel):
    id: str
    memory_id: str
    event_type: str
    content_hash: str
    actor_id: str
    source_refs: list[str]
    parent_memory_ids: list[str]
    metadata: dict[str, Any]
    previous_root: str
    event_hash: str
    chain_root: str
    signature: str
    public_key: str
    pq_algorithm: str | None = None
    pq_public_key: str | None = None
    pq_signature: str | None = None
    created_at: str


class Lineage(BaseModel):
    memory_id: str
    chain_root: str | None
    receipts: list[Receipt]


class VerifyRequest(BaseModel):
    receipt_id: str


class VerifyResult(BaseModel):
    receipt_id: str
    valid: bool
    checks: dict[str, bool]
