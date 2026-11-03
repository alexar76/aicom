"""A stranger can list a capability and post collateral without the operator's help.

Two blockers used to stand in the way, and together they meant the community publish flow
the docs describe had never been walked by anyone but the operator:

  1. **Identity was an env var.** The only publisher credential was
     `AIMARKET_PUBLISHER_TOKENS`, parsed once at app construction — one new publisher meant
     editing .env and restarting the hub.
  2. **Collateral needed a chain the image cannot reach.** In production every stake credit
     had to be backed by an on-chain deposit verified through a module the hub wheel and
     Docker image do not ship, so the gate could not be satisfied at all; the only way past
     was `AIMARKET_SUPPLY_SECURITY_RELAXED=1`, which removes the collateral requirement
     entirely rather than satisfying it.

A credit account answers both: it is a self-serve authenticated identity, and its balance is
money the operator already holds and can slash.
"""
from __future__ import annotations

from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

from aimarket_hub.api import create_app
from aimarket_hub.config import HubConfig
from aimarket_hub.database import HubDatabase
from aimarket_hub.signing import Signer

ADMIN_TOKEN = "test-admin-token-not-for-production"
ADMIN_HEADERS = {"Authorization": f"Bearer {ADMIN_TOKEN}"}


@contextmanager
def _hub(monkeypatch, tmp_path, **env):
    monkeypatch.setenv("AIMARKET_ADMIN_TOKEN", ADMIN_TOKEN)
    monkeypatch.setenv("AIMARKET_CREDITS_ENABLED", "1")
    monkeypatch.setenv("AIMARKET_ORACLE_FAMILY_URL", "off")
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    import aimarket_hub.crawler as crawler

    # Publishing tests exercise identity, stake, and payout. They must not turn
    # example.com's DNS availability into an unrelated test prerequisite.
    monkeypatch.setattr(
        crawler, "_url_is_safe", lambda url: url == "https://example.com/invoke"
    )
    root = tmp_path / f"hub-{len(list(tmp_path.iterdir()))}"
    root.mkdir(parents=True, exist_ok=True)
    config = HubConfig()
    config.db_path = str(root / "hub.db")
    config.signing_key_path = str(root / "key")
    app = create_app(config=config, db=HubDatabase(root / "hub.db"), signer=Signer(root / "key"))
    with TestClient(app) as client:
        yield client


def _account(client, funded_usd: float = 0.0) -> tuple[str, str]:
    signup = client.post("/ai-market/v2/accounts", json={"label": "publisher"}).json()
    if funded_usd:
        client.post(
            f"/ai-market/v2/accounts/{signup['account_id']}/credit",
            json={"amount_usd": funded_usd}, headers=ADMIN_HEADERS,
        )
    return signup["account_id"], signup["api_key"]


def _manifest(publisher_id: str = "") -> dict:
    body = {
        "product_id": "my-service",
        "capability_id": "my.service@v1",
        "name": "My service",
        "description": "Something the publisher actually runs",
        "invoke_url": "https://example.com/invoke",
        "price_per_call_usd": 0.01,
        "input_schema": {"type": "object"},
        "output_schema": {"type": "object"},
    }
    if publisher_id:
        body["publisher_id"] = publisher_id
    return body


class TestStakeFromCredits:
    def test_policy_is_public_but_account_balances_are_private(self, monkeypatch, tmp_path):
        with _hub(monkeypatch, tmp_path, AIMARKET_SUPPLY_MIN_STAKE_USD="17.5",
                  AIMARKET_SUPPLY_PRODUCT_ALLOWLIST="allowed-service") as client:
            acct, key = _account(client, funded_usd=30.0)
            public = client.get("/ai-market/v2/supply/policy")
            assert public.status_code == 200
            assert public.headers["cache-control"] == "no-store"
            assert public.json()["min_stake_usd"] == 17.5
            assert public.json()["product_allowlist"] == ["allowed-service"]
            assert "balance_usd" not in public.json()
            assert "publisher_id" not in public.json()
            for invalid in ("", "invalid-key"):
                assert client.get("/ai-market/v2/supply/policy",
                                  headers={"X-API-Key": invalid}).status_code == 401
            mine = client.get("/ai-market/v2/supply/policy", headers={"X-API-Key": key})
            assert mine.json()["publisher_id"] == acct
            assert mine.json()["additional_stake_usd"] == 17.5
            assert mine.json()["collateral_usd"] == 0
            assert mine.headers["cache-control"] == "no-store"

    def test_a_key_can_post_its_own_collateral(self, monkeypatch, tmp_path):
        with _hub(monkeypatch, tmp_path, AIMARKET_CREDITS_FREE_GRANT_USD="0") as client:
            acct, key = _account(client, funded_usd=30.0)
            r = client.post(
                "/ai-market/v2/supply/stake",
                json={"amount_usd": 25.0}, headers={"X-API-Key": key},
            )
            assert r.status_code == 200, r.text
            assert r.json()["stake_usd"] == pytest.approx(25.0)
            assert r.json()["collateral"] == "credits"
            # The money really left the spendable balance.
            balance = client.get("/ai-market/v2/account", headers={"X-API-Key": key}).json()
            assert balance["balance_usd"] == pytest.approx(5.0)

    def test_collateral_it_cannot_afford_is_refused(self, monkeypatch, tmp_path):
        with _hub(monkeypatch, tmp_path, AIMARKET_CREDITS_FREE_GRANT_USD="0") as client:
            _acct, key = _account(client, funded_usd=1.0)
            r = client.post(
                "/ai-market/v2/supply/stake",
                json={"amount_usd": 25.0}, headers={"X-API-Key": key},
            )
            assert r.status_code == 402
            assert "insufficient credit" in r.json()["detail"]

    def test_a_key_cannot_stake_for_somebody_else(self, monkeypatch, tmp_path):
        with _hub(monkeypatch, tmp_path) as client:
            _acct, key = _account(client, funded_usd=30.0)
            r = client.post(
                "/ai-market/v2/supply/stake",
                json={"publisher_id": "someone-else", "amount_usd": 5.0},
                headers={"X-API-Key": key},
            )
            assert r.status_code == 403

    def test_production_no_longer_needs_a_chain(self, monkeypatch, tmp_path):
        """The case that was impossible: prod, no relaxed flag, no on-chain verifier."""
        with _hub(
            monkeypatch, tmp_path,
            AIFACTORY_PROD="1", AIMARKET_CREDITS_FREE_GRANT_USD="0",
        ) as client:
            _acct, key = _account(client, funded_usd=30.0)
            r = client.post(
                "/ai-market/v2/supply/stake",
                json={"amount_usd": 25.0}, headers={"X-API-Key": key},
            )
            assert r.status_code == 200, r.text
            assert r.json()["stake_usd"] == pytest.approx(25.0)

    def test_the_old_bearer_path_still_needs_a_tx_hash_in_production(self, monkeypatch, tmp_path):
        """Nothing about the on-chain rail is loosened by the new one existing."""
        with _hub(
            monkeypatch, tmp_path,
            AIFACTORY_PROD="1", AIMARKET_PUBLISHER_TOKENS="pub-a:secretA",
        ) as client:
            r = client.post(
                "/ai-market/v2/supply/stake",
                json={"publisher_id": "pub-a", "amount_usd": 25.0},
                headers={"Authorization": "Bearer secretA"},
            )
            assert r.status_code == 400
            assert "tx_hash required" in r.json()["detail"]


class TestSelfServePublish:
    def test_a_key_publishes_as_itself(self, monkeypatch, tmp_path):
        with _hub(monkeypatch, tmp_path, AIMARKET_SUPPLY_MIN_STAKE_USD="0") as client:
            acct, key = _account(client)
            r = client.post(
                "/ai-market/v2/supply/register",
                json=_manifest(), headers={"X-API-Key": key},
            )
            assert r.status_code == 200, r.text
            assert r.json()["publisher_id"] == acct
            # And the catalogue really carries it.
            found = client.get("/ai-market/v2/search?q=service").json()["matches"]
            assert any(m["capability_id"] == "my.service@v1" for m in found)

    def test_a_key_cannot_publish_as_somebody_else(self, monkeypatch, tmp_path):
        with _hub(monkeypatch, tmp_path, AIMARKET_SUPPLY_MIN_STAKE_USD="0") as client:
            _acct, key = _account(client)
            r = client.post(
                "/ai-market/v2/supply/register",
                json=_manifest("a-rival-publisher"), headers={"X-API-Key": key},
            )
            assert r.status_code == 403

    def test_publishing_without_any_credential_is_still_refused(self, monkeypatch, tmp_path):
        with _hub(
            monkeypatch, tmp_path,
            AIMARKET_SUPPLY_MIN_STAKE_USD="0", AIMARKET_PUBLISHER_TOKENS="pub-a:secretA",
        ) as client:
            r = client.post("/ai-market/v2/supply/register", json=_manifest("pub-a"))
            assert r.status_code in (401, 403)

    def test_stake_then_publish_end_to_end(self, monkeypatch, tmp_path):
        """The documented community flow, walked by a stranger with no operator action
        beyond funding the account."""
        with _hub(
            monkeypatch, tmp_path,
            AIMARKET_SUPPLY_MIN_STAKE_USD="25", AIMARKET_CREDITS_FREE_GRANT_USD="0",
        ) as client:
            acct, key = _account(client, funded_usd=30.0)

            refused = client.post(
                "/ai-market/v2/supply/register", json=_manifest(), headers={"X-API-Key": key},
            )
            assert refused.status_code == 400
            assert "stake" in str(refused.json()["detail"]).lower()

            policy = client.get("/ai-market/v2/supply/policy", headers={"X-API-Key": key}).json()
            assert policy["additional_stake_usd"] == 25.0
            assert policy["requires_mandate"] is False
            before_balance = policy["balance_usd"]

            staked = client.post(
                "/ai-market/v2/supply/stake",
                json={"amount_usd": str(policy["additional_stake_usd"])}, headers={"X-API-Key": key},
            )
            assert staked.status_code == 200, staked.text

            after = client.get("/ai-market/v2/supply/policy", headers={"X-API-Key": key}).json()
            assert after["additional_stake_usd"] == 0
            assert after["stake_usd"] == after["collateral_usd"] == 25.0
            assert after["balance_usd"] == pytest.approx(before_balance - 25.0)

            ok = client.post(
                "/ai-market/v2/supply/register", json=_manifest(), headers={"X-API-Key": key},
            )
            assert ok.status_code == 200, ok.text
            assert ok.json()["publisher_id"] == acct


class TestSellersGetPaid:
    """The other half of a two-sided market: a publisher who is invoked earns money.

    Before this the hub had no seller-earnings route at all — `channels` states that nothing
    in it can send value, the only obligations table refunds depositors rather than
    providers, and the single rev-share design in the tree was imported by nothing but its
    own tests. A seller could list, be invoked, and still have to ask the operator to wire
    them a tenth of a cent by hand.
    """

    def _published(self, client, key, price=0.01):
        """The real seller shape: a manifest pointing at a service the seller runs."""
        return client.post(
            "/ai-market/v2/supply/register", headers={"X-API-Key": key}, json={
                "product_id": "seller-pack", "capability_id": "seller.pack@v1",
                "name": "Seller pack", "description": "a service the seller operates",
                "invoke_url": "https://example.com/invoke",
                "price_per_call_usd": price,
                "input_schema": {"type": "object"}, "output_schema": {"type": "object"},
            },
        )

    @staticmethod
    def _provider_answers(monkeypatch, ok: bool = True):
        """Stand in for the seller's own server."""
        import aimarket_hub.outbound_http as outbound

        class _Resp:
            status_code = 200 if ok else 500
            headers: dict[str, str] = {"content-type": "application/json"}
            text = '{"success": true}'

            @staticmethod
            def json():
                return {"success": ok, "result": {"answer": "from the seller"}}

        async def _post(url, **_kwargs):
            return _Resp()

        monkeypatch.setattr(outbound, "safe_post", _post)

    def _buy(self, client, key):
        return client.post(
            "/ai-market/v2/invoke", headers={"X-API-Key": key},
            json={"product_id": "seller-pack", "capability_id": "seller.pack@v1",
                  "input": {}, "source_hub": "local"},
        )

    def test_a_sale_splits_between_seller_and_operator(self, monkeypatch, tmp_path):
        with _hub(
            monkeypatch, tmp_path,
            AIMARKET_SUPPLY_MIN_STAKE_USD="0", AIMARKET_CREDITS_FREE_GRANT_USD="0",
            AIMARKET_PUBLISHER_SHARE_BPS="7000",
        ) as client:
            seller_acct, seller_key = _account(client)
            published = self._published(client, seller_key, price=0.01)
            assert published.status_code == 200, published.text
            self._provider_answers(monkeypatch)

            _buyer_acct, buyer_key = _account(client, funded_usd=1.0)
            bought = self._buy(client, buyer_key)
            assert bought.status_code == 200, bought.text

            seller = client.get(
                "/ai-market/v2/account", headers={"X-API-Key": seller_key},
            ).json()
            assert seller["balance_usd"] == pytest.approx(0.007)

            summary = client.get("/ai-market/v2/stats/live").json()["summary"]["credits"]
            assert summary["credits_earned_usd"] == pytest.approx(0.01)   # gross
            assert summary["publisher_payouts_usd"] == pytest.approx(0.007)
            assert summary["operator_net_usd"] == pytest.approx(0.003)    # the 30%

    def test_the_seller_can_spend_what_they_earned(self, monkeypatch, tmp_path):
        """Earnings are a real balance on the same rail, not a number in a report."""
        with _hub(
            monkeypatch, tmp_path,
            AIMARKET_SUPPLY_MIN_STAKE_USD="0", AIMARKET_CREDITS_FREE_GRANT_USD="0",
        ) as client:
            _seller_acct, seller_key = _account(client)
            self._published(client, seller_key, price=0.01)
            self._provider_answers(monkeypatch)
            _b, buyer_key = _account(client, funded_usd=1.0)
            for _ in range(3):
                assert self._buy(client, buyer_key).status_code == 200
            # The seller now buys their own capability with money they earned: 3 x $0.007
            # is more than the $0.01 it costs.
            assert self._buy(client, seller_key).status_code == 200

    def test_a_failed_call_pays_nobody(self, monkeypatch, tmp_path):
        with _hub(
            monkeypatch, tmp_path,
            AIMARKET_SUPPLY_MIN_STAKE_USD="0", AIMARKET_CREDITS_FREE_GRANT_USD="0",
        ) as client:
            _seller_acct, seller_key = _account(client)
            # invoke_url the hub will refuse to call → no delivery, no payout.
            client.post("/ai-market/v2/supply/register", headers={"X-API-Key": seller_key},
                        json=_manifest())
            _b, buyer_key = _account(client, funded_usd=1.0)
            client.post(
                "/ai-market/v2/invoke", headers={"X-API-Key": buyer_key},
                json={"product_id": "my-service", "capability_id": "my.service@v1",
                      "input": {}, "source_hub": "local"},
            )
            seller = client.get(
                "/ai-market/v2/account", headers={"X-API-Key": seller_key},
            ).json()
            assert seller["balance_usd"] == pytest.approx(0.0)
