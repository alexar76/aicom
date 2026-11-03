"""HTTP wiring tests for the ACEX Agent IPO leg (factory → hub → ACEX).

Verifies: admin-gated IPO float, listing/cap-table endpoints, paid-invoke revenue
routing into the CapShares pool, distribution + claim, sandbox trials accrue nothing,
and the Pulse Terminal pricing overlay reflecting live ACEX state.
"""

import importlib
import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ADMIN_TOKEN = "test-admin-token-not-for-production"
ADMIN = {"Authorization": f"Bearer {ADMIN_TOKEN}"}


class _FakeResp:
    status_code = 200
    text = ""

    def json(self):
        return {"output": {"translated": "hola"}}


class _FakeAsyncClient:
    """Stand-in for httpx.AsyncClient so paid invokes don't need a live factory."""

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, *a, **k):
        return _FakeResp()


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("AIFACTORY_CRYPTO_ENABLED", "0")
    monkeypatch.setenv("AIMARKET_ADMIN_TOKEN", ADMIN_TOKEN)
    monkeypatch.setenv("AIMARKET_SANDBOX_STUB_INVOKE", "1")
    monkeypatch.setenv("AIFACTORY_PUBLIC_URL", "http://factory.test")
    monkeypatch.setenv("ACEX_REQUIRE_AI_AUDIT", "0")
    monkeypatch.setenv("ACEX_AI_AUDIT_FEDERATED_SEARCH", "0")
    with tempfile.TemporaryDirectory() as tmp:
        monkeypatch.setenv("ACEX_IPO_DB_PATH", str(Path(tmp) / "acex_ipo.db"))
        monkeypatch.setenv("ACEX_AUDIT_DB_PATH", str(Path(tmp) / "acex_audit.db"))
        monkeypatch.setenv("AIMARKET_SANDBOX_DB_PATH", str(Path(tmp) / "sandbox.db"))

        # Reload acex_ipo so ACEX_IPO_DB_PATH takes effect; api.py imports it lazily.
        import aimarket_hub.acex_ipo as ipo
        import aimarket_hub.acex_audit as audit
        importlib.reload(ipo)
        importlib.reload(audit)
        audit._ledger = audit.AcexAuditLedger(str(Path(tmp) / "acex_audit.db"))
        # Pin the sandbox ledger to an isolated temp DB (the module _DB_PATH constant
        # is import-bound, so resetting to None alone would reuse a shared default file).
        import aimarket_hub.sandbox_trials as st
        st._ledger = st.SandboxTrialLedger(str(Path(tmp) / "sandbox.db"))

        from aimarket_hub.api import create_app
        from aimarket_hub.config import HubConfig
        from aimarket_hub.database import HubDatabase
        from aimarket_hub.signing import Signer
        import aimarket_hub.api as api_mod

        # Paid invokes call the factory via httpx — replace with the fake.
        monkeypatch.setattr(api_mod.httpx, "AsyncClient", _FakeAsyncClient)

        config = HubConfig()
        config.db_path = str(Path(tmp) / "test.db")
        config.signing_key_path = str(Path(tmp) / "key")
        db = HubDatabase(config.db_path)
        signer = Signer(config.signing_key_path)
        app = create_app(config=config, db=db, signer=signer)
        with TestClient(app) as c:
            yield c


@pytest.fixture
def crypto_client(monkeypatch):
    """Paid channel flows — crypto must be on."""
    monkeypatch.setenv("AIFACTORY_CRYPTO_ENABLED", "1")
    monkeypatch.setenv("AIMARKET_ALLOW_DEMO_CREDIT", "1")
    monkeypatch.setenv("AIMARKET_ADMIN_TOKEN", ADMIN_TOKEN)
    monkeypatch.setenv("AIMARKET_SANDBOX_STUB_INVOKE", "1")
    monkeypatch.setenv("AIFACTORY_PUBLIC_URL", "http://factory.test")
    monkeypatch.setenv("ACEX_REQUIRE_AI_AUDIT", "0")
    monkeypatch.setenv("ACEX_AI_AUDIT_FEDERATED_SEARCH", "0")
    with tempfile.TemporaryDirectory() as tmp:
        monkeypatch.setenv("ACEX_IPO_DB_PATH", str(Path(tmp) / "acex_ipo.db"))
        monkeypatch.setenv("ACEX_AUDIT_DB_PATH", str(Path(tmp) / "acex_audit.db"))
        monkeypatch.setenv("AIMARKET_SANDBOX_DB_PATH", str(Path(tmp) / "sandbox.db"))

        import aimarket_hub.acex_ipo as ipo
        import aimarket_hub.acex_audit as audit
        importlib.reload(ipo)
        importlib.reload(audit)
        audit._ledger = audit.AcexAuditLedger(str(Path(tmp) / "acex_audit.db"))
        import aimarket_hub.sandbox_trials as st
        st._ledger = st.SandboxTrialLedger(str(Path(tmp) / "sandbox.db"))

        from aimarket_hub.api import create_app
        from aimarket_hub.config import HubConfig
        from aimarket_hub.database import HubDatabase
        from aimarket_hub.signing import Signer
        import aimarket_hub.api as api_mod

        monkeypatch.setattr(api_mod.httpx, "AsyncClient", _FakeAsyncClient)

        config = HubConfig()
        config.db_path = str(Path(tmp) / "test.db")
        config.signing_key_path = str(Path(tmp) / "key")
        db = HubDatabase(config.db_path)
        signer = Signer(config.signing_key_path)
        app = create_app(config=config, db=db, signer=signer)
        with TestClient(app) as c:
            yield c


def _float(client, product_id="prod-translate", **kw):
    body = {"product_id": product_id, **kw}
    return client.post("/ai-market/v2/capital/ipo", json=body, headers=ADMIN)


class TestIpoEndpoints:
    def test_ipo_requires_admin(self, client):
        assert client.post("/ai-market/v2/capital/ipo", json={"product_id": "prod-translate"}).status_code == 401
        bad = client.post("/ai-market/v2/capital/ipo", json={"product_id": "prod-translate"},
                          headers={"Authorization": "Bearer wrong"})
        assert bad.status_code == 403

    def test_float_creates_listing_and_captable(self, client):
        r = _float(client)
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "approved"
        assert data["shares_outstanding"] == 1_000_000
        assert data["already_listed"] is False

        lst = client.get("/ai-market/v2/capital/listings/prod-translate").json()
        assert lst["holder_count"] == 1
        assert lst["revenue"]["gross_revenue_usd"] == 0.0

    def test_alias_path_also_works(self, client):
        _float(client)
        r = client.get("/api/v2/capital/listings/prod-translate")
        assert r.status_code == 200
        assert r.json()["product_id"] == "prod-translate"


class TestRevenueRouting:
    def test_paid_invoke_accrues_then_distributes(self, crypto_client):
        client = crypto_client
        _float(client, revenue_share_bps=5000)  # 50% to shareholders

        # Open a funded channel — the open endpoint mints a one-time debit secret which the
        # invoke must present (X-Payment-Channel-Secret), else the debit is rejected.
        ch = client.post("/ai-market/v2/channel/open", json={"deposit_usd": 5.0}).json()
        channel_id = ch["channel"]["channel_id"]
        channel_secret = ch["channel"]["channel_secret"]

        # Paid invoke (price 0.40) → 50% = 0.20 into the pool.
        r = client.post(
            "/ai-market/v2/invoke",
            headers={"X-Payment-Channel": channel_id, "X-Payment-Channel-Secret": channel_secret},
            json={
                "product_id": "prod-translate",
                "capability_id": "translate.multi@v2",
                "source_hub": "local",
                "input": {"text": "hello"},
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["price_usd"] == 0.40
        assert body["acex_revenue"]["to_pool_usd"] == 0.20

        rev = client.get("/ai-market/v2/capital/listings/prod-translate").json()["revenue"]
        assert rev["gross_revenue_usd"] == 0.40
        assert rev["accrued_undistributed_usd"] == 0.20

        # Distribute to the sole holder (treasury), then it becomes claimable.
        dist = client.post("/ai-market/v2/capital/listings/prod-translate/distribute", headers=ADMIN).json()
        assert dist["distributed_usd"] == 0.20

        pos = client.get("/ai-market/v2/capital/holdings", params={"holder": "factory-treasury"}).json()
        assert pos["positions"][0]["claimable_usd"] == 0.20

    def test_sandbox_invoke_accrues_nothing(self, client):
        _float(client)
        r = client.post(
            "/ai-market/v2/invoke",
            headers={"X-AIMarket-Sandbox-Visitor": "vis_acex_nofee_01"},
            json={
                "product_id": "prod-translate",
                "capability_id": "translate.multi@v2",
                "source_hub": "local",
                "input": {"text": "trial"},
            },
        )
        assert r.status_code == 200
        assert "acex_revenue" not in r.json()  # free trial → no shareholder revenue

        rev = client.get("/ai-market/v2/capital/listings/prod-translate").json()["revenue"]
        assert rev["gross_revenue_usd"] == 0.0

    def test_distribute_unknown_listing_404(self, client):
        r = client.post("/ai-market/v2/capital/listings/prod-nope/distribute", headers=ADMIN)
        assert r.status_code == 404


class TestPricingOverlay:
    def test_pricing_reflects_live_acex_listing(self, client):
        _float(client)
        snap = client.get("/api/v2/capital/pricing").json()
        assert snap["acex_listings_live"] >= 1
        row = next(x for x in snap["listings"] if x["listing_id"] == "prod-translate")
        assert row["acex_listed"] is True
        assert row["shares_outstanding"] == 1_000_000

    def test_pricing_includes_proof_of_audit(self, client):
        _float(client)
        snap = client.get("/api/v2/capital/pricing").json()
        row = next(x for x in snap["listings"] if x["listing_id"] == "prod-translate")
        poa = row["proof_of_audit"]
        assert poa["enabled"] is True
        assert poa["aggregate_score_bps"] >= 7000
        assert snap["proof_of_audit"]["listings_with_coverage"] >= 1


class TestAuditApi:
    def test_invoke_accrues_audit_rewards(self, crypto_client):
        client = crypto_client
        _float(client)
        ch = client.post("/ai-market/v2/channel/open", json={"deposit_usd": 5.0}).json()
        channel_id = ch["channel"]["channel_id"]
        channel_secret = ch["channel"]["channel_secret"]
        r = client.post(
            "/ai-market/v2/invoke",
            headers={"X-Payment-Channel": channel_id, "X-Payment-Channel-Secret": channel_secret},
            json={
                "product_id": "prod-translate",
                "capability_id": "translate.multi@v2",
                "source_hub": "local",
                "input": {"text": "paid"},
            },
        )
        assert r.status_code == 200
        body = r.json()
        assert body["acex_audit_rewards"]["to_auditors_usd"] == 0.004  # 1% of $0.40 list price

    def test_audit_detail_and_claim(self, crypto_client):
        client = crypto_client
        _float(client)
        ch = client.post("/ai-market/v2/channel/open", json={"deposit_usd": 5.0}).json()
        channel_id = ch["channel"]["channel_id"]
        channel_secret = ch["channel"]["channel_secret"]
        client.post(
            "/ai-market/v2/invoke",
            headers={"X-Payment-Channel": channel_id, "X-Payment-Channel-Secret": channel_secret},
            json={
                "product_id": "prod-translate",
                "capability_id": "translate.multi@v2",
                "source_hub": "local",
                "input": {"text": "paid"},
            },
        )
        detail = client.get("/api/v2/capital/audit/prod-translate").json()
        assert detail["enabled"] is True
        # SEC-05: claim is admin-gated; unauthenticated callers are rejected.
        unauth = client.post(
            "/api/v2/capital/audit/prod-translate/claim",
            json={"auditor": "ai-auditor:acex-v1"},
        )
        assert unauth.status_code in (401, 403)
        claim = client.post(
            "/api/v2/capital/audit/prod-translate/claim",
            json={"auditor": "ai-auditor:acex-v1"},
            headers=ADMIN,
        ).json()
        assert claim["ok"] is True
        assert claim["claimed_usd"] == 0.004


class TestAiAuditorGate:
    def test_human_score_is_forbidden(self, client, monkeypatch):
        monkeypatch.setenv("ACEX_REQUIRE_AI_AUDIT", "1")
        r = _float(client, audit_score_bps=9000)
        assert r.status_code == 400
        assert r.json()["error"] == "human_audit_override_forbidden"

    def test_empty_catalog_is_rejected(self, client, monkeypatch):
        monkeypatch.setenv("ACEX_REQUIRE_AI_AUDIT", "1")
        monkeypatch.setenv("ACEX_AI_AUDIT_FEDERATED_SEARCH", "0")
        r = _float(client, "prod-no-caps-here")
        assert r.status_code == 400
        body = r.json()
        assert body["error"] == "ai_audit_rejected"
        assert body["verdict"] == "reject"


class TestLedgerUnavailable:
    """A production hub with no Postgres URL refuses to open the ACEX ledgers
    (acex_storage.require_postgres_url). modelmarket.dev answered that refusal on the
    public GET /capital/audit with an unhandled RuntimeError — a 500, 2026-09-30."""

    @pytest.fixture
    def unopenable(self, client, monkeypatch):
        import aimarket_hub.acex_audit as audit
        import aimarket_hub.acex_ipo as ipo

        monkeypatch.setenv("AIFACTORY_PROD", "1")
        for name in ("AIMARKET_ACEX_AUDIT_DATABASE_URL", "AIMARKET_ACEX_IPO_DATABASE_URL",
                     "DATABASE_URL"):
            monkeypatch.delenv(name, raising=False)
        monkeypatch.setattr(audit, "_ledger", None)
        monkeypatch.setattr(ipo, "_ledger", None)
        return client

    @pytest.mark.parametrize("path, error", [
        ("/ai-market/v2/capital/audit", "audit_unavailable"),
        ("/ai-market/v2/capital/audit/lst-x", "audit_unavailable"),
        ("/ai-market/v2/capital/listings", "listings_unavailable"),
        ("/ai-market/v2/capital/listings/lst-x", "listings_unavailable"),
        ("/ai-market/v2/capital/holdings?holder=0xabc", "listings_unavailable"),
    ])
    def test_a_public_read_is_a_503_that_keeps_the_config_to_itself(self, unopenable, path, error):
        r = unopenable.get(path)
        assert r.status_code == 503, r.text
        body = r.json()
        assert body["error"] == error
        assert "DATABASE_URL" not in r.text and "AIFACTORY_PROD" not in r.text

    def test_an_unconfigured_ledger_is_a_state_not_a_traceback(self, unopenable, caplog):
        """modelmarket.dev runs without ACEX ledgers: every public read logged a full traceback
        (311 in a day before 2026-10-23). Now the reads still answer 503, and the reason is
        logged once per ledger per process, as a warning."""
        import logging

        import aimarket_hub.acex_storage as storage

        storage._warned.clear()
        caplog.set_level(logging.WARNING)
        for _ in range(3):
            for path in ("/ai-market/v2/capital/listings", "/ai-market/v2/capital/audit",
                         "/ai-market/v2/capital/holdings?holder=0xabc"):
                assert unopenable.get(path).status_code == 503
        assert unopenable.get("/ai-market/v2/capital/pricing").status_code == 200
        assert not [r for r in caplog.records if r.levelno >= logging.ERROR or r.exc_info]
        warned = [r.getMessage() for r in caplog.records if "ACEX" in r.getMessage() and r.levelno == logging.WARNING]
        assert len(warned) == 2, warned          # one for the IPO ledger, one for the audit ledger
