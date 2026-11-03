"""A caller says why it made a call, and the live feed shows it.

2026-10-12 on modelmarket.dev: the PingBlip owner saw two `gaia.weather.read` rows seconds
apart for one feed and read it as one meal charged twice. One was the hourly home-page
reading, the other the meal. Nothing on the feed could tell them apart. The caller now sends
a short public label (`purpose`), and the feed prints it. It is the caller's claim and it is
published, so anything but a short slug is dropped. A bad label never fails the call.
"""
from __future__ import annotations

from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

from aimarket_hub.api import create_app
from aimarket_hub.config import HubConfig
from aimarket_hub.database import HubDatabase
from aimarket_hub.models import Capability, normalize_purpose
from aimarket_hub.signing import Signer

INVOKE = {"product_id": "demo-echo", "capability_id": "demo.free@v1",
          "input": {"text": "hi"}, "source_hub": "local"}


@contextmanager
def _hub(monkeypatch, tmp_path):
    monkeypatch.setenv("AIMARKET_ADMIN_TOKEN", "test-admin-token-not-for-production")
    config = HubConfig()
    config.db_path = str(tmp_path / "hub.db")
    config.signing_key_path = str(tmp_path / "key")
    db = HubDatabase(tmp_path / "hub.db")
    db.upsert_capability(Capability(
        capability_id="demo.free@v1", product_id="demo-echo", name="Free",
        description="Costs nothing", price_per_call_usd=0.0,
        source_hub="local", invoke_url="", prompt_template='{"ok": true}',
    ))
    app = create_app(config=config, db=db, signer=Signer(tmp_path / "key"))
    with TestClient(app) as client:
        yield client, db


@pytest.mark.parametrize(("raw", "kept"), [
    ("feed", "feed"),
    ("home-weather", "home-weather"),
    ("  Feed ", "feed"),
    ("proof-verify", "proof-verify"),
    ("", ""),
    (None, ""),
    (42, ""),
    ("https://evil.example/x", ""),
    ("feed the cat", ""),
    ("9lives", ""),
    ("-feed", ""),
    ("a" * 25, ""),
    ("корм", ""),
])
def test_only_a_short_slug_survives(raw, kept):
    assert normalize_purpose(raw) == kept


def test_the_label_reaches_the_row_and_the_public_feed(monkeypatch, tmp_path):
    with _hub(monkeypatch, tmp_path) as (client, db):
        r = client.post("/ai-market/v2/invoke", json={**INVOKE, "purpose": "home-weather"})
        assert r.status_code == 200, r.text
        r = client.post("/ai-market/v2/invoke", json={**INVOKE, "purpose": "feed"})
        assert r.status_code == 200, r.text

        assert [row["purpose"] for row in db.recent_stats(limit=5)] == ["feed", "home-weather"]
        events = client.get("/ai-market/v2/stats/live").json()["events"]
        assert [e["purpose"] for e in events[:2]] == ["feed", "home-weather"]


def test_a_bad_label_is_dropped_not_refused(monkeypatch, tmp_path):
    with _hub(monkeypatch, tmp_path) as (client, db):
        r = client.post("/ai-market/v2/invoke",
                        json={**INVOKE, "purpose": "visit https://evil.example now"})
        assert r.status_code == 200, r.text
        assert db.recent_stats(limit=1)[0]["purpose"] == ""
        event = client.get("/ai-market/v2/stats/live").json()["events"][0]
        assert event["purpose"] == ""
        assert "evil" not in str(event)


def test_no_label_is_an_empty_label(monkeypatch, tmp_path):
    with _hub(monkeypatch, tmp_path) as (client, db):
        assert client.post("/ai-market/v2/invoke", json=INVOKE).status_code == 200
        assert db.recent_stats(limit=1)[0]["purpose"] == ""
