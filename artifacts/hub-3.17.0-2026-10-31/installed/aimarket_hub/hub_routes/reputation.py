"""Reputation: slashes, hub reputation, events, buyer-confirmed deliveries, disputes and the
oracle quorum.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from aimarket_hub import deliveries, settle
from aimarket_hub.api_models import ReputationEventsRequest
from aimarket_hub.config import HubConfig
from aimarket_hub.database import HubDatabase
from aimarket_hub.reputation_oracle import ReputationOracle
from aimarket_hub.signing import Signer
from aimarket_hub.slash_sync import SlashRegistry
from aimarket_hub.supply_security import SupplySecurity
from aimarket_hub.trust import TrustScorer


def register(
    *,
    _TRUSTED_PROXIES: frozenset[str],
    _require_admin: Callable[..., Any],
    config: HubConfig,
    db: HubDatabase,
    reputation_oracle: ReputationOracle,
    router: APIRouter,
    signer: Signer,
    slash_registry: SlashRegistry,
    supply_security: SupplySecurity,
    trust_scorer: TrustScorer,
) -> None:
    """Attach the /reputation routes to ``router``."""
    # api.py's module-level helpers; imported here because api.py imports this module.
    from aimarket_hub.api import (
        _client_address,
        _trim_rate_buckets,
    )

    # ── Reputation ──────────────────────────────────────────────

    # Federated slash log (F2 transport). Declared BEFORE the /reputation/{hub_url:path}
    # catch-all so the exact paths match first.
    @router.get("/reputation/slashes")
    async def get_slashes():
        """This hub's signed slash attestations — peers pull and verify these."""
        return {"hub_url": config.hub_url, "slashes": slash_registry.export()}

    @router.get("/reputation/slashes/by-provider/{provider:path}")
    async def get_slash_signal(provider: str):
        """Union view of slashes against a provider across local + ingested peer logs."""
        sig = slash_registry.slash_signal(provider)
        sig["federated_penalty"] = slash_registry.federated_penalty(provider)
        # Local per-event audit trail + the calibration in force (cool-down / caps),
        # so a slashed provider can see exactly what fired and what the ceiling is.
        sig["local_events"] = db.supply_slash_events_recent(provider, limit=20)
        pol = supply_security.policy
        sig["policy"] = {
            "slash_failure_threshold": pol.slash_failure_threshold,
            "slash_failure_window_s": pol.slash_failure_window_s,
            "verified_fail_threshold": pol.verified_fail_threshold,
            "verified_fail_window_s": pol.verified_fail_window_s,
            "slash_cooldown_s": pol.slash_cooldown_s,
            "slash_daily_cap_usd": pol.slash_daily_cap_usd,
        }
        return sig

    @router.get("/reputation/{hub_url:path}")
    async def get_reputation(hub_url: str):
        score = trust_scorer.compute_score(hub_url)
        details = trust_scorer.score_details(hub_url)
        events = db.reputation_events_for(hub_url, limit=20)
        return {
            "hub_url": hub_url,
            "trust_score": score,
            "details": details,
            "recent_events": [
                {"type": e.event_type, "timestamp": e.timestamp,
                 "price_usd": e.price_usd, "latency_ms": e.latency_ms}
                for e in events
            ],
        }

    #: How far a signed event's own timestamp may sit from this hub's clock and still be
    #: recorded. The canonical binds the timestamp, so an old event cannot be re-dated —
    #: but without a window a peer could keep a signed event in a drawer and post it
    #: months later, and the replay check below only sees exact duplicates.
    _REPUTATION_MAX_SKEW_S = 24 * 3600
    _reputation_rate: dict[str, list[float]] = {}
    _REPUTATION_RATE_MAX = 30           # requests (of up to 100 events) per window
    _REPUTATION_RATE_WINDOW_S = 60.0

    def _check_reputation_rate(client_ip: str) -> bool:
        key = (client_ip or "").strip() or "\x00no-address"
        now = time.time()
        window = now - _REPUTATION_RATE_WINDOW_S
        bucket = [t for t in _reputation_rate.get(key, []) if t > window]
        if len(bucket) >= _REPUTATION_RATE_MAX:
            _reputation_rate[key] = bucket
            return False
        bucket.append(now)
        _reputation_rate[key] = bucket
        if len(_reputation_rate) > 4096:
            _trim_rate_buckets(_reputation_rate, window, 4096, keep=key)
        return True

    def _reputation_timestamp_ok(raw: Any) -> bool:
        """ISO-8601 UTC, within ±_REPUTATION_MAX_SKEW_S of now. Unparseable -> False."""
        text = str(raw or "").strip()
        if not text:
            return False
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return False
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return abs((datetime.now(timezone.utc) - parsed).total_seconds()) <= _REPUTATION_MAX_SKEW_S

    @router.post("/reputation/events")
    async def submit_reputation_events(body: ReputationEventsRequest, request: Request):
        """Ingest signed reputation events from federation peers.

        A peer's key proves WHO said it; three more checks decide whether it counts:
        the event's timestamp must be recent (the canonical binds it, so this cannot be
        forged around), the exact signed bytes must not have been recorded before (one
        valid event used to be replayable without limit — 100 per request — and trust.py
        computes success rate and estimated bond from the last 10 events, so a peer
        could set a provider's score by volume), and the caller is rate-limited.
        """
        from aimarket_hub.models import ReputationEvent
        if not _check_reputation_rate(_client_address(request, _TRUSTED_PROXIES)):
            raise HTTPException(
                status_code=429,
                detail=f"reputation submissions limited to {_REPUTATION_RATE_MAX} per "
                       f"{int(_REPUTATION_RATE_WINDOW_S)}s",
            )
        rejected = 0
        replayed = 0
        for ev in body.events:
            provider = ev.get("provider_hub", "")
            sig = ev.get("signature")
            consumer = ev.get("consumer_hub", "")

            # Require non-empty provider and consumer hubs
            if not provider or not consumer:
                rejected += 1
                continue

            # Require signature — prevents anonymous reputation poisoning
            if not sig or not isinstance(sig, dict) or not sig.get("value"):
                rejected += 1
                continue

            # The signed timestamp must be current. Checked BEFORE the signature so a
            # stale event costs no Ed25519 verification.
            if not _reputation_timestamp_ok(ev.get("timestamp")):
                rejected += 1
                continue

            # Verify signature against known peer public key
            peer = db.get_peer(consumer)
            if not peer or not peer.public_key:
                rejected += 1
                continue

            # Build canonical form matching the event's signed fields
            canonical = (
                f"type:{ev.get('type','')}"
                f"|provider_hub:{provider}"
                f"|timestamp:{ev.get('timestamp','')}"
                f"|price_usd:{ev.get('price_usd',0)}"
                f"|latency_ms:{ev.get('latency_ms',0)}"
            )
            if not signer.verify(peer.public_key, sig["value"], canonical):
                rejected += 1
                continue

            stored = db.record_reputation_event(ReputationEvent(
                event_type=ev.get("type", "unknown"),
                provider_hub=provider,
                capability_id=ev.get("capability_id"),
                timestamp=ev.get("timestamp", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())),
                price_usd=ev.get("price_usd", 0),
                latency_ms=ev.get("latency_ms", 0),
                consumer_hub=consumer,
                signature=json.dumps(sig),
            ))
            if not stored:
                replayed += 1
        return {
            "received": len(body.events) - rejected - replayed,
            "rejected": rejected,
            "replayed": replayed,
        }

    # ── Buyer-confirmed deliveries (deliveries.py) ──────────────────────────────────
    # A buyer that paid a seller directly brings the seller's signed receipt and the payment's
    # transaction; this hub checks both and counts the delivery. The hub does not hold the
    # seller's books: it keeps a counter per seller, never an amount, an address or a tx.
    _delivery_rate: dict[str, list[float]] = {}
    _DELIVERY_RATE_MAX = 20
    _DELIVERY_RATE_WINDOW_S = 60.0

    def _delivery_terms(pay_to: str) -> "settle.PaymentTerms":
        # Any amount counts: the receipt proves the delivery, the chain proves a payment under
        # that authorization reached the right wallet. 1 base unit is the floor.
        return settle.PaymentTerms(
            chain="base", token="USDC", token_contract=deliveries.USDC_BASE, decimals=6,
            pay_to=pay_to, amount_units=1, amount_usd=0.000001,
            min_confirmations=settle._min_confirmations(), chain_id=8453, seller_units=1,
        )

    @router.post("/reputation/deliveries")
    async def submit_delivery(body: dict, request: Request):
        """A buyer's evidence that a seller delivered (or refunded): the seller's signed receipt
        plus the transaction on Base. Counted once per transaction; see deliveries.py."""
        key = _client_address(request, _TRUSTED_PROXIES) or "\x00no-address"
        now = time.time()
        bucket = [t for t in _delivery_rate.get(key, []) if t > now - _DELIVERY_RATE_WINDOW_S]
        if len(bucket) >= _DELIVERY_RATE_MAX:
            raise HTTPException(status_code=429, detail=f"at most {_DELIVERY_RATE_MAX} receipts per minute")
        bucket.append(now)
        _delivery_rate[key] = bucket
        if len(_delivery_rate) > 4096:
            _trim_rate_buckets(_delivery_rate, now - _DELIVERY_RATE_WINDOW_S, 4096, keep=key)
        receipt = body.get("receipt") if isinstance(body, dict) else None
        product = str((receipt or {}).get("product_id") or "") if isinstance(receipt, dict) else ""
        listings = [c for c in db.list_capabilities(limit=None) if c.product_id == product and (c.provider_pubkey or "").strip()]
        try:
            c = await asyncio.to_thread(
                deliveries.confirm, receipt, body.get("signature"), body.get("transaction"),
                listings=listings, verify_signature=Signer.verify,
                verify_transfer=settle.verify_transfer, terms_factory=_delivery_terms,
            )
        except deliveries.DeliveryError as exc:
            raise HTTPException(status_code=exc.status, detail=str(exc)) from exc
        recorded = db.record_delivery_confirmation(c)
        return {
            "recorded": recorded,
            "seller": {"source_hub": c.source_hub, "product_id": c.product_id},
            "kind": c.kind,
            "deliveries_30d": db.deliveries_30d().get((c.source_hub, c.product_id),
                                                      {"confirmed": 0, "distinct_buyers": 0, "refunded": 0}),
        }

    _dispute_rate: dict[str, list[float]] = {}
    _DISPUTE_RATE_MAX = 6
    _DISPUTE_RATE_WINDOW_S = 60.0
    #: Serialized ``evidence`` bytes accepted per dispute. The field is NOT covered by
    #: Dispute.canonical(), so it costs the submitter no extra signature to pad it to the
    #: edge's body limit — the one lever that made the unbounded ledger a cheap memory DoS.
    _DISPUTE_EVIDENCE_MAX_BYTES = 16_384

    def _check_dispute_rate(client_ip: str) -> bool:
        key = (client_ip or "").strip() or "\x00no-address"
        now = time.time()
        window = now - _DISPUTE_RATE_WINDOW_S
        bucket = [t for t in _dispute_rate.get(key, []) if t > window]
        if len(bucket) >= _DISPUTE_RATE_MAX:
            _dispute_rate[key] = bucket
            return False
        bucket.append(now)
        _dispute_rate[key] = bucket
        if len(_dispute_rate) > 4096:
            _trim_rate_buckets(_dispute_rate, window, 4096, keep=key)
        return True

    @router.post("/reputation/disputes")
    async def submit_dispute(
        body: dict,
        request: Request,
        authorization: str = Header(default=""),
    ):
        """File a dispute: consumer-signed (portable PoM) or hub-admin (legacy operator path).

        The consumer-signed branch is UNAUTHENTICATED by design (that is what makes the
        proof portable), so it carries its own limits: a per-address rate cap, a bound on
        the unsigned ``evidence`` blob, and a duplicate-id refusal in the oracle. Without
        them the process-lifetime dispute list was remote-controlled memory.
        """
        from aimarket_hub.reputation_oracle import Dispute

        sig = body.get("signature")
        consumer_pubkey = str(body.get("consumer_pubkey") or "").strip()

        if sig and consumer_pubkey:
            if not _check_dispute_rate(_client_address(request, _TRUSTED_PROXIES)):
                return JSONResponse(status_code=429, content={
                    "success": False, "error": "rate_limited",
                    "detail": (
                        f"consumer-signed disputes limited to {_DISPUTE_RATE_MAX} "
                        "per minute per client address"
                    ),
                    "protocol_version": "v2",
                })
            required = ("dispute_id", "invocation_id", "provider_hub", "consumer_hub")
            missing = [k for k in required if not str(body.get(k) or "").strip()]
            if missing:
                raise HTTPException(
                    status_code=400,
                    detail={"error": "missing_fields", "fields": missing},
                )
            evidence = body.get("evidence") or {}
            try:
                evidence_bytes = len(json.dumps(evidence, ensure_ascii=False).encode("utf-8"))
            except (TypeError, ValueError):
                raise HTTPException(
                    status_code=400, detail="evidence must be JSON-serializable"
                ) from None
            if evidence_bytes > _DISPUTE_EVIDENCE_MAX_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail=(
                        f"evidence is {evidence_bytes} bytes; the limit is "
                        f"{_DISPUTE_EVIDENCE_MAX_BYTES} (it is not covered by the dispute "
                        "signature, so it cannot be trusted at any size)"
                    ),
                )
            dispute = Dispute(
                dispute_id=str(body["dispute_id"]),
                invocation_id=str(body["invocation_id"]),
                provider_hub=str(body["provider_hub"]),
                consumer_hub=str(body["consumer_hub"]),
                reason=str(body.get("reason") or ""),
                evidence=body.get("evidence") or {},
                requested_slash_pct=float(body.get("requested_slash_pct", 0)),
                timestamp=str(body.get("timestamp") or ""),
                signature=str(sig),
                consumer_pubkey=consumer_pubkey,
            )
            try:
                recorded = reputation_oracle.submit_signed_dispute(dispute)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            return {
                "dispute_id": recorded.dispute_id,
                "status": "recorded",
                "mode": "consumer_signed",
            }

        _require_admin(authorization)
        for field in ("invocation_id", "provider_hub", "consumer_hub", "reason"):
            if not str(body.get(field) or "").strip():
                raise HTTPException(status_code=400, detail=f"{field} is required")
        dispute = reputation_oracle.file_dispute(
            invocation_id=str(body["invocation_id"]),
            provider_hub=str(body["provider_hub"]),
            consumer_hub=str(body["consumer_hub"]),
            reason=str(body["reason"]),
            requested_slash_pct=float(body.get("requested_slash_pct", 0.1)),
            evidence=body.get("evidence"),
        )
        return {
            "dispute_id": dispute.dispute_id,
            "status": "recorded",
            "mode": "hub_operator",
        }

    @router.post("/reputation/disputes/{dispute_id}/resolve")
    async def resolve_dispute(
        dispute_id: str,
        body: dict,
        authorization: str = Header(default=""),
    ):
        """Resolve a dispute (slash bond). Requires m-of-n signatures when quorum is configured."""
        _require_admin(authorization)
        slash_pct = float(body.get("slash_pct", 0))
        ruling_note = str(body.get("ruling_note", "") or "")
        signatures = body.get("signatures") or []
        result = reputation_oracle.resolve_dispute(
            dispute_id,
            slash_pct=slash_pct,
            ruling_note=ruling_note,
            signatures=signatures,
        )
        if result.get("error"):
            raise HTTPException(status_code=400, detail=result)
        return result

    @router.get("/reputation/oracle/quorum")
    async def oracle_quorum_status():
        """Public quorum config (keys only, no secrets)."""
        q = reputation_oracle.quorum
        if q is None:
            return {"mode": "single_operator", "authorities": 0, "threshold": 1}
        return {
            "mode": "m_of_n",
            "authorities": len(q.authorities),
            "threshold": q.threshold,
        }
