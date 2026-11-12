"""Scratch reproductions for the deposits / x402 zone audit. Read-only on the repo."""
from __future__ import annotations

import os
import sys

HUB_DIR = "/Users/alex/Desktop/ai_tests/aicompany/aicom/.claude/worktrees/bold-volhard-8c154f/aimarket-hub"
sys.path.insert(0, HUB_DIR)

import pytest  # noqa: E402

from aimarket_hub import channels, chain_net, credits, deposit_watch, settle, topup  # noqa: E402
from aimarket_hub.database import HubDatabase  # noqa: E402

USDC = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"
WALLET = "0x" + "d7" * 20
SHARED = "0x" + "a1" * 20
VICTIM = "0x" + "e8" * 20
ATTACKER = "0x" + "bb" * 20


def tx(n: int) -> str:
    return "0x" + f"{n:064x}"


def topic(addr: str) -> str:
    return "0x" + addr[2:].lower().rjust(64, "0")


class Chain:
    """A fake Base node: receipts with status/blockNumber, getLogs with an optional lag."""

    def __init__(self):
        self.head = 1000
        self.receipts: dict[str, dict] = {}
        self.logs: list[dict] = []
        self.logs_node_head: int | None = None   # simulate a lagging node serving eth_getLogs

    def add(self, tx_hash, block, logs):
        for lg in logs:
            lg.setdefault("transactionHash", tx_hash)
            lg.setdefault("blockNumber", hex(block))
        self.receipts[tx_hash] = {"status": "0x1", "blockNumber": hex(block), "transactionHash": tx_hash,
                                  "logs": logs}
        self.logs.extend(logs)

    def pay_auth(self, tx_hash, block, payer, nonce, units, to=WALLET):
        self.add(tx_hash, block, [
            {"address": USDC, "topics": [settle.AUTHORIZATION_USED_TOPIC, topic(payer), nonce], "data": "0x"},
            {"address": USDC, "topics": [settle.TRANSFER_TOPIC, topic(payer), topic(to)], "data": hex(units)},
        ])

    def plain(self, tx_hash, block, payer, units, to=WALLET):
        self.add(tx_hash, block, [
            {"address": USDC, "topics": [settle.TRANSFER_TOPIC, topic(payer), topic(to)], "data": hex(units)},
        ])

    def __call__(self, method, params):
        if method == "eth_chainId":
            return hex(8453)
        if method == "eth_blockNumber":
            return hex(self.head)
        if method == "eth_getTransactionReceipt":
            return self.receipts.get(params[0])
        if method == "eth_getLogs":
            f = params[0]
            lo, hi = int(f["fromBlock"], 16), int(f["toBlock"], 16)
            if self.logs_node_head is not None:
                hi = min(hi, self.logs_node_head)   # geth-style: a lagging node returns what it has
            return [lg for lg in self.logs
                    if lo <= int(lg["blockNumber"], 16) <= hi and len(lg["topics"]) >= 3
                    and lg["topics"][0] == settle.TRANSFER_TOPIC and lg["topics"][2] == f["topics"][2]]
        if method == "eth_getBlockByNumber":
            return {"timestamp": hex(2_000_000_000), "number": params[0]}
        raise AssertionError(method)


@pytest.fixture
def env(monkeypatch, tmp_path):
    monkeypatch.setenv("AIMARKET_DEPOSIT_CLAIMS_DIR", str(tmp_path / "claims"))
    monkeypatch.setenv("AIMARKET_CREDITS_ENABLED", "1")
    monkeypatch.setenv("AIMARKET_TOPUP_ENABLED", "1")
    monkeypatch.setenv("AIMARKET_X402_PAY_TO", SHARED)
    monkeypatch.setenv("AIMARKET_TOPUP_PAY_TO", WALLET)
    monkeypatch.setenv("AIMARKET_X402_CHAIN", "base")
    monkeypatch.setenv("AIMARKET_SETTLE_RPC_URL", "http://rpc.test")
    monkeypatch.setenv("AIMARKET_TOPUP_VERIFY_DECIMALS", "0")
    monkeypatch.setenv("AIMARKET_TOPUP_MIN_CONFIRMATIONS", "2")
    topup._VERIFY_LOG.clear()
    chain_net.reset_pools()
    chain = Chain()
    monkeypatch.setattr(settle, "_rpc", lambda url, method, params, timeout: chain(method, params))
    db = HubDatabase(tmp_path / "hub.db")
    return chain, db


def _watcher(db, chain):
    return deposit_watch.Watcher(
        store=deposit_watch.DepositStore(db._conn), ledger=credits.CreditsLedger(db._conn),
        topups=topup.TopupStore(db._conn), payments=settle.PaymentStore(db._conn),
        claim_deposit=lambda *, stack, **kw: channels.claim_deposit_as(stack, **kw),
        release_deposit=lambda *, stack, **kw: channels.release_deposit_as(stack, **kw),
        claim_holder=lambda **kw: channels.deposit_claim_holder(**kw), rpc=chain)


def _claim(*, stack, **kw):
    return channels.claim_deposit_as(stack, **kw)


def test_dust_authorization_over_victims_nonce_strands_the_real_payment(env):
    chain, db = env
    ledger = credits.CreditsLedger(db._conn)
    victim = ledger.create_account(label="victim", grant_usd=0)["account_id"]
    store = topup.TopupStore(db._conn)
    payments = settle.PaymentStore(db._conn)
    q, _body, _v2 = topup.quote(store=store, account_id=victim, amount_usd=100, hub_url="https://hub.test")
    # Victim pays 100 USDC over its nonce (block 990). Attacker reads the nonce off the mined
    # AuthorizationUsed log and pays 10 base units ($0.00001) over the SAME nonce from its own
    # wallet (EIP-3009 nonces are per authorizer), then presents its own tx first.
    chain.pay_auth(tx(1), 990, VICTIM, q.nonce, 100_000_000)
    chain.pay_auth(tx(2), 992, ATTACKER, q.nonce, 10)
    chain.head = 1000
    got = topup.redeem(store=store, ledger=ledger, payments=payments, nonce=q.nonce, tx_hash=tx(2),
                       claim_deposit=_claim, limit_key="ip:attacker")
    assert got["success"] and got["credited_usd"] == pytest.approx(0.00001)
    with pytest.raises(topup.TopupError) as refused:
        topup.redeem(store=store, ledger=ledger, payments=payments, nonce=q.nonce, tx_hash=tx(1),
                     claim_deposit=_claim, owner_account=victim)
    assert refused.value.error == "topup_already_credited"
    # The watcher sees the victim's 100 USDC: refused quote -> unattributed, never auto-credited,
    # not even after the victim links the paying wallet.
    w = _watcher(db, chain)
    w.scan_once()
    row = deposit_watch.DepositStore(db._conn).deposit(tx(1))
    assert row["status"] == deposit_watch.UNATTRIBUTED and deposit_watch.QUOTE_REFUSED in row["detail"]
    deposit_watch.DepositStore(db._conn).link(VICTIM, victim, "operator")
    w.credit_linked(VICTIM)
    assert deposit_watch.DepositStore(db._conn).deposit(tx(1))["status"] == deposit_watch.UNATTRIBUTED
    assert ledger.balance(victim) == pytest.approx(0.00001)   # paid $100, credited $0.00001


def test_lagging_logs_node_skips_a_linked_deposit_forever(env):
    chain, db = env
    ledger = credits.CreditsLedger(db._conn)
    acct = ledger.create_account(label="payer", grant_usd=0)["account_id"]
    store = deposit_watch.DepositStore(db._conn)
    store.link(VICTIM, acct, "operator")
    w = _watcher(db, chain)
    # First scan, nothing yet: cursor at safe+1.
    chain.head = 950
    w.scan_once()
    # A deposit at block 980. eth_blockNumber answers 1000 (node A); eth_getLogs is served by a
    # node 26 blocks behind (head 974): it returns what it has, nothing for 975..999.
    chain.plain(tx(7), 980, VICTIM, 5_000_000)
    chain.head = 1000
    chain.logs_node_head = 974
    s1 = w.scan_once()
    assert s1["next_block"] == 1000
    # The lagging node catches up; every later scan re-reads only 12 blocks behind the cursor.
    chain.logs_node_head = None
    for head in (1030, 1060, 1090):
        chain.head = head
        w.scan_once()
    assert store.deposit(tx(7)) is None          # never recorded, not even as unattributed
    assert ledger.balance(acct) == 0.0           # 5 USDC arrived, nothing credited


def test_fee_on_market_rail_402_names_seller_but_verifier_demands_splitter(monkeypatch, env):
    chain, db = env
    from aimarket_hub import x402
    from types import SimpleNamespace

    seller = "0x" + "5e" * 20
    splitter = "0x" + "99" * 20
    monkeypatch.setenv("AIMARKET_MARKET_FEE_BPS", "100")
    monkeypatch.setenv("AIMARKET_MARKET_FEE_TO", "0x" + "fe" * 20)
    monkeypatch.setenv("AIMARKET_MARKET_SPLITTER", splitter)
    cap = SimpleNamespace(price_per_call_usd=1.0, payout_address=seller, publisher_id="", capability_id="c@v1")
    # What the invoke 402 offers (middleware -> x402.payment_required_v2(pay_to=_bind_listing_payee)).
    offered = x402.payment_required_v2(1.0, "https://hub.test/ai-market/v2/invoke", pay_to=settle.seller_pay_to(
        cap, operator_pay_to=x402.recipient()))
    assert offered["accepts"][0]["payTo"].lower() == seller
    terms = settle.terms_for(cap, operator_pay_to=x402.recipient())
    assert terms.offer_to.lower() == splitter and terms.fee_units == 10_000
    nonce = "0x" + "11" * 32
    # Buyer pays exactly what the 402 says: 1 USDC to the seller under the invoice nonce.
    chain.pay_auth(tx(9), 990, VICTIM, nonce, 1_000_000, to=seller)
    with pytest.raises(settle.PaymentFinal):
        settle.verify_transfer(tx_hash=tx(9), terms=terms, require_nonce=nonce)


def test_transient_jsonrpc_error_strands_quote_payment_as_refused(monkeypatch, env):
    chain, db = env
    ledger = credits.CreditsLedger(db._conn)
    acct = ledger.create_account(label="buyer", grant_usd=0)["account_id"]
    store = topup.TopupStore(db._conn)
    q, _b, _v = topup.quote(store=store, account_id=acct, amount_usd=20, hub_url="https://hub.test")
    w = _watcher(db, chain)
    chain.head = 950
    w.scan_once()                                     # cursor at 950
    chain.pay_auth(tx(21), 960, VICTIM, q.nonce, 20_000_000)
    chain.head = 1000
    # The settlement node answers the receipt, then a JSON-RPC error body (HTTP 200) for
    # eth_blockNumber - e.g. a provider's rate-limit reply. settle._rpc raises PaymentError.
    state = {"fail": True}

    def flaky(url, method, params, timeout):
        if method == "eth_blockNumber" and state["fail"]:
            state["fail"] = False
            raise settle.PaymentError("chain rpc refused eth_blockNumber: {'code': -32005, 'message': 'rate limit'}")
        return chain(method, params)

    monkeypatch.setattr(settle, "_rpc", flaky)
    w.scan_once()
    deps = deposit_watch.DepositStore(db._conn)
    row = deps.deposit(tx(21))
    assert row["status"] == deposit_watch.UNATTRIBUTED and deposit_watch.QUOTE_REFUSED in row["detail"]
    # The node is healthy again; later scans never retry the redemption.
    for head in (1030, 1060, 1090):
        chain.head = head
        w.scan_once()
    assert deps.deposit(tx(21))["status"] == deposit_watch.UNATTRIBUTED
    assert store.get(q.nonce).status == topup.QUOTED
    assert ledger.balance(acct) == 0.0                # 20 USDC paid, nothing credited
