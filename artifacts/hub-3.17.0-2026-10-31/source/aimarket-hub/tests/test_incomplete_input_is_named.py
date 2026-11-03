"""A call that omits what the capability requires is refused HERE, by name.

`atlas.watchbox.check@v1` invoked without coordinates used to spend about a second
crossing the federation to be told "lat/lon required", and the caller got back a generic
failure with the real cause buried in a refuse_reason string. Fifteen of those on the
production hub. They were classified correctly — `incomplete`, outside the success rate —
but nobody was ever told which field was missing.

The schema already says. These tests hold the hub to answering from it, before routing,
for the local and the federated route alike, and to still writing the unscored row that
the live ticker has always shown.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aimarket_hub.api import create_app
from aimarket_hub.config import HubConfig
from aimarket_hub.database import HubDatabase
from aimarket_hub.models import Capability, Peer
from aimarket_hub.signing import Signer

SCHEMA = {
    "type": "object",
    "required": ["lat", "lon"],
    "properties": {"lat": {"type": "number"}, "lon": {"type": "number"}},
}


@pytest.fixture()
def hub(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AIFACTORY_CRYPTO_ENABLED", "0")
    monkeypatch.setenv("AIMARKET_ADMIN_TOKEN", "t" * 32)
    config = HubConfig()
    config.db_path = str(tmp_path / "hub.db")
    config.signing_key_path = str(tmp_path / "key")
    db = HubDatabase(config.db_path)
    app = create_app(config=config, db=db, signer=Signer(config.signing_key_path))
    return app, db


def _publish(db, *, source_hub, schema=SCHEMA):
    db.upsert_capability(Capability(
        capability_id="watchbox.check@v1",
        product_id="prod-atlas",
        name="watchbox.check@v1",
        price_per_call_usd=0.0,
        input_schema=schema,
        # A capability with no invoke_url is refused earlier as "not executable here", so
        # without this the local case never reaches the point the check now lives at.
        invoke_url="http://provider.test/invoke" if source_hub == "local" else "",
        source_hub=source_hub,
        source_hub_name=source_hub,
        trust_score=0.5,
    ))
    if source_hub != "local":
        db.upsert_peer(Peer(
            url=source_hub, name=source_hub, capabilities_count=1,
            well_known_url=f"{source_hub}/.well-known/ai-market.json", trusted=True,
        ))


def _invoke(client, source_hub, payload):
    return client.post("/ai-market/v2/invoke", json={
        "product_id": "prod-atlas",
        "capability_id": "watchbox.check@v1",
        "source_hub": source_hub,
        "input": payload,
    })


@pytest.mark.parametrize("source_hub", ["local", "https://atlas.example"])
def test_the_missing_fields_are_named_on_both_routes(hub, source_hub):
    app, db = hub
    _publish(db, source_hub=source_hub)
    with TestClient(app) as client:
        r = _invoke(client, source_hub, {"text": "рядом со мной"})
    assert r.status_code == 400
    body = r.json()
    assert body["error"] == "incomplete_input"
    assert body["missing"] == ["lat", "lon"]
    assert "lat, lon" in body["detail"]


def test_one_missing_field_reads_as_one(hub):
    app, db = hub
    _publish(db, source_hub="local")
    with TestClient(app) as client:
        body = _invoke(client, "local", {"lat": 51.5}).json()
    assert body["missing"] == ["lon"]
    assert "did not include it." in body["detail"]


def test_the_row_is_still_written_and_still_unscored(hub):
    app, db = hub
    _publish(db, source_hub="local")
    with TestClient(app) as client:
        _invoke(client, "local", {})
    rows = db.recent_stats(limit=10)
    assert [r["outcome"] for r in rows] == ["incomplete"]
    assert not rows[0]["success"]
    # The whole point: an omitted field must not move the hub's success rate.
    summary = db.stats_summary()
    assert summary["successful_invocations"] == 0
    assert summary["failed_invocations"] == 0
    assert summary["incomplete_invocations"] == 1
    assert summary["success_rate"] == 1.0


def test_a_complete_call_is_not_touched_by_the_check(hub, monkeypatch):
    """The guard must refuse only what is provably short — never a valid request."""
    app, db = hub
    _publish(db, source_hub="local")
    with TestClient(app) as client:
        r = _invoke(client, "local", {"lat": 51.5, "lon": -0.1})
    assert r.json().get("error") != "incomplete_input"


def test_a_capability_that_declares_nothing_is_never_refused(hub):
    """No `required` list means the hub has no basis to judge, so it must route."""
    app, db = hub
    _publish(db, source_hub="local", schema={"type": "object"})
    with TestClient(app) as client:
        r = _invoke(client, "local", {})
    assert r.json().get("error") != "incomplete_input"


ALTERNATIVES = {
    "type": "object",
    "properties": {
        "watchbox_id": {"type": "string"}, "owner_token": {"type": "string"},
        "west": {"type": "number"}, "south": {"type": "number"},
        "east": {"type": "number"}, "north": {"type": "number"},
    },
    "anyOf": [
        {"required": ["watchbox_id", "owner_token"]},
        {"required": ["west", "south", "east", "north"]},
    ],
}


def test_a_capability_with_two_ways_in_names_both(hub):
    """ATLAS's watchbox takes a stored id plus its token, OR a bbox. Say so."""
    app, db = hub
    _publish(db, source_hub="local", schema=ALTERNATIVES)
    with TestClient(app) as client:
        body = _invoke(client, "local", {"layers": ["fleet"]}).json()
    assert body["accepts"] == [["watchbox_id", "owner_token"], ["west", "south", "east", "north"]]
    assert "watchbox_id, owner_token or west, south, east, north" in body["detail"]


def test_satisfying_one_alternative_is_enough(hub):
    app, db = hub
    _publish(db, source_hub="local", schema=ALTERNATIVES)
    with TestClient(app) as client:
        r = _invoke(client, "local", {"west": 0, "south": 0, "east": 1, "north": 1})
    assert r.json().get("error") != "incomplete_input"


def test_a_half_finished_alternative_is_still_incomplete(hub):
    """An id without its token satisfies neither branch, so both are still offered."""
    app, db = hub
    _publish(db, source_hub="local", schema=ALTERNATIVES)
    with TestClient(app) as client:
        body = _invoke(client, "local", {"watchbox_id": "wb_1"}).json()
    assert body["error"] == "incomplete_input"
    assert body["accepts"][0] == ["owner_token"]


@pytest.fixture()
def paid_hub(tmp_path: Path, monkeypatch):
    """Crypto on, so a listed price is real money and the paywall is live."""
    monkeypatch.setenv("AIFACTORY_CRYPTO_ENABLED", "1")
    monkeypatch.setenv("AIMARKET_ADMIN_TOKEN", "t" * 32)
    config = HubConfig()
    config.db_path = str(tmp_path / "hub.db")
    config.signing_key_path = str(tmp_path / "key")
    db = HubDatabase(config.db_path)
    app = create_app(config=config, db=db, signer=Signer(config.signing_key_path))
    return app, db


def test_an_unpaid_priced_call_still_gets_402_not_400(paid_hub):
    """The payment wall comes first, and this is not a nicety.

    A client answering 402 is how x402 works: it needs the price and the terms to sign a
    payment. Answering 400 "your input is short" instead strands it — it never learns what
    to pay, and retrying with perfect input meets the 402 it should have had first.

    `deploy_hub_rebuild.sh` probes every selling peer with an empty input and demands 402.
    It rolled the apex hub back when this check ran too early, which is why the check now
    lives after the paywall rather than at the top of the handler.
    """
    app, db = paid_hub
    db.upsert_capability(Capability(
        capability_id="watchbox.check@v1",
        product_id="prod-atlas",
        name="watchbox.check@v1",
        price_per_call_usd=0.02,
        input_schema=SCHEMA,
        source_hub="https://atlas.example",
        source_hub_name="https://atlas.example",
        trust_score=0.5,
    ))
    db.upsert_peer(Peer(
        url="https://atlas.example", name="atlas", capabilities_count=1,
        well_known_url="https://atlas.example/.well-known/ai-market.json", trusted=True,
    ))
    with TestClient(app) as client:
        r = client.post("/ai-market/v2/invoke", json={
            "product_id": "prod-atlas",
            "capability_id": "watchbox.check@v1",
            "source_hub": "https://atlas.example",
            "input": {},
        })
    assert r.status_code == 402, r.text
    assert r.json()["error"] in ("payment_required", "payment_failed")
