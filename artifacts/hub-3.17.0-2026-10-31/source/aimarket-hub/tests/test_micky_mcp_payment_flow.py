"""Micky's payment lifecycle checks through the current MCP and invoke handlers.

The application, signature verification, SQLite credit ledger and payment gates are
real. Only the outbound provider transport is synthetic. MCP's existing in-memory
transport (also used by stdio) keeps the test completely offline. These tests make
no claim about chain settlement or rolling back a provider's external side effects.
"""
from __future__ import annotations

import json
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from aimarket_hub import outbound_http, sandbox_trials
from aimarket_hub.api import create_app
from aimarket_hub.config import HubConfig
from aimarket_hub.credits import CreditsLedger
from aimarket_hub.database import HubDatabase
from aimarket_hub.models import Capability
from aimarket_hub.signing import Signer
from aimarket_hub.supply_security import _bound_response_canonical


PRICE = 0.01
INITIAL = 0.02
PRODUCT = "micky-test"
CAPABILITY = "micky.test@v1"
PROVIDER_URL = "https://provider.invalid/invoke"


@dataclass
class PaymentHarness:
    client: Any
    db: HubDatabase
    ledger: CreditsLedger
    account_id: str
    api_key: str
    mode: str = "success"
    calls: list[dict[str, Any]] = field(default_factory=list)
    side_effects: list[dict[str, Any]] = field(default_factory=list)

    def account(self):
        return self.ledger.account(self.account_id)

    def holds(self):
        return [dict(row) for row in self.db._conn.execute(
            "SELECT receipt_id, amount_mc, status FROM credit_holds WHERE account_id = ? "
            "ORDER BY created_at, receipt_id", (self.account_id,),
        ).fetchall()]

    def invoke(self, **arguments):
        response = self.client.post("/mcp", headers={"X-API-Key": self.api_key}, json={
            "jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
                "name": "market_invoke", "arguments": {
                    "product_id": PRODUCT, "capability_id": CAPABILITY,
                    "input": {"action": "synthetic"}, "max_price_usd": PRICE,
                    **arguments,
                },
            },
        })
        assert response.status_code == 200, response.text
        payloads = [line[5:].strip() for line in response.text.splitlines() if line.startswith("data:")]
        assert len(payloads) == 1, response.text
        rpc = json.loads(payloads[0])
        assert "result" in rpc, rpc
        result = rpc["result"]
        return result, json.loads(result["content"][0]["text"])


def _capability(provider_key, price=PRICE):
    return Capability(
        capability_id=CAPABILITY, product_id=PRODUCT, name="Micky synthetic provider",
        description="A controlled payment lifecycle fixture.", source_hub="local",
        invoke_url=PROVIDER_URL, price_per_call_usd=price, trust_score=0.8,
        provider_pubkey=provider_key,
    )


@contextmanager
def _payment_hub(monkeypatch, tmp_path, *, balance=INITIAL, rate=60):
    for name, value in {
        "AIMARKET_CREDITS_ENABLED": "1", "AIMARKET_AUTO_CRAWL": "0",
        "AIMARKET_UPDATE_CHECK": "0", "AIMARKET_PQC": "0",
        "AIMARKET_SUPPLY_REQUIRE_RESPONSE_SIG": "1",
        "AIMARKET_ORACLE_FAMILY_URL": "off", "AIFACTORY_CRYPTO_ENABLED": "0",
        "AIMARKET_INVOKE_RATE_PER_MIN": str(rate), "AIMARKET_WORKERS": "1",
    }.items():
        monkeypatch.setenv(name, value)
    # A short balance must not be rescued by the trial in this paid-rail experiment.
    monkeypatch.setattr(sandbox_trials, "_ENABLED", False)
    config = HubConfig()
    config.db_path = str(tmp_path / "hub.db")
    config.signing_key_path = str(tmp_path / "hub.key")
    config.hub_url = "https://hub.invalid"
    db = HubDatabase(tmp_path / "hub.db")
    provider_signer = Signer(tmp_path / "provider.key")
    db.upsert_capability(_capability(provider_signer.public_key_b64))
    ledger = CreditsLedger(db._conn)
    account = ledger.create_account(label="synthetic buyer", grant_usd=balance)
    app = create_app(config=config, db=db, signer=Signer(tmp_path / "hub.key"))
    # This is the gateway's actual stdio transport flag, not a replacement money path.
    app.state.mcp_stdio = True
    with TestClient(app) as client:
        harness = PaymentHarness(client, db, ledger, account["account_id"], account["api_key"])

        async def provider_post(url, *, json=None, headers=None, **kwargs):
            assert url == PROVIDER_URL
            # An inspectable reservation exists BEFORE the provider receives the call.
            snapshot = harness.account()
            held = [hold for hold in harness.holds() if hold["status"] == "held"]
            assert len(held) == 1
            assert held[0]["amount_mc"] == 1000
            assert snapshot["held_usd"] == pytest.approx(PRICE)
            harness.calls.append({"input": json, "account_during_call": snapshot,
                                  "receipt_id": held[0]["receipt_id"], "headers": headers or {}})
            request = httpx.Request("POST", url)
            if harness.mode == "timeout_after_effect":
                harness.side_effects.append(json)
                raise httpx.ReadTimeout("response lost after synthetic effect", request=request)
            if harness.mode in ("http500", "http400"):
                status = 500 if harness.mode == "http500" else 400
                return httpx.Response(status, json={"error": "synthetic provider refusal"}, request=request)
            if harness.mode == "non_json":
                return httpx.Response(200, text="not-json", request=request)
            result = {"ok": True, "value": "fixture"}
            if harness.mode == "explicit_failure":
                result = {"ok": False, "error": "synthetic work failed"}
            if harness.mode == "claimed_overage":
                result["charged_usd"] = 999
            signature = provider_signer.sign_canonical(_bound_response_canonical(
                CAPABILITY, PRODUCT, (json or {}).get("input"), result,
            ))
            if harness.mode == "bad_signature":
                signature = "invalid-signature"
            return httpx.Response(200, json={"result": result}, request=request,
                                  headers={"X-Provider-Signature": signature})

        monkeypatch.setattr(outbound_http, "safe_post", provider_post)
        yield harness, provider_signer


def _money(harness, *, balance, held=0, spent=0):
    account = harness.account()
    assert account["balance_usd"] == pytest.approx(balance)
    assert account["held_usd"] == pytest.approx(held)
    assert account["spent_usd"] == pytest.approx(spent)
    assert balance + held + spent == pytest.approx(account["granted_usd"])


def test_mcp_hold_precedes_provider_and_success_captures_exact_price(monkeypatch, tmp_path):
    with _payment_hub(monkeypatch, tmp_path) as (harness, _):
        result, body = harness.invoke()
        assert result["isError"] is False, body
        assert body["charged_usd"] == pytest.approx(PRICE)
        assert len(harness.calls) == 1
        assert harness.calls[0]["account_during_call"]["balance_usd"] == pytest.approx(INITIAL - PRICE)
        assert harness.holds() == [{"receipt_id": harness.calls[0]["receipt_id"],
                                    "amount_mc": 1000, "status": "captured"}]
        _money(harness, balance=INITIAL - PRICE, spent=PRICE)


@pytest.mark.parametrize("mode", ["http500", "http400", "explicit_failure", "non_json", "bad_signature"])
def test_provider_failure_releases_hold_without_a_debit(monkeypatch, tmp_path, mode):
    with _payment_hub(monkeypatch, tmp_path) as (harness, _):
        harness.mode = mode
        result, body = harness.invoke()
        assert result["isError"] is True, body
        assert len(harness.calls) == 1
        assert [hold["status"] for hold in harness.holds()] == ["released"]
        _money(harness, balance=INITIAL)


def test_capture_error_withholds_output_and_releases_real_hold(monkeypatch, tmp_path):
    with _payment_hub(monkeypatch, tmp_path) as (harness, _):
        monkeypatch.setattr(CreditsLedger, "capture_hold", lambda self, receipt_id: {"error": "synthetic write refusal"})
        result, body = harness.invoke()
        assert result["isError"] is True, body
        assert "settlement failed" in body["detail"]
        assert "value" not in body
        assert [hold["status"] for hold in harness.holds()] == ["released"]
        _money(harness, balance=INITIAL)


def test_insufficient_balance_never_reaches_provider(monkeypatch, tmp_path):
    with _payment_hub(monkeypatch, tmp_path, balance=0.005) as (harness, _):
        result, body = harness.invoke()
        assert result["isError"] is True, body
        assert harness.calls == []
        assert harness.holds() == []
        _money(harness, balance=0.005)


def test_repriced_offer_over_ceiling_is_refused_before_hold_or_provider(monkeypatch, tmp_path):
    with _payment_hub(monkeypatch, tmp_path) as (harness, signer):
        harness.db.upsert_capability(_capability(signer.public_key_b64, price=0.015))
        result, body = harness.invoke(max_price_usd=PRICE)
        assert result["isError"] is True
        assert body["error"] == "price_limit_exceeded"
        assert body["current_price_usd"] == pytest.approx(0.015)
        assert harness.calls == [] and harness.holds() == []
        _money(harness, balance=INITIAL)


def test_provider_claimed_overage_does_not_change_the_reserved_price(monkeypatch, tmp_path):
    with _payment_hub(monkeypatch, tmp_path) as (harness, _):
        harness.mode = "claimed_overage"
        result, body = harness.invoke()
        assert result["isError"] is False, body
        assert body["charged_usd"] == pytest.approx(PRICE)
        _money(harness, balance=INITIAL - PRICE, spent=PRICE)


def test_timeout_releases_money_but_plain_retry_can_duplicate_external_effect(monkeypatch, tmp_path):
    with _payment_hub(monkeypatch, tmp_path) as (harness, _):
        harness.mode = "timeout_after_effect"
        for _attempt in range(2):
            result, body = harness.invoke()
            assert result["isError"] is True, body
            _money(harness, balance=INITIAL)
        assert len(harness.side_effects) == 2
        assert len(harness.calls) == 2
        assert len({call["receipt_id"] for call in harness.calls}) == 2
        assert all(not call["headers"].get("Idempotency-Key") for call in harness.calls)
        assert all(hold["status"] == "released" for hold in harness.holds())


def test_disabled_key_stops_before_provider_and_does_not_fall_back_to_trial(monkeypatch, tmp_path):
    with _payment_hub(monkeypatch, tmp_path) as (harness, _):
        harness.ledger.set_status(harness.account_id, "disabled")
        result, body = harness.invoke()
        assert result["isError"] is True
        assert body["error"] == "invalid_api_key"
        assert harness.calls == [] and harness.holds() == []
        _money(harness, balance=INITIAL)


def test_rate_limited_second_call_creates_no_second_hold_or_charge(monkeypatch, tmp_path):
    with _payment_hub(monkeypatch, tmp_path, rate=1) as (harness, _):
        first, body = harness.invoke()
        assert first["isError"] is False, body
        second, body = harness.invoke()
        assert second["isError"] is True
        assert body["error"] == "rate_limited"
        assert len(harness.calls) == 1 and len(harness.holds()) == 1
        _money(harness, balance=INITIAL - PRICE, spent=PRICE)
