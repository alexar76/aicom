"""Repro: an x402-paid call with a verify block and any X-Payment-Channel header runs the
provider, then 502s ("no reservation backs the verified invoke"), every time."""
from __future__ import annotations

from aimarket_hub.models import Capability
from tests.test_credits_invoke import _hub


def _settled(monkeypatch, price):
    from aimarket_hub import settle

    def _verify(*, tx_hash, terms, timeout=10.0, max_age_s=0, paid_before=None,
                require_nonce, rpc_url=""):
        return {"tx_hash": tx_hash, "paid_units": settle.to_units(price, terms.decimals),
                "authorizer": "0x" + "ab" * 20}

    monkeypatch.setattr(settle, "verify_transfer", _verify)


def test_x402_paid_verified_call_with_channel_header_dead_ends(monkeypatch, tmp_path):
    price = 0.10   # above the 0.05 Pay-on-Verified floor
    with _hub(monkeypatch, tmp_path, AIMARKET_CREDITS_ENABLED="0", AIMARKET_X402_ACCEPT="1",
              AIFACTORY_CRYPTO_ENABLED="1", AIMARKET_PAYMENT_RECIPIENT="0x" + "cd" * 20,
              AIMARKET_INVOKE_RATE_PER_MIN="100000", AIMARKET_VERIFY_METIS_URL="http://127.0.0.1:8080", AIMARKET_ALLOW_DEMO_CREDIT="1", AIMARKET_AUTO_CRAWL="0") as (client, db):
        runs = []
        import aimarket_hub.outbound_http as outbound

        class _Resp:
            status_code = 200
            headers = {}
            text = "{}"

            def json(self):
                return {"result": {"answer": "work done"}}

        async def _post(url, **kw):
            runs.append(url)
            return _Resp()

        monkeypatch.setattr(outbound, "safe_post", _post)
        db.upsert_capability(Capability(
            capability_id="demo.work@v1", product_id="demo-work", name="Work",
            description="does work", price_per_call_usd=price, source_hub="local",
            invoke_url="https://provider.test/invoke", trust_score=0.9,
            payout_address="0x" + "cd" * 20,
        ))
        _settled(monkeypatch, price)
        body = {"product_id": "demo-work", "capability_id": "demo.work@v1", "input": {"q": 1},
                "source_hub": "local", "verify": {"intent": "answer the question"}}
        quote = client.post("/ai-market/v2/invoke", json=body)
        assert quote.status_code == 402, quote.text
        paid = {"X-Payment": "0x" + "33" * 32, "X-Payment-Nonce": quote.json()["nonce"],
                "X-Payment-Secret": quote.json()["payment_secret"],
                "X-Payment-Channel": "ch_whatever"}
        statuses = []
        for _ in range(3):
            r = client.post("/ai-market/v2/invoke", json=body, headers=paid)
            statuses.append((r.status_code, r.json().get("detail")))
        print("statuses", statuses, "provider runs", len(runs))
        assert all(s == 502 for s, _ in statuses)
        assert len(runs) == 3   # the provider worked three times for one payment, nothing delivered
        # Without the channel header the same payment delivers.
        paid.pop("X-Payment-Channel")
        ok = client.post("/ai-market/v2/invoke", json=body, headers=paid)
        print("without channel header:", ok.status_code)
        assert ok.status_code == 200
