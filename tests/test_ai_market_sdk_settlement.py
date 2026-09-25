"""The SDK speaks the signed pilot flow: fetch the challenge, then confirm with the signature."""
from __future__ import annotations

from types import SimpleNamespace

import cli.ai_market_sdk as sdk_mod


def _client():
    client = sdk_mod.AIMarketClient.__new__(sdk_mod.AIMarketClient)
    client.base_url = "https://factory.example.test"
    client.access_token = "customer-jwt"
    client.timeout_sec = 5
    return client


def test_the_sdk_fetches_the_challenge_then_sends_the_signature(monkeypatch):
    sent = []

    def post(url, json=None, headers=None, timeout=None):
        sent.append((json, headers))
        if not json.get("payer_signature"):
            return SimpleNamespace(status_code=400, json=lambda: {"detail": {"challenge": "sign me"}},
                                   raise_for_status=lambda: None)
        return SimpleNamespace(status_code=200, json=lambda: {"license_key": "lk"},
                               raise_for_status=lambda: None)

    monkeypatch.setattr(sdk_mod.requests, "post", post)
    client = _client()
    assert client.settlement_challenge(product_id="p", tx_hash="0x" + "ab" * 32) == "sign me"
    out = client.confirm_settlement(product_id="p", tx_hash="0x" + "ab" * 32, payer_signature="0xsig")
    assert out == {"license_key": "lk"}
    assert sent[1][0]["payer_signature"] == "0xsig"
    assert all(h.get("Authorization") == "Bearer customer-jwt" for _, h in sent)
