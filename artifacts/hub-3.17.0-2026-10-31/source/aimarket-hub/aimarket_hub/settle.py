"""The market rail: the buyer pays the seller on-chain; the Hub only verifies.

INVARIANT
    USDC moves from the buyer to the listing's ``payout_address``. The Hub
    reads the chain (and, when present, the x402 ``PAYMENT-SIGNATURE`` that
    bound that transfer to this call) and never holds, credits, or reroutes
    the money. The host has no key and takes no cut.

This is the same economic joint as HESTIA, lifted to the catalogue:

    announce (hearth publishes ``payout_address``)
      → discover (Hub index / Bazaar ``payTo`` is that address)
      → pay seller (USDC on Base, EIP-3009 or a plain transfer)
      → consume (Hub or hearth verifies the receipt, then serves)

Wallet-address publishers are payable because they *are* the payee.
Operator-owned listings pay the operator's own wallet — the operator is
the seller, not a custodian. A priced listing with nobody to pay is
refused, not billed to the platform.

Credits and payment channels remain prepaid conveniences. They are not
how a seller is paid for a catalogue sale.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import re
import secrets
import time
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# keccak256("Transfer(address,indexed from,indexed to,uint256)")
TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
# keccak256("AuthorizationUsed(address,bytes32)") — EIP-3009. The token
# contract emits this when it accepts transferWithAuthorization; the nonce
# is the one the payer SIGNED. Matching it is what binds a payment to one
# call without the Hub holding a key.
AUTHORIZATION_USED_TOPIC = (
    "0x98de503528ee59b575ef0c0a2576a82497bfc029a5685b209e9ec333479b10a5"
)

_TX_HASH = re.compile(r"^0x[0-9a-fA-F]{64}$")
_ADDRESS = re.compile(r"^0x[0-9a-fA-F]{40}$")
_NONCE = re.compile(r"^0x[0-9a-fA-F]{64}$")


class PaymentError(RuntimeError):
    """The call has not been paid for. Carries a reason the buyer can act on."""


class PaymentFinal(PaymentError):
    """The transaction is mined and conclusively does not pay: it reverted, or what it moved is not
    this payment. Waiting changes nothing, unlike "not on chain yet" or a missing confirmation, so a
    caller may treat the payment as failed instead of pending forever."""


def is_address(value: str) -> bool:
    return bool(_ADDRESS.match((value or "").strip()))


def is_tx_hash(value: str) -> bool:
    return bool(_TX_HASH.match((value or "").strip()))


def mint_secret() -> str:
    return "0x" + secrets.token_hex(32)


def nonce_for_secret(secret: str) -> str:
    """The EIP-3009 nonce a payment secret commits to: sha256 of its 32 bytes.

    Once a payment is mined its nonce and transaction hash are public (the token logs
    AuthorizationUsed). A redemption that needed only those two let anyone watching the
    chain present them before the buyer did — and the buyer, who paid, was refused as
    "already spent". The nonce is therefore a commitment to a secret only the caller who
    took the 402 receives, and redeeming must open it. Same rule as hestia.payments.
    """
    return "0x" + hashlib.sha256(bytes.fromhex(secret.strip()[2:])).hexdigest()


def opens(secret: str, nonce: str) -> bool:
    if not (is_nonce(secret) and is_nonce(nonce)):
        return False
    return hmac.compare_digest(nonce_for_secret(secret), nonce.strip().lower())


def is_nonce(value: str) -> bool:
    return bool(_NONCE.match((value or "").strip()))


def to_units(amount_usd: float, decimals: int) -> int:
    """Dollars → token base units, rounded up so the seller never eats dust."""
    from decimal import Decimal, ROUND_CEILING
    scaled = Decimal(str(amount_usd)) * (10 ** decimals)
    return int(scaled.to_integral_value(rounding=ROUND_CEILING))


def seller_pay_to(cap: Any, *, operator_pay_to: str = "") -> str:
    """Who receives USDC for this listing. Empty means it cannot be sold.

    Order is the market joint, not a fallback stack that ends at the platform:

    1. The listing's own ``payout_address`` (what a hearth announces).
    2. A publisher identified by a 0x wallet — they *are* the payee.
    3. An operator-owned listing (no separate publisher) uses the operator's
       own seller wallet. That is the operator selling their work, not
       custody of someone else's sale.
    """
    explicit = str(getattr(cap, "payout_address", "") or "").strip()
    if is_address(explicit):
        return explicit
    publisher = str(getattr(cap, "publisher_id", "") or "").strip()
    if is_address(publisher):
        return publisher
    if not publisher and is_address(operator_pay_to):
        return operator_pay_to.strip()
    return ""


@dataclass(frozen=True)
class PaymentTerms:
    """What a buyer must do, in the units the chain uses."""

    chain: str
    token: str
    token_contract: str
    decimals: int
    pay_to: str
    amount_units: int
    amount_usd: float
    min_confirmations: int
    chain_id: int = 8453
    eip712_name: str = "USD Coin"
    eip712_version: str = "2"
    #: What the SELLER must receive. Equal to `amount_units` when there is no fee.
    seller_units: int = 0
    #: What the operator must receive, and where. Both zero/empty means no fee.
    fee_units: int = 0
    fee_to: str = ""
    #: Who the 402 names as `payTo` — the splitter when one is configured, so an
    #: off-the-shelf x402 client can produce both legs with one signature. The
    #: VERIFICATION still names the seller and the operator, never this address:
    #: what the hub requires is that both were paid, not that a particular contract
    #: was used to pay them.
    offer_to: str = ""

    def __post_init__(self) -> None:
        if not self.seller_units:
            object.__setattr__(self, "seller_units", self.amount_units)
        if not self.offer_to:
            object.__setattr__(self, "offer_to", self.pay_to)

    def as_x402_accept(self, resource: str = "") -> dict[str, Any]:
        return {
            "scheme": "exact",
            "network": self.chain,
            "maxAmountRequired": str(self.amount_units),
            "asset": self.token_contract,
            "payTo": self.offer_to,
            "resource": resource,
            "description": f"{self.amount_usd} {self.token}",
            "mimeType": "application/json",
            "maxTimeoutSeconds": 300,
            "extra": {
                "name": self.eip712_name,
                "version": self.eip712_version,
                "decimals": self.decimals,
                "symbol": self.token,
                "chainId": self.chain_id,
                "verifyingContract": self.token_contract,
            },
        }


def terms_for(cap: Any, *, operator_pay_to: str = "") -> PaymentTerms | None:
    """Priced listing with a seller, or None — never terms that pay nobody."""
    from aimarket_hub import x402

    price = float(getattr(cap, "price_per_call_usd", 0) or 0)
    pay_to = seller_pay_to(cap, operator_pay_to=operator_pay_to)
    if price <= 0 or not pay_to:
        return None
    profile = x402.asset_profile()
    if not profile:
        return None
    decimals = int(profile.get("decimals") or 6)
    extra = profile.get("extra") or {}
    gross = to_units(price, decimals)
    # A fee needs somewhere to send it AND something to split it. Configured without
    # either, it is not applied at all rather than quietly charged to the seller.
    bps = fee_bps()
    fee_to = fee_recipient() if bps else ""
    if not is_address(fee_to) or fee_to.lower() == pay_to.lower():
        bps, fee_to = 0, ""
    # The splitter is the whole mechanism: it is the address the 402 names, and it pays
    # both legs inside the one transaction the buyer sends. Without it deployed there is
    # nothing to name, `offer_to or pay_to` fell back to the SELLER, and the offer asked
    # the buyer for the full gross at the seller's address. The buyer would pay exactly
    # what the offer said, `verify_transfer` would then demand a fee leg that was never
    # sent, and the call would be refused — the buyer out the whole price, served
    # nothing, holding a payment that satisfies no invoice. The contract header says in
    # so many words that it is NOT deployed by default, so this is the shipped state of
    # any hub whose operator sets the fee and reads the fee documentation in order.
    #
    # Refusing to apply the fee is the safe failure: the rail keeps working exactly as
    # it does today and the operator earns nothing until the splitter exists. Loud,
    # because silently earning nothing is its own kind of wrong.
    splitter = splitter_address() if bps else ""
    if bps and not is_address(splitter):
        logger.error(
            "market fee is configured (%d bps to %s) but AIMARKET_MARKET_SPLITTER names "
            "no deployed contract — the fee is NOT being taken. Deploy MarketSplitter and "
            "set AIMARKET_MARKET_SPLITTER, or unset AIMARKET_MARKET_FEE_BPS.",
            bps, fee_to,
        )
        bps, fee_to, splitter = 0, "", ""
    seller_units, fee_units = fee_split(gross, bps)
    offer_to = splitter
    return PaymentTerms(
        chain=x402.chain(),
        token=x402.asset_symbol(),
        token_contract=str(profile["address"]),
        decimals=decimals,
        pay_to=pay_to,
        amount_units=gross,
        amount_usd=price,
        min_confirmations=_min_confirmations(),
        chain_id=x402.chain_id() or 8453,
        eip712_name=str(extra.get("name") or "USD Coin"),
        eip712_version=str(extra.get("version") or "2"),
        seller_units=seller_units,
        fee_units=fee_units,
        fee_to=fee_to,
        offer_to=offer_to or pay_to,
    )


def fee_bps() -> int:
    """The operator's share of a catalogue sale, in basis points. 0 = off.

    Capped at the same 10% the contract enforces, because the only thing worse than
    a hub that takes nothing is one whose advertised terms and whose contract
    disagree about how much.
    """
    try:
        return max(0, min(1000, int(os.getenv("AIMARKET_MARKET_FEE_BPS", "0"))))
    except ValueError:
        return 0


def fee_recipient() -> str:
    """Where the operator's share goes. Defaults to the hub's own x402 wallet."""
    from aimarket_hub import x402

    explicit = (os.getenv("AIMARKET_MARKET_FEE_TO") or "").strip()
    return explicit if is_address(explicit) else x402.recipient()


def splitter_address() -> str:
    """The `MarketSplitter` a 402 names as `payTo` so the buyer pays once.

    Without it a fee still settles — the hub requires both legs either way — but the
    buyer has to produce them itself, which off-the-shelf x402 clients cannot do.
    """
    value = (os.getenv("AIMARKET_MARKET_SPLITTER") or "").strip()
    return value if is_address(value) else ""


def fee_split(gross_units: int, bps: int) -> tuple[int, int]:
    """(seller_units, fee_units) — the same arithmetic the contract does.

    The OPERATOR's share is the computed one and the seller takes the remainder, so
    every rounding remainder goes to the seller and the fee is never more than `bps`
    of the gross. Mirrors `MarketSplitter._settle`; a divergence here would advertise
    terms the chain then refuses to satisfy.
    """
    fee = (int(gross_units) * int(bps)) // 10_000
    return int(gross_units) - fee, fee


def refuse_unbound_setting() -> None:
    """Say, once at startup, that AIMARKET_SETTLE_REQUIRE_BINDING=0 no longer does anything.

    There is no unbound payment any more. A plain transfer to the payee says nothing about
    who paid: its hash is public the moment it is mined, so whoever presents it first takes
    the call and the buyer who paid is refused as "already spent". Only a nonce committed to
    the buyer's secret says who paid, so every payment is bound and the switch is gone. An
    operator who still sets it to 0 is told so loudly rather than left believing it works.
    """
    raw = os.getenv("AIMARKET_SETTLE_REQUIRE_BINDING", "").strip().lower()
    if raw in ("0", "false", "no", "off"):
        logger.error(
            "AIMARKET_SETTLE_REQUIRE_BINDING=%s is ignored: an unbound payment is a plain "
            "transfer anyone who saw it on chain could redeem first, so every payment is "
            "bound to a nonce this hub minted. Remove the setting.", raw,
        )


def invoice_ttl_s() -> int:
    try:
        return max(30, int(os.getenv("AIMARKET_SETTLE_INVOICE_TTL_S", "300")))
    except ValueError:
        return 300


def max_age_s() -> int:
    try:
        return max(0, int(os.getenv("AIMARKET_SETTLE_MAX_AGE_S", "0")))
    except ValueError:
        return 0


def _min_confirmations() -> int:
    try:
        return max(1, int(os.getenv("AIMARKET_SETTLE_MIN_CONFIRMATIONS", "1")))
    except ValueError:
        return 1


def _topic_address(topic: str) -> str:
    return "0x" + (topic or "")[-40:]


def _rpc(url: str, method: str, params: list[Any], timeout: float) -> Any:
    response = httpx.post(
        url,
        json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
        timeout=timeout,
    )
    response.raise_for_status()
    body = response.json()
    if "error" in body:
        raise PaymentError(f"chain rpc refused {method}: {body['error']}")
    return body.get("result")


def _pool_transport(url: str, body: dict[str, Any], timeout: float) -> dict[str, Any]:
    # Through _rpc, looked up at call time: the pool keeps this function, and tests replace _rpc.
    return {"result": _rpc(url, body["method"], body["params"], timeout)}


def rpc_call(urls: list[str], method: str, params: list[Any], *, chain_id: int | None = None,
             timeout: float = 15.0) -> Any:
    """One JSON-RPC call over ``urls`` in rotation: a node that refuses (429, a block-range
    cap) rests and the next one answers. Raises chain_net.ChainNetError when none did."""
    from aimarket_hub import chain_net

    pool = chain_net.pool_for_urls(urls, chain_id=chain_id, timeout=timeout, transport=_pool_transport)
    return pool.call(method, params)


def rpc_urls(chain_id: int | None = None) -> list[str]:
    """Where to ask whether the seller was paid. Same exclusive-override rule
    as deposit verification: a bubble RPC must not fall through to mainnet."""
    from aimarket_hub import x402
    from aimarket_hub.deposit_verify import rpc_urls_for

    explicit = (os.getenv(f"AIMARKET_SETTLE_RPC_{chain_id}") if chain_id else "") or (os.getenv("AIMARKET_SETTLE_RPC_URL") or "").strip()
    if explicit:
        return [part.strip() for part in explicit.split(",") if part.strip()]
    if chain_id is None or chain_id == x402.chain_id():
        return rpc_urls_for(x402.chain())
    names = {1:"ethereum",8453:"base",10:"optimism",42161:"arbitrum",137:"polygon",84532:"base-sepolia"}
    return rpc_urls_for(names[chain_id]) if chain_id in names else []


def verify_transfer(
    *,
    tx_hash: str,
    terms: PaymentTerms,
    timeout: float = 10.0,
    max_age_s: int = 0,
    paid_before: float | None = None,
    require_nonce: str,
    rpc_url: str = "",
) -> dict[str, Any]:
    """Confirm ``tx_hash`` paid ``terms`` through the authorization over ``require_nonce``.

    Raises PaymentError with the reason. Returns the settled facts — never the caller's
    claim about them. Ported from ``hestia.payments.verify_transfer`` so Hub and hearth
    share one definition of "the seller was paid".

    The nonce is not optional. A transfer that no authorization over a nonce this hub
    minted moved is a payment to the seller by somebody, for something: nothing in it says
    it was this buyer, for this call.
    """
    if not is_tx_hash(tx_hash):
        raise PaymentError("payment reference must be a 0x transaction hash")
    tx_hash = tx_hash.strip().lower()
    want_nonce = (require_nonce or "").strip().lower()
    if not is_nonce(want_nonce):
        raise PaymentError(
            "payment is not bound to a call: pay with transferWithAuthorization signed "
            "over the nonce from the 402"
        )

    urls = [part.strip() for part in (rpc_url or "").split(",") if part.strip()] or rpc_urls(terms.chain_id)
    if not urls:
        raise PaymentError("no chain endpoint is configured")

    receipt = None
    used = ""
    transport_error: Exception | None = None
    for url in urls:
        try:
            if int(_rpc(url, "eth_chainId", [], timeout),16) != terms.chain_id:
                raise PaymentError("settlement RPC differs from the invoice chain")
            found = _rpc(url, "eth_getTransactionReceipt", [tx_hash], timeout)
        except (httpx.HTTPError, PaymentError, ValueError, TypeError) as exc:
            transport_error = PaymentError("cannot verify settlement RPC chain") if isinstance(exc,(ValueError,TypeError)) else exc
            continue
        if found:
            receipt, used = found, url
            break
    if receipt is None:
        if transport_error is not None and len(urls) == 1:
            raise transport_error
        raise PaymentError("transaction is not on chain yet")
    if str(receipt.get("status", "")).lower() not in ("0x1", "1"):
        raise PaymentFinal("transaction reverted")

    head = int(_rpc(used, "eth_blockNumber", [], timeout), 16)
    mined = int(receipt.get("blockNumber", "0x0"), 16)
    confirmations = max(0, head - mined + 1)
    if confirmations < terms.min_confirmations:
        raise PaymentError(
            f"payment has {confirmations} confirmation(s); "
            f"{terms.min_confirmations} required"
        )

    if max_age_s > 0 or paid_before is not None:
        block = _rpc(used, "eth_getBlockByNumber", [hex(mined), False], timeout)
        raw_ts = (block or {}).get("timestamp")
        if raw_ts is None:
            raise PaymentError("cannot establish payment age; refusing")
        try:
            mined_at = int(str(raw_ts), 16)
        except (TypeError, ValueError) as exc:
            raise PaymentError("cannot establish payment age; refusing") from exc
        age = time.time() - mined_at
        if paid_before is not None and mined_at >= paid_before:
            raise PaymentFinal("payment was mined after the invoice expired")
        if max_age_s > 0 and age > max_age_s:
            raise PaymentFinal(
                f"payment is {int(age)}s old; must be within {max_age_s}s of the "
                "call (an old transfer cannot be replayed as a fresh payment)"
            )

    want_to = terms.pay_to.lower()
    want_fee_to = (terms.fee_to or "").lower()
    want_token = terms.token_contract.lower()
    want_offer = (terms.offer_to or terms.pay_to).lower()
    paid = 0
    paid_fee = 0
    authorizer = ""
    nonce_seen = False
    bound_pays = False
    token_logs = [
        log for log in receipt.get("logs") or []
        if (log.get("topics") or []) and str(log.get("address", "")).lower() == want_token
    ]

    def transfer_at(index: int) -> tuple[str, str, int] | None:
        """(from, to, units) of the token log at `index`, when it is a Transfer."""
        if not 0 <= index < len(token_logs):
            return None
        topics = token_logs[index].get("topics") or []
        if len(topics) < 3 or (topics[0] or "").lower() != TRANSFER_TOPIC:
            return None
        return (_topic_address(topics[1]).lower(), _topic_address(topics[2]).lower(),
                int(token_logs[index].get("data") or "0x0", 16))

    for index, log in enumerate(token_logs):
        topics = log.get("topics") or []
        topic0 = (topics[0] or "").lower()
        if topic0 != AUTHORIZATION_USED_TOPIC or len(topics) < 3:
            continue
        if (topics[2] or "").lower() != want_nonce or bound_pays:
            continue
        nonce_seen = True
        who = _topic_address(topics[1]).lower()
        # Only what THIS authorization moved pays for the call — the token marks it used,
        # then transfers: its very next log. Counting every transfer to the payee let
        # anyone holding a buyer's signed authorization before it was mined bundle it
        # with a 1-unit authorization of their own and redeem the buyer's money under
        # their own invoice (hestia.payments has the same rule). Every match is tried,
        # not the first: nonces are per signer, so anyone can sign one over the same
        # nonce and put it ahead of the buyer's.
        moved = transfer_at(index + 1)
        if moved is None or moved[0] != who:
            continue
        if terms.fee_units:
            # A fee always goes through the splitter (terms_for), and the splitter pays
            # out of what THIS authorization delivered, in its next two transfers:
            # seller, then operator (MarketSplitter._settle). Legs counted across the
            # whole transaction let N authorizations share one fee leg, or pay a seller
            # of the payer's choosing through the splitter while another leg paid ours.
            to_seller, to_operator = transfer_at(index + 2), transfer_at(index + 3)
            if (moved[1] == want_offer and moved[2] >= terms.amount_units
                    and to_seller and to_seller[:2] == (want_offer, want_to)
                    and to_operator and to_operator[:2] == (want_offer, want_fee_to)):
                paid, paid_fee, authorizer, bound_pays = to_seller[2], to_operator[2], who, True
        elif moved[1] == want_to:
            paid, authorizer, bound_pays = moved[2], who, moved[2] >= terms.seller_units

    if not nonce_seen:
        raise PaymentFinal(
            "payment is not bound to this call: the transaction carries no "
            "EIP-3009 authorization for the nonce this hub issued. Pay with "
            "transferWithAuthorization using the nonce from the 402."
        )
    if not bound_pays:
        raise PaymentFinal(
            "the authorization for this nonce did not pay this call: its own transfer "
            f"must move at least the price from the signer to {terms.offer_to or terms.pay_to}"
            + (", and the splitter must pay the seller and the operator out of it"
               if terms.fee_units else "")
        )
    if paid == 0:
        raise PaymentFinal(
            f"no {terms.token} transfer to {terms.pay_to} found in that transaction"
        )
    if paid < terms.seller_units:
        raise PaymentFinal(
            f"paid {paid} base units, the seller's share is {terms.seller_units}"
        )
    # The fee is enforced by the chain, not by trusting a contract. Both legs must be
    # in THIS transaction: a buyer who paid the seller alone at the net price has not
    # paid for the call, and one who used the splitter produced both legs anyway. That
    # is why the hub never checks which address the payment was routed through.
    if terms.fee_units and paid_fee < terms.fee_units:
        raise PaymentFinal(
            f"the operator's share was not paid: {paid_fee} of {terms.fee_units} base "
            f"units reached {terms.fee_to}. Pay through the splitter named in the 402, "
            "or send both transfers in one transaction."
        )
    return {
        "tx_hash": tx_hash,
        "paid_units": paid,
        "fee_units": paid_fee,
        "confirmations": confirmations,
        "block_number": mined,
        "chain": terms.chain,
        "token": terms.token,
        "pay_to": terms.pay_to,
        "nonce": want_nonce,
        "authorizer": authorizer,
        "amount_usd": terms.amount_usd,
        "verified_at": time.time(),
    }


def extract_payment_ref(raw: str, payload: dict[str, Any] | None = None) -> dict[str, str]:
    """Tx hash + optional nonce from a header that may be a hash or x402 JSON."""
    text = (raw or "").strip()
    if is_tx_hash(text):
        return {"tx_hash": text.lower(), "nonce": ""}
    body = payload or {}
    extra = body.get("extra") if isinstance(body.get("extra"), dict) else {}
    inner = body.get("payload") if isinstance(body.get("payload"), dict) else {}
    auth = inner.get("authorization") if isinstance(inner.get("authorization"), dict) else (
        body.get("authorization") if isinstance(body.get("authorization"), dict) else {}
    )
    candidates = (
        body.get("txHash"), body.get("tx_hash"), body.get("transaction"),
        body.get("settleTx"), extra.get("txHash"), extra.get("tx_hash"),
        inner.get("txHash"), inner.get("tx_hash"),
    )
    tx_hash = ""
    for item in candidates:
        if is_tx_hash(str(item or "")):
            tx_hash = str(item).strip().lower()
            break
    nonce = str(
        body.get("nonce") or extra.get("nonce") or auth.get("nonce") or ""
    ).strip()
    return {"tx_hash": tx_hash, "nonce": nonce if is_nonce(nonce) else ""}


class InvoiceStore:
    """What a 402 promised, so settlement checks the terms the Hub advertised."""

    def __init__(self, conn: Any):
        self._conn = conn

    def mint(
        self, *, nonce: str, capability_id: str, pay_to: str, amount_units: int, ttl_s: int,
        secret: str = "",
    ) -> dict[str, Any]:
        now = time.time()
        expires = now + max(30, int(ttl_s))
        # Every unauthenticated 402 writes one of these, each holding a live secret. Once an
        # invoice is a day past its expiry no redemption can use it (and a replay of its
        # nonce is still refused: unknown, and its claim stays in x402_payments), so it goes.
        self._conn.execute("DELETE FROM settle_invoices WHERE expires_at < ?", (now - 86_400,))
        # The secret is kept so this hub's own A2A bridge can redeem for the task that was
        # quoted (a2a.py); anything outside the hub gets it only in that 402's body.
        self._conn.execute(
            "INSERT OR REPLACE INTO settle_invoices "
            "(nonce, capability_id, pay_to, amount_units, expires_at, consumed_at, tx_hash, secret) "
            "VALUES (?, ?, ?, ?, ?, 0, '', ?)",
            (nonce.lower(), capability_id, pay_to.lower(), str(amount_units), expires, secret.lower()),
        )
        self._conn.commit()
        return {
            "nonce": nonce.lower(),
            "capability_id": capability_id,
            "pay_to": pay_to.lower(),
            "amount_units": amount_units,
            "expires_at": expires,
        }

    def secret_for(self, nonce: str) -> str:
        row = self._conn.execute(
            "SELECT secret FROM settle_invoices WHERE nonce = ?", ((nonce or "").lower(),),
        ).fetchone()
        return str(row["secret"] or "") if row else ""

    def get(self, nonce: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT * FROM settle_invoices WHERE nonce = ?",
            (nonce.lower(),),
        ).fetchone()
        return dict(row) if row else None

    def consume(self, nonce: str, tx_hash: str) -> bool:
        cur = self._conn.execute(
            "UPDATE settle_invoices SET consumed_at = ?, tx_hash = ? "
            "WHERE nonce = ? AND consumed_at = 0",
            (time.time(), tx_hash.lower(), nonce.lower()),
        )
        self._conn.commit()
        return (cur.rowcount or 0) > 0

    def release(self, nonce: str) -> None:
        if not nonce:
            return
        self._conn.execute(
            "UPDATE settle_invoices SET consumed_at = 0, tx_hash = '' WHERE nonce = ?",
            (nonce.lower(),),
        )
        self._conn.commit()


class PaymentStore:
    """Spent on-chain payments: one transfer buys one Hub call."""

    def __init__(self, conn: Any):
        self._conn = conn

    def seen_tx(self, tx_hash: str) -> bool:
        row = self._conn.execute(
            "SELECT settle_tx_hash FROM x402_payments WHERE settle_tx_hash = ?",
            (tx_hash.lower(),),
        ).fetchone()
        return row is not None

    def seen_whole(self, tx_hash: str) -> bool:
        """True when the transaction was claimed whole, as an unbound payment once was."""
        row = self._conn.execute(
            "SELECT nonce FROM x402_payments WHERE settle_tx_hash = ? AND nonce = ?",
            (tx_hash.lower(), tx_hash.strip()),
        ).fetchone()
        return row is not None

    def seen_nonce(self, nonce: str) -> bool:
        row = self._conn.execute(
            "SELECT nonce FROM x402_payments WHERE nonce = ?",
            (str(nonce),),
        ).fetchone()
        return row is not None

    def claim(
        self,
        *,
        tx_hash: str,
        pay_to: str,
        payer: str,
        amount_usd: float,
        amount_atomic: int | str,
        asset: str,
        network: str,
        capability_id: str = "",
        nonce: str = "",
        receipt_id: str = "",
    ) -> bool:
        """Record a settled payment. False if this payment was already spent.

        A payment is its authorization: a transaction may carry several (a smart wallet
        settling two invoices at once), and keying them on the hash let whoever redeemed
        first deny every other payer in it. Rows keyed on the transaction itself were
        written while unbound payments still existed; such a transaction stays spent
        whole and pays nothing more.
        """
        key = (nonce or "").strip()
        if not key or key.lower() == tx_hash.strip().lower():
            return False
        if self.seen_nonce(key) or self.seen_whole(tx_hash):
            return False
        try:
            self._conn.execute(
                "INSERT INTO x402_payments "
                "(nonce, payer, amount_atomic, amount_usd, asset, network, "
                "receipt_id, capability_id, status, settle_tx_hash, settled_at, pay_to) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'settled', ?, datetime('now'), ?)",
                (
                    key, payer or "",
                    str(amount_atomic), float(amount_usd),
                    asset, network, receipt_id, capability_id,
                    tx_hash.lower(), pay_to.lower(),
                ),
            )
            self._conn.commit()
        except Exception:
            return False
        return True

    def release(self, tx_hash: str, nonce: str) -> None:
        """Un-spend ONE claim, the authorization's (releasing by hash alone would un-spend
        every other payment in the same tx)."""
        if not tx_hash or not nonce:
            return
        self._conn.execute(
            "DELETE FROM x402_payments WHERE settle_tx_hash = ? AND nonce = ?",
            (tx_hash.lower(), nonce.strip()),
        )
        self._conn.commit()
