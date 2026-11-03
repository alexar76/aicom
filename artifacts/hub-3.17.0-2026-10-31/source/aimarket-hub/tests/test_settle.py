"""The market rail: buyer pays the seller; Hub only verifies.

RPC is stubbed so these pin the money rules, not the network. One payment
buys one call, a transfer to the wrong address is refused, and a priced
listing without a seller is not billed to the platform.
"""

from __future__ import annotations

import json
from contextlib import contextmanager

import pytest
from types import SimpleNamespace
from fastapi.testclient import TestClient

from aimarket_hub import settle
from aimarket_hub.api import create_app
from aimarket_hub.config import HubConfig
from aimarket_hub.database import HubDatabase
from aimarket_hub.models import Capability
from aimarket_hub.signing import Signer

TRANSFER = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
BUYER = "0x6E94c380d908531f9822035d6cc4c8D2B0186C9c"
SELLER = "0x1218000000000000000000000000000000000001"
OPERATOR = "0x1218Ff3600000000000000000000000000000a0a"
TX = "0x" + "ab" * 32
NONCE = "0x" + "c3" * 32
PRICE = 0.02


def _topic_addr(address: str) -> str:
    return "0x" + "0" * 24 + address[2:].lower()


def fake_rpc(monkeypatch, *, to: str, units: int, token: str = USDC,
             status: str = "0x1", block: int = 100, head: int = 101) -> dict:
    seen: dict = {"receipts": 0}

    def _post(url, json=None, timeout=None):  # noqa: A002
        method = json["method"]

        class R:
            @staticmethod
            def raise_for_status() -> None:
                return None

            @staticmethod
            def json() -> dict:
                if method == "eth_chainId": return {"result": hex(8453)}
                if method == "eth_blockNumber":
                    return {"result": hex(head)}
                seen["receipts"] += 1
                return {
                    "result": {
                        "status": status,
                        "blockNumber": hex(block),
                        "logs": [
                            {
                                "address": token,
                                "topics": [TRANSFER, _topic_addr(BUYER), _topic_addr(to)],
                                "data": hex(units),
                            }
                        ],
                    }
                }

        return R()

    monkeypatch.setattr("aimarket_hub.settle.httpx.post", _post)
    monkeypatch.setattr(
        "aimarket_hub.settle.rpc_urls", lambda *args: ["http://rpc.invalid"],
    )
    return seen


def fake_rpc_bound(monkeypatch, *, to: str, units: int, nonce: str) -> None:
    """A receipt in FiatToken's order: the authorization over `nonce`, then its transfer."""
    auth_used = "0x98de503528ee59b575ef0c0a2576a82497bfc029a5685b209e9ec333479b10a5"
    logs = [
        {"address": USDC, "topics": [auth_used, _topic_addr(BUYER), nonce], "data": "0x"},
        {"address": USDC, "topics": [TRANSFER, _topic_addr(BUYER), _topic_addr(to)], "data": hex(units)},
    ]

    def _post(url, json=None, timeout=None):  # noqa: A002
        class R:
            @staticmethod
            def raise_for_status() -> None:
                return None

            @staticmethod
            def json() -> dict:
                if json["method"] == "eth_chainId": return {"result": hex(8453)}
                if json["method"] == "eth_blockNumber":
                    return {"result": hex(101)}
                return {"result": {"status": "0x1", "blockNumber": hex(100), "logs": logs}}

        return R()

    monkeypatch.setattr("aimarket_hub.settle.httpx.post", _post)
    monkeypatch.setattr("aimarket_hub.settle.rpc_urls", lambda *args: ["http://rpc.invalid"])


@contextmanager
def _hub(monkeypatch, tmp_path, **env):
    env.setdefault("AIMARKET_X402_CHAIN", "base")
    env.setdefault("AIMARKET_ORACLE_FAMILY_URL", "off")
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    root = tmp_path / f"hub-{len(list(tmp_path.iterdir()))}"
    root.mkdir(parents=True, exist_ok=True)
    config = HubConfig()
    config.db_path = str(root / "hub.db")
    config.signing_key_path = str(root / "key")
    db = HubDatabase(root / "hub.db")
    db.upsert_capability(Capability(
        capability_id="x.pay@v1", product_id="x-pay", name="Paid pack",
        description="static", price_per_call_usd=PRICE, source_hub="local",
        invoke_url="", prompt_template=json.dumps({"answer": "paid"}),
        payout_address=SELLER, publisher_id=SELLER,
    ))
    app = create_app(config=config, db=db, signer=Signer(root / "key"))
    with TestClient(app) as client:
        client.hub_db = db  # type: ignore[attr-defined]
        yield client


def _invoke(client, header: str | None = None, secret: str = ""):
    headers = {"X-PAYMENT": header} if header else {}
    if secret:
        headers["X-Payment-Secret"] = secret
    return client.post("/ai-market/v2/invoke", headers=headers, json={
        "product_id": "x-pay", "capability_id": "x.pay@v1",
        "input": {}, "source_hub": "local",
    })


@pytest.mark.parametrize("credits_on", ["0", "1"])
def test_search_tells_buyers_which_local_offers_accept_credits(monkeypatch, tmp_path, credits_on):
    with _hub(monkeypatch, tmp_path, AIMARKET_CREDITS_ENABLED=credits_on, AIMARKET_X402_PAY_TO=OPERATOR) as client:
        for name, price in (("operator", .1), ("free", 0)):
            client.hub_db.upsert_capability(Capability(
                capability_id=f"{name}.diagnose@v1", product_id=f"{name}-diagnose", name=name,
                description="diagnostic service", price_per_call_usd=price, source_hub="local",
                prompt_template=json.dumps({"answer": "diagnosis"}), payout_address=OPERATOR,
            ))
        response = client.get("/ai-market/v2/search", params={"limit": 0, "min_trust": 0})
        assert response.status_code == 200
        rows = {r["capability_id"]: r for r in response.json()["matches"]}
        assert rows["x.pay@v1"]["credits_eligible"] is False  # direct third-party seller
        assert rows["operator.diagnose@v1"]["credits_eligible"] is (credits_on == "1")
        assert rows["free.diagnose@v1"]["credits_eligible"] is True


class TestSellerPayTo:
    def test_a_wallet_publisher_is_the_payee(self):
        cap = Capability(
            capability_id="a@v1", product_id="p", name="n",
            publisher_id=SELLER, price_per_call_usd=0.01,
        )
        assert settle.seller_pay_to(cap, operator_pay_to=OPERATOR) == SELLER

    def test_an_explicit_payout_wins_over_the_operator_wallet(self):
        cap = Capability(
            capability_id="a@v1", product_id="p", name="n",
            publisher_id="some-slug", payout_address=SELLER, price_per_call_usd=0.01,
        )
        assert settle.seller_pay_to(cap, operator_pay_to=OPERATOR) == SELLER

    def test_a_slug_publisher_is_not_silently_paid_to_the_platform(self):
        cap = Capability(
            capability_id="a@v1", product_id="p", name="n",
            publisher_id="credit-acct-1", price_per_call_usd=0.01,
        )
        assert settle.seller_pay_to(cap, operator_pay_to=OPERATOR) == ""

    def test_an_operator_owned_listing_pays_the_operator_as_seller(self):
        cap = Capability(
            capability_id="a@v1", product_id="p", name="n", price_per_call_usd=0.01,
        )
        assert settle.seller_pay_to(cap, operator_pay_to=OPERATOR) == OPERATOR


class TestVerifyTransfer:
    def test_a_transfer_to_someone_else_is_refused(self, monkeypatch):
        fake_rpc_bound(monkeypatch, to=BUYER, units=20_000, nonce=NONCE)
        terms = settle.PaymentTerms("base", "USDC", USDC, 6, SELLER, 20_000, PRICE, 1)
        with pytest.raises(settle.PaymentError, match="did not pay this call"):
            settle.verify_transfer(tx_hash=TX, terms=terms, require_nonce=NONCE,
                                   rpc_url="http://rpc.invalid")

    def test_an_underpayment_is_refused(self, monkeypatch):
        fake_rpc_bound(monkeypatch, to=SELLER, units=19_999, nonce=NONCE)
        terms = settle.PaymentTerms("base", "USDC", USDC, 6, SELLER, 20_000, PRICE, 1)
        with pytest.raises(settle.PaymentError, match="did not pay this call"):
            settle.verify_transfer(tx_hash=TX, terms=terms, require_nonce=NONCE,
                                   rpc_url="http://rpc.invalid")

    def test_a_good_transfer_settles(self, monkeypatch):
        fake_rpc_bound(monkeypatch, to=SELLER, units=20_000, nonce=NONCE)
        terms = settle.PaymentTerms("base", "USDC", USDC, 6, SELLER, 20_000, PRICE, 1)
        out = settle.verify_transfer(tx_hash=TX, terms=terms, require_nonce=NONCE,
                                     rpc_url="http://rpc.invalid")
        assert out["pay_to"] == SELLER
        assert out["paid_units"] == 20_000
        assert out["tx_hash"] == TX
        assert out["authorizer"] == BUYER.lower()

    @pytest.mark.parametrize("nonce", ["", "0x1234", "not-a-nonce"])
    def test_without_a_nonce_nothing_settles(self, monkeypatch, nonce):
        """A plain transfer to the seller is money from somebody, for something."""
        seen = fake_rpc(monkeypatch, to=SELLER, units=1_000_000)
        terms = settle.PaymentTerms("base", "USDC", USDC, 6, SELLER, 20_000, PRICE, 1)
        with pytest.raises(settle.PaymentError, match="not bound to a call"):
            settle.verify_transfer(tx_hash=TX, terms=terms, require_nonce=nonce,
                                   rpc_url="http://rpc.invalid")
        assert seen["receipts"] == 0, "refused before the chain is even asked"

    def test_a_plain_transfer_next_to_the_nonce_pays_nothing(self, monkeypatch):
        """The nonce named, but no authorization over it moved the money."""
        fake_rpc(monkeypatch, to=SELLER, units=1_000_000)
        terms = settle.PaymentTerms("base", "USDC", USDC, 6, SELLER, 20_000, PRICE, 1)
        with pytest.raises(settle.PaymentError, match="no EIP-3009 authorization"):
            settle.verify_transfer(tx_hash=TX, terms=terms, require_nonce=NONCE,
                                   rpc_url="http://rpc.invalid")


class TestInvokeSettle:
    def test_an_unpaid_call_names_the_seller_not_the_platform(self, monkeypatch, tmp_path):
        with _hub(monkeypatch, tmp_path, AIMARKET_X402_PAY_TO=OPERATOR) as client:
            r = _invoke(client)
            assert r.status_code == 402
            body = r.json()
            assert body["pay_to"] == SELLER
            accepts = body.get("accepts") or []
            assert accepts and accepts[0]["payTo"] == SELLER
            raw = {k.upper(): v for k, v in r.headers.items()}["PAYMENT-REQUIRED"]
            import base64
            doc = json.loads(base64.b64decode(raw))
            assert doc["accepts"][0]["payTo"] == SELLER

    def test_a_paid_call_is_served_and_the_tx_cannot_buy_twice(self, monkeypatch, tmp_path):
        with _hub(monkeypatch, tmp_path) as client:
            quote = _invoke(client).json()
            fake_rpc_bound(monkeypatch, to=SELLER, units=20_000, nonce=quote["nonce"])
            first = _invoke(client, TX, secret=quote["payment_secret"])
            assert first.status_code == 200, first.text
            assert first.json()["result"]["answer"] == "paid"
            stats = client.get("/ai-market/v2/stats/live").json()["summary"]["x402"]
            assert stats["x402_settled_usd"] == pytest.approx(PRICE)
            assert stats["x402_unsettled_usd"] == 0.0
            second = _invoke(client, TX, secret=quote["payment_secret"])
            assert second.status_code == 402
            assert "already been" in second.json()["detail"]

    def test_a_plain_transfer_buys_nothing_whatever_the_setting_says(self, monkeypatch, tmp_path, caplog):
        """Nothing in a plain transfer says who paid: its hash is public once mined, so
        whoever presents it first takes the call. There is no unbound mode to turn on."""
        seen = fake_rpc(monkeypatch, to=SELLER, units=1_000_000)
        with caplog.at_level("ERROR", logger="aimarket_hub.settle"):
            with _hub(monkeypatch, tmp_path, AIMARKET_SETTLE_REQUIRE_BINDING="0") as client:
                r = _invoke(client, TX)
                assert r.status_code == 402
                assert "X-Payment-Nonce" in r.json()["detail"]
                assert seen["receipts"] == 0
        assert any("REQUIRE_BINDING=0 is ignored" in rec.getMessage() for rec in caplog.records), \
            "an operator who still sets the switch is told it does nothing"

    def test_a_signature_without_a_chain_receipt_is_not_a_payment(self, monkeypatch, tmp_path):
        with _hub(monkeypatch, tmp_path) as client:
            payload = {"scheme": "exact", "network": "eip155:8453", "asset": USDC}
            import base64
            header = base64.b64encode(json.dumps(payload).encode()).decode()
            r = _invoke(client, header)
            assert r.status_code == 402
            assert "on-chain" in r.json()["detail"]

    def test_discovery_advertises_the_seller(self, monkeypatch, tmp_path):
        with _hub(monkeypatch, tmp_path) as client:
            r = client.get("/discovery/resources")
            item = next(
                i for i in r.json()["items"]
                if i["metadata"]["capability_id"] == "x.pay@v1"
            )
            assert item["accepts"][0]["payTo"] == SELLER
            assert item["metadata"]["payout_address"] == SELLER

class TestAListingWithNoSeller:
    """A priced listing nobody can be paid for must not point at the platform.

    ``seller_pay_to`` already returns "" for a publisher that is a credit-account
    slug rather than a wallet, and ``settle.terms_for`` refuses such a listing at
    settlement. The 402 did not agree: it fell back to the operator's own wallet,
    so a buyer following the offer paid the platform and then got
    "this listing has no seller payout_address" back. The two ends now say the
    same thing.
    """

    @contextmanager
    def _sellerless_hub(self, monkeypatch, tmp_path, **env):
        env.setdefault("AIMARKET_X402_CHAIN", "base")
        env.setdefault("AIMARKET_X402_ACCEPT", "1")
        env.setdefault("AIMARKET_X402_PAY_TO", OPERATOR)
        env.setdefault("AIFACTORY_CRYPTO_ENABLED", "1")
        env.setdefault("AIMARKET_ORACLE_FAMILY_URL", "off")
        for key, value in env.items():
            monkeypatch.setenv(key, value)
        root = tmp_path / f"hub-{len(list(tmp_path.iterdir()))}"
        root.mkdir(parents=True, exist_ok=True)
        config = HubConfig()
        config.db_path = str(root / "hub.db")
        config.signing_key_path = str(root / "key")
        db = HubDatabase(root / "hub.db")
        db.upsert_capability(Capability(
            capability_id="x.slug@v1", product_id="x-slug", name="Slug pack",
            description="static", price_per_call_usd=PRICE, source_hub="local",
            invoke_url="", prompt_template=json.dumps({"answer": "paid"}),
            publisher_id="credit-acct-1",
        ))
        app = create_app(config=config, db=db, signer=Signer(root / "key"))
        with TestClient(app) as client:
            yield client

    def test_the_402_does_not_send_the_buyer_to_the_platform_wallet(
        self, monkeypatch, tmp_path,
    ):
        with self._sellerless_hub(monkeypatch, tmp_path) as client:
            r = client.post("/ai-market/v2/invoke", json={
                "product_id": "x-slug", "capability_id": "x.slug@v1",
                "input": {}, "source_hub": "local",
            })
            assert r.status_code == 402
            assert OPERATOR.lower() not in r.text.lower()
            body = r.json()
            assert body["error"] == "listing_not_sellable"
            assert "no payout address" in body["detail"]
            assert not body.get("accepts")

    def test_settlement_refuses_the_same_listing(self, monkeypatch, tmp_path):
        """The offer and the settlement agree: nobody to pay, no sale."""
        fake_rpc(monkeypatch, to=OPERATOR, units=20_000)
        with self._sellerless_hub(monkeypatch, tmp_path) as client:
            r = client.post("/ai-market/v2/invoke", headers={"X-PAYMENT": TX}, json={
                "product_id": "x-slug", "capability_id": "x.slug@v1",
                "input": {}, "source_hub": "local",
            })
            assert r.status_code == 402
            body = r.json()
            # The settlement refusal keeps its OWN reason rather than being
            # flattened into the generic one — it knows more than the offer does.
            assert body["error"] == "payment_invalid"
            assert "payout_address" in body["detail"]
            assert OPERATOR.lower() not in r.text.lower()


class TestPayeeIsNotOptional:
    """`None` means "no listing here"; "" means "this listing has no seller"."""

    def test_an_unbound_402_still_offers_the_operator_wallet(self, monkeypatch):
        monkeypatch.setenv("AIMARKET_X402_CHAIN", "base")
        monkeypatch.setenv("AIMARKET_X402_PAY_TO", OPERATOR)
        from aimarket_hub import x402
        accepts = x402.payment_requirements(PRICE)
        assert accepts and accepts[0]["payTo"] == OPERATOR

    def test_an_empty_payee_makes_no_offer_at_all(self, monkeypatch):
        monkeypatch.setenv("AIMARKET_X402_CHAIN", "base")
        monkeypatch.setenv("AIMARKET_X402_PAY_TO", OPERATOR)
        from aimarket_hub import x402
        assert x402.payment_requirements(PRICE, pay_to="") == []

SPLITTER = "0x5911770000000000000000000000000000000002"


def fake_rpc_two_legs(monkeypatch, *, seller_units: int, fee_units: int,
                      fee_to: str = OPERATOR, token: str = USDC,
                      block: int = 100, head: int = 101, nonce: str = "") -> None:
    """A receipt in the splitter's order: the buyer's authorization over `nonce`, its
    transfer into the splitter, then the splitter's legs to the seller and the operator."""
    auth_used = "0x98de503528ee59b575ef0c0a2576a82497bfc029a5685b209e9ec333479b10a5"
    logs = [
        {"address": token, "topics": [auth_used, _topic_addr(BUYER), nonce or NONCE], "data": "0x"},
        {"address": token, "topics": [TRANSFER, _topic_addr(BUYER), _topic_addr(SPLITTER)],
         "data": hex(seller_units + fee_units)},
        {"address": token, "topics": [TRANSFER, _topic_addr(SPLITTER), _topic_addr(SELLER)],
         "data": hex(seller_units)},
    ]
    if fee_units:
        logs.append(
            {"address": token, "topics": [TRANSFER, _topic_addr(SPLITTER), _topic_addr(fee_to)],
             "data": hex(fee_units)}
        )

    def _post(url, json=None, timeout=None):  # noqa: A002
        method = json["method"]

        class R:
            @staticmethod
            def raise_for_status() -> None:
                return None

            @staticmethod
            def json() -> dict:
                if method == "eth_chainId": return {"result": hex(8453)}
                if method == "eth_blockNumber":
                    return {"result": hex(head)}
                return {"result": {"status": "0x1", "blockNumber": hex(block), "logs": logs}}

        return R()

    monkeypatch.setattr("aimarket_hub.settle.httpx.post", _post)
    monkeypatch.setattr("aimarket_hub.settle.rpc_urls", lambda *args: ["http://rpc.invalid"])


class TestTheOperatorsShare:
    """A cut without custody: the chain says both were paid, or the call is refused."""

    def test_rounding_goes_to_the_seller(self):
        # The same arithmetic the contract does, and the same reason: the computed
        # side loses the dust, so the computed side must be the operator's.
        assert settle.fee_split(1, 250) == (1, 0)
        assert settle.fee_split(20_000, 250) == (19_500, 500)
        assert settle.fee_split(20_000, 0) == (20_000, 0)

    def test_a_fee_is_off_until_it_is_configured(self, monkeypatch):
        monkeypatch.delenv("AIMARKET_MARKET_FEE_BPS", raising=False)
        assert settle.fee_bps() == 0

    def test_the_fee_cannot_exceed_what_the_contract_allows(self, monkeypatch):
        monkeypatch.setenv("AIMARKET_MARKET_FEE_BPS", "5000")
        assert settle.fee_bps() == 1000

    def test_paying_only_the_seller_does_not_buy_the_call(self, monkeypatch):
        """The whole point: the fee is enforced by the chain, not by a contract."""
        fake_rpc_two_legs(monkeypatch, seller_units=19_500, fee_units=0)
        terms = settle.PaymentTerms(
            "base", "USDC", USDC, 6, SELLER, 20_000, PRICE, 1,
            seller_units=19_500, fee_units=500, fee_to=OPERATOR, offer_to=SPLITTER,
        )
        with pytest.raises(settle.PaymentError, match="the operator out of it"):
            settle.verify_transfer(tx_hash=TX, terms=terms, require_nonce=NONCE,
                                   rpc_url="http://rpc.invalid")

    def test_both_legs_in_one_transaction_settle(self, monkeypatch):
        fake_rpc_two_legs(monkeypatch, seller_units=19_500, fee_units=500)
        terms = settle.PaymentTerms(
            "base", "USDC", USDC, 6, SELLER, 20_000, PRICE, 1,
            seller_units=19_500, fee_units=500, fee_to=OPERATOR, offer_to=SPLITTER,
        )
        settled = settle.verify_transfer(
            tx_hash=TX, terms=terms, require_nonce=NONCE, rpc_url="http://rpc.invalid",
        )
        assert settled["paid_units"] == 19_500
        assert settled["fee_units"] == 500

    def test_the_402_names_the_splitter_but_verification_names_the_seller(self, monkeypatch):
        """`payTo` is a convenience; who must be paid is not."""
        monkeypatch.setenv("AIMARKET_X402_CHAIN", "base")
        monkeypatch.setenv("AIMARKET_MARKET_FEE_BPS", "250")
        monkeypatch.setenv("AIMARKET_MARKET_FEE_TO", OPERATOR)
        monkeypatch.setenv("AIMARKET_MARKET_SPLITTER", SPLITTER)
        cap = Capability(
            capability_id="a@v1", product_id="p", name="n",
            payout_address=SELLER, price_per_call_usd=PRICE,
        )
        terms = settle.terms_for(cap)
        assert terms is not None
        assert terms.offer_to == SPLITTER
        assert terms.as_x402_accept()["payTo"] == SPLITTER
        assert terms.pay_to == SELLER          # who verification requires
        assert terms.fee_to == OPERATOR
        assert terms.seller_units + terms.fee_units == terms.amount_units

    def test_a_fee_with_nowhere_to_send_it_is_not_charged(self, monkeypatch):
        monkeypatch.setenv("AIMARKET_X402_CHAIN", "base")
        monkeypatch.setenv("AIMARKET_MARKET_FEE_BPS", "250")
        monkeypatch.delenv("AIMARKET_MARKET_FEE_TO", raising=False)
        monkeypatch.delenv("AIMARKET_X402_PAY_TO", raising=False)
        monkeypatch.delenv("AIMARKET_PAYMENT_RECIPIENT", raising=False)
        cap = Capability(
            capability_id="a@v1", product_id="p", name="n",
            payout_address=SELLER, price_per_call_usd=PRICE,
        )
        terms = settle.terms_for(cap)
        assert terms is not None
        assert terms.fee_units == 0
        assert terms.seller_units == terms.amount_units
        assert terms.offer_to == SELLER

class TestTheRoutingFeeIsOwedToTheHub:
    """The hub's broker fee is owed to the HUB, not to the listing's seller.

    The federated path binds the listing's payee early, because most of its 402s are
    about the sale. The routing-fee refusal is not: `needed` there is the hub's own 1%
    for brokering somebody else's capability, and it was inheriting the seller's
    address — so the offer asked the buyer to pay the hub's fee TO THE SELLER. Caught
    on modelmarket.dev minutes after the rail shipped, by reading a real 402.

    Reaching that branch needs a registered federated peer, which is a heavy fixture;
    what is pinned here is the rule the fix turns on, and the end-to-end check is the
    live 402 itself.
    """

    def test_the_fee_goes_to_the_hub_wallet_not_to_any_listing(self, monkeypatch):
        monkeypatch.setenv("AIMARKET_X402_PAY_TO", OPERATOR)
        monkeypatch.delenv("AIMARKET_MARKET_FEE_TO", raising=False)
        assert settle.fee_recipient() == OPERATOR
        assert settle.fee_recipient() != SELLER

    def test_an_explicit_fee_wallet_wins(self, monkeypatch):
        other = "0x0fee000000000000000000000000000000000003"
        monkeypatch.setenv("AIMARKET_X402_PAY_TO", OPERATOR)
        monkeypatch.setenv("AIMARKET_MARKET_FEE_TO", other)
        assert settle.fee_recipient() == other

    def test_a_two_payee_total_makes_no_single_payee_offer(self, monkeypatch):
        """price + fee is owed to two addresses; `exact` has one `payTo`."""
        monkeypatch.setenv("AIMARKET_X402_CHAIN", "base")
        monkeypatch.setenv("AIMARKET_X402_PAY_TO", OPERATOR)
        from aimarket_hub import x402
        assert x402.payment_requirements(PRICE, pay_to="") == []


class TestAFeeWithoutASplitterIsNotCharged:
    """A fee configured without a deployed splitter took the buyer's whole payment.

    `MarketSplitter` is the mechanism: it is the address the 402 names, and it pays the
    seller and the operator inside the one transaction the buyer sends. Its own header
    says it is NOT deployed by default — so an operator who sets AIMARKET_MARKET_FEE_BPS
    and AIMARKET_MARKET_FEE_TO, and stops there, is in the shipped state.

    In that state `offer_to = splitter_address() if bps else ""` was empty and
    `offer_to or pay_to` fell back to the SELLER. The offer then asked for the full gross
    at the seller's address, the buyer paid exactly that, and `verify_transfer` refused
    for a fee leg that was never sent: the buyer out the whole price, served nothing,
    holding a payment no invoice can redeem.
    """

    def _terms(self, monkeypatch, cap, **env):
        for k, v in env.items():
            if v is None:
                monkeypatch.delenv(k, raising=False)
            else:
                monkeypatch.setenv(k, v)
        return settle.terms_for(cap)

    def _cap(self, seller):
        return SimpleNamespace(
            capability_id="demo.echo@v1", product_id="demo-echo",
            price_per_call_usd=1.0, payout_address=seller, publisher_id="",
        )

    def test_the_offer_never_names_the_seller_for_the_gross_when_a_fee_is_set(self, monkeypatch):
        seller = "0x" + "99" * 20
        terms = self._terms(
            monkeypatch, self._cap(seller),
            AIMARKET_X402_ENABLED="1", AIMARKET_PAYMENT_CHAIN="base",
            AIMARKET_PAYMENT_TOKENS="USDC",
            AIMARKET_MARKET_FEE_BPS="250",
            AIMARKET_MARKET_FEE_TO="0x" + "11" * 20,
            AIMARKET_MARKET_SPLITTER=None,          # the shipped state
        )
        assert terms is not None
        # The fee is simply not taken, and the offer is the ordinary seller-direct one.
        assert terms.fee_units == 0
        assert terms.fee_to == ""
        assert terms.seller_units == terms.amount_units
        assert terms.offer_to.lower() == seller.lower()

    def test_with_a_splitter_the_offer_names_the_splitter(self, monkeypatch):
        seller, splitter = "0x" + "99" * 20, "0x" + "77" * 20
        terms = self._terms(
            monkeypatch, self._cap(seller),
            AIMARKET_X402_ENABLED="1", AIMARKET_PAYMENT_CHAIN="base",
            AIMARKET_PAYMENT_TOKENS="USDC",
            AIMARKET_MARKET_FEE_BPS="250",
            AIMARKET_MARKET_FEE_TO="0x" + "11" * 20,
            AIMARKET_MARKET_SPLITTER=splitter,
        )
        assert terms is not None
        assert terms.offer_to.lower() == splitter.lower()
        assert terms.fee_units > 0
        assert terms.seller_units + terms.fee_units == terms.amount_units


@pytest.mark.parametrize('mined_at,allowed', [(999,True),(1000,False),(1001,False)])
def test_expired_invoice_uses_actual_mining_time(monkeypatch, mined_at, allowed):
    fake_rpc_bound(monkeypatch, to=SELLER, units=20_000, nonce=NONCE)
    original=settle._rpc
    def rpc(url, method, params, timeout):
        if method=='eth_getBlockByNumber': return {'timestamp': hex(mined_at)}
        return original(url,method,params,timeout)
    monkeypatch.setattr(settle,'_rpc',rpc)
    terms=settle.PaymentTerms('base','USDC',USDC,6,SELLER,20_000,PRICE,1)
    args=dict(tx_hash=TX,terms=terms,require_nonce=NONCE,rpc_url='http://rpc.invalid',paid_before=1000)
    if allowed:
        assert settle.verify_transfer(**args)['paid_units']==20_000
    else:
        with pytest.raises(settle.PaymentError, match='after the invoice expired'):
            settle.verify_transfer(**args)


def test_matching_receipt_from_wrong_chain_is_rejected(monkeypatch):
    fake_rpc_bound(monkeypatch,to=SELLER,units=20_000,nonce=NONCE)
    original=settle._rpc
    def rpc(url,method,params,timeout):
        if method=='eth_chainId':return '0x1'
        return original(url,method,params,timeout)
    monkeypatch.setattr(settle,'_rpc',rpc)
    terms=settle.PaymentTerms('base','USDC',USDC,6,SELLER,20_000,PRICE,1)
    with pytest.raises(settle.PaymentError,match='invoice chain'):
        settle.verify_transfer(tx_hash=TX,terms=terms,require_nonce=NONCE,rpc_url='http://wrong.test')


def test_eighteen_decimal_price_rounding_is_exact():
    assert settle.to_units(.12345678912345678,18)==123456789123456780
    assert settle.to_units(.0000001,6)==1
