"""Pydantic request/response models for the hub API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator

from aimarket_hub.models import normalize_purpose


class SearchRequest(BaseModel):
    intent: str = Field("", max_length=4000)
    budget: float | None = Field(None, ge=0, le=100_000)
    max_latency_ms: int | None = Field(None, ge=0)
    min_trust: float | None = Field(None, ge=0, le=1)
    hub: str = Field("any", max_length=256)
    limit: int = Field(20, ge=1, le=100)


class VerifyBlock(BaseModel):
    """Buyer opt-in for Pay-on-Verified settlement (escrow hold until a Metis verdict).

    The buyer supplies the task `intent` the verdict is judged against; money moves
    only after Metis scores the delivered output. `wait` holds the HTTP response
    until the verdict (bounded by `wait_timeout_s`); default is async — the invoke
    returns immediately with a pending envelope resolvable at
    GET /ai-market/v2/verification/{nonce}.
    """

    requested: bool = True
    intent: str = Field("", max_length=20_000)
    mode: str = Field("auto", pattern="^(auto|fast|thinking|council|agent)$")
    wait: bool = False
    wait_timeout_s: float = Field(300, ge=1, le=300)


class AppealRequest(BaseModel):
    """Body of POST /ai-market/v2/verification/{nonce}/appeal (the body is optional).

    The appellant is not named here — it follows from the verdict (a pass is appealed by
    the buyer, a fail by the seller) and is proven by the credential presented. The
    statement is shown to the appeal court as untrusted text and is never served back by
    the public verification lookup.
    """

    statement: str = Field("", max_length=4_000)


class SubcontractBlock(BaseModel):
    """A pass-through allowance for the providers of this call (mandates.md §6.2).

    The root buyer sets aside ``allowance_usd`` of its own funding that the provider may
    spend on subcontractors while serving the call, down to ``max_depth`` levels. What they
    do not spend is released when the call returns.
    """

    allowance_usd: float = Field(..., gt=0, le=1_000)
    max_depth: int = Field(1, ge=1, le=3)


class InvokeRequest(BaseModel):
    product_id: str = Field(..., min_length=2, max_length=80)
    capability_id: str = Field(..., min_length=2, max_length=80)
    source_hub: str = Field("local", max_length=256)
    input: dict[str, Any] = Field(default_factory=dict)
    # Buyer-side compare-and-set for the quoted price. Search and invoke are two
    # requests; without this ceiling a listing repriced between them could reserve
    # and capture more than the caller selected. Checked before any hold or provider
    # execution on both local and federated paths.
    max_price_usd: float | None = Field(None, ge=0, le=1_000_000)
    verify: VerifyBlock | None = None
    # EIP-712 DebitAuthorization for a channel funded through AIMarketEscrow. A body
    # field rather than a header because it is a structured, signed object (seven fields
    # plus a 65-byte signature) that the SDKs already build as a typed value — the
    # X-Payment-Channel headers carry an identity, this carries a claim.
    #
    # The buyer picks its receiptId and signs it BEFORE the invoke exists; the hub then
    # uses that same id as the ledger's receipt nonce, so the on-chain replay key
    # (usedReceipts) and the off-chain one are the same string. Required only on paid
    # invokes against an escrow-backed channel; ignored everywhere else.
    payment_authorization: dict[str, Any] | None = None
    subcontract: SubcontractBlock | None = None
    # The caller's public label for why it made the call ("feed", "home-weather"), shown on
    # /stats/live. A short slug or nothing: anything else is dropped, never a 422.
    purpose: str = ""

    @field_validator("purpose", mode="before")
    @classmethod
    def _purpose_slug(cls, value: Any) -> str:
        return normalize_purpose(value)


class ReceiptVerifyRequest(BaseModel):
    """A receipt to verify against this Hub's pinned live signing identities.

    The endpoint intentionally accepts no caller-supplied public key: allowing one
    would turn verification into a self-signed assertion. The bounded HTTP body and
    the additional serialized-size check in the handler keep the public verifier from
    becoming a JSON amplification surface.
    """

    receipt: dict[str, Any]


class LotteryEntitlementRequest(BaseModel):
    """An authenticated Hub subject binds its stable identity to its EVM wallet."""

    agent_id: str = Field(..., min_length=1, max_length=160)
    wallet: str = Field(..., min_length=42, max_length=42)


class StudioNode(BaseModel):
    """One hop of a studio blueprint — the executor's node shape, validated here too."""
    id: str = Field("", max_length=64)
    product_id: str = Field(..., min_length=2, max_length=80)
    capability_id: str = Field(..., min_length=2, max_length=80)
    input: dict[str, Any] = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list, max_length=16)
    # Names the upstream node whose result is fed to this hop. One parent, by design:
    # the executor's `input_from` is a single node id, so a fan-in graph has to say
    # which branch carries the data instead of getting whichever hop finished last.
    input_from: str | None = Field(None, max_length=64)
    # Which peer sells this row. Dropped silently by an earlier version of this model,
    # which is how every federated hop reached the executor with no idea where to look and
    # came back 400 — a field a forwarder does not declare is a field it deletes.
    source_hub: str | None = Field(None, max_length=200)


class StudioRunRequest(BaseModel):
    """A blueprint submitted through the hub's same-origin run path.

    Capped at the executor's own limit rather than trusting it to reject: this route
    exists so a browser can reach the executor at all, and a forwarder that passes on
    whatever it is handed is one bug away from being a general-purpose poster.
    """
    nodes: list[StudioNode] = Field(..., min_length=1, max_length=16)
    channel_id: str | None = Field(None, max_length=64)
    continue_on_error: bool = Field(False, strict=True)


class IpoRequest(BaseModel):
    """Float a product as an ACEX CapShares listing (Agent IPO)."""
    product_id: str = Field(..., min_length=2, max_length=80)
    name: str | None = Field(None, max_length=80)
    symbol: str | None = Field(None, max_length=12)
    max_supply: int | None = Field(None, ge=1, le=10_000_000_000)
    treasury: str | None = Field(None, max_length=128)
    audit_score_bps: int | None = Field(None, ge=0, le=10_000)
    revenue_share_bps: int | None = Field(None, ge=0, le=10_000)


class AuditSyncRequest(BaseModel):
    """Sync on-chain or external auditor coverage into the hub ledger."""
    auditor: str = Field(..., min_length=2, max_length=128)
    cover_usd: float = Field(..., gt=0, le=10_000_000)
    score_bps: int = Field(..., ge=7000, le=10_000)
    phase: str = Field("insuring", max_length=16)


class AuditClaimRequest(BaseModel):
    auditor: str = Field(..., min_length=2, max_length=128)


class AnnounceRequest(BaseModel):
    hub_url: str = Field(..., max_length=256)
    # Optional: the discovery document lives at a well-known path by definition, so
    # requiring callers to repeat it turned the open announce into a form only an
    # insider could fill in correctly. Defaults to <hub_url>/.well-known/ai-market.json.
    well_known_url: str = Field("", max_length=256)
    capabilities_count: int = Field(0, ge=0)
    hub_name: str = Field("", max_length=128)
    signer_public_key: str = Field("", max_length=128)
    signature: dict[str, str] | None = None


class ReputationEventsRequest(BaseModel):
    events: list[dict[str, Any]] = Field(..., min_length=1, max_length=100)


class PermissionViolationRequest(BaseModel):
    """One signed observation that a listed capability broke its own declaration.

    The declaration is NOT taken from this body — the Hub reads what the publisher
    actually declared at admission, so a reporter cannot choose which claim it is
    contradicting.
    """

    product_id: str = Field(min_length=1, max_length=128)
    capability_id: str = Field(min_length=1, max_length=192)
    permission: str = Field(min_length=1, max_length=64)
    reporter_pubkey: str = Field(min_length=1, max_length=128)
    signature: str = Field(min_length=1, max_length=256)
    consumer_id: str = Field(default="", max_length=128)


class ChannelOpenRequest(BaseModel):
    deposit_usd: float = Field(..., gt=0, le=10_000)
    token: str | None = Field(None, max_length=16)
    chain: str | None = Field(None, max_length=32)
    wallet: str = Field("", max_length=128)
    tx_hash: str = Field("", max_length=128)
    # EIP-191 signature by the PAYING wallet over channels.payer_proof_challenge().
    # channels.open() refuses an on-chain-verified deposit without it (unless the
    # operator sets AIMARKET_CHANNEL_ALLOW_UNPROVEN_PAYER=1), so a transport that
    # cannot carry it makes every production channel open fail.
    payer_signature: str = Field("", max_length=256)
    # Opt-in escrow funding: an AIMarketEscrow channelId the depositor already funded on
    # chain. When supplied (and the bridge is enabled) it REPLACES tx_hash/payer_signature
    # entirely — the contract records the depositor, so there is nothing for a bystander
    # to quote and no EIP-191 proof to collect. Ignored, and the transfer path unchanged,
    # on every hub that has not enabled the bridge.
    escrow_channel_id: str = Field("", max_length=66)


class ChannelCloseRequest(BaseModel):
    channel_id: str = Field(..., min_length=8, max_length=64)
    settle_tx_hash: str = Field("", max_length=128)
    wallet: str = Field("", max_length=128)  # for authorization
