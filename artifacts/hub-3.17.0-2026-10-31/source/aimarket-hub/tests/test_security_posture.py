"""The fleet alerter watched uptime and money and no security event at all.

`GET /ai-market/v2/security/posture` gives it the aggregate signals of an attack on the
open signup and the credit rail, and nothing that names anyone: how many signups the
per-address limit refused in the last hour, how many requests carried an X-API-Key no
account owns, and how much of the daily signup-grant budget is gone.
"""
from __future__ import annotations

from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

from aimarket_hub import security_posture
from aimarket_hub.api import create_app
from aimarket_hub.config import HubConfig
from aimarket_hub.database import HubDatabase
from aimarket_hub.models import Capability
from aimarket_hub.signing import Signer


@contextmanager
def _hub(monkeypatch, tmp_path, **env):
    monkeypatch.setenv("AIMARKET_ADMIN_TOKEN", "test-admin-token-not-for-production")
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    security_posture.reset()
    root = tmp_path / "hub"
    root.mkdir(parents=True, exist_ok=True)
    config = HubConfig()
    config.db_path = str(root / "hub.db")
    config.signing_key_path = str(root / "key")
    db = HubDatabase(root / "hub.db")
    app = create_app(config=config, db=db, signer=Signer(root / "key"))
    with TestClient(app) as client:
        yield client, db


def _posture(client) -> dict:
    r = client.get("/ai-market/v2/security/posture")
    assert r.status_code == 200, r.text
    return r.json()


def test_a_fresh_hub_reports_a_quiet_hour(monkeypatch, tmp_path):
    with _hub(monkeypatch, tmp_path, AIMARKET_CREDITS_ENABLED="1") as (client, _db):
        body = _posture(client)
        assert body["window_s"] == 3600
        assert body["signups_refused"] == 0
        assert body["bad_api_key_attempts"] == 0


def test_signups_the_address_limit_refuses_are_counted(monkeypatch, tmp_path):
    with _hub(monkeypatch, tmp_path, AIMARKET_CREDITS_ENABLED="1",
              AIMARKET_CREDITS_SIGNUPS_PER_HOUR="2",
              AIMARKET_CREDITS_FREE_GRANT_USD="0") as (client, _db):
        codes = [client.post("/ai-market/v2/accounts", json={"label": f"b{i}"}).status_code
                 for i in range(5)]
        assert codes.count(200) == 2
        assert _posture(client)["signups_refused"] == 3


def test_requests_with_a_key_no_account_owns_are_counted(monkeypatch, tmp_path):
    with _hub(monkeypatch, tmp_path, AIMARKET_CREDITS_ENABLED="1") as (client, db):
        db.upsert_capability(Capability(
            capability_id="demo.echo@v1", product_id="demo-echo", name="Echo",
            description="Returns what it is given", price_per_call_usd=0.004,
            source_hub="local", invoke_url="", prompt_template='{"ok": true}',
        ))
        body = {"product_id": "demo-echo", "capability_id": "demo.echo@v1",
                "input": {}, "source_hub": "local"}
        # A guessing sweep: a different key each time, each one counted once even though
        # the hub looks a key up more than once per request.
        for i in range(3):
            r = client.post("/ai-market/v2/invoke", json=body,
                            headers={"X-API-Key": "aimk_" + str(i) * 32})
            assert r.status_code == 401
        assert _posture(client)["bad_api_key_attempts"] == 3
        # The same wrong key retried straight away is one mistake, not three guesses.
        for _ in range(3):
            client.post("/ai-market/v2/invoke", json=body, headers={"X-API-Key": "aimk_" + "z" * 32})
        assert _posture(client)["bad_api_key_attempts"] == 4


def test_the_grant_budget_spent_today_is_reported(monkeypatch, tmp_path):
    with _hub(monkeypatch, tmp_path, AIMARKET_CREDITS_ENABLED="1",
              AIMARKET_CREDITS_FREE_GRANT_USD="1.0",
              AIMARKET_SIGNUP_GRANT_DAILY_USD="4.0") as (client, _db):
        assert client.post("/ai-market/v2/accounts", json={"label": "a"}).status_code == 200
        grant = _posture(client)["signup_grant"]
        assert grant["daily_budget_usd"] == pytest.approx(4.0)
        assert grant["granted_24h_usd"] == pytest.approx(1.0)
        assert grant["spent_fraction"] == pytest.approx(0.25)


def test_the_posture_names_no_one(monkeypatch, tmp_path):
    with _hub(monkeypatch, tmp_path, AIMARKET_CREDITS_ENABLED="1") as (client, _db):
        client.post("/ai-market/v2/invoke", json={"product_id": "x", "capability_id": "x@v1",
                                                   "input": {}}, headers={"X-API-Key": "aimk_wrong"})
        text = client.get("/ai-market/v2/security/posture").text
        assert "aimk_" not in text and "testclient" not in text
