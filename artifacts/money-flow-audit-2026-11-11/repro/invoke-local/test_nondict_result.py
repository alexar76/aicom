"""Repro: a provider whose `result` is not a JSON object is captured, then the hub answers 500."""
from __future__ import annotations

import pytest

from tests._mandate_kit import balance, funded_account, hub, list_provider
from tests.test_subcontract import BRIEF, Providers


@pytest.mark.parametrize("result", [["a", "b"], "plain text answer", None, 42])
def test_non_object_result_is_charged_then_500(monkeypatch, tmp_path, result):
    with hub(monkeypatch, tmp_path) as (client, db):
        providers = Providers(client.app_ref)
        import aimarket_hub.outbound_http as outbound

        monkeypatch.setattr(outbound, "safe_post", providers.post)
        list_provider(db, "brief.make@v1", "brief", 0.010, url="https://brief.test/invoke")

        async def brief(body, headers, p):
            return 200, {"result": result}

        providers.add("https://brief.test/invoke", brief)
        account, api_key = funded_account(client, db, 1.0)
        with pytest.raises((AttributeError, TypeError)) as err:
            client.post("/ai-market/v2/invoke", headers={"X-API-Key": api_key}, json=BRIEF)
        print("raised", repr(err.value), "balance", balance(db, account))
        rows = db._conn.execute("SELECT receipt_id, status, amount_mc FROM credit_holds").fetchall()
        print([dict(x) for x in rows])
        # What happened: the call is NOT 200, yet the money was captured.
        assert balance(db, account) == pytest.approx(0.99)
        assert all(x["status"] == "captured" for x in rows)


class _NaNResp:
    status_code = 200
    headers = {}
    text = '{"result": {"temp_c": NaN}}'

    def json(self):
        import json
        return json.loads(self.text)   # httpx parses NaN like this too


def test_nan_in_result_is_charged_then_500(monkeypatch, tmp_path):
    with hub(monkeypatch, tmp_path) as (client, db):
        import aimarket_hub.outbound_http as outbound

        async def _post(url, **kw):
            return _NaNResp()

        monkeypatch.setattr(outbound, "safe_post", _post)
        list_provider(db, "brief.make@v1", "brief", 0.010, url="https://brief.test/invoke")
        account, api_key = funded_account(client, db, 1.0)
        for attempt in range(2):        # the client retries the 500
            with pytest.raises(ValueError) as err:
                client.post("/ai-market/v2/invoke", headers={"X-API-Key": api_key}, json=BRIEF)
        print("raised", repr(err.value)[:90], "balance after 2 attempts", balance(db, account))
        rows = db._conn.execute("SELECT status FROM credit_holds").fetchall()
        assert [r["status"] for r in rows] == ["captured", "captured"]
        assert balance(db, account) == pytest.approx(0.98)


def test_nan_seller_is_paid_for_undelivered_calls(monkeypatch, tmp_path):
    from aimarket_hub.models import Capability

    with hub(monkeypatch, tmp_path) as (client, db):
        import aimarket_hub.outbound_http as outbound

        async def _post(url, **kw):
            return _NaNResp()

        monkeypatch.setattr(outbound, "safe_post", _post)
        seller, _ = funded_account(client, db, 0.0001)
        db.upsert_capability(Capability(
            capability_id="brief.make@v1", product_id="brief", name="b", description="p",
            price_per_call_usd=0.010, source_hub="local", invoke_url="https://brief.test/invoke",
            trust_score=0.9, publisher_id=seller))
        account, api_key = funded_account(client, db, 1.0)
        before = balance(db, seller)
        for _ in range(3):
            with pytest.raises(ValueError):
                client.post("/ai-market/v2/invoke", headers={"X-API-Key": api_key}, json=BRIEF)
        print("buyer", balance(db, account), "seller earned", round(balance(db, seller) - before, 6))
        assert balance(db, account) == pytest.approx(0.97)
        assert balance(db, seller) > before
