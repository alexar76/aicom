"""A hub must not offer what it cannot run.

Regression cover for the live incident: twelve seeded capabilities priced $0.15-$1.50
were listed for sale on modelmarket.dev while every invoke answered 404, because the
only guard was a name-pattern cleanup and the rows were named respectably
(`code.review@v1`, `legal.review@v1`).
"""

from __future__ import annotations

import tempfile
import time
from pathlib import Path

import pytest

from aimarket_hub.database import HubDatabase
from aimarket_hub.fulfillment import capability_is_fulfillable, has_execution_path
from aimarket_hub.models import Capability, Peer


def _cap(**kw) -> Capability:
    base = dict(
        capability_id="x@v1",
        product_id="prod-x",
        name="x",
        version="v1",
        description="",
        input_schema={},
        output_schema={},
        price_per_call_usd=1.0,
        source_hub="local",
    )
    base.update(kw)
    return Capability(**base)


class TestExecutionPath:
    def test_an_invoke_url_is_an_execution_path(self):
        assert has_execution_path("https://provider.example/invoke", "")

    def test_a_static_json_pack_is_an_execution_path(self):
        # Returned verbatim by the invoke handler — e.g. security-rules.sec-feed.
        assert has_execution_path("", '{"rules": []}')

    def test_a_prose_prompt_is_not_an_execution_path(self):
        # prompt_template also holds LLM prompts; only a JSON object is servable.
        assert not has_execution_path("", "You are a helpful assistant.")

    def test_nothing_is_not_an_execution_path(self):
        assert not has_execution_path("", "")
        assert not has_execution_path(None, None)

    def test_whitespace_is_not_a_url(self):
        assert not has_execution_path("   ", "  ")


class TestCapabilityIsFulfillable:
    def test_the_twelve_seeded_rows_are_refused(self):
        """The exact shape found in production: priced, local, no way to run it."""
        assert not capability_is_fulfillable(
            _cap(capability_id="code.review@v1", product_id="prod-code", price_per_call_usd=0.6)
        )

    def test_a_capability_with_a_provider_is_offerable(self):
        assert capability_is_fulfillable(
            _cap(capability_id="skopos.security.posture@v1",
                 invoke_url="https://skopos.modelmarket.dev/invoke")
        )

    def test_a_federated_capability_is_always_offerable(self):
        """The peer owns execution; applying the local rule would unlist the federation."""
        assert capability_is_fulfillable(
            _cap(capability_id="platon.random@v1", source_hub="https://oracles.modelmarket.dev")
        )

    def test_it_accepts_a_plain_dict_row(self):
        assert capability_is_fulfillable(
            {"source_hub": "local", "invoke_url": "https://p/invoke", "prompt_template": ""}
        )
        assert not capability_is_fulfillable(
            {"source_hub": "local", "invoke_url": "", "prompt_template": ""}
        )

    def test_the_demo_flag_is_not_what_decides_it(self):
        """A row can be honest about being a demo and still be unsellable, and vice
        versa. Fulfillability is about execution, not labelling — conflating the two is
        how the seeded rows stayed on sale with is_demo=0."""
        assert not capability_is_fulfillable(_cap(is_demo=True))
        assert capability_is_fulfillable(_cap(is_demo=True, invoke_url="https://p/invoke"))


@pytest.fixture
def db():
    with tempfile.TemporaryDirectory() as tmp:
        yield HubDatabase(Path(tmp) / "hub.db")


class TestOfferableCount:
    """`count_offerable` is SQL and `capability_is_fulfillable` is Python — the whole
    point is that they agree, because the manifest publishes the count and lists the
    rows. A drift between them advertises stock the hub then refuses to show."""

    def test_the_count_matches_the_predicate(self, db):
        rows = [
            _cap(capability_id="dead@v1"),
            _cap(capability_id="live@v1", invoke_url="https://p/invoke"),
            _cap(capability_id="pack@v1", prompt_template='{"rules": []}'),
            _cap(capability_id="peer@v1", source_hub="https://peer.example"),
        ]
        for r in rows:
            db.upsert_capability(r)

        assert db.count_capabilities("local") == 3      # the table, dead row included
        assert db.count_offerable("local") == 2         # live + pack
        assert db.count_offerable() == 3                # + the federated one

        by_python = sum(1 for r in rows if capability_is_fulfillable(r))
        assert by_python == db.count_offerable()

    def test_an_empty_hub_offers_nothing(self, db):
        assert db.count_offerable() == 0
        assert db.count_offerable("local") == 0


# ── the storefronts and the door ─────────────────────────────────────────────────────────

@pytest.fixture
def hub(tmp_path, monkeypatch):
    """A hub with one dead row, one live row and one federated row."""
    from fastapi.testclient import TestClient
    from aimarket_hub.api import create_app
    from aimarket_hub.config import HubConfig
    from aimarket_hub.signing import Signer

    monkeypatch.setenv("AIFACTORY_CRYPTO_ENABLED", "1")
    root = tmp_path / "hub"
    root.mkdir(parents=True, exist_ok=True)
    config = HubConfig()
    config.db_path = str(root / "hub.db")
    config.signing_key_path = str(root / "key")
    database = HubDatabase(root / "hub.db")
    for row in (
        # The live shape, verbatim: priced, local, nothing to run it with.
        _cap(capability_id="audit.perf@v1", product_id="prod-audit",
             price_per_call_usd=1.5),
        _cap(capability_id="skopos.posture@v1", product_id="prod-skopos",
             price_per_call_usd=0.5, invoke_url="https://skopos.example.com/invoke"),
        _cap(capability_id="platon.random@v1", product_id="prod-platon",
             price_per_call_usd=0.001, source_hub="https://oracles.example.com/family"),
    ):
        database.upsert_capability(row)
    database.upsert_peer(Peer(
        url="https://oracles.example.com/family",
        name="Oracle peer",
        capabilities_count=1,
        last_crawl=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        trust_score=0.5,
        trusted=True,
    ))
    app = create_app(config=config, db=database, signer=Signer(root / "key"))
    with TestClient(app) as client:
        yield client


class TestPriceListDoesNotAdvertiseTheUnrunnable:
    """The price list was the one storefront without the filter: 97 rows against the
    manifest's 85, and the twelve extras were the dead ones — headed by the most
    expensive item on the shelf. An agent shopping by price sorts descending."""

    def test_a_dead_row_is_absent_from_prices(self, hub):
        data = hub.get("/ai-market/v2/prices").json()
        ids = [row["capability_id"] for row in data["prices"]]
        assert "audit.perf@v1" not in ids

    def test_the_runnable_and_federated_rows_are_still_sold(self, hub):
        ids = [r["capability_id"] for r in hub.get("/ai-market/v2/prices").json()["prices"]]
        assert "skopos.posture@v1" in ids
        assert "platon.random@v1" in ids

    def test_the_count_still_matches_the_rows(self, hub):
        data = hub.get("/ai-market/v2/prices").json()
        assert data["count"] == len(data["prices"]) == 3  # two fixture rows + native pipeline executor

    def test_prices_and_the_manifest_agree(self, hub):
        priced = {r["capability_id"] for r in hub.get("/ai-market/v2/prices").json()["prices"]}
        listed = {t["capability_id"] for t in hub.get("/ai-market/v2/manifest").json()["tools"]}
        assert priced == listed

    def test_the_price_list_is_still_signed_over_what_it_returns(self, hub):
        data = hub.get("/ai-market/v2/prices").json()
        assert data["signature"]["algorithm"] == "ed25519"
        assert data["count"] == 3


class TestRefusalComesBeforeThePaywall:
    """Order matters more than the filters do. A caller holding a stale id still reaches
    the invoke handler, and if 402 fires first the buyer pays before anyone checks the
    hub can run it — $1.50 for `502 Factory returned 404`."""

    def test_an_unrunnable_capability_with_no_backend_is_404_not_402(self, hub):
        resp = hub.post("/ai-market/v2/invoke", json={
            "product_id": "prod-audit", "capability_id": "audit.perf@v1",
            "source_hub": "local", "input": {},
        })
        assert resp.status_code == 404, resp.text
        assert "not executable" in resp.json()["detail"]

    def test_the_refusal_names_no_price(self, hub):
        """Nothing in the answer may look like an invoice."""
        body = hub.post("/ai-market/v2/invoke", json={
            "product_id": "prod-audit", "capability_id": "audit.perf@v1",
            "source_hub": "local", "input": {},
        }).text
        assert "needed" not in body
        assert "1.5" not in body

    def test_a_runnable_paid_capability_still_demands_payment(self, hub):
        """The fix must not turn the paywall off for rows that CAN run."""
        resp = hub.post("/ai-market/v2/invoke", json={
            "product_id": "prod-skopos", "capability_id": "skopos.posture@v1",
            "source_hub": "local", "input": {},
        })
        assert resp.status_code == 402
        assert resp.json()["needed"] == 0.5


class TestFailedExecutionIsNotBilled:
    """The narrow guard above lets a factory-backed attempt through, so the money has to
    be protected on the other side: when execution fails, the buyer's channel must be
    exactly as full as before. This is the assertion that decides whether an unrunnable
    listing is a wasted call or a theft — on production, `audit.perf@v1` is priced $1.50
    and the factory answers 404 for it.
    """

    @pytest.fixture
    def paid_hub(self, tmp_path, monkeypatch):
        from fastapi.testclient import TestClient
        from aimarket_hub.api import create_app
        from aimarket_hub.config import HubConfig
        from aimarket_hub.signing import Signer
        import aimarket_hub.api as api_mod
        import aimarket_hub.channels as channels_mod
        from aimarket_hub.channels import ChannelLedger

        monkeypatch.setenv("AIFACTORY_CRYPTO_ENABLED", "1")
        monkeypatch.setenv("AIMARKET_ALLOW_DEMO_CREDIT", "1")
        monkeypatch.setenv("AIFACTORY_PUBLIC_URL", "http://factory.test")
        monkeypatch.setattr(channels_mod, "_ledger",
                            ChannelLedger(db_path=str(tmp_path / "channels.db")))

        class _FactoryThatHasNothing:
            """The live factory's answer for every one of the twelve seeded rows: 404."""
            def __init__(self, *a, **k):
                pass
            async def __aenter__(self):
                return self
            async def __aexit__(self, *a):
                return False
            async def post(self, url, **kw):
                from types import SimpleNamespace
                return SimpleNamespace(status_code=404, text="capability not found",
                                       json=lambda: {"error": "not found"})
        monkeypatch.setattr(api_mod.httpx, "AsyncClient", _FactoryThatHasNothing)

        root = tmp_path / "paid"
        root.mkdir(parents=True, exist_ok=True)
        config = HubConfig()
        config.db_path = str(root / "hub.db")
        config.signing_key_path = str(root / "key")
        database = HubDatabase(root / "hub.db")
        database.upsert_capability(_cap(capability_id="audit.perf@v1",
                                       product_id="prod-audit", price_per_call_usd=1.5))
        app = create_app(config=config, db=database, signer=Signer(root / "key"))
        with TestClient(app) as client:
            yield client

    def test_a_funded_channel_is_not_debited_when_execution_fails(self, paid_hub):
        opened = paid_hub.post("/ai-market/v2/channel/open",
                               json={"deposit_usd": 5.0}).json()["channel"]
        before = opened["balance_usd"]

        resp = paid_hub.post("/ai-market/v2/invoke", json={
            "product_id": "prod-audit", "capability_id": "audit.perf@v1",
            "source_hub": "local", "input": {},
        }, headers={"X-Payment-Channel": opened["channel_id"],
                    "X-Payment-Channel-Secret": opened["channel_secret"]})
        assert resp.status_code >= 400, "an absent capability must not answer 200"

        # Read the ledger, not a response body: the question is what the hub now
        # believes it is owed, and no endpoint reports a channel's balance.
        import aimarket_hub.channels as channels_mod
        row = channels_mod._ledger.get(opened["channel_id"])
        assert row is not None
        assert row["balance_usd"] == before, (
            f"the buyer paid for work that never ran: {row['balance_usd']} left of {before}")
        assert row["used_usd"] == 0.0, "a failed call was recorded as spent"

    def test_the_hold_is_released_not_left_dangling(self, paid_hub):
        """Releasing has to reach the reservation too. A hold that survives a failure
        freezes the buyer's money without ever billing it, which reads as a smaller bug
        and behaves like a larger one."""
        opened = paid_hub.post("/ai-market/v2/channel/open",
                               json={"deposit_usd": 5.0}).json()["channel"]
        paid_hub.post("/ai-market/v2/invoke", json={
            "product_id": "prod-audit", "capability_id": "audit.perf@v1",
            "source_hub": "local", "input": {},
        }, headers={"X-Payment-Channel": opened["channel_id"],
                    "X-Payment-Channel-Secret": opened["channel_secret"]})
        import aimarket_hub.channels as channels_mod
        with channels_mod._ledger._get_conn() as conn:
            reserved = conn.execute(
                "SELECT COALESCE(SUM(amount_cents), 0) AS c FROM channel_holds "
                "WHERE channel_id = ? AND status = 'held'", (opened["channel_id"],)
            ).fetchone()["c"]
        assert reserved == 0, f"{reserved} cents still held after a failed invoke"


class TestProductionDoesNotSeedAShowcase:
    """`seed_capabilities` fires whenever the local count is zero, so deleting the twelve
    unexecutable demo rows from a live hub is undone by the next restart. Production must
    therefore not seed at all — otherwise catalogue hygiene is a temporary state."""

    def _hub(self, tmp_path, monkeypatch, **env):
        from fastapi.testclient import TestClient
        from aimarket_hub.api import create_app
        from aimarket_hub.config import HubConfig
        from aimarket_hub.signing import Signer

        for key in ("AIFACTORY_PROD", "AIMARKET_SKIP_SEED"):
            monkeypatch.delenv(key, raising=False)
        for key, value in env.items():
            monkeypatch.setenv(key, value)
        root = tmp_path / f"seed-{len(env)}-{'-'.join(env)}"
        root.mkdir(parents=True, exist_ok=True)
        config = HubConfig()
        config.db_path = str(root / "hub.db")
        config.signing_key_path = str(root / "key")
        database = HubDatabase(root / "hub.db")
        app = create_app(config=config, db=database, signer=Signer(root / "key"))
        with TestClient(app):
            # The native executor is actual runnable supply, not a showcase seed.
            native = database.get_capability("hephaestus", "pipeline.run@v1", "local")
            assert native is not None and native.price_per_call_usd == 0
            return database.count_capabilities("local") - 1

    def test_a_production_hub_starts_with_an_empty_local_catalogue(self, tmp_path, monkeypatch):
        assert self._hub(tmp_path, monkeypatch, AIFACTORY_PROD="1") == 0

    def test_a_development_hub_still_gets_its_showcase(self, tmp_path, monkeypatch):
        assert self._hub(tmp_path, monkeypatch) == 12

    def test_the_existing_skip_switch_still_works(self, tmp_path, monkeypatch):
        assert self._hub(tmp_path, monkeypatch, AIMARKET_SKIP_SEED="1") == 0
