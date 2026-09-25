"""One on-chain transfer buys one thing, whichever door it is presented at.

Synthetic chain answers and throwaway stores only: no RPC, no real transfers.
Each test names the audit finding it pins down.
"""
from __future__ import annotations

import asyncio
import sqlite3
import threading
import time
import uuid
from types import SimpleNamespace

import pytest
from eth_abi import decode as abi_decode
from eth_abi import encode as abi_encode
from eth_account import Account
from eth_account.messages import encode_defunct
from fastapi import HTTPException
from web3.providers.base import BaseProvider

PLATFORM = "0x" + "12" * 20
PRODUCT = "prod-abc123def456"
SITE = "https://shop.example.test"
TX = "0x" + "ab" * 32


def _chain_key(tx: str) -> str:
    # web3 sends any case, with or without 0x, as one lowercase 0x hash.
    body = tx.strip()
    body = body[2:] if body[:2].lower() == "0x" else body
    return "0x" + body.lower()


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path / "data"))
    monkeypatch.setenv("AIFACTORY_CRYPTO_ENABLED", "1")
    monkeypatch.setenv("CUSTOMER_JWT_SECRET", "synthetic-test-secret-000000000000000")
    monkeypatch.setenv("AIFACTORY_AI_MARKET_DEMO_PAYMENT", "0")
    monkeypatch.setenv("AIFACTORY_UNI_ENABLED", "0")
    monkeypatch.setenv("AIFACTORY_AI_MARKET_CHAIN", "base")
    monkeypatch.setenv("AIFACTORY_AI_MARKET_TOKEN", "USDT")
    monkeypatch.setenv("NEXT_PUBLIC_SITE_URL", SITE)
    for key in ("AIFACTORY_PROD", "AIFACTORY_PRODUCTION", "AIFACTORY_ENV",
                "AIFACTORY_AI_MARKET_CONTRACT", "AIFACTORY_AI_MARKET_ALLOW_UNPROVEN_PAYER",
                "AIMARKET_DEPOSIT_CLAIMS_DIR"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("AIFACTORY_AI_MARKET_REQUIRE_PAYER_PROOF", "1")

    from web.backend.api import ai_market, payment
    from web.backend.services import customer_auth
    from web.backend.services.ai_market_protocol import channels
    from web.backend.services.commerce import CommerceService
    import web.backend.services.uni_bridge as bridge

    store = CommerceService(base_dir=str(tmp_path / "store"))
    for mod, attr in ((payment, "commerce"), (ai_market, "commerce"),
                      (channels, "_commerce"), (customer_auth, "_commerce")):
        monkeypatch.setattr(mod, attr, store)
    monkeypatch.setattr(payment, "_pending_payments", {})
    monkeypatch.setattr(payment, "_confirm_locks", {})
    monkeypatch.setattr(payment, "PENDING_PAYMENTS_FILE", tmp_path / "pending.json")
    monkeypatch.setattr(payment, "payment_verify_stub_enabled", lambda: False)
    monkeypatch.setattr(payment, "RECIPIENT_ADDRESS_EVM", PLATFORM)
    monkeypatch.setattr(payment, "_catalog_checkout_usdt", lambda p: 5.0)
    monkeypatch.setattr(ai_market, "pilot_settlement_price_usdt", lambda p: 5.0)
    monkeypatch.setattr(bridge, "credit_payment_confirm", lambda **kw: None)

    async def _no_fanout(event):
        return []
    monkeypatch.setattr(ai_market, "_fanout_external_integrations", _no_fanout)

    transfers: dict[str, dict] = {}

    def _verify(*, chain, tx_hash, expected_recipient, expected_amount, expected_token):
        rec = transfers.get(_chain_key(tx_hash))
        if rec is None:
            return {"verified": False, "error": "Transaction not found on chain"}
        if expected_recipient.lower() != PLATFORM.lower() or rec["amount"] < expected_amount:
            return {"verified": False, "error": "no matching transfer"}
        return {"verified": True, "confirmations": 100, "from": rec["from"], "to": PLATFORM,
                "amount": rec["amount"], "token": expected_token, "block_number": 100}

    monkeypatch.setattr(payment, "_verify_evm_transaction", _verify)

    def pay(tx: str, sender: str, amount: float = 5.0) -> None:
        transfers[_chain_key(tx)] = {"from": sender, "amount": amount}

    def customer(email: str) -> dict:
        row = store.register_customer(email, "synthetic-password")
        return {"sub": row["id"], "email": row["email"],
                "token": store.create_token(row["id"], row["email"])}

    return SimpleNamespace(payment=payment, ai_market=ai_market, channels=channels,
                           store=store, pay=pay, customer=customer, tmp=tmp_path)


def _call(coro):
    try:
        return 200, asyncio.run(coro)
    except HTTPException as exc:
        return exc.status_code, exc.detail


def _quote(env, buyer: dict, payment_id: str | None = None) -> dict:
    pid = payment_id or f"pay-{uuid.uuid4().hex[:10]}"
    quote = {"payment_id": pid, "product_id": PRODUCT, "amount": 5.0, "currency": "USDC",
             "chain": "base", "status": "pending", "customer_id": buyer["sub"],
             "customer_email": buyer["email"], "wallet_address": PLATFORM,
             "created_at": time.time(), "expires_at": time.time() + 3600}
    env.payment._pending_payments[pid] = quote
    return quote


def _checkout(env, buyer: dict, tx: str, signer=None, signature: str | None = None):
    from web.backend.schemas.api_requests import ConfirmPaymentRequest
    from web.backend.services.payment_claim import claim_message

    quote = _quote(env, buyer)
    if signature is None:
        signature = ""
        if signer is not None:
            signature = signer.sign_message(encode_defunct(text=claim_message(quote, tx))).signature.hex()
    status, out = _call(env.payment.confirm_payment(
        quote["payment_id"], ConfirmPaymentRequest(tx_hash=tx, payer_signature=signature),
        customer={"sub": buyer["sub"], "email": buyer["email"]}, test_confirmations=None))
    return status, out, quote


def _pilot(env, tx: str, *, who: dict | None = None, signature: str = ""):
    from web.backend.schemas.api_requests import AiMarketSettlementConfirmRequest

    body = AiMarketSettlementConfirmRequest(product_id=PRODUCT, tx_hash=tx, payer_signature=signature)
    auth = f"Bearer {who['token']}" if who else None
    return _call(env.ai_market.confirm_pilot_settlement(body, authorization=auth))


def _pilot_signed(env, tx: str, who: dict, signer):
    """Ask the pilot for its challenge, sign it with ``signer``, and send it back.

    Returns the first answer as is when the pilot refused before asking for a proof.
    """
    status, detail = _pilot(env, tx, who=who)
    if status != 400 or not isinstance(detail, dict) or "challenge" not in detail:
        return status, detail
    sig = signer.sign_message(encode_defunct(text=detail["challenge"])).signature.hex()
    return _pilot(env, tx, who=who, signature=sig)


def _orders(env) -> list[tuple]:
    return [tuple(r) for r in env.store.conn.execute(
        "SELECT payment_id, customer_id, tx_hash FROM orders ORDER BY created_at").fetchall()]


# ── [high] anonymous pilot front-runs the signed checkout ────────────────────

def test_anonymous_pilot_cannot_take_a_checkout_transfer(env):
    payer = Account.create()
    victim = env.customer("victim@example.test")
    env.pay(TX, payer.address)

    status, _ = _pilot(env, TX)  # a stranger who copied the hash from an explorer
    assert status == 401
    assert _orders(env) == []

    status, out, _ = _checkout(env, victim, TX, signer=payer)
    assert status == 200 and out["status"] == "confirmed", out
    assert [o[1] for o in _orders(env)] == [victim["sub"]]


def test_signed_in_stranger_needs_the_payers_signature_at_the_pilot(env):
    payer, stranger_wallet = Account.create(), Account.create()
    stranger = env.customer("stranger@example.test")
    env.pay(TX, payer.address)

    status, detail = _pilot(env, TX, who=stranger)
    assert status == 400 and "challenge" in detail
    assert stranger["sub"] in detail["challenge"]  # the proof names the account it credits

    status, _ = _pilot_signed(env, TX, stranger, stranger_wallet)
    assert status == 403
    assert _orders(env) == []


def test_pilot_with_payer_proof_issues_one_license_and_spends_the_transfer(env):
    payer = Account.create()
    buyer = env.customer("buyer@example.test")
    env.pay(TX, payer.address)

    status, detail = _pilot(env, TX, who=buyer)
    assert status == 400 and "challenge" in detail, (status, detail)
    status, out = _pilot_signed(env, TX, buyer, payer)
    assert status == 200 and out["status"] == "entitlement_activated", out
    assert [o[1:] for o in _orders(env)] == [(buyer["sub"], TX)]

    # The same transfer cannot then also buy a checkout license.
    status, _, _ = _checkout(env, buyer, TX, signer=payer)
    assert status == 409
    assert len(_orders(env)) == 1


# ── [high] a bare 64-hex hash is the same transfer as its 0x form ────────────

def test_bare_hex_hash_is_the_same_transfer(env):
    from web.backend.services.payment_claim import canonical_tx_hash

    assert canonical_tx_hash("AB" * 32) == TX
    assert canonical_tx_hash(" 0X" + "AB" * 32) == TX
    assert canonical_tx_hash("A" * 88) == "A" * 88  # base58 stays case-sensitive

    payer = Account.create()
    buyer = env.customer("buyer@example.test")
    env.pay(TX, payer.address)
    status, _, _ = _checkout(env, buyer, TX, signer=payer)
    assert status == 200

    status, _ = _pilot_signed(env, TX[2:], buyer, payer)
    assert status == 409
    assert len(_orders(env)) == 1

    # The database refuses the bare alias on its own, too.
    with pytest.raises(sqlite3.IntegrityError):
        env.store.conn.execute(
            """INSERT INTO orders (id, customer_id, customer_email, payment_id, product_id,
               amount, currency, tx_hash, status, license_key, created_at)
               SELECT 'o2', customer_id, customer_email, 'p2', product_id, amount, currency,
               substr(tx_hash, 3), status, 'l2', created_at FROM orders LIMIT 1""")
    env.store.conn.rollback()


# ── [high] checkout never consulted the channel / invoke registries ──────────

def _open_channel(env, buyer: dict, tx: str, payer) -> dict:
    ch = env.channels
    sig = payer.sign_message(encode_defunct(text=ch.deposit_proof_challenge(
        chain="base", tx_hash=tx, payer=payer.address, deposit_usd=5.0))).signature.hex()
    return ch.open_channel(deposit_usd=5.0, tx_hash=tx, customer_id=buyer["sub"],
                           customer_email=buyer["email"], signature=sig)


def test_channel_deposit_then_checkout_same_transfer_is_refused(env):
    payer = Account.create()
    buyer = env.customer("buyer@example.test")
    env.pay(TX, payer.address)

    opened = _open_channel(env, buyer, TX, payer)
    assert "error" not in opened, opened
    assert opened["channel"]["balance_usd"] == 5.0

    status, _, quote = _checkout(env, buyer, TX, signer=payer)
    assert status == 409
    assert _orders(env) == []
    assert env.payment._pending_payments[quote["payment_id"]]["status"] == "pending"


def test_invoke_payment_then_checkout_same_transfer_is_refused(env):
    payer = Account.create()
    buyer = env.customer("buyer@example.test")
    env.pay(TX, payer.address)

    claimed = env.channels.claim_payment_tx(tx_hash=TX, chain="base", token="USDT",
                                            amount_usd=5.0, purpose="invoke:p/c",
                                            sender=payer.address, claimant=payer.address)
    assert claimed["ok"] is True

    status, _, _ = _checkout(env, buyer, TX, signer=payer)
    assert status == 409
    assert _orders(env) == []


def test_checkout_then_channel_or_invoke_same_transfer_is_refused(env):
    payer = Account.create()
    buyer = env.customer("buyer@example.test")
    env.pay(TX, payer.address)
    status, _, _ = _checkout(env, buyer, TX.upper().replace("0X", "0x"), signer=payer)
    assert status == 200

    assert _open_channel(env, buyer, TX, payer).get("error") == "tx_hash_already_used"
    assert env.channels.claim_payment_tx(tx_hash=TX[2:], chain="base", token="USDT",
                                         amount_usd=5.0, purpose="invoke:p/c")["ok"] is False


def test_checkout_retry_after_a_crash_between_claim_and_order_is_not_locked_out(env):
    from web.backend.services.ai_market_protocol.on_chain import claim_deposit
    from web.backend.services.payment_claim import DOOR_CHECKOUT

    payer = Account.create()
    buyer = env.customer("buyer@example.test")
    env.pay(TX, payer.address)
    quote_id = "pay-crashed01"
    # The previous attempt claimed the transfer and died before writing the order.
    assert claim_deposit(chain="base", tx_hash=TX, stack=DOOR_CHECKOUT, claim_id=quote_id)["ok"]

    from web.backend.schemas.api_requests import ConfirmPaymentRequest
    from web.backend.services.payment_claim import claim_message
    quote = _quote(env, buyer, payment_id=quote_id)
    sig = payer.sign_message(encode_defunct(text=claim_message(quote, TX))).signature.hex()
    status, out = _call(env.payment.confirm_payment(
        quote_id, ConfirmPaymentRequest(tx_hash=TX, payer_signature=sig),
        customer={"sub": buyer["sub"]}, test_confirmations=None))
    assert status == 200 and out["status"] == "confirmed", out

    # Another checkout still cannot reuse the transfer.
    status, _, _ = _checkout(env, buyer, TX, signer=payer)
    assert status == 409


# ── [medium] invoke registry was case-sensitive ─────────────────────────────

def test_invoke_claim_case_aliases_are_one_transfer(env):
    body = "ab" * 16 + "AB" * 16
    aliases = ["0x" + body.lower(), "0x" + body.upper(), "0x" + body, body]
    results = [env.channels.claim_payment_tx(tx_hash=t, chain="base", token="USDT",
                                             amount_usd=0.4, purpose="invoke:p/c")["ok"]
               for t in aliases]
    assert results == [True, False, False, False]
    # Lookups and the refund-obligation marker find the claim under any spelling.
    assert env.channels.payment_tx_claim(aliases[1]) is not None
    assert env.channels.mark_payment_tx_unfulfilled(tx_hash=aliases[2], reason="x")["ok"]


# ── [medium] the canonical unique index crashed startup on old duplicates ────

_OLD_ORDERS_DDL = """CREATE TABLE orders (id TEXT PRIMARY KEY, customer_id TEXT NOT NULL,
    customer_email TEXT NOT NULL, payment_id TEXT NOT NULL UNIQUE, product_id TEXT NOT NULL,
    amount REAL NOT NULL, currency TEXT NOT NULL, tx_hash TEXT NOT NULL, referral_source TEXT,
    status TEXT NOT NULL, license_key TEXT NOT NULL, created_at REAL NOT NULL)"""


def test_existing_alias_orders_do_not_stop_startup(tmp_path, monkeypatch, caplog):
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path / "data"))
    from web.backend.services.commerce import CommerceService, TxHashAlreadyUsedError

    store = tmp_path / "store"
    store.mkdir()
    db = sqlite3.connect(store / "commerce.db")
    db.execute(_OLD_ORDERS_DDL)
    db.execute("CREATE UNIQUE INDEX idx_orders_tx_hash_unique ON orders(tx_hash)")
    for n, tx in enumerate(["0x" + "ab" * 32, "0x" + "AB" * 32, "0x" + "cd" * 32, "cd" * 32]):
        db.execute("INSERT INTO orders VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                   (f"o{n}", "c", "c@x", f"p{n}", PRODUCT, 5, "USDC", tx, None, "paid", f"l{n}", n))
    db.commit()
    db.close()

    caplog.set_level("ERROR")
    svc = CommerceService(base_dir=str(store))  # used to raise sqlite3.IntegrityError

    dups = {d["tx_hash"]: sorted(d["payment_ids"]) for d in svc.duplicate_tx_orders()}
    assert dups == {"0x" + "ab" * 32: ["p0", "p1"], "0x" + "cd" * 32: ["p2", "p3"]}
    assert "more than one order" in caplog.text
    # With the index missing, new aliases are still refused by the canonical lookup.
    with pytest.raises(TxHashAlreadyUsedError):
        svc.create_order_and_license(customer_id="c", customer_email="c@x", payment_id="p9",
                                     product_id=PRODUCT, amount=5, currency="USDC",
                                     tx_hash="Ab" * 32)


def test_clean_database_gets_the_canonical_index(tmp_path, monkeypatch):
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path / "data"))
    from web.backend.services.commerce import CommerceService

    svc = CommerceService(base_dir=str(tmp_path / "store"))
    names = {r[0] for r in svc.conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    assert "idx_orders_canonical_tx_v2" in names
    assert svc.duplicate_tx_orders() == []


# ── [medium] contract-wallet payers could never claim ───────────────────────

_MAGIC = bytes.fromhex("1626ba7e") + b"\0" * 28
_ERC6492_SUFFIX = bytes.fromhex("6492" * 16)


class _SmartWalletNode(BaseProvider):
    """A node that knows one ERC-1271 wallet, controlled by ``owner``."""

    def __init__(self, wallet: str, owner: str, permissive: bool = False):
        super().__init__()
        self.wallet, self.owner, self.permissive = wallet.lower(), owner.lower(), permissive
        self.calls: list[str] = []

    def make_request(self, method, params):
        self.calls.append(method)
        if method == "eth_chainId":
            return {"jsonrpc": "2.0", "id": 1, "result": "0x2105"}
        if method == "eth_getCode":
            code = "0x6001" if params[0].lower() == self.wallet else "0x"
            return {"jsonrpc": "2.0", "id": 1, "result": code}
        if method == "eth_call" and params[0]["to"].lower() == self.wallet:
            data = bytes.fromhex(params[0]["data"][2:])
            if data[:4] == _MAGIC[:4]:
                digest, sig = abi_decode(["bytes32", "bytes"], data[4:])
                if self.permissive:
                    return {"jsonrpc": "2.0", "id": 1, "result": "0x" + _MAGIC.hex()}
                try:
                    _index, inner = abi_decode(["uint256", "bytes"], sig)
                    signer = Account._recover_hash(digest, signature=inner)
                except Exception:
                    signer = ""
                if signer.lower() == self.owner:
                    return {"jsonrpc": "2.0", "id": 1, "result": "0x" + _MAGIC.hex()}
        return {"jsonrpc": "2.0", "id": 1,
                "error": {"code": 3, "message": "execution reverted", "data": "0x"}}


def _smart_wallet_signature(owner, message: str) -> str:
    """What a Coinbase-style smart wallet returns before its first deployment."""
    inner = owner.sign_message(encode_defunct(text=message)).signature
    wrapped = abi_encode(["uint256", "bytes"], [0, bytes(inner)])
    factory_call = b"\x5f" * 196
    blob = abi_encode(["address", "bytes", "bytes"], ["0x" + "fa" * 20, factory_call, wrapped])
    return "0x" + (blob + _ERC6492_SUFFIX).hex()


@pytest.mark.parametrize("permissive,expected", [(False, 200), (True, 403)])
def test_contract_wallet_payer_can_claim_via_erc1271(env, monkeypatch, permissive, expected):
    from web.backend.schemas.api_requests import ConfirmPaymentRequest
    from web.backend.services.payment_claim import claim_message

    owner, wallet = Account.create(), "0x" + "5c" * 20
    buyer = env.customer("buyer@example.test")
    env.pay(TX, wallet)
    node = _SmartWalletNode(wallet, owner.address, permissive=permissive)
    monkeypatch.setattr(env.payment, "_pool_for_chain", lambda c: SimpleNamespace(run=lambda f: f("http://node")))
    monkeypatch.setattr(env.payment.Web3, "HTTPProvider", lambda url, **kw: node)

    quote = _quote(env, buyer)
    signature = _smart_wallet_signature(owner, claim_message(quote, TX))
    assert len(signature) > 512  # the old field cap refused it before verification
    status, out = _call(env.payment.confirm_payment(
        quote["payment_id"], ConfirmPaymentRequest(tx_hash=TX, payer_signature=signature),
        customer={"sub": buyer["sub"]}, test_confirmations=None))
    assert status == expected, out
    assert "eth_call" in node.calls
    assert len(_orders(env)) == (1 if expected == 200 else 0)


def test_unsignable_payment_is_held_for_operator_review(env):
    from web.backend.schemas.api_requests import ConfirmPaymentRequest

    payer = Account.create()
    buyer = env.customer("buyer@example.test")
    env.pay(TX, payer.address)

    # The buyer paid from somewhere that cannot sign messages (an exchange withdrawal).
    status, detail, quote = _checkout(env, buyer, TX, signer=Account.create())
    assert status == 403
    assert detail["payer"].lower() == payer.address.lower()
    assert quote["payment_id"] in detail["recovery"]
    pid = quote["payment_id"]
    review = env.payment._pending_payments[pid]["claim_review"]
    assert review["tx_hash"] == TX and review["payer"].lower() == payer.address.lower()

    # An expired quote under review survives a restart instead of being dropped.
    env.payment._pending_payments[pid]["expires_at"] = time.time() - 1
    env.payment._persist_pending_payments()
    env.payment._load_pending_payments_from_disk()
    assert pid in env.payment._pending_payments

    with pytest.raises(HTTPException) as exc:
        env.payment._require_payment_admin({"role": "viewer", "sub": "v"})
    assert exc.value.status_code == 403
    admin = env.payment._require_payment_admin({"role": "admin", "sub": "ops-1"})
    listed = asyncio.run(env.payment.list_claim_reviews(admin=admin))
    assert [c["payment_id"] for c in listed["claims"]] == [pid]

    status, out = _call(env.payment.approve_claim_review(
        pid, ConfirmPaymentRequest(tx_hash=TX), admin=admin))
    assert status == 200 and out["status"] == "confirmed", out
    assert [o[1:] for o in _orders(env)] == [(buyer["sub"], TX)]


def test_operator_cannot_release_a_transfer_spent_elsewhere(env):
    from web.backend.schemas.api_requests import ConfirmPaymentRequest

    payer = Account.create()
    buyer = env.customer("buyer@example.test")
    env.pay(TX, payer.address)
    status, _, quote = _checkout(env, buyer, TX, signature="")
    assert status == 400
    assert env.payment._pending_payments[quote["payment_id"]]["claim_review"]["tx_hash"] == TX
    assert env.channels.claim_payment_tx(tx_hash=TX, chain="base", token="USDT",
                                         amount_usd=5.0, purpose="invoke:p/c")["ok"]

    admin = env.payment._require_payment_admin({"role": "admin", "sub": "ops-1"})
    status, _ = _call(env.payment.approve_claim_review(
        quote["payment_id"], ConfirmPaymentRequest(tx_hash=TX), admin=admin))
    assert status == 409
    assert _orders(env) == []


# ── [low] the signed message did not say which site it belongs to ────────────

def test_claim_message_names_the_site_and_is_bound_to_it(env, monkeypatch):
    from web.backend.services.payment_claim import claim_message, verify_claim

    payer = Account.create()
    quote = dict(payment_id="pay-1", customer_id="buyer-1", product_id=PRODUCT, chain="base",
                 currency="USDC", amount=5.0, wallet_address=PLATFORM)
    message = claim_message(quote, TX)
    assert message.startswith(SITE)
    assert f"Sign only on {SITE}" in message and TX in message and "pay-1" in message
    signature = payer.sign_message(encode_defunct(text=message)).signature.hex()
    assert verify_claim(quote, TX, signature, payer.address)

    monkeypatch.setenv("NEXT_PUBLIC_SITE_URL", "https://other-deployment.example.test")
    assert not verify_claim(quote, TX, signature, payer.address)
    # A quote pins the site it was issued on, so a config change mid-checkout is harmless.
    assert verify_claim({**quote, "site": SITE}, TX, signature, payer.address)


# ── the shared sqlite connection: order + license commit as one unit ────────

def test_order_and_license_survive_a_rollback_from_another_thread(tmp_path, monkeypatch):
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path / "data"))
    from web.backend.services.commerce import CommerceService

    svc = CommerceService(base_dir=str(tmp_path / "store"))
    conn = svc.conn
    real_execute = conn.execute
    between, other_done = threading.Event(), threading.Event()

    def execute(sql, *args, **kwargs):
        if "INSERT INTO licenses" in sql and threading.current_thread().name == "buyer":
            between.set()
            other_done.wait(0.5)  # give the other request its chance to interleave
        return real_execute(sql, *args, **kwargs)

    monkeypatch.setattr(conn, "execute", execute)

    def buyer():
        svc.create_order_and_license(customer_id="c", customer_email="c@x", payment_id="p1",
                                     product_id=PRODUCT, amount=5, currency="USDC", tx_hash=TX)

    def other_request():
        between.wait(2)
        conn.rollback()  # e.g. another request's failed write on the same connection
        other_done.set()

    threads = [threading.Thread(target=buyer, name="buyer"), threading.Thread(target=other_request)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(5)
    counts = [svc.conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in ("orders", "licenses")]
    assert counts == [1, 1]
