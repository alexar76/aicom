"""Trial quota, verification records and appeals, receipt checks and the lottery work-seat
entitlement.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from aimarket_hub import verified_settlement
from aimarket_hub.api_models import AppealRequest, LotteryEntitlementRequest, ReceiptVerifyRequest
from aimarket_hub.config import HubConfig
from aimarket_hub.sandbox_trials import sandbox_quota
from aimarket_hub.signing import pqc_required, receipt_signature_version, Signer
from aimarket_hub.verified_settlement import VerifiedSettlementService


def register(
    *,
    _ADMIN_TOKEN: str,
    _AGENT_TOKENS: dict[str, str],
    _NS_AGENT: tuple[str, str, dict[str, str]],
    _TRUSTED_PROXIES: frozenset[str],
    _check_invoke_rate: Callable[..., Any],
    _require_subject_credential: Callable[..., Any],
    config: HubConfig,
    router: APIRouter,
    signer: Signer,
    verify_svc: VerifiedSettlementService,
) -> None:
    """Attach the sandbox, verification, receipt and lottery routes to ``router``."""
    # api.py's module-level helpers; imported here because api.py imports this module.
    from aimarket_hub.api import (
        _client_address,
    )

    # ── Invoke (plugin-gated) ───────────────────────────────────

    @router.get("/sandbox/quota")
    async def sandbox_quota_endpoint(visitor_id: str = ""):
        """Remaining free widget trials for a visitor id (embed localStorage)."""
        return {**sandbox_quota(visitor_id), "protocol_version": "v2"}

    @router.get("/verification/{nonce}")
    async def verification_lookup(nonce: str):
        """Pay-on-Verified verdict lookup: the async settlement's polling surface.

        Returns the (possibly still pending) verification envelope, the receipt
        with the envelope folded in, and — for refunded verdicts — the signed
        verification_rejection receipt.
        """
        rec = verify_svc.lookup(nonce)
        if rec is None:
            return JSONResponse(status_code=404, content={
                "success": False,
                "error": "verification_not_found",
                "protocol_version": "v2",
            })
        return {"success": True, **rec, "protocol_version": "v2"}

    @router.get("/verification/appeals/stats")
    async def verification_appeal_stats():
        """How often the appeal court agreed with the first instance — aggregate only.

        The research signal for calibrating the first-instance verifier. Two path segments,
        so it never collides with GET /verification/{nonce}.
        """
        return {"success": True, **verify_svc.appeal_stats(), "protocol_version": "v2"}

    @router.post("/verification/{nonce}/appeal")
    async def verification_appeal(
        nonce: str,
        request: Request,
        body: AppealRequest | None = None,
        x_payment_channel_secret: str | None = Header(default=None, alias="X-Payment-Channel-Secret"),
        x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    ):
        """Appeal a provisional Pay-on-Verified verdict to the second verifier.

        Only the party the verdict went against, only inside the window, and only with a
        bond: the buyer appeals a pass with the channel secret (bond held on that channel),
        the seller appeals a fail with its publisher account's X-API-Key (bond held on its
        hub credits). 202 with the filed appeal; the outcome lands on
        GET /verification/{nonce}. See docs/pay-on-verified.md "Appeals".
        """
        if not _check_invoke_rate(_client_address(request, _TRUSTED_PROXIES) or "anonymous"):
            return JSONResponse(status_code=429, content={
                "success": False, "error": "rate_limited", "protocol_version": "v2",
            })
        try:
            filed = verify_svc.file_appeal(
                nonce,
                channel_secret=(x_payment_channel_secret or "").strip(),
                api_key=(x_api_key or "").strip(),
                statement=(body.statement if body is not None else ""),
            )
        except verified_settlement.AppealRefused as exc:
            return JSONResponse(status_code=exc.status, content={
                "success": False, "error": exc.code, "detail": exc.detail,
                "protocol_version": "v2",
            })
        return JSONResponse(status_code=202, content={
            "success": True, **filed, "protocol_version": "v2",
        })

    @router.post("/receipts/verify")
    async def receipt_verify(body: ReceiptVerifyRequest):
        """Verify one receipt against this Hub's live Ed25519 + ML-DSA-65 keys.

        This is deliberately a *self* verifier: the public key is never accepted from
        the request, so a caller cannot make an arbitrary self-signed object appear
        trusted. Browser clients still verify Ed25519 locally; this endpoint evaluates
        ML-DSA-65 until WebCrypto exposes a post-quantum primitive.
        """
        receipt = body.receipt
        # Nginx caps the production request body, but direct ASGI deployments and test
        # clients may not. Keep verification CPU and response size predictably bounded.
        try:
            encoded_size = len(json.dumps(
                receipt, ensure_ascii=False, separators=(",", ":"), default=str
            ).encode())
        except (TypeError, ValueError, RecursionError):
            encoded_size = 131_073
        if encoded_size > 131_072:
            raise HTTPException(status_code=413, detail="receipt exceeds 128 KiB")

        signature = receipt.get("signature")
        version = receipt_signature_version(receipt)
        classical_valid = False
        hybrid_valid = False
        pq_present = isinstance(signature, dict) and bool(signature.get("pq_value"))
        if version and isinstance(signature, dict):
            classical_valid = any(
                Signer.verify(
                    signer.public_key_b64,
                    str(signature.get("value") or ""),
                    canonical,
                )
                for canonical in signer.receipt_canonical_candidates(receipt, version)
            )
            hybrid_valid = signer.verify_receipt_signature(receipt)

        return {
            "valid": hybrid_valid,
            "classical_valid": classical_valid,
            "pq_present": pq_present,
            # `None` means there was no PQ claim to evaluate. When present, `valid`
            # requires both layers and pins ML-DSA to this Hub's persisted PQ key.
            "pq_valid": hybrid_valid if pq_present else None,
            "algorithm": "ed25519+ml-dsa-65" if pq_present else "ed25519",
            "signature_version": version or None,
            "signer_matches_live_key": classical_valid,
            "policy_requires_pq": pqc_required(),
            "protocol_version": "v2",
        }

    @router.post("/lottery/work-seat-entitlement")
    async def lottery_work_seat_entitlement(
        body: LotteryEntitlementRequest,
        authorization: str = Header(default=""),
    ):
        """Issue a short-lived, Hub-signed lottery entitlement for this agent.

        Every federated Hub uses its own agent credential registry and signing key.
        The lottery relayer trusts only this Hub or an active peer key pinned by its
        federation registry; a self-selected key is never accepted.
        """
        # NOT via the shared-publish-token relaxation. The whole value of this
        # entitlement is "this Hub can tell its agents apart": the relayer turns
        # (hub_url, agent_id) into the on-chain participant nullifier that rations one
        # unpaid work seat per agent. A credential that speaks for ANY agent_id mints
        # unlimited distinct participants from one token — a sybil generator for the
        # lottery — so this route requires a real per-agent credential (or the operator's
        # admin token) on every hub, production or not.
        if not _AGENT_TOKENS and not _ADMIN_TOKEN:
            raise HTTPException(
                status_code=503,
                detail=(
                    "disabled: lottery entitlements need a per-agent credential. Set "
                    "AIMARKET_AGENT_TOKENS='<agent_id>:<secret>,...' (the shared publish "
                    "token cannot prove which agent is asking)."
                ),
            )
        _require_subject_credential(authorization, body.agent_id, (_NS_AGENT,))
        from aimarket_hub.lottery_entitlement import issue_entitlement

        try:
            entitlement = issue_entitlement(
                signer=signer,
                hub_url=config.hub_url,
                agent_id=body.agent_id,
                wallet=body.wallet,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {"entitlement": entitlement, "protocol_version": "v2"}
