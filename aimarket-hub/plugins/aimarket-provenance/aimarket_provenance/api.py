"""FastAPI router for provenance endpoints.

Endpoints under /ai-market/v2/p/provenance/:
  POST   /attest               — create a ProvenanceReceipt (auto-auth if token set)
  GET    /receipt/{receipt_id}  — retrieve a stored receipt (public)
  GET    /verify/{receipt_id}   — verify a receipt end-to-end (public)
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Header, HTTPException

from aimarket_hub.signing import Signer

from .receipt import ProvenanceReceipt
from .storage import ProvenanceStorage
from .verifier import verify_receipt

logger = logging.getLogger(__name__)


def _check_auth(authorization: str, api_token: str) -> None:
    """Require Bearer token auth on /attest.

    Fail-closed: if api_token is empty (operator misconfigured), reject all
    requests with 503. Previous behavior of allowing all requests when token
    was unset led to unauthenticated receipt forgery in default deploys.
    """
    if not api_token:
        raise HTTPException(
            status_code=503,
            detail=(
                "Provenance /attest requires AIMARKET_PROVENANCE_API_TOKEN to be set. "
                "Set this env var (with a strong random secret) before exposing the endpoint."
            ),
        )
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token")
    token = authorization[7:]
    # Constant-time comparison to prevent timing attacks
    import hmac
    if not hmac.compare_digest(token, api_token):
        raise HTTPException(status_code=403, detail="Invalid API token")


def create_provenance_router(
    storage: ProvenanceStorage,
    signer: Signer,
    hub_name: str = "AIMarket Hub",
    hub_version: str = "3.0.0",
    api_token: str = "",
    verify_domain: str = "https://verify.aimarket.org",
) -> APIRouter:
    router = APIRouter(tags=["provenance"])

    @router.post("/attest")
    async def attest(
        payload: dict[str, Any],
        authorization: str = Header(default=""),
    ) -> dict[str, Any]:
        """Create a self-contained ProvenanceReceipt.

        Requires Bearer token in Authorization header if
        AIMARKET_PROVENANCE_API_TOKEN is configured.
        """
        _check_auth(authorization, api_token)

        missing = [f for f in ["model_id", "input", "output"] if f not in payload]
        if missing:
            raise HTTPException(
                status_code=400,
                detail=f"Missing required fields: {', '.join(missing)}",
            )

        receipt = ProvenanceReceipt.create(
            model_id=payload["model_id"],
            provider_hub=payload.get("provider_hub", hub_name),
            input_payload=payload["input"],
            output_payload=payload["output"],
            signer=signer,
            hub_name=hub_name,
            hub_version=hub_version,
            parent_receipts=payload.get("parent_receipts"),
            tee_attestation=payload.get("tee_attestation"),
            latency_ms=payload.get("latency_ms", 0),
            price_usd=payload.get("price_usd", 0.0),
            invocation_nonce=payload.get("invocation_nonce"),
            reputation_score=payload.get("reputation_score"),
        )

        storage.store(receipt)
        logger.info("Provenance receipt created: %s", receipt.receipt_id)
        return receipt.to_dict()

    @router.get("/receipt/{receipt_id:path}")
    async def get_receipt(receipt_id: str) -> dict[str, Any]:
        """Retrieve a stored provenance receipt by ID (public)."""
        receipt = storage.get_by_receipt_id(receipt_id)
        if not receipt:
            raise HTTPException(status_code=404, detail="Receipt not found")
        return receipt.to_dict()

    @router.get("/verify/{receipt_id:path}")
    async def verify(receipt_id: str) -> dict[str, Any]:
        """Verify a provenance receipt by ID — all checks (public)."""
        receipt = storage.get_by_receipt_id(receipt_id)
        if not receipt:
            raise HTTPException(status_code=404, detail="Receipt not found")

        result = verify_receipt(receipt, signer)
        return {
            "receipt_id": receipt_id,
            "model_id": receipt.model_id,
            "provider_hub": receipt.provider_hub,
            "timestamp": receipt.timestamp,
            **result.to_dict(),
        }

    return router
