"""Buying credits with USDC — the one self-serve way money enters the credits rail.

Everything else on the credits rail (mandates, subcontracting allowances, A2A and REST
invokes paid with ``X-API-Key``) needs credit on an account, and until this module only the
operator could put it there (``POST /accounts/{id}/credit``). A stranger's agent could open an
account but never fund it. This is the door that lets it.

The flow is the x402 "exact" scheme the hub already speaks for seller-direct sales, pointed at
the operator instead of a seller:

1. **Quote.** ``POST /ai-market/v2/account/topup`` with the account's ``X-API-Key`` and
   ``{"amount_usd": 5}`` answers ``402`` with ordinary x402 terms: pay ``amount`` USDC to
   ``payTo`` by an EIP-3009 ``transferWithAuthorization`` signed over the ``nonce`` in the
   offer. The nonce is random, minted here, and bound in ``credit_topup_quotes`` to that
   account and that amount.
2. **Pay.** The buyer signs the authorization with its own wallet and sends the transaction
   itself. The hub holds no key, submits nothing and pays no gas.
3. **Redeem.** The buyer (or anyone) presents the transaction hash. The hub reads the chain:
   the token logged ``AuthorizationUsed(payer, nonce)`` and, in its very next log, moved at
   least the quoted amount from that payer to ``payTo`` (``settle.verify_transfer`` — the
   same definition of "paid" the market rail uses). Then it credits the QUOTED account.

**Why redemption needs no secret — unlike an invoke.** The seller-direct rail binds a nonce
to a secret only the payer holds (``settle.nonce_for_secret``), because an invoke is service
to whoever presents the payment: a watcher who saw the mined transaction could redeem it
first and take the call. A top-up is not service to the presenter. The account is fixed when
the quote is minted, so presenting someone else's payment only credits *their* account, once.
Requiring a secret here would protect nothing and would strand the money of a buyer who lost
it; so redemption is open to anyone holding the transaction hash, and the hub could redeem on
the buyer's behalf.

**One payment, one credit — across every door.** A transfer to the operator's wallet is also
what the channel-deposit door accepts. Before crediting, a redemption claims the transaction
in the shared deposit-claim registry (``deposit_claims``), the same single-use record the
channel door and the Factory write, and records the authorization in ``x402_payments``. Each
step is idempotent on the quote's nonce, so a redemption interrupted halfway is finished by
the next one, and two racing redemptions credit once.

Off unless ``AIMARKET_TOPUP_ENABLED=1``: it is a door money comes in through, and an operator
opens it on purpose. Operator guide: ``docs/credits-topup.md``.
"""
from __future__ import annotations

import logging
import os
import secrets
import time
from dataclasses import dataclass
from typing import Any, Callable

from aimarket_hub import credits, settle, x402
from aimarket_hub.db_backend import returning_one
from aimarket_hub.paging import page_limit


# Top-up quotes one account read may return.
QUOTES_PAGE_MAX = 200

logger = logging.getLogger(__name__)

#: The deposit-claim registry's name for this door (``deposit_claims.claim_deposit``).
TOPUP_STACK = "aimarket-hub-topup"
#: The capability id a top-up's authorization is recorded under in ``x402_payments``.
TOPUP_CAPABILITY = "credits.topup"
QUOTED, REDEEMING, CREDITED = "quoted", "redeeming", "credited"
#: A redemption that stopped halfway may be finished by another after this long.
STALE_REDEEMING_S = 60.0


class TopupError(Exception):
    """A refusal the caller can act on: HTTP status, stable error code, human detail."""

    def __init__(self, status: int, error: str, detail: str, **extra: Any):
        super().__init__(detail)
        self.status, self.error, self.detail, self.extra = status, error, detail, extra

    def body(self) -> dict[str, Any]:
        return {"success": False, "error": self.error, "detail": self.detail, **self.extra,
                "protocol_version": "v2"}


# ── configuration ────────────────────────────────────────────────────────────


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def switched_on() -> bool:
    return os.getenv("AIMARKET_TOPUP_ENABLED", "0").strip().lower() in ("1", "true", "yes", "on")


def pay_to() -> str:
    """Where top-up USDC goes: ``AIMARKET_TOPUP_PAY_TO``, else the hub's own x402 wallet."""
    explicit = (os.getenv("AIMARKET_TOPUP_PAY_TO") or "").strip()
    return explicit if settle.is_address(explicit) else (x402.recipient() or "").strip()


def min_usd() -> float:
    return max(0.01, _float("AIMARKET_TOPUP_MIN_USD", 1.0))


def max_usd() -> float:
    return max(min_usd(), _float("AIMARKET_TOPUP_MAX_USD", 100.0))


def daily_usd() -> float:
    """Most one account may buy in 24 hours. Bounds the damage of a stolen key's top-ups
    (money in, not out — but still money the operator then owes as service)."""
    return max(min_usd(), _float("AIMARKET_TOPUP_DAILY_USD", 500.0))


def quote_ttl_s() -> int:
    """How long an unpaid quote is offered. A PAID quote stays redeemable after this."""
    return max(60, _int("AIMARKET_TOPUP_QUOTE_TTL_S", 900))


def min_confirmations() -> int:
    return max(1, _int("AIMARKET_TOPUP_MIN_CONFIRMATIONS", 2))


def max_open_quotes() -> int:
    return max(1, _int("AIMARKET_TOPUP_MAX_OPEN_QUOTES", 5))


def retain_days() -> int:
    """Days an unredeemed quote is kept. A payment made for it can be redeemed until then."""
    return max(1, _int("AIMARKET_TOPUP_RETAIN_DAYS", 30))


def unavailable_reason() -> str:
    """Why the door is shut, or "" when it is open."""
    if not switched_on():
        return "USDC top-ups are switched off on this hub (AIMARKET_TOPUP_ENABLED)"
    if not credits.enabled():
        return "the credits rail is switched off on this hub"
    if x402.asset_profile() is None or not x402.caip2():
        return "this hub names no USDC asset to be paid in"
    if not settle.is_address(pay_to()):
        return "this hub names no wallet to pay top-ups to (AIMARKET_TOPUP_PAY_TO)"
    return ""


def enabled() -> bool:
    return not unavailable_reason()


def well_known() -> dict[str, Any]:
    """The ``payment_rails.credits.topup`` block of ``/.well-known/ai-market.json``."""
    profile = x402.asset_profile() or {}
    out: dict[str, Any] = {"enabled": enabled(), "quote": "/ai-market/v2/account/topup",
                           "redeem": "/ai-market/v2/topups/{nonce}", "binding": "eip3009"}
    if enabled():
        out.update({
            "asset": x402.asset_symbol(), "asset_address": profile.get("address", ""),
            "network": x402.caip2(), "pay_to": pay_to(),
            "min_usd": min_usd(), "max_usd": max_usd(), "daily_usd": daily_usd(),
            "min_confirmations": min_confirmations(), "quote_ttl_s": quote_ttl_s(),
        })
    else:
        out["reason"] = unavailable_reason()
    return out


# ── amounts ──────────────────────────────────────────────────────────────────


def cents(amount_usd: Any) -> int:
    """A top-up amount in whole cents. Anything finer, negative or not a number is refused
    rather than rounded: the buyer is told exactly what it will pay."""
    try:
        value = float(amount_usd)
    except (TypeError, ValueError):
        raise TopupError(400, "amount_invalid", "amount_usd must be a number of US dollars") from None
    if value != value or value in (float("inf"), float("-inf")):
        raise TopupError(400, "amount_invalid", "amount_usd must be a finite number")
    whole = round(value * 100)
    if abs(value * 100 - whole) > 1e-6:
        raise TopupError(400, "amount_invalid", "amount_usd is in whole cents (e.g. 5 or 12.50)")
    return int(whole)


def units_for_cents(amount_cents: int, decimals: int) -> int:
    return int(amount_cents) * 10 ** (int(decimals) - 2) if decimals >= 2 else int(amount_cents) // 10 ** (2 - decimals)


def units_to_mc(units: int, decimals: int) -> int:
    """Token base units → ledger millicents, rounded DOWN: the ledger never credits a
    fraction of a millicent the chain did not deliver."""
    return (int(units) * credits.MILLICENTS_PER_DOLLAR) // (10 ** int(decimals))


# ── the quote store ──────────────────────────────────────────────────────────


@dataclass
class Quote:
    nonce: str
    account_id: str
    amount_units: int
    pay_to: str
    token_contract: str
    chain: str
    chain_id: int
    expires_at: float
    status: str
    tx_hash: str = ""
    payer: str = ""
    paid_units: int = 0
    credited_mc: int = 0
    reference: str = ""
    detail: str = ""
    redeeming_since: float = 0.0
    created_at: str = ""
    credited_at: float = 0.0

    @classmethod
    def from_row(cls, row: Any) -> "Quote":
        d = dict(row)
        return cls(
            nonce=str(d["nonce"]), account_id=str(d["account_id"]), amount_units=int(d["amount_units"]),
            pay_to=str(d["pay_to"]), token_contract=str(d["token_contract"]), chain=str(d["chain"]),
            chain_id=int(d.get("chain_id") or 0), expires_at=float(d["expires_at"]),
            status=str(d["status"]), tx_hash=str(d.get("tx_hash") or ""), payer=str(d.get("payer") or ""),
            paid_units=int(d.get("paid_units") or 0), credited_mc=int(d.get("credited_mc") or 0),
            reference=str(d.get("reference") or ""), detail=str(d.get("detail") or ""),
            redeeming_since=float(d.get("redeeming_since") or 0),
            created_at=str(d.get("created_at") or ""), credited_at=float(d.get("credited_at") or 0),
        )

    def amount_usd(self, decimals: int) -> float:
        return round(self.amount_units / 10 ** decimals, 6)

    def public(self, decimals: int, *, owner: bool = False) -> dict[str, Any]:
        """What GET /topups/{nonce} shows. The account id only to its owner: the nonce is
        public once the payment is mined, and it must not name whose account it funded."""
        out: dict[str, Any] = {
            "nonce": self.nonce, "status": self.status, "amount_usd": self.amount_usd(decimals),
            "amount_units": str(self.amount_units), "pay_to": self.pay_to, "asset": self.token_contract,
            "chain": self.chain, "expires_at": self.expires_at, "created_at": self.created_at,
        }
        if self.status in (CREDITED, REDEEMING):
            out["tx_hash"] = self.tx_hash
        if self.status == CREDITED:
            out.update({"credited_usd": credits.mc_to_usd(self.credited_mc), "credited_at": self.credited_at,
                        "paid_usd": round(self.paid_units / 10 ** decimals, 6)})
            if self.paid_units > self.amount_units:
                # Paid more than quoted: credited the quote, the rest is the operator's to refund.
                out["overpaid_usd"] = round((self.paid_units - self.amount_units) / 10 ** decimals, 6)
        if owner:
            out.update({"account_id": self.account_id, "payer": self.payer, "reference": self.reference})
        return out


class TopupStore:
    """``credit_topup_quotes``: every state change is ONE conditional statement."""

    def __init__(self, conn: Any):
        self._conn = conn

    def mint(self, *, account_id: str, amount_units: int, pay_to: str, token_contract: str,
             chain: str, chain_id: int, ttl_s: int, now: float | None = None) -> Quote:
        now = time.time() if now is None else now
        nonce = "0x" + secrets.token_hex(32)
        self._conn.execute(
            "INSERT INTO credit_topup_quotes (nonce, account_id, amount_units, pay_to, token_contract, "
            "chain, chain_id, expires_at, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (nonce, account_id, int(amount_units), pay_to.lower(), token_contract.lower(),
             chain, int(chain_id), now + int(ttl_s), QUOTED),
        )
        self._conn.commit()
        quote = self.get(nonce)
        assert quote is not None
        return quote

    def get(self, nonce: str) -> Quote | None:
        row = self._conn.execute(
            "SELECT * FROM credit_topup_quotes WHERE nonce = ?", ((nonce or "").strip().lower(),),
        ).fetchone()
        return Quote.from_row(row) if row else None

    def open_quotes(self, account_id: str, now: float | None = None) -> int:
        now = time.time() if now is None else now
        row = self._conn.execute(
            "SELECT COUNT(*) AS n FROM credit_topup_quotes WHERE account_id = ? AND status = ? "
            "AND expires_at > ?", (account_id, QUOTED, now),
        ).fetchone()
        return int((row["n"] if row else 0) or 0)

    def credited_mc_since(self, account_id: str, hours: float = 24.0, now: float | None = None) -> int:
        now = time.time() if now is None else now
        row = self._conn.execute(
            "SELECT COALESCE(SUM(credited_mc), 0) AS total FROM credit_topup_quotes "
            "WHERE account_id = ? AND status = ? AND credited_at >= ?",
            (account_id, CREDITED, now - float(hours) * 3600.0),
        ).fetchone()
        return int((row["total"] if row else 0) or 0)

    def open_units(self, account_id: str, now: float | None = None) -> int:
        """Token units still offered to this account by unpaid, unexpired quotes."""
        now = time.time() if now is None else now
        row = self._conn.execute(
            "SELECT COALESCE(SUM(amount_units), 0) AS total FROM credit_topup_quotes "
            "WHERE account_id = ? AND status = ? AND expires_at > ?", (account_id, QUOTED, now),
        ).fetchone()
        return int((row["total"] if row else 0) or 0)

    def begin(self, nonce: str, tx_hash: str, now: float | None = None) -> bool:
        """Claim the quote for this redemption. True when THIS call won it.

        A quote is won from ``quoted``, or taken over from a ``redeeming`` that has been
        stuck for STALE_REDEEMING_S on the same transaction — a redemption that crashed
        after claiming. Every later step is idempotent on the nonce, so finishing it is safe.
        """
        now = time.time() if now is None else now
        won = returning_one(
            self._conn,
            "UPDATE credit_topup_quotes SET status = ?, tx_hash = ?, redeeming_since = ? "
            "WHERE nonce = ? AND (status = ? OR (status = ? AND tx_hash = ? AND redeeming_since < ?)) "
            "RETURNING nonce",
            (REDEEMING, tx_hash.lower(), now, nonce.lower(), QUOTED, REDEEMING, tx_hash.lower(),
             now - STALE_REDEEMING_S),
            commit=True,
        )
        return won is not None

    def release(self, nonce: str, tx_hash: str) -> None:
        """Give a claimed quote back (a transient failure before anything was credited)."""
        self._conn.execute(
            "UPDATE credit_topup_quotes SET status = ?, tx_hash = '', redeeming_since = 0 "
            "WHERE nonce = ? AND status = ? AND tx_hash = ?",
            (QUOTED, nonce.lower(), REDEEMING, tx_hash.lower()),
        )
        self._conn.commit()

    def credit(self, nonce: str, *, payer: str, paid_units: int, credited_mc: int, reference: str,
               detail: str = "", now: float | None = None) -> None:
        self._conn.execute(
            "UPDATE credit_topup_quotes SET status = ?, payer = ?, paid_units = ?, credited_mc = ?, "
            "reference = ?, detail = ?, credited_at = ? WHERE nonce = ? AND status = ?",
            (CREDITED, payer.lower(), int(paid_units), int(credited_mc), reference, detail[:300],
             time.time() if now is None else now, nonce.lower(), REDEEMING),
        )
        self._conn.commit()

    def for_account(self, account_id: str, limit: int = 50) -> list[Quote]:
        rows = self._conn.execute(
            "SELECT * FROM credit_topup_quotes WHERE account_id = ? ORDER BY created_at DESC LIMIT ?",
            (account_id, page_limit(limit, maximum=QUOTES_PAGE_MAX)),
        ).fetchall()
        return [Quote.from_row(r) for r in rows]

    def prune(self, now: float | None = None) -> int:
        """Forget unredeemed quotes past retention. Credited rows are kept: they are the
        record of money that came in."""
        now = time.time() if now is None else now
        cur = self._conn.execute(
            "DELETE FROM credit_topup_quotes WHERE status = ? AND expires_at < ?",
            (QUOTED, now - retain_days() * 86_400),
        )
        self._conn.commit()
        return int(getattr(cur, "rowcount", 0) or 0)


# ── quote ────────────────────────────────────────────────────────────────────


_DECIMALS_READ: dict[str, int] = {}


def check_decimals(token: str, decimals: int) -> None:
    """Refuse to quote when the token's own ``decimals()`` is not what the hub prices in.

    The amount a quote asks for and the credit it grants are both scaled by ``decimals``.
    An ``AIMARKET_X402_ASSET`` override on a chain with a built-in profile keeps that
    profile's 6 — point it at an 18-decimal token and a $5 quote would ask for 5e-12 of it
    and credit $5. The token is asked once per address and remembered.
    """
    if os.getenv("AIMARKET_TOPUP_VERIFY_DECIMALS", "1").strip().lower() in ("0", "false", "no", "off"):
        return
    key = (token or "").lower()
    onchain = _DECIMALS_READ.get(key)
    if onchain is None:
        try:
            onchain = int(str(settle.rpc_call(settle.rpc_urls(), "eth_call", [{"to": token, "data": "0x313ce567"}, "latest"],
                                              timeout=5.0)), 16)
        except Exception:  # noqa: BLE001 - no node answered: refused below
            onchain = None
        if onchain is None:
            raise TopupError(503, "topup_unavailable", "the token's decimals could not be read from the chain; retry",
                             retryable=True)
        _DECIMALS_READ[key] = onchain
    if onchain != int(decimals):
        raise TopupError(503, "topup_unavailable",
                         f"the token reports {onchain} decimals and this hub prices in {decimals}; "
                         "top-ups are refused until the operator fixes the asset configuration")


def quote(*, store: TopupStore, account_id: str, amount_usd: Any, hub_url: str,
          now: float | None = None) -> tuple[Quote, dict[str, Any], dict[str, Any]]:
    """Mint a quote. Returns (quote, 402 JSON body, V2 PaymentRequired for the header)."""
    reason = unavailable_reason()
    if reason:
        raise TopupError(503, "topup_unavailable", reason)
    amount_cents = cents(amount_usd)
    amount = amount_cents / 100
    if amount < min_usd() - 1e-9 or amount > max_usd() + 1e-9:
        raise TopupError(400, "amount_out_of_range",
                         f"a top-up is between {min_usd():.2f} and {max_usd():.2f} USD",
                         min_usd=min_usd(), max_usd=max_usd())
    if store.open_quotes(account_id, now) >= max_open_quotes():
        raise TopupError(429, "too_many_open_quotes",
                         f"this account already has {max_open_quotes()} unpaid top-up quotes; pay one or "
                         "let them expire", max_open_quotes=max_open_quotes())
    profile = x402.asset_profile() or {}
    decimals = int(profile.get("decimals") or 6)
    extra = dict(profile.get("extra") or {})
    units = units_for_cents(amount_cents, decimals)
    # What was bought in 24 hours AND what is still offered: a pile of open quotes paid at
    # once would otherwise buy past the limit (redemption checks it again).
    bought_mc = store.credited_mc_since(account_id, now=now)
    offered_usd = store.open_units(account_id, now) / 10 ** decimals
    if credits.mc_to_usd(bought_mc) + offered_usd + amount > daily_usd() + 1e-9:
        raise TopupError(429, "daily_topup_limit",
                         f"this account may buy at most {daily_usd():.2f} USD of credit in 24 hours",
                         daily_usd=daily_usd(), bought_usd=credits.mc_to_usd(bought_mc),
                         offered_usd=round(offered_usd, 6))
    check_decimals(str(profile["address"]), decimals)
    store.prune(now)
    minted = store.mint(account_id=account_id, amount_units=units, pay_to=pay_to(),
                        token_contract=str(profile["address"]), chain=x402.chain(),
                        chain_id=x402.chain_id(), ttl_s=quote_ttl_s(), now=now)
    base = (hub_url or "").rstrip("/")
    resource = f"{base}/ai-market/v2/account/topup"
    description = f"{amount:.2f} USD of credit on {base or 'this hub'}"
    domain = {"name": str(extra.get("name") or "USD Coin"), "version": str(extra.get("version") or "2"),
              "chainId": minted.chain_id, "verifyingContract": str(profile["address"])}
    v2 = {
        "x402Version": x402.X402_VERSION,
        "error": "Payment required",
        "resource": {"url": resource, "description": description, "mimeType": "application/json"},
        "accepts": [{
            "scheme": "exact", "network": x402.caip2(), "amount": str(units), "asset": str(profile["address"]),
            "payTo": minted.pay_to, "maxTimeoutSeconds": quote_ttl_s(),
            "extra": {**domain, "nonce": minted.nonce},
        }],
    }
    v1_accept = {
        "scheme": "exact", "network": minted.chain, "maxAmountRequired": str(units),
        "asset": str(profile["address"]), "payTo": minted.pay_to, "resource": resource,
        "description": description, "mimeType": "application/json", "maxTimeoutSeconds": quote_ttl_s(),
        "extra": {**domain, "nonce": minted.nonce, "decimals": decimals, "symbol": x402.asset_symbol()},
    }
    body = {
        "success": False,
        "error": "payment_required",
        "detail": (f"Pay {amount:.2f} {x402.asset_symbol()} to {minted.pay_to} with transferWithAuthorization "
                   f"signed over nonce {minted.nonce}, send the transaction, then POST its hash to "
                   f"{base}/ai-market/v2/topups/{minted.nonce}. Only an EIP-3009 authorization over this "
                   "nonce is credited; a plain transfer is not."),
        "x402Version": 1,
        "accepts": [v1_accept],
        "nonce": minted.nonce,
        "binding": "eip3009",
        "pay_to": minted.pay_to,
        "expires_at": minted.expires_at,
        "topup": {
            "nonce": minted.nonce, "amount_usd": amount, "amount_units": str(units),
            "asset": x402.asset_symbol(), "asset_address": str(profile["address"]), "decimals": decimals,
            "network": x402.caip2(), "chain": minted.chain, "chain_id": minted.chain_id,
            "pay_to": minted.pay_to, "expires_at": minted.expires_at,
            "min_confirmations": min_confirmations(),
            "redeem_url": f"{base}/ai-market/v2/topups/{minted.nonce}",
            "status_url": f"{base}/ai-market/v2/topups/{minted.nonce}",
        },
        "protocol_version": "v2",
    }
    return minted, body, v2


# ── redeem ───────────────────────────────────────────────────────────────────


def _terms(q: Quote) -> settle.PaymentTerms:
    """What the chain check requires of the authorization over this quote's nonce.

    Any positive amount from its own transfer to ``payTo`` is accepted here, not only the
    quoted amount: the nonce already binds the payment to one account, and refusing an
    underpayment would strand money that is unambiguously that account's. What is CREDITED
    is decided after the check — never more than the quote.
    """
    profile = x402.asset_profile() or {}
    decimals = int(profile.get("decimals") or 6)
    return settle.PaymentTerms(
        chain=q.chain, token=x402.asset_symbol(), token_contract=q.token_contract, decimals=decimals,
        pay_to=q.pay_to, amount_units=1, amount_usd=q.amount_usd(decimals),
        min_confirmations=min_confirmations(), chain_id=q.chain_id or 8453,
    )


def _credited_answer(q: Quote, ledger: Any, *, replay: bool, owner: bool, decimals: int) -> dict[str, Any]:
    out: dict[str, Any] = {"success": True, "status": CREDITED, "nonce": q.nonce, "tx_hash": q.tx_hash,
                           "credited_usd": credits.mc_to_usd(q.credited_mc), "chain": q.chain,
                           "paid_usd": round(q.paid_units / 10 ** decimals, 6),
                           "idempotent_replay": replay, "protocol_version": "v2"}
    if q.paid_units > q.amount_units:
        out["overpaid_usd"] = round((q.paid_units - q.amount_units) / 10 ** decimals, 6)
        out["overpaid_note"] = "credited up to the quote; the excess is the operator's to refund"
    if owner:
        out.update({"account_id": q.account_id, "payer": q.payer, "reference": q.reference,
                    "balance_usd": ledger.balance(q.account_id)})
    return out


_VERIFY_LOG: dict[str, list[float]] = {}


def verify_allowed(key: str, *, now: float | None = None, per_minute: int = 12) -> bool:
    """Redemption is open to anyone and every verification is a round trip to a chain RPC.

    The budget is the CALLER's — the quote owner's account, anybody else's address — not
    the quote's: a limit keyed on the nonce alone let anyone who read the nonce off the
    chain spend it with bogus hashes and lock the owner out.
    """
    now = time.time() if now is None else now
    recent = [t for t in _VERIFY_LOG.get(key, []) if t > now - 60.0]
    if len(recent) >= per_minute:
        _VERIFY_LOG[key] = recent
        return False
    recent.append(now)
    _VERIFY_LOG[key] = recent
    if len(_VERIFY_LOG) > 10_000:
        for stale in [k for k, v in _VERIFY_LOG.items() if not v or v[-1] < now - 60.0]:
            _VERIFY_LOG.pop(stale, None)
    return True


def redeem(*, store: TopupStore, ledger: Any, payments: settle.PaymentStore, nonce: str, tx_hash: str,
           claim_deposit: Callable[..., dict[str, Any]], owner_account: str = "", limit_key: str = "",
           verify: Callable[..., dict[str, Any]] | None = None, now: float | None = None) -> dict[str, Any]:
    """Credit the quoted account for a mined payment. Safe to call any number of times.

    ``owner_account`` is the account the caller authenticated as, if any: the answer shows
    the balance and account only to that account's owner. Crediting never depends on it.
    ``limit_key`` names the verification budget of a caller who is NOT the quote's owner —
    the route passes the client address (default: the nonce). The owner spends its
    account's own budget, which nobody without its key can exhaust.

    No outcome of a redemption is final except a credit: a refusal leaves the quote open, so
    the same payment can be presented again once whatever refused it has changed.
    """
    verify = verify or settle.verify_transfer
    nonce = (nonce or "").strip().lower()
    if not settle.is_nonce(nonce):
        raise TopupError(400, "nonce_invalid", "the top-up nonce is 32 bytes of 0x-prefixed hex")
    q = store.get(nonce)
    if q is None:
        raise TopupError(404, "topup_unknown", "no top-up quote with that nonce on this hub")
    decimals = int((x402.asset_profile() or {}).get("decimals") or 6)
    owner = bool(owner_account) and owner_account == q.account_id
    tx_hash = (tx_hash or "").strip().lower()
    if q.status == CREDITED:
        if tx_hash and tx_hash != q.tx_hash:
            raise TopupError(409, "topup_already_credited",
                             "this quote was already paid and credited by another transaction")
        return _credited_answer(q, ledger, replay=True, owner=owner, decimals=decimals)
    if not settle.is_tx_hash(tx_hash):
        raise TopupError(400, "tx_hash_invalid",
                         "send the payment's 0x transaction hash: this hub verifies payments and never "
                         "settles them, so submit the signed authorization yourself and send its hash")
    if q.status == REDEEMING and q.tx_hash != tx_hash:
        raise TopupError(409, "topup_in_progress", "another transaction is being redeemed for this quote",
                         retryable=True)

    # Per account for the owner, never per (account, nonce): accounts are free to open and
    # expired quotes stay redeemable, so a budget per quote multiplied chain reads by both.
    if not verify_allowed(f"acct:{q.account_id}" if owner else (limit_key or nonce), now=now):
        raise TopupError(429, "too_many_attempts", "too many checks from this caller; retry in a minute",
                         retryable=True)
    try:
        settled = verify(tx_hash=tx_hash, terms=_terms(q), require_nonce=nonce)
    except settle.PaymentError as exc:
        text = str(exc)
        pending = "confirmation" in text or "not on chain yet" in text
        raise TopupError(409 if pending else 402, "payment_not_final" if pending else "payment_invalid",
                         text, retryable=pending) from None
    except Exception as exc:  # noqa: BLE001 - an RPC that cannot be reached is not a refusal
        logger.error("topup: chain verification of %s failed: %s", tx_hash[:18], exc)
        raise TopupError(503, "verifier_unavailable",
                         "the chain could not be read; retry — nothing was credited", retryable=True) from None

    paid_units = int(settled.get("paid_units") or 0)
    credited_units = min(paid_units, q.amount_units)
    credited_mc = units_to_mc(credited_units, decimals)
    payer = str(settled.get("authorizer") or "")
    if credited_mc <= 0:
        raise TopupError(402, "payment_invalid", "the authorization moved less than a millicent")
    # The daily limit, again at redemption: quotes are paid after they are minted and stay
    # redeemable after they expire, so the quote-time check alone bounds nothing. Over it,
    # the credit waits — the money is the account's either way.
    bought_mc = store.credited_mc_since(q.account_id, now=now)
    if credits.mc_to_usd(bought_mc + credited_mc) > daily_usd() + 1e-9:
        raise TopupError(429, "daily_topup_limit",
                         f"this account may be credited at most {daily_usd():.2f} USD in 24 hours; this payment "
                         "stays redeemable — retry later", retryable=True, daily_usd=daily_usd(),
                         bought_usd=credits.mc_to_usd(bought_mc))

    if not store.begin(nonce, tx_hash, now):
        latest = store.get(nonce)
        if latest is not None and latest.status == CREDITED:
            return _credited_answer(latest, ledger, replay=True, owner=owner, decimals=decimals)
        raise TopupError(409, "topup_in_progress", "this top-up is being credited; read its status",
                         retryable=True)

    reference = f"topup:{q.chain}:{nonce}"
    # 1. The transaction, across every door and every name of its chain (channels.py).
    claim = claim_deposit(chain=q.chain, tx_hash=tx_hash, stack=TOPUP_STACK, claim_id=nonce,
                          amount_cents=credited_units * 100 // 10 ** decimals, chain_id=q.chain_id or None,
                          share_within_stack=True)
    if not claim.get("ok"):
        store.release(nonce, tx_hash)
        held = claim.get("claim") or {}
        if claim.get("error") == "already_claimed" and held.get("stack"):
            detail = (f"transaction {tx_hash} was already used at another door ({held['stack']}); "
                      "nothing was credited")
            logger.error("topup: %s — nonce %s", detail, nonce[:18])
            raise TopupError(409, "payment_already_used", detail)
        raise TopupError(503, "deposit_registry_unavailable",
                         "the single-use deposit registry could not be read or written; retry — nothing was "
                         "credited", retryable=True)
    # 2. The authorization, in the ledger of spent x402 payments.
    if not payments.claim(tx_hash=tx_hash, pay_to=q.pay_to, payer=payer, amount_usd=paid_units / 10 ** decimals,
                          amount_atomic=paid_units, asset=q.token_contract, network=q.chain,
                          capability_id=TOPUP_CAPABILITY, nonce=nonce, receipt_id=reference):
        if not _spent_by_this_topup(payments, nonce, tx_hash):
            store.release(nonce, tx_hash)
            if payments.seen_nonce(nonce):
                raise TopupError(409, "payment_already_used",
                                 "this payment authorization was already spent on something else; nothing "
                                 "was credited")
            # Not recorded anywhere: the write failed (PaymentStore.claim swallows the reason).
            raise TopupError(503, "payment_record_unavailable",
                             "the payment could not be recorded; retry — nothing was credited", retryable=True)
    # 3. The credit — one transaction, idempotent on the reference.
    result = ledger.deposit(q.account_id, credited_mc, reference=reference,
                            note=f"USDC top-up {tx_hash[:18]}… from {payer[:10]}…")
    if result.get("error"):
        store.release(nonce, tx_hash)
        logger.error("topup: crediting %s for %s failed: %s", q.account_id, nonce[:18], result["error"])
        raise TopupError(500, "credit_failed", "the payment verified but the credit could not be written; "
                         "retry, or give the operator this nonce", retryable=True)
    detail = ""
    if paid_units > q.amount_units:
        detail = f"overpaid {paid_units - q.amount_units} base units; credited the quote"
        logger.error("topup: %s paid %s base units over its %s-unit quote %s — the excess is not credited; "
                     "refund it", payer[:12], paid_units - q.amount_units, q.amount_units, nonce[:18])
    elif paid_units < q.amount_units:
        detail = f"paid {paid_units} of {q.amount_units} base units; credited what arrived"
    store.credit(nonce, payer=payer, paid_units=paid_units, credited_mc=credited_mc, reference=reference,
                 detail=detail, now=now)
    logger.warning("topup: credited $%.5f to %s for %s (tx %s, payer %s)",
                   credits.mc_to_usd(credited_mc), q.account_id, nonce[:18], tx_hash[:18], payer[:12])
    done = store.get(nonce)
    assert done is not None
    return _credited_answer(done, ledger, replay=bool(result.get("idempotent_replay")), owner=owner,
                            decimals=decimals)


def _spent_by_this_topup(payments: settle.PaymentStore, nonce: str, tx_hash: str) -> bool:
    row = payments._conn.execute(
        "SELECT capability_id, settle_tx_hash FROM x402_payments WHERE nonce = ?", (nonce,),
    ).fetchone()
    return bool(row) and row["capability_id"] == TOPUP_CAPABILITY and row["settle_tx_hash"] == tx_hash.lower()
