"""A listing whose answer does not depend on what it is asked ranks after the ones whose answer does.

On 2026-10-06 four free "install / bootstrap" listings of one federated hub ranked first on every hub for
wallet, treasury, transaction, install and monitor queries, above capabilities that answer the request. Two
calls with two different wallet addresses got back the same 2 KB install pack, byte for byte. The owner's rule:
rank such a listing after the services, never remove it.
"""

from __future__ import annotations

import asyncio
import json
import time

import pytest

from aimarket_hub import answer_dependence as ad
from aimarket_hub.database import HubDatabase
from aimarket_hub.models import Capability, Peer

DAY = 24 * 3600
# A few days back from the real clock, not a fixed date: search reads the verdict with no `now`, so
# observations count only inside the 30-day window behind time.time(). With T0 fixed at 2026-09-21
# the two search tests began to fail on 2026-10-21, when the first observation left that window.
T0 = time.time() - 3 * DAY
PACK = {"artifact": "industrial-sentinel", "container": "ghcr.io/example/sentinel:1.4.2",
        "agent_skill": {"catalog": "https://skills.example/sentinel", "path": "skills/sentinel"},
        "paid_routes": ["/wallet-balance", "/gas-price", "/wallet-activity"], "purpose": "install " * 20}
KEY = ("https://peer.example", "industrial-sentinel", "industrial.sentinel.wallet-monitor-bootstrap@v1")


@pytest.fixture
def db(tmp_path):
    # Three production hubs (hunt, attested, independent) run on Postgres: with
    # AIMARKET_TEST_DATABASE_URL set, every test here runs there on a fresh schema.
    from tests._mandate_kit import PG_URL, _reset_postgres

    if PG_URL:
        _reset_postgres(PG_URL)
        d = HubDatabase(tmp_path / "unused.db", database_url=PG_URL)
    else:
        d = HubDatabase(tmp_path / "hub.db")
    yield d
    if PG_URL:
        d.close()


def cap(capability_id, product_id="p", *, source_hub="https://peer.example", price=0.0, name="", description="",
        invoke_url="https://peer.example/invoke", prompt_template="", trust=0.5):
    return Capability(
        capability_id=capability_id, product_id=product_id, name=name or capability_id, version="v1",
        description=description, input_schema={}, output_schema={}, price_per_call_usd=price,
        source_hub=source_hub, trust_score=trust, invoke_url=invoke_url, prompt_template=prompt_template,
    )


# ── what is recorded ────────────────────────────────────────────────────────────────────────────────────────

def test_errors_refusals_and_empty_answers_are_not_recorded(db):
    for response in ({"success": False, "error": "address required"}, {"error": "bad input"},
                     {"result": {"status": "failed"}}, {"ok": False}, {"result": None}, {}, [], ""):
        assert ad.observe(db, KEY, {"address": "0x1"}, response, now=T0) is False
    assert ad.independent_keys(db, now=T0 + 2 * DAY) == set()


def test_the_envelope_is_not_the_answer():
    assert ad.answer_of({"success": True, "result": PACK, "receipt": {"nonce": "x"}}) == PACK
    assert ad.answer_of(PACK) == PACK


# ── the verdict ─────────────────────────────────────────────────────────────────────────────────────────────

def test_one_answer_to_different_inputs_for_a_day_is_input_independent(db):
    assert ad.observe(db, KEY, {"address": "0xaaa"}, {"result": PACK}, now=T0)
    assert ad.observe(db, KEY, {"address": "0xbbb"}, {"result": PACK}, now=T0 + 5)
    # The same instant is not enough: a live-data service with optional parameters looks like this too.
    assert ad.independent_keys(db, now=T0 + 10) == set()
    assert ad.observe(db, KEY, {"address": "0xccc"}, {"result": PACK}, now=T0 + DAY)
    assert ad.independent_keys(db, now=T0 + DAY) == {KEY}


def test_one_different_answer_clears_it(db):
    ad.observe(db, KEY, {"address": "0xaaa"}, PACK, now=T0)
    ad.observe(db, KEY, {"address": "0xbbb"}, PACK, now=T0 + DAY)
    assert ad.independent_keys(db, now=T0 + DAY) == {KEY}
    ad.observe(db, KEY, {"address": "0xddd"}, {**PACK, "balance": "12.5"}, now=T0 + DAY + 60)
    assert ad.independent_keys(db, now=T0 + DAY + 60) == set()


def test_the_same_input_twice_is_one_input(db):
    ad.observe(db, KEY, {"address": "0xaaa"}, PACK, now=T0)
    ad.observe(db, KEY, {"address": "0xaaa"}, PACK, now=T0 + 2 * DAY)
    assert ad.independent_keys(db, now=T0 + 2 * DAY) == set()


def test_a_tiny_identical_answer_is_an_empty_result_not_a_handout(db):
    for i, at in enumerate((T0, T0 + DAY, T0 + 2 * DAY)):
        ad.observe(db, KEY, {"address": f"0x{i}"}, {"eth": 0, "usdc": 0}, now=at)
    assert ad.independent_keys(db, now=T0 + 2 * DAY) == set()


def test_old_observations_stop_counting(db):
    ad.observe(db, KEY, {"address": "0xaaa"}, PACK, now=T0)
    ad.observe(db, KEY, {"address": "0xbbb"}, PACK, now=T0 + DAY)
    assert ad.independent_keys(db, now=T0 + DAY) == {KEY}
    assert ad.independent_keys(db, now=T0 + DAY + ad.WINDOW_S + 1) == set()


def test_a_capability_remembers_a_bounded_number_of_inputs(db):
    for i in range(ad.KEEP_INPUTS + 5):
        ad.observe(db, KEY, {"address": f"0x{i}"}, PACK, now=T0 + i)
    count = dict(db._conn.execute("SELECT COUNT(*) AS n FROM answer_observations").fetchone())["n"]
    assert count == ad.KEEP_INPUTS


def test_only_digests_are_kept(db):
    ad.observe(db, KEY, {"address": "0xsecretish"}, PACK, now=T0)
    row = dict(db._conn.execute("SELECT * FROM answer_observations").fetchone())
    assert "0xsecretish" not in json.dumps(row)
    assert len(row["input_digest"]) == 64


# ── search: demoted, never removed ──────────────────────────────────────────────────────────────────────────

@pytest.fixture
def catalogue(db):
    db.upsert_capability(cap(
        "industrial.sentinel.wallet-monitor-bootstrap@v1", "industrial-sentinel",
        name="Wallet monitor bootstrap", description="Wallet balance monitor: install the wallet balance agent.",
    ))
    db.upsert_capability(cap(
        "evm.asset.balance@v1", "evm-balance", source_hub="https://indep.example", price=0.004,
        name="EVM Asset Balance", description="Balance of an asset held by a wallet on an EVM chain.",
    ))
    return db


def _order(db, query="wallet balance monitor"):
    return [(m.capability.capability_id, m.input_independent) for m in db.search_capabilities_detailed(query, limit=None)]


def test_a_handout_ranks_after_the_service_and_stays_listed(catalogue):
    before = _order(catalogue)
    assert before[0][0] == "industrial.sentinel.wallet-monitor-bootstrap@v1"  # the complaint, reproduced
    ad.observe(catalogue, KEY, {"address": "0xaaa"}, PACK, now=T0)
    ad.observe(catalogue, KEY, {"address": "0xbbb"}, PACK, now=T0 + DAY)
    after = [row for row in _order(catalogue) if row[0] in {c for c, _ in before}]
    assert after == [("evm.asset.balance@v1", False), ("industrial.sentinel.wallet-monitor-bootstrap@v1", True)]


def test_the_page_is_cut_after_the_demotion(catalogue):
    ad.observe(catalogue, KEY, {"address": "0xaaa"}, PACK, now=T0)
    ad.observe(catalogue, KEY, {"address": "0xbbb"}, PACK, now=T0 + DAY)
    top = catalogue.search_capabilities_detailed("wallet balance monitor", limit=1)
    assert [m.capability.capability_id for m in top] == ["evm.asset.balance@v1"]


def test_a_local_static_pack_needs_no_calls_to_be_demoted(db):
    db.upsert_capability(cap("hub.hello@v1", "hub-hello", source_hub="local", invoke_url="",
                             prompt_template=json.dumps({"answer": "hello"}), name="Hub hello wallet balance"))
    db.upsert_capability(cap("evm.asset.balance@v1", "evm-balance", source_hub="local",
                             name="EVM Asset Balance", description="wallet balance"))
    rows = _order(db, "wallet balance")
    assert rows[-1] == ("hub.hello@v1", True)
    assert ("evm.asset.balance@v1", False) in rows


def test_demotion_keeps_each_groups_own_order():
    import dataclasses

    @dataclasses.dataclass(frozen=True)
    class Match:
        capability: object
        input_independent: bool = False

    ms = [Match(cap(c)) for c in ("a@v1", "h1@v1", "b@v1", "h2@v1", "c@v1")]
    flagged = {("https://peer.example", "p", "h1@v1"), ("https://peer.example", "p", "h2@v1")}
    out = ad.demote(ms, flagged)
    assert [m.capability.capability_id for m in out] == ["a@v1", "b@v1", "c@v1", "h1@v1", "h2@v1"]
    assert [m.input_independent for m in out] == [False, False, False, True, True]


# ── the probe ───────────────────────────────────────────────────────────────────────────────────────────────

def test_the_probe_never_touches_what_could_act_or_cost():
    assert ad.acts(cap("evm.usdc.invoice.cancel@v1"))
    assert ad.acts(cap("pipeline.run@v1", "hephaestus"))
    assert ad.acts(cap("x.notify@v1", name="Send a Telegram message"))
    assert not ad.acts(cap("industrial.sentinel.wallet-monitor-bootstrap@v1", "industrial-sentinel"))
    assert not ad.acts(cap("industrial.sentinel.install@v1", "industrial-sentinel"))


def test_candidates_are_free_federated_and_harmless(db):
    db.upsert_capability(cap("industrial.sentinel.install@v1", "industrial-sentinel"))
    db.upsert_capability(cap("evm.asset.balance@v1", price=0.004))                  # paid
    db.upsert_capability(cap("evm.usdc.invoice.cancel@v1"))                          # acts
    db.upsert_capability(cap("local.thing@v1", source_hub="local"))                  # ours, observed passively
    names = [c.capability_id for c in ad.probe_candidates(db, now=T0)]
    assert names == ["industrial.sentinel.install@v1"]


class FakePeers:
    """A peer hub answering /ai-market/v2/invoke: one capability is a handout, one echoes, one errors."""

    def __init__(self):
        self.calls = []

    async def resolve(self, peer):
        return f"{peer.url}/ai-market/v2/invoke"

    async def post(self, url, *, json, headers, timeout):
        self.calls.append((json["capability_id"], json["input"], headers.get("X-AIMarket-Probe")))

        class R:
            def __init__(self, status, body):
                self.status_code, self._body = status, body

            def json(self):
                return self._body

        if json["capability_id"].startswith("handout"):
            return R(200, {"success": True, "result": PACK})
        if json["capability_id"].startswith("echo"):
            return R(200, {"success": True, "result": {"you_asked": json["input"], "pad": "x" * 300}})
        return R(400, {"error": "address required"})


def _peer_catalogue(db):
    db.upsert_peer(Peer(url="https://peer.example", name="Peer", trusted=True))
    for cid in ("handout.pack@v1", "echo.lookup@v1", "strict.lookup@v1", "x.send@v1"):
        db.upsert_capability(cap(cid))


def _probe(db, peers, now):
    class Config:
        hub_url = "https://hub.example"

    return asyncio.run(ad.probe_free(db, Config(), resolve_endpoint=peers.resolve, post=peers.post, now=now))


def test_a_day_of_probing_finds_the_handout_and_only_the_handout(db, monkeypatch):
    monkeypatch.delenv("AIMARKET_ANSWER_PROBE", raising=False)
    _peer_catalogue(db)
    peers = FakePeers()
    first = _probe(db, peers, T0)
    assert first["probed"] == 3                                   # x.send@v1 is never asked
    assert {c for c, _, _ in peers.calls} == {"handout.pack@v1", "echo.lookup@v1", "strict.lookup@v1"}
    assert all(tag == "answer-dependence" for _, _, tag in peers.calls)
    assert len({json.dumps(i, sort_keys=True) for _, i, _ in peers.calls}) == len(peers.calls)  # never the same input
    assert ad.independent_keys(db, now=T0) == set()                # not on one round
    assert _probe(db, peers, T0 + 60)["probed"] == 0               # nothing due a minute later
    _probe(db, peers, T0 + DAY)                                    # the suspected handout is asked again
    assert ad.independent_keys(db, now=T0 + DAY) == {("https://peer.example", "p", "handout.pack@v1")}


def test_the_probe_can_be_switched_off(db, monkeypatch):
    monkeypatch.setenv("AIMARKET_ANSWER_PROBE", "0")
    _peer_catalogue(db)
    peers = FakePeers()
    assert _probe(db, peers, T0) == {"probed": 0, "disabled": True}
    assert peers.calls == []


def test_the_api_records_answers_without_ever_failing_a_call(db):
    from aimarket_hub.api import _observe_answer

    class Body:
        product_id, capability_id, input = "industrial-sentinel", KEY[2], {"address": "0xaaa"}

    _observe_answer(db, KEY[0], Body(), {"success": True, "result": PACK})
    assert dict(db._conn.execute("SELECT COUNT(*) AS n FROM answer_observations").fetchone())["n"] == 1
    _observe_answer(None, KEY[0], Body(), PACK)  # broken bookkeeping is logged, not raised


def test_fields_the_capability_ignores_do_not_make_new_inputs(db, monkeypatch):
    """Anyone could demote an input-dependent competitor by resending ONE real input with junk
    fields: the same answer to "different" inputs for a day read as a handout."""
    from types import SimpleNamespace

    monkeypatch.setattr(db, "get_capability", lambda p, c, h="local": SimpleNamespace(
        input_schema={"type": "object", "properties": {"address": {"type": "string"}}}), raising=False)
    ad.observe(db, KEY, {"address": "0xaaa", "junk": 1}, PACK, now=T0)
    ad.observe(db, KEY, {"address": "0xaaa", "junk": 2}, PACK, now=T0 + DAY)
    ad.observe(db, KEY, {"address": "0xaaa", "junk": 3}, PACK, now=T0 + 2 * DAY)
    assert KEY not in ad.independent_keys(db, now=T0 + 2 * DAY)


def test_real_inputs_still_count(db, monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr(db, "get_capability", lambda p, c, h="local": SimpleNamespace(
        input_schema={"type": "object", "properties": {"address": {"type": "string"}}}), raising=False)
    ad.observe(db, KEY, {"address": "0xaaa", "junk": 1}, PACK, now=T0)
    ad.observe(db, KEY, {"address": "0xbbb", "junk": 1}, PACK, now=T0 + DAY)
    assert KEY in ad.independent_keys(db, now=T0 + DAY)
