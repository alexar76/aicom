"""USDC landing in the top-up wallet is credited without anybody presenting it (deposit_watch.py).

2026-10-04: the first company-to-company payment (Independent AI prepaying its account at Attested
Memory) was a plain transfer from a wallet app. Nothing could match it to an account, so the operator
credited it by hand — after somebody noticed it on chain. These tests pin the replacement: the hub
watches its own top-up wallet. No test here reaches a real chain: a fake RPC serves the logs.
"""
from __future__ import annotations

import time

import pytest
from eth_account import Account
from eth_account.messages import encode_defunct

from aimarket_hub import channels, credits, deposit_watch, settle, topup
from tests._mandate_kit import ADMIN_TOKEN, HUB, balance, funded_account, hub
from tests.test_topup import USDC_BASE, Chain

WALLET = "0x" + "d7" * 20          # receives top-ups and nothing else
SHARED = "0x" + "a1" * 20          # the hub's x402 wallet
SENDER = "0x" + "e8" * 20
ADMIN = {"Authorization": f"Bearer {ADMIN_TOKEN}"}


def tx(n: int) -> str:
    return "0x" + f"{n:064x}"


def _topic(address: str) -> str:
    return "0x" + address[2:].lower().rjust(64, "0")


class FakeChain:
    """eth_blockNumber / eth_getLogs / eth_getTransactionReceipt over a list of transfers."""

    def __init__(self):
        self.head = 1000
        self.logs: list[dict] = []
        self.receipts: dict[str, dict] = {}
        self.fail_logs = False

    def transfer(self, tx_hash: str, sender: str, units: int, auth_nonce: str = ""):
        # A new transfer is in a new block: the hub's own watcher already read up to the head
        # when the app started (and then sleeps for the interval).
        self.head += 1
        block = self.head
        log = {"address": USDC_BASE.lower(), "transactionHash": tx_hash, "blockNumber": hex(block),
               "topics": [deposit_watch.TRANSFER_TOPIC, _topic(sender), _topic(WALLET)], "data": hex(units)}
        self.logs.append(log)
        logs = [log]
        if auth_nonce:
            logs.insert(0, {"address": USDC_BASE.lower(),
                            "topics": [deposit_watch.AUTHORIZATION_USED_TOPIC, _topic(sender), auth_nonce]})
        self.receipts[tx_hash] = {"logs": logs}

    def __call__(self, method: str, params: list):
        if method == "eth_chainId":
            return hex(8453)
        if method == "eth_blockNumber":
            return hex(self.head)
        if method == "eth_getLogs":
            if self.fail_logs:
                raise deposit_watch.Retry("node down")
            f = params[0]
            lo, hi = int(f["fromBlock"], 16), int(f["toBlock"], 16)
            return [log for log in self.logs if lo <= int(log["blockNumber"], 16) <= hi
                    and log["topics"][2] == f["topics"][2]]
        if method == "eth_getTransactionReceipt":
            return self.receipts.get(params[0])
        raise AssertionError(method)


@pytest.fixture
def on(monkeypatch):
    monkeypatch.setenv("AIMARKET_CREDITS_ENABLED", "1")
    monkeypatch.setenv("AIMARKET_TOPUP_ENABLED", "1")
    monkeypatch.setenv("AIMARKET_X402_PAY_TO", SHARED)
    monkeypatch.setenv("AIMARKET_TOPUP_PAY_TO", WALLET)
    monkeypatch.setenv("AIMARKET_X402_CHAIN", "base")
    monkeypatch.setenv("AIMARKET_SETTLE_RPC_URL", "http://rpc.test")
    monkeypatch.setenv("AIMARKET_TOPUP_VERIFY_DECIMALS", "0")
    monkeypatch.setenv("AIMARKET_TOPUP_MIN_CONFIRMATIONS", "1")
    topup._VERIFY_LOG.clear()
    topup._DECIMALS_READ.clear()
    fake = FakeChain()
    monkeypatch.setattr(settle, "_rpc", lambda url, method, params, timeout: fake(method, params))
    return fake


def watcher(db, fake):
    return deposit_watch.Watcher(
        store=deposit_watch.DepositStore(db._conn), ledger=credits.CreditsLedger(db._conn),
        topups=topup.TopupStore(db._conn), payments=settle.PaymentStore(db._conn),
        claim_deposit=lambda *, stack, **kw: channels.claim_deposit_as(stack, **kw),
        release_deposit=lambda *, stack, **kw: channels.release_deposit_as(stack, **kw),
        claim_holder=lambda **kw: channels.deposit_claim_holder(**kw), rpc=fake)


def _well_known_watch(client) -> dict:
    return client.get("/.well-known/ai-market.json").json()["payment_rails"]["credits"]["topup"]["deposit_watch"]


def test_the_shared_x402_wallet_is_never_watched(monkeypatch, tmp_path, on):
    monkeypatch.delenv("AIMARKET_TOPUP_PAY_TO")
    assert not deposit_watch.enabled()
    assert "AIMARKET_TOPUP_PAY_TO" in deposit_watch.unavailable_reason()
    with hub(monkeypatch, tmp_path) as (client, db):
        block = _well_known_watch(client)
    assert block["enabled"] is False and "AIMARKET_TOPUP_PAY_TO" in block["reason"]
    monkeypatch.setenv("AIMARKET_TOPUP_PAY_TO", SHARED.upper().replace("0X", "0x"))   # named, but the same wallet
    assert not deposit_watch.enabled() and "AIMARKET_X402_PAY_TO" in deposit_watch.unavailable_reason()


def test_a_plain_transfer_from_a_linked_wallet_is_credited_once(monkeypatch, tmp_path, on):
    with hub(monkeypatch, tmp_path) as (client, db):
        account, _ = funded_account(client, db, 0.0)
        assert client.post(f"/ai-market/v2/accounts/{account}/payer-wallets", json={"address": SENDER},
                           headers=ADMIN).status_code == 200
        on.transfer(tx(1), SENDER, 1_015_400)
        w = watcher(db, on)
        summary = w.scan_once()
        assert summary["credited"] == 1
        assert balance(db, account) == pytest.approx(1.0154)
        w.scan_once()
        assert balance(db, account) == pytest.approx(1.0154)            # no second credit
        again = client.post(f"/ai-market/v2/accounts/{account}/credit", headers=ADMIN,
                            json={"amount_usd": 1.0154, "tx_hash": tx(1)})
        assert again.status_code == 409                                  # nor by hand


def test_money_from_an_unknown_wallet_waits_and_is_credited_when_linked(monkeypatch, tmp_path, on):
    with hub(monkeypatch, tmp_path) as (client, db):
        account, _ = funded_account(client, db, 0.0)
        on.transfer(tx(2), SENDER, 2_000_000)
        assert watcher(db, on).scan_once()["unattributed"] == 1
        assert _well_known_watch(client)["unattributed_deposits"] == 1
        listed = client.get("/ai-market/v2/admin/deposits", headers=ADMIN).json()["unattributed"]
        assert [(d["tx_hash"], d["sender"], d["amount_units"]) for d in listed] == [(tx(2), SENDER, 2_000_000)]
        assert balance(db, account) == 0.0
        linked = client.post(f"/ai-market/v2/accounts/{account}/payer-wallets", json={"address": SENDER},
                             headers=ADMIN).json()
        assert linked["credited_now"] == 1
        assert balance(db, account) == pytest.approx(2.0)
        assert _well_known_watch(client)["unattributed_deposits"] == 0


def test_a_wallet_links_itself_with_a_signature(monkeypatch, tmp_path, on):
    wallet = Account.create()
    address = wallet.address.lower()
    with hub(monkeypatch, tmp_path) as (client, db):
        account, key = funded_account(client, db, 0.0)
        _, other_key = funded_account(client, db, 0.0)
        now = int(time.time())

        def sign(acct_id, signer=wallet, issued=now):
            msg = deposit_watch.link_message(hub_url=HUB, account_id=acct_id, address=address, issued_at=issued)
            return "0x" + signer.sign_message(encode_defunct(text=msg)).signature.hex().removeprefix("0x")

        def link(api_key, signature, issued=now):
            return client.post("/ai-market/v2/account/payer-wallets", headers={"X-API-Key": api_key},
                               json={"address": address, "issued_at": issued, "signature": signature})

        assert link(key, sign(account, signer=Account.create())).status_code == 403   # not this wallet
        assert link(key, sign(account, issued=now - 3600), issued=now - 3600).status_code == 400
        assert link(key, sign(account)).json()["linked"] == "linked"
        listed = client.get("/ai-market/v2/account/payer-wallets", headers={"X-API-Key": key}).json()
        assert [w["address"] for w in listed["wallets"]] == [address]
        other = client.get("/ai-market/v2/account", headers={"X-API-Key": other_key}).json()["account_id"]
        assert link(other_key, sign(other)).status_code == 409                       # one wallet, one account


def test_a_paid_quote_is_redeemed_without_anyone_presenting_it(monkeypatch, tmp_path, on):
    chain = Chain()
    with hub(monkeypatch, tmp_path) as (client, db):
        account, key = funded_account(client, db, 0.0)
        offer = client.post("/ai-market/v2/account/topup", headers={"X-API-Key": key}, json={"amount_usd": 5})
        assert offer.status_code == 402 and offer.json()["pay_to"].lower() == WALLET
        nonce = offer.json()["nonce"]
        chain.pays(tx(3), nonce, 5_000_000, payer=SENDER)

        def verify(*, tx_hash, terms, require_nonce, **_):
            return chain.verify(tx_hash=tx_hash, terms=type("T", (), {**terms.__dict__, "pay_to": "0x" + "a1" * 20,
                                                                        "amount_units": terms.amount_units,
                                                                        "token_contract": USDC_BASE.lower()})(),
                                require_nonce=require_nonce)
        monkeypatch.setattr(settle, "verify_transfer", verify)
        on.transfer(tx(3), SENDER, 5_000_000, auth_nonce=nonce)
        assert watcher(db, on).scan_once()["credited"] == 1
        assert balance(db, account) == pytest.approx(5.0)
        assert client.get(f"/ai-market/v2/topups/{nonce}").json()["status"] == "credited"


def test_a_transfer_the_operator_already_credited_is_not_credited_again(monkeypatch, tmp_path, on):
    with hub(monkeypatch, tmp_path) as (client, db):
        account, _ = funded_account(client, db, 0.0)
        assert client.post(f"/ai-market/v2/accounts/{account}/credit", headers=ADMIN,
                           json={"amount_usd": 1.0, "tx_hash": tx(4)}).status_code == 200
        client.post(f"/ai-market/v2/accounts/{account}/payer-wallets", json={"address": SENDER}, headers=ADMIN)
        on.transfer(tx(4), SENDER, 1_000_000)
        assert watcher(db, on).scan_once().get(deposit_watch.ELSEWHERE) == 1
        assert balance(db, account) == pytest.approx(1.0)


def test_a_node_failure_leaves_the_blocks_to_read_again(monkeypatch, tmp_path, on):
    with hub(monkeypatch, tmp_path) as (client, db):
        w = watcher(db, on)
        w.scan_once()
        key = f"base:{WALLET}"
        before = w.store.cursor(key)
        on.head += 50
        on.fail_logs = True
        with pytest.raises(deposit_watch.Retry):
            w.scan_once()
        assert w.store.cursor(key) == before


def test_the_link_command_fills_the_hubs_own_message(monkeypatch, tmp_path, on, capsys):
    """scripts/credits_topup_pay.py link: what a person runs. The message comes from the well-known
    template, so it must be exactly what the hub verifies — a drift would answer 403 for everyone."""
    import importlib.util
    import pathlib

    path = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "credits_topup_pay.py"
    if not path.is_file():
        pytest.skip("scripts/credits_topup_pay.py is not in this checkout")
    spec = importlib.util.spec_from_file_location("credits_topup_pay", path)
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    wallet = Account.create()
    with hub(monkeypatch, tmp_path) as (client, db):
        account, key = funded_account(client, db, 0.0)
        on.transfer(tx(5), wallet.address, 3_000_000)
        watcher(db, on).scan_once()

        def http(method, url, body=None, headers=None):
            r = client.request(method, url.removeprefix(HUB), json=body, headers=headers or {})
            return r.status_code, r.json()
        monkeypatch.setattr(script, "http", http)
        (tmp_path / "account.key").write_text(key)
        monkeypatch.setenv("TEST_WALLET_KEY", wallet.key.hex())
        assert script.main(["link", "--hub", HUB, "--api-key-file", str(tmp_path / "account.key"),
                            "--wallet-key-env", "TEST_WALLET_KEY"]) == 0
        assert balance(db, account) == pytest.approx(3.0)
    out = capsys.readouterr().out
    assert "credited now 1" in out and wallet.key.hex().removeprefix("0x") not in out


def test_a_credited_deposit_is_never_turned_back_into_unattributed(monkeypatch, tmp_path, on):
    """A scan that read the sender as unlinked, finishing after the link endpoint credited the same
    transfer, must not leave it listed (and paging) as unattributed."""
    with hub(monkeypatch, tmp_path) as (client, db):
        store = deposit_watch.DepositStore(db._conn)
        store.record(tx_hash=tx(6), sender=SENDER, amount_units=1, block=1, status=deposit_watch.CREDITED,
                     account_id="acct_x")
        store.record(tx_hash=tx(6), sender=SENDER, amount_units=1, block=1, status=deposit_watch.UNATTRIBUTED)
        assert store.deposit(tx(6))["status"] == deposit_watch.CREDITED
        assert store.count_unattributed() == 0
        assert store.link(SENDER, "acct_x", "operator") == "linked"
        assert store.link(SENDER, "acct_y", "operator") == "taken"
        assert store.unlink(SENDER, "acct_y") is False and store.unlink(SENDER, "acct_x") is True



# ── Independent review, 2026-10-04: no transfer holds up the others ──────────────────────────
# Each test below reproduced a defect the review found in 3.15.11 (the first one stopped the live
# watcher for good on any refused quote payment); each now asserts the behaviour that replaced it.

TOKEN = USDC_BASE.lower()


class Node:
    """A careless fake Base node: transactions made of token logs, receipts that can be withheld,
    and an eth_getLogs that ignores the address and recipient filters (the watcher must re-check)."""

    def __init__(self):
        self.head, self.chain_id = 1000, 8453
        self.logs: list[dict] = []
        self.receipts: dict[str, dict | None] = {}
        self.paid: dict[tuple[str, str], tuple[int, str]] = {}

    def send(self, tx_hash, parts, *, withhold_receipt=False, token=TOKEN, to=WALLET):
        """parts: ("transfer", sender, units) or ("auth", authorizer, nonce)."""
        self.head += 1
        block = hex(self.head)
        receipt_logs = []
        for part in parts:
            if part[0] == "auth":
                receipt_logs.append({"address": TOKEN, "topics": [deposit_watch.AUTHORIZATION_USED_TOPIC,
                                                                  _topic(part[1]), part[2]]})
                continue
            log = {"address": token, "transactionHash": tx_hash, "blockNumber": block,
                   "topics": [deposit_watch.TRANSFER_TOPIC, _topic(part[1]), _topic(to)], "data": hex(part[2])}
            self.logs.append(log)
            receipt_logs.append(log)
        self.receipts[tx_hash] = None if withhold_receipt else {"logs": receipt_logs}

    def release(self, tx_hash):
        self.receipts[tx_hash] = {"logs": [log for log in self.logs if log["transactionHash"] == tx_hash]}

    def __call__(self, method, params):
        if method == "eth_chainId":
            return hex(self.chain_id)
        if method == "eth_blockNumber":
            return hex(self.head)
        if method == "eth_getLogs":
            f = params[0]
            lo, hi = int(f["fromBlock"], 16), int(f["toBlock"], 16)
            return [log for log in self.logs if lo <= int(log["blockNumber"], 16) <= hi]
        if method == "eth_getTransactionReceipt":
            return self.receipts.get(params[0])
        raise AssertionError(method)

    def verify(self, *, tx_hash, terms, require_nonce, **_):
        found = self.paid.get((tx_hash, require_nonce))
        if found is None:
            raise settle.PaymentError("no authorization for this nonce")
        units, payer = found
        return {"tx_hash": tx_hash, "paid_units": units, "authorizer": payer}


@pytest.fixture
def node(monkeypatch, on):
    n = Node()
    monkeypatch.setattr(settle, "_rpc", lambda url, method, params, timeout: n(method, params))
    monkeypatch.setattr(settle, "verify_transfer", n.verify)
    return n


def _link(client, account, address):
    r = client.post(f"/ai-market/v2/accounts/{account}/payer-wallets", json={"address": address}, headers=ADMIN)
    assert r.status_code == 200, r.text


def _quote(client, key, usd=5):
    r = client.post("/ai-market/v2/account/topup", headers={"X-API-Key": key}, json={"amount_usd": usd})
    assert r.status_code == 402, r.text
    return r.json()["nonce"]


def _row(db, tx_hash):
    return deposit_watch.DepositStore(db._conn).deposit(tx_hash)


def test_a_refused_quote_payment_does_not_stop_the_watcher(monkeypatch, tmp_path, node):
    """3.15.11 read `exc.retryable` (an AttributeError): one dust payment over any open quote
    stopped the live watcher for good, and every later deposit waited behind it."""
    attacker, linked = "0x" + "a8" * 20, "0x" + "f4" * 20
    with hub(monkeypatch, tmp_path) as (client, db):
        victim, _ = funded_account(client, db, 0.0)
        _link(client, victim, linked)
        _, key = funded_account(client, db, 0.0)
        nonce = _quote(client, key, 1)
        node.paid[(tx(300), nonce)] = (1, attacker)
        node.send(tx(300), [("auth", attacker, nonce), ("transfer", attacker, 1)])
        node.send(tx(301), [("transfer", linked, 7_000_000)])
        watcher(db, node).scan_once()
        assert balance(db, victim) == pytest.approx(7.0)
        row = _row(db, tx(300))
        assert row["status"] == deposit_watch.UNATTRIBUTED and deposit_watch.QUOTE_REFUSED in row["detail"]


def test_dust_quote_payments_cannot_wedge_the_cursor(monkeypatch, tmp_path, node):
    attacker, linked = "0x" + "a9" * 20, "0x" + "f3" * 20
    with hub(monkeypatch, tmp_path) as (client, db):
        victim, _ = funded_account(client, db, 0.0)
        _link(client, victim, linked)
        nonces = []
        for _ in range(3):
            _, key = funded_account(client, db, 0.0)
            nonces += [_quote(client, key, 1) for _ in range(5)]
        for i, n in enumerate(nonces[:13]):
            node.paid[(tx(100 + i), n)] = (1, attacker)
            node.send(tx(100 + i), [("auth", attacker, n), ("transfer", attacker, 1)])
        node.send(tx(200), [("transfer", linked, 7_000_000)])
        watcher(db, node).scan_once()
        assert balance(db, victim) == pytest.approx(7.0)


def test_a_quote_over_its_daily_limit_waits_while_the_others_are_credited(monkeypatch, tmp_path, node):
    monkeypatch.setenv("AIMARKET_TOPUP_DAILY_USD", "5")
    big, linked = "0x" + "f1" * 20, "0x" + "f2" * 20
    with hub(monkeypatch, tmp_path) as (client, db):
        acct_big, key_big = funded_account(client, db, 0.0)
        acct_other, _ = funded_account(client, db, 0.0)
        _link(client, acct_other, linked)
        q1 = _quote(client, key_big)
        q2 = topup.TopupStore(db._conn).mint(account_id=acct_big, amount_units=5_000_000, pay_to=WALLET,
                                             token_contract=TOKEN, chain="base", chain_id=8453, ttl_s=900).nonce
        for i, n in ((10, q1), (11, q2)):
            node.paid[(tx(i), n)] = (5_000_000, big)
            node.send(tx(i), [("auth", big, n), ("transfer", big, 5_000_000)])
        node.send(tx(12), [("transfer", linked, 3_000_000)])
        w = watcher(db, node)
        w.scan_once()
        assert balance(db, acct_big) == pytest.approx(5.0) and balance(db, acct_other) == pytest.approx(3.0)
        assert _row(db, tx(11))["status"] == deposit_watch.PENDING
        monkeypatch.setenv("AIMARKET_TOPUP_DAILY_USD", "50")    # the day rolls over
        topup._VERIFY_LOG.clear()
        w.scan_once()
        assert balance(db, acct_big) == pytest.approx(10.0)
        assert _row(db, tx(11))["status"] == deposit_watch.CREDITED


def test_two_senders_in_one_transaction_are_credited_to_neither(monkeypatch, tmp_path, node):
    """A dust transfer from a linked wallet placed in front of somebody else's payment used to
    credit the whole transaction to the linked account."""
    attacker, victim = "0x" + "aa" * 20, "0x" + "bb" * 20
    with hub(monkeypatch, tmp_path) as (client, db):
        acct, _ = funded_account(client, db, 0.0)
        _link(client, acct, attacker)
        node.send(tx(1), [("transfer", attacker, 1), ("auth", victim, "0x" + "77" * 32),
                          ("transfer", victim, 50_000_000)])
        watcher(db, node).scan_once()
        assert balance(db, acct) == 0.0
        row = _row(db, tx(1))
        assert row["status"] == deposit_watch.UNATTRIBUTED and row["detail"].startswith(deposit_watch.SEVERAL_SENDERS)


def test_the_payment_recipient_wallet_is_never_watched(monkeypatch, on):
    monkeypatch.delenv("AIMARKET_X402_PAY_TO")
    monkeypatch.setenv("AIMARKET_PAYMENT_RECIPIENT", WALLET)     # x402 falls back to it; channels deposit there
    assert not deposit_watch.enabled()
    assert "AIMARKET_PAYMENT_RECIPIENT" in deposit_watch.unavailable_reason()


def test_dust_is_ignored_not_paged(monkeypatch, tmp_path, node):
    dust = "0x" + "cc" * 20
    with hub(monkeypatch, tmp_path) as (client, db):
        acct, _ = funded_account(client, db, 0.0)
        node.send(tx(2), [("transfer", dust, 5)])
        watcher(db, node).scan_once()
        assert _row(db, tx(2))["status"] == deposit_watch.IGNORED
        assert _well_known_watch(client)["unattributed_deposits"] == 0
        _link(client, acct, dust)
        assert _row(db, tx(2))["status"] == deposit_watch.IGNORED


def test_a_hand_credit_settles_an_unattributed_deposit(monkeypatch, tmp_path, node):
    sender = "0x" + "dd" * 20
    with hub(monkeypatch, tmp_path) as (client, db):
        acct, _ = funded_account(client, db, 0.0)
        node.send(tx(3), [("transfer", sender, 2_000_000)])
        w = watcher(db, node)
        w.scan_once()
        assert _well_known_watch(client)["unattributed_deposits"] == 1
        r = client.post(f"/ai-market/v2/accounts/{acct}/credit", headers=ADMIN,
                        json={"amount_usd": 2.0, "tx_hash": tx(3)})
        assert r.status_code == 200
        w.scan_once()
        assert _row(db, tx(3))["status"] == deposit_watch.ELSEWHERE
        assert _well_known_watch(client)["unattributed_deposits"] == 0
        assert balance(db, acct) == pytest.approx(2.0)


def test_a_missing_receipt_waits_instead_of_guessing(monkeypatch, tmp_path, node):
    """3.15.11 read a missing receipt as "no quote": a quote payment from a linked wallet went
    to the wallet's account, and the quote's owner could never redeem it."""
    payer = "0x" + "ee" * 20
    with hub(monkeypatch, tmp_path) as (client, db):
        acct_a, _ = funded_account(client, db, 0.0)
        acct_b, key_b = funded_account(client, db, 0.0)
        _link(client, acct_a, payer)
        nonce = _quote(client, key_b)
        node.paid[(tx(4), nonce)] = (5_000_000, payer)
        node.send(tx(4), [("auth", payer, nonce), ("transfer", payer, 5_000_000)], withhold_receipt=True)
        w = watcher(db, node)
        w.scan_once()
        assert _row(db, tx(4))["status"] == deposit_watch.PENDING
        assert balance(db, acct_a) == 0.0 and balance(db, acct_b) == 0.0
        node.receipts[tx(4)] = {"logs": [
            {"address": TOKEN, "topics": [deposit_watch.AUTHORIZATION_USED_TOPIC, _topic(payer), nonce]},
            *[log for log in node.logs if log["transactionHash"] == tx(4)]]}
        w.scan_once()
        assert balance(db, acct_b) == pytest.approx(5.0) and balance(db, acct_a) == 0.0


def test_a_quote_presented_by_hand_settles_its_waiting_row(monkeypatch, tmp_path, node):
    payer = "0x" + "ef" * 20
    with hub(monkeypatch, tmp_path) as (client, db):
        acct_b, key_b = funded_account(client, db, 0.0)
        nonce = _quote(client, key_b)
        node.paid[(tx(5), nonce)] = (5_000_000, payer)
        node.send(tx(5), [("auth", payer, nonce), ("transfer", payer, 5_000_000)], withhold_receipt=True)
        w = watcher(db, node)
        w.scan_once()
        assert client.post(f"/ai-market/v2/topups/{nonce}", json={"tx_hash": tx(5)}).status_code == 200
        node.receipts[tx(5)] = {"logs": [
            {"address": TOKEN, "topics": [deposit_watch.AUTHORIZATION_USED_TOPIC, _topic(payer), nonce]},
            *[log for log in node.logs if log["transactionHash"] == tx(5)]]}
        w.scan_once()
        assert balance(db, acct_b) == pytest.approx(5.0)
        assert _row(db, tx(5))["status"] == deposit_watch.CREDITED
        wk = _well_known_watch(client)
        assert wk["unattributed_deposits"] == 0 and wk["pending_deposits"] == 0


def test_both_quotes_paid_in_one_transaction_are_redeemed(monkeypatch, tmp_path, node):
    payer = "0x" + "e1" * 20
    with hub(monkeypatch, tmp_path) as (client, db):
        acct_1, key_1 = funded_account(client, db, 0.0)
        acct_2, key_2 = funded_account(client, db, 0.0)
        n1, n2 = _quote(client, key_1, 2), _quote(client, key_2, 3)
        node.paid[(tx(6), n1)] = (2_000_000, payer)
        node.paid[(tx(6), n2)] = (3_000_000, payer)
        node.send(tx(6), [("auth", payer, n1), ("transfer", payer, 2_000_000),
                          ("auth", payer, n2), ("transfer", payer, 3_000_000)])
        watcher(db, node).scan_once()
        assert balance(db, acct_1) == pytest.approx(2.0) and balance(db, acct_2) == pytest.approx(3.0)


def test_a_link_that_lands_mid_scan_is_settled_on_the_next(monkeypatch, tmp_path, node):
    sender = "0x" + "e2" * 20
    with hub(monkeypatch, tmp_path) as (client, db):
        acct, _ = funded_account(client, db, 0.0)
        node.send(tx(7), [("transfer", sender, 4_000_000)])
        w = watcher(db, node)
        w.scan_once()
        assert deposit_watch.DepositStore(db._conn).link(sender, acct, "operator") == "linked"  # no backlog pass
        w.scan_once()
        assert balance(db, acct) == pytest.approx(4.0)


def test_logs_the_node_should_not_have_returned_are_ignored(monkeypatch, tmp_path, node):
    linked = "0x" + "e3" * 20
    with hub(monkeypatch, tmp_path) as (client, db):
        acct, _ = funded_account(client, db, 0.0)
        _link(client, acct, linked)
        node.send(tx(8), [("transfer", linked, 9_000_000)], token="0x" + "99" * 20)   # another token
        node.send(tx(9), [("transfer", linked, 9_000_000)], to="0x" + "98" * 20)      # to somebody else
        watcher(db, node).scan_once()
        assert balance(db, acct) == 0.0 and _row(db, tx(8)) is None and _row(db, tx(9)) is None


def test_a_node_on_another_chain_stops_the_scan(monkeypatch, tmp_path, node):
    with hub(monkeypatch, tmp_path) as (client, db):
        w = watcher(db, node)
        node.chain_id = 1
        with pytest.raises(deposit_watch.Retry):
            w.scan_once()
        assert w.store.cursor(f"base:{WALLET}") is None


def test_the_operator_settles_an_open_deposit_out_of_band(monkeypatch, tmp_path, node):
    sender = "0x" + "e4" * 20
    with hub(monkeypatch, tmp_path) as (client, db):
        node.send(tx(13), [("transfer", sender, 1_000_000)])
        watcher(db, node).scan_once()
        url = f"/ai-market/v2/admin/deposits/{tx(13)}/resolve"
        assert client.post(url, json={}, headers=ADMIN).status_code == 400
        assert client.post(url, json={"note": "refunded"}, headers={"Authorization": "Bearer wrong"}).status_code in (401, 403)
        r = client.post(url, json={"note": "refunded in 0xabc"}, headers=ADMIN)
        assert r.status_code == 200 and r.json()["deposit"]["status"] == deposit_watch.RESOLVED
        assert _well_known_watch(client)["unattributed_deposits"] == 0
        assert client.post(url, json={"note": "again"}, headers=ADMIN).status_code == 409


def test_the_well_known_says_when_the_wallet_was_last_read(monkeypatch, tmp_path, node):
    with hub(monkeypatch, tmp_path) as (client, db):
        assert _well_known_watch(client)["last_scan_at"] is None
        watcher(db, node).scan_once()
        assert abs(_well_known_watch(client)["last_scan_at"] - time.time()) < 60


def test_a_hub_that_cannot_check_signatures_says_so(monkeypatch, tmp_path, node):
    monkeypatch.setattr(deposit_watch, "signature_links_available", lambda: False)
    with hub(monkeypatch, tmp_path) as (client, db):
        _, key = funded_account(client, db, 0.0)
        r = client.post("/ai-market/v2/account/payer-wallets", headers={"X-API-Key": key},
                        json={"address": SENDER, "issued_at": int(time.time()), "signature": "0x00"})
        assert r.status_code == 503


def test_a_token_with_other_decimals_is_not_credited_by_the_watcher(monkeypatch, tmp_path, on):
    """The quote door refuses an asset whose decimals() is not the scale the hub converts
    with; plain transfers are the same money through a second door. 1e18 units of an
    18-decimal token would otherwise be credited as $1e12."""
    monkeypatch.setenv("AIMARKET_TOPUP_VERIFY_DECIMALS", "1")
    reported = {"decimals": 18}

    def node(url, method, params, timeout):
        if method == "eth_call":
            return hex(reported["decimals"])
        return on(method, params)

    monkeypatch.setattr(settle, "_rpc", node)
    with hub(monkeypatch, tmp_path) as (client, db):
        account, _ = funded_account(client, db, 0.0)
        assert client.post(f"/ai-market/v2/accounts/{account}/payer-wallets", json={"address": SENDER},
                           headers=ADMIN).status_code == 200
        on.transfer(tx(9), SENDER, 1_000_000)
        w = watcher(db, on)
        summary = w.scan_once()
        assert summary["scanned"] is False and "18 decimals" in summary["reason"]
        assert w.credit_linked(SENDER) == []
        assert balance(db, account) == 0.0
        topup._DECIMALS_READ.clear()
        reported["decimals"] = 6
        assert w.scan_once()["credited"] == 1
        assert balance(db, account) == pytest.approx(1.0)


def test_a_node_that_answers_429_rests_while_the_next_one_serves_the_scan(monkeypatch, tmp_path, on):
    """2026-10-08..21 the Independent hub's only watcher node (mainnet.base.org) answered 429 to
    every eth_getLogs and the scan asked it again each minute for 13 days. With a list, the
    refusing node rests and the next one in rotation reads the logs."""
    import httpx

    monkeypatch.setenv("AIMARKET_SETTLE_RPC_URL", "http://limited.test,http://rpc.test")
    asked: list[tuple[str, str]] = []

    def rpc(url, method, params, timeout):
        asked.append((url, method))
        if url == "http://limited.test" and method == "eth_getLogs":
            request = httpx.Request("POST", url)
            raise httpx.HTTPStatusError("429 Too Many Requests", request=request,
                                        response=httpx.Response(429, request=request, headers={"Retry-After": "60"}))
        return on(method, params)

    monkeypatch.setattr(settle, "_rpc", rpc)
    with hub(monkeypatch, tmp_path) as (client, db):
        account, _ = funded_account(client, db, 0.0)
        assert client.post(f"/ai-market/v2/accounts/{account}/payer-wallets", json={"address": SENDER},
                           headers=ADMIN).status_code == 200
        w = deposit_watch.Watcher(
            store=deposit_watch.DepositStore(db._conn), ledger=credits.CreditsLedger(db._conn),
            topups=topup.TopupStore(db._conn), payments=settle.PaymentStore(db._conn),
            claim_deposit=lambda *, stack, **kw: channels.claim_deposit_as(stack, **kw),
            release_deposit=lambda *, stack, **kw: channels.release_deposit_as(stack, **kw),
            claim_holder=lambda **kw: channels.deposit_claim_holder(**kw))
        for n in range(1, 4):
            on.transfer(tx(70 + n), SENDER, 1_000_000)
            assert w.scan_once()["credited"] == 1
        assert balance(db, account) == pytest.approx(3.0)
    logs = [url for url, method in asked if method == "eth_getLogs"]
    first_refusal = logs.index("http://limited.test")
    assert set(logs[first_refusal + 1:]) == {"http://rpc.test"}       # asked once, then left to rest


def test_a_scan_that_catches_up_rests_between_windows_and_a_current_one_does_not(monkeypatch, tmp_path, on):
    """Catching up 13 days back to back, the Independent node's scan was refused after ~10 windows
    and waited a minute each time; paced, the same node served 1138 in a row."""
    rests: list[float] = []
    monkeypatch.setattr(deposit_watch, "_rest", rests.append)
    monkeypatch.setenv("AIMARKET_DEPOSIT_WATCH_PAUSE_S", "0.25")
    with hub(monkeypatch, tmp_path) as (client, db):
        w = watcher(db, on)
        key = f"base:{WALLET.lower()}"
        w.scan_once()                              # at the head: nothing to catch up
        assert rests == []
        on.head += 20 * 500                        # 20 windows behind
        w.scan_once()
        assert rests and set(rests) == {0.25}
        assert len(rests) == 20 - deposit_watch.CATCH_UP_CHUNKS   # none once 4 or fewer were left
        assert w.store.cursor(key) == on.head + 1
