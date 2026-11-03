"""The catalogue may not present an unmeasured number as a measurement.

Every row of the live public manifest carried ``success_rate_30d: 0.5`` and
``trust_score: 0.5`` — all 76 of them, byte-identical. That is not a coincidence and not
a rating: the crawler deliberately ignores peer-declared success rates (a peer that could
claim 99% would dominate routing on first index) and seeds a neutral baseline instead,
and the code that was supposed to replace it with observed data never ran. So the hub
signed a document that told every consumer, and every UI built on it, that seventy-six
capabilities were measured at exactly one-in-two.

The fix is not to invent better numbers. It is to publish what is behind them:
``observations_30d`` and a ``reputation_basis``, and to serve the real rate the moment
there is one. These tests pin both halves — the honesty marker AND the measurement.
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from aimarket_hub.api import create_app
from aimarket_hub.config import HubConfig
from aimarket_hub.database import HubDatabase
from aimarket_hub.models import Capability, InvocationStat, Peer
from aimarket_hub.signing import Signer

ADMIN_TOKEN = "test-admin-token-not-for-production"

LOCAL_CAP = "demo.translate@v1"
PEER_URL = "https://peer.example.com"
PEER_CAP = "peer.summarize@v1"


def _iso(offset_s: float = 0.0) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + offset_s))


def _seeded_db(tmp_path) -> HubDatabase:
    db = HubDatabase(tmp_path / "hub.db")
    db.upsert_capability(Capability(
        capability_id=LOCAL_CAP, product_id="demo", name="translate",
        description="Translate text between languages", source_hub="local",
        price_per_call_usd=0.01, trust_score=0.5, success_rate_30d=0.5,
        invoke_url="https://demo.example.com/invoke",
    ))
    db.upsert_capability(Capability(
        capability_id=PEER_CAP, product_id="peer-prod", name="summarize",
        description="Summarize a document", source_hub=PEER_URL,
        source_hub_name="Peer Hub", price_per_call_usd=0.02,
        trust_score=0.5, success_rate_30d=0.5,
        invoke_url=f"{PEER_URL}/invoke",
    ))
    db.upsert_peer(Peer(
        url=PEER_URL, name="Peer Hub", capabilities_count=1,
        last_crawl=_iso(), trust_score=0.5, trusted=True,
    ))
    return db


def _client(tmp_path, db: HubDatabase, monkeypatch) -> TestClient:
    monkeypatch.setenv("AIMARKET_ADMIN_TOKEN", ADMIN_TOKEN)
    config = HubConfig()
    config.db_path = str(tmp_path / "hub.db")
    config.signing_key_path = str(tmp_path / "key")
    app = create_app(config=config, db=db, signer=Signer(config.signing_key_path))
    return TestClient(app)


def _record(db: HubDatabase, capability_id: str, *, source_hub: str,
            success: bool, age_s: float = 0.0) -> None:
    db.record_invocation(InvocationStat(
        capability_id=capability_id, product_id="demo", source_hub=source_hub,
        price_usd=0.01, latency_ms=42, success=success, timestamp=_iso(-age_s),
    ))


def _tool(manifest: dict, capability_id: str) -> dict:
    for tool in manifest["tools"]:
        if tool["capability_id"] == capability_id:
            return tool
    raise AssertionError(f"{capability_id} absent from the manifest")


class TestObservationsQuery:
    def test_no_invocations_means_no_rows(self, tmp_path):
        db = _seeded_db(tmp_path)
        observed = db.observations_30d()
        assert observed["by_capability"] == {}
        assert observed["by_hub"] == {}

    def test_counts_attempts_and_successes_per_capability_and_hub(self, tmp_path):
        db = _seeded_db(tmp_path)
        _record(db, LOCAL_CAP, source_hub="local", success=True)
        _record(db, LOCAL_CAP, source_hub="local", success=True)
        _record(db, LOCAL_CAP, source_hub="local", success=False)
        _record(db, PEER_CAP, source_hub=PEER_URL, success=True)

        observed = db.observations_30d()
        assert observed["by_capability"][LOCAL_CAP] == (3, 2)
        assert observed["by_capability"][PEER_CAP] == (1, 1)
        assert observed["by_hub"]["local"] == (3, 2)
        assert observed["by_hub"][PEER_URL] == (1, 1)

    def test_window_excludes_invocations_older_than_thirty_days(self, tmp_path):
        """A 30-day rate that silently counts year-old traffic is a different metric."""
        db = _seeded_db(tmp_path)
        _record(db, LOCAL_CAP, source_hub="local", success=True, age_s=40 * 86400)
        _record(db, LOCAL_CAP, source_hub="local", success=False, age_s=29 * 86400)

        observed = db.observations_30d()
        assert observed["by_capability"][LOCAL_CAP] == (1, 0)


class TestManifestReputationBasis:
    def test_unobserved_rows_are_labelled_not_scored(self, tmp_path, monkeypatch):
        db = _seeded_db(tmp_path)
        with _client(tmp_path, db, monkeypatch) as client:
            manifest = client.get("/ai-market/v2/manifest").json()

        tool = _tool(manifest, LOCAL_CAP)
        assert tool["observations_30d"] == 0
        assert tool["reputation_basis"] == "unobserved"

    def test_the_published_rate_becomes_the_measurement(self, tmp_path, monkeypatch):
        """Three of four succeeded: the manifest must say 0.75, not the 0.5 placeholder."""
        db = _seeded_db(tmp_path)
        for success in (True, True, True, False):
            _record(db, LOCAL_CAP, source_hub="local", success=success)

        with _client(tmp_path, db, monkeypatch) as client:
            manifest = client.get("/ai-market/v2/manifest").json()

        tool = _tool(manifest, LOCAL_CAP)
        assert tool["reputation_basis"] == "measured"
        assert tool["observations_30d"] == 4
        assert tool["success_rate_30d"] == pytest.approx(0.75)

    def test_a_measured_row_never_claims_evidence_it_lacks(self, tmp_path, monkeypatch):
        """The invariant the whole change exists to hold, asserted over every row."""
        db = _seeded_db(tmp_path)
        _record(db, PEER_CAP, source_hub=PEER_URL, success=True)

        with _client(tmp_path, db, monkeypatch) as client:
            manifest = client.get("/ai-market/v2/manifest").json()

        assert manifest["tools"], "nothing to assert on"
        for tool in manifest["tools"]:
            measured = tool["reputation_basis"] == "measured"
            assert measured is (tool["observations_30d"] > 0), tool["capability_id"]

    def test_peer_trust_is_marked_unearned_and_local_is_marked_self(
        self, tmp_path, monkeypatch,
    ):
        db = _seeded_db(tmp_path)
        with _client(tmp_path, db, monkeypatch) as client:
            manifest = client.get("/ai-market/v2/manifest").json()

        by_hub = manifest["by_hub"]
        assert by_hub["local"]["trust_basis"] == "self"
        assert by_hub[PEER_URL]["trust_basis"] == "unobserved"
        assert by_hub[PEER_URL]["observations_30d"] == 0

    def test_peer_trust_becomes_measured_once_it_has_traded(self, tmp_path, monkeypatch):
        db = _seeded_db(tmp_path)
        _record(db, PEER_CAP, source_hub=PEER_URL, success=True)

        with _client(tmp_path, db, monkeypatch) as client:
            manifest = client.get("/ai-market/v2/manifest").json()

        assert manifest["by_hub"][PEER_URL]["trust_basis"] == "measured"
        assert manifest["by_hub"][PEER_URL]["observations_30d"] == 1

    def test_the_manifest_signature_still_verifies(self, tmp_path, monkeypatch):
        """The new fields sit inside ``tools_hash``, so the envelope must be unchanged.

        Adding fields to a SIGNED document is exactly where a protocol change breaks
        every consumer at once, so this is pinned rather than assumed.
        """
        db = _seeded_db(tmp_path)
        _record(db, LOCAL_CAP, source_hub="local", success=True)

        with _client(tmp_path, db, monkeypatch) as client:
            manifest = client.get("/ai-market/v2/manifest").json()

        signer = Signer(str(tmp_path / "key"))
        canonical = signer.manifest_canonical(manifest)
        assert "tools_hash:" in canonical
        assert signer.verify(
            manifest["signature"]["public_key"],
            manifest["signature"]["value"],
            canonical,
        )


class TestSearchReputationBasis:
    def test_offers_carry_the_same_marker(self, tmp_path, monkeypatch):
        """An agent choosing between offers needs it more than a catalogue reader does."""
        db = _seeded_db(tmp_path)
        _record(db, PEER_CAP, source_hub=PEER_URL, success=True)
        _record(db, PEER_CAP, source_hub=PEER_URL, success=True)

        with _client(tmp_path, db, monkeypatch) as client:
            matches = client.get(
                "/ai-market/v2/search", params={"intent": "", "limit": 20},
            ).json()["matches"]

        assert matches, "search returned nothing to assert on"
        for row in matches:
            measured = row["reputation_basis"] == "measured"
            assert measured is (row["observations_30d"] > 0), row["capability_id"]
        summarize = [m for m in matches if m["capability_id"] == PEER_CAP]
        if summarize:  # the row is subject to discovery gates; assert only if offered
            assert summarize[0]["reputation_basis"] == "measured"
            assert summarize[0]["observations_30d"] == 2


class TestProtocolSchemaDeclaresTheFields:
    def test_manifest_schema_is_not_left_behind(self):
        """The spec is the contract other implementations read; drift makes it a lie."""
        import json
        from pathlib import Path

        here = Path(__file__).resolve()
        # Monorepo: aimarket-hub/tests/… → parents[2] is repo root.
        # Satellite checkout: tests/… only — protocol lives in alexar76/aimarket-protocol.
        candidates = [
            here.parents[2] / "aimarket-protocol" / "schemas" / "manifest.json",
            here.parents[3] / "aimarket-protocol" / "schemas" / "manifest.json",
        ]
        schema_path = next((p for p in candidates if p.is_file()), None)
        if schema_path is None:
            pytest.skip("aimarket-protocol schema not in this checkout (satellite CI)")
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        tool_props = schema["properties"]["tools"]["items"]["properties"]
        assert tool_props["reputation_basis"]["enum"] == ["measured", "unobserved"]
        assert tool_props["observations_30d"]["type"] == "integer"
