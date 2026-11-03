"""ACEX capital: pricing, Agent IPO (float, listings, distribution, positions) and audits, on
the hub prefix and the /api/v2/capital alias.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse

from aimarket_hub.acex_storage import LedgerNotConfigured
from aimarket_hub.api_models import AuditClaimRequest, AuditSyncRequest, IpoRequest
from aimarket_hub.database import HubDatabase


def register(
    *,
    _require_admin: Callable[..., Any],
    db: HubDatabase,
    router: APIRouter,
) -> SimpleNamespace:
    """Attach the capital routes to ``router`` and the ``capital_alias`` router."""
    # api.py's module-level helpers; imported here because api.py imports this module.
    from aimarket_hub.api import (
        logger,
    )

    # ── ACEX Capital (Pulse Terminal) ───────────────────────────

    from aimarket_hub.capital_pricing import hub_capital_pricing

    @router.get("/capital/pricing")
    async def capital_pricing(
        chain: str = "any",
        listing_id: str | None = None,
        limit: int = 50,
    ):
        """Capability revenue indices for Pulse Terminal (ACEX Phase 2)."""
        return hub_capital_pricing(db, chain=chain, listing_id=listing_id, limit=min(limit, 200))

    capital_alias = APIRouter(prefix="/api/v2/capital", tags=["acex-capital"])

    @capital_alias.get("/pricing")
    async def capital_pricing_alias(
        chain: str = "any",
        listing_id: str | None = None,
        limit: int = 50,
    ):
        return hub_capital_pricing(db, chain=chain, listing_id=listing_id, limit=min(limit, 200))

    # ── ACEX Agent IPO (factory → hub → ACEX leg) ────────────────
    # Float a product as CapShares, inspect the cap table, and distribute the
    # invoke-revenue pool to holders. Mounted on both the hub prefix
    # (/ai-market/v2/capital/...) and the Pulse Terminal alias (/api/v2/capital/...).
    from aimarket_hub import acex_ipo

    def _acex_ledger_unavailable(ledger: str, **empty: Any) -> JSONResponse:
        """The 503 for a public ACEX read whose ledger cannot be opened.

        The cause stays in the log: it names the hub's storage configuration, which is
        the operator's business, not the caller's.
        """
        return JSONResponse(status_code=503, content={
            **empty,
            "error": f"{ledger}_unavailable",
            "detail": f"the ACEX {ledger} ledger is not available on this hub",
            "protocol_version": "v2",
        })

    def _register_capital_ipo(r: APIRouter, base: str) -> None:
        @r.post(base + "/ipo")
        async def capital_ipo(body: IpoRequest, authorization: str = Header(default="")):
            _require_admin(authorization)  # minting CapShares is privileged
            from aimarket_hub import acex_ai_audit

            ai_pack: dict | None = None
            audit_score = body.audit_score_bps
            auditor_id = ""
            auditor_kind = ""
            pack_sha = ""
            if acex_ai_audit.require_ai_audit():
                if body.audit_score_bps is not None:
                    return JSONResponse(
                        status_code=400,
                        content={
                            "error": "human_audit_override_forbidden",
                            "detail": (
                                "ALP auditor is an agent (ai-auditor:acex-v1). "
                                "Do not submit audit_score_bps; the AI pack is the score."
                            ),
                            "protocol_version": "v2",
                        },
                    )
                caps = acex_ai_audit.caps_for_product(db, body.product_id)
                ai_pack = acex_ai_audit.audit_capabilities(body.product_id, caps)
                if ai_pack.get("verdict") != "approve":
                    return JSONResponse(
                        status_code=400,
                        content={**ai_pack, "error": "ai_audit_rejected", "protocol_version": "v2"},
                    )
                audit_score = int(ai_pack["score_bps"])
                auditor_id = str(ai_pack.get("auditor_id") or acex_ai_audit.AUDITOR_ID)
                auditor_kind = str(ai_pack.get("auditor_kind") or acex_ai_audit.AUDITOR_KIND)
                pack_sha = str(ai_pack.get("pack_sha256") or "")
            res = acex_ipo.float_product(
                body.product_id, name=body.name, symbol=body.symbol,
                max_supply=body.max_supply, treasury=body.treasury,
                audit_score_bps=audit_score, revenue_share_bps=body.revenue_share_bps,
                auditor_id=auditor_id, auditor_kind=auditor_kind,
                audit_pack_sha256=pack_sha,
            )
            if not res.get("error") and auditor_id:
                try:
                    from aimarket_hub import acex_audit
                    acex_audit.sync_coverage(
                        body.product_id,
                        auditor=auditor_id,
                        cover_usd=float(os.environ.get("ACEX_AI_AUDITOR_COVER_USD", "10000") or 10000),
                        score_bps=int(audit_score or 0),
                        phase="insuring",
                    )
                except Exception:
                    logger.warning("ACEX AI auditor coverage sync failed for %s", body.product_id)
            code = 400 if res.get("error") else 200
            extra = {"ai_audit": ai_pack} if ai_pack else {}
            return JSONResponse(status_code=code, content={**res, **extra, "protocol_version": "v2"})

        @r.get(base + "/listings")
        async def capital_listings(limit: int = 50):
            try:
                return {
                    "listings": acex_ipo.list_listings(limit=min(limit, 500)),
                    "protocol_version": "v2",
                }
            except LedgerNotConfigured:
                return _acex_ledger_unavailable("listings", listings=[])
            except Exception:
                logger.exception("ACEX listings read failed")
                return _acex_ledger_unavailable("listings", listings=[])

        @r.get(base + "/listings/{listing_id}")
        async def capital_listing(listing_id: str):
            try:
                res = acex_ipo.listing_state(listing_id)
            except LedgerNotConfigured:
                return _acex_ledger_unavailable("listings")
            except Exception:
                logger.exception("ACEX listings read failed")
                return _acex_ledger_unavailable("listings")
            code = 404 if res.get("error") else 200
            return JSONResponse(status_code=code, content={**res, "protocol_version": "v2"})

        @r.post(base + "/listings/{listing_id}/distribute")
        async def capital_distribute(listing_id: str, authorization: str = Header(default="")):
            _require_admin(authorization)
            res = acex_ipo.distribute(listing_id)
            code = 404 if res.get("error") == "unknown_listing" else (400 if res.get("error") else 200)
            return JSONResponse(status_code=code, content={**res, "protocol_version": "v2"})

        @r.get(base + "/holdings")
        async def capital_holdings(holder: str):
            try:
                positions = acex_ipo.holder_positions(holder)
            except LedgerNotConfigured:
                return _acex_ledger_unavailable("listings", holder=holder, positions=[])
            except Exception:
                logger.exception("ACEX listings read failed")
                return _acex_ledger_unavailable("listings", holder=holder, positions=[])
            return {"holder": holder, "positions": positions, "protocol_version": "v2"}

    def _register_capital_audit(r: APIRouter, base: str) -> None:
        from aimarket_hub import acex_audit

        @r.get(base + "/audit")
        async def capital_audit_list(limit: int = 50):
            # The ledger opens lazily, and a production hub without its Postgres URL refuses
            # to open it at all (acex_storage.require_postgres_url). That refusal reached a
            # public GET as an unhandled RuntimeError — a 500 on modelmarket.dev, 2026-09-30.
            try:
                listings = acex_audit.list_audit_states(limit=min(limit, 500))
            except LedgerNotConfigured:
                return _acex_ledger_unavailable("audit", listings=[])
            except Exception:
                logger.exception("ACEX audit ledger read failed")
                return _acex_ledger_unavailable("audit", listings=[])
            return {"listings": listings, "protocol_version": "v2"}

        @r.get(base + "/audit/{listing_id}")
        async def capital_audit_detail(listing_id: str):
            try:
                res = acex_audit.listing_audit_state(listing_id)
            except LedgerNotConfigured:
                return _acex_ledger_unavailable("audit")
            except Exception:
                logger.exception("ACEX audit ledger read failed")
                return _acex_ledger_unavailable("audit")
            code = 404 if res.get("error") else 200
            return JSONResponse(status_code=code, content={**res, "protocol_version": "v2"})

        @r.post(base + "/audit/{listing_id}/sync")
        async def capital_audit_sync(
            listing_id: str,
            body: AuditSyncRequest,
            authorization: str = Header(default=""),
        ):
            _require_admin(authorization)
            res = acex_audit.sync_coverage(
                listing_id,
                body.auditor,
                cover_usd=body.cover_usd,
                score_bps=body.score_bps,
                phase=body.phase,
            )
            code = 404 if res.get("error") == "unknown_listing" else (400 if res.get("error") else 200)
            return JSONResponse(status_code=code, content={**res, "protocol_version": "v2"})

        @r.post(base + "/audit/{listing_id}/claim")
        async def capital_audit_claim(
            listing_id: str,
            body: AuditClaimRequest,
            authorization: str = Header(default=""),
        ):
            # SEC-05: claiming auditor rewards moves funds — gate behind admin auth
            # like the rest of the capital/audit privileged surface (mint/sync).
            _require_admin(authorization)
            res = acex_audit.claim_audit_reward(listing_id, body.auditor)
            code = 400 if res.get("error") else 200
            return JSONResponse(status_code=code, content={**res, "protocol_version": "v2"})

    _register_capital_ipo(router, "/capital")   # /ai-market/v2/capital/...
    _register_capital_ipo(capital_alias, "")     # /api/v2/capital/...
    _register_capital_audit(router, "/capital")
    _register_capital_audit(capital_alias, "")

    return SimpleNamespace(
        capital_alias=capital_alias,
    )
