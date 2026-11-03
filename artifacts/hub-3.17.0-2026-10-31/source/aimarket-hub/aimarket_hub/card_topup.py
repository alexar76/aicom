"""Buying credits with a card — Stripe Checkout, the second self-serve door onto the credits rail.

``topup.py`` lets an agent with a USDC wallet fund its account. A person with a card and no
wallet could not, so a stranger who found the hub and wanted to try a paid capability had to
open a wallet first. This door takes a card the way every shop does, and lands the money on
the same ledger line a USDC top-up does (``CreditsLedger.deposit``: paid credit, ``topup``).

The flow:

1. **Session.** ``POST /ai-market/v2/account/topup/card`` with the account's ``X-API-Key`` and
   ``{"amount_usd": 10}`` opens a Stripe Checkout Session for exactly that amount (plus the
   operator's card fee, if one is set, shown before paying) and answers its ``checkout_url``.
   The account is bound here, in ``card_topups``; Stripe learns only the top-up id.
2. **Pay.** A person opens the URL and pays on Stripe's page. No card number ever reaches
   the hub (PCI scope stays with Stripe).
3. **Credit.** Stripe calls ``POST /ai-market/v2/stripe/webhook``. The hub checks the
   ``Stripe-Signature`` (HMAC-SHA256 over ``t.payload`` with the endpoint secret, five
   minutes' tolerance), then the session itself against the row it opened: same session id,
   ``usd``, the exact amount, ``paid``, and live money only when the key is live. Then it
   credits the bound account, once: the ledger reference is the session id.

**Who owes the sales tax** is the operator's choice (``AIMARKET_CARD_TOPUP_TAX``), decided
per checkout and kept on its row, so a hub that changes the setting never re-checks an older
checkout under the new rule:

* ``off`` (default) — no tax is computed; the operator is the seller and handles VAT itself.
* ``stripe_tax`` — Stripe Tax computes it (``automatic_tax``) from the billing address the
  page collects; the operator stays the seller and must have its registrations in Stripe.
* ``managed_payments`` — Stripe is the merchant of record: it computes, collects and remits
  the tax, handles disputes and may refund within 60 days. Needs Managed Payments switched on
  in the Dashboard, an eligible product tax code and a newer API version.

With tax, the credit is still the amount the buyer asked for: tax is the state's, not the
buyer's balance. ``AIMARKET_CARD_TOPUP_TAX_BEHAVIOR`` says whether it is added on top
(``exclusive``, default) or already inside the price (``inclusive``).

A webhook can be lost. ``POST /card-topups/{id}/refresh`` asks Stripe for the session and runs
the same check, so a paid top-up is never stranded on a delivery failure.

Verified refunds and disputes freeze new credit spending until a trusted operator reviews
the account. Balances and existing reservations are preserved for reconciliation; this door
does not issue refunds or take credit back. Credit already spent cannot be recalled by the
hub, which is why the per-account daily limit also exists.

Off unless ``AIMARKET_CARD_TOPUP_ENABLED=1`` and both Stripe secrets are set
(``AIMARKET_STRIPE_SECRET_KEY[_FILE]``, ``AIMARKET_STRIPE_WEBHOOK_SECRET[_FILE]``).
Standalone deployments also accept legacy ``STRIPE_*`` names. Guide: docs/card-topup.md.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import time
from typing import Any, Callable

from aimarket_hub import credits
from aimarket_hub.db_backend import atomic, returning_one
from aimarket_hub.paging import page_limit
from aimarket_hub.topup import TopupError, cents

logger = logging.getLogger(__name__)

STRIPE_API = "https://api.stripe.com"
#: Stripe accepts a Checkout Session expiry between 30 minutes and 24 hours from now.
SESSION_TTL_S = 3600
SIGNATURE_TOLERANCE_S = 300
NEW, OPEN, CREDITED, EXPIRED, FAILED, DISPUTED = "new", "open", "credited", "expired", "failed", "disputed"
REFUNDED = "refunded"
TAX_OFF, STRIPE_TAX, MANAGED_PAYMENTS = "off", "stripe_tax", "managed_payments"
TAX_MODES = (TAX_OFF, STRIPE_TAX, MANAGED_PAYMENTS)
#: The API version every call is pinned to; Managed Payments needs 2025-03-31.basil or later.
STRIPE_VERSION = "2024-06-20"
STRIPE_VERSION_MANAGED = "2025-03-31.basil"
#: "General - Electronically Supplied Services": the broadest code Managed Payments accepts.
DEFAULT_TAX_CODE = "txcd_10000000"
_ID_PREFIX = "ctp_"
PAID_EVENTS = ("checkout.session.completed", "checkout.session.async_payment_succeeded")
#: Card top-ups one account read may return.
CARD_TOPUPS_PAGE_MAX = 200


# ── configuration ────────────────────────────────────────────────────────────


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _secret(name: str) -> str:
    """A secret from ``<NAME>_FILE`` (a docker secret) or ``<NAME>``. Never logged."""
    path = (os.getenv(f"{name}_FILE") or "").strip()
    if path:
        try:
            with open(path, encoding="utf-8") as handle:
                return handle.read().strip()
        except OSError:
            logger.error("card top-up: %s_FILE is set but unreadable", name)
            return ""
    return (os.getenv(name) or "").strip()


def _stripe_secret(name: str) -> str:
    """Prefer service-scoped credentials; a configured but unreadable secret stays closed."""
    scoped = f"AIMARKET_{name}"
    if scoped in os.environ or f"{scoped}_FILE" in os.environ:
        return _secret(scoped)
    return _secret(name)


def secret_key() -> str:
    return _stripe_secret("STRIPE_SECRET_KEY")


def webhook_secret() -> str:
    return _stripe_secret("STRIPE_WEBHOOK_SECRET")


def switched_on() -> bool:
    return os.getenv("AIMARKET_CARD_TOPUP_ENABLED", "0").strip().lower() in ("1", "true", "yes", "on")


def min_usd() -> float:
    # Stripe's own floor for a USD charge is $0.50; a top-up below a few dollars is mostly fee.
    return max(0.5, _float("AIMARKET_CARD_TOPUP_MIN_USD", 5.0))


def max_usd() -> float:
    return max(min_usd(), _float("AIMARKET_CARD_TOPUP_MAX_USD", 100.0))


def daily_usd() -> float:
    """Most one account may buy by card in 24 hours. A card can be stolen and a charge
    disputed after the credit is spent; this bounds what one account can lose the operator."""
    return max(min_usd(), _float("AIMARKET_CARD_TOPUP_DAILY_USD", 200.0))


def fee_pct() -> float:
    """A surcharge the buyer pays on top, in percent, to cover the card processor's fee.
    0 by default: the operator absorbs it. Where surcharging cards is restricted, keep 0."""
    return min(10.0, max(0.0, _float("AIMARKET_CARD_TOPUP_FEE_PCT", 0.0)))


def fee_fixed_usd() -> float:
    return min(5.0, max(0.0, _float("AIMARKET_CARD_TOPUP_FEE_FIXED_USD", 0.0)))


def tax_mode() -> str:
    """Who computes the sales tax on a card top-up; "" when the setting names no known mode
    (the door then stays shut rather than guess)."""
    value = (os.getenv("AIMARKET_CARD_TOPUP_TAX") or TAX_OFF).strip().lower()
    return value if value in TAX_MODES else ""


def tax_code() -> str:
    value = (os.getenv("AIMARKET_CARD_TOPUP_TAX_CODE") or DEFAULT_TAX_CODE).strip()
    return value if re.fullmatch(r"txcd_\d{8}", value) else ""


def tax_behavior() -> str:
    value = (os.getenv("AIMARKET_CARD_TOPUP_TAX_BEHAVIOR") or "exclusive").strip().lower()
    return value if value in ("exclusive", "inclusive") else ""


def unavailable_reason() -> str:
    if not switched_on():
        return "card top-ups are switched off on this hub (AIMARKET_CARD_TOPUP_ENABLED)"
    if not credits.enabled():
        return "the credits rail is switched off on this hub"
    if not secret_key():
        return "this hub has no Stripe secret key (STRIPE_SECRET_KEY)"
    if not webhook_secret():
        return "this hub has no Stripe webhook secret (STRIPE_WEBHOOK_SECRET)"
    if not tax_mode():
        return f"AIMARKET_CARD_TOPUP_TAX must be one of {', '.join(TAX_MODES)}"
    if tax_mode() != TAX_OFF and not tax_code():
        return "AIMARKET_CARD_TOPUP_TAX_CODE must be a Stripe tax code such as txcd_10000000"
    if tax_mode() != TAX_OFF and not tax_behavior():
        return "AIMARKET_CARD_TOPUP_TAX_BEHAVIOR must be exclusive or inclusive"
    return ""


def enabled() -> bool:
    return not unavailable_reason()


def well_known() -> dict[str, Any]:
    """The ``payment_rails.credits.topup_card`` block of ``/.well-known/ai-market.json``."""
    out: dict[str, Any] = {"enabled": enabled(), "provider": "stripe-checkout",
                           "create": "/ai-market/v2/account/topup/card", "status": "/ai-market/v2/card-topups/{id}"}
    if enabled():
        out.update({"currency": "usd", "min_usd": min_usd(), "max_usd": max_usd(), "daily_usd": daily_usd(),
                    "fee_pct": fee_pct(), "fee_fixed_usd": fee_fixed_usd(), "tax": {"mode": tax_mode()}})
        if tax_mode() != TAX_OFF:
            # A buyer should know before paying whether tax comes on top of the figure it asked.
            out["tax"].update({"behavior": tax_behavior(), "seller_of_record":
                               "stripe" if tax_mode() == MANAGED_PAYMENTS else "operator"})
    else:
        out["reason"] = unavailable_reason()
    return out


def fee_cents(amount_cents: int) -> int:
    """The surcharge on a top-up, rounded UP to the cent: the buyer is shown it before paying."""
    pct = fee_pct()
    variable = -(-int(amount_cents) * round(pct * 100) // 10_000) if pct else 0
    return variable + round(fee_fixed_usd() * 100)


# ── Stripe over HTTP ─────────────────────────────────────────────────────────


def _form(obj: dict[str, Any], prefix: str = "") -> list[tuple[str, str]]:
    """Stripe's form encoding: nested keys as ``a[b][0][c]``."""
    out: list[tuple[str, str]] = []
    for key, value in obj.items():
        name = f"{prefix}[{key}]" if prefix else str(key)
        if isinstance(value, dict):
            out.extend(_form(value, name))
        elif isinstance(value, list):
            out.extend(_form({str(i): v for i, v in enumerate(value)}, name))
        elif value is not None:
            out.append((name, str(value).lower() if isinstance(value, bool) else str(value)))
    return out


def _stripe_request(method: str, path: str, *, form: dict[str, Any] | None = None,
                    idempotency_key: str = "", version: str = STRIPE_VERSION) -> tuple[int, dict[str, Any]]:
    """One call to Stripe's API with the hub's secret key. Blocking: callers are off the loop."""
    from urllib.parse import urlencode

    import httpx

    headers = {"Authorization": f"Bearer {secret_key()}", "Stripe-Version": version}
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    body = None
    if form is not None:
        # Encoded here, not passed as `data=`: httpx takes `data` as a mapping only, and a
        # list of pairs (needed for Stripe's repeated nested keys) is read as a byte stream.
        body = urlencode(_form(form)).encode("ascii")
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    with httpx.Client(timeout=20.0, follow_redirects=False) as client:
        response = client.request(method, f"{STRIPE_API}{path}", headers=headers, content=body)
    try:
        body = response.json()
    except ValueError:
        body = {}
    return response.status_code, body if isinstance(body, dict) else {}


def verify_signature(payload: bytes, header: str, secret: str, *, now: float | None = None,
                     tolerance_s: int = SIGNATURE_TOLERANCE_S) -> bool:
    """Stripe's webhook signature: ``t=<unix>,v1=<hex HMAC-SHA256 of "t.payload">`` (several v1
    while a secret is being rolled). Fresh within ``tolerance_s``, compared in constant time."""
    if not secret or not header:
        return False
    stamp = ""
    signatures: list[str] = []
    for item in header.split(","):
        key, _, value = item.strip().partition("=")
        if key == "t":
            stamp = value
        elif key == "v1" and value:
            signatures.append(value)
    if not stamp.isdigit() or not signatures:
        return False
    now = time.time() if now is None else now
    if abs(now - int(stamp)) > tolerance_s:
        return False
    want = hmac.new(secret.encode(), f"{stamp}.".encode() + payload, hashlib.sha256).hexdigest()
    return any(hmac.compare_digest(want, s) for s in signatures)


# ── storage ──────────────────────────────────────────────────────────────────


class CardTopupStore:
    """``card_topups``: conditional transitions, with reversal freezes in one transaction."""

    def __init__(self, conn: Any):
        self._conn = conn

    def _write(self, sql: str, params: tuple) -> bool:
        """One statement and its commit in ONE critical section of the shared connection.
        Taken as two, another thread's failing statement between them rolls the write back:
        a checkout handed to its buyer whose row never learned its session id could never be
        credited, however the payment went."""
        return returning_one(self._conn, f"{sql} RETURNING topup_id", params, commit=True) is not None

    def open_new(self, *, account_id: str, amount_cents: int, charge_cents: int, tax: str = TAX_OFF,
                 behavior: str = "", now: float | None = None) -> dict[str, Any]:
        now = time.time() if now is None else now
        topup_id = f"{_ID_PREFIX}{secrets.token_hex(12)}"
        self._write(
            "INSERT INTO card_topups (topup_id, account_id, amount_cents, charge_cents, status, created_at, "
            "expires_at, tax_mode, tax_behavior) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (topup_id, account_id, int(amount_cents), int(charge_cents), NEW, now, now + SESSION_TTL_S,
             tax, behavior),
        )
        row = self.get(topup_id)
        assert row is not None
        return row

    def get(self, topup_id: str) -> dict[str, Any] | None:
        if not is_topup_id(topup_id):
            return None
        row = self._conn.execute("SELECT * FROM card_topups WHERE topup_id = ?", (topup_id,)).fetchone()
        return dict(row) if row else None

    def by_payment_intent(self, payment_intent: str) -> dict[str, Any] | None:
        if not payment_intent:
            return None
        row = self._conn.execute(
            "SELECT * FROM card_topups WHERE payment_intent = ?", (payment_intent,),
        ).fetchone()
        return dict(row) if row else None

    def opened(self, topup_id: str, *, session_id: str, checkout_url: str, livemode: bool) -> None:
        self._write(
            "UPDATE card_topups SET status = ?, session_id = ?, checkout_url = ?, livemode = ? "
            "WHERE topup_id = ? AND status = ?",
            (OPEN, session_id, checkout_url, 1 if livemode else 0, topup_id, NEW),
        )

    def failed(self, topup_id: str, detail: str) -> None:
        self._write(
            "UPDATE card_topups SET status = ?, detail = ? WHERE topup_id = ? AND status = ?",
            (FAILED, detail[:300], topup_id, NEW),
        )

    def discard(self, topup_id: str) -> None:
        """A row that never reached Stripe and never will (refused before opening)."""
        self._write("DELETE FROM card_topups WHERE topup_id = ? AND status = ?", (topup_id, NEW))

    def credited(self, topup_id: str, *, payment_intent: str, credited_mc: int, tax_cents: int = 0,
                 detail: str = "", now: float | None = None) -> bool:
        won = returning_one(
            self._conn,
            "UPDATE card_topups SET status = ?, payment_intent = ?, credited_mc = ?, tax_cents = ?, credited_at = ?, "
            "detail = ? WHERE topup_id = ? AND status IN (?, ?) RETURNING topup_id",
            (CREDITED, payment_intent, int(credited_mc), int(tax_cents), time.time() if now is None else now,
             detail[:300], topup_id, OPEN, EXPIRED),
            commit=True,
        )
        return won is not None

    def expired(self, topup_id: str) -> None:
        self._write("UPDATE card_topups SET status = ? WHERE topup_id = ? AND status = ?", (EXPIRED, topup_id, OPEN))

    def _review_reversal(self, topup_id: str, status: str, detail: str) -> bool:
        """Freeze new spending with the reversal, atomically and once per transition.

        Money stays in the ledger for reconciliation. Only the existing admin
        account-status route can reactivate the account; duplicate webhooks must
        not undo a later trusted reconciliation. In-flight holds can still settle
        or release, but cannot fund NEW subcontracted calls.
        """
        allowed = (CREDITED,) if status == DISPUTED else (CREDITED, DISPUTED)
        placeholders = ",".join("?" for _ in allowed)
        with atomic(self._conn):
            row = returning_one(
                self._conn,
                "UPDATE card_topups SET status = ?, detail = ? WHERE topup_id = ? "
                f"AND status IN ({placeholders}) RETURNING account_id",
                (status, detail[:300], topup_id, *allowed),
            )
            if row is None:
                return False
            account_id = str(row["account_id"])
            account = returning_one(
                self._conn,
                "UPDATE credit_accounts SET status = 'disabled' WHERE account_id = ? RETURNING account_id",
                (account_id,),
            )
            if account is None:
                raise TopupError(503, "reversal_pending", "the funding account could not be frozen yet",
                                 retryable=True)
            self._conn.execute(
                "INSERT INTO credit_ledger (account_id, kind, amount_mc, receipt_id, note) "
                "VALUES (?, 'review_freeze', 0, ?, ?)",
                (account_id, f"card:{topup_id}:{status}", f"Stripe {status}: operator review required"),
            )
            return True

    def disputed(self, topup_id: str, detail: str) -> bool:
        return self._review_reversal(topup_id, DISPUTED, detail)

    def refunded(self, topup_id: str, detail: str) -> bool:
        return self._review_reversal(topup_id, REFUNDED, detail)

    def committed_cents(self, account_id: str, *, hours: float = 24.0, now: float | None = None) -> int:
        """What this account has bought by card in the window, plus checkouts still open:
        the daily limit is checked against both, since an open checkout may be paid. A
        refunded or disputed top-up still counts — its credit stays on the account, and the
        limit bounds what a stolen card can turn into credit, not what the hub kept."""
        now = time.time() if now is None else now
        row = self._conn.execute(
            "SELECT COALESCE(SUM(amount_cents), 0) AS total FROM card_topups WHERE account_id = ? AND ("
            "(status IN (?, ?, ?) AND credited_at >= ?) OR (status IN (?, ?) AND expires_at > ?))",
            (account_id, CREDITED, DISPUTED, REFUNDED, now - hours * 3600, NEW, OPEN, now),
        ).fetchone()
        return int((dict(row) if row else {}).get("total") or 0)

    def for_account(self, account_id: str, limit: int = 50) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM card_topups WHERE account_id = ? ORDER BY created_at DESC LIMIT ?",
            (account_id, page_limit(limit, maximum=CARD_TOPUPS_PAGE_MAX)),
        ).fetchall()
        return [dict(r) for r in rows]


def is_topup_id(value: Any) -> bool:
    text = str(value or "")
    return len(text) == len(_ID_PREFIX) + 24 and text.startswith(_ID_PREFIX) and all(
        c in "0123456789abcdef" for c in text[len(_ID_PREFIX):])


def public(row: dict[str, Any], *, owner: bool = False, hub_url: str = "") -> dict[str, Any]:
    """A top-up as its buyer sees it; the account only to that account's own key."""
    out: dict[str, Any] = {
        "topup_id": row["topup_id"],
        "status": row["status"],
        "amount_usd": int(row["amount_cents"]) / 100,
        "charge_usd": int(row["charge_cents"]) / 100,
        "fee_usd": (int(row["charge_cents"]) - int(row["amount_cents"])) / 100,
        "created_at": _iso(float(row["created_at"])),
        "expires_at": _iso(float(row["expires_at"])),
    }
    if row["status"] == OPEN and row.get("checkout_url"):
        out["checkout_url"] = row["checkout_url"]
    if row.get("credited_at"):
        out["credited_at"] = _iso(float(row["credited_at"]))
        out["credited_usd"] = credits.mc_to_usd(int(row["credited_mc"] or 0))
    if (row.get("tax_mode") or TAX_OFF) != TAX_OFF:
        out["tax"] = {"mode": row["tax_mode"], "behavior": row.get("tax_behavior") or ""}
        if row.get("tax_cents"):
            out["tax"]["tax_usd"] = int(row["tax_cents"]) / 100
    if hub_url:
        out["status_url"] = f"{hub_url.rstrip('/')}/ai-market/v2/card-topups/{row['topup_id']}"
    if owner:
        out["account_id"] = row["account_id"]
        if row.get("detail"):
            out["detail"] = row["detail"]
    return out


def _iso(ts: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts)) if ts else ""


# ── the door ─────────────────────────────────────────────────────────────────


StripeCall = Callable[..., tuple[int, dict[str, Any]]]


def create(*, store: CardTopupStore, account_id: str, amount_usd: Any, hub_url: str,
           stripe: StripeCall | None = None, now: float | None = None) -> dict[str, Any]:
    """Open a Checkout Session for ``amount_usd`` of credit on ``account_id``."""
    reason = unavailable_reason()
    if reason:
        raise TopupError(503, "card_topup_unavailable", reason)
    stripe = stripe or _stripe_request
    amount = cents(amount_usd)
    if amount < round(min_usd() * 100) or amount > round(max_usd() * 100):
        raise TopupError(400, "amount_out_of_range",
                         f"a card top-up is {min_usd():.2f}-{max_usd():.2f} USD", min_usd=min_usd(), max_usd=max_usd())
    limit = round(daily_usd() * 100)

    def over_limit(committed: int) -> TopupError:
        return TopupError(429, "daily_topup_limit",
                          f"this account may buy at most {daily_usd():.2f} USD by card in 24 hours "
                          "(open checkouts count until they expire)", retryable=True,
                          daily_usd=daily_usd(), committed_usd=committed / 100)

    committed = store.committed_cents(account_id, now=now)
    if committed + amount > limit:
        raise over_limit(committed)
    fee = fee_cents(amount)
    mode = tax_mode()
    behavior = tax_behavior() if mode != TAX_OFF else ""
    row = store.open_new(account_id=account_id, amount_cents=amount, charge_cents=amount + fee, tax=mode,
                         behavior=behavior, now=now)
    # Checked again with this row in the sum: two requests that both passed the check above
    # would otherwise both open, past the limit. Each now sees the other's row, so at worst
    # both are refused (and may retry); never are both let through.
    committed = store.committed_cents(account_id, now=now)
    if committed > limit:
        store.discard(row["topup_id"])
        raise over_limit(committed - amount)
    base = hub_url.rstrip("/")
    status_url = f"{base}/ai-market/v2/card-topups/{row['topup_id']}"
    host = base.split("://", 1)[-1].split("/", 1)[0] or "AIMarket hub"
    form = {
        "mode": "payment",
        "client_reference_id": row["topup_id"],
        "success_url": status_url,
        "cancel_url": status_url,
        "expires_at": int(row["expires_at"]),
        "metadata": {"topup_id": row["topup_id"]},
        "payment_intent_data": {"metadata": {"topup_id": row["topup_id"]}},
        "line_items": [{"quantity": 1, "price_data": {
            "currency": "usd", "unit_amount": amount + fee,
            "product_data": {"name": f"Prepaid credit on {host}: ${amount / 100:.2f}"
                                     + (f" (incl. ${fee / 100:.2f} card fee)" if fee else "")},
        }}],
    }
    if mode != TAX_OFF:
        price = form["line_items"][0]["price_data"]
        price["tax_behavior"] = behavior
        price["product_data"]["tax_code"] = tax_code()
    if mode == STRIPE_TAX:
        # Stripe Tax locates the buyer by the billing address; a digital top-up has no other.
        form["automatic_tax"] = {"enabled": True}
        form["billing_address_collection"] = "required"
    elif mode == MANAGED_PAYMENTS:
        # Stripe is the seller: it collects the address and chooses the payment methods itself,
        # and refuses `automatic_tax`, `payment_method_types` and the like alongside this.
        form["managed_payments"] = {"enabled": True}
    try:
        status, session = stripe("POST", "/v1/checkout/sessions", form=form, idempotency_key=row["topup_id"],
                                 version=_version(mode))
    except Exception as exc:  # noqa: BLE001 - Stripe unreachable
        store.failed(row["topup_id"], f"stripe unreachable: {type(exc).__name__}")
        logger.error("card top-up: Stripe unreachable opening %s: %s", row["topup_id"], type(exc).__name__)
        raise TopupError(503, "stripe_unavailable", "the card processor could not be reached; nothing was charged",
                         retryable=True) from None
    url = str(session.get("url") or "")
    if status >= 300 or not url or not str(session.get("id") or "").startswith("cs_"):
        message = str((session.get("error") or {}).get("message") or f"HTTP {status}")
        store.failed(row["topup_id"], f"stripe refused: {message}")
        logger.error("card top-up: Stripe refused session %s: %s", row["topup_id"], message)
        raise TopupError(502, "stripe_refused", "the card processor refused to open a checkout; nothing was charged")
    store.opened(row["topup_id"], session_id=str(session["id"]), checkout_url=url,
                 livemode=bool(session.get("livemode")))
    opened = store.get(row["topup_id"]) or row
    return {"success": True, **public(opened, owner=True, hub_url=hub_url), "protocol_version": "v2"}


def _version(mode: str) -> str:
    return STRIPE_VERSION_MANAGED if mode == MANAGED_PAYMENTS else STRIPE_VERSION


def _paid_amounts(row: dict[str, Any], session: dict[str, Any]) -> tuple[bool, int]:
    """Do the session's figures match the checkout the hub opened, under the tax rule the row
    was opened with? Returns (match, tax in cents).

    Without tax the total is the charge. With tax added on top (exclusive) the subtotal is the
    charge and the total is subtotal + tax — nothing else (no discount, no shipping) may move
    it. With tax inside the price (inclusive) the total is the charge."""
    def number(value: Any) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return -1

    total = number(session.get("amount_total"))
    charge = int(row["charge_cents"])
    if (row.get("tax_mode") or TAX_OFF) == TAX_OFF:
        return total == charge, 0
    tax = number((session.get("total_details") or {}).get("amount_tax") or 0)
    if tax < 0:
        return False, 0
    if row.get("tax_behavior") == "inclusive":
        return total == charge, tax
    subtotal = number(session.get("amount_subtotal"))
    return subtotal == charge and total == subtotal + tax, tax


def _live_key() -> bool:
    return secret_key().startswith(("sk_live_", "rk_live_"))


def settle_session(*, store: CardTopupStore, ledger: Any, session: dict[str, Any],
                   now: float | None = None) -> dict[str, Any]:
    """Credit a paid Checkout Session, once. Shared by the webhook and the refresh.

    Every figure is checked against the row the hub opened — never taken from the event:
    an event names a top-up id, and a forged or replayed one must not be able to choose the
    amount or the account.
    """
    topup_id = str(session.get("client_reference_id") or (session.get("metadata") or {}).get("topup_id") or "")
    row = store.get(topup_id)
    if row is None:
        return {"outcome": "ignored", "reason": "not a top-up of this hub"}
    if row["status"] == CREDITED:
        return {"outcome": "already_credited", "topup_id": topup_id}
    if row["status"] in (DISPUTED, REFUNDED, FAILED):
        return {"outcome": row["status"], "topup_id": topup_id}
    if str(session.get("id") or "") != row["session_id"]:
        logger.error("card top-up: session %s does not belong to %s", str(session.get("id"))[:40], topup_id)
        return {"outcome": "refused", "reason": "session mismatch"}
    if session.get("payment_status") != "paid":
        return {"outcome": "pending", "topup_id": topup_id, "payment_status": session.get("payment_status")}
    matches, tax_cents = _paid_amounts(row, session)
    if str(session.get("currency") or "").lower() != "usd" or not matches:
        logger.error("card top-up: %s paid %s %s (subtotal %s, tax %s), expected %s usd cents under tax mode %s — "
                     "NOT credited, check it in Stripe", topup_id, session.get("amount_total"), session.get("currency"),
                     session.get("amount_subtotal"), (session.get("total_details") or {}).get("amount_tax"),
                     row["charge_cents"], row.get("tax_mode") or TAX_OFF)
        return {"outcome": "refused", "reason": "amount or currency differs from the checkout opened"}
    if _live_key() and not session.get("livemode"):
        logger.error("card top-up: test-mode payment for %s on a live key — not credited", topup_id)
        return {"outcome": "refused", "reason": "test-mode payment on a live hub"}
    credited_mc = int(row["amount_cents"]) * (credits.MILLICENTS_PER_DOLLAR // 100)
    reference = f"card:stripe:{row['session_id']}"
    result = ledger.deposit(row["account_id"], credited_mc, reference=reference,
                            note=f"card top-up {topup_id}")
    if result.get("error"):
        logger.error("card top-up: crediting %s failed: %s", topup_id, result["error"])
        raise TopupError(500, "credit_failed", "the payment is confirmed but the credit could not be written; "
                         "it is retried on the next delivery or refresh", retryable=True)
    payment_intent = str(session.get("payment_intent") or "")
    if isinstance(session.get("payment_intent"), dict):
        payment_intent = str(session["payment_intent"].get("id") or "")
    store.credited(topup_id, payment_intent=payment_intent, credited_mc=credited_mc, tax_cents=tax_cents, now=now)
    logger.warning("card top-up: credited $%.2f to %s for %s", int(row["amount_cents"]) / 100, row["account_id"],
                   topup_id)
    return {"outcome": "credited", "topup_id": topup_id,
            "replay": bool(result.get("idempotent_replay"))}


def _reversal_row(store: CardTopupStore, ledger: Any, payment_intent: str) -> dict[str, Any] | None:
    """Resolve a reversal even when Stripe delivers it before the paid-session event.

    Checkout Sessions read access is enough; no extra PaymentIntent permission is needed.
    Only a session already bound to a local row can establish the association. Temporary
    lookup/settlement failures must be retried by Stripe, not acknowledged as ignored.
    """
    from urllib.parse import urlencode

    row = store.by_payment_intent(payment_intent)
    if row is not None or not payment_intent:
        return row
    try:
        status, result = _stripe_request("GET", "/v1/checkout/sessions?" + urlencode(
            {"payment_intent": payment_intent, "limit": 1}), version=STRIPE_VERSION_MANAGED)
    except Exception:
        raise TopupError(503, "stripe_unavailable", "cannot associate the reversal yet", retryable=True) from None
    if status >= 300:
        raise TopupError(503, "stripe_unavailable", "cannot associate the reversal yet", retryable=True)
    for session in result.get("data", []):
        topup_id = str(session.get("client_reference_id") or (session.get("metadata") or {}).get("topup_id") or "")
        row = store.get(topup_id)
        if row is None or row["session_id"] != session.get("id") or session.get("payment_intent") != payment_intent:
            continue
        # Read with the version of this row's tax mode and run all normal amount checks.
        refresh(store=store, ledger=ledger, topup_id=topup_id)
        row = store.by_payment_intent(payment_intent)
        if row is None:
            raise TopupError(503, "reversal_pending", "the paid session is not reconciled yet",
                             retryable=True)
        return row
    return None


def handle_webhook(*, store: CardTopupStore, ledger: Any, payload: bytes, signature: str,
                   now: float | None = None) -> dict[str, Any]:
    """A Stripe event, verified. Anything not about a top-up is acknowledged and ignored, so
    Stripe does not retry it for days."""
    if not verify_signature(payload, signature, webhook_secret(), now=now):
        raise TopupError(400, "signature_invalid", "the Stripe-Signature does not verify")
    try:
        event = json.loads(payload)
    except ValueError:
        raise TopupError(400, "event_malformed", "the event is not JSON") from None
    kind = str(event.get("type") or "")
    obj = ((event.get("data") or {}).get("object") or {}) if isinstance(event, dict) else {}
    if not isinstance(obj, dict):
        return {"outcome": "ignored"}
    if kind in PAID_EVENTS:
        return settle_session(store=store, ledger=ledger, session=obj, now=now)
    if kind == "checkout.session.expired":
        topup_id = str(obj.get("client_reference_id") or "")
        row = store.get(topup_id)
        if row is not None and row["session_id"] == obj.get("id"):
            store.expired(topup_id)
            return {"outcome": "expired", "topup_id": topup_id}
        return {"outcome": "ignored"}
    if kind == "charge.dispute.created":
        row = _reversal_row(store, ledger, str(obj.get("payment_intent") or ""))
        if row is not None:
            if store.disputed(row["topup_id"], f"dispute {str(obj.get('id'))[:40]}: {str(obj.get('reason'))[:60]}"):
                logger.error("card top-up: DISPUTE on %s (account %s, $%.2f) — account frozen for review; credit already "
                             "spent cannot be recalled", row["topup_id"], row["account_id"], int(row["amount_cents"]) / 100)
            return {"outcome": "disputed", "topup_id": row["topup_id"]}
        return {"outcome": "ignored"}
    if kind == "charge.refunded":
        # Refunds are made in Stripe, by the operator — or, under Managed Payments, by Stripe
        # itself within 60 days. The money left; the credit may already be spent, so the hub
        # freezes new spending for operator review without inventing a confiscation.
        row = _reversal_row(store, ledger, str(obj.get("payment_intent") or ""))
        if row is not None and row["status"] in (CREDITED, DISPUTED):
            refunded = obj.get("amount_refunded")
            if store.refunded(row["topup_id"], f"refunded {refunded} cents in Stripe"):
                logger.error("card top-up: REFUND of %s cents on %s (account %s, credit $%.2f) — account frozen; correct the balance by "
                             "hand if the credit should go", refunded, row["topup_id"], row["account_id"],
                             int(row["amount_cents"]) / 100)
            return {"outcome": "refunded", "topup_id": row["topup_id"]}
        return {"outcome": "ignored"}
    return {"outcome": "ignored"}


def refresh(*, store: CardTopupStore, ledger: Any, topup_id: str, stripe: StripeCall | None = None,
            now: float | None = None) -> dict[str, Any]:
    """Ask Stripe where a top-up's session stands, and credit it if it is paid — the
    recovery path for a webhook that never arrived."""
    if not enabled():
        raise TopupError(503, "card_topup_unavailable", unavailable_reason())
    row = store.get(topup_id)
    if row is None:
        raise TopupError(404, "topup_unknown", "no card top-up with that id on this hub")
    if row["status"] in (CREDITED, DISPUTED, FAILED, REFUNDED) or not row["session_id"]:
        return {"outcome": row["status"], "topup_id": topup_id}
    stripe = stripe or _stripe_request
    try:
        status, session = stripe("GET", f"/v1/checkout/sessions/{row['session_id']}",
                                 version=_version(row.get("tax_mode") or TAX_OFF))
    except Exception:  # noqa: BLE001
        raise TopupError(503, "stripe_unavailable", "the card processor could not be reached; retry",
                         retryable=True) from None
    if status >= 300:
        raise TopupError(502, "stripe_refused", f"the card processor answered HTTP {status}")
    if session.get("status") == "expired" and session.get("payment_status") != "paid":
        store.expired(topup_id)
        return {"outcome": EXPIRED, "topup_id": topup_id}
    return settle_session(store=store, ledger=ledger, session=session, now=now)
