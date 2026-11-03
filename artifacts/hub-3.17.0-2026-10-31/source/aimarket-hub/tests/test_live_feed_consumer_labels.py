"""Who the live feed says a call came from.

Measured 2026-09-30 on modelmarket.dev: every priced call in /stats/live read `anonymous`.
They were the operator's own credit accounts (PingBlip's turnkey key, the weather-witness
desk) — the resolver knew only the admin Bearer, a channel and a sandbox visitor, so the
credits rail, x402 and the /mcp gateway all fell through, and the feed counted our own
spending as external demand.
"""
from __future__ import annotations

import hashlib
from contextlib import contextmanager

from fastapi.testclient import TestClient

from aimarket_hub.api import create_app
from aimarket_hub.config import HubConfig
from aimarket_hub.database import HubDatabase
from aimarket_hub.mcp_gateway import MCP_CALLER_HEADER
from aimarket_hub.models import Capability, InvocationStat
from aimarket_hub.signing import Signer

ADMIN_TOKEN = "test-admin-token-not-for-production"
INVOKE = {"product_id": "demo-echo", "capability_id": "demo.echo@v1",
          "input": {"text": "hi"}, "source_hub": "local"}


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
    db.upsert_capability(Capability(
        capability_id="demo.echo@v1", product_id="demo-echo", name="Echo",
        description="Returns what it is given", price_per_call_usd=0.004,
        source_hub="local", invoke_url="", prompt_template='{"answer": "echo", "ok": true}',
    ))
    db.upsert_capability(Capability(
        capability_id="demo.free@v1", product_id="demo-echo", name="Free",
        description="Costs nothing", price_per_call_usd=0.0,
        source_hub="local", invoke_url="", prompt_template='{"ok": true}',
    ))
    app = create_app(config=config, db=db, signer=Signer(root / "key"))
    with TestClient(app) as client:
        yield client, db


def _digest(ident: str) -> str:
    return hashlib.sha256(ident.encode("utf-8")).hexdigest()[:12]


def _stored_labels(db: HubDatabase) -> list[str]:
    return [str(r["consumer_hub"]) for r in db.recent_stats(limit=50)]


def test_a_credit_account_is_named_not_anonymous(monkeypatch, tmp_path):
    with _hub(monkeypatch, tmp_path, AIMARKET_CREDITS_ENABLED="1",
              AIMARKET_CREDITS_FREE_GRANT_USD="0.05") as (client, db):
        signup = client.post("/ai-market/v2/accounts", json={"label": "buyer"}).json()
        r = client.post("/ai-market/v2/invoke", json=INVOKE, headers={"X-API-Key": signup["api_key"]})
        assert r.status_code == 200, r.text

        account_id = signup["account_id"]
        assert _stored_labels(db) == [f"account:{account_id}"]
        event = client.get("/ai-market/v2/stats/live").json()["events"][0]
        # Public: the prefix says which rail paid, the id is pseudonymized like a channel's.
        assert event["consumer_hub"] == f"account:{_digest(account_id)}"
        assert account_id not in event["consumer_hub"]
        assert event["traffic_class"] == "external"


def test_an_mcp_forward_is_named_and_its_header_cannot_write_the_feed(monkeypatch, tmp_path):
    with _hub(monkeypatch, tmp_path) as (client, db):
        r = client.post("/ai-market/v2/invoke", json={**INVOKE, "capability_id": "demo.free@v1"},
                        headers={MCP_CALLER_HEADER: "mcpx-OfficialAnthropicClient"})
        assert r.status_code == 200, r.text
        assert _stored_labels(db) == ["mcp:mcpx-OfficialAnthropicClient"]
        event = client.get("/ai-market/v2/stats/live").json()["events"][0]
        # The header is unauthenticated: whatever it says is hashed before it goes public.
        assert event["consumer_hub"] == f"mcp:{_digest('mcpx-OfficialAnthropicClient')}"


def test_a_sandbox_trial_outranks_the_mcp_label(monkeypatch, tmp_path):
    """A priced call through /mcp carries both; the trial is what the monitor labels."""
    with _hub(monkeypatch, tmp_path) as (client, db):
        client.post("/ai-market/v2/invoke", json={**INVOKE, "capability_id": "demo.free@v1"},
                    headers={MCP_CALLER_HEADER: "mcpx-abc12345",
                             "X-AIMarket-Sandbox-Visitor": "mcpx-abc12345"})
        assert _stored_labels(db) == ["sandbox:mcpx-abc12345"]


def test_no_identity_at_all_is_still_anonymous(monkeypatch, tmp_path):
    with _hub(monkeypatch, tmp_path) as (client, db):
        client.post("/ai-market/v2/invoke", json={**INVOKE, "capability_id": "demo.free@v1"})
        assert _stored_labels(db) == ["anonymous"]


def test_listed_operator_accounts_count_as_our_own_traffic(monkeypatch, tmp_path):
    with _hub(monkeypatch, tmp_path,
              AIMARKET_OPERATOR_ACCOUNTS="acct_ours1, acct_ours2") as (client, db):
        for i, consumer in enumerate(
            ["account:acct_ours1", "account:acct_ours2", "account:acct_customer", "anonymous"]
        ):
            db.record_invocation(InvocationStat(
                capability_id=f"cap-{i}@v1", product_id="p", source_hub="local",
                price_usd=0.001, latency_ms=1, success=True,
                timestamp="2026-09-30T12:00:0%dZ" % i, consumer_hub=consumer,
            ))
        data = client.get("/ai-market/v2/stats/live?limit=50").json()
        by_cap = {e["capability_id"]: e["traffic_class"] for e in data["events"]}
        assert by_cap == {"cap-0@v1": "operator_self", "cap-1@v1": "operator_self",
                          "cap-2@v1": "external", "cap-3@v1": "external"}
        s = data["summary"]
        assert s["operator_self_invocations"] == 2
        assert s["external_invocations"] == 2


def test_an_unverified_x_payment_does_not_label_a_call_x402(monkeypatch, tmp_path):
    """The label came from the header before any verification, so a junk X-Payment on a free
    call showed on the public feed as x402-paid demand."""
    with _hub(monkeypatch, tmp_path) as (client, db):
        r = client.post("/ai-market/v2/invoke", json={**INVOKE, "capability_id": "demo.free@v1"},
                        headers={"X-Payment": "0x" + "ab" * 32})
        assert r.status_code == 200, r.text
        assert "x402" not in _stored_labels(db)


def test_the_home_page_labels_like_the_feed(monkeypatch):
    """terminal_ssr kept its own copy of the rules: it published raw account ids and counted the
    operator's own accounts as customers after the feed had learned not to."""
    from aimarket_hub.terminal_ssr import public_events
    monkeypatch.setenv("AIMARKET_OPERATOR_ACCOUNTS", "acct_ops1")
    out = public_events([{"consumer_hub": "account:acct_0123456789abcdef"}, {"consumer_hub": "mcp:abc"},
                         {"consumer_hub": "account:acct_ops1"}], "https://modelmarket.dev")
    assert [e["consumer_hub"] for e in out] == [
        "account:" + _digest("acct_0123456789abcdef"), "mcp:" + _digest("abc"), "account:" + _digest("acct_ops1")]
    assert [e["traffic_class"] for e in out] == ["external", "external", "operator_self"]
