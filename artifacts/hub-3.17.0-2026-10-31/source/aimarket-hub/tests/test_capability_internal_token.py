"""Hub attaches X-AIMarket-Internal-Token only to operator-named provider gateways."""

from __future__ import annotations

from contextlib import contextmanager

from fastapi.testclient import TestClient

from aimarket_hub.api import create_app
from aimarket_hub.config import HubConfig
from aimarket_hub.database import HubDatabase
from aimarket_hub.signing import Signer

ADMIN_TOKEN = "test-admin-token-not-for-production"
ADMIN_HEADERS = {"Authorization": f"Bearer {ADMIN_TOKEN}"}
CAP_TOKEN = "hub-capability-token-" + ("x" * 32)


@contextmanager
def _hub(monkeypatch, tmp_path, **env):
    monkeypatch.setenv("AIMARKET_ADMIN_TOKEN", ADMIN_TOKEN)
    monkeypatch.setenv("AIMARKET_CREDITS_ENABLED", "1")
    monkeypatch.setenv("AIMARKET_ORACLE_FAMILY_URL", "off")
    monkeypatch.setenv("AIMARKET_SUPPLY_MIN_STAKE_USD", "0")
    monkeypatch.setenv("AIMARKET_CREDITS_FREE_GRANT_USD", "0")
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    root = tmp_path / "hub-cap-token"
    root.mkdir(parents=True, exist_ok=True)
    config = HubConfig()
    config.db_path = str(root / "hub.db")
    config.signing_key_path = str(root / "key")
    app = create_app(config=config, db=HubDatabase(root / "hub.db"), signer=Signer(root / "key"))
    with TestClient(app) as client:
        yield client


def _account(client, funded_usd: float = 1.0) -> str:
    signup = client.post("/ai-market/v2/accounts", json={"label": "buyer"}).json()
    client.post(
        f"/ai-market/v2/accounts/{signup['account_id']}/credit",
        json={"amount_usd": funded_usd},
        headers=ADMIN_HEADERS,
    )
    return signup["api_key"]


def test_internal_token_sent_only_to_gateway_hosts(monkeypatch, tmp_path):
    captured: list[dict] = []

    import aimarket_hub.outbound_http as outbound

    class _Resp:
        status_code = 200
        headers = {"content-type": "application/json"}
        text = '{"success": true}'

        @staticmethod
        def json():
            return {"success": True, "result": {"ok": True}}

    async def _post(url, **kwargs):
        captured.append({"url": url, "headers": dict(kwargs.get("headers") or {})})
        return _Resp()

    monkeypatch.setattr(outbound, "safe_post", _post)

    with _hub(
        monkeypatch,
        tmp_path,
        AIMARKET_CAPABILITY_TOKEN=CAP_TOKEN,
        AIMARKET_INVOKE_HOST_GATEWAY="kova-api",
        AIMARKET_ALLOW_LOCAL_PUBLISH="1",
    ) as client:
        seller = client.post("/ai-market/v2/accounts", json={"label": "kova"}).json()
        assert (
            client.post(
                "/ai-market/v2/supply/register",
                headers={"X-API-Key": seller["api_key"]},
                json={
                    "product_id": "kova-network",
                    "capability_id": "kova.network.status@v1",
                    "name": "status",
                    "description": "network",
                    "invoke_url": "http://kova-api:8000/capabilities/kova-network/kova.network.status@v1/invoke",
                    "price_per_call_usd": 0.001,
                    "input_schema": {"type": "object"},
                    "output_schema": {"type": "object"},
                },
            ).status_code
            == 200
        )
        buyer_key = _account(client)
        r = client.post(
            "/ai-market/v2/invoke",
            headers={"X-API-Key": buyer_key},
            json={
                "product_id": "kova-network",
                "capability_id": "kova.network.status@v1",
                "input": {},
                "source_hub": "local",
            },
        )
        assert r.status_code == 200, r.text

    assert captured
    assert captured[0]["headers"].get("X-AIMarket-Internal-Token") == CAP_TOKEN


def test_internal_token_not_sent_to_arbitrary_hosts(monkeypatch, tmp_path):
    captured: list[dict] = []

    import aimarket_hub.outbound_http as outbound
    import aimarket_hub.crawler as crawler

    # This is an outbound-header test, not a DNS integration test. Keep it
    # deterministic in offline/sandboxed CI while the runtime SSRF gate remains intact.
    monkeypatch.setattr(
        crawler, "_url_is_safe", lambda url: url == "https://example.com/invoke"
    )

    class _Resp:
        status_code = 200
        headers = {"content-type": "application/json"}
        text = '{"success": true}'

        @staticmethod
        def json():
            return {"success": True, "result": {"ok": True}}

    async def _post(url, **kwargs):
        captured.append({"url": url, "headers": dict(kwargs.get("headers") or {})})
        return _Resp()

    monkeypatch.setattr(outbound, "safe_post", _post)

    with _hub(
        monkeypatch,
        tmp_path,
        AIMARKET_CAPABILITY_TOKEN=CAP_TOKEN,
        AIMARKET_INVOKE_HOST_GATEWAY="kova-api",
    ) as client:
        seller = client.post("/ai-market/v2/accounts", json={"label": "ext"}).json()
        assert (
            client.post(
                "/ai-market/v2/supply/register",
                headers={"X-API-Key": seller["api_key"]},
                json={
                    "product_id": "ext-svc",
                    "capability_id": "ext.svc@v1",
                    "name": "ext",
                    "description": "external",
                    "invoke_url": "https://example.com/invoke",
                    "price_per_call_usd": 0.001,
                    "input_schema": {"type": "object"},
                    "output_schema": {"type": "object"},
                },
            ).status_code
            == 200
        )
        buyer_key = _account(client)
        r = client.post(
            "/ai-market/v2/invoke",
            headers={"X-API-Key": buyer_key},
            json={
                "product_id": "ext-svc",
                "capability_id": "ext.svc@v1",
                "input": {},
                "source_hub": "local",
            },
        )
        assert r.status_code == 200, r.text

    assert captured
    assert "X-AIMarket-Internal-Token" not in captured[0]["headers"]
