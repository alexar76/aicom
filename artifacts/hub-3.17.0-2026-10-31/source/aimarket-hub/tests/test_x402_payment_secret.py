"""Only the buyer who took the 402 can redeem what they paid.

Once a transferWithAuthorization is mined, its transaction hash and its nonce are public: the
token contract logs AuthorizationUsed(authorizer, nonce). A redemption that needed only those
two let anyone watching the chain present them first — and the buyer who paid was then told
"already spent". The 402's nonce is therefore sha256 of a secret that goes to that caller and
nowhere else, and redeeming must open it (settle.nonce_for_secret, _settle_market_payment).

Real receipts here (logs in FiatToken's order), not a stubbed verifier, because two of the
rules live in how the receipt is read: only the transfer an authorization itself moved pays
for it, and each authorization in a transaction is its own payment.
"""
from __future__ import annotations

import base64
import hashlib
import json
import time

import pytest
from aimarket_hub import settle

from tests.test_settle import BUYER, SELLER, USDC, _hub, _topic_addr

AUTH_USED = settle.AUTHORIZATION_USED_TOPIC
TRANSFER = settle.TRANSFER_TOPIC
ATTACKER = "0x" + "ad" * 20
UNITS = 20_000            # PRICE 0.02 in six-decimal USDC
BODY = {"product_id": "x-pay", "capability_id": "x.pay@v1", "input": {}, "source_hub": "local"}


def auth_used(who: str, nonce: str) -> dict:
    return {"address": USDC, "topics": [AUTH_USED, _topic_addr(who), nonce], "data": "0x"}


def transfer(frm: str, to: str, units: int) -> dict:
    return {"address": USDC, "topics": [TRANSFER, _topic_addr(frm), _topic_addr(to)], "data": hex(units)}


def chain(monkeypatch, logs: list[dict], *, mined_at: int | None = None) -> None:
    """A chain holding one receipt. ``mined_at`` is its block's timestamp; without it the
    chain cannot say when the payment was mined, as a pruned or flaky node cannot."""
    def _post(url, json=None, timeout=None):
        method = json["method"]

        class R:
            @staticmethod
            def raise_for_status() -> None:
                return None

            @staticmethod
            def json() -> dict:
                if method == "eth_chainId": return {"result": hex(8453)}
                if method == "eth_blockNumber":
                    return {"result": hex(101)}
                if method == "eth_getBlockByNumber" and mined_at is not None:
                    return {"result": {"number": hex(100), "timestamp": hex(mined_at)}}
                return {"result": {"status": "0x1", "blockNumber": hex(100), "logs": logs}}

        return R()

    monkeypatch.setattr("aimarket_hub.settle.httpx.post", _post)
    monkeypatch.setattr("aimarket_hub.settle.rpc_urls", lambda *args: ["http://rpc.invalid"])


@pytest.fixture
def hub(monkeypatch, tmp_path):
    with _hub(monkeypatch, tmp_path, AIMARKET_X402_ACCEPT="1",
              AIFACTORY_CRYPTO_ENABLED="1", AIMARKET_SETTLE_MAX_AGE_S="0") as client:
        yield client


def quote(client) -> dict:
    r = client.post("/ai-market/v2/invoke", json=BODY)
    assert r.status_code == 402, r.text
    return {"body": r.json(), "headers": r.headers}


def redeem(client, tx: str, **headers):
    sent = {"X-PAYMENT": tx, **{f"X-Payment-{k.title()}": v for k, v in headers.items()}}
    return client.post("/ai-market/v2/invoke", json=BODY, headers=sent)


def test_the_402_commits_its_nonce_to_a_secret_carried_in_its_body_only(hub):
    q = quote(hub)
    body = q["body"]
    assert body["nonce"] == settle.nonce_for_secret(body["payment_secret"])
    # Not in PAYMENT-REQUIRED, not in accepts[].extra, not in any header: those are what
    # proxies log and what the A2A bridge persists with a task.
    secret = body["payment_secret"]
    assert secret not in json.dumps(body.get("accepts") or [])
    assert all(secret not in str(v) for v in q["headers"].values())
    required = q["headers"].get("payment-required")
    if required:
        assert secret not in base64.b64decode(required + "=" * (-len(required) % 4)).decode()
    assert quote(hub)["body"]["payment_secret"] != secret


def test_someone_watching_the_chain_cannot_redeem_the_buyers_invoice(hub, monkeypatch):
    q = quote(hub)["body"]
    chain(monkeypatch, [auth_used(BUYER, q["nonce"]), transfer(BUYER, SELLER, UNITS)])
    tx = "0x" + "1" * 64
    guess = "0x" + hashlib.sha256(b"a guess").hexdigest()
    for attempt in ({}, {"nonce": q["nonce"]}, {"nonce": q["nonce"], "secret": q["nonce"]},
                    {"nonce": q["nonce"], "secret": guess}):
        watcher = redeem(hub, tx, **attempt)
        assert watcher.status_code == 402, (attempt, watcher.text)
    assert settle.InvoiceStore(hub.hub_db._conn).get(q["nonce"])["consumed_at"] == 0
    buyer = redeem(hub, tx, secret=q["payment_secret"])
    assert buyer.status_code == 200, buyer.text
    again = redeem(hub, tx, secret=q["payment_secret"])
    assert again.status_code == 402


def test_a_buyers_authorization_bundled_by_someone_else_pays_only_the_buyer(hub, monkeypatch):
    """Whoever holds the buyer's signed authorization before it is mined can submit it inside
    their own transaction next to a 1-unit authorization over an invoice they took. Only the
    transfer an authorization itself moved pays for it."""
    buyer, attacker = quote(hub)["body"], quote(hub)["body"]
    chain(monkeypatch, [
        auth_used(BUYER, buyer["nonce"]), transfer(BUYER, SELLER, UNITS),
        auth_used(ATTACKER, attacker["nonce"]), transfer(ATTACKER, SELLER, 1),
    ])
    tx = "0x" + "2" * 64
    stolen = redeem(hub, tx, secret=attacker["payment_secret"])
    assert stolen.status_code == 402 and "did not pay this call" in stolen.json()["detail"]
    assert redeem(hub, tx, secret=buyer["payment_secret"]).status_code == 200


@pytest.mark.parametrize("logs", [
    lambda n: [auth_used(BUYER, n), transfer(BUYER, ATTACKER, UNITS), transfer(ATTACKER, SELLER, UNITS)],
    lambda n: [auth_used(BUYER, n), transfer(ATTACKER, SELLER, UNITS)],
    lambda n: [transfer(BUYER, SELLER, UNITS), auth_used(BUYER, n)],
], ids=["authorization-paid-elsewhere", "transfer-from-someone-else", "authorization-moved-nothing"])
def test_an_authorization_whose_own_transfer_did_not_pay_the_seller_buys_nothing(hub, monkeypatch, logs):
    q = quote(hub)["body"]
    chain(monkeypatch, logs(q["nonce"]))
    assert redeem(hub, "0x" + "3" * 64, secret=q["payment_secret"]).status_code == 402


def test_two_payments_in_one_transaction_buy_two_calls(hub, monkeypatch):
    """A smart wallet may settle two invoices at once. Keyed on the transaction hash, the
    first redeemed denied the other payer — or the same payer — their paid call."""
    first, second = quote(hub)["body"], quote(hub)["body"]
    chain(monkeypatch, [
        auth_used(BUYER, first["nonce"]), transfer(BUYER, SELLER, UNITS),
        auth_used(BUYER, second["nonce"]), transfer(BUYER, SELLER, UNITS),
    ])
    tx = "0x" + "4" * 64
    for q in (first, second):
        r = redeem(hub, tx, secret=q["payment_secret"])
        assert r.status_code == 200, r.text
    assert redeem(hub, tx, secret=first["payment_secret"]).status_code == 402


def test_a_claim_is_one_authorization_and_nothing_is_claimed_whole(hub):
    store = settle.PaymentStore(hub.hub_db._conn)
    common = {"pay_to": SELLER, "payer": BUYER, "amount_usd": 0.02, "amount_atomic": UNITS,
              "asset": USDC, "network": "base"}
    whole, bundled = "0x" + "5" * 64, "0x" + "6" * 64
    n1, n2 = "0x" + "a1" * 32, "0x" + "a2" * 32
    assert not store.claim(tx_hash=whole, nonce=whole, **common)   # no unbound payment
    assert not store.claim(tx_hash=whole, nonce="", **common)
    assert not store.seen_tx(whole)
    assert store.claim(tx_hash=bundled, nonce=n1, **common)
    assert store.claim(tx_hash=bundled, nonce=n2, **common)        # its own payment
    # Un-spending one authorization leaves the other spent; releasing without a nonce
    # un-spends nothing.
    store.release(bundled, "")
    assert store.seen_nonce(n1) and store.seen_nonce(n2)
    store.release(bundled, n1)
    assert not store.seen_nonce(n1) and store.seen_nonce(n2)
    assert store.claim(tx_hash=bundled, nonce=n1, **common)


def test_a_transaction_spent_whole_before_binding_pays_nothing_more(hub):
    """Rows keyed on the transaction itself were written while unbound payments existed."""
    store = settle.PaymentStore(hub.hub_db._conn)
    legacy = "0x" + "5" * 64
    hub.hub_db._conn.execute(
        "INSERT INTO x402_payments (nonce, payer, amount_atomic, amount_usd, asset, network, "
        "receipt_id, capability_id, status, settle_tx_hash, settled_at, pay_to) "
        "VALUES (?, ?, ?, ?, ?, ?, '', '', 'settled', ?, datetime('now'), ?)",
        (legacy, BUYER, str(UNITS), 0.02, USDC, "base", legacy, SELLER.lower()),
    )
    hub.hub_db._conn.commit()
    assert not store.claim(tx_hash=legacy, nonce="0x" + "a1" * 32, pay_to=SELLER, payer=BUYER,
                           amount_usd=0.02, amount_atomic=UNITS, asset=USDC, network="base")


def test_the_nonce_rule_is_the_hearths():
    """One published rule for hub and hearth alike: sha256 of the secret's 32 bytes."""
    assert settle.nonce_for_secret("0x" + "00" * 32) == (
        "0x66687aadf862bd776c8fc18b8e9f8e20089714856ee233b3902a591d0d5f2925"
    )
    secret = settle.mint_secret()
    assert settle.opens(secret, settle.nonce_for_secret(secret))
    assert not settle.opens(settle.nonce_for_secret(secret), settle.nonce_for_secret(secret))


def test_a_same_nonce_authorization_placed_first_cannot_deny_the_buyer(hub, monkeypatch):
    """EIP-3009 nonces are per signer: anyone can sign a 1-unit authorization over the
    buyer's nonce and put it ahead of the buyer's in a bundle. Every match is tried."""
    q = quote(hub)["body"]
    chain(monkeypatch, [
        auth_used(ATTACKER, q["nonce"]), transfer(ATTACKER, SELLER, 1),
        auth_used(BUYER, q["nonce"]), transfer(BUYER, SELLER, UNITS),
    ])
    assert redeem(hub, "0x" + "7" * 64, secret=q["payment_secret"]).status_code == 200


def test_an_old_invoice_and_its_secret_do_not_outlive_their_use(hub):
    store = settle.InvoiceStore(hub.hub_db._conn)
    stale = "0x" + "b1" * 32
    store.mint(nonce=stale, capability_id="x.pay@v1", pay_to=SELLER, amount_units=UNITS,
               ttl_s=60, secret="0x" + "c1" * 32)
    hub.hub_db._conn.execute("UPDATE settle_invoices SET expires_at = 1 WHERE nonce = ?", (stale,))
    hub.hub_db._conn.commit()
    quote(hub)                                   # any 402 sweeps
    assert store.get(stale) is None and store.secret_for(stale) == ""


@pytest.mark.parametrize("mined_at_offset,redeemed", [(-1, True), (0, False), (None, False)])
def test_an_expired_invoice_is_redeemed_only_by_a_payment_mined_before_it_expired(
    hub, monkeypatch, mined_at_offset, redeemed,
):
    """The TTL bounds when the buyer may PAY, not when the hub hears of it: a transfer mined
    in time is the buyer's even if the retry arrives after expiry (a slow block, a client
    that crashed between paying and presenting). One mined at or after expiry paid a quote
    that had already lapsed, and a chain that cannot say when it was mined proves nothing."""
    q = quote(hub)["body"]
    store = settle.InvoiceStore(hub.hub_db._conn)
    expired_at = int(time.time()) - 60           # whole seconds, as block timestamps are
    hub.hub_db._conn.execute("UPDATE settle_invoices SET expires_at = ? WHERE nonce = ?",
                             (expired_at, q["nonce"]))
    hub.hub_db._conn.commit()
    chain(monkeypatch, [auth_used(BUYER, q["nonce"]), transfer(BUYER, SELLER, UNITS)],
          mined_at=None if mined_at_offset is None else expired_at + mined_at_offset)

    r = redeem(hub, "0x" + "e" * 64, secret=q["payment_secret"])
    if redeemed:
        assert r.status_code == 200, r.text
        assert store.get(q["nonce"])["consumed_at"] > 0
    else:
        assert r.status_code == 402, r.text
        assert r.json()["detail"] == (
            "payment was mined after the invoice expired" if mined_at_offset is not None
            else "cannot establish payment age; refusing")
        assert store.get(q["nonce"])["consumed_at"] == 0, "a refused payment spent the invoice"


# ── An operator fee: every leg belongs to the authorization that paid it ──────────

SPLITTER = "0x5911770000000000000000000000000000000002"
OPERATOR = "0x1218Ff3600000000000000000000000000000a0a"


@pytest.fixture
def fee_terms(monkeypatch):
    from aimarket_hub.models import Capability

    for key, value in {"AIMARKET_X402_CHAIN": "base", "AIMARKET_MARKET_FEE_BPS": "250",
                       "AIMARKET_MARKET_FEE_TO": OPERATOR, "AIMARKET_MARKET_SPLITTER": SPLITTER}.items():
        monkeypatch.setenv(key, value)
    terms = settle.terms_for(Capability(capability_id="a@v1", product_id="p", name="n",
                                        payout_address=SELLER, price_per_call_usd=0.02))
    assert terms.fee_units and terms.offer_to.lower() == SPLITTER.lower()
    return terms


def _verify(terms, nonce):
    return settle.verify_transfer(tx_hash="0x" + "8" * 64, terms=terms, require_nonce=nonce)


def test_a_splitter_payment_is_its_own_three_transfers(monkeypatch, fee_terms):
    t, n = fee_terms, "0x" + "e1" * 32
    chain(monkeypatch, [
        auth_used(BUYER, n), transfer(BUYER, SPLITTER, t.amount_units),
        transfer(SPLITTER, SELLER, t.seller_units), transfer(SPLITTER, OPERATOR, t.fee_units),
    ])
    settled = _verify(t, n)
    assert (settled["paid_units"], settled["fee_units"]) == (t.seller_units, t.fee_units)


@pytest.mark.parametrize("attack", ["shared-fee-leg", "splitter-to-another-seller", "operator-unpaid"])
def test_a_fee_leg_or_seller_leg_cannot_be_borrowed_from_another_authorization(monkeypatch, fee_terms, attack):
    t, n1, n2 = fee_terms, "0x" + "e2" * 32, "0x" + "e3" * 32
    logs = {
        # Two authorizations each pay the seller its share directly; one fee transfer.
        "shared-fee-leg": [auth_used(BUYER, n1), transfer(BUYER, SELLER, t.seller_units),
                           auth_used(BUYER, n2), transfer(BUYER, SELLER, t.seller_units),
                           transfer(BUYER, OPERATOR, t.fee_units)],
        # Full price into the splitter naming the payer as seller, plus a share to ours.
        "splitter-to-another-seller": [
            auth_used(ATTACKER, n1), transfer(ATTACKER, SPLITTER, t.amount_units),
            transfer(SPLITTER, ATTACKER, t.seller_units), transfer(SPLITTER, OPERATOR, t.fee_units),
            auth_used(ATTACKER, n2), transfer(ATTACKER, SELLER, t.seller_units)],
        # Through the splitter, but the operator's leg is missing.
        "operator-unpaid": [auth_used(BUYER, n1), transfer(BUYER, SPLITTER, t.amount_units),
                            transfer(SPLITTER, SELLER, t.amount_units)],
    }[attack]
    chain(monkeypatch, logs)
    for nonce in (n1, n2):
        with pytest.raises(settle.PaymentError):
            _verify(t, nonce)


def test_a_browser_client_may_send_the_secret(monkeypatch, tmp_path):
    """With CORS on, a header missing from the allow-list never leaves a browser: a web
    x402 client could pay but never redeem."""
    with _hub(monkeypatch, tmp_path, AIMARKET_CORS_ORIGINS="https://app.example") as client:
        r = client.options("/ai-market/v2/invoke", headers={
            "Origin": "https://app.example", "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "x-payment, x-payment-secret"})
    assert r.status_code == 200, r.text
    assert "x-payment-secret" in r.headers.get("access-control-allow-headers", "").lower()


def test_a_402_buys_the_call_it_quoted_and_no_other(hub, monkeypatch):
    """The same seller may list several capabilities at the same price or less. A payment
    over one 402's nonce buys the call that 402 quoted, not a different one of theirs."""
    from aimarket_hub.models import Capability

    hub.hub_db.upsert_capability(Capability(
        capability_id="x.other@v1", product_id="x-other", name="Other pack",
        description="static", price_per_call_usd=0.01, source_hub="local",
        invoke_url="", prompt_template=json.dumps({"answer": "other"}),
        payout_address=SELLER, publisher_id=SELLER,
    ))
    q = quote(hub)["body"]
    chain(monkeypatch, [auth_used(BUYER, q["nonce"]), transfer(BUYER, SELLER, UNITS)])
    tx = "0x" + "9" * 64
    other = {"product_id": "x-other", "capability_id": "x.other@v1", "input": {}, "source_hub": "local"}
    moved = hub.post("/ai-market/v2/invoke", json=other,
                     headers={"X-PAYMENT": tx, "X-Payment-Secret": q["payment_secret"]})
    assert moved.status_code == 402 and "quoted for x.pay@v1" in moved.json()["detail"]
    assert settle.InvoiceStore(hub.hub_db._conn).get(q["nonce"])["consumed_at"] == 0
    assert redeem(hub, tx, secret=q["payment_secret"]).status_code == 200
