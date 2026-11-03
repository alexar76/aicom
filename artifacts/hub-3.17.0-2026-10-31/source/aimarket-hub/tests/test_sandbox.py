"""Sandbox try-before-buy API tests."""

import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aimarket_hub.api import create_app
from aimarket_hub.config import HubConfig
from aimarket_hub.database import HubDatabase
from aimarket_hub.signing import Signer


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("AIMARKET_SANDBOX_STUB_INVOKE", "1")
    monkeypatch.delenv("AIFACTORY_PUBLIC_URL", raising=False)
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test.db"
        key_path = Path(tmp) / "test_key"
        sandbox_db = Path(tmp) / "sandbox.db"
        monkeypatch.setenv("AIMARKET_SANDBOX_DB_PATH", str(sandbox_db))
        # Pin the ledger to this test's temp DB. (The module _DB_PATH constant is
        # import-bound, so resetting to None alone would reuse a shared default file
        # and make per-IP rate-limit assertions depend on prior runs.)
        import aimarket_hub.sandbox_trials as st
        st._ledger = st.SandboxTrialLedger(str(sandbox_db))
        config = HubConfig()
        config.db_path = str(db_path)
        config.signing_key_path = str(key_path)
        db = HubDatabase(str(db_path))
        signer = Signer(key_path)
        app = create_app(config=config, db=db, signer=signer)
        with TestClient(app) as c:
            yield c


class TestSandbox:
    def test_quota_new_visitor(self, client):
        r = client.get("/ai-market/v2/sandbox/quota", params={"visitor_id": "vis_testquota01"})
        assert r.status_code == 200
        data = r.json()
        assert data["enabled"] is True
        assert data["remaining"] >= 1

    def test_sandbox_invoke_no_payment(self, client):
        vid = "vis_invoke_" + os.urandom(6).hex()
        r = client.post(
            "/ai-market/v2/invoke",
            headers={"X-AIMarket-Sandbox-Visitor": vid},
            json={
                "product_id": "prod-translate",
                "capability_id": "translate.multi@v2",
                "source_hub": "local",
                "input": {"text": "hello sandbox"},
            },
        )
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is True
        assert body.get("sandbox") is True
        assert body["price_usd"] == 0
        assert body["list_price_usd"] > 0

    def test_sandbox_exhausts_quota(self, client):
        vid = "vis_exhaust_" + os.urandom(4).hex()
        for _ in range(3):
            r = client.post(
                "/ai-market/v2/invoke",
                headers={"X-AIMarket-Sandbox-Visitor": vid},
                json={
                    "product_id": "prod-translate",
                    "capability_id": "translate.multi@v2",
                    "source_hub": "local",
                    "input": {"text": "trial"},
                },
            )
            assert r.status_code == 200
        r = client.post(
            "/ai-market/v2/invoke",
            headers={"X-AIMarket-Sandbox-Visitor": vid},
            json={
                "product_id": "prod-translate",
                "capability_id": "translate.multi@v2",
                "source_hub": "local",
                "input": {"text": "over limit"},
            },
        )
        assert r.status_code == 429
        assert r.json()["error"] == "trial_quota_exhausted"


def test_a_free_capability_takes_no_trial(monkeypatch, tmp_path):
    """A $0 SKU must stay reachable after the visitor's allowance is gone.

    Every hub that routes to a peer sends a sandbox visitor header. When a free capability
    consumed a trial, hub.attestedmemory.net's visitor on hunt used its lifetime three on
    hunt's FREE `signal.leaderboard@v1` and every routed call after that came back 429
    `trial_quota_exhausted` — which hunt's own assay of the attested hub then read as
    that hub being broken.
    """
    from aimarket_hub.models import Capability
    import aimarket_hub.sandbox_trials as st

    monkeypatch.setenv("AIMARKET_SANDBOX_STUB_INVOKE", "1")
    monkeypatch.delenv("AIFACTORY_PUBLIC_URL", raising=False)
    monkeypatch.setenv("AIMARKET_SANDBOX_DB_PATH", str(tmp_path / "sandbox.db"))
    st._ledger = st.SandboxTrialLedger(str(tmp_path / "sandbox.db"))
    config = HubConfig()
    config.db_path = str(tmp_path / "test.db")
    config.signing_key_path = str(tmp_path / "key")
    db = HubDatabase(config.db_path)
    app = create_app(config=config, db=db, signer=Signer(tmp_path / "key"))
    vid = "vis_free_" + os.urandom(4).hex()

    def call(capability_id, product_id):
        return c.post(
            "/ai-market/v2/invoke",
            headers={"X-AIMarket-Sandbox-Visitor": vid},
            json={"product_id": product_id, "capability_id": capability_id,
                  "source_hub": "local", "input": {"text": "x"}},
        )

    with TestClient(app) as c:
        # After startup: the demo seeder only fills an EMPTY catalogue.
        db.upsert_capability(Capability(
            capability_id="free.echo@v1", product_id="prod-translate", name="free.echo",
            version="v1", description="free", price_per_call_usd=0.0,
            source_hub="local", source_hub_name="test",
        ))
        for _ in range(3):
            assert call("translate.multi@v2", "prod-translate").status_code == 200
        # Allowance gone for the priced SKU…
        assert call("translate.multi@v2", "prod-translate").status_code == 429
        # …and the free one still answers, and did not touch the ledger.
        for _ in range(5):
            assert call("free.echo@v1", "prod-translate").status_code != 429
        assert st.sandbox_quota(vid)["used"] == 3
