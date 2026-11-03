"""A key on the MCP connection pays where the free trial stops (2026-10-06).

Before this, the only rail an MCP client could use after the trial was an EIP-3009 payment
it had to sign and broadcast itself, per call, with USDC and gas on Base; prepaid credit was
"used over the HTTP API with X-API-Key, not through this MCP tool". The funnel showed
hundreds of tool lists and no paying caller. Now a key minted on /start rides the
connection (X-API-Key, or Authorization: Bearer aimk_…) and pays from its balance, and a
short balance never leaves a key-holder worse off than a stranger: the trial still applies.

The mocked half pins what the gateway sends; the last tests run the real hub end to end
(signup → free call → wall → top-up → charged call) through the same loopback hop.
"""

from __future__ import annotations

import json
from contextlib import contextmanager

import httpx
import pytest

from tests.test_mcp_gateway import _FakeResponse, _call, _hub_client, _rpc, _sse

ADMIN_TOKEN = "test-admin-token-not-for-production"
KEY = "aimk_" + "A" * 32
ECHO = {"product_id": "prod-hub", "capability_id": "hub.echo@v1"}


@pytest.fixture
def scripted(monkeypatch):
    """The internal invoke, answered from a script: [(status, body), …]; the last repeats."""
    state: dict = {"calls": [], "replies": [(200, {"success": True, "output": {"ok": True}})]}

    async def fake_post(self, url, json=None, headers=None, **kwargs):  # noqa: A002
        state["calls"].append({"url": url, "body": json or {}, "headers": dict(headers or {})})
        replies = state["replies"]
        status, body = replies.pop(0) if len(replies) > 1 else replies[0]
        return _FakeResponse(body, status_code=status)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    return state


def _text(result: dict) -> dict:
    return json.loads(result["content"][0]["text"])


def _short_balance(balance: float = 0.0) -> tuple[int, dict]:
    return 402, {"success": False, "error": "payment_required", "detail": "insufficient credit",
                 "needed": 0.01, "balance": balance,
                 "payment_ways": [{"rail": "seller_direct", "header": "X-Payment"},
                                  {"rail": "credits", "header": "X-API-Key", "open_signup": True}]}


# --- what the gateway sends ------------------------------------------------------------------

def test_a_keyed_call_is_paid_from_the_balance_not_the_trial(monkeypatch, tmp_path, scripted):
    with _hub_client(monkeypatch, tmp_path) as client:
        result = _call(client, "market_invoke", ECHO, headers={"X-API-Key": KEY})["result"]
    assert result["isError"] is False
    sent = scripted["calls"]
    assert len(sent) == 1
    assert sent[0]["headers"]["X-API-Key"] == KEY
    assert "X-AIMarket-Sandbox-Visitor" not in sent[0]["headers"], (
        "the hub serves a sandbox call free even with a key on it, so a paying customer "
        "would never be charged"
    )


def test_a_bearer_account_key_is_read_like_x_api_key(monkeypatch, tmp_path, scripted):
    with _hub_client(monkeypatch, tmp_path) as client:
        _call(client, "market_invoke", ECHO, headers={"Authorization": f"Bearer {KEY}"})
    assert scripted["calls"][0]["headers"]["X-API-Key"] == KEY


def test_someone_elses_bearer_is_never_forwarded(monkeypatch, tmp_path, scripted):
    """An admin token, another hub's credential or an OAuth attempt is not our key."""
    with _hub_client(monkeypatch, tmp_path) as client:
        _call(client, "market_invoke", ECHO, headers={"Authorization": "Bearer admin-secret-token"})
    headers = scripted["calls"][0]["headers"]
    assert "X-API-Key" not in headers
    assert "Authorization" not in headers and "authorization" not in headers
    assert headers.get("X-AIMarket-Sandbox-Visitor"), "a keyless caller is a trial visitor"


def test_a_short_balance_falls_back_to_the_trial(monkeypatch, tmp_path, scripted):
    """A new key starts at $0: its first calls must not be worse than having no key."""
    scripted["replies"] = [_short_balance(), (200, {"success": True, "sandbox": True, "output": {"ok": 1}})]
    with _hub_client(monkeypatch, tmp_path) as client:
        result = _call(client, "market_invoke", ECHO, headers={"X-API-Key": KEY})["result"]
    assert result["isError"] is False
    keyed, trial = scripted["calls"]
    assert keyed["headers"]["X-API-Key"] == KEY
    assert "X-API-Key" not in trial["headers"]
    assert trial["headers"]["X-AIMarket-Sandbox-Visitor"].startswith("mcpx-")


def test_short_balance_and_spent_trial_point_at_the_top_up(monkeypatch, tmp_path, scripted):
    scripted["replies"] = [
        _short_balance(0.0021),
        (429, {"error": "trial_quota_exhausted"}),
        (402, {"success": False, "error": "payment_required", "needed": 0.01,
               "payment_ways": _short_balance()[1]["payment_ways"]}),
    ]
    with _hub_client(monkeypatch, tmp_path, AIMARKET_CREDITS_ENABLED="1",
                     AIMARKET_CREDITS_OPEN_SIGNUP="1") as client:
        result = _call(client, "market_invoke", ECHO, headers={"X-API-Key": KEY})["result"]
    body = _text(result)
    assert result["isError"] is True and body["trial_exhausted"] is True
    steps = body["next_steps"]
    assert "$0.0021" in steps[1] and "/start" in steps[1] and "Top it up" in steps[1]
    assert not any("Easiest way on" in s for s in steps), "a key-holder is not told to get a key"
    assert len(scripted["calls"]) == 3


def test_a_listing_credits_cannot_buy_is_named_as_such(monkeypatch, tmp_path, scripted):
    scripted["replies"] = [
        (402, {"success": False, "error": "payment_required", "needed": 0.01,
               "detail": "this listing pays its seller directly, so it cannot be bought with hub "
                         "credits — pay on chain with X-Payment"}),
        (429, {"error": "trial_quota_exhausted"}),
        (402, {"success": False, "error": "payment_required", "needed": 0.01}),
    ]
    with _hub_client(monkeypatch, tmp_path) as client:
        steps = _text(_call(client, "market_invoke", ECHO, headers={"X-API-Key": KEY})["result"])["next_steps"]
    assert any("cannot buy this listing" in s for s in steps)


def test_an_unknown_key_fails_closed_with_a_fix(monkeypatch, tmp_path, scripted):
    """A typo in a paying customer's config must not become calls nobody is billed for."""
    scripted["replies"] = [(401, {"success": False, "error": "invalid_api_key",
                                  "detail": "X-API-Key is not a known credit account on this hub"})]
    with _hub_client(monkeypatch, tmp_path, AIMARKET_CREDITS_ENABLED="1") as client:
        result = _call(client, "market_invoke", ECHO, headers={"X-API-Key": "aimk_typo_typo_typo"})["result"]
    body = _text(result)
    assert result["isError"] is True and body["error"] == "invalid_api_key"
    assert "MCP client's server config" in body["next_steps"][0]
    assert len(scripted["calls"]) == 1, "no silent fallback to the trial on a bad key"


def test_a_malformed_key_still_reaches_the_hub_to_be_refused(monkeypatch, tmp_path, scripted):
    with _hub_client(monkeypatch, tmp_path) as client:
        _call(client, "market_invoke", ECHO, headers={"X-API-Key": "has spaces; and=stuff"})
    assert scripted["calls"][0]["headers"]["X-API-Key"] == "malformed-key"


def test_a_payer_on_another_rail_does_not_also_send_the_key(monkeypatch, tmp_path, scripted):
    with _hub_client(monkeypatch, tmp_path) as client:
        _call(client, "market_invoke", {**ECHO, "x_payment": "0x" + "ef" * 32,
                                        "x_payment_nonce": "0x" + "cd" * 32},
              headers={"X-API-Key": KEY})
    headers = scripted["calls"][0]["headers"]
    assert headers["X-PAYMENT"] == "0x" + "ef" * 32
    assert "X-API-Key" not in headers, "one call, one rail"


# --- what a keyless stranger is told ---------------------------------------------------------

def test_the_wall_names_the_key_first_while_signup_is_open(monkeypatch, tmp_path, scripted):
    scripted["replies"] = [(429, {"error": "trial_quota_exhausted"}), _short_balance()]
    with _hub_client(monkeypatch, tmp_path, AIMARKET_CREDITS_ENABLED="1",
                     AIMARKET_CREDITS_OPEN_SIGNUP="1") as client:
        steps = _text(_call(client, "market_invoke", ECHO)["result"])["next_steps"]
    assert steps[1].startswith("Easiest way on: get an API key at ") and "/start" in steps[1]
    assert "X-API-Key" in steps[1]
    assert not any("cannot be paid for through MCP" in s for s in steps)


def test_a_closed_signup_is_not_offered(monkeypatch, tmp_path, scripted):
    closed = _short_balance()
    closed[1]["payment_ways"][1]["open_signup"] = False
    scripted["replies"] = [(429, {"error": "trial_quota_exhausted"}), closed]
    with _hub_client(monkeypatch, tmp_path, AIMARKET_CREDITS_ENABLED="1",
                     AIMARKET_CREDITS_OPEN_SIGNUP="0") as client:
        steps = " ".join(_text(_call(client, "market_invoke", ECHO)["result"])["next_steps"])
    assert "/start" not in steps
    assert "operator only" in steps


# --- account_status --------------------------------------------------------------------------

def test_account_status_is_listed_only_on_a_keyed_connection(monkeypatch, tmp_path):
    with _hub_client(monkeypatch, tmp_path) as client:
        plain = {t["name"] for t in _sse(_rpc(client, "tools/list"))["result"]["tools"]}
        keyed = {t["name"] for t in _sse(_rpc(client, "tools/list", headers={"X-API-Key": KEY}))["result"]["tools"]}
    assert "account_status" not in plain
    assert "account_status" in keyed


# --- the first call should not break ---------------------------------------------------------

@pytest.mark.parametrize("tool", ["weather_now", "air_quality_now"])
def test_a_place_tool_called_with_nothing_says_what_to_send(monkeypatch, tmp_path, scripted, tool):
    with _hub_client(monkeypatch, tmp_path) as client:
        result = _call(client, tool, {})["result"]
    assert result["isError"] is True
    text = result["content"][0]["text"]
    assert text.startswith(f"Invalid arguments for {tool}:") and '"Berlin"' in text
    assert scripted["calls"] == [], "refused before a hub round trip and a row on the tape"


@pytest.mark.parametrize("args", [{"city": "Berlin"}, {"latitude": 52.5, "longitude": 13.4},
                                  {"latitude": 0, "longitude": 0}])
def test_a_place_tool_accepts_either_way_in(args):
    from aimarket_hub.mcp_gateway import _place_input

    assert _place_input(args) == args


@pytest.mark.parametrize("args", [{}, {"city": "  "}, {"latitude": 52.5}])
def test_a_place_tool_refuses_half_a_place(args):
    from aimarket_hub.mcp_gateway import _place_input

    with pytest.raises(ValueError, match="a place is required"):
        _place_input(args)


# --- the real hub, end to end ----------------------------------------------------------------

@contextmanager
def _real_hub(monkeypatch, tmp_path):
    """A hub whose MCP gateway reaches its own invoke over ASGI instead of a mocked post.

    The capability is a static JSON pack (fulfillment.has_execution_path), so the invoke
    needs no provider and the money path is the hub's own, untouched.
    """
    import aimarket_hub.sandbox_trials as trials
    from fastapi.testclient import TestClient

    from aimarket_hub.api import create_app
    from aimarket_hub.config import HubConfig
    from aimarket_hub.database import HubDatabase
    from aimarket_hub.models import Capability
    from aimarket_hub.signing import Signer

    for name, value in {"AIMARKET_ADMIN_TOKEN": ADMIN_TOKEN, "AIMARKET_CREDITS_ENABLED": "1",
                        "AIMARKET_CREDITS_OPEN_SIGNUP": "1", "AIMARKET_SIGNUP_GRANT_USD": "0",
                        "AIMARKET_SANDBOX_MAX_PER_VISITOR": "1"}.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(trials, "_MAX_PER_VISITOR", 1)
    monkeypatch.setattr(trials, "_ledger", trials.SandboxTrialLedger(str(tmp_path / "trials.db")))
    config = HubConfig()
    config.db_path = str(tmp_path / "hub.db")
    config.signing_key_path = str(tmp_path / "key")
    config.hub_url = "https://hub.example"
    db = HubDatabase(tmp_path / "hub.db")
    db.upsert_capability(Capability(
        capability_id="hub.echo@v1", product_id="prod-hub", name="echo",
        description="Static pack.", price_per_call_usd=0.01, trust_score=0.5,
        source_hub="local", invoke_url="", prompt_template='{"answer": "echo", "ok": true}',
    ))
    app = create_app(config=config, db=db, signer=Signer(tmp_path / "key"))
    real_init = httpx.AsyncClient.__init__

    def init(self, *args, **kwargs):
        kwargs.setdefault("transport", httpx.ASGITransport(app=app, client=("127.0.0.1", 40000)))
        real_init(self, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", init)
    with TestClient(app) as client:
        yield client


def test_signup_free_call_wall_top_up_and_a_charged_call(monkeypatch, tmp_path):
    with _real_hub(monkeypatch, tmp_path) as client:
        signup = client.post("/ai-market/v2/accounts", json={"label": "start-page"})
        assert signup.status_code == 200, signup.text
        key = signup.json()["api_key"]
        account_id = signup.json()["account_id"]
        assert signup.json()["balance_usd"] == 0

        keyed = {"X-API-Key": key}
        # 1. A $0 key still gets the free call.
        first = _call(client, "market_invoke", ECHO, headers=keyed)["result"]
        assert first["isError"] is False, first
        assert _text(first)["ok"] is True

        # 2. Trial spent, balance empty: the wall names the balance and the top-up page.
        wall = _call(client, "market_invoke", ECHO, headers=keyed)["result"]
        body = _text(wall)
        assert wall["isError"] is True and body["error"] == "payment_required", body
        assert any("$0.0000" in s and "/start" in s for s in body["next_steps"]), body["next_steps"]

        # 3. Credit arrives (the operator's door here; the page's USDC door ends in the same ledger).
        credited = client.post(f"/ai-market/v2/accounts/{account_id}/credit", json={"amount_usd": 1},
                               headers={"Authorization": f"Bearer {ADMIN_TOKEN}"})
        assert credited.status_code == 200, credited.text

        # 4. The same connection now pays from the balance.
        paid = _call(client, "market_invoke", ECHO, headers=keyed)["result"]
        assert paid["isError"] is False, paid
        assert _text(paid)["charged_usd"] == pytest.approx(0.01)
        account = client.get("/ai-market/v2/account", headers=keyed).json()
        assert account["spent_usd"] == pytest.approx(0.01)
        assert account["balance_usd"] == pytest.approx(0.99)

        # 5. account_status reads the same figure.
        status = _text(_call(client, "account_status", {}, headers=keyed)["result"])
        assert status["balance_usd"] == pytest.approx(0.99)
        assert status["top_up"].endswith("/start#topup")


def test_account_status_with_an_unknown_key_says_how_to_fix_it(monkeypatch, tmp_path):
    with _real_hub(monkeypatch, tmp_path) as client:
        result = _call(client, "account_status", {}, headers={"X-API-Key": "aimk_" + "Z" * 32})["result"]
    assert result["isError"] is True
    assert "MCP client's server config" in _text(result)["next_steps"][0]


# --- the page --------------------------------------------------------------------------------

def test_start_page_is_served_with_the_shared_chrome(monkeypatch, tmp_path):
    with _hub_client(monkeypatch, tmp_path) as client:
        r = client.get("/start")
    assert r.status_code == 200
    body = r.text
    for marker in ("<!--HEAD-->", "<!--NAV-->", "<!--FOOTER-->", "<!--BACKDROP-->"):
        assert marker not in body
    assert '<link rel="stylesheet" href="/assets/site.css">' in body
    assert 'id="mint"' in body and 'id="pay"' in body
    # Five languages, one file; every key the English table has, the others have too.
    import re

    tables = re.findall(r"\n    (en|ru|es|fr|zh): \{(.*?)\n    \}", body, re.S)
    assert [name for name, _ in tables] == ["en", "ru", "es", "fr", "zh"]
    keys = {name: set(re.findall(r'(?m)(?:^\s+|,\s)([a-z][a-z0-9_]*): "', block)) for name, block in tables}
    assert len(keys["en"]) > 40
    for name in ("ru", "es", "fr", "zh"):
        assert keys[name] == keys["en"], f"{name} is missing {sorted(keys['en'] - keys[name])}"


def test_the_manifest_and_the_402_name_the_page_only_while_signup_is_open(monkeypatch, tmp_path):
    with _hub_client(monkeypatch, tmp_path, AIMARKET_CREDITS_ENABLED="1", AIMARKET_CREDITS_OPEN_SIGNUP="1") as client:
        open_conf = client.get("/.well-known/ai-market.json").json()["payment_rails"]["credits"]
    with _hub_client(monkeypatch, tmp_path, AIMARKET_CREDITS_ENABLED="1", AIMARKET_CREDITS_OPEN_SIGNUP="0") as client:
        closed_conf = client.get("/.well-known/ai-market.json").json()["payment_rails"]["credits"]
    assert open_conf["start_url"].endswith("/start")
    assert "start_url" not in closed_conf


# --- the key in the URL, for clients that cannot set a header -----------------------------

def test_a_key_in_the_path_pays_like_the_header(monkeypatch, tmp_path, scripted):
    with _hub_client(monkeypatch, tmp_path) as client:
        r = client.post(f"/mcp/k/{KEY}", json={"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                               "params": {"name": "market_invoke", "arguments": ECHO}})
        tools = _sse(client.post(f"/ai-market/mcp/k/{KEY}", json={
            "jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}))["result"]["tools"]
        info = client.get(f"/mcp/k/{KEY}").json()
    assert r.status_code == 200
    assert scripted["calls"][0]["headers"]["X-API-Key"] == KEY
    assert "X-AIMarket-Sandbox-Visitor" not in scripted["calls"][0]["headers"]
    assert "account_status" in {t["name"] for t in tools}
    assert info["status"] == "ok"


def test_a_garbage_path_key_reaches_the_hub_to_be_refused(monkeypatch, tmp_path, scripted):
    with _hub_client(monkeypatch, tmp_path) as client:
        client.post("/mcp/k/not a key!", json={"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                                "params": {"name": "market_invoke", "arguments": ECHO}})
    assert scripted["calls"][0]["headers"]["X-API-Key"] == "malformed-key"


def test_the_access_log_never_shows_a_path_key():
    import logging

    from aimarket_hub.mcp_gateway import install_access_log_redaction, redact_key_path

    install_access_log_redaction()
    record = logging.LogRecord("uvicorn.access", logging.INFO, __file__, 1,
                               '%s - "%s %s HTTP/%s" %d',
                               ("1.2.3.4:5", "POST", f"/mcp/k/{KEY}?x=1", "1.1", 200), None)
    for f in logging.getLogger("uvicorn.access").filters:
        f.filter(record)
    line = record.getMessage()
    assert KEY not in line and "/mcp/k/<redacted>?x=1" in line
    assert redact_key_path(f"/ai-market/mcp/k/{KEY}") == "/ai-market/mcp/k/<redacted>"
    assert redact_key_path("/mcp") == "/mcp"
