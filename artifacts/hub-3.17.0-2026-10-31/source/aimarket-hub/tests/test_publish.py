"""Developer publish + invoke_url routing."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aimarket_hub.api import create_app
from aimarket_hub.config import HubConfig
from aimarket_hub.database import HubDatabase
from aimarket_hub.publish import validate_manifest
from aimarket_hub.signing import Signer

PUBLISH_TOKEN = "test-publish-token"
PUBLISH_HEADERS = {"Authorization": f"Bearer {PUBLISH_TOKEN}"}


class _ProviderResp:
    status_code = 200
    text = ""

    def __init__(self, payload: dict, headers: dict | None = None):
        self._payload = payload
        self.headers = headers or {}

    def json(self):
        return self._payload


class _RoutingAsyncClient:
    """Routes httpx posts: provider invoke_url vs factory."""

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, *a, **k):
        if url.endswith("/invoke") and "127.0.0.1:3456" in url:
            inp = (k.get("json") or {}).get("input", {})
            name = inp.get("name", "world")
            return _ProviderResp({"success": True, "result": {"greeting": f"Hello, {name}!"}})
        return _ProviderResp({"output": {"translated": "hola"}})


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("AIMARKET_PUBLISH_TOKEN", PUBLISH_TOKEN)
    monkeypatch.setenv("AIMARKET_ALLOW_LOCAL_PUBLISH", "1")
    monkeypatch.setenv("AIMARKET_SANDBOX_STUB_INVOKE", "1")
    monkeypatch.setenv("AIMARKET_SUPPLY_SECURITY_RELAXED", "1")
    monkeypatch.setenv("AIMARKET_SUPPLY_REQUIRE_RESPONSE_SIG", "0")
    monkeypatch.setenv("AIFACTORY_PUBLIC_URL", "http://factory.test")
    monkeypatch.setenv("AIFACTORY_CRYPTO_ENABLED", "0")
    import aimarket_hub.api as api_mod

    monkeypatch.setattr(api_mod.httpx, "AsyncClient", _RoutingAsyncClient)

    with tempfile.TemporaryDirectory() as tmp:
        config = HubConfig()
        config.db_path = str(Path(tmp) / "test.db")
        config.signing_key_path = str(Path(tmp) / "key")
        db = HubDatabase(config.db_path)
        signer = Signer(config.signing_key_path)
        app = create_app(config=config, db=db, signer=signer)
        with TestClient(app) as c:
            yield c


MANIFEST = {
    "product_id": "demo-hello",
    "capability_id": "greet@v1",
    "name": "greet",
    "description": "Says hello",
    "invoke_url": "http://127.0.0.1:3456/invoke",
    "price_per_call_usd": 0.01,
    "publisher_id": "demo-publisher",
    "provider_pubkey": "dGVzdA==",
    "input_schema": {"type": "object", "properties": {"name": {"type": "string"}}},
    "output_schema": {"type": "object", "properties": {"greeting": {"type": "string"}}},
}


class TestPublishManifest:
    @pytest.mark.parametrize("price", ["NaN", "Infinity", "-Infinity", True])
    def test_nonfinite_or_boolean_price_never_enters_the_catalogue(self, monkeypatch, price):
        monkeypatch.setenv("AIMARKET_ALLOW_LOCAL_PUBLISH", "1")
        with pytest.raises(ValueError, match="price_per_call_usd"):
            validate_manifest({**MANIFEST, "price_per_call_usd": price})

    def test_validate_manifest(self, monkeypatch):
        monkeypatch.setenv("AIMARKET_ALLOW_LOCAL_PUBLISH", "1")
        cap = validate_manifest(MANIFEST)
        assert cap.product_id == "demo-hello"
        assert cap.invoke_url.endswith("/invoke")

    def test_register_and_invoke(self, client):
        reg = client.post("/ai-market/v2/supply/register", json=MANIFEST, headers=PUBLISH_HEADERS)
        assert reg.status_code == 200
        assert reg.json()["published"] is True

        inv = client.post("/ai-market/v2/invoke", json={
            "product_id": "demo-hello",
            "capability_id": "greet@v1",
            "source_hub": "local",
            "input": {"name": "dev"},
        })
        assert inv.status_code == 200
        data = inv.json()
        assert data["success"] is True
        assert data["result"]["greeting"] == "Hello, dev!"

    def test_register_requires_token_in_prod(self, client, monkeypatch):
        monkeypatch.setenv("AIFACTORY_PROD", "1")
        monkeypatch.delenv("AIMARKET_PUBLISH_TOKEN", raising=False)
        # Re-create app so _require_publish picks up env without token
        import aimarket_hub.api as api_mod
        from aimarket_hub.config import HubConfig
        from aimarket_hub.database import HubDatabase
        from aimarket_hub.signing import Signer
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            config = HubConfig()
            config.db_path = str(Path(tmp) / "prod.db")
            config.signing_key_path = str(Path(tmp) / "key")
            db = HubDatabase(config.db_path)
            signer = Signer(config.signing_key_path)
            monkeypatch.setattr(api_mod.httpx, "AsyncClient", _RoutingAsyncClient)
            from fastapi.testclient import TestClient
            app = api_mod.create_app(config=config, db=db, signer=signer)
            with TestClient(app) as prod_client:
                resp = prod_client.post("/ai-market/v2/supply/register", json=MANIFEST)
                assert resp.status_code == 503

    def test_missing_token_is_401_only_when_a_credential_actually_exists(
        self, client, monkeypatch, tmp_path
    ):
        """503 "disabled" and 401 "missing token" must not be confused.

        The per-subject credential gate answers a token-less production request. If NO
        registry is configured, no token the caller could ever present would work — the
        operator has to act — so the honest answer is 503, and a 401 would send the
        client into a retry loop it cannot win. Once the subject IS registered, the
        token is genuinely what is missing and 401 is correct. Both directions are
        pinned here because the gate previously raised 401 before it had even looked at
        the registries.
        """
        import aimarket_hub.api as api_mod
        from aimarket_hub.config import HubConfig
        from aimarket_hub.database import HubDatabase
        from aimarket_hub.signing import Signer
        from fastapi.testclient import TestClient

        monkeypatch.setenv("AIFACTORY_PROD", "1")
        monkeypatch.delenv("AIMARKET_PUBLISH_TOKEN", raising=False)
        monkeypatch.delenv("AIMARKET_ADMIN_TOKEN", raising=False)
        monkeypatch.setattr(api_mod.httpx, "AsyncClient", _RoutingAsyncClient)

        def _prod_client(idx: int):
            config = HubConfig()
            config.db_path = str(tmp_path / f"gate{idx}.db")
            config.signing_key_path = str(tmp_path / f"key{idx}")
            return TestClient(api_mod.create_app(
                config=config,
                db=HubDatabase(config.db_path),
                signer=Signer(config.signing_key_path),
            ))

        publisher_id = MANIFEST["publisher_id"]

        # Nothing configured: the caller cannot fix this, the operator must.
        with _prod_client(0) as c:
            assert c.post("/ai-market/v2/supply/register", json=MANIFEST).status_code == 503

        # The subject now has a credential, so the omission is the caller's.
        monkeypatch.setenv("AIMARKET_PUBLISHER_TOKENS", f"{publisher_id}:s3cret")
        with _prod_client(1) as c:
            assert c.post("/ai-market/v2/supply/register", json=MANIFEST).status_code == 401
            wrong = c.post(
                "/ai-market/v2/supply/register", json=MANIFEST,
                headers={"Authorization": "Bearer nope"},
            )
            assert wrong.status_code == 403
