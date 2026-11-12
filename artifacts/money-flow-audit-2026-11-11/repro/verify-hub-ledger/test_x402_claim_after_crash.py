"""Verify invoke-local-4: a seller-direct claim committed at admission, with the process dying
before the answer (simulated by committing the same claim the admission commits and then
starting a fresh app on the same DB), is never released; the paid retry is refused."""
from __future__ import annotations

from aimarket_hub.models import Capability
from tests.test_credits_invoke import _hub


def _cap(price):
    return Capability(capability_id="demo.echo@v1", product_id="demo-echo", name="Echo",
                      description="d", price_per_call_usd=price, source_hub="local", invoke_url="",
                      prompt_template='{"answer": "echo", "ok": true}', payout_address="0x" + "cd" * 20)


def test_claim_survives_crash(monkeypatch, tmp_path):
    from aimarket_hub import settle

    def _verify(*, tx_hash, terms, timeout=10.0, max_age_s=0, paid_before=None, require_nonce, rpc_url=""):
        return {"tx_hash": tx_hash, "paid_units": terms.amount_units, "authorizer": "0x" + "ab" * 20}

    env = dict(AIMARKET_CREDITS_ENABLED="0", AIMARKET_X402_ACCEPT="1", AIFACTORY_CRYPTO_ENABLED="1",
               AIMARKET_PAYMENT_RECIPIENT="0x" + "cd" * 20, AIMARKET_AUTO_CRAWL="0")
    body = {"product_id": "demo-echo", "capability_id": "demo.echo@v1", "input": {"text": "hi"},
            "source_hub": "local"}
    tx = "0x" + "44" * 32
    with _hub(monkeypatch, tmp_path, **env) as (client, db):
        db.upsert_capability(_cap(0.004))
        quote = client.post("/ai-market/v2/invoke", json=body).json()
        monkeypatch.setattr(settle, "verify_transfer", _verify)
        # What _settle_market_payment commits at admission (payments.py:209) before the provider runs:
        ok = settle.PaymentStore(db._conn).claim_invoice(
            tx_hash=tx, pay_to="0x" + "cd" * 20, payer="0x" + "ab" * 20, amount_usd=0.004,
            amount_atomic=4000, asset="0x833589fcd6edb6e08f4c7c32d4f71b54bda02913", network="base",
            capability_id="demo.echo@v1", nonce=quote["nonce"])
        assert ok
        # ...process dies here: no _local_unwind ran. A restarted hub on the same DB:
        r = client.post("/ai-market/v2/invoke", json=body, headers={
            "X-Payment": tx, "X-Payment-Nonce": quote["nonce"], "X-Payment-Secret": quote["payment_secret"]})
        print("retry after crash:", r.status_code, r.json().get("error"), r.json().get("detail"))
        row = db._conn.execute("SELECT status, receipt_id FROM x402_payments WHERE nonce = ?",
                               (quote["nonce"],)).fetchone()
        print("claim row:", dict(row))
        assert r.status_code == 402 and "already been used" in r.json()["detail"]
