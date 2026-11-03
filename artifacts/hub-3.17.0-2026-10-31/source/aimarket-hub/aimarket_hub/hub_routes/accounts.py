"""Health, credit accounts, top-ups, payer wallets, deposits, the ledger, credit and
collateral.
"""

from __future__ import annotations

import contextlib
import re
import time
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from aimarket_hub import (
    card_topup,
    consumer_labels,
    credits,
    deposit_watch,
    security_posture,
    settle,
    topup,
    x402,
)
from aimarket_hub.channels import payment_readiness
from aimarket_hub.config import HubConfig
from aimarket_hub.credits import CreditsLedger
from aimarket_hub.database import HubDatabase
from aimarket_hub.deposit_watch import DepositStore
from aimarket_hub.paging import page_limit
from aimarket_hub.settle import PaymentStore as SettlePaymentStore
from aimarket_hub.signing import Signer
from aimarket_hub.topup import TopupStore

# Unclaimed deposits one admin request may read.
DEPOSITS_PAGE_MAX = 500


def register(
    *,
    _TRUSTED_PROXIES: frozenset[str],
    _is_admin_bearer: Callable[..., Any],
    _require_admin: Callable[..., Any],
    _signup_allowed: Callable[..., Any],
    config: HubConfig,
    db: HubDatabase,
    hub_credits: CreditsLedger,
    hub_deposits: DepositStore,
    hub_settle: SettlePaymentStore,
    hub_topups: TopupStore,
    router: APIRouter,
    signer: Signer,
) -> SimpleNamespace:
    """Attach /health and the account, top-up and deposit routes to ``router``."""
    # api.py's module-level helpers; imported here because api.py imports this module.
    from aimarket_hub.api import (
        _HUB_STARTED_AT,
        OPERATOR_CREDIT_STACK,
        _client_address,
    )

    @router.get("/health")
    async def hub_health():
        from aimarket_hub import signing as _signing

        runtime_payment = payment_readiness()
        # A hub that cannot check ML-DSA-65 refuses every AIMarket hub's manifest (they all sign
        # hybrid) and indexes none of them. That is a broken hub, and it must say so here rather
        # than look healthy: "degraded", with the reason. Still HTTP 200 — it serves; deploy
        # scripts and monitors that read the body decide what to do with it.
        can_verify_pq = _signing.pqc_available()
        warnings = [] if can_verify_pq else [_signing.PQ_MISSING_ADVICE]
        return {
            "status": "ok" if not warnings else "degraded",
            **({"warnings": warnings} if warnings else {}),
            "service": "aimarket-hub",
            "version": config.hub_version,
            # Operators and monitors need to prove that production did not silently
            # fall back to a local file after a restart. These are readiness facts, not
            # secrets; keys and connection strings are deliberately not returned here.
            "database_backend": db._backend.backend_type,
            "payment_ready": bool(
                config.payment_ready and runtime_payment.get("can_credit_channels", False)
            ),
            "pqc_ready": bool(signer.pq_public_key_b64),
            # pqc_ready = this hub SIGNS hybrid (its operator's choice); pqc_can_verify = it can
            # READ hybrid peers, which every hub needs.
            "pqc_can_verify": can_verify_pq,
            "pq_unverifiable_refusals": _signing.pq_unverifiable_refusals(),
            "uptime_seconds": int(time.time() - _HUB_STARTED_AT),
        }

    def _public_consumer_label(raw: str) -> str:
        """Pseudonymize a consumer label for a PUBLIC feed (rules in consumer_labels, shared with
        the server-rendered home page so the two can never disagree again)."""
        return consumer_labels.public_consumer_label(raw)

    # Which credit accounts, servers and wallets are the operator's own ecosystem: nothing in
    # the ledger can tell them apart from a customer's (on a hub with signup closed every
    # account is operator-minted, including ones minted FOR a customer), so they are listed,
    # in ecosystem.json — see _ecosystem_policy and aimarket_hub/ecosystem.py.

    # ── Credit accounts: the self-serve half of the credits rail ────────────────
    # The blocker this replaces: the only buyer identity the hub had was
    # AIMARKET_PUBLISHER_TOKENS / AIMARKET_AGENT_TOKENS, parsed out of os.environ once at
    # app construction. One new customer meant editing .env and restarting the hub, which
    # is not an onboarding path, it is a maintenance window per signup.

    @router.post("/accounts")
    async def create_credit_account(
        request: Request,
        body: dict | None = None,
        authorization: str = Header(default=""),
    ):
        ledger = hub_credits
        if not credits.enabled() or ledger is None:
            raise HTTPException(
                status_code=503,
                detail="credit accounts are off on this hub (AIMARKET_CREDITS_ENABLED=0)",
            )
        is_admin = _is_admin_bearer(authorization)
        if not credits.signup_open() and not is_admin:
            raise HTTPException(
                status_code=403,
                detail="this hub issues credit accounts by hand — ask the operator for a key",
            )
        content_type = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
        if not is_admin and content_type != "application/json":
            # A body-less or form POST is a "simple" cross-site request: any page a visitor
            # opens could mint grant-bearing accounts from the visitor's address, draining
            # the daily grant budget and the visitor's own signup bucket. JSON needs a CORS
            # preflight, which this hub's empty allowlist refuses.
            raise HTTPException(
                status_code=415,
                detail="send the signup as JSON: Content-Type: application/json",
            )
        client_ip = _client_address(request, _TRUSTED_PROXIES) or "anonymous"
        if not is_admin and not _signup_allowed(client_ip):
            raise HTTPException(
                status_code=429,
                detail="too many accounts from this address — try again later",
            )
        label = str((body or {}).get("label") or "")[:120]
        # A self-minted key gets the operator's advertised free grant; an operator-minted
        # one can be opened with any starting balance, because at that point the operator
        # has already decided what it is worth.
        grant = credits.signup_grant_usd()
        grant_note = ""
        if is_admin:
            with contextlib.suppress(TypeError, ValueError):
                grant = max(0.0, float((body or {}).get("grant_usd", grant)))
        elif "grant_usd" in (body or {}):
            # Refuse rather than ignore. Silently overriding a privileged field is
            # how a caller comes to believe it is the operator: a service holding
            # the wrong token asked for grant_usd=0, got the signup grant, and
            # only discovered it was not admin at the first call that moves money
            # — which is the one call that must not be the first to find out.
            raise HTTPException(
                status_code=403,
                detail="grant_usd is operator-only; this request is not admin-authenticated",
            )
        if is_admin:
            account = ledger.create_account(label=label, grant_usd=grant, grant_note=credits.OPERATOR_GRANT_NOTE)
        else:
            # A farmed grant is bounded by a budget, not by telling people from
            # bots — which is not a thing this hub can do. When the budget is
            # spent the account is still opened, just at zero, so a real buyer
            # can still top up and work. The check and the grant are one step.
            account = ledger.open_signup_account(label=label)
            grant_note = account.pop("grant_note", "")
        return {
            "success": True,
            **account,
            **({"grant_note": grant_note} if grant_note else {}),
            # Said once, here, because it is the only time the key exists in plaintext.
            "note": "store api_key now — only its hash is kept, it cannot be shown again",
            "usage": "send it as the X-API-Key header on /ai-market/v2/invoke",
            "protocol_version": "v2",
        }

    @router.get("/account")
    async def read_credit_account(x_api_key: str | None = Header(default=None, alias="X-API-Key")):
        ledger = hub_credits
        if not credits.enabled() or ledger is None:
            raise HTTPException(status_code=503, detail="credit accounts are off on this hub")
        account_id = ledger.resolve(x_api_key or "")
        if not account_id:
            raise HTTPException(status_code=401, detail="unknown or disabled X-API-Key")
        return {"success": True, **(ledger.account(account_id) or {}), "protocol_version": "v2"}

    def _topup_claim(*, stack: str, **kw: Any) -> dict[str, Any]:
        from aimarket_hub.channels import claim_deposit_as

        return claim_deposit_as(stack, **kw)

    def _topup_answer(call: Any) -> Any:
        try:
            return call()
        except topup.TopupError as exc:
            return JSONResponse(status_code=exc.status, content=exc.body())

    async def _topup_offloaded(call: Any) -> Any:
        # Redemption reads the chain (two or more blocking RPC round trips) and a quote may
        # read the token's decimals: off the event loop, or one slow node stalls every request.
        from starlette.concurrency import run_in_threadpool

        return await run_in_threadpool(_topup_answer, call)

    def _topup_limit_key(request: Request) -> str:
        # Anybody but the quote's owner (topup.redeem gives the owner its account's budget),
        # including a caller holding some other account's key.
        return f"ip:{_client_address(request, _TRUSTED_PROXIES) or 'anonymous'}"

    @router.post("/account/topup")
    async def topup_credit_account(
        request: Request,
        body: dict | None = None,
        x_api_key: str | None = Header(default=None, alias="X-API-Key"),
        x_payment: str | None = Header(default=None, alias="X-Payment"),
        payment_signature: str | None = Header(default=None, alias="PAYMENT-SIGNATURE"),
        x_payment_nonce: str | None = Header(default=None, alias="X-Payment-Nonce"),
    ):
        """Buy credit with USDC (aimarket_hub/topup.py, docs/credits-topup.md).

        Without a payment: a 402 whose x402 terms pay the operator ``amount_usd`` USDC by an
        EIP-3009 authorization over a nonce bound to THIS account. With ``X-Payment: <tx hash>``
        (or an x402 payload carrying it) and ``X-Payment-Nonce``: the same redemption as
        ``POST /topups/{nonce}``.
        """
        # This 402 is complete as built; the x402 middleware must not mint an invoice onto it.
        request.state.x402_passthrough = True
        ledger = hub_credits
        if not credits.enabled() or ledger is None:
            return JSONResponse(status_code=503, content=topup.TopupError(
                503, "topup_unavailable", "credit accounts are off on this hub").body())
        account_id = ledger.resolve(x_api_key or "")
        if not account_id:
            return JSONResponse(status_code=401, content=topup.TopupError(
                401, "api_key_required",
                "send the X-API-Key of the account to credit (open one with POST /ai-market/v2/accounts)",
            ).body())
        raw = (x_payment or payment_signature or "").strip()
        if raw:
            ref = settle.extract_payment_ref(raw, x402.decode_payment(raw))
            nonce = (x_payment_nonce or ref["nonce"] or "").strip()
            return await _topup_offloaded(lambda: topup.redeem(
                store=hub_topups, ledger=ledger, payments=hub_settle, nonce=nonce, tx_hash=ref["tx_hash"],
                claim_deposit=_topup_claim, owner_account=account_id,
                limit_key=_topup_limit_key(request),
            ))
        amount = (body or {}).get("amount_usd")
        answer = await _topup_offloaded(lambda: topup.quote(store=hub_topups, account_id=account_id,
                                                            amount_usd=amount, hub_url=config.hub_url))
        if isinstance(answer, JSONResponse):
            return answer
        _quote, content, v2 = answer
        return JSONResponse(status_code=402, content=content,
                            headers={"PAYMENT-REQUIRED": x402.encode_header(v2)})

    @router.post("/topups/{nonce}")
    async def redeem_topup(
        nonce: str,
        request: Request,
        body: dict | None = None,
        x_api_key: str | None = Header(default=None, alias="X-API-Key"),
        x_payment: str | None = Header(default=None, alias="X-Payment"),
    ):
        """Credit a mined top-up payment. Open to anyone holding the transaction hash: the
        account was bound when the quote was minted, so presenting someone else's payment only
        credits THEIR account, once. The balance is shown only to the account's own key."""
        request.state.x402_passthrough = True
        ledger = hub_credits
        if not credits.enabled() or ledger is None:
            return JSONResponse(status_code=503, content=topup.TopupError(
                503, "topup_unavailable", "credit accounts are off on this hub").body())
        tx_hash = str((body or {}).get("tx_hash") or "").strip()
        if not tx_hash and x_payment:
            tx_hash = settle.extract_payment_ref(x_payment, x402.decode_payment(x_payment))["tx_hash"]
        owner = ledger.resolve(x_api_key) if x_api_key else ""
        return await _topup_offloaded(lambda: topup.redeem(
            store=hub_topups, ledger=ledger, payments=hub_settle, nonce=nonce, tx_hash=tx_hash,
            claim_deposit=_topup_claim, owner_account=owner, limit_key=_topup_limit_key(request),
        ))

    @router.get("/topups/{nonce}")
    async def read_topup(nonce: str, x_api_key: str | None = Header(default=None, alias="X-API-Key")):
        """Where a top-up stands. The account it funded is shown only to that account's key."""
        q = hub_topups.get(nonce) if settle.is_nonce(nonce) else None
        if q is None:
            return JSONResponse(status_code=404, content=topup.TopupError(
                404, "topup_unknown", "no top-up quote with that nonce on this hub").body())
        owner = bool(x_api_key) and hub_credits is not None and hub_credits.resolve(x_api_key) == q.account_id
        decimals = int((x402.asset_profile() or {}).get("decimals") or 6)
        return {"success": True, **q.public(decimals, owner=owner), "protocol_version": "v2"}

    def _deposit_watcher() -> deposit_watch.Watcher:
        from aimarket_hub.channels import claim_deposit_as, deposit_claim_holder, release_deposit_as

        return deposit_watch.Watcher(
            store=hub_deposits, ledger=hub_credits, topups=hub_topups, payments=hub_settle,
            claim_deposit=lambda *, stack, **kw: claim_deposit_as(stack, **kw),
            release_deposit=lambda *, stack, **kw: release_deposit_as(stack, **kw),
            claim_holder=lambda **kw: deposit_claim_holder(**kw))

    async def _credit_linked_now(address: str) -> list[str]:
        from starlette.concurrency import run_in_threadpool

        if not deposit_watch.enabled():
            return []
        return await run_in_threadpool(_deposit_watcher().credit_linked, address)

    @router.get("/security/posture")
    async def security_posture_view():
        """Aggregate security signals for the fleet alerter, over the last hour: signups the
        per-address limit refused, requests carrying an X-API-Key no account owns, and the
        share of the daily signup-grant budget spent. Counts only — nothing names anyone."""
        grant: dict[str, Any] = {"daily_budget_usd": 0.0, "granted_24h_usd": 0.0, "spent_fraction": 0.0}
        if hub_credits is not None and credits.enabled():
            daily = credits.grant_budget_daily_usd()
            granted = credits.mc_to_usd(hub_credits.granted_mc(since_hours=24))
            grant = {
                "daily_budget_usd": daily,
                "granted_24h_usd": granted,
                "spent_fraction": round(granted / daily, 4) if daily > 0 else 0.0,
            }
        return {
            "window_s": security_posture.WINDOW_S,
            "signups_refused": security_posture.count(security_posture.SIGNUP_REFUSED),
            "bad_api_key_attempts": security_posture.count(security_posture.BAD_API_KEY),
            "signup_grant": grant,
            "protocol_version": "v2",
        }

    @router.post("/account/rotate-key")
    async def rotate_api_key(x_api_key: str | None = Header(default=None, alias="X-API-Key")):
        """Replace this account's key; the old one stops working immediately.

        Authenticated by the key itself, so a holder whose key leaked (a URL in a log, a
        shared notebook) can end it without the operator. The new key is shown once."""
        if hub_credits is None or not credits.enabled():
            raise HTTPException(status_code=503, detail="credit accounts are off on this hub")
        if not (x_api_key or "").strip():
            raise HTTPException(status_code=401, detail="send the key to rotate as X-API-Key")
        out = hub_credits.rotate_key(x_api_key)
        if out.get("error"):
            raise HTTPException(status_code=401, detail=out["error"])
        return {"success": True, **out, "protocol_version": "v2"}

    @router.post("/account/payer-wallets")
    async def link_payer_wallet(body: dict, x_api_key: str | None = Header(default=None, alias="X-API-Key")):
        """Say that a wallet's plain transfers into the top-up wallet are this account's top-ups.

        The wallet proves it is yours by signing ``deposit_watch.link_message`` (EIP-191). One
        wallet belongs to one account. Transfers it already sent are credited at once.
        """
        ledger = hub_credits
        if not credits.enabled() or ledger is None:
            raise HTTPException(status_code=503, detail="credit accounts are off on this hub")
        account_id = ledger.resolve(x_api_key or "")
        if not account_id:
            raise HTTPException(status_code=401, detail="unknown or disabled X-API-Key")
        address = str((body or {}).get("address") or "").strip().lower()
        if not settle.is_address(address):
            raise HTTPException(status_code=400, detail="address must be a 0x wallet address")
        try:
            issued_at = int((body or {}).get("issued_at"))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="issued_at must be unix seconds") from None
        if abs(time.time() - issued_at) > deposit_watch.LINK_MAX_AGE_S:
            raise HTTPException(status_code=400, detail="issued_at is more than 10 minutes from the hub's clock")
        message = deposit_watch.link_message(hub_url=config.hub_url, account_id=account_id,
                                             address=address, issued_at=issued_at)
        if not deposit_watch.signature_links_available():
            raise HTTPException(status_code=503, detail="this hub cannot check wallet signatures "
                                "(eth-account is not installed): ask the operator to link the wallet")
        if deposit_watch.signer_of(message, str((body or {}).get("signature") or "")) != address:
            raise HTTPException(status_code=403, detail="the signature is not this wallet's over the link message",
                                headers={"X-Link-Message": message.replace("\n", "\\n")})
        outcome = hub_deposits.link(address, account_id, "signature")
        if outcome == "taken":
            raise HTTPException(status_code=409, detail="this wallet is linked to another account")
        credited = await _credit_linked_now(address)
        return {"success": True, "address": address, "account_id": account_id, "linked": outcome,
                "credited_now": credited.count(deposit_watch.CREDITED), "protocol_version": "v2"}

    @router.get("/account/payer-wallets")
    async def list_payer_wallets(x_api_key: str | None = Header(default=None, alias="X-API-Key")):
        ledger = hub_credits
        account_id = ledger.resolve(x_api_key or "") if ledger is not None else ""
        if not account_id:
            raise HTTPException(status_code=401, detail="unknown or disabled X-API-Key")
        return {"success": True, "account_id": account_id, "wallets": hub_deposits.wallets(account_id),
                "deposit_watch": deposit_watch.well_known(None, config.hub_url), "protocol_version": "v2"}

    @router.post("/account/payer-wallets/unlink")
    async def unlink_payer_wallet(body: dict, x_api_key: str | None = Header(default=None, alias="X-API-Key")):
        ledger = hub_credits
        account_id = ledger.resolve(x_api_key or "") if ledger is not None else ""
        if not account_id:
            raise HTTPException(status_code=401, detail="unknown or disabled X-API-Key")
        address = str((body or {}).get("address") or "").strip().lower()
        return {"success": True, "unlinked": hub_deposits.unlink(address, account_id), "protocol_version": "v2"}

    @router.post("/accounts/{account_id}/payer-wallets")
    async def operator_link_payer_wallet(account_id: str, body: dict, authorization: str = Header(default="")):
        """Link a wallet to an account by the OPERATOR's word — e.g. a company that pays from a wallet
        whose key it will not bring to a signing tool. Transfers it already sent are credited at once."""
        _require_admin(authorization)
        if hub_credits is None or hub_credits.account(account_id) is None:
            raise HTTPException(status_code=404, detail=f"unknown account {account_id}")
        address = str((body or {}).get("address") or "").strip().lower()
        if not settle.is_address(address):
            raise HTTPException(status_code=400, detail="address must be a 0x wallet address")
        outcome = hub_deposits.link(address, account_id, "operator")
        if outcome == "taken":
            raise HTTPException(status_code=409, detail="this wallet is linked to another account")
        credited = await _credit_linked_now(address)
        return {"success": True, "address": address, "account_id": account_id, "linked": outcome,
                "credited_now": credited.count(deposit_watch.CREDITED), "protocol_version": "v2"}

    @router.get("/admin/deposits")
    async def admin_deposits(limit: int = 100, authorization: str = Header(default="")):
        """Money in the top-up wallet that no account claims yet — the operator's to-do."""
        _require_admin(authorization)
        rows = hub_deposits.open_rows(limit=page_limit(limit, maximum=DEPOSITS_PAGE_MAX))
        return {"success": True, "deposit_watch": deposit_watch.well_known(hub_deposits, config.hub_url),
                "unattributed": [r for r in rows if r["status"] == deposit_watch.UNATTRIBUTED],
                "pending": [r for r in rows if r["status"] == deposit_watch.PENDING],
                "protocol_version": "v2"}

    @router.post("/admin/deposits/{tx_hash}/resolve")
    async def admin_resolve_deposit(tx_hash: str, body: dict, authorization: str = Header(default="")):
        """The operator settled an open deposit out of band (refunded it, credited it some other way):
        it stops counting as unattributed. The note is kept on the row."""
        _require_admin(authorization)
        note = str((body or {}).get("note") or "").strip()
        if not note:
            raise HTTPException(status_code=400, detail="say how it was settled: {\"note\": \"refunded in 0x…\"}")
        tx = tx_hash.strip().lower()
        if not hub_deposits.resolve(tx, note):
            raise HTTPException(status_code=409, detail="no pending or unattributed deposit with that tx_hash")
        return {"success": True, "deposit": hub_deposits.deposit(tx), "protocol_version": "v2"}

    @router.get("/account/topups")
    async def list_topups(limit: int = 50, x_api_key: str | None = Header(default=None, alias="X-API-Key")):
        """The caller's own top-ups, newest first: USDC quotes, and card checkouts beside them."""
        ledger = hub_credits
        if not credits.enabled() or ledger is None:
            raise HTTPException(status_code=503, detail="credit accounts are off on this hub")
        account_id = ledger.resolve(x_api_key or "")
        if not account_id:
            raise HTTPException(status_code=401, detail="unknown or disabled X-API-Key")
        decimals = int((x402.asset_profile() or {}).get("decimals") or 6)
        return {"success": True, "account_id": account_id,
                "topups": [q.public(decimals, owner=True) for q in hub_topups.for_account(account_id, limit)],
                "card_topups": [card_topup.public(r, owner=True, hub_url=config.hub_url)
                                for r in hub_card_topups.for_account(account_id, limit)],
                "protocol_version": "v2"}

    # ── Card top-ups (card_topup.py): Stripe Checkout onto the same credits rail ──
    hub_card_topups = card_topup.CardTopupStore(db._conn)

    @router.post("/account/topup/card")
    async def card_topup_open(
        request: Request,
        body: dict | None = None,
        x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    ):
        """Open a Stripe Checkout for ``{"amount_usd": N}`` of credit on the key's account and
        answer its ``checkout_url``. A person pays there; the credit lands when Stripe confirms."""
        ledger = hub_credits
        if not credits.enabled() or ledger is None:
            return JSONResponse(status_code=503, content=topup.TopupError(
                503, "topup_unavailable", "credit accounts are off on this hub").body())
        account_id = ledger.resolve(x_api_key or "")
        if not account_id:
            return JSONResponse(status_code=401, content=topup.TopupError(
                401, "api_key_required",
                "send the X-API-Key of the account to credit (open one with POST /ai-market/v2/accounts)",
            ).body())
        # Each checkout is a call to Stripe on the operator's key: a budget per account.
        if not topup.verify_allowed(f"card-open:{account_id}", per_minute=6):
            return JSONResponse(status_code=429, content=topup.TopupError(
                429, "too_many_attempts", "too many checkouts opened; retry in a minute", retryable=True).body())
        answer = await _topup_offloaded(lambda: card_topup.create(
            store=hub_card_topups, account_id=account_id, amount_usd=(body or {}).get("amount_usd"),
            hub_url=config.hub_url))
        if isinstance(answer, JSONResponse):
            return answer
        return JSONResponse(status_code=201, content=answer)

    @router.get("/card-topups/{topup_id}")
    async def card_topup_read(topup_id: str, x_api_key: str | None = Header(default=None, alias="X-API-Key")):
        """Where a card top-up stands — also the page Stripe sends the buyer back to. The id
        is unguessable; the account it funds is shown only to that account's key."""
        row = hub_card_topups.get(topup_id)
        if row is None:
            return JSONResponse(status_code=404, content=topup.TopupError(
                404, "topup_unknown", "no card top-up with that id on this hub").body())
        owner = bool(x_api_key) and hub_credits is not None and hub_credits.resolve(x_api_key) == row["account_id"]
        return {"success": True, **card_topup.public(row, owner=owner, hub_url=config.hub_url),
                "protocol_version": "v2"}

    @router.post("/card-topups/{topup_id}/refresh")
    async def card_topup_refresh(topup_id: str, request: Request):
        """Ask Stripe where this checkout stands and credit it if paid: the recovery path for
        a webhook that never arrived. Open to whoever holds the id — the credit can only go to
        the account bound when the checkout was opened."""
        if not topup.verify_allowed(_topup_limit_key(request)):
            return JSONResponse(status_code=429, content=topup.TopupError(
                429, "too_many_attempts", "too many checks from this caller; retry in a minute",
                retryable=True).body())
        result = await _topup_offloaded(lambda: card_topup.refresh(
            store=hub_card_topups, ledger=hub_credits, topup_id=topup_id))
        if isinstance(result, JSONResponse):
            return result
        row = hub_card_topups.get(topup_id)
        return {"success": True, "outcome": result.get("outcome"),
                **(card_topup.public(row, hub_url=config.hub_url) if row else {}), "protocol_version": "v2"}

    @router.post("/stripe/webhook")
    async def stripe_webhook(request: Request):
        """Stripe's events. Verified by Stripe-Signature before anything is read; the figures
        that matter are checked against the checkout the hub opened (card_topup.settle_session)."""
        payload = await request.body()
        if len(payload) > 256 * 1024:
            return JSONResponse(status_code=413, content={"success": False, "error": "event_too_large"})
        if not card_topup.webhook_secret() or not credits.enabled() or hub_credits is None:
            return JSONResponse(status_code=503, content={"success": False, "error": "card_topup_unavailable"})
        result = await _topup_offloaded(lambda: card_topup.handle_webhook(
            store=hub_card_topups, ledger=hub_credits, payload=payload,
            signature=request.headers.get("Stripe-Signature", "")))
        if isinstance(result, JSONResponse):
            return result
        return {"received": True, "outcome": result.get("outcome")}

    @router.get("/account/ledger")
    async def read_credit_ledger(
        limit: int = 50,
        x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    ):
        """Every movement on the caller's own account.

        A prepaid balance is the operator holding the buyer's money; the buyer gets to see
        what happened to it without asking.
        """
        ledger = hub_credits
        if not credits.enabled() or ledger is None:
            raise HTTPException(status_code=503, detail="credit accounts are off on this hub")
        account_id = ledger.resolve(x_api_key or "")
        if not account_id:
            raise HTTPException(status_code=401, detail="unknown or disabled X-API-Key")
        return {
            "success": True,
            "account_id": account_id,
            "entries": ledger.recent(account_id, limit=limit),
            "protocol_version": "v2",
        }

    @router.post("/accounts/{account_id}/credit")
    async def credit_account(
        account_id: str, body: dict, authorization: str = Header(default=""),
    ):
        """Top up an account — OPERATOR ONLY.

        Deliberately the only way money enters the rail. Whatever the operator uses to get
        paid (a checkout, an invoice, a stablecoin transfer they watched land) calls this
        once it has the money; the hub does not pretend to have collected anything itself.
        """
        _require_admin(authorization)
        ledger = hub_credits
        if not credits.enabled() or ledger is None:
            raise HTTPException(status_code=503, detail="credit accounts are off on this hub")
        try:
            amount = float(body.get("amount_usd"))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="amount_usd must be a number") from None
        tx_hash = str(body.get("tx_hash") or "").strip().lower()
        # Older AEGIS callers sent a chain transfer as an operator grant named
        # usdc:<chain>:<tx>. Recognize that wire shape too: merely adding tx_hash
        # in the new caller would let old/new retries credit two reference names.
        supplied_reference = str(body.get("reference") or "").strip()
        legacy_usdc = re.fullmatch(r"usdc:([a-z0-9_-]+):(0x[0-9a-fA-F]{64})", supplied_reference)
        if legacy_usdc:
            reference_chain, reference_tx = legacy_usdc.groups()
            reference_tx = reference_tx.lower()
            if tx_hash and tx_hash != reference_tx:
                raise HTTPException(status_code=400, detail="USDC reference and transaction do not match")
            if body.get("chain") and str(body["chain"]).strip().lower() != reference_chain:
                raise HTTPException(status_code=400, detail="USDC reference and chain do not match")
            tx_hash = reference_tx
        if tx_hash:
            # Money that arrived on chain but that no top-up quote can match (a plain transfer,
            # a nonce this hub never minted): credited as PAID credit, and the transaction is
            # claimed in the registry every door shares, so it cannot also fund a channel or be
            # credited again — here or by a top-up redemption.
            from aimarket_hub.channels import claim_deposit_as, deposit_registry_labels

            if not settle.is_tx_hash(tx_hash):
                raise HTTPException(status_code=400, detail="tx_hash must be a 0x transaction hash")
            if ledger.account(account_id) is None:
                # Before the claim: a claim taken for a mistyped account would hold the
                # transaction against the right one.
                raise HTTPException(status_code=404, detail=f"unknown account {account_id}")
            chain_name = legacy_usdc.group(1) if legacy_usdc else str(body.get("chain") or x402.chain()).strip().lower()
            chain_id = x402.chain_id() if chain_name == x402.chain() else None
            labels = deposit_registry_labels(chain_name, chain_id)
            canonical_reference = f"chain:{labels[0]}:{tx_hash}"
            aliases = [f"{prefix}:{label}:{tx_hash}" for prefix in ("chain", "usdc") for label in labels]
            previous = ledger._conn.execute(
                "SELECT reference, account_id, amount_mc FROM credit_topups WHERE reference IN ("
                + ",".join("?" for _ in aliases) + ")", tuple(aliases),
            ).fetchall()
            if len(previous) > 1:
                raise HTTPException(status_code=409, detail="Transfer has conflicting legacy credits; operator reconciliation required")
            old_credit = previous[0] if previous else None
            if old_credit and (old_credit["account_id"] != account_id
                               or int(old_credit["amount_mc"]) != credits.usd_to_mc(amount)):
                raise HTTPException(status_code=409, detail="Transfer legacy credit belongs to another account or amount")
            claim_id = f"credit:{account_id}"
            claim = claim_deposit_as(OPERATOR_CREDIT_STACK, chain=chain_name, tx_hash=tx_hash,
                                     claim_id=claim_id, amount_cents=int(round(amount * 100)),
                                     chain_id=chain_id or None)
            held = claim.get("claim") or {}
            ours = held.get("stack") == OPERATOR_CREDIT_STACK and (
                held.get("claim_id") == claim_id or (old_credit and held.get("claim_id") == account_id)
            )
            if not claim.get("ok") and not (claim.get("error") == "already_claimed" and ours):
                raise HTTPException(status_code=409 if claim.get("error") == "already_claimed" else 503,
                                    detail=f"transaction not credited: {claim.get('error')} "
                                           f"({held.get('stack') or 'unknown door'})")
            # Reuse a committed legacy grant's exact unique reference: deposit()
            # returns its original credit without increasing the balance again.
            # New requests, including the old reference-only caller, all choose
            # the canonical reference, so racing wire versions cannot diverge.
            result = ledger.deposit(account_id, credits.usd_to_mc(amount),
                                    reference=old_credit["reference"] if old_credit else canonical_reference,
                                    note=str(body.get("note") or "operator-credited on-chain payment")[:200])
            if result.get("error"):
                # A same-account retry can finish between our claim and this
                # ledger write. Never release a shared claim on a local error:
                # it may already protect that successful concurrent credit.
                # An interrupted credit stays reserved for retry/reconciliation.
                raise HTTPException(status_code=400, detail=result["error"])
            return {"success": True, **result, "tx_hash": tx_hash, "protocol_version": "v2"}
        result = ledger.grant(
            account_id,
            amount,
            note=str(body.get("note") or "")[:200],
            reference=str(body.get("reference") or "")[:200],
        )
        if result.get("error"):
            raise HTTPException(status_code=400, detail=result["error"])
        return {"success": True, **result, "protocol_version": "v2"}

    @router.post("/accounts/{account_id}/collateral/return")
    async def return_account_collateral(
        account_id: str, body: dict, authorization: str = Header(default=""),
    ):
        """Give a publisher their posted stake back — OPERATOR ONLY.

        Until this existed, collateral had no way out of the hub at all. `POST
        /supply/stake` moves a publisher's money from `balance_mc` into `collateral_mc`,
        and the ONLY caller of `return_collateral` was the compensation on a stake the
        ledger refused. There is no unstake anywhere in the stack — `supply_security` and
        `database` know `supply_stake_add`, `_get` and `_slash`, and nothing else — so a
        publisher who staked $25 could be slashed out of it or hold it forever, and those
        were the only two endings.

        Deliberately NOT self-service. When a stake may be released is policy — a
        cooldown, whether live listings must be withdrawn first, whether a disputed
        publisher may exit — and inventing that policy inside a bug fix would be worse
        than the hole it closes. This is the same authority that puts money onto the rail
        (`/accounts/{id}/credit`) being able to take it back off collateral, so the
        operator can make a publisher whole today; a self-service unstake is a separate,
        deliberate decision.

        The ledger's own `supply_stakes` row is NOT touched here: this returns the money,
        it does not retire the stake's standing. Pass `note` to say which it was.
        """
        _require_admin(authorization)
        ledger = hub_credits
        if not credits.enabled() or ledger is None:
            raise HTTPException(status_code=503, detail="credit accounts are off on this hub")
        try:
            amount = float(body.get("amount_usd"))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="amount_usd must be a number") from None
        account = ledger.account(account_id)
        if account is None:
            raise HTTPException(status_code=404, detail=f"unknown account {account_id}")
        posted = float(account.get("collateral_usd") or 0.0)
        if amount > posted + 1e-9:
            # `return_collateral` floors collateral at zero and would credit the whole
            # amount to spendable balance anyway, inventing money out of a typo.
            raise HTTPException(
                status_code=400,
                detail=f"account holds ${posted:.6f} of collateral, cannot return ${amount:.6f}",
            )
        result = ledger.return_collateral(
            account_id, amount, note=str(body.get("note") or "operator return")[:200],
        )
        if result.get("error"):
            raise HTTPException(status_code=400, detail=result["error"])
        return {"success": True, **result, "protocol_version": "v2"}

    @router.post("/accounts/{account_id}/status")
    async def set_credit_account_status(
        account_id: str, body: dict, authorization: str = Header(default=""),
    ):
        _require_admin(authorization)
        ledger = hub_credits
        if not credits.enabled() or ledger is None:
            raise HTTPException(status_code=503, detail="credit accounts are off on this hub")
        result = ledger.set_status(account_id, str(body.get("status") or ""))
        if result.get("error"):
            raise HTTPException(status_code=400, detail=result["error"])
        return {"success": True, **result, "protocol_version": "v2"}

    return SimpleNamespace(
        _deposit_watcher=_deposit_watcher,
    )
