"""Subcontracting (aimarket-protocol/mandates.md §6), end to end.

The providers in these tests are real participants: when the hub executes one, it receives
the headers the hub sends and may call the SAME hub back over ASGI to buy from another
provider, exactly as a deployed provider would over HTTPS. Nothing about the job token or
the grant is mocked.
"""
from __future__ import annotations

import json
from contextlib import contextmanager
from typing import Any, Awaitable, Callable

import httpx
import pytest

from tests._mandate_kit import (  # noqa: E402  (importorskip awr first)
    HUB, balance, funded_account, hub, issue, key, list_provider, list_static,
    mandated_invoke, owner_link_payload, setup_mandate,
)
from aimarket_hub import subcontract
from aimarket_hub.models import Capability, Peer

Handler = Callable[[dict, dict, "Providers"], Awaitable[tuple[int, dict]]]


class _Resp:
    def __init__(self, status: int, body: dict):
        self.status_code = status
        self._body = body
        self.headers = {"content-type": "application/json"}
        self.text = json.dumps(body)

    def json(self) -> dict:
        return self._body


class Providers:
    """Fake provider endpoints that can call back into the hub under test."""

    def __init__(self, app: Any):
        self.app = app
        self.handlers: dict[str, Handler] = {}
        self.seen: dict[str, list[dict]] = {}

    def add(self, url: str, handler: Handler) -> None:
        self.handlers[url] = handler

    async def post(self, url: str, **kwargs: Any) -> _Resp:
        headers = {k: v for k, v in (kwargs.get("headers") or {}).items() if v}
        self.seen.setdefault(url, []).append(headers)
        status, body = await self.handlers[url](kwargs.get("json") or {}, headers, self)
        return _Resp(status, body)

    async def buy(self, payload: dict, headers: dict) -> httpx.Response:
        transport = httpx.ASGITransport(app=self.app)
        async with httpx.AsyncClient(transport=transport, base_url=HUB) as c:
            return await c.post("/ai-market/v2/invoke", json=payload, headers=headers)


def job_headers(incoming: dict, *, with_grant: bool = True) -> dict:
    out = {subcontract.JOB_HEADER: incoming[subcontract.JOB_HEADER]}
    if with_grant and subcontract.GRANT_HEADER in incoming:
        out[subcontract.GRANT_HEADER] = incoming[subcontract.GRANT_HEADER]
    return out


WEATHER = {"product_id": "wx", "capability_id": "wx.read@v1", "input": {"q": 1}, "source_hub": "local"}
BRIEF = {"product_id": "brief", "capability_id": "brief.make@v1", "input": {"topic": "x"}, "source_hub": "local"}


@pytest.fixture
def world(monkeypatch, tmp_path):
    """A hub selling a static weather read ($0.001) and a provider-backed brief ($0.010)."""
    with hub(monkeypatch, tmp_path) as (client, db):
        providers = Providers(client.app_ref)
        import aimarket_hub.outbound_http as outbound

        monkeypatch.setattr(outbound, "safe_post", providers.post)
        list_static(db, capability_id="wx.read@v1", product_id="wx", price=0.001)
        list_provider(db, "brief.make@v1", "brief", 0.010, url="https://brief.test/invoke")
        yield client, db, providers


def _buyer(client, db, usd=1.0):
    account, api_key = funded_account(client, db, usd)
    return account, api_key


class TestCostPlus:
    def test_the_provider_spends_the_allowance_and_the_buyer_sees_the_bill(self, world):
        client, db, providers = world

        async def brief(body, headers, p):
            spent = []
            for _ in range(2):
                r = await p.buy(WEATHER, job_headers(headers))
                assert r.status_code == 200, r.text
                spent.append(r.json())
            return 200, {"result": {"brief": "two readings", "children": [s["job"] for s in spent]}}

        providers.add("https://brief.test/invoke", brief)
        account, api_key = _buyer(client, db)
        r = client.post("/ai-market/v2/invoke", headers={"X-API-Key": api_key},
                        json={**BRIEF, "subcontract": {"allowance_usd": 0.005}})
        assert r.status_code == 200, r.text
        body = r.json()
        sub = body["subcontracting"]
        assert sub["allowance_usd"] == pytest.approx(0.005)
        assert sub["spent_usd"] == pytest.approx(0.002)
        assert sub["released_usd"] == pytest.approx(0.003)
        assert [n["funded_by"] for n in sub["nodes"]] == ["allowance", "allowance"]
        assert all(n["status"] == "captured" and n["depth"] == 1 for n in sub["nodes"])
        # buyer paid the brief plus exactly what the subcontractors cost
        assert balance(db, account) == pytest.approx(1.0 - 0.010 - 0.002)
        # the tree is readable later by id
        tree = client.get(f"/ai-market/v2/jobs/{sub['job_id']}").json()
        assert tree["allowance_status"] == "closed" and len(tree["nodes"]) == 3

    def test_children_can_never_spend_more_than_the_allowance(self, world):
        client, db, providers = world
        outcomes = []

        async def greedy(body, headers, p):
            for _ in range(5):
                r = await p.buy(WEATHER, job_headers(headers))
                outcomes.append((r.status_code, r.json().get("error")))
            return 200, {"result": {"ok": True}}

        providers.add("https://brief.test/invoke", greedy)
        account, api_key = _buyer(client, db)
        r = client.post("/ai-market/v2/invoke", headers={"X-API-Key": api_key},
                        json={**BRIEF, "subcontract": {"allowance_usd": 0.003}})
        assert r.status_code == 200
        assert [o[0] for o in outcomes] == [200, 200, 200, 402, 402]
        assert outcomes[-1][1] == "allowance_exhausted"
        assert r.json()["subcontracting"]["spent_usd"] == pytest.approx(0.003)
        assert balance(db, account) == pytest.approx(1.0 - 0.010 - 0.003)

    def test_a_failed_subcontractor_hands_its_money_back_for_a_retry(self, world):
        client, db, providers = world
        from aimarket_hub.models import Capability

        db.upsert_capability(Capability(
            capability_id="flaky@v1", product_id="flaky", name="flaky", description="x",
            price_per_call_usd=0.003, source_hub="local", invoke_url="",
            prompt_template='{"ok": false, "error": "sensor offline"}',
        ))
        codes = []

        async def retrying(body, headers, p):
            r = await p.buy({**WEATHER, "product_id": "flaky", "capability_id": "flaky@v1"}, job_headers(headers))
            codes.append(r.status_code)
            r = await p.buy({**WEATHER}, job_headers(headers))   # the retry, elsewhere
            codes.append(r.status_code)
            return 200, {"result": {"ok": True}}

        providers.add("https://brief.test/invoke", retrying)
        account, api_key = _buyer(client, db)
        r = client.post("/ai-market/v2/invoke", headers={"X-API-Key": api_key},
                        json={**BRIEF, "subcontract": {"allowance_usd": 0.003}})
        # the $0.003 failure returned to the allowance, so the $0.001 retry was still paid
        assert codes == [502, 200]
        sub = r.json()["subcontracting"]
        assert sub["spent_usd"] == pytest.approx(0.001)
        assert sorted(n["status"] for n in sub["nodes"]) == ["captured", "failed"]
        assert balance(db, account) == pytest.approx(1.0 - 0.010 - 0.001)

    def test_the_provider_fails_after_its_subcontractor_delivered(self, world):
        """Cost-plus: materials consumed are paid for; the failing provider is not (§6.3)."""
        client, db, providers = world

        async def breaks(body, headers, p):
            await p.buy(WEATHER, job_headers(headers))
            return 500, {"error": "boom"}

        providers.add("https://brief.test/invoke", breaks)
        account, api_key = _buyer(client, db)
        r = client.post("/ai-market/v2/invoke", headers={"X-API-Key": api_key},
                        json={**BRIEF, "subcontract": {"allowance_usd": 0.005}})
        assert r.status_code == 502
        assert balance(db, account) == pytest.approx(1.0 - 0.001)

    def test_a_grant_dies_with_the_root_call(self, world):
        client, db, providers = world
        kept = {}

        async def leaks(body, headers, p):
            kept.update(job_headers(headers))
            return 200, {"result": {"ok": True}}

        providers.add("https://brief.test/invoke", leaks)
        account, api_key = _buyer(client, db)
        client.post("/ai-market/v2/invoke", headers={"X-API-Key": api_key},
                    json={**BRIEF, "subcontract": {"allowance_usd": 0.005}})
        r = client.post("/ai-market/v2/invoke", headers=kept, json=WEATHER)
        assert r.status_code == 402 and r.json()["error"] == "allowance_exhausted"
        assert balance(db, account) == pytest.approx(1.0 - 0.010)

    def test_a_grant_cannot_be_mixed_with_another_payment(self, world):
        client, db, providers = world
        seen = {}

        async def mixes(body, headers, p):
            r = await p.buy(WEATHER, {**job_headers(headers), "X-API-Key": "aimk_whatever"})
            seen["r"] = (r.status_code, r.json()["error"])
            return 200, {"result": {"ok": True}}

        providers.add("https://brief.test/invoke", mixes)
        _, api_key = _buyer(client, db)
        client.post("/ai-market/v2/invoke", headers={"X-API-Key": api_key},
                    json={**BRIEF, "subcontract": {"allowance_usd": 0.005}})
        assert seen["r"] == (403, "job_invalid")   # §7: job_invalid is always a 403


class TestTreeLimits:
    def test_depth_and_cycles(self, world):
        client, db, providers = world
        list_provider(db, "mid.step@v1", "mid", 0.002, url="https://mid.test/invoke")
        seen = {}

        async def brief(body, headers, p):
            r = await p.buy({**WEATHER, "product_id": "mid", "capability_id": "mid.step@v1"}, job_headers(headers))
            seen["mid"] = r.status_code
            r = await p.buy(BRIEF, job_headers(headers))          # itself: a cycle
            seen["cycle"] = (r.status_code, r.json().get("limit"))
            return 200, {"result": {"ok": True}}

        async def mid(body, headers, p):
            r = await p.buy(WEATHER, job_headers(headers))        # depth 2 > max_depth 1
            seen["deep"] = (r.status_code, r.json().get("limit"))
            return 200, {"result": {"ok": True}}

        providers.add("https://brief.test/invoke", brief)
        providers.add("https://mid.test/invoke", mid)
        _, api_key = _buyer(client, db)
        r = client.post("/ai-market/v2/invoke", headers={"X-API-Key": api_key},
                        json={**BRIEF, "subcontract": {"allowance_usd": 0.01, "max_depth": 1}})
        assert r.status_code == 200
        assert seen == {"mid": 200, "deep": (403, "depth"), "cycle": (403, "cycle")}

    def test_two_levels_when_the_buyer_allows_them(self, world):
        client, db, providers = world
        list_provider(db, "mid.step@v1", "mid", 0.002, url="https://mid.test/invoke")

        async def brief(body, headers, p):
            r = await p.buy({**WEATHER, "product_id": "mid", "capability_id": "mid.step@v1"}, job_headers(headers))
            assert r.status_code == 200, r.text
            return 200, {"result": {"ok": True}}

        async def mid(body, headers, p):
            r = await p.buy(WEATHER, job_headers(headers))
            assert r.status_code == 200, r.text
            return 200, {"result": {"ok": True}}

        providers.add("https://brief.test/invoke", brief)
        providers.add("https://mid.test/invoke", mid)
        account, api_key = _buyer(client, db)
        r = client.post("/ai-market/v2/invoke", headers={"X-API-Key": api_key},
                        json={**BRIEF, "subcontract": {"allowance_usd": 0.01, "max_depth": 2}})
        sub = r.json()["subcontracting"]
        assert sorted(n["depth"] for n in sub["nodes"]) == [1, 2]
        assert sub["spent_usd"] == pytest.approx(0.003)
        assert balance(db, account) == pytest.approx(1.0 - 0.010 - 0.003)

    def test_a_forged_token_is_refused(self, world):
        client, db, providers = world
        r = client.post("/ai-market/v2/invoke", headers={subcontract.JOB_HEADER: "eyJ2IjoxfQ.AAAA"}, json=WEATHER)
        assert r.status_code == 403 and r.json()["error"] == "job_invalid"


class TestFixedPrice:
    def test_a_provider_paying_its_own_way_is_still_in_the_tree(self, world):
        client, db, providers = world
        _, provider_key = _buyer(client, db)

        async def brief(body, headers, p):
            assert subcontract.GRANT_HEADER not in headers   # no allowance was asked for
            r = await p.buy(WEATHER, {**job_headers(headers, with_grant=False), "X-API-Key": provider_key})
            assert r.status_code == 200, r.text
            return 200, {"result": {"ok": True}}

        providers.add("https://brief.test/invoke", brief)
        account, api_key = _buyer(client, db)
        r = client.post("/ai-market/v2/invoke", headers={"X-API-Key": api_key}, json=BRIEF)
        sub = r.json()["subcontracting"]
        assert [(n["funded_by"], n["status"]) for n in sub["nodes"]] == [("own", "captured")]
        assert "allowance_usd" not in sub
        assert balance(db, account) == pytest.approx(1.0 - 0.010)


class TestMandatedJobs:
    @pytest.mark.parametrize("delegated", [False, True])
    def test_the_allowance_counts_against_the_mandate_and_settles_to_what_was_spent(self, world, delegated):
        client, db, providers = world

        async def brief(body, headers, p):
            assert headers["X-AIMarket-Principal"] == key(1).did
            assert headers["X-AIMarket-Agent"] == key(3 if delegated else 2).did
            r = await p.buy(WEATHER, job_headers(headers))
            assert r.status_code == 200, r.text
            return 200, {"result": {"ok": True}}

        providers.add("https://brief.test/invoke", brief)
        m = setup_mandate(client, db, per_day=100_000,
                          subcontract={"perCallAllowance": 5_000, "maxDepth": 1})
        leaf = m["digest"]
        if delegated:
            doc = issue(m["agent"], key(3).did, parent=leaf, per_day=100_000,
                        subcontract={"perCallAllowance": 5_000, "maxDepth": 1})
            response = client.post("/ai-market/v2/mandates", json=doc)
            assert response.status_code == 200, response.text
            leaf = response.json()["digest"]
        r = mandated_invoke(client, m, {**BRIEF, "subcontract": {"allowance_usd": 0.005}},
                            agent=key(3) if delegated else None, leaf=leaf)
        assert r.status_code == 200, r.text
        usage = client.get(f"/ai-market/v2/mandates/{m['digest']}",
                           headers={"X-API-Key": m["api_key"]}).json()["usage"]
        assert usage["spent_today_usd"] == pytest.approx(0.010 + 0.001)
        assert balance(db, m["account"]) == pytest.approx(1.0 - 0.011)

    def test_a_mandate_bounds_the_allowance(self, world):
        client, db, providers = world
        providers.add("https://brief.test/invoke", lambda *a: None)
        m = setup_mandate(client, db, subcontract={"perCallAllowance": 2_000, "maxDepth": 1})
        r = mandated_invoke(client, m, {**BRIEF, "subcontract": {"allowance_usd": 0.005}})
        assert r.status_code == 402 and r.json()["limit"] == "subcontract.perCallAllowance"
        m2 = setup_mandate(client, db, owner_seed=11, agent_seed=12)
        r = mandated_invoke(client, m2, {**BRIEF, "subcontract": {"allowance_usd": 0.001}})
        assert r.status_code == 403 and "does not allow subcontracting" in r.json()["detail"]
        assert balance(db, m["account"]) == pytest.approx(1.0)

    def test_children_stay_inside_the_root_mandate_scope(self, world):
        client, db, providers = world
        seen = {}

        async def brief(body, headers, p):
            r = await p.buy(WEATHER, job_headers(headers))
            seen["r"] = (r.status_code, r.json().get("error"))
            return 200, {"result": {"ok": True}}

        providers.add("https://brief.test/invoke", brief)
        m = setup_mandate(client, db, scope=("brief.*",),
                          subcontract={"perCallAllowance": 5_000, "maxDepth": 1})
        r = mandated_invoke(client, m, {**BRIEF, "subcontract": {"allowance_usd": 0.005}})
        assert r.status_code == 200
        assert seen["r"] == (403, "mandate_scope")


# ── what an independent review of the money path found (each pinned) ────

class TestReviewFindings:
    def test_a_funded_provider_never_sees_the_buyers_balance(self, world):
        client, db, providers = world
        seen = {}

        async def brief(body, headers, p):
            r = await p.buy(WEATHER, job_headers(headers))
            seen["ok"] = r.json()
            r = await p.buy({**WEATHER, "input": {"q": 2}}, job_headers(headers))
            r = await p.buy({**WEATHER, "input": {"q": 3}}, job_headers(headers))
            seen["refused"] = r.json()
            return 200, {"result": {"ok": True}}

        providers.add("https://brief.test/invoke", brief)
        account, api_key = _buyer(client, db, usd=5.0)
        client.post("/ai-market/v2/invoke", headers={"X-API-Key": api_key},
                    json={**BRIEF, "subcontract": {"allowance_usd": 0.002}})
        # $5 is what the buyer holds; the provider may learn only what is left of the allowance
        assert seen["ok"]["remaining_balance"] == pytest.approx(0.001)
        assert "4.9" not in str(seen["refused"]) and seen["refused"]["error"] == "allowance_exhausted"

    def test_concurrent_joins_never_exceed_the_fan_out_limit(self, world, tmp_path):
        """Forty threads join one call at once. The fan-out limit is a counter moved by one
        conditional statement, so exactly MAX_CHILDREN_PER_NODE of them get in."""
        import threading

        from aimarket_hub.signing import Signer

        client, db, providers = world
        jobs_store = subcontract.JobStore(db._conn, Signer(tmp_path / "jobkey"), HUB)
        for round_ in range(5):   # a lost race is probabilistic; several rounds catch it
            root = jobs_store.open_root(product_id="brief", capability_id="brief.make@v1")
            token = jobs_store.issue_token(root)
            wins, limits = [], []
            barrier = threading.Barrier(40)

            def join(i):
                barrier.wait()
                try:
                    jobs_store.join(token=token, grant_secret="", product_id="wx", capability_id=f"wx.read{i}@v1")
                    wins.append(i)
                except subcontract.SubcontractError as exc:
                    limits.append(exc.extra.get("limit"))

            threads = [threading.Thread(target=join, args=(i,)) for i in range(40)]
            [t.start() for t in threads]
            [t.join() for t in threads]
            assert len(wins) == subcontract.MAX_CHILDREN_PER_NODE, round_
            assert limits == ["children"] * (40 - subcontract.MAX_CHILDREN_PER_NODE)

    def test_a_child_refunded_after_the_root_closed_is_given_back_to_the_mandate(self, world):
        from aimarket_hub import credits, mandates

        client, db, providers = world
        m = setup_mandate(client, db, per_day=100_000, subcontract={"perCallAllowance": 5_000, "maxDepth": 1})
        ledger = credits.CreditsLedger(db._conn)
        store = mandates.MandateStore(db._conn, HUB)
        adm = mandates.Admission(chain=store.chain(m["digest"]), account_id=m["account"], product_id="p", store=store)
        # the root reserves an allowance, a child carves $0.003 out of it, the root closes
        mandates.MandatedCredits(ledger, adm).hold_allowance(m["account"], 0.005, "alw_x")
        child = subcontract.AllowanceCredits(ledger, "alw_x")
        child.hold(m["account"], 0.003, "child_1")
        released = ledger.release_hold("alw_x")["released_usd"]
        store.settle("alw_x", 5_000 - round(released * 1_000_000))
        assert store.usage(m["digest"])["spent_today_usd"] == pytest.approx(0.003)
        # ...then the child fails: its money goes to the balance, and back off the mandate
        child.release_hold("child_1")
        assert child.released_to == "balance"
        store.give_back("alw_x", child.released_micro)
        assert store.usage(m["digest"])["spent_today_usd"] == 0
        assert balance(db, m["account"]) == pytest.approx(1.0)

    def test_both_holds_of_a_federated_child_are_given_back_to_the_mandate(self, world):
        """A federated child resolves TWO holds through one proxy — its price and its
        routing fee. When both come back after the root closed, both go back off the root
        mandate's counters; remembering only the last release gave back just the fee."""
        from aimarket_hub import credits, mandates

        client, db, providers = world
        m = setup_mandate(client, db, per_day=100_000, subcontract={"perCallAllowance": 5_000, "maxDepth": 1})
        ledger = credits.CreditsLedger(db._conn)
        store = mandates.MandateStore(db._conn, HUB)
        adm = mandates.Admission(chain=store.chain(m["digest"]), account_id=m["account"], product_id="p", store=store)
        mandates.MandatedCredits(ledger, adm).hold_allowance(m["account"], 0.005, "alw_f")
        child = subcontract.AllowanceCredits(ledger, "alw_f")
        child.hold(m["account"], 0.002, "price_1")
        child.hold(m["account"], 0.00002, "fee_1")
        released = ledger.release_hold("alw_f")["released_usd"]
        store.settle("alw_f", 5_000 - round(released * 1_000_000))
        assert store.usage(m["digest"])["spent_today_usd"] == pytest.approx(0.00202)
        child.release_hold("price_1")
        child.release_hold("fee_1")
        assert child.released_to == "balance" and child.released_micro == 2_020
        store.give_back("alw_f", child.released_micro)
        assert store.usage(m["digest"])["spent_today_usd"] == 0
        assert balance(db, m["account"]) == pytest.approx(1.0)
        assert child.captured_micro == 0

    def test_a_stranded_allowance_is_swept(self, world):
        from aimarket_hub import credits, invoke_funding, mandates

        client, db, providers = world
        account, _ = _buyer(client, db)
        ledger = credits.CreditsLedger(db._conn)
        jobs_store = subcontract.JobStore(db._conn, None, HUB)   # open_root signs nothing
        ledger.hold(account, 0.005, "alw_stranded")
        jobs_store.open_root(product_id="brief", capability_id="brief.make@v1", allowance_micro=5_000,
                             account_id=account, allowance_receipt="alw_stranded", now=0)
        assert balance(db, account) == pytest.approx(0.995)
        swept = invoke_funding.sweep_stale_allowances(credits_ledger=ledger,
                                                      store=mandates.MandateStore(db._conn, HUB), jobs=jobs_store)
        assert swept == 1 and balance(db, account) == pytest.approx(1.0)


# ── a child bought from a PEER ──────────────────────────────────────────
#
# The live shape. The apex hub executes no capability of its own — every one of its listings
# is federated — so a composite provider there can only hire children that the hub ROUTES to
# another satellite. Grant funding is wrapped around both branches of the invoke handler, so
# the federated branch's price hold AND its routing-fee hold are carved out of the allowance;
# until these tests every subcontracting test bought local packs only, and that path had
# never run under a test before it was meant to run live.

PEER = "https://gaia.test"
PEER_INVOKE = f"{PEER}/ai-market/v2/invoke"
FED_WEATHER = {"product_id": "gaia.gateway", "capability_id": "gaia.weather.read@v1",
               "input": {"city": "Helsinki"}, "source_hub": PEER}
FED_AIR = {**FED_WEATHER, "capability_id": "gaia.air.read@v1"}
FED_PRICE = 0.001
ROUTING_FEE = round(FED_PRICE * 100 / 10_000, 6)       # AIMARKET_ROUTING_FEE_BPS default: 1 %

# The two ways a hub bills a routed capability (config.sells_on_behalf_of / peer_api_key).
FED_CONFIGS = {
    # The apex's own configuration for GAIA: AIMARKET_SELLS_FOR names the peer, so this hub
    # is the seller of record — it bills the list price and takes no routing fee on top.
    "seller_of_record": ({"AIMARKET_SELLS_FOR": PEER}, 0.0),
    # A resold peer: the hub pays the peer from its own account there and bills the
    # catalogued price plus its routing fee — two holds, both from the allowance.
    "resale": ({"AIMARKET_PEER_API_KEYS": f"{PEER}=aimk_this_hubs_account_at_the_peer"}, ROUTING_FEE),
}


def gaia_envelope(capability_id: str, *, ok: bool = True) -> dict:
    """What GAIA's oracle_core answers (no top-level `success`; the hub normalizes it)."""
    if not ok:
        return {"ok": False, "error": "upstream relay offline", "refuse_reason": "upstream relay offline"}
    return {
        "capability_id": capability_id,
        "output": {"reading": {"device_id": "om-wx-helsinki", "ts": "2026-09-26T10:00:00Z",
                               "values": {"temperature_c": 11.2}}},
        "price_usd": FED_PRICE,
        "receipt": {"nonce": "gaia-1", "latency_ms": 12, "price_usd": FED_PRICE},
    }


@contextmanager
def federated_world(monkeypatch, tmp_path, *, peer_ok: bool = True, **env):
    """A hub that routes GAIA's two reads to a peer and sells a local composite ($0.010)."""
    with hub(monkeypatch, tmp_path, **env) as (client, db):
        import aimarket_hub.api as api_mod
        import aimarket_hub.peer_routing as peer_routing
        import aimarket_hub.outbound_http as outbound

        providers = Providers(client.app_ref)
        monkeypatch.setattr(outbound, "safe_post", providers.post)

        async def well_known(url, *, timeout=10.0):
            assert url == f"{PEER}/.well-known/ai-market.json", url
            return _Resp(200, {"name": "gaia", "mcp_endpoint": PEER_INVOKE})

        monkeypatch.setattr(outbound, "safe_get", well_known)
        # Transport decisions are cached per peer URL for the life of the process.
        monkeypatch.setattr(peer_routing, "_peer_endpoint_cache", {})
        db.upsert_peer(Peer(url=PEER, name="gaia", capabilities_count=2,
                            well_known_url=f"{PEER}/.well-known/ai-market.json", trusted=True))
        for cap in (FED_WEATHER, FED_AIR):
            # What the crawler stores for a peer's catalogue entry: the price the fee is
            # based on, under source_hub = the peer.
            db.upsert_capability(Capability(
                capability_id=cap["capability_id"], product_id=cap["product_id"],
                name=cap["capability_id"], price_per_call_usd=FED_PRICE,
                source_hub=PEER, source_hub_name=PEER, trust_score=0.5,
            ))
        list_provider(db, "brief.make@v1", "brief", 0.010, url="https://brief.test/invoke")

        async def gaia(body, headers, p):
            return 200, gaia_envelope(body["capability_id"], ok=peer_ok)

        providers.add(PEER_INVOKE, gaia)
        yield client, db, providers


class TestFederatedChild:
    @pytest.mark.parametrize("config", sorted(FED_CONFIGS))
    def test_a_grant_funded_federated_child_is_carved_from_the_allowance(self, monkeypatch, tmp_path, config):
        env, fee = FED_CONFIGS[config]
        with federated_world(monkeypatch, tmp_path, **env) as (client, db, providers):
            children: list[dict] = []

            async def brief(body, headers, p):
                for child in (FED_WEATHER, FED_AIR):
                    r = await p.buy({**child, "max_price_usd": FED_PRICE + fee}, job_headers(headers))
                    assert r.status_code == 200, r.text
                    children.append(r.json())
                return 200, {"result": {"witnessed": [c["job"]["node"] for c in children]}}

            providers.add("https://brief.test/invoke", brief)
            account, api_key = _buyer(client, db)
            r = client.post("/ai-market/v2/invoke", headers={"X-API-Key": api_key},
                            json={**BRIEF, "subcontract": {"allowance_usd": 0.01, "max_depth": 1}})
            assert r.status_code == 200, r.text
            body = r.json()
            buyer_left = balance(db, account)

        per_child = FED_PRICE + fee
        sub = body["subcontracting"]
        assert [c["job"]["funded_by"] for c in children] == ["allowance", "allowance"]
        # The price AND the routing fee of each child came out of the allowance…
        assert sub["spent_usd"] == pytest.approx(2 * per_child)
        assert sub["spent_usd"] + sub["released_usd"] == pytest.approx(sub["allowance_usd"])
        # …and the bill of materials adds up to what was spent: a node's price is what the
        # allowance paid for it, the fee included.
        assert [n["price_usd"] for n in sub["nodes"]] == pytest.approx([per_child, per_child])
        assert sub["spent_from_allowance_usd"] == pytest.approx(sub["spent_usd"])
        assert all(n["status"] == "captured" and n["funded_by"] == "allowance" for n in sub["nodes"])
        # The buyer paid the composite plus exactly its materials, nothing else.
        assert buyer_left == pytest.approx(1.0 - 0.010 - 2 * per_child)
        # Linkage and money stay on this hub: the peer never sees the token or the grant.
        for sent in providers.seen[PEER_INVOKE]:
            assert subcontract.JOB_HEADER not in sent and subcontract.GRANT_HEADER not in sent
            assert sent.get("X-API-Key") in (None, "aimk_this_hubs_account_at_the_peer")

    def test_the_root_receipt_commits_to_the_federated_childrens_receipts(self, monkeypatch, tmp_path):
        pytest.importorskip("aimarket_provenance")
        env, _ = FED_CONFIGS["seller_of_record"]
        with federated_world(monkeypatch, tmp_path, **env) as (client, db, providers):
            digests: list[str] = []

            async def brief(body, headers, p):
                for child in (FED_WEATHER, FED_AIR):
                    r = await p.buy(child, job_headers(headers))
                    assert r.status_code == 200, r.text
                    digests.append(r.json()["provenance_receipt"]["digest_sri"])
                return 200, {"result": {"ok": True}}

            providers.add("https://brief.test/invoke", brief)
            _, api_key = _buyer(client, db)
            r = client.post("/ai-market/v2/invoke", headers={"X-API-Key": api_key},
                            json={**BRIEF, "subcontract": {"allowance_usd": 0.01}})
            assert r.status_code == 200, r.text
            body = r.json()
            assert sorted(n["receipt_digest"] for n in body["subcontracting"]["nodes"]) == sorted(digests)
            document = client.get(body["provenance_receipt"]["receipt_url"]).json()
            document = document.get("receipt", document)
            assert sorted(p["digestSRI"] for p in document["credentialSubject"]["parents"]) == sorted(digests)

    def test_a_peer_refusal_hands_price_and_fee_back_to_the_allowance(self, monkeypatch, tmp_path):
        env, _ = FED_CONFIGS["resale"]
        with federated_world(monkeypatch, tmp_path, peer_ok=False, **env) as (client, db, providers):
            outcomes = []

            async def brief(body, headers, p):
                for child in (FED_WEATHER, FED_AIR):
                    r = await p.buy(child, job_headers(headers))
                    outcomes.append((r.status_code, r.json().get("success")))
                return 200, {"result": {"ok": True}}

            providers.add("https://brief.test/invoke", brief)
            account, api_key = _buyer(client, db)
            r = client.post("/ai-market/v2/invoke", headers={"X-API-Key": api_key},
                            json={**BRIEF, "subcontract": {"allowance_usd": 0.01}})
            sub = r.json()["subcontracting"]
            buyer_left = balance(db, account)
        # GAIA's honest refusal is passed through, and nothing is billed for it.
        assert outcomes == [(200, False), (200, False)]
        assert [(n["status"], n["price_usd"]) for n in sub["nodes"]] == [("failed", 0.0), ("failed", 0.0)]
        assert sub["spent_usd"] == 0 and sub["released_usd"] == pytest.approx(0.01)
        assert buyer_left == pytest.approx(1.0 - 0.010)

    def test_a_federated_child_needs_its_source_hub(self, monkeypatch, tmp_path):
        """Without source_hub the hub looks for a LOCAL capability, finds only the peer's
        listing and says which source_hub to send; the attempt costs nothing."""
        env, _ = FED_CONFIGS["seller_of_record"]
        with federated_world(monkeypatch, tmp_path, **env) as (client, db, providers):
            seen = {}

            async def brief(body, headers, p):
                r = await p.buy({**FED_WEATHER, "source_hub": "local"}, job_headers(headers))
                seen["r"] = (r.status_code, r.json().get("detail", ""))
                return 200, {"result": {"ok": True}}

            providers.add("https://brief.test/invoke", brief)
            account, api_key = _buyer(client, db)
            r = client.post("/ai-market/v2/invoke", headers={"X-API-Key": api_key},
                            json={**BRIEF, "subcontract": {"allowance_usd": 0.01}})
            sub = r.json()["subcontracting"]
            buyer_left = balance(db, account)
        status, detail = seen["r"]
        assert status == 400 and f'source_hub="{PEER}"' in detail
        assert [n["status"] for n in sub["nodes"]] == ["failed"]
        assert sub["spent_usd"] == 0
        assert PEER_INVOKE not in providers.seen
        assert buyer_left == pytest.approx(1.0 - 0.010)


def test_the_grant_never_travels_in_clear_text_to_a_public_provider(monkeypatch, tmp_path):
    """The grant spends the buyer's allowance. A provider registered at a plain-http public
    URL gets the job token (linkage) but not the grant, so it pays its own subcontractors."""
    with hub(monkeypatch, tmp_path) as (client, db):
        providers = Providers(client.app_ref)
        import aimarket_hub.outbound_http as outbound

        monkeypatch.setattr(outbound, "safe_post", providers.post)
        list_provider(db, "brief.make@v1", "brief", 0.010, url="http://brief.test/invoke")

        async def brief(body, headers, p):
            return 200, {"result": {"ok": True}}

        providers.add("http://brief.test/invoke", brief)
        account, api_key = _buyer(client, db)
        r = client.post("/ai-market/v2/invoke", headers={"X-API-Key": api_key},
                        json={**BRIEF, "subcontract": {"allowance_usd": 0.005}})
        assert r.status_code == 200, r.text
        seen = providers.seen["http://brief.test/invoke"][0]
        assert subcontract.JOB_HEADER in seen
        assert subcontract.GRANT_HEADER not in seen
        # The unspent allowance came back in full.
        assert r.json()["subcontracting"]["released_usd"] == pytest.approx(0.005)
        assert balance(db, account) == pytest.approx(1.0 - 0.010)


@pytest.mark.parametrize("url,ok", [
    ("https://brief.test/invoke", True),
    ("http://brief.test/invoke", False),
    ("http://127.0.0.1:9000/invoke", True),
    ("http://localhost:9000/invoke", True),
    ("http://203.0.113.9/invoke", False),
    ("ftp://brief.test/invoke", False),
    ("", False),
])
def test_where_a_grant_may_be_sent(url, ok, monkeypatch):
    from aimarket_hub import invoke_funding

    monkeypatch.delenv("AIMARKET_INVOKE_HOST_GATEWAY", raising=False)
    assert invoke_funding.grant_may_travel_to(url) is ok
    monkeypatch.setenv("AIMARKET_INVOKE_HOST_GATEWAY", "kova-api")
    assert invoke_funding.grant_may_travel_to("http://kova-api:8000/invoke") is True
