"""The credits rail as seen over HTTP — a fresh hub that can actually be paid.

The behaviour under test is the difference between a node with a P&L and a node without
one. Before the rail existed, `price = 0.0 if (sandbox_mode or not crypto_on)` meant every
default deployment served its whole priced catalogue for free, and the only alternative was
six configuration interlocks plus an escrow contract the operator had to deploy themselves.
"""
from __future__ import annotations

from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

from aimarket_hub.api import create_app
from aimarket_hub.config import HubConfig
from aimarket_hub.database import HubDatabase
from aimarket_hub.models import Capability
from aimarket_hub.signing import Signer

ADMIN_TOKEN = "test-admin-token-not-for-production"
ADMIN_HEADERS = {"Authorization": f"Bearer {ADMIN_TOKEN}"}


@contextmanager
def _hub(monkeypatch, tmp_path, **env):
    monkeypatch.setenv("AIMARKET_ADMIN_TOKEN", ADMIN_TOKEN)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    root = tmp_path / f"hub-{len(list(tmp_path.iterdir()))}"
    root.mkdir(parents=True, exist_ok=True)
    config = HubConfig()
    config.db_path = str(root / "hub.db")
    config.signing_key_path = str(root / "key")
    db = HubDatabase(root / "hub.db")
    app = create_app(config=config, db=db, signer=Signer(root / "key"))
    with TestClient(app) as client:
        yield client, db


def _list_priced_capability(db: HubDatabase, price: float = 0.004) -> None:
    """A local capability with a static pack, so the invoke needs no provider.

    A `prompt_template` holding a JSON object is the hub's zero-dependency execution path
    (`fulfillment.has_execution_path`) — and the only way a fresh deployment has anything
    of its own to sell at all.
    """
    db.upsert_capability(Capability(
        capability_id="demo.echo@v1",
        product_id="demo-echo",
        name="Echo",
        description="Returns what it is given",
        price_per_call_usd=price,
        source_hub="local",
        invoke_url="",
        prompt_template='{"answer": "echo", "ok": true}',
    ))


class TestPricedInvokeWithoutAChain:
    def test_priced_capability_is_free_when_no_rail_is_on(self, monkeypatch, tmp_path):
        """The shipped default, pinned so the change in behaviour is deliberate and visible."""
        with _hub(monkeypatch, tmp_path, AIMARKET_CREDITS_ENABLED="0") as (client, db):
            _list_priced_capability(db)
            r = client.post("/ai-market/v2/invoke", json={
                "product_id": "demo-echo", "capability_id": "demo.echo@v1",
                "input": {"text": "hi"}, "source_hub": "local",
            })
            assert r.status_code != 402

    def test_priced_capability_demands_payment_once_credits_are_on(self, monkeypatch, tmp_path):
        with _hub(monkeypatch, tmp_path, AIMARKET_CREDITS_ENABLED="1") as (client, db):
            _list_priced_capability(db)
            r = client.post("/ai-market/v2/invoke", json={
                "product_id": "demo-echo", "capability_id": "demo.echo@v1",
                "input": {"text": "hi"}, "source_hub": "local",
            })
            assert r.status_code == 402
            body = r.json()
            # A 402 must name a rail the caller can actually reach — the old text named
            # only X-Payment-Channel, which on a chainless hub is a dead end.
            assert "X-API-Key" in body["detail"]
            assert any(w["rail"] == "credits" for w in body["payment_ways"])

    def test_a_closed_signup_is_not_offered_as_the_way_in(self, monkeypatch, tmp_path):
        """With signup closed POST /accounts answers 403; naming it sent every buyer who
        hit the 402 to a door that refuses them."""
        with _hub(monkeypatch, tmp_path, AIMARKET_CREDITS_ENABLED="1",
                  AIMARKET_CREDITS_OPEN_SIGNUP="0") as (client, db):
            _list_priced_capability(db)
            r = client.post("/ai-market/v2/invoke", json={
                "product_id": "demo-echo", "capability_id": "demo.echo@v1",
                "input": {"text": "hi"}, "source_hub": "local",
            })
            assert r.status_code == 402
            detail = r.json()["detail"]
            assert "X-API-Key" in detail
            assert "/ai-market/v2/accounts" not in detail
            assert "operator" in detail

    def test_an_unknown_key_is_refused_rather_than_served_free(self, monkeypatch, tmp_path):
        with _hub(monkeypatch, tmp_path, AIMARKET_CREDITS_ENABLED="1") as (client, db):
            _list_priced_capability(db)
            r = client.post(
                "/ai-market/v2/invoke",
                json={"product_id": "demo-echo", "capability_id": "demo.echo@v1",
                      "input": {"text": "hi"}, "source_hub": "local"},
                headers={"X-API-Key": "aimk_wrong"},
            )
            assert r.status_code == 401
            assert r.json()["error"] == "invalid_api_key"

    def test_signup_then_paid_invoke_moves_money(self, monkeypatch, tmp_path):
        with _hub(
            monkeypatch, tmp_path,
            AIMARKET_CREDITS_ENABLED="1", AIMARKET_CREDITS_FREE_GRANT_USD="0.05",
        ) as (client, db):
            _list_priced_capability(db, price=0.004)

            signup = client.post("/ai-market/v2/accounts", json={"label": "buyer"})
            assert signup.status_code == 200
            key = signup.json()["api_key"]
            assert signup.json()["balance_usd"] == pytest.approx(0.05)

            r = client.post(
                "/ai-market/v2/invoke",
                json={"product_id": "demo-echo", "capability_id": "demo.echo@v1",
                      "input": {"text": "hi"}, "source_hub": "local"},
                headers={"X-API-Key": key},
            )
            assert r.status_code == 200, r.text

            account = client.get("/ai-market/v2/account", headers={"X-API-Key": key}).json()
            assert account["spent_usd"] == pytest.approx(0.004)
            assert account["balance_usd"] == pytest.approx(0.046)
            assert account["held_usd"] == pytest.approx(0.0)

    def test_an_empty_balance_cannot_buy(self, monkeypatch, tmp_path):
        with _hub(
            monkeypatch, tmp_path,
            AIMARKET_CREDITS_ENABLED="1", AIMARKET_CREDITS_FREE_GRANT_USD="0",
        ) as (client, db):
            _list_priced_capability(db, price=0.004)
            key = client.post("/ai-market/v2/accounts", json={}).json()["api_key"]
            r = client.post(
                "/ai-market/v2/invoke",
                json={"product_id": "demo-echo", "capability_id": "demo.echo@v1",
                      "input": {"text": "hi"}, "source_hub": "local"},
                headers={"X-API-Key": key},
            )
            assert r.status_code == 402
            assert "insufficient credit" in r.json()["detail"]

    def test_operator_top_up_is_admin_only(self, monkeypatch, tmp_path):
        with _hub(
            monkeypatch, tmp_path,
            AIMARKET_CREDITS_ENABLED="1", AIMARKET_CREDITS_FREE_GRANT_USD="0",
        ) as (client, db):
            signup = client.post("/ai-market/v2/accounts", json={}).json()
            acct, key = signup["account_id"], signup["api_key"]

            assert client.post(
                f"/ai-market/v2/accounts/{acct}/credit", json={"amount_usd": 5},
            ).status_code in (401, 403)

            ok = client.post(
                f"/ai-market/v2/accounts/{acct}/credit",
                json={"amount_usd": 5, "note": "invoice 1", "reference": "invoice-1"}, headers=ADMIN_HEADERS,
            )
            assert ok.status_code == 200
            assert ok.json()["balance_usd"] == pytest.approx(5.0)

            replay = client.post(
                f"/ai-market/v2/accounts/{acct}/credit",
                json={"amount_usd": 5, "reference": "invoice-1"}, headers=ADMIN_HEADERS,
            )
            assert replay.status_code == 200
            assert replay.json()["idempotent_replay"] is True
            assert replay.json()["balance_usd"] == pytest.approx(5.0)

            entries = client.get(
                "/ai-market/v2/account/ledger", headers={"X-API-Key": key},
            ).json()["entries"]
            assert any(e["kind"] == "grant" and e["note"] == "invoice 1" for e in entries)


class TestOperatorVisibility:
    def test_the_manifest_advertises_a_reachable_rail(self, monkeypatch, tmp_path):
        with _hub(monkeypatch, tmp_path, AIMARKET_CREDITS_ENABLED="1") as (client, _db):
            rails = client.get("/.well-known/ai-market.json").json()["payment_rails"]
            assert rails["credits"]["enabled"] is True
            assert rails["credits"]["header"] == "X-API-Key"
            # Sub-cent pricing is the point: the channel ledger cannot express it.
            assert rails["credits"]["min_unit_usd"] < 0.01

    def test_live_stats_separate_earnings_from_money_held(self, monkeypatch, tmp_path):
        with _hub(
            monkeypatch, tmp_path,
            AIMARKET_CREDITS_ENABLED="1", AIMARKET_CREDITS_FREE_GRANT_USD="0",
        ) as (client, db):
            _list_priced_capability(db, price=0.004)
            signup = client.post("/ai-market/v2/accounts", json={}).json()
            client.post(
                f"/ai-market/v2/accounts/{signup['account_id']}/credit",
                json={"amount_usd": 1.0}, headers=ADMIN_HEADERS,
            )
            client.post(
                "/ai-market/v2/invoke",
                json={"product_id": "demo-echo", "capability_id": "demo.echo@v1",
                      "input": {"text": "hi"}, "source_hub": "local"},
                headers={"X-API-Key": signup["api_key"]},
            )
            summary = client.get("/ai-market/v2/stats/live").json()["summary"]
            assert summary["credits"]["credits_earned_usd"] == pytest.approx(0.004)
            assert summary["credits"]["outstanding_credit_usd"] == pytest.approx(0.996)


class TestSignupDoor:
    def test_closed_signup_refuses_strangers_but_not_the_operator(self, monkeypatch, tmp_path):
        with _hub(
            monkeypatch, tmp_path,
            AIMARKET_CREDITS_ENABLED="1", AIMARKET_CREDITS_OPEN_SIGNUP="0",
        ) as (client, _db):
            assert client.post("/ai-market/v2/accounts", json={}).status_code == 403
            r = client.post(
                "/ai-market/v2/accounts", json={"grant_usd": 2.5}, headers=ADMIN_HEADERS,
            )
            assert r.status_code == 200
            assert r.json()["balance_usd"] == pytest.approx(2.5)

    def test_open_signup_is_rate_limited_per_address(self, monkeypatch, tmp_path):
        with _hub(
            monkeypatch, tmp_path,
            AIMARKET_CREDITS_ENABLED="1", AIMARKET_CREDITS_SIGNUPS_PER_HOUR="2",
        ) as (client, _db):
            assert client.post("/ai-market/v2/accounts", json={}).status_code == 200
            assert client.post("/ai-market/v2/accounts", json={}).status_code == 200
            assert client.post("/ai-market/v2/accounts", json={}).status_code == 429

    def test_a_signup_that_is_not_json_is_refused_and_spends_nothing(self, monkeypatch, tmp_path):
        """A body-less or form POST needs no CORS preflight, so any page a visitor opened
        could mint grant-bearing accounts from the visitor's address."""
        with _hub(
            monkeypatch, tmp_path,
            AIMARKET_CREDITS_ENABLED="1", AIMARKET_CREDITS_SIGNUPS_PER_HOUR="1",
        ) as (client, _db):
            assert client.post("/ai-market/v2/accounts").status_code == 415
            # a form body never reaches the handler (422); either way no account is minted
            assert client.post("/ai-market/v2/accounts", data={"label": "x"}).status_code in (415, 422)
            assert client.post("/ai-market/v2/accounts", content=b"{}",
                               headers={"Content-Type": "text/plain"}).status_code in (415, 422)
            # none of those used the address's one signup
            assert client.post("/ai-market/v2/accounts", json={}).status_code == 200

    def test_ipv6_signups_are_counted_per_48_not_per_address(self, monkeypatch, tmp_path):
        """A host is handed a /64 and a free tunnel a routed /48: rotating addresses inside
        one /48 is one actor, and gets one actor's ceiling."""
        with _hub(
            monkeypatch, tmp_path,
            AIMARKET_CREDITS_ENABLED="1", AIMARKET_CREDITS_SIGNUPS_PER_HOUR="2",
            AIMARKET_TRUSTED_PROXIES="testclient",
        ) as (client, _db):
            def signup(addr):
                return client.post("/ai-market/v2/accounts", json={},
                                   headers={"X-Forwarded-For": addr}).status_code
            assert signup("2001:db8:aa:1::1") == 200
            assert signup("2001:db8:aa:2::1") == 200     # another /64, same /48
            assert signup("2001:db8:aa:3::7") == 429
            assert signup("2001:db8:bb:1::1") == 200     # another /48 is another actor

    def test_accounts_are_off_when_the_rail_is_off(self, monkeypatch, tmp_path):
        with _hub(monkeypatch, tmp_path, AIMARKET_CREDITS_ENABLED="0") as (client, _db):
            assert client.post("/ai-market/v2/accounts", json={}).status_code == 503


def test_open_signup_grants_until_the_budget_is_spent(monkeypatch):
    """The door stays open at zero once the day's grant budget is gone."""
    import os
    import tempfile

    from fastapi.testclient import TestClient

    from aimarket_hub.api import create_app

    with tempfile.TemporaryDirectory() as tmp:
        monkeypatch.setenv("AIMARKET_DB_PATH", os.path.join(tmp, "hub.db"))
        monkeypatch.setenv("AIMARKET_CREDITS_ENABLED", "1")
        monkeypatch.setenv("AIMARKET_CREDITS_OPEN_SIGNUP", "1")
        monkeypatch.setenv("AIMARKET_SIGNUP_GRANT_USD", "0.05")
        monkeypatch.setenv("AIMARKET_SIGNUP_GRANT_DAILY_USD", "0.05")
        monkeypatch.setenv("AIMARKET_CREDITS_SIGNUPS_PER_HOUR", "50")
        with TestClient(create_app()) as client:
            first = client.post("/ai-market/v2/accounts", json={"label": "first"})
            assert first.status_code == 200
            assert first.json()["balance_usd"] == pytest.approx(0.05)
            assert "grant_note" not in first.json()

            second = client.post("/ai-market/v2/accounts", json={"label": "second"})
            assert second.status_code == 200
            body = second.json()
            # Still a usable account — just not a funded one.
            assert body["balance_usd"] == 0.0
            assert body["api_key"]
            assert "daily" in body["grant_note"]

            rails = client.get("/.well-known/ai-market.json").json()["payment_rails"]
            assert rails["credits"]["free_grant_usd"] == pytest.approx(0.05)


def test_grant_usd_is_refused_rather_than_ignored(monkeypatch):
    """A privileged field must never be silently dropped.

    This is the bug that hid a wrong admin token for a whole build: a caller
    asked for a zero-balance account, got the signup grant instead, and found
    out it was not admin only when it later tried to credit a paid buyer.
    """
    import os
    import tempfile

    from fastapi.testclient import TestClient

    from aimarket_hub.api import create_app

    with tempfile.TemporaryDirectory() as tmp:
        monkeypatch.setenv("AIMARKET_DB_PATH", os.path.join(tmp, "hub.db"))
        monkeypatch.setenv("AIMARKET_CREDITS_ENABLED", "1")
        monkeypatch.setenv("AIMARKET_CREDITS_OPEN_SIGNUP", "1")
        monkeypatch.setenv("AIMARKET_SIGNUP_GRANT_USD", "0.05")
        monkeypatch.setenv("AIMARKET_SIGNUP_GRANT_DAILY_USD", "10")
        monkeypatch.setenv("AIMARKET_CREDITS_SIGNUPS_PER_HOUR", "50")
        monkeypatch.setenv("AIMARKET_ADMIN_TOKEN", "a" * 40)
        with TestClient(create_app()) as client:
            refused = client.post("/ai-market/v2/accounts", json={"label": "x", "grant_usd": 0})
            assert refused.status_code == 403
            assert "operator-only" in refused.json()["detail"]

            # A wrong bearer is no better than none.
            wrong = client.post(
                "/ai-market/v2/accounts",
                json={"label": "x", "grant_usd": 0},
                headers={"Authorization": "Bearer " + "b" * 40},
            )
            assert wrong.status_code == 403

            # Asking for nothing still works and still gets the advertised grant.
            plain = client.post("/ai-market/v2/accounts", json={"label": "x"})
            assert plain.status_code == 200
            assert plain.json()["balance_usd"] == pytest.approx(0.05)

            # The operator keeps full control of the opening balance.
            admin = client.post(
                "/ai-market/v2/accounts",
                json={"label": "enterprise", "grant_usd": 25},
                headers={"Authorization": "Bearer " + "a" * 40},
            )
            assert admin.status_code == 200
            assert admin.json()["balance_usd"] == pytest.approx(25.0)


def test_only_admin_may_move_money_into_an_account(monkeypatch):
    """/credit is the boundary the wrong token finally hit. Pin it."""
    import os
    import tempfile

    from fastapi.testclient import TestClient

    from aimarket_hub.api import create_app

    with tempfile.TemporaryDirectory() as tmp:
        monkeypatch.setenv("AIMARKET_DB_PATH", os.path.join(tmp, "hub.db"))
        monkeypatch.setenv("AIMARKET_CREDITS_ENABLED", "1")
        monkeypatch.setenv("AIMARKET_CREDITS_OPEN_SIGNUP", "1")
        monkeypatch.setenv("AIMARKET_CREDITS_SIGNUPS_PER_HOUR", "50")
        monkeypatch.setenv("AIMARKET_SIGNUP_GRANT_USD", "0")
        monkeypatch.setenv("AIMARKET_ADMIN_TOKEN", "a" * 40)
        with TestClient(create_app()) as client:
            account = client.post("/ai-market/v2/accounts", json={"label": "buyer"}).json()
            assert account["balance_usd"] == 0.0
            body = {"amount_usd": 5, "reference": "probe-1"}

            assert client.post(f"/ai-market/v2/accounts/{account['account_id']}/credit",
                               json=body).status_code in (401, 403)
            assert client.post(f"/ai-market/v2/accounts/{account['account_id']}/credit", json=body,
                               headers={"Authorization": "Bearer " + "b" * 40}).status_code == 403

            credited = client.post(
                f"/ai-market/v2/accounts/{account['account_id']}/credit", json=body,
                headers={"Authorization": "Bearer " + "a" * 40})
            assert credited.status_code == 200
            assert credited.json()["balance_usd"] == pytest.approx(5.0)


class TestOneCallIsChargedOnce:
    """A call paid on chain must not also be charged on a ledger rail.

    The 402 advertises every rail the hub can take (`_payment_ways`), and an HTTP client
    that answers with `X-Payment` keeps sending its standing `X-API-Key` on the same
    request — that is what a client library does. Both rails then fired: USDC moved to the
    seller on chain AND the full list price was held and captured from prepaid credits.
    The ledger leg has no refund path, so the second charge was permanent.

    The same request shape reached three `return`s between the settlement and the try that
    owns the release, each of which left the on-chain claim consumed for a call nobody ran.
    """

    def _settled(self, monkeypatch, *, price: float):
        """Make the on-chain verifier answer 'this transfer is good' without a chain."""
        from aimarket_hub import settle

        def _verify(*, tx_hash, terms, timeout=10.0, max_age_s=0, paid_before=None,
                    require_nonce, rpc_url=""):
            return {
                "tx_hash": tx_hash,
                "paid_units": settle.to_units(price, terms.decimals),
                "authorizer": "0x" + "ab" * 20,
            }

        monkeypatch.setattr(settle, "verify_transfer", _verify)

    def test_paying_on_chain_does_not_also_spend_credits(self, monkeypatch, tmp_path):
        price = 0.004
        with _hub(
            monkeypatch, tmp_path,
            AIMARKET_CREDITS_ENABLED="1",
            AIMARKET_X402_ACCEPT="1",
            AIFACTORY_CRYPTO_ENABLED="1",
            AIMARKET_PAYMENT_RECIPIENT="0x" + "cd" * 20,
        ) as (client, db):
            db.upsert_capability(Capability(
                capability_id="demo.echo@v1", product_id="demo-echo", name="Echo",
                description="Returns what it is given", price_per_call_usd=price,
                source_hub="local", invoke_url="",
                prompt_template='{"answer": "echo", "ok": true}',
                payout_address="0x" + "cd" * 20,
            ))
            self._settled(monkeypatch, price=price)

            signup = client.post("/ai-market/v2/accounts", json={}).json()
            acct, key = signup["account_id"], signup["api_key"]
            client.post(f"/ai-market/v2/accounts/{acct}/credit", json={"amount_usd": 5},
                        headers=ADMIN_HEADERS)
            before = client.get("/ai-market/v2/account", headers={"X-API-Key": key}).json()

            body = {
                "product_id": "demo-echo", "capability_id": "demo.echo@v1",
                "input": {"text": "hi"}, "source_hub": "local",
            }
            # Step one: quote. Anonymous, because a client holding credits is simply
            # served from them — the 402 that mints the nonce is the one a caller gets
            # before it has identified itself.
            quote = client.post("/ai-market/v2/invoke", json=body)
            assert quote.status_code == 402, quote.text
            nonce, secret = quote.json()["nonce"], quote.json()["payment_secret"]

            # Step two: it pays the seller on chain and retries. The key is still there.
            r = client.post("/ai-market/v2/invoke", json=body, headers={
                "X-API-Key": key,                       # rides along, as clients do
                "X-Payment": "0x" + "11" * 32,          # and the call is paid on chain
                "X-Payment-Nonce": nonce,
                "X-Payment-Secret": secret,             # that it is the one who paid
            })
            assert r.status_code == 200, r.text

            after = client.get("/ai-market/v2/account", headers={"X-API-Key": key}).json()
            assert after["balance_usd"] == before["balance_usd"], (
                "the call was paid on chain and the credits rail charged for it as well"
            )
            assert after.get("held_usd", 0) == 0, "a hold survived a delivered call"

    def test_a_refused_call_leaves_the_payment_redeemable(self, monkeypatch, tmp_path):
        """A buyer who paid and was then refused must not lose the payment.

        `_settle_market_payment` burns both replay keys the moment the receipt verifies,
        and the refusals that follow it — a short input, a bad verification plan, a
        provider 502 — returned without giving anything back. The money is with the seller
        and cannot come back; what CAN come back is the claim, so the same payment buys
        the retry instead of being consumed for nothing.
        """
        price = 0.004
        with _hub(
            monkeypatch, tmp_path,
            AIMARKET_CREDITS_ENABLED="0",
            AIMARKET_X402_ACCEPT="1",
            AIFACTORY_CRYPTO_ENABLED="1",
            AIMARKET_PAYMENT_RECIPIENT="0x" + "cd" * 20,
        ) as (client, db):
            db.upsert_capability(Capability(
                capability_id="demo.echo@v1", product_id="demo-echo", name="Echo",
                description="Returns what it is given", price_per_call_usd=price,
                source_hub="local", invoke_url="",
                prompt_template='{"answer": "echo", "ok": true}',
                payout_address="0x" + "cd" * 20,
                input_schema={"type": "object", "required": ["text"],
                              "properties": {"text": {"type": "string"}}},
            ))
            self._settled(monkeypatch, price=price)

            short_body = {"product_id": "demo-echo", "capability_id": "demo.echo@v1",
                          "input": {}, "source_hub": "local"}
            quote = client.post("/ai-market/v2/invoke", json=short_body)
            assert quote.status_code == 402, quote.text
            nonce, tx = quote.json()["nonce"], "0x" + "22" * 32
            paid = {"X-Payment": tx, "X-Payment-Nonce": nonce,
                    "X-Payment-Secret": quote.json()["payment_secret"]}

            # Paid, then refused for a reason that has nothing to do with the payment.
            refused = client.post("/ai-market/v2/invoke", json=short_body, headers=paid)
            assert refused.status_code == 400, refused.text

            # The same money must still buy the call it paid for.
            retry = client.post("/ai-market/v2/invoke", headers=paid, json={
                **short_body, "input": {"text": "hi"},
            })
            assert retry.status_code == 200, (
                "the refusal consumed the payment: the buyer paid and can never redeem it"
            )


class TestCollateralCanLeaveTheHub:
    """Posted stake had no way out, and a failed stake kept the money.

    `POST /supply/stake` moves a publisher's credits from spendable balance into
    `collateral_mc`. Nothing in the stack knows how to release it — `supply_security` and
    `database` have `supply_stake_add`, `_get` and `_slash` and no unstake — and the only
    caller of `return_collateral` was the compensation on a stake the LEDGER refused,
    which catches `ValueError` alone. Every other way `supply_security.stake` can fail —
    it writes three rows — took the money and recorded no stake.
    """

    def _staked(self, client, tmp_path, monkeypatch):
        signup = client.post("/ai-market/v2/accounts", json={}).json()
        acct, key = signup["account_id"], signup["api_key"]
        client.post(f"/ai-market/v2/accounts/{acct}/credit", json={"amount_usd": 100},
                    headers=ADMIN_HEADERS)
        return acct, key

    def test_the_operator_can_return_posted_collateral(self, monkeypatch, tmp_path):
        with _hub(monkeypatch, tmp_path, AIMARKET_CREDITS_ENABLED="1") as (client, db):
            acct, key = self._staked(client, tmp_path, monkeypatch)
            from aimarket_hub import credits as credits_mod

            ledger = credits_mod.ledger()
            ledger.debit(acct, 25.0, receipt_id="stake_test", note="supply stake",
                         as_collateral=True)
            before = client.get("/ai-market/v2/account", headers={"X-API-Key": key}).json()

            r = client.post(f"/ai-market/v2/accounts/{acct}/collateral/return",
                            json={"amount_usd": 25.0, "note": "unstaked"},
                            headers=ADMIN_HEADERS)
            assert r.status_code == 200, r.text
            after = client.get("/ai-market/v2/account", headers={"X-API-Key": key}).json()
            assert round(after["balance_usd"] - before["balance_usd"], 6) == 25.0, (
                "the stake never came back"
            )
            assert round(float(after.get("collateral_usd") or 0), 6) == 0.0

    def test_returning_more_than_was_posted_is_refused(self, monkeypatch, tmp_path):
        """`return_collateral` floors collateral at zero and credits the balance anyway."""
        with _hub(monkeypatch, tmp_path, AIMARKET_CREDITS_ENABLED="1") as (client, db):
            acct, key = self._staked(client, tmp_path, monkeypatch)
            from aimarket_hub import credits as credits_mod

            credits_mod.ledger().debit(acct, 25.0, receipt_id="stake_test",
                                       note="supply stake", as_collateral=True)
            before = client.get("/ai-market/v2/account", headers={"X-API-Key": key}).json()
            r = client.post(f"/ai-market/v2/accounts/{acct}/collateral/return",
                            json={"amount_usd": 500.0}, headers=ADMIN_HEADERS)
            assert r.status_code == 400
            after = client.get("/ai-market/v2/account", headers={"X-API-Key": key}).json()
            assert after["balance_usd"] == before["balance_usd"], "a typo minted money"

    def test_it_is_operator_only(self, monkeypatch, tmp_path):
        with _hub(monkeypatch, tmp_path, AIMARKET_CREDITS_ENABLED="1") as (client, db):
            acct, key = self._staked(client, tmp_path, monkeypatch)
            r = client.post(f"/ai-market/v2/accounts/{acct}/collateral/return",
                            json={"amount_usd": 1.0}, headers={"X-API-Key": key})
            assert r.status_code in (401, 403)


class TestACreditLineBuysOnlyTheOperatorsOwnResources:
    """A granted limit must not pay a stranger.

    The credit line is the operator's own money: taken in once, issued as a limit, and
    mostly granted outright so a new project can try the catalogue for free. Spending it
    on a listing whose seller has to be paid for real means the operator pays that seller
    in USDC, out of pocket, for a call the buyer got as a gift — and `_pay_publisher_share`
    cannot even record the obligation, because a wallet is not a credit account, so the
    share was silently dropped and the operator kept 100% of somebody else's sale.
    """

    def _wallet_listing(self, db, *, payout: str, price: float = 0.004):
        db.upsert_capability(Capability(
            capability_id="demo.echo@v1", product_id="demo-echo", name="Echo",
            description="Returns what it is given", price_per_call_usd=price,
            source_hub="local", invoke_url="",
            prompt_template='{"answer": "echo", "ok": true}',
            payout_address=payout,
        ))

    def _funded_key(self, client) -> str:
        signup = client.post("/ai-market/v2/accounts", json={}).json()
        client.post(f"/ai-market/v2/accounts/{signup['account_id']}/credit",
                    json={"amount_usd": 10}, headers=ADMIN_HEADERS)
        return signup["api_key"]

    def test_credits_cannot_buy_a_listing_that_pays_someone_else(self, monkeypatch, tmp_path):
        with _hub(monkeypatch, tmp_path, AIMARKET_CREDITS_ENABLED="1",
                  AIFACTORY_CRYPTO_ENABLED="1",
                  AIMARKET_PAYMENT_RECIPIENT="0x" + "11" * 20) as (client, db):
            self._wallet_listing(db, payout="0x" + "99" * 20)     # somebody else
            key = self._funded_key(client)
            r = client.post("/ai-market/v2/invoke", json={
                "product_id": "demo-echo", "capability_id": "demo.echo@v1",
                "input": {"text": "hi"}, "source_hub": "local",
            }, headers={"X-API-Key": key})
            assert r.status_code == 402, r.text
            body = r.json()
            assert "pays its seller directly" in body["detail"]
            # And it must not advertise the rail it just refused.
            assert not any(w["rail"] == "credits" for w in body["payment_ways"])
            assert any(w["rail"] == "seller_direct" for w in body["payment_ways"])

    def test_the_buyer_is_not_charged_for_the_refusal(self, monkeypatch, tmp_path):
        with _hub(monkeypatch, tmp_path, AIMARKET_CREDITS_ENABLED="1",
                  AIFACTORY_CRYPTO_ENABLED="1",
                  AIMARKET_PAYMENT_RECIPIENT="0x" + "11" * 20) as (client, db):
            self._wallet_listing(db, payout="0x" + "99" * 20)
            key = self._funded_key(client)
            before = client.get("/ai-market/v2/account", headers={"X-API-Key": key}).json()
            client.post("/ai-market/v2/invoke", json={
                "product_id": "demo-echo", "capability_id": "demo.echo@v1",
                "input": {"text": "hi"}, "source_hub": "local",
            }, headers={"X-API-Key": key})
            after = client.get("/ai-market/v2/account", headers={"X-API-Key": key}).json()
            assert after["balance_usd"] == before["balance_usd"]
            assert float(after.get("held_usd") or 0) == 0.0

    def test_the_operators_own_listing_is_still_bought_with_credits(self, monkeypatch, tmp_path):
        """The payee being the operator's own recipient is the operator selling their work."""
        own = "0x" + "11" * 20
        with _hub(monkeypatch, tmp_path, AIMARKET_CREDITS_ENABLED="1",
                  AIFACTORY_CRYPTO_ENABLED="1",
                  AIMARKET_PAYMENT_RECIPIENT=own) as (client, db):
            self._wallet_listing(db, payout=own)
            key = self._funded_key(client)
            r = client.post("/ai-market/v2/invoke", json={
                "product_id": "demo-echo", "capability_id": "demo.echo@v1",
                "input": {"text": "hi"}, "source_hub": "local",
            }, headers={"X-API-Key": key})
            assert r.status_code == 200, r.text

    def test_a_listing_with_no_external_payee_is_unaffected(self, monkeypatch, tmp_path):
        with _hub(monkeypatch, tmp_path, AIMARKET_CREDITS_ENABLED="1") as (client, db):
            _list_priced_capability(db)                            # no payout_address
            key = self._funded_key(client)
            r = client.post("/ai-market/v2/invoke", json={
                "product_id": "demo-echo", "capability_id": "demo.echo@v1",
                "input": {"text": "hi"}, "source_hub": "local",
            }, headers={"X-API-Key": key})
            assert r.status_code == 200, r.text


class TestAShortRequestFreezesNothing:
    """An invoke that left out a required field is answered 400 AFTER its price was held.

    That order is deliberate (see `_refuse_incomplete_input`: payment first, so x402 clients
    see a 402 before a 400), and the refusal returns above the `finally` that releases the
    reservation. It gave back the on-chain claim but not the ledger hold, so a credit buyer
    who forgot a field had the price held — neither captured nor returned — for good. Found
    by the A2A bridge's "missing input, then resume" flow.
    """

    def test_the_hold_is_released_and_the_complete_call_is_charged_once(self, monkeypatch, tmp_path):
        with _hub(monkeypatch, tmp_path, AIMARKET_CREDITS_ENABLED="1") as (client, db):
            db.upsert_capability(Capability(
                capability_id="demo.echo@v1", product_id="demo-echo", name="Echo",
                description="static", price_per_call_usd=0.004, source_hub="local", invoke_url="",
                prompt_template='{"answer": "echo"}',
                input_schema={"type": "object", "required": ["text"],
                              "properties": {"text": {"type": "string"}}},
            ))
            signup = client.post("/ai-market/v2/accounts", json={}).json()
            acct, key = signup["account_id"], signup["api_key"]
            client.post(f"/ai-market/v2/accounts/{acct}/credit", json={"amount_usd": 1},
                        headers=ADMIN_HEADERS)
            before = client.get("/ai-market/v2/account", headers={"X-API-Key": key}).json()
            body = {"product_id": "demo-echo", "capability_id": "demo.echo@v1", "source_hub": "local"}

            short = client.post("/ai-market/v2/invoke", json={**body, "input": {}},
                                headers={"X-API-Key": key})
            assert short.status_code == 400 and short.json()["error"] == "incomplete_input"
            after_short = client.get("/ai-market/v2/account", headers={"X-API-Key": key}).json()
            assert float(after_short.get("held_usd") or 0) == 0.0, "the refused call kept its price held"
            assert after_short["balance_usd"] == before["balance_usd"]

            ok = client.post("/ai-market/v2/invoke", json={**body, "input": {"text": "hi"}},
                             headers={"X-API-Key": key})
            assert ok.status_code == 200, ok.text
            after = client.get("/ai-market/v2/account", headers={"X-API-Key": key}).json()
            assert after["balance_usd"] == pytest.approx(before["balance_usd"] - 0.004)
            assert float(after.get("held_usd") or 0) == 0.0


def test_a_holder_rotates_a_leaked_key_without_the_operator(monkeypatch, tmp_path):
    """A key in a URL, a log or a shared notebook could only be ended by the operator
    disabling the whole account. The holder now replaces it; the old one dies at once."""
    with _hub(monkeypatch, tmp_path, AIMARKET_CREDITS_ENABLED="1") as (client, _db):
        opened = client.post("/ai-market/v2/accounts", json={}).json()
        old = opened["api_key"]
        rotated = client.post("/ai-market/v2/account/rotate-key", headers={"X-API-Key": old})
        assert rotated.status_code == 200
        new = rotated.json()["api_key"]
        assert new != old and rotated.json()["account_id"] == opened["account_id"]
        assert client.get("/ai-market/v2/account", headers={"X-API-Key": old}).status_code == 401
        assert client.get("/ai-market/v2/account", headers={"X-API-Key": new}).status_code == 200
        assert client.post("/ai-market/v2/account/rotate-key", headers={"X-API-Key": old}).status_code == 401


def test_free_studio_runs_are_bounded_per_address(monkeypatch, tmp_path):
    with _hub(monkeypatch, tmp_path, AIMARKET_STUDIO_RUNS_PER_HOUR="2") as (client, _db):
        body = {"nodes": [{"id": "n1", "product_id": "pp", "capability_id": "cc"}]}
        codes = [client.post("/studio/run", json=body).status_code for _ in range(3)]
        assert codes[-1] == 429
        assert 429 not in codes[:2]
