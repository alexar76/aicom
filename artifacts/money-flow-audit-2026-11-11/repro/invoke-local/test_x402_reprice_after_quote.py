"""Repro: a buyer pays exactly the 402 quote on chain; the listing is repriced upward before
the paid retry; the hub refuses the payment (402 payment_invalid). The USDC is with the seller."""
from __future__ import annotations

from aimarket_hub.models import Capability
from tests.test_credits_invoke import _hub


def _paid_exactly(monkeypatch, quoted_price):
    from aimarket_hub import settle

    def _verify(*, tx_hash, terms, timeout=10.0, max_age_s=0, paid_before=None,
                require_nonce, rpc_url=""):
        paid = settle.to_units(quoted_price, terms.decimals)
        # mimic verify_transfer's own rule
        if paid < terms.seller_units:
            raise settle.PaymentError(f"paid {paid} base units, the seller's share is {terms.seller_units}")
        return {"tx_hash": tx_hash, "paid_units": paid, "authorizer": "0x" + "ab" * 20}

    monkeypatch.setattr(settle, "verify_transfer", _verify)


def _cap(price):
    return Capability(capability_id="demo.echo@v1", product_id="demo-echo", name="Echo",
                      description="d", price_per_call_usd=price, source_hub="local", invoke_url="",
                      prompt_template='{"answer": "echo", "ok": true}', payout_address="0x" + "cd" * 20)


def test_reprice_between_quote_and_paid_retry(monkeypatch, tmp_path):
    with _hub(monkeypatch, tmp_path, AIMARKET_CREDITS_ENABLED="0", AIMARKET_X402_ACCEPT="1",
              AIFACTORY_CRYPTO_ENABLED="1", AIMARKET_PAYMENT_RECIPIENT="0x" + "cd" * 20,
              AIMARKET_ALLOW_DEMO_CREDIT="1", AIMARKET_AUTO_CRAWL="0") as (client, db):
        db.upsert_capability(_cap(0.004))
        body = {"product_id": "demo-echo", "capability_id": "demo.echo@v1", "input": {"text": "hi"},
                "source_hub": "local"}
        quote = client.post("/ai-market/v2/invoke", json=body)
        assert quote.status_code == 402
        _paid_exactly(monkeypatch, 0.004)          # buyer pays the quoted amount to the seller
        db.upsert_capability(_cap(0.005))          # listing repriced before the paid retry
        r = client.post("/ai-market/v2/invoke", json=body, headers={
            "X-Payment": "0x" + "44" * 32, "X-Payment-Nonce": quote.json()["nonce"],
            "X-Payment-Secret": quote.json()["payment_secret"]})
        print("paid retry:", r.status_code, r.json().get("error"), r.json().get("detail"))
        assert r.status_code == 402 and r.json()["error"] == "payment_invalid"
