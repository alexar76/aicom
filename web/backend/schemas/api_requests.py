"""Validated request bodies for public and admin HTTP APIs."""

from __future__ import annotations

import re
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

_DELIVERY = Literal["marketing_landing", "full_software"]
_LOCALE_RE = r"^[a-z]{2}(-[A-Za-z]{2,8})?$"
_PRODUCT_ID_RE = re.compile(r"^prod-[a-z0-9]{8,64}$", re.I)
_EVM_TX_RE = re.compile(r"^0x[a-fA-F0-9]{64}$")
_CHAIN = Literal["base", "arbitrum", "ethereum", "solana"]
_PAYMENT_TOKEN = Literal["USDT", "USDC", "ETH", "SOL"]
_STRIPE_PLAN = Literal["maker", "studio", "enterprise"]
_FEEDBACK_SOURCE = Literal["product_page", "widget", "sandbox", "other"]


# ── Products / discovery (admin + guest) ─────────────────────────────────────


class CreateProductRequest(BaseModel):
    idea: str = Field(..., min_length=3, max_length=8000)
    admin_instructions: Optional[str] = Field(None, max_length=16000)
    delivery_profile: Optional[_DELIVERY] = None
    production_mode: bool = False
    interface_locale: Optional[str] = Field(None, max_length=16, pattern=_LOCALE_RE)
    content_locale: Optional[str] = Field(None, max_length=16)

    @field_validator("content_locale")
    @classmethod
    def normalize_content_locale(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        s = str(v).strip().lower()
        if s in ("", "auto"):
            return "auto"
        return s[:16]


class BatchCreateIdeasRequest(BaseModel):
    ideas: list[str] = Field(..., min_length=1, max_length=50)
    mode: Literal["continue_on_error", "fail_fast"] = "continue_on_error"
    max_immediate_start: int = Field(2, ge=1, le=20)
    active_limit: int = Field(30, ge=1, le=200)
    admin_instructions: Optional[str] = Field(None, max_length=16000)
    delivery_profile: Optional[_DELIVERY] = None
    production_mode: bool = False
    interface_locale: Optional[str] = Field(None, max_length=16, pattern=_LOCALE_RE)
    content_locale: Optional[str] = Field(None, max_length=16)

    @field_validator("ideas")
    @classmethod
    def validate_ideas(cls, ideas: list[str]) -> list[str]:
        out: list[str] = []
        for raw in ideas:
            s = str(raw or "").strip()
            if len(s) < 3:
                raise ValueError("Each idea must be at least 3 characters")
            if len(s) > 8000:
                raise ValueError("Each idea must be at most 8000 characters")
            out.append(s)
        return out


class RunDiscoveryRequest(BaseModel):
    create_product: bool = True
    top_k: int = Field(5, ge=1, le=20)


class GuestLandingRequest(BaseModel):
    phrase: str = Field(..., min_length=8, max_length=2000)


# ── Customer portal ─────────────────────────────────────────────────────────


class CustomerRegisterRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=254)
    password: str = Field(..., min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        s = v.strip().lower()
        if "@" not in s or s.startswith("@") or s.endswith("@"):
            raise ValueError("Invalid email address")
        return s


class CustomerLoginRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=254)
    password: str = Field(..., min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        return CustomerRegisterRequest.validate_email(v)


class CustomerCreateRunRequest(BaseModel):
    idea: str = Field(..., min_length=8, max_length=2000)

    @field_validator("idea")
    @classmethod
    def strip_idea(cls, v: str) -> str:
        return v.strip()


class DemoNoteCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    body: str = Field("", max_length=8000)


class DemoNotePatchRequest(BaseModel):
    title: Optional[str] = Field(None, max_length=500)
    body: Optional[str] = Field(None, max_length=8000)

    @model_validator(mode="after")
    def require_patch_fields(self) -> "DemoNotePatchRequest":
        if self.title is None and self.body is None:
            raise ValueError("Provide title and/or body")
        return self


class StripeCheckoutRequest(BaseModel):
    target_plan: _STRIPE_PLAN = "maker"
    success_url: str = Field(..., min_length=8, max_length=2000)
    cancel_url: str = Field(..., min_length=8, max_length=2000)

    @field_validator("success_url", "cancel_url")
    @classmethod
    def validate_http_url(cls, v: str) -> str:
        s = v.strip()
        if not s.startswith(("https://", "http://")):
            raise ValueError("URL must start with http:// or https://")
        return s


# ── Feedback ──────────────────────────────────────────────────────────────────


class FeedbackSubmitRequest(BaseModel):
    product_id: str = Field(..., min_length=5, max_length=80)
    rating: int = Field(..., ge=1, le=5)
    comment: str = Field(..., min_length=1, max_length=4000)
    source: _FEEDBACK_SOURCE = "product_page"
    page_url: Optional[str] = Field(None, max_length=500)
    journey_step: Optional[str] = Field(None, max_length=80)
    tags: list[str] = Field(default_factory=list, max_length=32)
    locale: Optional[str] = Field(None, max_length=16, pattern=_LOCALE_RE)
    session_id: Optional[str] = Field(None, max_length=80)
    contact_email: Optional[str] = Field(None, max_length=254)

    @field_validator("product_id")
    @classmethod
    def validate_product_id(cls, v: str) -> str:
        s = v.strip()
        if not _PRODUCT_ID_RE.match(s):
            raise ValueError("product_id must look like prod-<hex>")
        return s

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, tags: list[str]) -> list[str]:
        out: list[str] = []
        for raw in tags[:32]:
            t = str(raw or "").strip()[:64]
            if t:
                out.append(t)
        return out


# ── Payments ──────────────────────────────────────────────────────────────────


class CreatePaymentRequest(BaseModel):
    product_id: str = Field(..., min_length=5, max_length=80)
    chain: _CHAIN = "base"
    token: str = Field(default="USDT", max_length=16)
    amount: Optional[float] = Field(None, gt=0, le=1_000_000)
    referral_source: Optional[str] = Field(None, max_length=128)

    @field_validator("product_id")
    @classmethod
    def validate_product_id(cls, v: str) -> str:
        s = v.strip()
        if not _PRODUCT_ID_RE.match(s):
            raise ValueError("product_id must look like prod-<hex>")
        return s

    @model_validator(mode="after")
    def validate_chain_token(self) -> "CreatePaymentRequest":
        tok = str(self.token or "USDT").strip().upper()
        if self.chain == "solana":
            if tok not in ("SOL", "USDC"):
                raise ValueError("Solana payments support SOL or USDC")
        elif tok not in ("USDT", "USDC", "ETH"):
            raise ValueError("EVM payments support USDT, USDC, or ETH")
        object.__setattr__(self, "token", tok)
        return self


class ConfirmPaymentRequest(BaseModel):
    tx_hash: str = Field(..., min_length=16, max_length=128)

    @field_validator("tx_hash")
    @classmethod
    def validate_tx_hash(cls, v: str) -> str:
        s = v.strip()
        if s.startswith("0x") and not _EVM_TX_RE.match(s):
            raise ValueError("Invalid EVM transaction hash")
        if len(s) < 16:
            raise ValueError("tx_hash too short")
        return s


# ── AI Market pilot ─────────────────────────────────────────────────────────


class AiMarketSearchRequest(BaseModel):
    task_description: str = Field("", max_length=4000)

    @field_validator("task_description")
    @classmethod
    def strip_task(cls, v: str) -> str:
        return v.strip()


class AiMarketSettlementConfirmRequest(BaseModel):
    product_id: str = Field(..., min_length=5, max_length=80)
    tx_hash: str = Field(..., min_length=16, max_length=128)
    chain: Optional[str] = Field(None, max_length=32)
    token: Optional[str] = Field(None, max_length=16)
    contract_address: Optional[str] = Field(None, max_length=128)
    customer_id: Optional[str] = Field(None, max_length=80)
    customer_email: Optional[str] = Field(None, max_length=254)
    wallet_address: Optional[str] = Field(None, max_length=128)
    amount: float = Field(..., gt=0, le=1_000_000)

    @field_validator("product_id")
    @classmethod
    def validate_product_id(cls, v: str) -> str:
        s = v.strip()
        if not _PRODUCT_ID_RE.match(s):
            raise ValueError("product_id must look like prod-<hex>")
        return s


class AiMarketCapabilityInvokeRequest(BaseModel):
    """Optional JSON body for capability invoke (pilot echoes safely bounded fields)."""

    input: dict[str, Any] = Field(default_factory=dict)

    @field_validator("input")
    @classmethod
    def bound_input(cls, v: dict[str, Any]) -> dict[str, Any]:
        if len(v) > 32:
            raise ValueError("input may have at most 32 keys")
        return v


# ── Telemetry ─────────────────────────────────────────────────────────────────


class TelemetryEventRequest(BaseModel):
    product_id: str = Field(..., min_length=5, max_length=80)
    event_type: str = Field(..., min_length=2, max_length=64, pattern=r"^[a-z][a-z0-9_]{1,63}$")
    data: dict[str, Any] = Field(default_factory=dict)
    session_id: Optional[str] = Field(None, max_length=80)
    page_url: Optional[str] = Field(None, max_length=500)
    locale: Optional[str] = Field(None, max_length=16, pattern=_LOCALE_RE)

    @field_validator("product_id")
    @classmethod
    def validate_product_id(cls, v: str) -> str:
        s = v.strip()
        if not s.startswith("prod-"):
            raise ValueError("Invalid product_id")
        return s

    @field_validator("data")
    @classmethod
    def bound_data(cls, v: dict[str, Any]) -> dict[str, Any]:
        if len(v) > 48:
            raise ValueError("data may have at most 48 keys")
        return v


class EvolutionSignalRequest(BaseModel):
    product_id: str = Field(..., min_length=5, max_length=80)
    signal: str = Field(..., min_length=2, max_length=64, pattern=r"^[a-z][a-z0-9_]{1,63}$")
    weight: float = Field(0.5, ge=0.0, le=1.0)
    context: dict[str, Any] = Field(default_factory=dict)
    session_id: Optional[str] = Field(None, max_length=80)

    @field_validator("product_id")
    @classmethod
    def validate_product_id(cls, v: str) -> str:
        s = v.strip()
        if not s.startswith("prod-"):
            raise ValueError("Invalid product_id")
        return s


# ── Support chat ──────────────────────────────────────────────────────────────


class SupportUiContext(BaseModel):
    current_page: Optional[str] = Field(None, max_length=200)
    active_tab: Optional[str] = Field(None, max_length=200)
    selected_product_id: Optional[str] = Field(None, max_length=80)
    preferred_locale: Optional[str] = Field(None, max_length=8)

    @field_validator("preferred_locale")
    @classmethod
    def validate_preferred_locale(cls, v: Optional[str]) -> Optional[str]:
        if v is None or not str(v).strip():
            return None
        s = str(v).strip().lower()
        if s.startswith("ru"):
            return "ru"
        if s.startswith("es"):
            return "es"
        return "en"

    @field_validator("selected_product_id")
    @classmethod
    def validate_product_id(cls, v: Optional[str]) -> Optional[str]:
        if v is None or not str(v).strip():
            return None
        s = str(v).strip()
        if not s.startswith("prod-"):
            raise ValueError("selected_product_id must start with prod-")
        return s


class SupportCreateSessionRequest(BaseModel):
    product_id: Optional[str] = Field(None, max_length=80)
    ui_context: Optional[SupportUiContext] = None

    @field_validator("product_id")
    @classmethod
    def validate_product_id(cls, v: Optional[str]) -> Optional[str]:
        if v is None or not str(v).strip():
            return None
        s = str(v).strip()
        if not s.startswith("prod-"):
            raise ValueError("product_id must start with prod-")
        return s


class SupportPostMessageRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    ui_context: Optional[SupportUiContext] = None


# ── Admin demo replay ─────────────────────────────────────────────────────────


class DemoReplayPatchRequest(BaseModel):
    enabled: Optional[bool] = None
    title: Optional[str] = Field(None, max_length=200)
    video_url: Optional[str] = Field(None, max_length=2000)

    @field_validator("video_url")
    @classmethod
    def strip_video_url(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        s = str(v).strip()
        return s or None


# ── Wow demo features ─────────────────────────────────────────────────────────


class PipelineReplayForkRequest(BaseModel):
    frame_index: int = Field(..., ge=0)
    operator_notes: Optional[str] = Field(None, max_length=2000)
    model_override: Optional[str] = Field(None, max_length=120)


class ProductShowcaseEnqueueRequest(BaseModel):
    product_id: str = Field(..., min_length=6, max_length=80)
    base_url: Optional[str] = Field(None, max_length=500)


class PromptImprovementApplyRequest(BaseModel):
    proposal_id: str = Field(..., min_length=4, max_length=120)
