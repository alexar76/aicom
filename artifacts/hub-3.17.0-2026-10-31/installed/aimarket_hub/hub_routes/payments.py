"""Paying for a call: publisher shares, hearth owners, payees bound to a call, market
settlement and release, and the payment hints a 402 carries.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

import httpx
from fastapi import HTTPException, Request

from aimarket_hub import credits, settle, topup, x402
from aimarket_hub.config import HubConfig
from aimarket_hub.credits import CreditsLedger
from aimarket_hub.settle import InvoiceStore, PaymentStore as SettlePaymentStore
from aimarket_hub.signing import Signer


def register(
    *,
    _is_admin_bearer: Callable[..., Any],
    config: HubConfig,
    hub_credits: CreditsLedger,
    hub_invoices: InvoiceStore,
    hub_settle: SettlePaymentStore,
) -> SimpleNamespace:
    """Build the payment helpers the invoke routes use."""
    # api.py's module-level helpers; imported here because api.py imports this module.
    from aimarket_hub.api import (
        OPERATOR_SELF_CONSUMER,
        _SAFE_ID_CHARS,
        logger,
    )

    def _pay_publisher_share(cap: Any, price_usd: float, receipt_id: str) -> None:
        """Credits-rail residual only. Catalogue sales pay the seller on-chain.

        A wallet publisher is paid by ``payout_address``, not by a silent credit.
        This helper remains for a buyer who prepaid in credits: if the publisher
        also holds a credit account, they can be book-kept here. It never
        substitutes for the market rail and never claims a wallet seller
        "cannot be paid".
        """
        if price_usd <= 0 or config.publisher_share_bps <= 0:
            return
        publisher_id = str(getattr(cap, "publisher_id", "") or "").strip()
        if not publisher_id or not credits.enabled():
            return
        if hub_credits.account(publisher_id) is None:
            return
        share = round(price_usd * config.publisher_share_bps / 10000, 6)
        if share <= 0:
            return
        try:
            result = hub_credits.pay_publisher(
                publisher_id, share, receipt_id=receipt_id, note="capability sale",
            )
        except Exception as exc:  # noqa: BLE001 - never fail a delivered call on a payout
            logger.error("payout: crediting %s failed: %s", publisher_id, exc)
            return
        if result.get("error"):
            logger.error("payout: crediting %s failed: %s", publisher_id, result["error"])
        else:
            logger.info(
                "payout: %s earned $%.6f (%d bps of $%.6f)",
                publisher_id, share, config.publisher_share_bps, price_usd,
            )

    def _credit_hearth_owner(peer: Any, bill: Any, capability_id: str, charged_usd: float) -> None:
        """Pay a hearth tenant's owner their share of what this hub charged its buyer.

        The hearth served the call on this hub's key because the owner chose this hub and named
        a credit account here (hestia/hub_billing.py). Its `hub_billing` block is signed by the
        hearth's provider key, which this hub pinned when it indexed the hearth, so the account
        to credit is the owner's word, carried by a key nobody else holds. The amount is never
        the hearth's number: it is AIMARKET_PUBLISHER_SHARE_BPS of what THIS hub captured.
        An operator tenant names no account, and the hub keeps what it charged.
        """
        if not isinstance(bill, dict):
            return
        account = str(bill.get("bill_to_account") or "")
        if not account:
            return
        if str(bill.get("hub") or "").rstrip("/") != (config.hub_url or "").rstrip("/"):
            logger.error("hearth bill from %s names hub %r, not this hub — not credited",
                         peer.url, bill.get("hub"))
            return
        if bill.get("capability_id") != capability_id:
            logger.error("hearth bill from %s is for %r, not %r — not credited",
                         peer.url, bill.get("capability_id"), capability_id)
            return
        if not Signer.verify_object_signature(
            bill, getattr(peer, "public_key", "") or "",
            pq_public_key_b64=getattr(peer, "pq_public_key", "") or None,
        ):
            logger.error("hearth bill from %s does not verify against its pinned key — "
                         "not credited", peer.url)
            return
        share = round(charged_usd * config.publisher_share_bps / 10000, 6)
        if share <= 0 or not credits.enabled():
            return
        try:
            result = hub_credits.pay_publisher(
                account, share, receipt_id=f"hearth:{bill.get('id', '')}",
                note=f"hearth owner share: {peer.url} {bill.get('slug', '')}",
            )
        except Exception as exc:  # noqa: BLE001 - never fail a delivered call on a payout
            logger.error("hearth owner payout to %s failed: %s", account, exc)
            return
        if result.get("error"):
            logger.error("hearth owner payout to %s failed: %s", account, result["error"])
        else:
            logger.info("hearth owner %s earned $%.6f for %s via %s",
                        account, share, capability_id, peer.url)

    def _bind_listing_payee(request: Request, cap: Any) -> str:
        """Publish the seller on this request so a 402 names their wallet."""
        pay_to = settle.seller_pay_to(cap, operator_pay_to=x402.recipient())
        request.state.x402_pay_to = pay_to
        request.state.x402_capability_id = getattr(cap, "capability_id", "") or ""
        request.state.x402_price = float(getattr(cap, "price_per_call_usd", 0) or 0)
        return pay_to

    def _bind_hub_fee_payee(request: Request, fee_usd: float) -> None:
        """This 402 is for the HUB's routing fee, so it must name the hub's wallet.

        The federated broker path binds the listing's payee early, because most of its
        402s are about the sale. The routing-fee refusal is not: `needed` there is the
        hub's own 1% for brokering somebody else's capability, and it was inheriting the
        seller's address — so the offer asked the buyer to pay the hub's fee TO THE
        SELLER. The hub got nothing and the seller got an extra percent.
        """
        request.state.x402_pay_to = settle.fee_recipient()
        request.state.x402_price = float(fee_usd or 0)

    def _unbind_payee(request: Request) -> None:
        """No single payee can express this offer, so make no on-chain offer.

        A total of "list price plus routing fee" is owed to two different addresses and
        x402's `exact` scheme has one `payTo`. Naming the seller hands them the hub's
        fee; naming the hub makes it custody the seller's price. An empty payee produces
        no `accepts` at all, which leaves the buyer the rails that CAN express it — the
        channel and credit ways already in the body.
        """
        request.state.x402_pay_to = ""

    def _settle_market_payment(
        *,
        raw: str,
        payload: dict | None,
        cap: Any,
        price_usd: float,
        capability_id: str,
        header_nonce: str = "",
        header_secret: str = "",
    ) -> dict:
        """Verify the buyer paid this listing's seller on-chain.

        Accepts a bare tx hash (HESTIA) or an x402 PAYMENT-SIGNATURE that
        names the same payee and carries the settle transaction. A signature
        without a chain receipt is not a payment.
        """
        terms = settle.terms_for(cap, operator_pay_to=x402.recipient())
        if terms is None:
            return {"error": "this listing has no seller payout_address"}
        ref = settle.extract_payment_ref(raw, payload)
        tx_hash = ref["tx_hash"]
        nonce = (header_nonce or ref["nonce"] or "").strip().lower()
        inner = (payload or {}).get("payload") if isinstance((payload or {}).get("payload"), dict) else {}
        if (payload or {}).get("authorization") or inner.get("authorization"):
            checked = x402.verify_payment(payload or {}, price_usd=price_usd, pay_to=terms.pay_to)
            if not checked.get("ok"):
                return {"error": checked.get("error") or "payment could not be verified"}
            nonce = nonce or str(checked.get("nonce") or "")
        if not tx_hash:
            return {"error": (
                "pay USDC on-chain to the seller payout_address, then retry with "
                "X-Payment: <tx hash> (and X-Payment-Nonce from the 402)"
            )}
        secret = (header_secret or "").strip().lower()
        if not nonce and settle.is_nonce(secret):
            nonce = settle.nonce_for_secret(secret)
        if not settle.is_nonce(nonce):
            # A plain transfer to the seller says nothing about who paid: its hash is public
            # once mined, so whoever presented it first would take the call.
            return {"error": (
                "send X-Payment-Nonce with the nonce from this 402 and pay with "
                "transferWithAuthorization signed over it"
            )}
        if hub_settle.seen_nonce(nonce):
            return {"error": "this authorization has already been used"}
        if not settle.opens(secret, nonce):
            # The nonce and the transaction are public once mined: anyone could present
            # them. Only the caller who took the 402 holds what opens the nonce.
            return {"error": (
                "send X-Payment-Secret with the payment_secret from the 402 you paid: the "
                "nonce and the transaction are public once mined, so they cannot show who paid"
                if not secret else "that payment secret does not open this payment nonce"
            )}
        invoice = hub_invoices.get(nonce)
        if invoice is None:
            return {"error": "unknown payment nonce"}
        quoted_for = str(invoice.get("capability_id") or "")
        if quoted_for and quoted_for != capability_id:
            # A 402 quotes one call; its payment buys that call, not another the same
            # seller lists at the same price or less.
            return {"error": f"that invoice was quoted for {quoted_for}, not {capability_id}"}
        if float(invoice.get("consumed_at") or 0) > 0:
            return {"error": "that payment nonce has already been spent"}
        expired = time.time() > float(invoice["expires_at"])
        if str(invoice.get("pay_to") or "").lower() != terms.pay_to.lower():
            return {"error": "payment is addressed to somebody else"}
        if int(invoice["amount_units"]) > terms.amount_units:
            terms = settle.PaymentTerms(
                **{**terms.__dict__, "amount_units": int(invoice["amount_units"])}
            )
        try:
            settled = settle.verify_transfer(
                tx_hash=tx_hash,
                terms=terms,
                max_age_s=settle.max_age_s(),
                paid_before=float(invoice["expires_at"]) if expired else None,
                require_nonce=nonce,
            )
        except settle.PaymentError as exc:
            return {"error": str(exc)}
        except httpx.HTTPError:
            raise HTTPException(
                status_code=503, detail="payment verifier unavailable",
            ) from None
        if not hub_invoices.consume(nonce, settled["tx_hash"]):
            return {"error": "that payment nonce has already been spent"}
        if not hub_settle.claim(
            tx_hash=settled["tx_hash"],
            pay_to=terms.pay_to,
            payer=settled.get("authorizer") or "",
            amount_usd=price_usd,
            amount_atomic=settled["paid_units"],
            asset=terms.token_contract,
            network=terms.chain,
            capability_id=capability_id,
            nonce=nonce,
        ):
            hub_invoices.release(nonce)
            return {"error": "that payment has already been spent on another call"}
        logger.info(
            "settle: $%.6f USDC to seller %s for %s tx=%s",
            price_usd, terms.pay_to, capability_id, settled["tx_hash"],
        )
        return {
            "ok": True,
            "tx_hash": settled["tx_hash"],
            "pay_to": terms.pay_to,
            "amount_usd": price_usd,
            "payer": settled.get("authorizer") or "",
            "nonce": nonce,
            "rail": "seller_direct",
        }

    def _release_market_payment(accepted: object) -> None:
        """Un-spend a verified seller-direct payment when the call is refused unserved.

        The money itself cannot come back: this rail pays the seller's wallet directly and
        the Hub is not in the transaction. What the Hub can do, and did not, is stop
        CONSUMING the buyer's claim. `_settle_market_payment` burns both replay keys the
        moment the receipt verifies — `hub_invoices.consume` and `hub_settle.claim` — and
        every refusal after that point (a short input, a safety block, a provider 502, a
        failed capture) left the buyer having paid for a call that never ran, holding a
        nonce and a tx hash that could never be presented again.

        Releasing them restores the only compensation seller-direct can offer: the payment
        stays redeemable, so the buyer retries the same money instead of paying twice. The
        one place that already did this — `hub_settle.claim` failing on an
        already-spent tx — shows the shape was understood; it was just never wired to the
        exits that actually happen.

        Never raises: it runs from `finally`, where an exception would mask the real error.
        """
        if not isinstance(accepted, dict) or accepted.get("error") or not accepted.get("ok"):
            return
        try:
            nonce = str(accepted.get("nonce") or "")
            if nonce:
                hub_invoices.release(nonce)
            tx_hash = str(accepted.get("tx_hash") or "")
            if tx_hash:
                hub_settle.release(tx_hash, nonce)
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "invoke: releasing the seller-direct payment %s raised: %s",
                str(accepted.get("tx_hash") or "")[:18], exc,
            )
        else:
            logger.info(
                "invoke: released unserved seller-direct payment %s (nonce %s) — the "
                "buyer's money is with the seller and the claim is redeemable again",
                str(accepted.get("tx_hash") or "")[:18], str(accepted.get("nonce") or "")[:18],
            )

    def _payment_hint(credits_on: bool, crypto_on: bool, *, seller: bool = True) -> str:
        """What a 402 should actually tell the payer.

        The old text named one header and stopped ("X-Payment-Channel required"), which on a
        hub with the chain switched off described a rail the caller could not reach: opening
        a channel needs a funded escrow the operator may never have deployed. A 402 that does
        not name a reachable way to pay is a dead end, so this reports the rails THIS hub has
        actually got switched on.
        """
        # With signup closed, POST /accounts answers 403: naming it sent every buyer to a
        # door that refuses them. Keys then exist only as the operator issues them.
        key_source = (
            f"from {config.hub_url}/start or POST {config.hub_url}/ai-market/v2/accounts"
            if credits.signup_open() else "issued by this hub's operator (signup is closed)"
        )
        if topup.enabled():
            key_source += f", funded with USDC at POST {config.hub_url}/ai-market/v2/account/topup"

        if not seller:
            # No wallet to pay for this listing (`seller_pay_to` is empty), so naming the
            # on-chain rail sent the buyer to an address that does not exist. Measured on a
            # hub set up by the operator quickstart, 2026-10-12.
            rails = []
            if credits_on:
                rails.append(f"send X-API-Key for a credit account ({key_source})")
            if crypto_on:
                rails.append("send X-Payment-Channel")
            if rails:
                return "payment required — " + ", or ".join(rails)
            return "payment required — this listing has no payout wallet and no other rail is on"

        if credits_on and crypto_on:
            return (
                "payment required — pay USDC on-chain to the seller payout_address "
                "(X-Payment / PAYMENT-SIGNATURE), or send X-API-Key for a credit account "
                f"({key_source}) or X-Payment-Channel"
            )
        if credits_on:
            return (
                "payment required — pay USDC on-chain to the seller payout_address "
                f"(X-Payment: <tx hash>), or send X-API-Key {key_source}"
            )
        return (
            "payment required — pay USDC on-chain to the seller payout_address, "
            "then retry with X-Payment: <tx hash> or PAYMENT-SIGNATURE"
        )

    def _pays_a_third_party(cap: Any) -> bool:
        """Does settling this listing send money OUT of the hub, to somebody else?

        The credit line is the operator's own resource: money taken in once and issued
        as a limit, most of it granted outright so a new project can try the catalogue
        for free. Spending that limit on a listing whose seller must be paid for real
        would mean the operator pays a stranger, in USDC, out of pocket, for a call the
        buyer got as a gift — and `_pay_publisher_share` cannot even book it, because a
        wallet is not a credit account, so today it is simply dropped and the operator
        keeps 100% of somebody else's sale.

        So the rule is the plain one: a credit line buys the operator's OWN resources.
        Anything with an external payee is bought on the rail that actually pays them.

        `seller_pay_to` is the same resolver settlement uses, so this cannot drift from
        who really gets paid: it answers empty for an operator-owned listing and for a
        named publisher booked inside the ledger, and an address for a listing that
        names one. An address equal to the operator's own recipient is the operator
        selling their own work and is not a third party.
        """
        try:
            payee = settle.seller_pay_to(cap, operator_pay_to=x402.recipient())
        except Exception:  # noqa: BLE001 - never fail an invoke on a policy lookup
            return False
        payee = str(payee or "").strip()
        if not payee:
            return False
        own = str(x402.recipient() or "").strip()
        return payee.lower() != own.lower()

    def _payment_ways(credits_on: bool, crypto_on: bool, *, seller: bool = True) -> dict[str, Any]:
        """Machine-readable twin of the hint, so an agent can act on a 402 without parsing prose.

        ``seller=False``: the listing has no wallet to pay (see `_payment_hint`), so the
        on-chain rail is not offered at all.
        """
        ways: list[dict[str, Any]] = []
        if seller:
            ways.append({
                "rail": "seller_direct",
                "header": "X-Payment",
                "also": ["PAYMENT-SIGNATURE", "X-PAYMENT", "X-Payment-Nonce"],
                "asset": "USDC",
                "note": "pay the listing payout_address on-chain; the hub never holds the money",
            })
        if credits_on:
            ways.append({
                "rail": "credits",
                "header": "X-API-Key",
                "signup": f"{config.hub_url}/ai-market/v2/accounts",
                "open_signup": credits.signup_open(),
                **({"topup": f"{config.hub_url}/ai-market/v2/account/topup"} if topup.enabled() else {}),
                # The human door to the same three calls: key, client config, top-up.
                **({"start": f"{config.hub_url}/start"} if credits.signup_open() else {}),
            })
        if crypto_on:
            ways.append({
                "rail": "channel",
                "header": "X-Payment-Channel",
                "open": f"{config.hub_url}/ai-market/v2/channel/open",
            })
        return {"payment_ways": ways}

    def _resolve_invoke_consumer_hub(
        *,
        x_sandbox_visitor: str | None = None,
        x_payment_channel: str | None = None,
        authorization: str = "",
        credit_account: str = "",
        x402_paid: bool = False,
        mcp_caller: str | None = None,
    ) -> str:
        """Who to credit on InvocationStat.consumer_hub for /stats/live.

        - Admin Bearer smoke → ``operator_self`` (does not count as external)
        - Paying channel → ``channel:<id>`` (external)
        - Credit account (X-API-Key, or the account a mandate/job draws on) →
          ``account:<id>`` (external unless ecosystem.json lists it under self.accounts,
          or AIMARKET_OPERATOR_ACCOUNTS does)
        - x402 / tx-hash payment → ``x402`` (external)
        - Sandbox visitor → ``sandbox:<id>`` (external)
        - Hub's own /mcp gateway → ``mcp:<visitor digest>`` (external)
        - Else → ``anonymous`` (external)

        Keeps the live feed honest: an agent or browser trial is demand, not
        the operator testing their own hub. SELF vs EXT itself is decided in
        ecosystem.py, from this label plus what the write site knew (caller_class). Every rail but the channel used to fall
        through to ``anonymous`` — so the credits accounts that carried every priced call
        on modelmarket.dev (PingBlip, the weather-witness desk) read as strangers.

        The sandbox and MCP labels come from unauthenticated headers: they group rows on a
        public feed and decide nothing else. ``account:`` is authenticated (the key resolved).
        """
        if _is_admin_bearer(authorization):
            return OPERATOR_SELF_CONSUMER

        def _label(prefix: str, raw: str) -> str:
            cleaned = "".join(c for c in raw.strip() if c in _SAFE_ID_CHARS)[:64]
            return f"{prefix}:{cleaned}" if cleaned else prefix

        if x_payment_channel and x_payment_channel.strip():
            return _label("channel", x_payment_channel)
        if credit_account and credit_account.strip():
            return _label("account", credit_account)
        if x402_paid:
            return "x402"
        if x_sandbox_visitor and x_sandbox_visitor.strip():
            return _label("sandbox", x_sandbox_visitor)
        if mcp_caller and mcp_caller.strip():
            return _label("mcp", mcp_caller)
        return "anonymous"

    return SimpleNamespace(
        _bind_hub_fee_payee=_bind_hub_fee_payee,
        _bind_listing_payee=_bind_listing_payee,
        _credit_hearth_owner=_credit_hearth_owner,
        _pay_publisher_share=_pay_publisher_share,
        _payment_hint=_payment_hint,
        _payment_ways=_payment_ways,
        _pays_a_third_party=_pays_a_third_party,
        _release_market_payment=_release_market_payment,
        _resolve_invoke_consumer_hub=_resolve_invoke_consumer_hub,
        _settle_market_payment=_settle_market_payment,
        _unbind_payee=_unbind_payee,
    )
